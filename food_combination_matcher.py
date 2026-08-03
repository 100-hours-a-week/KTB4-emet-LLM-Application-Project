"""
레시피 재료 리스트를 받아 궁합이 안 좋은 조합을 찾아주는 매칭 모듈.

두 가지 방식으로 매칭한다:
1. check_pair_taboo   : food_combination_taboo.json의 combinations(구체적 재료 쌍) 매칭
2. check_category_taboo: generalized_category_rules(탄닌+철분, 퓨린 조합 등 카테고리 단위 규칙) 매칭

재료명 비교는 항상 ingredient_synonyms.normalize_ingredient_name()을 거친 대표명 기준으로 한다.
"""

import json
from itertools import combinations
from pathlib import Path

from ingredient_synonyms import normalize_ingredient_name
from ingredient_categories import get_ingredient_categories, CATEGORY_LABEL_TO_TAG

_DATA_PATH = Path(__file__).parent / "food_combination_taboo.json"

with open(_DATA_PATH, encoding="utf-8") as f:
    _DATA = json.load(f)

_COMBINATIONS = _DATA["combinations"]
_CATEGORY_RULES = _DATA["generalized_category_rules"]

## combinations를 빠른 조회를 위해 {frozenset({a, b}): 항목} 형태로 인덱싱
_PAIR_INDEX = {
    frozenset(normalize_ingredient_name(n) for n in item["pair"]): item
    for item in _COMBINATIONS
}


def check_pair_taboo(ingredient_list: list[str]) -> list[dict]:
    """
    주어진 재료 리스트 안에서, 사전에 등록된 '구체적 재료 쌍' 궁합이 있는지 찾는다.
    반환: [{"pair": [...], "reason": ..., "level": ..., "note": ...}, ...]
    """
    normalized = [normalize_ingredient_name(n) for n in ingredient_list]
    found = []
    seen_keys = set()

    for a, b in combinations(set(normalized), 2):
        key = frozenset({a, b})
        if key in _PAIR_INDEX and key not in seen_keys:
            found.append(_PAIR_INDEX[key])
            seen_keys.add(key)

    return found


def check_category_taboo(ingredient_list: list[str]) -> list[dict]:
    """
    주어진 재료 리스트가 특정 '카테고리 조합 규칙'(예: 탄닌+철분)에 걸리는지 확인.
    각 규칙은 categories 필드에 2개의 한글 카테고리 라벨을 갖고 있으며,
    재료 리스트 전체에서 두 카테고리가 모두 발견되면 매칭된 것으로 본다.

    반환: [{"categories": [...], "examples": [...], "reason": ..., "level": ..., "note": ...}, ...]
    """
    ## 재료 리스트 전체가 가진 카테고리 태그 합집합
    all_tags = set()
    for name in ingredient_list:
        all_tags |= get_ingredient_categories(name)

    found = []
    for rule in _CATEGORY_RULES:
        labels = rule["categories"]
        tags_needed = {CATEGORY_LABEL_TO_TAG.get(label) for label in labels}
        tags_needed.discard(None)  ## "특정 약물/조합" 같은 참고용 라벨은 매칭 대상에서 제외

        if not tags_needed:
            continue

        ## 규칙이 요구하는 태그가 전부 재료 리스트에 있으면 매칭
        ## (단, 태그가 1개뿐인 규칙 -- 예: 퓨린+퓨린 -- 은 같은 태그를 가진 재료가
        ##  2개 이상 있어야 의미가 있으므로 별도 처리)
        if len(tags_needed) == 1:
            tag = next(iter(tags_needed))
            matching_ingredients = [
                n for n in ingredient_list if tag in get_ingredient_categories(n)
            ]
            if len(matching_ingredients) >= 2:
                found.append(rule)
        else:
            if tags_needed.issubset(all_tags):
                found.append(rule)

    return found


def check_all(ingredient_list: list[str]) -> dict:
    """
    check_pair_taboo + check_category_taboo를 합쳐서 반환.
    반환 형태: {"pair_matches": [...], "category_matches": [...]}
    """
    return {
        "pair_matches": check_pair_taboo(ingredient_list),
        "category_matches": check_category_taboo(ingredient_list),
    }


if __name__ == "__main__":
    ## 간단한 동작 확인용
    test_cases = [
        ["꽃게", "단감", "간장"],
        ["시금치", "두부", "된장"],
        ["치킨", "생맥주"],
        ["새우", "맥주", "고추장"],
        ["커피", "철분보충제"],
        ["당근", "오이"],
        ["소고기", "고구마"],
    ]
    for ingredients in test_cases:
        result = check_all(ingredients)
        print(f"재료: {ingredients}")
        for m in result["pair_matches"]:
            print(f"  [재료쌍] {m['pair']} -> {m['reason']} ({m['level']})")
        for m in result["category_matches"]:
            print(f"  [카테고리] {m['categories']} -> {m['reason']} ({m['level']})")
        if not result["pair_matches"] and not result["category_matches"]:
            print("  매칭 없음")
        print()
