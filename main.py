
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

import graph

@asynccontextmanager
async def lifespan(app: FastAPI):
    # FastAPI 앱 초기화 시점에 인덱싱 + RAG 체인 구성
    app.state.rag = graph.build()
    yield


app = FastAPI(lifespan=lifespan)


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    answer: str

@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    answer = app.state.rag({"query":req.question})
    return QueryResponse(answer=answer)
