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


class QueryResponse(BaseModel):
    answer: str


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    from IPython.display import Image, display

    
    answer = await app.state.rag.ainvoke({"query": req.question})
    print(f"answer:\n{answer}")
    
    return QueryResponse(answer=answer)