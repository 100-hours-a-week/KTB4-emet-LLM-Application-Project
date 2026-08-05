# Title: LLM 기반 요리 레시피 추천 어플리케이션 (LLM-based Recipe Recommendation Application)

## Description
  직접 요리재료를 입력하면 요리레시피를 추천하는 LLM 어플리케이션.

---
  
## Function
### Main
- 현재 가진 재료를 기반으로 레시피 생성(LLM) 및 검색(RAG)을 병합해서 레시피 추천        <--- **executable**
### Sub
- 추가 재료가 필요한 레시피 추천 (부족한 재료 목록 함께 제시)                        <--- **executable**
- 대화 중 재료 추가/제거/교체("대파 대신 토마토로 변경해줘" 등) 반영 후 재추천          <--- **executable**
- 재료명 동의어/상위-하위 개념 정규화(계란=달걀, 청사과⊂사과 등)로 매칭 정확도 향상        <--- **executable**
- 번호/이름/부정 표현("2번 말고 3번")까지 이해하는 레시피 선택                       <--- **executable**
- RAG 검색 결과의 재료 적정성 자동 평가(특수 재료 게이트 + 점수제)로 부실한 추천 필터링    <--- **executable**
- 동일 선택지 재선택 시 캐시 재사용으로 LLM 재호출 없이 즉시 응답                     <--- **executable**
- 레시피 데이터 수집 파이프라인(랜덤 키워드 수집 → PDF 저장 → LLM 구조화 → VDB 저장)      <--- **executable (수동 실행 + 서버 재시작 필요)**
  
- 추천한 레시피가 긍정적이면 새로운 레시피는 문서화 저장                              <--- **In development**
- 추천한 레시피가 부정적이면 해당 내용을 고려해서 재생성및 재탐색을 통한 레시피 재추천        <--- **In development**   
---

## Flowchart
<img width="2636" height="6070" alt="full_graph_current_korean" src="https://github.com/user-attachments/assets/5070d1ab-864d-481f-8c26-e29c08b87c0e" />

---

## RoadMap   
https://github.com/100-hours-a-week/KTB4-emet-LLM-Application-Project/blob/main/Roadmap.md   

---
## component(update: 2026.08.04)   
chatbot_project/   
├── app/   
├── Dockerfile  
├── data_pipeline/  
│   ├── collect_recipe_links.py  
│   ├── food_keywords.py  
│   ├── recipe_pipeline.py  
│   ├── save_recipes_pdf.py  
│   ├── structured.py  
│   ├── collected/  
│   │   └── recipe_ids.json  
│   ├── original_recipes/  
│   └── structured_recipes/  
├── graph.png  
├── graph.py  
├── ingredient_synonyms.py  
├── llm.py  
├── main.py  
├── model/  
├── nodes/  
│   ├── __init__.py  
│   ├── analysis.py  
│   ├── ingredients.py  
│   ├── nodes.py  
│   ├── preview_recipes.py  
│   └── recipes.py  
├── rag/  
│   ├── __init__.py  
│   ├── config.py  
│   ├── loader.py  
│   ├── local_embeddings.py  
│   └── vectorstore.py  
├── self_model/  
│   └── loader.py  
├── templates/  
│   ├── __init__.py  
│   ├── analysis_prompts.py  
│   ├── ingredients_prompts.py  
│   ├── preview_recipes_prompts.py  
│   ├── prompts.py  
│   └── recipes_prompts.py  
├── pyproject.toml  
├── schems.py  
├── states.py  
└── uv.lock   

---
## version
### Patch Version (0.x.N) — Development Stage
- 0.x.1: alex's rag chain 
- 0.x.2: refactoring              
- 0.x.3: langgraph   <--- **now processing**
### Minor Version (0.N.x) — LLM Provider Branch
- 0.0.x: adapt model free gen ai(geminai, ollama, etc)
- 0.1.x: adapt model not free gen ai(claude)  <--- **now processing**
- 0.2.x: adapt model my gen ai

---

## 실행방법

`.env`의 `LLM_PROVIDER`(`"google"` 또는 `"claude"`) 및 해당 API 키가 설정되어 있어야 합니다.
백엔드(챗봇 서버)와 데이터 파이프라인(레시피 수집기)은 별개 프로세스입니다.

> 임베딩은 LLM 프로바이더와 무관하게 로컬 모델(`sentence-transformers`의 `BAAI/bge-m3`)을 사용합니다.
> API 키가 필요 없는 대신, 최초 실행 시 모델 가중치(약 2.27GB)를 다운로드합니다
> (Docker 이미지는 빌드 시점에 미리 받아두므로 컨테이너 기동 시 재다운로드가 없습니다).

### 백엔드 (챗봇 서버)

FastAPI 서버 하나가 백엔드와 프런트(정적 페이지 서빙)를 모두 담당합니다.

~~~bash
cd chatbot_project
uv run uvicorn main:app --reload --port 8000
~~~

### 프론트 (웹 UI)

별도 서버 없이, 백엔드가 `/`에서 `static/index.html`을 그대로 서빙합니다.
백엔드를 먼저 띄운 뒤 브라우저로 접속하면 됩니다.

~~~
http://localhost:8000
~~~

`http://localhost:8000/docs`에서 FastAPI 자동 문서로 `/query`를 직접 호출해볼 수도 있습니다.

> 멀티턴(재료 추가/제거/변경 등) 테스트 시, 첫 응답으로 받은 `thread_id`를 이후 요청에도
> 그대로 실어 보내야 같은 대화로 이어집니다.

### 데이터 파이프라인 (레시피 수집기)

서버와 무관하게 독립 실행되는 스크립트로, 레시피를 수집(랜덤 키워드) → PDF 저장 →
LLM 구조화 → 벡터스토어(VDB) 저장까지 연속으로 처리합니다. 자세한 옵션은
[data_pipeline/PIPELINE_사용법.md](data_pipeline/PIPELINE_사용법.md) 참고.

~~~bash
cd chatbot_project

# 소량 테스트 (20개 처리 후 종료)
uv run python data_pipeline/recipe_pipeline.py --max-recipes 20

# 무제한 연속 실행 (Ctrl+C로 중단)
uv run python data_pipeline/recipe_pipeline.py
~~~

> 파이프라인이 저장한 새 레시피는 백엔드가 **재시작해야** 검색에 반영됩니다
> (서버는 시작 시 1회만 VDB를 로드합니다).

## Data Source
### Train & Rag Document
1. 만개의 레시피   
- URL: https://www.10000recipe.com/?srsltid=AfmBOooLjpoIMbvss7HL5iXygBMquTRGr-oGYMjopTBaFqNWWb5L2QuT
- 레시피 문서


### DB(미사용)

1. 식품의약품안전처(식품영양성분 데이터베이스)   
- URL: https://various.foodsafetykorea.go.kr/nutrient/general/down/list.do
- 요리 레시피 성분 및 칼로리 계산을 위한 데이터
- 생성한 답변 레시피의 재료와 DB의 성분표 매칭해서 성분 및 칼로리 계산




