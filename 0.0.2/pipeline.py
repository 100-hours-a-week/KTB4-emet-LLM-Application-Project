## ----< 0.0.2 부터 사용할 코드> ---- ##

import os
from glob import glob
from dotenv import load_dotenv

from langchain_community.document_loaders import TextLoader, PyPDFLoader, BSHTMLLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

path_docs = "./docs/"
chunk_size = 300
chunk_overlap = 30
embeddings = GoogleGenerativeAIEmbeddings(
        model = "models/gemini-embedding-001",
        google_api_key=os.environ["GOOGLE_API_KEY"]
)
k = 5
DB_PATH = "./database/"
collection_name = "test_db"

## -----  Document Loader ---- ##
def load_dcoumets(path_docs = "./docs/"):
    path_docs = path_docs
    file_txt = glob(path_docs + "*.txt")            ## <- 문서 파일 종류에 따른 수정 필요

    load_docs = []

    for file  in file_txt:
        load_docs.append(TextLoader(file, encoding="utf-8").load())
    print(f"불러온 문서 수: {len(load_docs)}")
    return load_docs

## --------- Text Splitter --------- ##
def document2chunk(load_docs,chunk_size = 500 , chunk_overlap = 50):

    splitter = RecursiveCharacterTextSplitter(
        chunk_size = chunk_size,
        chunk_overlap = chunk_overlap,
    )
    ## 청크(세분화 문서 리스트) 리스트 생성
    split_docs = splitter.split_documents(load_docs)
    print(f"분할된 chunk 수: {len(split_docs)}")
    return split_docs


## --------- Embedding && VDB && Retriever --------- ##
def init_VDB(init_docs, k = 3):
    ## Chroma VDB 최초 생성
    vectorstore = Chroma.from_documents(init_docs, embeddings, collection_name) ## <- 클라우드 DB 변경 필요
    
    ## 검색시 Chroma VDB에서 상위 3개 관련문서 반환하도록 설정  
    retriever = vectorstore.as_retriever(search_kwargs={"k": k})

    return vectorstore, retriever

## VDB 로컬 저장 
def upload_vdb():
    load_vdb = Chroma(
        persist_directory = DB_PATH,
        embedding_function = embeddings,
        collection_name = collection_name,
    )
    return load_vdb
 

## 미완성 수정 필요
def download_vdb():
    return 0
