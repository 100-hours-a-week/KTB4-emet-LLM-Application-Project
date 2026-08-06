"""
레시피 수집 연속 파이프라인 (무중단, 랜덤 음식 키워드)

query(랜덤 키워드) -> collect -> pdf -> structure -> vdb

네 단계가 asyncio 큐 3개로 연결되어 **동시에** 돈다. food_keywords.py의 목록을
무작위 순서로 계속 순회하며 검색하고, 발견 즉시 다음 단계로 흘려보낸다:
검색에서 ID를 찾으면 즉시 PDF 다운로드를 시작하고, PDF가 저장되는 즉시 LLM
구조화를 시작하고, 구조화가 끝나는 즉시 벡터스토어(VDB)에 임베딩해서 저장한다.

--max-recipes를 지정하지 않으면 Ctrl+C로 직접 멈출 때까지 무한히 돈다.
한 단계가 실패하면 새 항목 공급이 끊기고, 이미 큐에 전달된 항목까지만 처리한
뒤 종료코드 1로 끝난다.

사용법 (프로젝트 루트에서):
  uv run python data_pipeline/recipe_pipeline.py
  uv run python data_pipeline/recipe_pipeline.py --max-recipes 200
  uv run python data_pipeline/recipe_pipeline.py --pages-per-query 3 --llm-workers 3
  uv run python data_pipeline/recipe_pipeline.py --skip-collect             # 기존 ID 목록만 재처리
  uv run python data_pipeline/recipe_pipeline.py --skip-collect --skip-pdf  # 기존 PDF만 구조화+VDB

* structure 단계는 LLM_PROVIDER=claude 이면 ANTHROPIC_API_KEY가 .env에 설정되어 있어야 함
* vdb 단계는 graph.py(서버)와 동일한 컬렉션/경로(rag/config.py)를 사용 -> 서버 재시작 없이
  다음 조회부터 바로 반영되지는 않음 (서버는 시작 시 1회 로드), 서버도 재시작해야 새 문서가 검색됨
"""

import argparse
import asyncio
import json
import os
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from playwright.async_api import async_playwright

from data_pipeline.food_keywords import FOOD_KEYWORDS
from data_pipeline.collect_recipe_links import OUTPUT_FILE as IDS_FILE, collect_pages
from data_pipeline.save_recipes_pdf import (
    DELAY_SEC as PDF_DELAY_SEC,
    MAX_CONSECUTIVE_FAILS,
    OUTPUT_DIR as PDF_DIR,
    USER_AGENT,
    save_one,
)
from data_pipeline.structured import STRUCTURED_DIR, extract_recipe_id, structure_pdf_file
from rag.config import COLLECTION_NAME, get_embedding, get_db_path
from rag.loader import json_loader
from rag.vectorstore import VectorStore

_DONE = None  # 큐 종료 신호 (ID/JSON경로는 str|Path라서 None과 겹치지 않음)


# ---------------------------------------------------------------------------
# 1단계: 랜덤 음식 키워드 수집 -> ID를 발견하는 즉시 id_q로 전달
# ---------------------------------------------------------------------------
async def query_stage(
    pages_per_query: int, max_recipes: int | None, skip_collect: bool,
    id_q: asyncio.Queue, counts: dict,
) -> str:
    try:
        if skip_collect:
            print("\n[수집] --skip-collect 지정, 기존 collected/recipe_ids.json 사용")
            if not IDS_FILE.exists():
                return "recipe_ids.json이 없음 (수집을 먼저 실행해야 함)"
            with open(IDS_FILE, encoding="utf-8") as f:
                for rid in json.load(f):
                    id_q.put_nowait(rid)
            return ""

        print(f"\n[수집] 랜덤 음식 키워드로 연속 수집 시작 (키워드당 {pages_per_query}페이지)")
        seen_ids: set[str] = set()
        keywords = FOOD_KEYWORDS.copy()

        while True:
            random.shuffle(keywords)
            for keyword in keywords:
                if max_recipes is not None and counts["ok"] + counts["fail"] >= max_recipes:
                    print(f"\n[수집] 목표 {max_recipes}개 도달, 수집 중단")
                    return ""

                print(f"\n[수집] 랜덤 키워드: '{keyword}'")
                async for fresh_ids in collect_pages(keyword, pages_per_query):
                    new_ids = fresh_ids - seen_ids
                    if not new_ids:
                        continue
                    seen_ids.update(new_ids)
                    for rid in sorted(new_ids):
                        id_q.put_nowait(rid)
    except Exception as e:
        return f"수집 실패: {e}"
    finally:
        id_q.put_nowait(_DONE)


# ---------------------------------------------------------------------------
# 2단계: ID가 도착하는 즉시 PDF 저장 -> pdf_q로 전달
# ---------------------------------------------------------------------------
async def pdf_stage(skip_pdf: bool, id_q: asyncio.Queue, pdf_q: asyncio.Queue) -> str:
    try:
        if skip_pdf:
            print("\n[PDF] --skip-pdf 지정, 기존 PDF 사용")
            existing = sorted(PDF_DIR.glob("*.pdf"))
            for pdf_path in existing:
                pdf_q.put_nowait(pdf_path)
            print(f"[PDF] 기존 PDF {len(existing)}개를 구조화 단계로 전달")
            return ""

        consecutive_fails = 0
        saved = 0

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(user_agent=USER_AGENT)
            try:
                while True:
                    rid = await id_q.get()
                    if rid is _DONE:
                        break

                    print(f"[PDF] recipe_id={rid}")
                    pdf_path = await save_one(page, rid)

                    if pdf_path is not None:
                        consecutive_fails = 0
                        saved += 1
                        pdf_q.put_nowait(pdf_path)
                    else:
                        consecutive_fails += 1
                        if consecutive_fails >= MAX_CONSECUTIVE_FAILS:
                            return "연속 실패 다수 발생 (차단 가능성) -> PDF 저장 중단"

                    await asyncio.sleep(PDF_DELAY_SEC)
            finally:
                await browser.close()

        print(f"\n[PDF] 완료: {saved}개 저장")
        return ""
    except Exception as e:
        return f"PDF저장 실패: {e}"
    finally:
        pdf_q.put_nowait(_DONE)


