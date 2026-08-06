from contextlib import asynccontextmanager
from glob import glob
from pathlib import Path
import json
import os
import uuid
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import graph
from rag.config import get_db_path
from rag.vectorstore import sync_vdb_from_s3

from dotenv import load_dotenv
load_dotenv()

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
    "build_rag_recipe_options": "찾은 레시피를 정리하는 중",
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
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    ## 그래프 빌드(=VDB 로드) 전에 S3에서 최신 VDB를 먼저 받아옴
    sync_vdb_from_s3(get_db_path())

    app.state.rag = graph.build()
    yield
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

        ## 첫 노드(query_analysis) 실행 중에는 astream이 아무 청크도 내보내지 않아
        ## 화면이 멈춘 것처럼 보이므로, 진입 노드 문구를 먼저 한 번 보내둔다.
        yield f"data: {json.dumps({'type': 'progress', 'status': NODE_DISPLAY_NAMES[ENTRY_NODE]}, ensure_ascii=False)}\n\n"

        try:
            async for chunk in app.state.rag.astream(
                {"query": req.question}, config, stream_mode="updates"
            ):
                node_name = list(chunk.keys())[0]
                display = NODE_DISPLAY_NAMES.get(node_name, "처리하는 중")
                yield f"data: {json.dumps({'type': 'progress', 'status': display}, ensure_ascii=False)}\n\n"

            ## stream_mode="updates"의 마지막 청크는 마지막 노드가 "반환한" 필드만 담고 있어
            ## 그래프 구조 변경(병렬 노드 등)에 취약함 -> 체크포인터에 저장된 전체 상태를 다시 조회해서 answer를 꺼낸다.
            snapshot = await app.state.rag.aget_state(config)
            answer = (snapshot.values.get("answer") or "결과가 없습니다.") if snapshot else "결과가 없습니다."
            yield f"data: {json.dumps({'type': 'final', 'answer': answer, 'thread_id': thread_id}, ensure_ascii=False)}\n\n"

        except Exception as e:
            ## 내부 예외 메시지를 그대로 클라이언트에 노출하지 않는다.
            print(f"[SSE] 그래프 실행 실패 (thread_id={thread_id}): {e}")
            error_message = "답변 생성 중 문제가 발생했어요. 다시 시도해 주세요."
            yield f"data: {json.dumps({'type': 'error', 'message': error_message}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )