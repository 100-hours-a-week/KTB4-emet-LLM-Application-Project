import json

from schems import (
    StructuredRecipe,
    RecipeList,
    IngredientList,
    OptionMatchResult,
)
from pydantic import ValidationError

import llm
from templates import recipes_prompts
from states import OverrallState
from . import preview_recipes

from dotenv import load_dotenv
load_dotenv()

## graph.py에서 초기화된 retriever가 주입됩니다.
retriever = None


def invalid_response(options):
    lines = ["죄송해요, 목록에 있는 번호나 요리 이름으로 다시 말씀해 주세요.\n"]
    for idx, opt in enumerate(options, start=1):
        lines.append(f"{idx}. {opt.title}")
    return {
        "answer": "\n".join(lines),
        "selected_option": None,
    }


## fetch_rag_recipe, finalize_recipe가 공통으로 쓰는 헬퍼이므로 파일 상단에 둠
def format_ingredient(item):
    name, amount, unit = item
    if amount == -1:
        return name
    return f"{name} {amount}{unit}".strip()


## 재료 기반 레시피 검색
async def retreiver_recipes(state: OverrallState):
    print("\n현재노드: retreiver_recipes\n")
    global retriever

    ingredient_names = state["ingredient_list"].ingredients_name
    print(ingredient_names)

    ## 재료가 하나도 추출되지 않았으면 검색 불가 (빈 쿼리는 임베딩 API가 400으로 거부)
    if not ingredient_names:
        print("[DEBUG] 추출된 재료 없음 -> 레시피 검색 건너뜀")
        return {"retrieved_recipes": RecipeList(recipes=[])}

    search_query = ", ".join(ingredient_names)
    docs = await retriever.ainvoke(search_query)
    print("DEBUG metadata:", docs[0].metadata)
    print(f"[DEBUG] 검색된 레시피 수: {len(docs)}")
    print(f"[DEBUG] 레시피 미리보기: {[d.page_content[:50] for d in docs]}")

    ## page_content는 StructuredRecipe 필드 그대로의 JSON 문자열이므로 파싱해서
    ## StructuredRecipe 인스턴스로 변환한다.
    recipes = []
    for d in docs:
        try:
            data = json.loads(d.page_content)
            recipes.append(StructuredRecipe(**data))
        except (json.JSONDecodeError, ValidationError) as e:
            ## 파싱 실패한 문서는 건너뛰고 계속 진행 (전체 검색을 중단시키지 않음)
            print(f"[WARN] 레시피 파싱 실패, 스킵: {e}")
            continue

    return {"retrieved_recipes": RecipeList(recipes=recipes)}


## 사용자의 선택 발화를 LLM이 바로 판단해 번호로 매칭
## (번호 정규식/부분일치 휴리스틱은 "2번 말고 3번" 같은 발화를 오판해서 제거)
def select_recipe_option(state: OverrallState):
    print("\n현재노드: select_recipe_option\n")

    query = state["query"]
    options = preview_recipes.sort_options(state["recipe_options"])

    ## present_recipe_options가 보여준 번호와 동일한 순서로 번호를 매겨 전달
    option_titles = "\n".join(
        f"{idx}. {opt.title}" for idx, opt in enumerate(options, start=1)
    )
    query_option_match = recipes_prompts.option_match_prompt.format(
        option_titles=option_titles, query=query
    )

    result = llm.invoke_structured(OptionMatchResult, query_option_match, fallback=None)
    if result is None or result.selected_number is None:
        print("매칭 실패: 무효 처리")
        return invalid_response(options)

    idx = result.selected_number - 1
    if not (0 <= idx < len(options)):
        print(f"범위 밖 번호: {result.selected_number}")
        return invalid_response(options)

    selected = options[idx]
    print(f"LLM 매칭 성공: {result.selected_number}번 {selected.title}")
    return {"selected_option": selected}


## 다음 노드 선택
def conditional_select_recipe_option(state: OverrallState):
    selected = state.get("selected_option")

    if selected is None:
        return "invalid"

    if selected.source == "generated":
        return "finalize_recipe"

    return "fetch_rag_recipe"


## RAG 출처 옵션 선택 시: 이미 정형화된 레시피를 recipe_id로 재조회 (LLM 호출 없음)
def fetch_rag_recipe(state: OverrallState):
    print("\n현재노드: fetch_rag_recipe\n")

    selected = state["selected_option"]
    recipe_id = selected.recipe_id

    matched = None
    for recipe in state["retrieved_recipes"].recipes:
        if recipe.recipe_id == recipe_id:
            matched = recipe
            break

    if matched is None:
        ## 정상적으로는 발생하면 안 되는 상황 (retrieved_recipes에 있던 옵션인데 못 찾음)
        print(f"[WARN] recipe_id={recipe_id} 재조회 실패")
        return {
            "answer": "죄송해요, 선택하신 레시피를 다시 찾지 못했어요. 다시 시도해 주세요.",
            "structured_recipe": None,
        }

    ingredients_str = ", ".join(format_ingredient(item) for item in matched.ingredients)
    answer = (
        f"[{matched.title}] ({matched.servings}인분 / {matched.cook_time}분)\n\n"
        f"재료: {ingredients_str}\n\n"
        f"{matched.steps}"
    )

    return {"structured_recipe": matched, "answer": answer}


## LLM 생성 옵션 선택 시: title/추가재료를 고정한 채 정식 레시피 완성
def finalize_recipe(state: OverrallState):
    print("\n현재노드: finalize_recipe\n")

    selected = state["selected_option"]
    query_finalize_recipe = recipes_prompts.finalize_from_preview_prompt.format(
        ingredients=state["ingredient_list"].ingredients_name,
        selected_title=selected.title,
        needed_ingredients=selected.needed_ingredients,
    )

    result = llm.invoke_structured(StructuredRecipe, query_finalize_recipe, fallback=None)
    if result is None:
        return {
            "answer": "죄송해요, 레시피를 완성하는 데 문제가 생겼어요. 다시 시도해 주세요.",
            "structured_recipe": None,
        }

    ingredients_str = ", ".join(format_ingredient(item) for item in result.ingredients)
    answer = (
        f"[{result.title}] ({result.servings}인분 / {result.cook_time}분)\n\n"
        f"재료: {ingredients_str}\n\n"
        f"{result.steps}"
    )

    return {"structured_recipe": result, "answer": answer}


## 재료 기반 레시피 생성
### 임시 미사용 노드
### -> 프리뷰레시피 옵션 -> 파이널 라이즈
def generate_recipe(state: OverrallState):
    print("\n현재노드: generate_recipe\n")
    ## query_analysis -> now -> node_llm -> confirm_ingrediant

    ## undeveloped(): query -> ingrediant
    ## query_reipes = recipes_prompts.generate_prompt.format(query=state["query"], ingrediant=state["ingrediant"])
    getnerate_recipe_model = llm.get_llm()
    ingredients = state["ingredient_list"].ingredients_name
    query_getnerate_recipe = recipes_prompts.generate_prompt.format(ingredients=ingredients)

    try:
        result = getnerate_recipe_model.invoke(query_getnerate_recipe)
        print(type(result), result)
    except Exception as e:
        print(f"생성 실패: {e}")
        result = IngredientList(ingredients=[])

    return {"query": query_getnerate_recipe}


