"""
레시피 수집 스트리밍 파이프라인

collect_recipe_links -> save_recipes_pdf -> structured
세 단계를 asyncio 큐 2개(ID 큐, PDF 큐)로 연결해 동시에 실행한다.
1단계가 페이지에서 ID를 발견하는 즉시 2단계가 해당 PDF를 내려받기 시작하고,
2단계가 PDF를 저장하는 즉시 3단계가 LLM 구조화를 시작한다.

- 스킵 기능 유지: --skip-collect는 기존 recipe_ids.json의 ID를 큐에 흘려보내고,
  --skip-pdf는 기존 original_recipes/*.pdf를 바로 3단계 큐에 넣는다.
- 이미 구조화된 레시피(structured_recipes/<id>.json 존재)는 자동으로 건너뜀.
- 한 단계가 실패하면 상류에서 새 항목 공급이 끊기고, 이미 전달된 항목까지만
  처리한 뒤 종료코드 1로 끝난다.

사용법 (프로젝트 루트에서):
  uv run python recipes/recipe_pipeline.py "볶음밥" 20
  uv run python recipes/recipe_pipeline.py "볶음밥" 20 --start 0 --end 200
  uv run python recipes/recipe_pipeline.py "볶음밥" 20 --skip-collect   # 링크수집 건너뛰기
  uv run python recipes/recipe_pipeline.py "볶음밥" 20 --skip-pdf       # PDF저장 건너뛰기
  uv run python recipes/recipe_pipeline.py "볶음밥" 20 --llm-workers 3  # 3단계 동시 처리 수

* 3단계(structured)는 LLM_PROVIDER=claude 이면 ANTHROPIC_API_KEY가 .env에 설정되어 있어야 함
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from playwright.async_api import async_playwright

from data_pipeline.collect_recipe_links import OUTPUT_FILE as IDS_FILE, collect_pages
from data_pipeline.save_recipes_pdf import (
    DELAY_SEC as PDF_DELAY_SEC,
    MAX_CONSECUTIVE_FAILS,
    OUTPUT_DIR as PDF_DIR,
    USER_AGENT,
    save_one,
)
from data_pipeline.structured import STRUCTURED_DIR, structure_pdf_file

_DONE = None  # 큐 종료 신호 (ID는 str, PDF는 Path라서 None과 겹치지 않음)


# ---------------------------------------------------------------------------
# 1단계: 링크 수집 -> ID를 발견하는 즉시 id_q로 전달
# ---------------------------------------------------------------------------
async def collect_stage(query: str, max_pages: int, skip_collect: bool, id_q: asyncio.Queue) -> str:
    try:
        if skip_collect:
            print("\n[1단계] --skip-collect 지정, 기존 recipe_ids.json 사용")
            if not IDS_FILE.exists():
                return "recipe_ids.json이 없음 (1단계를 먼저 실행해야 함)"
            with open(IDS_FILE, encoding="utf-8") as f:
                for rid in json.load(f):
                    id_q.put_nowait(rid)
            return ""

        print("\n[1단계] 링크 수집 시작 (발견 즉시 2단계로 전달)")
        async for fresh_ids in collect_pages(query, max_pages):
            for rid in sorted(fresh_ids):
                id_q.put_nowait(rid)
        return ""
    except Exception as e:
        return f"1단계 링크수집 실패: {e}"
    finally:
        id_q.put_nowait(_DONE)


# ---------------------------------------------------------------------------
# 2단계: ID가 도착하는 즉시 PDF 저장 -> pdf_q로 전달
# ---------------------------------------------------------------------------
async def pdf_stage(start: int, end: int, skip_pdf: bool, id_q: asyncio.Queue, pdf_q: asyncio.Queue) -> str:
    try:
        if skip_pdf:
            print("\n[2단계] --skip-pdf 지정, 기존 PDF 사용")
            existing = sorted(PDF_DIR.glob("*.pdf"))
            for pdf_path in existing:
                pdf_q.put_nowait(pdf_path)
            print(f"[2단계] 기존 PDF {len(existing)}개를 3단계로 전달")
            return ""

        consecutive_fails = 0
        idx = 0
        saved = 0

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(user_agent=USER_AGENT)
            try:
                while True:
                    rid = await id_q.get()
                    if rid is _DONE:
                        break

                    in_window = start <= idx < end  # --start/--end 범위 (도착 순서 기준)
                    idx += 1
                    if not in_window:
                        continue

                    print(f"[2단계] recipe_id={rid}")
                    pdf_path = await save_one(page, rid)

                    if pdf_path is not None:
                        consecutive_fails = 0
                        saved += 1
                        pdf_q.put_nowait(pdf_path)
                    else:
                        consecutive_fails += 1
                        if consecutive_fails >= MAX_CONSECUTIVE_FAILS:
                            return "연속 실패 다수 발생 (차단 가능성) -> 2단계 중단"

                    await asyncio.sleep(PDF_DELAY_SEC)
            finally:
                await browser.close()

        print(f"\n[2단계] 완료: PDF {saved}개를 3단계로 전달")
        return ""
    except Exception as e:
        return f"2단계 PDF저장 실패: {e}"
    finally:
        pdf_q.put_nowait(_DONE)


# ---------------------------------------------------------------------------
# 3단계: PDF가 도착하는 즉시 LLM 구조화 -> structured_recipes/*.json
# ---------------------------------------------------------------------------
async def structure_stage(pdf_q: asyncio.Queue, counts: dict) -> str:
    try:
        while True:
            pdf_path = await pdf_q.get()
            if pdf_path is _DONE:
                pdf_q.put_nowait(_DONE)  # 다른 워커도 종료 신호를 받도록 되돌려 놓음
                break
            ok = await structure_pdf_file(Path(pdf_path))
            counts["ok" if ok else "fail"] += 1
        return ""
    except Exception as e:
        return f"3단계 구조화 실패: {e}"


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------
async def run_pipeline(args) -> int:
    id_q: asyncio.Queue = asyncio.Queue()
    pdf_q: asyncio.Queue = asyncio.Queue()
    counts = {"ok": 0, "fail": 0}

    results = await asyncio.gather(
        collect_stage(args.query, args.max_pages, args.skip_collect, id_q),
        pdf_stage(args.start, args.end, args.skip_pdf, id_q, pdf_q),
        *(structure_stage(pdf_q, counts) for _ in range(args.llm_workers)),
    )

    errors = [r for r in results if r]

    print(f"\n{'=' * 60}")
    print(f"구조화 결과: 성공 {counts['ok']}개 / 실패 {counts['fail']}개  -> {STRUCTURED_DIR.name}/")
    if errors:
        for err in errors:
            print(f"파이프라인 오류: {err}")
        return 1
    print("파이프라인 전체 완료 (수집 ∥ PDF저장 ∥ 구조화 동시 실행)")
    return 0


def main():
    parser = argparse.ArgumentParser(description="레시피 수집 스트리밍 파이프라인 (수집∥PDF∥구조화)")
    parser.add_argument("query", help="검색어 (예: 볶음밥)")
    parser.add_argument("max_pages", type=int, help="검색 결과 최대 페이지 수")
    parser.add_argument("--start", type=int, default=0, help="PDF 저장 시작 인덱스 (기본 0)")
    parser.add_argument("--end", type=int, default=200, help="PDF 저장 끝 인덱스 (기본 200)")
    parser.add_argument("--skip-collect", action="store_true", help="1단계 건너뛰기 (기존 recipe_ids.json 사용)")
    parser.add_argument("--skip-pdf", action="store_true", help="2단계 건너뛰기 (기존 PDF 사용)")
    parser.add_argument("--llm-workers", type=int, default=1, help="3단계 동시 LLM 요청 수 (기본 1)")
    args = parser.parse_args()

    sys.exit(asyncio.run(run_pipeline(args)))


if __name__ == "__main__":
    main()
