"""
사용자 대화(턴 단위) 로그를 SQLite에 남긴다.

data/ 디렉토리에 저장 -> EC2 배포 시 -v /home/ubuntu/data:/app/data 마운트를
그대로 타서, VDB와 마찬가지로 재배포해도 로그가 유지된다.
베타테스트 기간 동안은 이 파일을 주기적으로 S3에도 백업해서(rag/vectorstore.py의
VDB 업로드와 동일한 방식/환경변수 네이밍), EC2에 직접 안 들어가도 로그를 내려받아
확인할 수 있게 한다.

주의: upload_to_s3()는 매번 같은 키(logs.db)를 덮어쓰는 "현재 상태 백업"이라
과거 이력은 남지 않는다. 날짜별로 이력을 보존하려면 rotate_and_archive()를 쓴다
(main.py가 베타테스트 기간 동안 매일 22:00 KST에 호출).
"""
import asyncio
import json
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DB_PATH = Path(__file__).resolve().parent / "data" / "logs.db"
ARCHIVE_DIR = DB_PATH.parent / "logs_archive"
_KST = ZoneInfo("Asia/Seoul")

## logs.db에 대한 쓰기(INSERT)와 rotate_and_archive()의 파일 교체가 동시에 일어나면
## 안 되므로 같은 락으로 직렬화한다.
_write_lock = threading.Lock()


def _resolve_bucket_and_prefix() -> tuple[str | None, str]:
    ## 버킷/프리픽스 미지정 시 VDB와 같은 버킷을 재사용 (베타 단계에서 버킷을 따로
    ## 안 만들어도 되도록). 프리픽스는 logs로 분리해서 VDB 데이터와 안 섞이게 함.
    bucket = os.getenv("LOG_S3_BUCKET") or os.getenv("VDB_S3_BUCKET")
    prefix = os.getenv("LOG_S3_PREFIX", "logs")
    return bucket, prefix


def upload_to_s3() -> None:
    """LOG_S3_UPLOAD=1 이고 버킷이 설정된 경우에만 data/logs.db를 S3로 업로드.
    항상 같은 키를 덮어써서 "현재까지의 전체 로그" 스냅샷 하나만 유지한다.
    실패해도 서버 동작에 영향 없도록 예외를 삼키고 로그만 남긴다."""
    if os.getenv("LOG_S3_UPLOAD") != "1":
        return
    if not DB_PATH.exists():
        return

    bucket, prefix = _resolve_bucket_and_prefix()
    if not bucket:
        print("[conversation_log] LOG_S3_BUCKET/VDB_S3_BUCKET 둘 다 미설정 -> S3 업로드 건너뜀")
        return

    try:
        import boto3

        s3 = boto3.client("s3")
        s3.upload_file(str(DB_PATH), bucket, f"{prefix}/logs.db")
        print(f"[conversation_log] logs.db를 s3://{bucket}/{prefix}/logs.db 에 업로드 완료")
    except Exception as e:
        print(f"[conversation_log] S3 업로드 실패: {e}")


def rotate_and_archive() -> None:
    """지금까지 쌓인 logs.db를 날짜가 찍힌 이름으로 보관하고, 이후 기록은 새
    logs.db에 쌓이도록 교체한다. 아카이브 파일은 (LOG_S3_UPLOAD=1인 경우)
    덮어쓰지 않는 날짜별 키로 S3에도 올려서 베타테스트 기간 동안의 로그 이력을
    전부 보존한다. main.py가 매일 22:00(KST)에 호출한다."""
    if not DB_PATH.exists():
        return

    date_str = datetime.now(_KST).strftime("%Y-%m-%d")
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = ARCHIVE_DIR / f"logs_{date_str}.db"
    if archive_path.exists():
        ## 같은 날짜에 이미 로테이션된 적 있음(수동 재시작 등) -> 덮어쓰지 않게 시각까지 붙임
        archive_path = ARCHIVE_DIR / f"logs_{date_str}_{datetime.now(_KST).strftime('%H%M%S')}.db"

    with _write_lock:
        DB_PATH.rename(archive_path)
        init_db()

    print(f"[conversation_log] logs.db 로테이션 완료 -> {archive_path.name}")

    if os.getenv("LOG_S3_UPLOAD") != "1":
        return
    bucket, prefix = _resolve_bucket_and_prefix()
    if not bucket:
        print("[conversation_log] LOG_S3_BUCKET/VDB_S3_BUCKET 둘 다 미설정 -> 아카이브 S3 업로드 건너뜀")
        return

    try:
        import boto3

        s3 = boto3.client("s3")
        key = f"{prefix}/archive/{archive_path.name}"
        s3.upload_file(str(archive_path), bucket, key)
        print(f"[conversation_log] 아카이브를 s3://{bucket}/{key} 에 업로드 완료")
    except Exception as e:
        print(f"[conversation_log] 아카이브 S3 업로드 실패: {e}")


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                query TEXT NOT NULL,
                answer TEXT,
                query_type TEXT,
                node_path TEXT,
                node_timings_json TEXT,
                llm_calls_json TEXT,
                used_rag INTEGER NOT NULL DEFAULT 0,
                used_generation INTEGER NOT NULL DEFAULT 0,
                total_elapsed_ms INTEGER,
                error TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


## 이 노드가 경로에 있으면 그 턴에서 RAG/생성 로직을 실제로 거쳤다고 판단.
## (엄밀히는 preview_recipe_options처럼 부족분이 0이면 LLM 생성을 건너뛰는 경우도
## 있지만, 로그/분석 목적으로는 노드 방문 여부 기준의 근사치로 충분함)
_RAG_NODES = {"rag_adequacy_check", "resolve_rag_name_match", "fetch_rag_recipe"}
_GENERATION_NODES = {"preview_recipe_options", "generate_recipe_by_name", "finalize_recipe"}


def classify_path(node_path: list[str]) -> tuple[bool, bool]:
    used_rag = any(n in _RAG_NODES for n in node_path)
    used_generation = any(n in _GENERATION_NODES for n in node_path)
    return used_rag, used_generation


def _insert_sync(
    *,
    thread_id: str,
    created_at: str,
    query: str,
    answer: str | None,
    query_type: str | None,
    node_path: list[str],
    node_timings: list[dict],
    llm_calls: list[dict],
    total_elapsed_ms: int | None,
    error: str | None = None,
) -> None:
    used_rag, used_generation = classify_path(node_path)
    with _write_lock:
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(
                """
                INSERT INTO conversation_logs
                    (thread_id, created_at, query, answer, query_type, node_path,
                     node_timings_json, llm_calls_json, used_rag, used_generation,
                     total_elapsed_ms, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    thread_id,
                    created_at,
                    query,
                    answer,
                    query_type,
                    ",".join(node_path),
                    json.dumps(node_timings, ensure_ascii=False),
                    json.dumps(llm_calls, ensure_ascii=False),
                    int(used_rag),
                    int(used_generation),
                    total_elapsed_ms,
                    error,
                ),
            )
            conn.commit()
        finally:
            conn.close()


async def insert_log(**kwargs) -> None:
    """이벤트 루프를 막지 않도록 별도 스레드에서 동기 sqlite3 쓰기 실행."""
    try:
        await asyncio.to_thread(_insert_sync, **kwargs)
    except Exception as e:
        ## 로그 적재 실패가 실제 응답 흐름을 막으면 안 됨 -> 조용히 경고만 남김
        print(f"[conversation_log] 로그 저장 실패: {e}")
