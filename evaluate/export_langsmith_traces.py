"""
LangSmith 프로젝트 "Rice"에서 지정한 3개 시간대의 Trace를 다운로드하는 스크립트.

사전 준비:
    pip install langsmith --break-system-packages   (또는 uv add langsmith)
    환경변수 LANGSMITH_API_KEY 설정 필요 (.env 또는 export)

실행:
    python export_langsmith_traces.py
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from langsmith import Client
from dotenv import load_dotenv

load_dotenv()

PROJECT_NAME = "Rice"
KST = ZoneInfo("Asia/Seoul")
TODAY = datetime.now(KST).date()  # 오늘 날짜 (2026-08-07 기준으로 실행한다고 가정)

## ── 시간대별 카테고리 정의 ──────────────────────────────────────
## (이름, 시작시각(KST), 종료시각(KST))
TIME_WINDOWS = [
    ("1_AF_sector", "08:23", "08:57"),
    ("2_E2E_20cases", "09:43", "09:49"),
    ("3_web_search", "10:31", "10:47"),
]

OUTPUT_ROOT = Path("./langsmith_export")


def to_kst_datetime(time_str: str) -> datetime:
    """'HH:MM' 문자열을 오늘 날짜 기준 KST 시각의 UTC datetime으로 변환.
    LangSmith SDK(0.9.1)의 list_runs(start_time=...)가 비-UTC tz-aware
    datetime을 제대로 처리하지 못해서(같은 순간이어도 UTC로 명시 변환 안 하면
    필터가 조용히 0건을 반환함) 여기서 미리 UTC로 변환해서 반환한다."""
    hour, minute = map(int, time_str.split(":"))
    kst_dt = datetime(TODAY.year, TODAY.month, TODAY.day, hour, minute, tzinfo=KST)
    return kst_dt.astimezone(timezone.utc)


def serialize_run(run) -> dict:
    """langsmith Run 객체를 JSON 직렬화 가능한 dict로 변환."""
    data = run.dict() if hasattr(run, "dict") else dict(run)
    return json.loads(json.dumps(data, default=str, ensure_ascii=False))


def export_window(client: Client, category: str, start_str: str, end_str: str):
    start_time = to_kst_datetime(start_str)
    end_time = to_kst_datetime(end_str)

    print(f"\n=== {category} ({start_str}~{end_str} KST) ===")

    ## 1) 해당 시간대의 최상위 run(=trace 시작점)만 조회
    root_runs = list(
        client.list_runs(
            project_name=PROJECT_NAME,
            is_root=True,
            start_time=start_time,
        )
    )
    ## start_time 필터는 "이후"만 지원하는 경우가 많아, end_time은 코드에서 한 번 더 걸러줌
    root_runs = [r for r in root_runs if r.start_time <= end_time]

    print(f"발견된 trace 수: {len(root_runs)}")

    out_dir = OUTPUT_ROOT / category
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = []

    for root in root_runs:
        trace_id = root.trace_id
        ## 2) 이 trace_id에 속한 모든 run(전체 노드) 조회
        all_runs = list(client.list_runs(project_name=PROJECT_NAME, trace_id=trace_id))

        trace_data = {
            "trace_id": str(trace_id),
            "runs": [serialize_run(r) for r in all_runs],
        }

        out_path = out_dir / f"trace-{trace_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(trace_data, f, ensure_ascii=False, indent=2)

        query = (root.inputs or {}).get("query", "")
        thread_id = (root.extra or {}).get("metadata", {}).get("thread_id", "")
        latency = None
        if root.end_time and root.start_time:
            latency = (root.end_time - root.start_time).total_seconds()

        summary.append({
            "trace_id": str(trace_id),
            "thread_id": thread_id,
            "start_time": str(root.start_time),
            "latency_sec": latency,
            "query": query,
        })
        print(f"  저장됨: {out_path.name} (query={query!r}, latency={latency}s)")

    ## 카테고리별 요약 파일도 같이 저장
    summary_path = out_dir / "_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"요약 저장됨: {summary_path}")


def main():
    client = Client()
    for category, start_str, end_str in TIME_WINDOWS:
        export_window(client, category, start_str, end_str)

    print("\n전체 완료. 결과는 ./langsmith_export/ 폴더 아래에 카테고리별로 저장됨.")
    print("2_E2E_20cases는 기능 수정 전/후가 섞여있을 수 있으니, ")
    print("_summary.json의 start_time을 보고 수동으로 전/후를 나눠서 비교하는 걸 추천.")


if __name__ == "__main__":
    main()
