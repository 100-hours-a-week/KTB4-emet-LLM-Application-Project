import os
from pathlib import Path

from rag.local_embeddings import LocalBGEEmbeddings
 

## graph.py(서버)와 data_pipeline(파이프라인)이 반드시 같은 VDB(컬렉션+경로)를
## 봐야 하므로, 이 값들은 여기 한 곳에서만 정의하고 양쪽이 그대로 가져다 쓴다.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

COLLECTION_NAME = "local_embedding_bge_m3_vdb"  ## 08_04 updated
RETRIEVER_K = 12

## RAG 레시피 출처 표기용. data_pipeline/collect_recipe_links.py가 전부 이 사이트에서만
## 수집하고, recipe_id가 원본 URL의 레시피 ID와 그대로 일치하므로 상수 하나로 충분하다.
RECIPE_SITE_NAME = "만개의레시피"
RECIPE_URL_TEMPLATE = "https://www.10000recipe.com/recipe/{recipe_id}"

embedding = LocalBGEEmbeddings(model_name="BAAI/bge-m3", device="cpu")

def get_embedding():
    return embedding


def get_db_path() -> str:
    ## DB_PATH가 상대경로여도 실행 위치와 무관하게 프로젝트 루트 기준으로 고정
    return str((PROJECT_ROOT / os.getenv("DB_PATH", "data/vdb")).resolve())
