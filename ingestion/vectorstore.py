from langchain_chroma import Chroma
import os

class VectorStore:

    VDB: Chroma

    def __init__(self, split_docs, embedding, collection_name,  persist_directory):
        if self.is_exsists(persist_directory):
            self.load_local_vdb(embedding, collection_name, persist_directory)
            self.add_new_docs(split_docs)
        else :
            self.create_vdb(split_docs, embedding, collection_name,  persist_directory)

    def is_exsists(self, persist_directory):
        if os.path.exists(persist_directory) and os.listdir(persist_directory):
            print("VDB directory is exists.")
            return True


        print("VDB directory is not exists.")
        return False

    @staticmethod
    def doc_id(doc) -> str:
        """문서 고유 ID. loader가 부여한 doc_id(레시피 ID 기반)를 쓰고, 없으면 source+page로 대체"""
        known = doc.metadata.get("doc_id")
        if known:
            return known
        source = doc.metadata.get("source", "unknown")
        page = doc.metadata.get("page")
        return f"{source}:p{page}" if page is not None else source

    @classmethod
    def unique_docs(cls, docs):
        """같은 배치 안에서 ID가 중복되면 첫 문서만 남김 (Chroma는 중복 ID 배치를 거부함)"""
        seen = set()
        unique = []
        for doc in docs:
            key = cls.doc_id(doc)
            if key in seen:
                continue
            seen.add(key)
            unique.append(doc)
        return unique

    def load_local_vdb(self,embedding, collection_name,persist_directory):
        self.VDB = Chroma(
            persist_directory=persist_directory,
            embedding_function=embedding,
            collection_name=collection_name
        )
        print("VDB loaded.")


    ## 최신버전 Chroma는 persist_directory 설정되면 문서 추가되면 자동으로 업데이트
    def create_vdb(self, split_docs, embedding, collection_name,  persist_directory):
        docs = self.unique_docs(split_docs)
        self.VDB = Chroma.from_documents(
            persist_directory=persist_directory,
            documents=docs,
            embedding=embedding,
            ids=[self.doc_id(d) for d in docs],
            collection_name=collection_name
        )
        print(f"VDB creating and embeddings. (문서 {len(docs)}개)")

    def retriever(self, k):
        return self.VDB.as_retriever(search_kwargs={"k": k})

    def add_new_docs(self, new_docs):
        """기존 VDB에 없는 문서(차집합)만 임베딩해서 추가"""
        docs = self.unique_docs(new_docs)
        existing_ids = set(self.VDB.get(include=[])["ids"])
        fresh = [d for d in docs if self.doc_id(d) not in existing_ids]

        if not fresh:
            print("VDB is up to date. (신규 문서 없음)")
            return

        self.VDB.add_documents(fresh, ids=[self.doc_id(d) for d in fresh])
        print(f"VDB doc is updated. (신규 문서 {len(fresh)}개 추가)")
