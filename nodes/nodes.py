from langchain_core.messages import HumanMessage, AIMessage

import llm
from states import OverrallState

from dotenv import load_dotenv
load_dotenv()


## 미개발구간 출력
## 개발 진행중인 구간은 주석형태로 표시
def undeveloped(state: OverrallState):
    print("해당 구간은 아직 미개발입니다. 감사합니다.")
    return {"answer": f"죄송합니다. 해당 기능은 아직 개발 중입니다.{state["query_type"]}"}


def format_docs(ds):
    return "\n\n".join(d.page_content for d in ds)



def respond_infeasible(state: OverrallState):
    result = state["ingredient_analysis_result"]
    reason = result.reason or "재료 조합상 적절한 요리를 만들기 어려워요."
    current_ingredients = state["ingredient_list"].ingredients_name
    answer = (
        f"📋 현재 재료: {', '.join(current_ingredients)}\n\n"
        f"죄송해요, 이 재료로는 요리를 만들기 어려울 것 같아요.\n이유: {reason}"
    )
    return {"answer": answer}

## <-------------------------------------------------- < 미사용 > ------------------------------------------>



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




