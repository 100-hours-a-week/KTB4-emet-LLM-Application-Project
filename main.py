from contextlib import asynccontextmanager
from glob import glob
import os

from fastapi import FastAPI
from pydantic import BaseModel

import graph 

@asynccontextmanager
async def lifespan(app: FastAPI):
    # FastAPI 앱 초기화 시점에 인덱싱 + RAG 체인 구성
    app.state.rag = graph.build()
    yield
    app.state.rag.get_graph().draw_mermaid_png(output_file_path="graph.png")


app = FastAPI(lifespan=lifespan)


class QueryRequest(BaseModel):
    question: str
    thread_id: str | None = None

class QueryResponse(BaseModel):
    answer: str
    thread_id: str


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    from IPython.display import Image, display

    
    result = await app.state.rag.ainvoke(
        {
            "query": req.question},
            config={"configurable": {"thread_id": thread_id}},
    )

    ## ainvoke는 상태(dict) 전체를 반환하므로 경로별 결과 필드에서 답변을 꺼냄
    answer = result.get("answer") or result.get("retrieved_recipes") or "결과가 없습니다."
    return QueryResponse(answer=answer)