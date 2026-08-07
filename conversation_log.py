"""
사용자 대화(턴 단위) 로그를 SQLite에 남긴다.

data/ 디렉토리에 저장 -> EC2 배포 시 -v /home/ubuntu/data:/app/data 마운트를
그대로 타서, VDB와 마찬가지로 재배포해도 로그가 유지된다.
베타테스트 기간 동안은 이 파일을 주기적으로 S3에도 백업해서(rag/vectorstore.py의
VDB 업로드와 동일한 방식/환경변수 네이밍), EC2에 직접 안 들어가도 로그를 내려받아
확인할 수 있게 한다.
"""
import asyncio
import json
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "logs.db"


def upload_to_s3() -> None:
    """LOG_S3_UPLOAD=1 이고 버킷이 설정된 경우에만 data/logs.db를 S3로 업로드.
    실패해도 서버 동작에 영향 없도록 예외를 삼키고 로그만 남긴다."""
    if os.getenv("LOG_S3_UPLOAD") != "1":
        return
    if not DB_PATH.exists():
        return

    ## 버킷/프리픽스 미지정 시 VDB와 같은 버킷을 재사용 (베타 단계에서 버킷을 따로
    ## 안 만들어도 되도록). 프리픽스는 logs로 분리해서 VDB 데이터와 안 섞이게 함.
    bucket = os.getenv("LOG_S3_BUCKET") or os.getenv("VDB_S3_BUCKET")
    if not bucket:
        print("[conversation_log] LOG_S3_BUCKET/VDB_S3_BUCKET 둘 다 미설정 -> S3 업로드 건너뜀")
        return
    prefix = os.getenv("LOG_S3_PREFIX", "logs")

    try:
        import boto3

        s3 = boto3.client("s3")
        s3.upload_file(str(DB_PATH), bucket, f"{prefix}/logs.db")
        print(f"[conversation_log] logs.db를 s3://{bucket}/{prefix}/logs.db 에 업로드 완료")
    except Exception as e:
        print(f"[conversation_log] S3 업로드 실패: {e}")


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
