"""
요리 이름 검색 흐름에서 RAG에 없는 요리를 LLM이 생성하기 전, 실존 여부를
확인하기 위한 웹 검색 모듈. SEARCH_PROVIDER 환경변수로 공급자를 스위칭한다
(llm.py의 LLM_PROVIDER 패턴과 동일 — 상위 코드는 어떤 엔진을 쓰는지 몰라도 됨).

현재 지원: tavily
"""
import os

from dotenv import load_dotenv
load_dotenv()


def web_search(query: str, max_results: int = 5) -> str:
    """검색 결과를 LLM 프롬프트에 바로 넣을 수 있는 텍스트로 반환.
    실패 시(키 미설정, 네트워크 오류 등) 빈 문자열을 반환해 상위 프롬프트가
    "검색 결과 없음"으로 자연스럽게 처리하게 한다 (검색 실패가 곧 "실존하지
    않는 요리"로 오판되지 않도록, 프롬프트에서 빈 결과와 무관 결과를 구분해야 함)."""
    provider = os.getenv("SEARCH_PROVIDER", "tavily")
    try:
        if provider == "tavily":
            return _search_tavily(query, max_results)
        raise ValueError(f"지원하지 않는 SEARCH_PROVIDER: {provider}")
    except Exception as e:
        print(f"[web_search] 검색 실패(provider={provider}): {e}")
        return ""


def _search_tavily(query: str, max_results: int) -> str:
    from tavily import TavilyClient

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY가 설정되지 않았습니다.")

    client = TavilyClient(api_key=api_key)
    response = client.search(query, max_results=max_results, include_answer=True)

    lines = []
    if response.get("answer"):
        lines.append(f"요약: {response['answer']}")
    for r in response.get("results", []):
        title = r.get("title", "")
        content = r.get("content", "")
        lines.append(f"- {title}: {content}")

    return "\n".join(lines)
