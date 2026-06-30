# Tilte: Food Chat-bot

## Description
---
- 타이틀
    현재 보유 식재료에 따른 요리 레시피 추천 챗봇
- 내용
    직접 요리재료를 입력하거나, 기록한 현재 보유 식재료를 기반으로 요리레시피를 추천하는 LLM 어플리케이션.
    좋아하거나 소비기한때문에 반드시 넣고(처리하고) 싶은 재료, 제한성분(당,염분), 다이어트(칼로리제한), 근성장(단백질)을 고려해서 레시피 생성


## 목표
- 알파 버전: 볶음밥류 레시피 
- 베타 버전: 밥(쌀) 요리 레시피 

## Data
---
### Train & Rag Document
1. 만개의 레시피
https://www.10000recipe.com/?srsltid=AfmBOooLjpoIMbvss7HL5iXygBMquTRGr-oGYMjopTBaFqNWWb5L2QuT
- 1차: 각 요리 레시피 스크랩
- 2차: 요리 레시피 문서 정형화(요리이름,종류,재료,)

### DB
- 요리 레시피 성분 계산을 위한 데이터
1. 식품의약품안전처(식품영양성분 데이터베이스)
https://various.foodsafetykorea.go.kr/nutrient/general/down/list.do
- 재료 성분 DB다운

## Main
---

---
## Dir

main.py
|- app.py
|- model.py / model_genai.py
 |- 
 |-


## Function Flow
---

    직접 레시피 재료 입력 / 현재 보유 식재료 레시피 요청
                    ↓
       (선택)희망 필수재료, 요리 종류, 칼로리, 성분제한 요청
                    ↓
          < 레시피 생성 가능한가? > -(No)->    재료 부족으로 인한 레시피 추천 불가능 응답   ->  부족한 재료 응답 
                    |
                  (Yes)
                    |
                    ↓ 
            적합한 요리 레시피 리스트 응답
                    ↓