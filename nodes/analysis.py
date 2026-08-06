from schems import QueryType, IngredientAnalysisResult, IngredientFeasibility
from food_combination_matcher import check_all

import llm
from templates import analysis_prompts
from states import OverrallState

from dotenv import load_dotenv
load_dotenv()


## 최근 대화 몇 턴을 프롬프트에 넣을 텍스트로 정리
def format_recent_context(messages, max_turns=3):
    if not messages:
        return "(이전 대화 없음)"

    recent = messages[-(max_turns * 2):]
    lines = []
    for m in recent:
        role = "사용자" if m.type == "human" else "AI"
        lines.append(f"{role}: {m.content}")

    return "\n".join(lines) if lines else "(이전 대화 없음)"


## 질의 분석
def query_analysis(state: OverrallState):
    print("현재노드: query_analysis")
    recent_context = format_recent_context(state.get("messages", []))
    query_analysis_query = analysis_prompts.query_prompt.format(
        query=state["query"],
        recent_context=recent_context,
    )

    ## 분류 실패 시 "NONE"으로 폴백 -> conditional_query_type에서 undeveloped로 라우팅됨
    result = llm.invoke_structured(
        QueryType, query_analysis_query, fallback=None
    )

    print(type(result), result)

    return {"query_type": result}


## 다음 노드 선택
def conditional_query_type(state: OverrallState):
    print("현재 컨디셔널함수:conditional_query_type")
    print(state["query_type"])
    qurey_type = state["query_type"].type
    if qurey_type == "레시피 추천":
        return "reset_recipe_options"
    elif qurey_type == "레시피 선택":
            return "select_recipe_option"
    elif qurey_type == "레시피 이름 검색":
        ## dish_name 추출에 실패하면(방어적으로) 검색을 시도하지 않고 안내로 빠진다
        if state["query_type"].dish_name:
            return "search_by_name"
        return "respond_unrealated"
    elif qurey_type == "NONETYPE":
        return "respond_undevopled"
    elif qurey_type == "NONE":
        return "respond_unrealated"

    return "respond_unrealated"

## 재료 조합 경고 메시지 리스트 생성 (LLM 호출 없음 — 순수 코드)
def build_combination_warnings(ingredient_names: list[str]) -> list[str] | None:
    result = check_all(ingredient_names)
    warnings = []

    for item in result["pair_matches"]:
        a, b = item["pair"]
        warnings.append(f"{a}+{b}: {item['reason']} ({item['level']})")

    for item in result["category_matches"]:
        warnings.append(f"{', '.join(item['categories'])}: {item['reason']} ({item['level']})")

    return warnings if warnings else None

## 추출한 재료 검토
def ingredient_analysis(state: OverrallState):
    print("현재노드: ingredient_analysis")

    ingredient_names = state["ingredient_list"].ingredients_name

    query_ingredient_analysis = analysis_prompts.ingredient_prompt.format(
        ingredients=ingredient_names
    )

    ## 판정 실패 시 안전하게 "생성 불가"로 처리 (undeveloped로 라우팅됨)
    result = llm.invoke_structured(
        IngredientFeasibility, query_ingredient_analysis, fallback=None
    )

    ## 궁합 체크는 feasibility 판정과 무관하게 항상 수행 (LLM 호출 없음, 순수 코드)
    combination_warnings = build_combination_warnings(ingredient_names)

    ingredient_analysis_result = IngredientAnalysisResult(
        feasibility=result.feasibility if result else "not_cookable",
        reason=result.reason if result else "재료 정보를 판정하는 중 문제가 발생했어요.",
        structured_recipe=None,
        needed_ingredients=None,
        combination_warnings=combination_warnings,
    )

    print(f"\n\ningredient_analysis_result: {ingredient_analysis_result}\n\n")

    return {"ingredient_analysis_result": ingredient_analysis_result}



## 다음 노드 선택
def conditional_ingredient_analysis(state: OverrallState):

    print("현재 컨디셔널함수: conditional_ingredient_analysis")
    feasibility = state["ingredient_analysis_result"].feasibility
    print(f"ingredient_analysis_result.feasibility: {feasibility}")

    if feasibility in ("directly_cookable", "needs_more_ingredients"):
        return "retreiver_recipes"

    elif feasibility == "not_cookable":
        return "respond_infeasible"

    print("conditional_ingredient_analysis 예외발생")
    return "undeveloped"
