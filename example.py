"""
LangGraph Conditional Edges 예제
배송·환불 문서 기반 RAG를 통해
동적 제어 방식과 잘못 설계된 흐름을 비교합니다.

설치:
    pip install langgraph langchain-anthropic --break-system-packages
"""

from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage


# ──────────────────────────────────────────────
# 공통: 상태 정의
# ──────────────────────────────────────────────
class RAGState(TypedDict):
    messages: Annotated[list, add_messages]
    context: str        # 검색된 청크 내용
    quality: str        # "sufficient" | "insufficient"
    retry_count: int    # 재검색 횟수


# ──────────────────────────────────────────────
# 공통: 노드 함수들
# ──────────────────────────────────────────────
CHUNKS = {
    "환불": "환불은 7일 이내 가능. 세일 상품은 환불 불가. 교환은 환불과 동일 절차.",
    "배송": "배송은 평균 3일. 제주·도서 지역은 추가 2일.",
}


def retrieve(state: RAGState) -> RAGState:
    """질문 키워드로 관련 청크 검색"""
    query = state["messages"][-1].content
    if "환불" in query or "세일" in query:
        keyword = "환불"
    elif "배송" in query:
        keyword = "배송"
    else:
        keyword = None
    context = CHUNKS.get(keyword, "관련 문서 없음") if keyword else "관련 문서 없음"
    print(f"  [retrieve] 키워드={keyword}, 청크={context[:30]}...")
    return {"context": context}


def generate(state: RAGState) -> RAGState:
    """검색된 Context로 답변 생성 (실제로는 LLM 호출)"""
    answer = f"[LLM 답변] Context 기반 답변: {state['context']}"
    print(f"  [generate] {answer}")
    return {"messages": [AIMessage(content=answer)]}


# ──────────────────────────────────────────────
# ══════════════════════════════════════════════
# 1. 정상 케이스
#    품질이 충분하면 → generate
#    부족하면 → retrieve 재시도 (최대 2회)
# ══════════════════════════════════════════════
# ──────────────────────────────────────────────
def evaluate_correct(state: RAGState) -> RAGState:
    """[정상] context가 있으면 sufficient, 없으면 insufficient"""
    quality = "sufficient" if state["context"] != "관련 문서 없음" else "insufficient"
    count = state.get("retry_count", 0)
    print(f"  [evaluate] quality={quality}, retry={count}")
    return {"quality": quality, "retry_count": count + 1}


def route_correct(state: RAGState) -> str:
    """[정상] Conditional Edge 함수 — 품질과 재시도 횟수로 분기"""
    if state["quality"] == "sufficient":
        return "generate"       # 충분하면 응답 생성
    elif state["retry_count"] >= 2:
        return "generate"       # 최대 재시도 초과 시 강제 종료
    else:
        return "retrieve"       # 부족하면 재검색


def build_correct_graph() -> StateGraph:
    g = StateGraph(RAGState)
    g.add_node("retrieve", retrieve)
    g.add_node("evaluate", evaluate_correct)
    g.add_node("generate", generate)

    g.set_entry_point("retrieve")
    g.add_edge("retrieve", "evaluate")
    g.add_conditional_edges(
        "evaluate",
        route_correct,
        {
            "generate": "generate",   # sufficient → generate
            "retrieve": "retrieve",   # insufficient → 재검색
        }
    )
    g.add_edge("generate", END)
    return g.compile()


# ──────────────────────────────────────────────
# ══════════════════════════════════════════════
# 문제 케이스 1: 조건 함수가 항상 "insufficient" 반환
#               → 무한 루프 (여기서는 max_steps로 강제 중단)
# ══════════════════════════════════════════════
# ──────────────────────────────────────────────
def evaluate_always_insufficient(state: RAGState) -> RAGState:
    """[문제1] 버그: context 내용과 무관하게 항상 insufficient"""
    print(f"  [evaluate-bug1] 항상 insufficient 반환")
    return {"quality": "insufficient", "retry_count": state.get("retry_count", 0) + 1}


def route_bug1(state: RAGState) -> str:
    """[문제1] 항상 retrieve로만 분기 → 무한 루프"""
    if state["retry_count"] >= 3:   # 데모용 강제 탈출 (실제 버그 상황엔 없음)
        print("  [route-bug1] 강제 탈출 (실제론 무한 루프)")
        return "generate"
    return "retrieve"               # 항상 재검색 → 루프


def build_bug1_graph() -> StateGraph:
    g = StateGraph(RAGState)
    g.add_node("retrieve", retrieve)
    g.add_node("evaluate", evaluate_always_insufficient)
    g.add_node("generate", generate)

    g.set_entry_point("retrieve")
    g.add_edge("retrieve", "evaluate")
    g.add_conditional_edges(
        "evaluate",
        route_bug1,
        {"retrieve": "retrieve", "generate": "generate"}
    )
    g.add_edge("generate", END)
    return g.compile()


