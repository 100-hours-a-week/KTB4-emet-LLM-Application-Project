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



## <-------------------------------------------------- < 미사용 > ------------------------------------------>



async def node_llm(state: OverrallState):

    llm_model = llm.llm_loader()
    human_msg = HumanMessage(content=state["query"])
    full_messages = state["messages"] + [human_msg]

    answer = ""
    async for chunk in llm_model.astream(full_messages):
        print(chunk.content, end="", flush=True)
        answer += chunk.content

    ai_msg = AIMessage(content=answer)

    return {"messages": [human_msg, ai_msg], "answer": answer}
