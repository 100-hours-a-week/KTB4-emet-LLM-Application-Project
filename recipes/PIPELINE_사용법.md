# 레시피 수집 파이프라인 사용법

`details/recipe_pipeline.py` — 레시피 수집 3단계를 하나로 묶은 랭그래프 중앙센터.

```
수집(collect_links) → PDF저장(save_pdfs) → 구조화(structure)
```

각 단계가 실패하면(종료코드 ≠ 0) 다음 단계로 넘어가지 않고 즉시 중단된다.

## 실행 흐름

| 노드 | 실행 스크립트 | 작업 디렉토리 | 결과물 |
|---|---|---|---|
| `collect_links` | `collect_recipe_links.py <검색어> <페이지수>` | `recipes/` | `recipe_ids.json` |
| `save_pdfs` | `save_recipes_pdf.py <start> <end>` | `recipes/` | `original_recipes/*.pdf` |
| `structure` | `python -m recipes.structured` | 프로젝트 루트 | `structured_recipes/*.json` |

## 기본 사용법

프로젝트 루트(`chatbot_project/`)에서 실행:

```bash
# 전체 실행: "볶음밥" 검색, 1~20페이지 수집 → PDF 저장(0~200) → 구조화
uv run python details/recipe_pipeline.py "볶음밥" 20
```

## 옵션

```bash
# PDF 저장 범위 지정 (배치 실행용)
uv run python details/recipe_pipeline.py "볶음밥" 20 --start 0 --end 200
uv run python details/recipe_pipeline.py "볶음밥" 20 --start 200 --end 500

# 1단계 건너뛰기: 기존 recipe_ids.json 재사용
uv run python details/recipe_pipeline.py "볶음밥" 20 --skip-collect

# 2단계까지 건너뛰기: 기존 PDF 재사용, 구조화만 실행
uv run python details/recipe_pipeline.py "볶음밥" 20 --skip-collect --skip-pdf
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--start` | 0 | PDF 저장 시작 인덱스 |
| `--end` | 200 | PDF 저장 끝 인덱스 |
| `--skip-collect` | - | 1단계(링크 수집) 건너뛰기 |
| `--skip-pdf` | - | 2단계(PDF 저장) 건너뛰기 |

## 주의사항

- **올라마**: `LLM_PROVIDER=ollama`인 경우 3단계 실행 전에 올라마가 켜져 있어야 함
- **딜레이**: 서버 부하 최소화를 위한 페이지 간 딜레이(2.5초/5초)는 각 스크립트에 그대로 유지됨 — 줄이지 말 것
- `recipe_ids.json`이 없는 상태에서 2단계로 진입하면 에러 메시지와 함께 중단됨
- 이미 저장된 PDF는 자동으로 건너뛰므로 중단 후 재실행해도 안전함