# ──────────────────────────────────────────────
# ══════════════════════════════════════════════
# 문제 케이스 2: 조건 함수가 엣지 맵에 없는 키 반환
#               → KeyError 런타임 오류
# ══════════════════════════════════════════════
# ──────────────────────────────────────────────
def route_bug2(state: RAGState) -> str:
    """[문제2] 오타: 엣지 맵 키와 불일치하는 값 반환"""
    # 엣지 맵에는 "generate", "retrieve"만 등록했는데
    # 아래처럼 오타로 "regenerate"를 반환하면 KeyError 발생
    return "regenerate"     # ← 오타! 엣지 맵에 없는 키


def build_bug2_graph() -> StateGraph:
    g = StateGraph(RAGState)
    g.add_node("retrieve", retrieve)
    g.add_node("evaluate", evaluate_correct)
    g.add_node("generate", generate)

    g.set_entry_point("retrieve")
    g.add_edge("retrieve", "evaluate")
    g.add_conditional_edges(
        "evaluate",
        route_bug2,
        {
            "generate": "generate",   # "regenerate"는 여기 없음 → KeyError
            "retrieve": "retrieve",
        }
    )
    g.add_edge("generate", END)
    return g.compile()


# ──────────────────────────────────────────────
# ══════════════════════════════════════════════
# 문제 케이스 3: 카운터 없이 루프 — 탈출 조건 자체가 없음
#               → 비용 폭증·타임아웃
# ══════════════════════════════════════════════
# ──────────────────────────────────────────────
def route_bug3(state: RAGState) -> str:
    """[문제3] 재시도 횟수 확인 없이 품질만 보고 분기
       → context가 없는 질문이 들어오면 영원히 retrieve 반복"""
    if state["quality"] == "sufficient":
        return "generate"
    return "retrieve"       # 카운터 체크 없음 → 탈출 불가


def build_bug3_graph() -> StateGraph:
    g = StateGraph(RAGState)
    g.add_node("retrieve", retrieve)
    g.add_node("evaluate", evaluate_correct)
    g.add_node("generate", generate)

    g.set_entry_point("retrieve")
    g.add_edge("retrieve", "evaluate")
    g.add_conditional_edges(
        "evaluate",
        route_bug3,
        {"generate": "generate", "retrieve": "retrieve"}
    )
    g.add_edge("generate", END)
    return g.compile()


# ──────────────────────────────────────────────
# 실행
# ──────────────────────────────────────────────
INIT_STATE: RAGState = {
    "messages": [HumanMessage(content="세일 상품도 환불이 되나요?")],
    "context": "",
    "quality": "",
    "retry_count": 0,
}

if __name__ == "__main__":

    # ── 정상 케이스 ──
    print("=" * 50)
    print("정상 케이스")
    print("=" * 50)
    app = build_correct_graph()
    result = app.invoke(INIT_STATE)
    print(f"최종 답변: {result['messages'][-1].content}\n")

    # ── 문제 케이스 1 ──
    print("=" * 50)
    print("문제 케이스 1 — 항상 insufficient (데모용 강제 탈출 포함)")
    print("=" * 50)
    app1 = build_bug1_graph()
    result1 = app1.invoke(INIT_STATE)
    print(f"최종 상태 retry_count: {result1['retry_count']}\n")

    # ── 문제 케이스 2 ──
    print("=" * 50)
    print("문제 케이스 2 — 오타 KeyError")
    print("=" * 50)
    app2 = build_bug2_graph()
    try:
        app2.invoke(INIT_STATE)
    except Exception as e:
        print(f"오류 발생: {type(e).__name__} — {e}\n")

    # ── 문제 케이스 3 ──
    print("=" * 50)
    print("문제 케이스 3 — 카운터 없는 루프 (존재하지 않는 키워드 질문)")
    print("  실제로는 무한 루프이므로 recursion_limit으로 강제 중단")
    print("=" * 50)
    app3 = build_bug3_graph()
    bad_state: RAGState = {
        "messages": [HumanMessage(content="멤버십 혜택이 뭐야?")],  # 매칭 키워드 없음
        "context": "",
        "quality": "",
        "retry_count": 0,
    }
    try:
        app3.invoke(bad_state, config={"recursion_limit": 5})
    except Exception as e:
        print(f"오류 발생: {type(e).__name__} — {e}")
        print("→ 재검색 탈출 조건이 없어 recursion_limit에 걸림\n")



mermaid_code = app.get_graph().draw_mermaid()
print(mermaid_code)
