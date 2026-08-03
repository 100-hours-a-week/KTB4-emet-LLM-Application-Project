"""
재료의 성분 카테고리 태깅 모듈.
generalized_category_rules(탄닌+철분, 퓨린 조합 등)처럼 개별 재료가 아니라
"성분 카테고리" 단위로 매칭해야 하는 규칙을 위해 사용한다.

ingredient_synonyms.normalize_ingredient_name()으로 정규화된 대표명을 키로 사용한다.
"""

from ingredient_synonyms import normalize_ingredient_name

## 카테고리 태그 상수 (오탈자 방지용)
TANNIN = "tannin"                    # 탄닌
IRON = "iron"                        # 철분
PURINE = "purine"                    # 퓨린 (통풍 관련)
CALCIUM = "calcium"                  # 칼슘
PHOSPHATE = "phosphate"              # 인/인산
CAFFEINE = "caffeine"                # 카페인
TYRAMINE_FERMENTED = "tyramine"      # 티라민 함유 발효식품
VITAMIN_C = "vitamin_c"              # 비타민C (환원제 역할 포함)
BENZOATE_PRESERVATIVE = "benzoate"   # 안식향산나트륨 등 방부제
HIGH_FAT_CHOLESTEROL = "high_fat"    # 고지방/고콜레스테롤
SPICY = "spicy"                      # 매운 음식 (캡사이신)
OXALATE = "oxalate"                  # 옥살산(수산)

## 대표명(normalize_ingredient_name 결과 기준) -> 카테고리 태그 집합
## 재료 하나가 여러 카테고리에 동시에 속할 수 있음 (예: 커피 = 탄닌 + 카페인)
INGREDIENT_CATEGORIES: dict[str, set[str]] = {
    "감": {TANNIN},
    "도토리묵": {TANNIN},
    "커피": {TANNIN, CAFFEINE},
    "홍차": {TANNIN, CAFFEINE},

    "철분제": {IRON},

    "닭고기": {PURINE},
    "맥주": {PURINE},
    "새우": {PURINE},
    "조개": {PURINE},
    "소시지": {PURINE},
    "돼지고기": {PURINE},  # 삼겹살+소주 조합 커버

    "치즈": {CALCIUM, TYRAMINE_FERMENTED},
    "우유": {CALCIUM},
    "멸치": {CALCIUM},
    "두부": {CALCIUM},
    "미역": {CALCIUM},

    "콩": {PHOSPHATE},
    "탄산음료": {PHOSPHATE},

    "초콜릿": {CAFFEINE},

    "레몬": {VITAMIN_C},
    "오렌지": {VITAMIN_C},
    "자몽": {VITAMIN_C},

    "버터": {HIGH_FAT_CHOLESTEROL},
    "소고기": {HIGH_FAT_CHOLESTEROL},

    "고춧가루": {SPICY},
    "고추장": {SPICY},

    "시금치": {OXALATE},
    "땅콩": {PURINE, OXALATE},  ## 퓨린(통풍)과 옥살산(땅콩+맥주 요로결석 근거) 둘 다 보유
}

## JSON의 한글 카테고리 라벨 -> 내부 태그 매핑
## generalized_category_rules의 "categories" 필드 문자열과 매칭할 때 사용
CATEGORY_LABEL_TO_TAG = {
    "탄닌 고함유 식품": TANNIN,
    "철분 고함유 식품": IRON,
    "퓨린 고함유 식품": PURINE,
    "티라민 함유 발효식품": TYRAMINE_FERMENTED,
    "특정 약물/조합": None,  ## 재료 카테고리가 아니라 참고용 문구라 매칭 대상에서 제외
    "안식향산나트륨 함유 음료": BENZOATE_PRESERVATIVE,
    "비타민C 함유 음료": VITAMIN_C,
    "고지방·고콜레스테롤 조합": HIGH_FAT_CHOLESTEROL,
    "매운 음식": SPICY,
    "우유": CALCIUM,
}


def get_ingredient_categories(name: str) -> set[str]:
    """재료명을 정규화한 뒤 해당 재료가 속한 카테고리 태그 집합을 반환."""
    normalized = normalize_ingredient_name(name)
    return INGREDIENT_CATEGORIES.get(normalized, set())
