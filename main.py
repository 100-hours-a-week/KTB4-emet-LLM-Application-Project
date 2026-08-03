from contextlib import asynccontextmanager
from glob import glob
from pathlib import Path
import os
import uuid
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

import graph 
from rag.config import get_db_path
from rag.vectorstore import sync_vdb_from_s3

from dotenv import load_dotenv
load_dotenv()

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
    return FileResponse(STATIC_DIR / "index.html")


class QueryRequest(BaseModel):
    question: str
    thread_id: str | None = None

class QueryResponse(BaseModel):
    answer: str
    thread_id: str


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    from IPython.display import Image, display

    thread_id = req.thread_id or str(uuid.uuid4())   
    result = await app.state.rag.ainvoke(
        {
            "query": req.question},
            config={"configurable": {"thread_id": thread_id }},
    )

    ## ainvoke는 상태(dict) 전체를 반환하므로 경로별 결과 필드에서 답변을 꺼냄
    answer = result.get("answer") or result.get("retrieved_recipes") or "결과가 없습니다."
    return QueryResponse(answer=answer, thread_id=thread_id)