from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from glob import glob
from pathlib import Path
from zoneinfo import ZoneInfo
import asyncio
import json
import os
import time
import uuid
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import conversation_log
import llm
from rag.config import get_db_path
from rag.vectorstore import sync_vdb_from_s3

from dotenv import load_dotenv
load_dotenv()

## MemorySaver는 프로세스가 떠 있는 동안 스레드별 체크포인트가 계속 쌓이기만 하므로,
## 일정 시간 활동이 없는 스레드는 주기적으로 지워서 메모리 누적을 막는다.
SESSION_IDLE_TTL_SECONDS = int(os.getenv("SESSION_IDLE_TTL_SECONDS", 7200))  # 2시간
SESSION_SWEEP_INTERVAL_SECONDS = int(os.getenv("SESSION_SWEEP_INTERVAL_SECONDS", 1800))  # 30분

## 베타테스트 기간 동안 대화 로그(data/logs.db)를 주기적으로 S3에 백업하는 주기.
## LOG_S3_UPLOAD=1일 때만 동작 (conversation_log.upload_to_s3 참고).
LOG_S3_UPLOAD_INTERVAL_SECONDS = int(os.getenv("LOG_S3_UPLOAD_INTERVAL_SECONDS", 600))  # 10분

## 베타테스트 기간 동안 logs.db를 매일 이 시각(KST)에 날짜별로 아카이브하고 새 파일로
## 교체한다 (conversation_log.rotate_and_archive 참고). S3 업로드와 별개로 항상 로컬
## 로테이션은 수행되고, LOG_S3_UPLOAD=1인 경우에만 아카이브가 추가로 S3에 올라간다.
LOG_ROTATE_HOUR_KST = int(os.getenv("LOG_ROTATE_HOUR_KST", 22))  # 밤 10시

## 그래프 진입 노드 (START -> query_analysis 고정 경로)
ENTRY_NODE = "query_analysis"

## 노드별 SSE progress 문구. 매핑에 없는 노드는 .get()의 기본값("처리하는 중")으로 표시.
NODE_DISPLAY_NAMES = {
    "query_analysis": "질문을 이해하는 중",
    "reset_recipe_options": "재료 변경 사항을 확인하는 중",
    "extract_ingredient": "재료를 정리하는 중",
    "extract_ingredient_update": "변경할 재료를 확인하는 중",
    "apply_ingredient_modification": "재료 목록을 업데이트하는 중",
    "ingredient_analysis": "요리 가능 여부를 확인하는 중",
    "retreiver_recipes": "비슷한 레시피를 찾는 중",
    "rag_adequacy_check": "레시피 적합성을 검토하는 중",
    "preview_recipe_options": "새로운 요리 아이디어를 만드는 중",
    "present_recipe_options": "선택지를 정리하는 중",
    "select_recipe_option": "선택하신 레시피를 확인하는 중",
    "finalize_recipe": "레시피를 완성하는 중",
    "fetch_rag_recipe": "레시피를 불러오는 중",
    "respond_infeasible": "결과를 정리하는 중",
    "respond_undevopled": "지원 가능한 요청인지 확인하는 중",
    "respond_unrealated": "요청 내용을 확인하는 중",
    "undeveloped": "응답을 준비하는 중",
    "search_by_name": "요청하신 요리를 검색하는 중",
    "filter_valid_candidates": "검색 결과를 정리하는 중",
    "judge_name_match": "검색 결과가 맞는지 확인하는 중",
    "resolve_rag_name_match": "찾은 레시피를 정리하는 중",
    "generate_recipe_by_name": "레시피를 새로 만드는 중",
}

async def _sweep_idle_threads(app: FastAPI):
    """일정 시간 활동이 없던 thread_id를 체크포인터에서 정리하는 백그라운드 루프."""
    while True:
        await asyncio.sleep(SESSION_SWEEP_INTERVAL_SECONDS)
        now = time.time()
        idle_thread_ids = [
            thread_id
            for thread_id, last_seen in app.state.thread_last_seen.items()
            if now - last_seen > SESSION_IDLE_TTL_SECONDS
        ]
        for thread_id in idle_thread_ids:
            await app.state.rag.checkpointer.adelete_thread(thread_id)
            app.state.thread_last_seen.pop(thread_id, None)
        if idle_thread_ids:
            print(f"[session cleanup] 유휴 스레드 {len(idle_thread_ids)}개 정리: {idle_thread_ids}")


async def _periodic_log_upload():
    """대화 로그를 주기적으로 S3에 백업하는 백그라운드 루프.
    (LOG_S3_UPLOAD=1 아니면 conversation_log.upload_to_s3 내부에서 조용히 스킵됨)"""
    while True:
        await asyncio.sleep(LOG_S3_UPLOAD_INTERVAL_SECONDS)
        await asyncio.to_thread(conversation_log.upload_to_s3)


