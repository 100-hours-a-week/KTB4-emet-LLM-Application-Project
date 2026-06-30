
from contextlib import asynccontextmanager
from glob import glob
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_google_genai import ChatGoogleGenerativeAI

doc_path = "../Docs/FOOD/RICE"

## 환경 변수 읽기
load_dotenv()


def build_llm():
    provider = os.getenv("LLM_PROVIDER", "goolge").lower()
    print(f"LLM Provider: {provider}")

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "gemma4:e2b-mlx"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
    return ChatGoogleGenerativeAI(
        model=os.getenv("GOOGLE_MODEL", "gemini-2.5-flash"),
        google_api_key=os.getenv("GOOGLE_API_KEY"),
    )
    


def build_rag_chain():
    ## 개인화 필요
    pdf_paths = sorted(glob(doc_path+"/*.pdf"))
    pdf_docs = []
    for p in pdf_paths:
        loader = PyPDFLoader(p)
        pages = loader.load()          # 해당 PDF의 모든 페이지를 한 번에 리스트로 반환
        for doc in pages:
            page_num = doc.metadata["page"] + 1
            preview = doc.page_content[:40].replace("\n", " ")
            print(f"[페이지 {page_num}] {preview}...")
        pdf_docs.extend(pages)          # 리스트 통째로 추가
    docs = pdf_docs
    print(f"로딩된 Document 수: {len(docs)}")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size = 500,
        chunk_overlap = 50,
    )
    split_docs = splitter.split_documents(docs)
    print(f"분할된 chunk 수: {len(split_docs)}")

    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=os.getenv("GOOGLE_API_KEY"),
    )

    vectorstore = Chroma.from_documents(split_docs, embeddings)

    # RAG
    retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "다음 문서를 근거로 사용자 질문에 답하세요. "
         "근거가 부족하면 '주어진 자료에서는 확인할 수 없습니다.'라고 답하세요.\n\n"
         "{context}"),
        ("human", "{question}"),
    ])

    llm = build_llm()

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
