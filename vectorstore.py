from langchain_chroma import Chroma
import os




class VectorStore:

    VDB: Chroma

    def __init__(self, split_docs, embedding, collection_name,  persist_directory):
        if self.is_exsists(persist_directory):
            self.load_local_vdb(embedding, collection_name, persist_directory)
            if self.has_new_doc(len(split_docs),persist_directory):
                print("VDB doc is updated.")
                self.VDB.add_documents(split_docs)
            
        else :
            self.create_vdb(split_docs, embedding, collection_name,  persist_directory)

    def is_exsists(self, persist_directory):
        if os.path.exists(persist_directory) and os.listdir(persist_directory):
            print("VDB directory is exists.")
            return True
            
            
        print("VDB directory is not exists.")
        return False
    
    def has_new_doc(self, new_length, persist_directory):
        if new_length > self.VDB._collection.count():
            return True
        return False

    def load_local_vdb(self,embedding, collection_name,persist_directory):
        self.VDB = Chroma(
            persist_directory=persist_directory,
            embedding_function=embedding,
            collection_name=collection_name
        )
        print("VDB loaded.")


    ## 최신버전 Chroma는 persist_directory 설정되면 문서 추가되면 자동으로 업데이트
    def create_vdb(self, split_docs, embedding, collection_name,  persist_directory):
        self.VDB = Chroma.from_documents(
            persist_directory=persist_directory,
            documents=split_docs, 
            embedding=embedding,
            collection_name=collection_name   
        )
        print("VDB creating and embeddings.")


    ## VDB 로컬 저장(인메모리->로컬파일) 
    ### DB_PATH, collection_name 둘 중 하나라도 변경이 발생할때 사용
    def save_vdb(DB_PATH):
        print(f"VDB was local saved at {DB_PATH}")
    
    def retriever(self, k):
        return self.VDB.as_retriever(k=k)
    
    def add_new_docs(self, new_docs):
        ## 중복 문서(청크)은?
        self.VDB.add_documents(new_docs)