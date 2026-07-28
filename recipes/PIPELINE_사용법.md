# 레시피 수집 파이프라인 사용법

`recipes/recipe_pipeline.py` — 레시피 수집 3단계를 asyncio 큐로 연결한 스트리밍 파이프라인.

```
수집(collect) ──ID 큐──> PDF저장(pdf) ──PDF 큐──> 구조화(structure)
```

세 단계가 **동시에** 돈다: 1단계가 검색 페이지에서 ID를 발견하는 즉시 2단계가 해당
레시피 PDF를 내려받기 시작하고, PDF가 저장되는 즉시 3단계가 LLM 구조화를 시작한다.
한 단계가 실패하면 새 항목 공급이 끊기고, 이미 큐에 전달된 항목까지만 처리한 뒤
종료코드 1로 끝난다.

## 실행 흐름

| 단계 | 사용 모듈 | 결과물 |
|---|---|---|
| `collect` | `collect_recipe_links.py` | `recipe_ids.json` (+ ID 큐로 실시간 전달) |
| `pdf` | `save_recipes_pdf.py` | `original_recipes/*.pdf` (+ PDF 큐로 실시간 전달) |
| `structure` | `structured.py` | `structured_recipes/<recipe_id>.json` |

각 스크립트는 예전처럼 단독 실행도 가능하다 (`uv run python recipes/collect_recipe_links.py "볶음밥" 20` 등).

## 기본 사용법

프로젝트 루트(`chatbot_project/`)에서 실행:

```bash
# 전체 실행: "볶음밥" 검색, 1~20페이지 수집 ∥ PDF 저장(0~200) ∥ 구조화
uv run python recipes/recipe_pipeline.py "볶음밥" 20
```

## 옵션

```bash
# PDF 저장 범위 지정 (배치 실행용, ID 도착 순서 기준)
uv run python recipes/recipe_pipeline.py "볶음밥" 20 --start 0 --end 200
uv run python recipes/recipe_pipeline.py "볶음밥" 20 --start 200 --end 500

# 1단계 건너뛰기: 기존 recipe_ids.json의 ID를 큐에 흘려보냄
uv run python recipes/recipe_pipeline.py "볶음밥" 20 --skip-collect

# 2단계까지 건너뛰기: 기존 PDF를 바로 3단계로 전달, 구조화만 실행
uv run python recipes/recipe_pipeline.py "볶음밥" 20 --skip-collect --skip-pdf

# 3단계 LLM 동시 요청 수 늘리기 (기존 PDF가 많이 쌓여있을 때 유용)
uv run python recipes/recipe_pipeline.py "볶음밥" 20 --skip-collect --skip-pdf --llm-workers 3
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--start` | 0 | PDF 저장 시작 인덱스 (ID 도착 순서 기준) |
| `--end` | 200 | PDF 저장 끝 인덱스 |
| `--skip-collect` | - | 1단계(링크 수집) 건너뛰기 |
| `--skip-pdf` | - | 2단계(PDF 저장) 건너뛰기 |
| `--llm-workers` | 1 | 3단계 동시 LLM 요청 수 |

## 주의사항

- **클로드**: `LLM_PROVIDER=claude`인 경우 `ANTHROPIC_API_KEY`가 `.env`에 설정되어 있어야 함
- **중복 방지**: 3단계는 원본 PDF만 읽으며, `structured_recipes/<id>.json`이 이미 있는
  레시피는 자동으로 건너뜀 — 중단 후 재실행해도 토큰 낭비 없음
- **딜레이**: 서버 부하 최소화를 위한 딜레이(수집 2.5초/PDF 5초)는 그대로 유지됨 — 줄이지 말 것
- `--skip-collect` 지정 시 `recipe_ids.json`이 없으면 에러 메시지와 함께 중단됨
- 이미 저장된 PDF는 2단계에서 다운로드를 건너뛰고 경로만 3단계로 전달함
