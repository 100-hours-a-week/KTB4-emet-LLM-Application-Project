from langchain_chroma import Chroma


class VectorStore:

    VDB: Chroma

    def __init__(self, split_docs, embedding, collection_name="default",  DB_PATH="./chromadb"):
        self.create_vdb(split_docs, embedding, collection_name,  DB_PATH)
    
    ## 최신버전 Chroma는 persist_directory 설정되면 문서 추가되면 자동으로 업데이트
    def create_vdb(self, split_docs, embedding, collection_name,  DB_PATH):
        self.VDB = Chroma.from_documents(
            persist_directory=DB_PATH,
            documents=split_docs, 
            embedding=embedding,
            collection_name=collection_name   
        )
        print("VDB 생성 및 인덱싱 완료!")

    def add_doc(self, new_docs):
        self.VDB.add_documents(new_docs)
    
    def retriever(self, k):
        return self.VDB.as_retriever(search_kwargs={"k": k})
    


    ## VDB 로컬 저장(인메모리->로컬파일) 
    ### DB_PATH, collection_name 둘 중 하나라도 변경이 발생할때 사용
    def save_vdb(DB_PATH, collection_name):

        print("VDB 로컬 저장 완료!")
    
    ## 
    def load_vdb(embedding, collection_name ="default",DB_PATH="./chromadb"):
        loaded_db = Chroma(
            persist_directory=DB_PATH,
            embedding_function=embedding,
            collection_name=collection_name
        )
        print("VDB 로컬 불러오기 완료!")