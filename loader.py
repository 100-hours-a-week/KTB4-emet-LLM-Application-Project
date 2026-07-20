from glob import glob
import os

from langchain_community.document_loaders import PyPDFLoader
from langchain_google_genai import ChatGoogleGenerativeAI

document_path = "../Docs/FOOD/RICE" 


def text_loader():
    return -1

def md_loader():
    return -1

def html_loader():
    return -1


def pdf_loader(pdf_path_list, limit=-1):
    pdf_docs = []
    total_pages = 0

    for p in pdf_path_list:
        loader = PyPDFLoader(p)
        pages = loader.load()

        for doc in pages:
            # limit 도달하면 더 이상 문서를 추가하지 않음
            if limit > -1 and len(pdf_docs) >= limit:
                break

            page_num = doc.metadata["page"] + 1
            total_pages += 1  # 페이지 번호가 아니라 페이지 개수를 셈
            preview = doc.page_content[:40].replace("\n", " ")
            print(f"[페이지 {page_num}] {preview}...")

            pdf_docs.append(doc)  # extend(pages) 대신 낱개 append로 limit 초과분 제외

        if limit > -1 and len(pdf_docs) >= limit:
            break  # 목표치 채웠으면 남은 PDF 파일은 아예 안 읽음

    print(f"로딩된 전체 PDF Document 파일 수: {len(pdf_docs)}")
    print(f"로딩된 전체 PDF Document 페이지 수: {total_pages}")
    return pdf_docs


def fileloader_distributor(limit=-1):
    pdf_path_list = sorted(glob(document_path+"/*.pdf"))
    pdf_docs = pdf_loader(pdf_path_list, limit=limit)

    document = []
    document.extend(pdf_docs)

    return document


# 수정 필요
def model_loader():
    return 0

def llm_loader():
    provider = os.getenv("LLM_PROVIDER", "google").lower()
    print(f"LLM Provider: {provider}")
    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "gemma4:e2b-mlx"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
    # 수정 필요
    elif provider == "self":
        ## 직접만들 모델 사용
        return -1
    return ChatGoogleGenerativeAI(
        model=os.getenv("GOOGLE_MODEL", "gemini-2.5-flash"),
        google_api_key=os.getenv("GOOGLE_API_KEY"),
    )