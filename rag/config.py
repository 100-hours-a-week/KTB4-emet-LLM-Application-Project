import os
from pathlib import Path

from langchain_google_genai import GoogleGenerativeAIEmbeddings

## graph.py(서버)와 data_pipeline(파이프라인)이 반드시 같은 VDB(컬렉션+경로)를
## 봐야 하므로, 이 값들은 여기 한 곳에서만 정의하고 양쪽이 그대로 가져다 쓴다.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

COLLECTION_NAME = "test_db3"
RETRIEVER_K = 5


def get_embedding():
    return GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=os.environ["GOOGLE_API_KEY"],
    )


def get_db_path() -> str:
    ## DB_PATH가 상대경로여도 실행 위치와 무관하게 프로젝트 루트 기준으로 고정
    return str((PROJECT_ROOT / os.getenv("DB_PATH", "data/vdb")).resolve())
