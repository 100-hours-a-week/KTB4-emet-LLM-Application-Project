# Tilte: Food Recipe Generate Chat-bot

## version
- 0.0.1: alex's rag chain 
- 0.0.2: refactoring              <--- now processing
- 0.0.3: ranggraph migrations 
- 0.0.4:

### Development Phase
- 0.0.x: using model free gen ai(geminai, ollama, etc)  <--- now processing
- 0.1.x: using model not free gen ai(claude)
- 0.2.x: using model my gen ai

## 실행방법
~~~
ollama run gemma4:e2b-mlx
uv run pipeline.py
uv run uvicorn main:app --reload
~~~


## Data(draft)
### Train & Rag Document
1. 만개의 레시피   
https://www.10000recipe.com/?srsltid=AfmBOooLjpoIMbvss7HL5iXygBMquTRGr-oGYMjopTBaFqNWWb5L2QuT
- 1차: 각 요리 레시피 스크랩
- 2차: 요리 레시피 문서 정형화(요리이름,종류,재료)

### DB

1. 식품의약품안전처(식품영양성분 데이터베이스)   
https://various.foodsafetykorea.go.kr/nutrient/general/down/list.do
  - 요리 레시피 성분 및 칼로리 계산을 위한 데이터
  - 생성한 답변 레시피의 재료와 DB의 성분표 매칭해서 성분 및 칼로리 계산



## Flowchart(draft)
<img width="2720" height="2640" alt="query_analysis_and_regen_loop_v10" src="https://github.com/user-attachments/assets/f8f23cac-cd5d-4a99-a6a7-ee30e05d6f4d" />
<img width="2720" height="3200" alt="recipe_review_full_flow_vertical" src="https://github.com/user-attachments/assets/4e67ebf3-2831-4840-ac3b-f59692332603" />




## Description(draft)

- 제목
    현재 보유 식재료에 따른 요리 레시피 추천 챗봇
- 내용
    직접 요리재료를 입력하거나, 기록한 현재 보유 식재료를 기반으로 요리레시피를 추천하는 LLM 어플리케이션.
- 기능
    좋아하거나 소비기한때문에 반드시 넣고(처리하고) 싶은 재료, 제한성분(당,염분), 다이어트(칼로리제한), 근성장(단백질)을 고려해서 레시피 생성하기
    재료가 부족하다면 추가가 필요한 재료와 그에따른 레시피 추천하기
    추천한 레시피를 사용했단면 개인 히스토리로 저장해서, 다음에 동일한 재료 있을시 우선순위 높여서 추천하기
    나만의 요리 레시피 입력해놓고, 레시피 요청할때 만들 수 있으면 추천하기(RAG)
