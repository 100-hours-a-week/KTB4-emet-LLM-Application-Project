from glob import glob
import os
import re
from pathlib import Path
import json

from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader
from langchain_google_genai import ChatGoogleGenerativeAI

source_dir = Path(__file__).resolve().parent.parent / "recipes" / "original_recipes"


def _recipe_id_from_name(path: Path) -> str:
    """파일명에서 레시피 ID 추출 ('12345_제목.pdf' -> '12345', 패턴이 없으면 파일명 전체)"""
    match = re.match(r"(\d+)_", path.stem)
    return match.group(1) if match else path.stem


def json_loader(json_path_list, limit=-1):
    """
    JSON 파일을 읽어서 Document로 감싸기만 하는 로더.
    필드 파싱/텍스트 조합은 하지 않음 (스키마 변경에 안전하게 만들기 위함).
    """
    json_docs = []

    for p in json_path_list:
        if limit > -1 and len(json_docs) >= limit:
            break

        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)

        recipe_id = str(data.get("recipe_id") or data.get("seq") or p.stem)
        doc = Document(
            page_content=json.dumps(data, ensure_ascii=False),
            metadata={
                "source": str(p),
                "seq": recipe_id,
                "doc_id": f"json:{recipe_id}",  # VDB 중복 방지용 고유 ID (레시피 ID 기반)
            },
        )

        preview = str(data)[:40].replace("\n", " ")
        print(f"[{p.name}] {preview}...")
        json_docs.append(doc)

    print(f"로딩된 전체 JSON Document 파일 수: {len(json_docs)}")
    return json_docs


# 초기버전 / 오리지널 pdf 사용
def pdf_loader(pdf_path_list, limit=-1):
    pdf_docs = []
    total_pages = 0

    for p in pdf_path_list:
        loader = PyPDFLoader(p)
        pages = loader.load()
        recipe_id = _recipe_id_from_name(Path(p))

        for doc in pages:
            # limit 도달하면 더 이상 문서를 추가하지 않음
            if limit > -1 and len(pdf_docs) >= limit:
                break

            page_num = doc.metadata["page"] + 1
            # VDB 중복 방지용 고유 ID: 레시피 ID + 페이지 (한 PDF가 여러 페이지 문서가 되므로)
            doc.metadata["doc_id"] = f"pdf:{recipe_id}:p{page_num}"
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
    processed_dir = Path(__file__).resolve().parent.parent / "recipes" / "structured_recipes"

    json_path_list = sorted(processed_dir.glob("*.json"))
    json_docs = json_loader(json_path_list, limit=limit)

    return json_docs


# 수정 필요
def model_loader():
    return 0

def llm_loader():
    provider = os.getenv("LLM_PROVIDER", "google").lower()
    #print(f"LLM Provider: {provider}")
    if provider == "claude":
        from langchain_anthropic import ChatAnthropic
        # API 키는 ANTHROPIC_API_KEY 환경변수에서 자동으로 읽음
        return ChatAnthropic(
            model=os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8"),
            max_tokens=16000,
        )
    # 수정 필요
    elif provider == "self":
        ## 직접만들 모델 사용
        return -1
    return ChatGoogleGenerativeAI(
        model=os.getenv("GOOGLE_MODEL", "gemini-2.5-flash"),
        google_api_key=os.getenv("GOOGLE_API_KEY"),
    )