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

# 1.befoer main query, evaluate RAG
uv run evaluate.py

# 2-1.main query(single query)
uv run graph.py

# 2-2.main query by fastapi(not build)
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



## User Using Flow(draft)
~~~

       (필수쿼리)직접 레시피 재료 입력 / 현재 보유 식재료 레시피 요청(세션유지)
                    |
                    ↓
       (선택쿼리)희망 필수재료, 요리 종류, 칼로리, 성분제한 요청(세션컨텍스트 유지)
                    |
                 모델 입력
                    ↓                                                                               
           < 레시피 생성/탐색  가능한가? >       --(No)-→    재료 부족으로 인한 레시피 추천 불가능한 이유 응답(부족한 필수 재료들, etc) 
                    |                                                   |
                    |                                                   ↓
                    |                                       부족한 재료로 추가시 생성 가능한 요리 레시피 응답
                    |                                                   |
                    |                                                   ↓
                  (Yes)                                    < 사용자가 부족한 필수 재료들 입수 가능여부 응답 >   --(No)-→  -↓ 
                    |                                                   |                                       |
                    |                                                 (Yes)                                     |
                    |                                                   |                                       |
                    ↓                                                   ↓                                       |
          적합한 요리 레시피 리스트 응답          ←---------            레시피가 재생성 및 재탐색                            |
                    |                                                   ↑                                      |
                    |                                       제공한 레시피 리스트 제외 처리(Loop Counting)              |
                    |                                                   ↑                                       |
                    |                                                 (Yes)                                     ↓
                    ↓                                                   |                                       
        < 사용자가 제공한 레시피 사용할지여부? >          --(No)-→         < Loop N번초과 안했는가? >      --(No)-→      - 모델 출력 → 
                    |                                                                                           |
                    |                                                                                           ↓
                  (Yes)                                                                              endpoint[레시피불가능]: 배달 추천
                    |
                 모델 출력
                    ↓   
     endpoint: 사용한 레시피에대한 새로운 Document 작성 및 저장(개인 히스토리)
~~~


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
