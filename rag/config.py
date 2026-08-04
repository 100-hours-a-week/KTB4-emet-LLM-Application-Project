import os
from pathlib import Path

from rag.local_embeddings import LocalBGEEmbeddings
 

## graph.py(서버)와 data_pipeline(파이프라인)이 반드시 같은 VDB(컬렉션+경로)를
## 봐야 하므로, 이 값들은 여기 한 곳에서만 정의하고 양쪽이 그대로 가져다 쓴다.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

COLLECTION_NAME = "local_embedding_bge_m3_vdb"  ## 08_04 updated
RETRIEVER_K = 12

embedding = LocalBGEEmbeddings(model_name="BAAI/bge-m3", device="cpu")

def get_embedding():
    return embedding


def get_db_path() -> str:
    ## DB_PATH가 상대경로여도 실행 위치와 무관하게 프로젝트 루트 기준으로 고정
    return str((PROJECT_ROOT / os.getenv("DB_PATH", "data/vdb")).resolve())
