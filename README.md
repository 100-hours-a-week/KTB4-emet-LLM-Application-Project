# Title: LLM 기반 요리 레시피 추천 어플리케이션 (LLM-based Recipe Recommendation Application)

## Description
  직접 요리재료를 입력하거나, 기록한 현재 보유 식재료를 기반으로 요리레시피를 추천하는 LLM 어플리케이션.

---
  
## Function
### Main
- 현재 가진 재료를 기반으로 레시피 제작 및 검색 해서 레시피 추천                       <--- **executable/In development**
### Sub
- 추가 재료가 필요한 레시피 추천                                                <--- **executable/In development**
- 추천한 레시피가 긍정적이면 새로운 레시피는 문서화 저장                              <--- **In development**
- 자동 음식 레시피 문서 업데이트                                                <--- **In development**
- 추천한 레시피가 부정적이면 해당 내용을 고려해서 재생성및 재탐색을 통한 레시피 재추천        <--- **In development**
- 개인 요청(제한성분(당,염분), 다이어트(칼로리제한), 근성장(단백질), 등)을 고려해서 레시피 추천
- 추천한 레시피를 사용했단면 개인 히스토리로 저장해서, 다음에 동일한 재료 있을시 우선순위 높여서 추천
- 나만의 요리 레시피 입력해서 검색가능한 문서화로 저장
      
---

## Flowchart(draft)
<img width="1360" height="2400" alt="image" src="https://github.com/user-attachments/assets/9d2d87e0-a7ee-4749-bfdb-99c608a8d73e" />


---
## version
### Patch Version (0.x.N) — Development Stage
- 0.x.1: alex's rag chain 
- 0.x.2: refactoring              
- 0.x.3: ranggraph   <--- **now processing**
### Minor Version (0.N.x) — LLM Provider Branch
- 0.0.x: adapt model free gen ai(geminai, ollama, etc)  <--- **now processing**
- 0.1.x: adapt model not free gen ai(claude)
- 0.2.x: adapt model my gen ai

---

## 실행방법

~~~
ollama run gemma4:e2b-mlx

# 1.before main query, evaluate RAG
uv run evaluate.py

# 2-1.main query(single query)
uv run graph.py

# 2-2.main query by fastapi(not build)
uv run uvicorn main:app --reload
~~~

## Data Source(draft)
### Train & Rag Document
1. 만개의 레시피   
- URL: https://www.10000recipe.com/?srsltid=AfmBOooLjpoIMbvss7HL5iXygBMquTRGr-oGYMjopTBaFqNWWb5L2QuT
- 레시피 문서

### DB

1. 식품의약품안전처(식품영양성분 데이터베이스)   
- URL: https://various.foodsafetykorea.go.kr/nutrient/general/down/list.do
- 요리 레시피 성분 및 칼로리 계산을 위한 데이터
- 생성한 답변 레시피의 재료와 DB의 성분표 매칭해서 성분 및 칼로리 계산




