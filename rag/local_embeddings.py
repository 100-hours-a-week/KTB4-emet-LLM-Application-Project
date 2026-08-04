"""
로컬 임베딩 모델 (BAAI/bge-m3).
LangChain의 Embeddings 인터페이스(embed_documents/embed_query)를 그대로 구현해서,
기존 GoogleGenerativeAIEmbeddings를 쓰던 자리에 그대로 대체 가능하게 만든 클래스.

설치 필요:
    pip install sentence-transformers --break-system-packages
"""

from typing import List
from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer


class LocalBGEEmbeddings(Embeddings):
    """
    BAAI/bge-m3를 로컬에서 서빙하는 임베딩 클래스.
    폴백 없음 -> 실패하면 그대로 예외를 던짐 (벡터 공간 혼입 방지 원칙,
    임베딩은 다른 모델로 조용히 대체되면 안 되므로 의도적으로 폴백을 걸지 않음).
    """

    _model: SentenceTransformer | None = None  # 클래스 레벨 캐시 (재사용, 중복 로딩 방지)

    def __init__(self, model_name: str = "BAAI/bge-m3", device: str = "cpu"):
        if LocalBGEEmbeddings._model is None:
            print(f"[LocalBGEEmbeddings] 모델 로딩 중: {model_name} (device={device})")
            LocalBGEEmbeddings._model = SentenceTransformer(model_name, device=device)
        self.model = LocalBGEEmbeddings._model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """문서(레시피 등) 임베딩. ChromaDB 저장 시 사용됨."""
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,  # 코사인 유사도 계산 안정성을 위해 정규화
            show_progress_bar=len(texts) > 20,
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> List[float]:
        """검색 쿼리 임베딩. retreiver_recipes에서 사용됨.
        embed_documents와 반드시 같은 모델/정규화 방식을 써야 함 (그래야 같은 벡터 공간)."""
        embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding.tolist()
