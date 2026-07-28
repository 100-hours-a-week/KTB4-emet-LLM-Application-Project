import re
from states import OverrallState
from schems import OptionMatchResult, StructuredRecipe
from pydantic import ValidationError
import ingestion.loader as loader
import ingestion.template as template


## present_recipe_options와 반드시 같은 정렬 기준을 써야 번호가 일치함
def _sorted_options(options):
    return sorted(options, key=lambda o: len(o.needed_ingredients))


def _invalid_response(options):
    lines = ["죄송해요, 목록에 있는 번호나 요리 이름으로 다시 말씀해 주세요.\n"]
    for idx, opt in enumerate(options, start=1):
        lines.append(f"{idx}. {opt.title}")
    return {
        "answer": "\n".join(lines),
        "selected_option": None,
    }


## fetch_rag_recipe, finalize_recipe가 공통으로 쓰는 헬퍼이므로 파일 상단에 둠
## (이전에는 fetch_rag_recipe 안에 중첩 함수로만 있어서 finalize_recipe에서 못 봤음)
def _format_ingredient(item):
    name, amount, unit = item
    if amount == -1:
        return name
    return f"{name} {amount}{unit}".strip()


## 사용자의 선택 발화에서 유효한 옵션을 찾아 매칭 (번호 -> 부분일치 -> LLM 순)
def select_recipe_option(state: OverrallState):
    print("\n현재노드: select_recipe_option\n")

    query = state["query"]
    options = _sorted_options(state["recipe_options"])

    ## 1) 번호로 골랐는지 우선 확인 (결정론적, LLM 호출 없음)
    match = re.search(r"\d+", query)
    if match:
        idx = int(match.group()) - 1
        if 0 <= idx < len(options):
            print(f"번호 매칭 성공: {idx + 1}번")
            return {"selected_option": options[idx]}

    ## 2) 부분 일치 시도 (오타 없는 경우 LLM 호출 없이 빠르게 처리)
    candidates = [
        opt for opt in options
        if opt.title in query or query in opt.title
    ]
    if len(candidates) == 1:
        print(f"부분 일치 성공: {candidates[0].title}")
        return {"selected_option": candidates[0]}

    ## 3) 오타/표현 차이 대응을 위한 LLM 매칭 (앞 두 단계가 실패했을 때만 호출)
    llm_model = loader.llm_loader()
    option_match_model = llm_model.with_structured_output(
        OptionMatchResult, method="json_schema"
    )
    option_titles = "\n".join(f"- {opt.title}" for opt in options)
    query_option_match = template.option_match_prompt.format(
        option_titles=option_titles, query=query
    )

    try:
        result = option_match_model.invoke(query_option_match)
    except ValidationError as e:
        print(f"검증 실패: {e}")
        return _invalid_response(options)

    if result.matched_title:
        for opt in options:
            if opt.title.strip() == result.matched_title.strip():
                print(f"LLM 매칭 성공: {opt.title}")
                return {"selected_option": opt}

    print("매칭 실패: 무효 처리")
    return _invalid_response(options)


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

    ingredients_str = ", ".join(_format_ingredient(item) for item in matched.ingredients)
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
    llm_model = loader.llm_loader()
    finalize_recipe_model = llm_model.with_structured_output(
        StructuredRecipe, method="json_schema"
    )
    query_finalize_recipe = template.finalize_recipe_from_preview_prompt.format(
        ingredients=state["ingredient_list"].ingredients_name,
        selected_title=selected.title,
        needed_ingredients=selected.needed_ingredients,
    )

    try:
        result = finalize_recipe_model.invoke(query_finalize_recipe)
    except ValidationError as e:
        print(f"검증 실패: {e}")
        return {
            "answer": "죄송해요, 레시피를 완성하는 데 문제가 생겼어요. 다시 시도해 주세요.",
            "structured_recipe": None,
        }

    ingredients_str = ", ".join(_format_ingredient(item) for item in result.ingredients)
    answer = (
        f"[{result.title}] ({result.servings}인분 / {result.cook_time}분)\n\n"
        f"재료: {ingredients_str}\n\n"
        f"{result.steps}"
    )

    return {"structured_recipe": result, "answer": answer}