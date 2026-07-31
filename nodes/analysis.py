from schems import QueryType, IngredientAnalysisResult, IngredientFeasibility

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
        QueryType, query_analysis_query, fallback=QueryType(type="NONE")
    )

    print(type(result), result)

    return {"query_type": result.type}


## 다음 노드 선택
def conditional_query_type(state: OverrallState):
    print("현재 컨디셔널함수:conditional_query_type")
    print(f"query_type: {state["query_type"]}")
    print(state["query_type"])
    if state["query_type"] == "레시피 추천":
        return "extract_ingredient"
    elif state["query_type"] == "레시피 선택":
            return "select_recipe_option"
    elif state["query_type"] == "레시피 반응":
        return "undeveloped"
    elif state["query_type"] == "NONETYPE":
        return "undeveloped"
    elif state["query_type"] == "NONE":
        return "undeveloped"

    return "undeveloped"


## 추출한 재료 검토
def ingredient_analysis(state: OverrallState):
    print("현재노드: ingredient_analysis")

    query_ingredient_analysis = analysis_prompts.ingredient_prompt.format(
        ingredients=state["ingredient_list"].ingredients_name
    )

    ## 판정 실패 시 안전하게 "생성 불가"로 처리 (undeveloped로 라우팅됨)
    result = llm.invoke_structured(
        IngredientFeasibility, query_ingredient_analysis, fallback=None
    )
    ingredient_analysis_result = IngredientAnalysisResult(
        feasibility=result.feasibility if result else "not_cookable",
        structured_recipe=None,
        needed_ingredients=None,
    )

    print(f"\n\ningredient_analysis_result: {ingredient_analysis_result}\n\n")

    return {"ingredient_analysis_result": ingredient_analysis_result}


## 다음 노드 선택
def conditional_ingredient_analysis(state: OverrallState):

    print("현재 컨디셔널함수: conditional_ingredient_analysis")
    feasibility = state["ingredient_analysis_result"].feasibility
    print(f"ingredient_analysis_result.feasibility: {feasibility}")

    if feasibility in ("directly_cookable", "needs_more_ingredients"):
        return ["preview_recipe_options", "retreiver_recipes"]

    elif feasibility == "not_cookable":
        print("배달이나 시켜드십쇼. ㅋㅋㅋㅋㅋㅋㅋㅋ")
        return "undeveloped"

    return "undeveloped"
