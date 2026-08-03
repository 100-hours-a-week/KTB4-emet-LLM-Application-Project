# 레시피 수집 파이프라인 사용법

`data_pipeline/recipe_pipeline.py` — 랜덤 음식 키워드로 레시피를 **무중단으로 계속** 수집해서
PDF 저장 → LLM 구조화 → 벡터스토어(VDB) 저장까지 이어지는 스트리밍 파이프라인.

```
수집(query) ──ID 큐──> PDF저장(pdf) ──PDF 큐──> 구조화(structure) ──JSON 큐──> VDB저장(vdb)
```

네 단계가 **동시에** 돈다. `food_keywords.py`에 정리된 요리 키워드 목록을 무작위 순서로
계속 순회하며 검색하고, ID를 발견하는 즉시 PDF 다운로드를 시작하고, PDF가 저장되는 즉시
LLM 구조화를 시작하고, 구조화가 끝나는 즉시 벡터스토어에 임베딩해서 저장한다.
`--max-recipes`를 지정하지 않으면 **Ctrl+C로 직접 멈출 때까지 무한히** 돈다.

한 단계가 실패하면 새 항목 공급이 끊기고, 이미 큐에 전달된 항목까지만 처리한 뒤
종료코드 1로 끝난다.

## 실행 흐름

| 단계 | 사용 모듈 | 결과물 |
|---|---|---|
| `query` | `food_keywords.py` + `collect_recipe_links.py` | `collected/recipe_ids.json` (+ ID 큐로 실시간 전달) |
| `pdf` | `save_recipes_pdf.py` | `original_recipes/*.pdf` (+ PDF 큐로 실시간 전달) |
| `structure` | `structured.py` | `structured_recipes/<recipe_id>.json` (+ JSON 큐로 실시간 전달) |
| `vdb` | `rag/vectorstore.py` (`rag/config.py`로 서버와 컬렉션/경로 공유) | `data/vdb/` (Chroma 컬렉션) |

각 하위 스크립트(`collect_recipe_links.py`, `save_recipes_pdf.py`, `structured.py`)는
예전처럼 단독 실행도 가능하다 (예: `uv run python data_pipeline/collect_recipe_links.py "볶음밥" 20`).

## 기본 사용법

프로젝트 루트(`chatbot_project/`)에서 실행:

```bash
# 무제한 연속 실행: 랜덤 키워드로 계속 수집 ∥ PDF저장 ∥ 구조화 ∥ VDB저장 (Ctrl+C로 중단)
uv run python data_pipeline/recipe_pipeline.py
```

## 옵션

```bash
# 누적 처리 개수 제한 (테스트/배치용 안전장치)
uv run python data_pipeline/recipe_pipeline.py --max-recipes 200

# 키워드당 검색 페이지 수 늘리기 (키워드 하나를 더 깊이 훑음)
uv run python data_pipeline/recipe_pipeline.py --pages-per-query 3

# 구조화 단계 동시 LLM 요청 수 늘리기
uv run python data_pipeline/recipe_pipeline.py --llm-workers 3

# 수집 건너뛰기: 기존 collected/recipe_ids.json의 ID를 큐에 흘려보냄 (1회성, 랜덤 순회 아님)
uv run python data_pipeline/recipe_pipeline.py --skip-collect

# 수집+PDF저장 모두 건너뛰기: 기존 PDF를 구조화+VDB저장만 (밀린 백로그 처리용)
uv run python data_pipeline/recipe_pipeline.py --skip-collect --skip-pdf
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--pages-per-query` | 2 | 키워드 하나당 검색할 페이지 수 |
| `--max-recipes` | 무제한 | 누적 처리(성공+실패) 목표 개수. 기본은 Ctrl+C로 직접 중단 |
| `--skip-collect` | - | 수집 단계 건너뛰기 (기존 `collected/recipe_ids.json` 사용) |
| `--skip-pdf` | - | PDF 저장 단계 건너뛰기 (기존 PDF 사용) |
| `--llm-workers` | 1 | 구조화 단계 동시 LLM 요청 수 |

## 주의사항

- **클로드**: `LLM_PROVIDER=claude`인 경우 `ANTHROPIC_API_KEY`가 `.env`에 설정되어 있어야 함
- **VDB는 서버와 같은 컬렉션/경로를 공유**(`rag/config.py`): 파이프라인이 저장한 새 레시피는
  FastAPI 서버가 **재시작**해야 검색에 반영됨 (서버는 시작 시 1회만 VDB를 로드)
- **중복 방지**: `structure` 단계는 원본 PDF만 읽으며 `structured_recipes/<id>.json`이 이미
  있으면 건너뜀. `vdb` 단계도 이미 저장된 문서면 임베딩 API를 호출하지 않고 무해하게 스킵함
  → 중단 후 재실행해도 토큰/임베딩 비용 낭비 없음
- **딜레이**: 서버 부하 최소화를 위한 딜레이(수집 2.5초/PDF 5초)는 그대로 유지됨 — 줄이지 말 것
- **키워드 순회**: `food_keywords.py`의 키워드를 무작위로 섞어 반복 순회하므로, 목록을 한 바퀴
  다 돌면 같은 키워드로 다시 검색을 시도한다 (사이트에 반복 요청이 나감 — 딜레이는 유지되지만
  완전히 새로운 레시피만 계속 나오는 건 아님을 감안할 것)
- `--skip-collect` 지정 시 `collected/recipe_ids.json`이 없으면 에러 메시지와 함께 중단됨
- 이미 저장된 PDF는 PDF 단계에서 다운로드를 건너뛰고 경로만 다음 단계로 전달함
