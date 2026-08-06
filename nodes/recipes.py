import json
import uuid
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
from rag.config import RECIPE_SITE_NAME, RECIPE_URL_TEMPLATE
from . import preview_recipes

from dotenv import load_dotenv
load_dotenv()

## graph.py에서 초기화된 retriever가 주입됩니다.
retriever = None

def _format_ingredient_item(item: list) -> str:
    """StructuredRecipe.ingredients의 [재료명, 양, 단위] 한 항목을 문자열로."""
    name, amount, unit = item
    if amount == -1:
        return name
    return f"{name} {amount}{unit}".strip()
 
 
def format_recipe_answer(recipe: StructuredRecipe) -> str:
    """완성된 StructuredRecipe를 사용자에게 보여줄 답변 문자열로 변환.
    finalize_recipe 신규 생성 / 캐시 재사용 양쪽에서 동일하게 사용."""
    ingredients_str = ", ".join(_format_ingredient_item(item) for item in recipe.ingredients)
    return (
        f"[{recipe.title}] ({recipe.servings}인분 / {recipe.cook_time}분)\n\n"
        f"재료: {ingredients_str}\n\n"
        f"{recipe.steps}"
    )


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


## RAG 검색 결과(Document 리스트)를 StructuredRecipe 리스트로 변환.
## page_content는 StructuredRecipe 필드 그대로의 JSON 문자열이므로 파싱만 하면 됨.
## retreiver_recipes(재료 기반 검색)와 name_search.search_by_name(이름 기반 검색)이 공유.
def parse_recipe_docs(docs) -> list[StructuredRecipe]:
    parsed = []
    for d in docs:
        try:
            data = json.loads(d.page_content)
            parsed.append(StructuredRecipe(**data))
        except (json.JSONDecodeError, ValidationError) as e:
            ## 파싱 실패한 문서는 건너뛰고 계속 진행 (전체 검색을 중단시키지 않음)
            print(f"[WARN] 레시피 파싱 실패, 스킵: {e}")
            continue
    return parsed


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

    ## 검색 결과가 0건이면 아래 docs[0] 접근이 IndexError가 되므로 먼저 빠져나간다
    if not docs:
        print("[DEBUG] 검색 결과 없음 -> 빈 레시피 목록 반환")
        return {"retrieved_recipes": RecipeList(recipes=[])}

    print("DEBUG metadata:", docs[0].metadata)
    print(f"[DEBUG] 검색된 레시피 수: {len(docs)}")
    print(f"[DEBUG] 레시피 미리보기: {[d.page_content[:50] for d in docs]}")

    return {"retrieved_recipes": RecipeList(recipes=parse_recipe_docs(docs))}


## 사용자의 선택 발화를 LLM이 바로 판단해 번호로 매칭
## (번호 정규식/부분일치 휴리스틱은 "2번 말고 3번" 같은 발화를 오판해서 제거)
def select_recipe_option(state: OverrallState):
    print("\n현재노드: select_recipe_option\n")

    query = state["query"]
    ## present_recipe_options와 정렬 기준뿐 아니라 자르는 개수까지 동일해야
    ## 번호가 어긋나지 않는다 (이전에는 슬라이스가 없어 화면에 없던 옵션도 매칭 후보가 됐음)
    options = preview_recipes.sort_options(state["recipe_options"])[:preview_recipes.PREVIEW_TOTAL_COUNT]

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

    ## RAG 출처 레시피에만 출처를 붙인다 (LLM 생성분은 finalize_recipe 경로라 여기 안 옴).
    ## recipe_id가 원본 사이트의 레시피 ID와 그대로 일치해서 정확한 링크를 만들 수 있음.
    if matched.recipe_id:
        source_url = RECIPE_URL_TEMPLATE.format(recipe_id=matched.recipe_id)
        answer += f"\n\n출처: {RECIPE_SITE_NAME} ({source_url})"

    return {"structured_recipe": matched, "answer": answer}


## LLM 생성 옵션 선택 시: title/추가재료를 고정한 채 정식 레시피 완성

def finalize_recipe(state: OverrallState):
    print("\n현재노드: finalize_recipe\n")
 
    selected = state["selected_option"]
    cache_key = f"{selected.source}:{selected.recipe_id}"
 
    finalized_recipes = state.get("finalized_recipes", {})
 
    ## 캐시 확인: 이미 만든 적 있는 요리면 재사용 (LLM 재호출 없음)
    if cache_key in finalized_recipes:
        print(f"캐시 적중: '{selected.title}' ({cache_key}) -> 재사용")
        cached_recipe = finalized_recipes[cache_key]
        return {
            "structured_recipe": cached_recipe,
            "answer": format_recipe_answer(cached_recipe),
        }
 
    ## 캐시 미스: 새로 생성
    print(f"캐시 미스: '{selected.title}' ({cache_key}) -> 신규 생성")
 
    query_finalize = recipes_prompts.finalize_from_preview_prompt.format(
        ingredients=state["ingredient_list"].ingredients_name,
        selected_title=selected.title,
        needed_ingredients=selected.needed_ingredients,
    )
 
    result = llm.invoke_structured(StructuredRecipe, query_finalize, fallback=None)
 
    if result is None:
        answer = "죄송해요, 레시피를 만드는 중 문제가 발생했어요. 다시 시도해주세요."
        return {"answer": answer}
 
    ## 생성된 레시피에도 이 세션에서 유일한 recipe_id 부여 (G 접두사 규칙 유지)
    if not result.recipe_id:
        result.recipe_id = f"G{uuid.uuid4().hex[:8]}"
 
    return {
        "structured_recipe": result,
        "finalized_recipes": {**finalized_recipes, cache_key: result},
        "answer": format_recipe_answer(result),
    }


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


