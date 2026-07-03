from langgraph.graph import StateGraph, START, END, MessagesState
from langchain_core.messages import HumanMessage, AIMessage

from states import StateExample


# === 첫 번째 병렬 검색 노드 ===
def search_a(state: StateExample) -> dict:
    return {
        "message": state["message"],
        "results": ["결과 A"],
        "count": 1,
    }

# === 두 번째 병렬 검색 노드 ===
def search_b(state: StateExample) -> dict:
    return {
        "message": state["message"],
        "results": ["결과 B"],
        "count": 10,
    }

# 1차 질문: 레시피 추천해주기
## 자동으로 메세지 이어서 concat            <- 에러 발생지점
def recommand_receipe(state: MessagesState) -> dict:
    user_msg = state["messages"][-1].content
    reply = AIMessage(content=f"'{user_msg}'에 대한 답변")
    return {"messages": [reply]}




def build_struct():

    builder = StateGraph(StateExample)

    builder.add_node("search_a", search_a)
    builder.add_node("search_b", search_b)
    builder.add_node("recommand_receipe", recommand_receipe)

    builder.add_edge(START, "search_a")
    builder.add_edge(START, "search_b")
    builder.add_edge("search_a", "recommand_receipe")
    builder.add_edge("search_b", "recommand_receipe")
    builder.add_edge("recommand_receipe", END)

    return builder


def run():
    builder = build_struct()
    graph = builder.compile()

    ## 스트리밍으로 변경예정
    result = graph.invoke({
        "count": 0, "results":[],"message": [HumanMessage(content="쌀밥,계란,대파,소금으로 만들 수 있는 요리 레시피 알려줘.")]
    })

    print(result["count"])
    print(result["results"])
    print(result["message"])


run()   