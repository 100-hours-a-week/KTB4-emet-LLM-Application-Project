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

    @staticmethod
    def _version_key(prefix: str) -> str:
        """VDB 데이터 자체와 섞이지 않도록 prefix 폴더 밖의 별도 키에 버전을 둔다."""
        return f"{prefix}.version"

    @staticmethod
    def _local_version_path(persist_directory: str) -> Path:
        p = Path(persist_directory)
        return p.parent / f"{p.name}.version"

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

    @classmethod
    def _upload_directory_to_s3(cls, persist_directory, bucket, prefix):
        import boto3
        from datetime import datetime, timezone

        s3 = boto3.client("s3")
        local_root = Path(persist_directory)
        uploaded = 0

        for file_path in local_root.rglob("*"):
            if file_path.is_file():
                relative_path = file_path.relative_to(local_root)
                s3_key = f"{prefix}/{relative_path.as_posix()}"
                s3.upload_file(str(file_path), bucket, s3_key)
                uploaded += 1

        ## 업로드한 VDB를 식별할 버전 마커. 다음 서버 기동 시 이 값과 로컬 마커가
        ## 같으면 전체 다운로드/재임베딩을 건너뛸 수 있다.
        version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        s3.put_object(Bucket=bucket, Key=cls._version_key(prefix), Body=version.encode())
        cls._local_version_path(persist_directory).write_text(version)

        print(f"VDB {uploaded}개 파일을 s3://{bucket}/{prefix} 에 동기화 완료 (버전={version})")


def _get_remote_version(bucket: str, prefix: str) -> str | None:
    """S3에 올려둔 버전 마커를 읽는다. 아직 한 번도 버전과 함께 업로드된 적 없으면 None."""
    import boto3
    from botocore.exceptions import ClientError

    s3 = boto3.client("s3")
    try:
        obj = s3.get_object(Bucket=bucket, Key=VectorStore._version_key(prefix))
        return obj["Body"].read().decode().strip()
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            return None
        raise


def sync_vdb_from_s3(persist_directory: str) -> None:
    """
    VDB_S3_BUCKET이 설정되어 있으면, S3의 최신 VDB를 persist_directory로 내려받는다.
    앱 시작 시점(main.py의 lifespan)에서 호출해 EC2가 항상 최신 VDB를 쓰도록 보장.
    미설정 시 조용히 건너뜀 (로컬 전용 개발 환경에서도 에러 없이 동작).

    S3/로컬 버전 마커가 같으면 다운로드를 건너뛴다. 이게 없으면 매 기동마다
    전체 VDB를 무조건 새로 받아써서, 로컬 VDB가 이미 최신이어도 그 위에
    다시 덮어써 add_new_docs가 문서 ID 불일치로 오인하고 전체를 재임베딩하는
    문제(로컬 개발 시 매번 수 분씩 걸리는 원인)가 있었다.
    """
    bucket = os.getenv("VDB_S3_BUCKET")
    if not bucket:
        print("VDB_S3_BUCKET 미설정 -> S3 동기화 건너뜀 (로컬 VDB 그대로 사용)")
        return

    prefix = os.getenv("VDB_S3_PREFIX", "vdb")

    remote_version = _get_remote_version(bucket, prefix)
    local_version_path = VectorStore._local_version_path(persist_directory)
    local_version = local_version_path.read_text().strip() if local_version_path.exists() else None

    if remote_version is not None and remote_version == local_version:
        print(f"VDB 버전 최신(버전={remote_version}) -> S3 다운로드 건너뜀")
        return

    _download_directory_from_s3(persist_directory, bucket, prefix)

    if remote_version is not None:
        local_version_path.write_text(remote_version)


def _download_directory_from_s3(persist_directory: str, bucket: str, prefix: str) -> None:
    import boto3

    s3 = boto3.client("s3")
    local_root = Path(persist_directory)
    local_root.mkdir(parents=True, exist_ok=True)

    paginator = s3.get_paginator("list_objects_v2")
    downloaded = 0

    ## S3 Prefix는 경로가 아니라 순수 문자열 접두사라, 끝에 "/"를 안 붙이면
    ## "{prefix}.version" 같은 형제 키까지 이 폴더 밑으로 잘못 끌려온다.
    for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/"):
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