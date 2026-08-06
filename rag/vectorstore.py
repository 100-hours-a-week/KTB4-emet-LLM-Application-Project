from langchain_chroma import Chroma
import os
from pathlib import Path
class VectorStore:

    VDB: Chroma

    def __init__(self, split_docs, embedding, collection_name, persist_directory):
        if self.is_exsists(persist_directory):
            self.load_local_vdb(embedding, collection_name, persist_directory)
            self.add_new_docs(split_docs)
        else:
            self.create_vdb(split_docs, embedding, collection_name, persist_directory)

        ## VDB 생성/갱신이 끝난 뒤 항상 S3 동기화 시도 (환경변수 없으면 자동 스킵)
        self._sync_to_s3_if_configured(persist_directory)

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

    def _sync_to_s3_if_configured(self, persist_directory):
        """VDB_S3_UPLOAD=1 이고 VDB_S3_BUCKET이 설정된 경우에만 S3로 업로드.

        서버가 뜰 때마다(=매 요청 때가 아니라 기동 시 1회) 무조건 업로드하면
        기동 직전에 이미 sync_vdb_from_s3()로 다운로드한 내용을 그대로 다시 올리는
        불필요한 왕복이 매번 발생해 기동 시간이 늘어난다. 업로드는 실제로 문서가
        추가/변경되는 data_pipeline 실행 시에만 필요하므로 기본은 건너뛴다.
        """
        if os.getenv("VDB_S3_UPLOAD") != "1":
            print("VDB_S3_UPLOAD != 1 -> S3 업로드 건너뜀 (서버 기동 시 정상 동작)")
            return

        bucket = os.getenv("VDB_S3_BUCKET")
        if not bucket:
            print("VDB_S3_BUCKET 미설정 -> S3 동기화 건너뜀")
            return

        prefix = os.getenv("VDB_S3_PREFIX", "vdb")
        self._upload_directory_to_s3(persist_directory, bucket, prefix)

    @staticmethod
    def _upload_directory_to_s3(persist_directory, bucket, prefix):
        import boto3

        s3 = boto3.client("s3")
        local_root = Path(persist_directory)
        uploaded = 0

        for file_path in local_root.rglob("*"):
            if file_path.is_file():
                relative_path = file_path.relative_to(local_root)
                s3_key = f"{prefix}/{relative_path.as_posix()}"
                s3.upload_file(str(file_path), bucket, s3_key)
                uploaded += 1

        print(f"VDB {uploaded}개 파일을 s3://{bucket}/{prefix} 에 동기화 완료")


def sync_vdb_from_s3(persist_directory: str) -> None:
    """
    VDB_S3_BUCKET이 설정되어 있으면, S3의 최신 VDB를 persist_directory로 내려받는다.
    앱 시작 시점(main.py의 lifespan)에서 호출해 EC2가 항상 최신 VDB를 쓰도록 보장.
    미설정 시 조용히 건너뜀 (로컬 전용 개발 환경에서도 에러 없이 동작).
    """
    bucket = os.getenv("VDB_S3_BUCKET")
    if not bucket:
        print("VDB_S3_BUCKET 미설정 -> S3 동기화 건너뜀 (로컬 VDB 그대로 사용)")
        return

    prefix = os.getenv("VDB_S3_PREFIX", "vdb")
    _download_directory_from_s3(persist_directory, bucket, prefix)


def _download_directory_from_s3(persist_directory: str, bucket: str, prefix: str) -> None:
    import boto3

    s3 = boto3.client("s3")
    local_root = Path(persist_directory)
    local_root.mkdir(parents=True, exist_ok=True)

    paginator = s3.get_paginator("list_objects_v2")
    downloaded = 0

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            relative_path = key[len(prefix):].lstrip("/")
            if not relative_path:
                continue  ## prefix 자체가 폴더 마커로 찍힌 경우 건너뜀

            local_path = local_root / relative_path
            local_path.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, key, str(local_path))
            downloaded += 1

    if downloaded == 0:
        print(f"s3://{bucket}/{prefix} 에 파일이 없음 -> 로컬 VDB 유지")
    else:
        print(f"S3에서 {downloaded}개 파일을 {persist_directory} 로 다운로드 완료")