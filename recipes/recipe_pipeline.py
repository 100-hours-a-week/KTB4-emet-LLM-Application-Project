"""
레시피 수집 파이프라인 중앙센터 (LangGraph)

collect_recipe_links.py -> save_recipes_pdf.py -> structured.py
세 단계를 하나의 그래프로 묶어 순서대로 실행한다.
각 단계가 실패하면 다음 단계로 넘어가지 않고 즉시 종료한다.

사용법 (프로젝트 루트에서):
  uv run python details/recipe_pipeline.py "볶음밥" 20
  uv run python details/recipe_pipeline.py "볶음밥" 20 --start 0 --end 200
  uv run python details/recipe_pipeline.py "볶음밥" 20 --skip-collect   # 링크수집 건너뛰기
  uv run python details/recipe_pipeline.py "볶음밥" 20 --skip-pdf       # PDF저장 건너뛰기

* 3단계(structured)는 LLM_PROVIDER=ollama 이면 올라마가 켜져 있어야 함
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Literal, TypedDict

from langgraph.graph import StateGraph, START, END

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RECIPES_DIR = PROJECT_ROOT / "recipes"


# ---------------------------------------------------------------------------
# 상태 정의
# ---------------------------------------------------------------------------
class PipelineState(TypedDict):
    query: str            # 검색어
    max_pages: int        # 검색 결과 최대 페이지 수
    start: int            # PDF 저장 시작 인덱스
    end: int              # PDF 저장 끝 인덱스
    skip_collect: bool    # 1단계 건너뛰기 (recipe_ids.json 재사용)
    skip_pdf: bool        # 2단계 건너뛰기 (기존 PDF 재사용)
    last_step: str        # 마지막으로 실행한 단계 이름
    failed: bool          # 직전 단계 실패 여부
    error: str            # 실패 메시지


# ---------------------------------------------------------------------------
# 공통 실행 헬퍼: 서브프로세스로 실행하며 출력을 실시간으로 그대로 보여줌
# ---------------------------------------------------------------------------
def run_step(name: str, cmd: list[str], cwd: Path) -> tuple[bool, str]:
    print(f"\n{'=' * 60}")
    print(f"[{name}] 실행: {' '.join(cmd)}  (cwd={cwd})")
    print(f"{'=' * 60}")

    proc = subprocess.run(cmd, cwd=cwd)

    if proc.returncode != 0:
        msg = f"{name} 단계가 종료코드 {proc.returncode}로 실패"
        print(f"\n[{name}] 실패: {msg}")
        return False, msg

    print(f"\n[{name}] 완료")
    return True, ""


# ---------------------------------------------------------------------------
# 노드 정의
# ---------------------------------------------------------------------------
def collect_links_node(state: PipelineState) -> PipelineState:
    """1단계: 검색 결과에서 레시피 ID 수집 -> recipes/recipe_ids.json"""
    if state["skip_collect"]:
        print("\n[1단계] --skip-collect 지정, 기존 recipe_ids.json 사용")
        return {**state, "last_step": "collect_links", "failed": False}

    ok, err = run_step(
        "1단계 링크수집",
        [sys.executable, "collect_recipe_links.py", state["query"], str(state["max_pages"])],
        cwd=RECIPES_DIR,
    )
    return {**state, "last_step": "collect_links", "failed": not ok, "error": err}


def save_pdfs_node(state: PipelineState) -> PipelineState:
    """2단계: recipe_ids.json의 레시피를 PDF로 저장 -> recipes/original_recipes/"""
    if state["skip_pdf"]:
        print("\n[2단계] --skip-pdf 지정, 기존 PDF 사용")
        return {**state, "last_step": "save_pdfs", "failed": False}

    if not (RECIPES_DIR / "recipe_ids.json").exists():
        return {
            **state,
            "last_step": "save_pdfs",
            "failed": True,
            "error": "recipe_ids.json이 없음 (1단계를 먼저 실행해야 함)",
        }

    ok, err = run_step(
        "2단계 PDF저장",
        [sys.executable, "save_recipes_pdf.py", str(state["start"]), str(state["end"])],
        cwd=RECIPES_DIR,
    )
    return {**state, "last_step": "save_pdfs", "failed": not ok, "error": err}


def structure_node(state: PipelineState) -> PipelineState:
    """3단계: PDF -> LLM 구조화 -> recipes/structured_recipes/*.json"""
    ok, err = run_step(
        "3단계 구조화",
        [sys.executable, "-m", "recipes.structured"],
        cwd=PROJECT_ROOT,
    )
    return {**state, "last_step": "structure", "failed": not ok, "error": err}


# ---------------------------------------------------------------------------
# 조건부 엣지: 직전 단계가 실패했으면 그래프 종료
# ---------------------------------------------------------------------------
def check_failed(state: PipelineState) -> Literal["continue", "stop"]:
    return "stop" if state["failed"] else "continue"


# ---------------------------------------------------------------------------
# 그래프 조립
# ---------------------------------------------------------------------------
def build_graph():
    builder = StateGraph(PipelineState)

    builder.add_node("collect_links", collect_links_node)
    builder.add_node("save_pdfs", save_pdfs_node)
    builder.add_node("structure", structure_node)

    builder.add_edge(START, "collect_links")
    builder.add_conditional_edges(
        "collect_links", check_failed, {"continue": "save_pdfs", "stop": END}
    )
    builder.add_conditional_edges(
        "save_pdfs", check_failed, {"continue": "structure", "stop": END}
    )
    builder.add_edge("structure", END)

    return builder.compile()


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="레시피 수집 파이프라인 (수집→PDF→구조화)")
    parser.add_argument("query", help="검색어 (예: 볶음밥)")
    parser.add_argument("max_pages", type=int, help="검색 결과 최대 페이지 수")
    parser.add_argument("--start", type=int, default=0, help="PDF 저장 시작 인덱스 (기본 0)")
    parser.add_argument("--end", type=int, default=200, help="PDF 저장 끝 인덱스 (기본 200)")
    parser.add_argument("--skip-collect", action="store_true", help="1단계 건너뛰기")
    parser.add_argument("--skip-pdf", action="store_true", help="2단계 건너뛰기")
    args = parser.parse_args()

    graph = build_graph()

    initial_state: PipelineState = {
        "query": args.query,
        "max_pages": args.max_pages,
        "start": args.start,
        "end": args.end,
        "skip_collect": args.skip_collect,
        "skip_pdf": args.skip_pdf,
        "last_step": "",
        "failed": False,
        "error": "",
    }

    final_state = graph.invoke(initial_state)

    print(f"\n{'=' * 60}")
    if final_state["failed"]:
        print(f"파이프라인 중단: [{final_state['last_step']}] {final_state['error']}")
        sys.exit(1)
    print("파이프라인 전체 완료 (수집 → PDF 저장 → 구조화)")


if __name__ == "__main__":
    main()