# ---------------------------------------------------------------------------
# 3단계: PDF가 도착하는 즉시 LLM 구조화 -> structured_recipes/*.json, vdb_q로 전달
# ---------------------------------------------------------------------------
async def structure_stage(pdf_q: asyncio.Queue, vdb_q: asyncio.Queue, counts: dict) -> str:
    try:
        while True:
            pdf_path = await pdf_q.get()
            if pdf_path is _DONE:
                pdf_q.put_nowait(_DONE)  # 다른 워커도 종료 신호를 받도록 되돌려 놓음
                break

            ok = await structure_pdf_file(Path(pdf_path))
            counts["ok" if ok else "fail"] += 1

            if ok:
                json_path = STRUCTURED_DIR / f"{extract_recipe_id(str(pdf_path))}.json"
                vdb_q.put_nowait(json_path)
        return ""
    except Exception as e:
        return f"구조화 실패: {e}"
    finally:
        vdb_q.put_nowait(_DONE)


# ---------------------------------------------------------------------------
# 4단계: 구조화된 JSON이 도착하는 즉시 VDB에 임베딩 저장
# (graph.py와 동일한 컬렉션/경로를 rag/config.py로 공유)
# ---------------------------------------------------------------------------
async def vdb_stage(vdb_q: asyncio.Queue) -> str:
    try:
        print("\n[VDB] 벡터스토어 초기화")
        ## 서버(graph.py)는 기동 시 불필요한 업로드를 건너뛰도록 기본값이 꺼져 있지만,
        ## 이 파이프라인은 실제로 VDB를 새로 만드는 쪽이므로 여기서는 업로드를 켠다.
        os.environ["VDB_S3_UPLOAD"] = "1"
        embedding = get_embedding()
        db_path = get_db_path()
        ## 기존 structured_recipes 전체로 초기화 -> VectorStore가 신규분만 골라 add
        initial_docs = json_loader(sorted(STRUCTURED_DIR.glob("*.json")))
        vdb = VectorStore(initial_docs, embedding, COLLECTION_NAME, db_path)
        print(f"[VDB] 준비 완료 (기존 문서 {len(initial_docs)}개 기준)")

        added = 0
        while True:
            json_path = await vdb_q.get()
            if json_path is _DONE:
                break

            docs = json_loader([json_path])
            if not docs:
                continue
            ## 이미 저장된 문서면 add_new_docs가 자체적으로 걸러내고 무해하게 스킵
            vdb.add_new_docs(docs)
            added += 1
            print(f"[VDB] 처리 완료 ({added}번째) -> {Path(json_path).name}")

        print(f"\n[VDB] 완료: 신규 문서 처리 {added}건")
        return ""
    except Exception as e:
        return f"VDB저장 실패: {e}"


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------
async def run_pipeline(args) -> int:
    id_q: asyncio.Queue = asyncio.Queue()
    pdf_q: asyncio.Queue = asyncio.Queue()
    vdb_q: asyncio.Queue = asyncio.Queue()
    counts = {"ok": 0, "fail": 0}

    results = await asyncio.gather(
        query_stage(args.pages_per_query, args.max_recipes, args.skip_collect, id_q, counts),
        pdf_stage(args.skip_pdf, id_q, pdf_q),
        *(structure_stage(pdf_q, vdb_q, counts) for _ in range(args.llm_workers)),
        vdb_stage(vdb_q),
    )

    errors = [r for r in results if r]

    print(f"\n{'=' * 60}")
    print(f"구조화 결과: 성공 {counts['ok']}개 / 실패 {counts['fail']}개  -> {STRUCTURED_DIR.name}/")
    if errors:
        for err in errors:
            print(f"파이프라인 오류: {err}")
        return 1
    print("파이프라인 전체 완료 (수집 ∥ PDF저장 ∥ 구조화 ∥ VDB저장 동시 실행)")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="랜덤 음식 키워드로 레시피를 계속 수집 -> PDF저장 -> 구조화 -> VDB저장하는 무중단 파이프라인"
    )
    parser.add_argument(
        "--pages-per-query", type=int, default=2,
        help="키워드 하나당 검색할 페이지 수 (기본 2)",
    )
    parser.add_argument(
        "--max-recipes", type=int, default=None,
        help="누적 처리(성공+실패) 목표 개수. 기본은 무제한 -> Ctrl+C로 직접 중단",
    )
    parser.add_argument("--skip-collect", action="store_true", help="수집 건너뛰기 (기존 collected/recipe_ids.json 사용)")
    parser.add_argument("--skip-pdf", action="store_true", help="PDF 저장 건너뛰기 (기존 PDF 사용)")
    parser.add_argument("--llm-workers", type=int, default=1, help="구조화 단계 동시 LLM 요청 수 (기본 1)")
    args = parser.parse_args()

    try:
        sys.exit(asyncio.run(run_pipeline(args)))
    except KeyboardInterrupt:
        print("\n\n사용자 중단(Ctrl+C). 지금까지 처리된 PDF/구조화 결과는 디스크에 그대로 남아있습니다.")
        sys.exit(130)


if __name__ == "__main__":
    main()