async def _daily_log_rotation():
    """매일 LOG_ROTATE_HOUR_KST 시각(KST, 기본 22시)에 logs.db를 날짜별로 아카이브하고
    새 파일로 교체하는 백그라운드 루프."""
    kst = ZoneInfo("Asia/Seoul")
    while True:
        now = datetime.now(kst)
        next_run = now.replace(hour=LOG_ROTATE_HOUR_KST, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        await asyncio.sleep((next_run - now).total_seconds())
        await asyncio.to_thread(conversation_log.rotate_and_archive)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ## 그래프 빌드(=VDB 로드) 전에 S3에서 최신 VDB를 먼저 받아옴
    sync_vdb_from_s3(get_db_path())

    ## graph를 import하는 순간 graph.py 최상단의 init_vdb()가 실행되어 VDB가 로드/생성된다.
    ## 이 import를 파일 최상단에 두면 main.py 로드 시점(=S3 다운로드보다 먼저)에 실행돼버려서
    ## 방금 받은 최신 VDB가 아니라 그 이전 로컬 상태로 그래프가 구성되는 문제가 있었다.
    ## 반드시 sync_vdb_from_s3() 이후에 와야 한다.
    import graph

    conversation_log.init_db()

    app.state.rag = graph.build()
    app.state.thread_last_seen = {}
    sweep_task = asyncio.create_task(_sweep_idle_threads(app))
    log_upload_task = asyncio.create_task(_periodic_log_upload())
    log_rotation_task = asyncio.create_task(_daily_log_rotation())

    yield

    sweep_task.cancel()
    log_upload_task.cancel()
    log_rotation_task.cancel()
    for task in (sweep_task, log_upload_task, log_rotation_task):
        try:
            await task
        except asyncio.CancelledError:
            pass
    ## 종료 직전 마지막 상태도 한 번 더 백업 (주기적 업로드 사이에 종료되는 경우 대비)
    await asyncio.to_thread(conversation_log.upload_to_s3)
    app.state.rag.get_graph().draw_mermaid_png(output_file_path="graph.png")



app = FastAPI(lifespan=lifespan)

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


class QueryRequest(BaseModel):
    question: str
    thread_id: str | None = None

class QueryResponse(BaseModel):
    answer: str
    thread_id: str


@app.post(
    "/query",
    responses={
        200: {
            "description": "SSE 스트림. progress(여러 번) -> final 또는 error(1회)로 종료.",
            "content": {"text/event-stream": {}},
        }
    },
)
async def query(req: QueryRequest):
    async def event_generator():
        thread_id = req.thread_id or str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}
        app.state.thread_last_seen[thread_id] = time.time()

        ## 첫 노드(query_analysis) 실행 중에는 astream이 아무 청크도 내보내지 않아
        ## 화면이 멈춘 것처럼 보이므로, 진입 노드 문구를 먼저 한 번 보내둔다.
        yield f"data: {json.dumps({'type': 'progress', 'status': NODE_DISPLAY_NAMES[ENTRY_NODE]}, ensure_ascii=False)}\n\n"

        ## 이번 턴 동안 발생하는 LLM 호출(provider별)을 대화 로그용으로 수집
        llm_log_token = llm.llm_call_log.set([])
        node_timings: list[dict] = []
        turn_start = time.perf_counter()
        last_ts = turn_start

        try:
            async for chunk in app.state.rag.astream(
                {"query": req.question}, config, stream_mode="updates"
            ):
                node_name = list(chunk.keys())[0]
                now = time.perf_counter()
                node_timings.append({"node": node_name, "elapsed_ms": round((now - last_ts) * 1000)})
                last_ts = now
                display = NODE_DISPLAY_NAMES.get(node_name, "처리하는 중")
                yield f"data: {json.dumps({'type': 'progress', 'status': display}, ensure_ascii=False)}\n\n"

            ## stream_mode="updates"의 마지막 청크는 마지막 노드가 "반환한" 필드만 담고 있어
            ## 그래프 구조 변경(병렬 노드 등)에 취약함 -> 체크포인터에 저장된 전체 상태를 다시 조회해서 answer를 꺼낸다.
            snapshot = await app.state.rag.aget_state(config)
            answer = (snapshot.values.get("answer") or "결과가 없습니다.") if snapshot else "결과가 없습니다."
            query_type = snapshot.values.get("query_type") if snapshot else None

            await conversation_log.insert_log(
                thread_id=thread_id,
                created_at=datetime.now(timezone.utc).isoformat(),
                query=req.question,
                answer=answer,
                query_type=query_type.type if query_type else None,
                node_path=[t["node"] for t in node_timings],
                node_timings=node_timings,
                llm_calls=llm.llm_call_log.get() or [],
                total_elapsed_ms=round((time.perf_counter() - turn_start) * 1000),
            )

            yield f"data: {json.dumps({'type': 'final', 'answer': answer, 'thread_id': thread_id}, ensure_ascii=False)}\n\n"

        except Exception as e:
            ## 내부 예외 메시지를 그대로 클라이언트에 노출하지 않는다.
            print(f"[SSE] 그래프 실행 실패 (thread_id={thread_id}): {e}")
            error_message = "답변 생성 중 문제가 발생했어요. 다시 시도해 주세요."

            await conversation_log.insert_log(
                thread_id=thread_id,
                created_at=datetime.now(timezone.utc).isoformat(),
                query=req.question,
                answer=None,
                query_type=None,
                node_path=[t["node"] for t in node_timings],
                node_timings=node_timings,
                llm_calls=llm.llm_call_log.get() or [],
                total_elapsed_ms=round((time.perf_counter() - turn_start) * 1000),
                error=str(e),
            )

            yield f"data: {json.dumps({'type': 'error', 'message': error_message}, ensure_ascii=False)}\n\n"
        finally:
            llm.llm_call_log.reset(llm_log_token)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.delete("/session/{thread_id}")
async def delete_session(thread_id: str):
    """사용자가 새 대화를 시작할 때, 이전 스레드의 체크포인트를 명시적으로 정리."""
    await app.state.rag.checkpointer.adelete_thread(thread_id)
    app.state.thread_last_seen.pop(thread_id, None)
    return {"ok": True}