from langchain_core.messages import HumanMessage, AIMessage
from nodes.preview_recipes import evaluate_rag_options,compute_missing_ingredients
from schems import RecipeOption 
import llm
from states import OverrallState
import os
from dotenv import load_dotenv
load_dotenv()

PREVIEW_TOTAL_COUNT = int(os.getenv("PREVIEW_TOTAL_COUNT"))  ## 최종적으로 사용자에게 보여줄 전체 선택지 개수 (RAG 적합 + LLM 생성 합산)

## 미개발구간 출력
## 개발 진행중인 구간은 주석형태로 표시
def undeveloped(state: OverrallState):
    print("해당 구간은 아직 미개발입니다. 감사합니다.")
    return {"answer": f"죄송합니다. 해당 기능은 아직 개발 중입니다.{state["query_type"]}"}


def format_docs(ds):
    return "\n\n".join(d.page_content for d in ds)

def respond_undevopled(state: OverrallState):
    result = state["query_type"]
    reason = result.reason or "개발되지 않은 기능에 대한 요청"
    answer = (
        f"죄송해요, 해당 요청은 아직 개발되지 않은 저희 기능이입니다. 다른 요청 부탁드립니다.\n이유: {reason}"
    )
    return {"answer": answer}

def respond_unrealated(state: OverrallState):
    result = state["query_type"]
    reason = result.reason or "관련없는 요청"
    answer = (
        f"죄송해요, 해당 요청은 저희와 관련없는 기능이입니다. 다른 요청 부탁드립니다.\n이유: {reason}"
    )
    return {"answer": answer}


def respond_infeasible(state: OverrallState):
    result = state["ingredient_analysis_result"]
    reason = result.reason or "재료 조합상 적절한 요리를 만들기 어려워요."
    current_ingredients = state["ingredient_list"].ingredients_name
    answer = (
        f"📋 현재 재료: {', '.join(current_ingredients)}\n\n"
        f"죄송해요, 이 재료로는 요리를 만들기 어려울 것 같아요.\n이유: {reason}"
    )
    return {"answer": answer}

 
def rag_adequacy_check(state: OverrallState):
    """
    RAG 검색 결과(k=12로 늘린 것) 전체를 순회하며 적정성 평가.
    LLM 호출 없음. 적합 판정 상위 N개를 채택하고, 부족한 개수를 계산해
    preview_recipe_options가 몇 개를 생성해야 하는지 넘겨준다.
    """
    print("\n현재노드: rag_adequacy_check\n")
 
    rag_recipes = state["retrieved_recipes"].recipes
    user_ingredient_names = state["ingredient_list"].ingredients_name
 
    selected_recipes, shortfall = evaluate_rag_options(
        rag_recipes, user_ingredient_names, max_count=PREVIEW_TOTAL_COUNT
    )
 
    ## 적합 판정된 RAG 레시피들만 RecipeOption 형태로 변환
    rag_options = []
    for recipe in selected_recipes:
        recipe_names = {item[0] for item in recipe.ingredients if item}
        needed = compute_missing_ingredients(recipe_names, set(user_ingredient_names))
        rag_options.append(
            RecipeOption(
                title=recipe.title,
                source="rag",
                recipe_id=recipe.recipe_id,
                needed_ingredients=needed,
            )
        )
 
    print(f"적합 RAG 선택지: {len(rag_options)}개, 부족분: {shortfall}개")
 
    return {
        "rag_options": rag_options,
        "preview_needed_count": shortfall,
    }
 
"""
async def node_llm(state: OverrallState):

    llm_model = llm.get_llm()
    human_msg = HumanMessage(content=state["query"])
    full_messages = state["messages"] + [human_msg]

    ## 스트리밍 실패 시 사과 문구로 폴백 (부분 응답은 버림)
    try:
        answer = ""
        async for chunk in llm_model.astream(full_messages):
            print(chunk.content, end="", flush=True)
            answer += chunk.content
    except Exception as e:
        print(f"[node_llm] 호출 실패: {e}")
        answer = "죄송합니다. 답변 생성 중 문제가 발생했어요. 다시 시도해 주세요."

    ai_msg = AIMessage(content=answer)

    return {"messages": [human_msg, ai_msg], "answer": answer}
"""



