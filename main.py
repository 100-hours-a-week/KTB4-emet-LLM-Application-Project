
from contextlib import asynccontextmanager
from glob import glob
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

import loader
import splitter
from vectorstore import VectorStore

load_dotenv()

doc_path = "../Docs/FOOD/RICE"


DB_PATH = "./database/"
collection_name = "test_db"
retriever_k = 5
    


def build_rag_chain():
    document = loader.fileloader_distributor()
    splitted_docs = splitter.Token_splitter(document)

    embedding = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=os.getenv("GOOGLE_API_KEY"),
    )

    vdb = VectorStore(splitted_docs, embedding, collection_name,  DB_PATH)

    retriever = vdb.retriever(k=retriever_k)

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "다음 문서를 근거로 사용자 질문에 답하세요. "
         "근거가 부족하면 '주어진 자료에서는 확인할 수 없습니다.'라고 답하세요.\n\n"
         "{context}"),
        ("human", "{question}"),
    ])

    llm = loader.llm_loader()

    def format_docs(ds):
        return "\n\n".join(d.page_content for d in ds)

    rag = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )
    return rag


@asynccontextmanager
async def lifespan(app: FastAPI):
    # FastAPI 앱 초기화 시점에 인덱싱 + RAG 체인 구성
    app.state.rag = build_rag_chain()  
    yield


app = FastAPI(lifespan=lifespan)


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    answer: str


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    answer = app.state.rag.invoke(req.question)
    return QueryResponse(answer=answer)
