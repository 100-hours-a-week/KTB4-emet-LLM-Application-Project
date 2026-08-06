from schems import IngredientList, IngredientUpdate
from ingredient_synonyms import normalize_ingredient_name

import llm
from templates import ingredients_prompts
from states import OverrallState

from dotenv import load_dotenv
load_dotenv()


## recipe_options를 매 턴 초기화 (턴 간 옵션 누적 버그 방지)
## None을 반환하면 states.add_or_reset reducer가 목록을 비움
def reset_recipe_options(state: OverrallState):
    print("현재노드: reset_recipe_options")
    return {"recipe_options": None}


## 다음 노드 선택: 이전 재료 유무로 첫 턴/변경 턴 분기 (LLM 호출 없음)
def conditional_has_previous(state: OverrallState):
    print("현재 컨디셔널함수: conditional_has_previous")

    previous = state.get("ingredient_list")
    if previous and previous.ingredients:
        return "extract_ingredient_update"

    print("이전 재료 없음 -> 첫 턴 추출 (extract_ingredient)")
    return "extract_ingredient"


## 첫 턴: 질의에서 보유 재료 추출 후 전체 교체 diff로 변환
async def extract_ingredient(state: OverrallState):
    print("현재노드: extract_ingredient")

    query_extract_ingredient = ingredients_prompts.extract_prompt.format(query=state["query"])

    # is_empty는 @computed_field로 ingredients 기반 자동 계산되므로 생성자에 넘기지 않음
    result = await llm.ainvoke_structured(
        IngredientList, query_extract_ingredient, fallback=IngredientList(ingredients=[])
    )

    return {
        "ingredient_update": IngredientUpdate(mode="replace", add=result.ingredients)
    }


## 변경 턴: 발화가 기존 목록에 가하는 변경(diff)을 LLM 1회 호출로 판정+추출
## swap("대파 대신 토마토")도 remove_names + add 조합으로 표현됨
async def extract_ingredient_update(state: OverrallState):
    print("현재노드: extract_ingredient_update")

    query_update = ingredients_prompts.update_prompt.format(
        previous_ingredients=", ".join(state["ingredient_list"].ingredients_name),
        query=state["query"],
    )

    ## 실패 시 빈 diff로 폴백 -> 기존 목록이 그대로 유지됨 (정보를 잃지 않는 방향)
    result = await llm.ainvoke_structured(
        IngredientUpdate, query_update, fallback=IngredientUpdate(mode="diff")
    )

    print(f"ingredient_update: mode={result.mode}, add={[i.name for i in result.add]}, "
          f"remove={result.remove_names}")
    return {"ingredient_update": result}


## base에 candidates를 이어붙이되, 정규화된 대표명 기준으로 이미 나온 재료는 건너뛴다.
## candidates 안에서 서로 동의어인 항목끼리도 걸러진다
## (예: "계란이랑 달걀 있어"처럼 한 발화 안에 동의어 두 개가 같이 들어와도 하나만 남음).
## base 쪽 집합은 매 항목 추가 시 갱신되므로, 이전에는 diff 모드에서만 이렇게 처리되고
## replace 모드는 중복 제거가 아예 없었던 것도 함께 해결된다.
def _merge_deduped(base: list, candidates: list) -> list:
    seen = {normalize_ingredient_name(ing.name) for ing in base}
    merged = list(base)
    for ing in candidates:
        norm = normalize_ingredient_name(ing.name)
        if norm in seen:
            continue
        merged.append(ing)
        seen.add(norm)
    return merged


## diff를 기존 목록에 적용해 최종 ingredient_list 계산 (LLM 호출 없음 — 순수 코드)
## 중복 제거는 이 노드에서만 처리 (extract 계열 노드는 중복을 신경 쓸 필요 없음)
def apply_ingredient_modification(state: OverrallState):
    print("현재노드: apply_ingredient_modification")

    update = state["ingredient_update"]
    previous = state.get("ingredient_list")

    if update.mode == "replace" or not (previous and previous.ingredients):
        final_list = IngredientList(ingredients=_merge_deduped([], update.add))

    else:
        ## 제거 먼저, 추가 나중: 같은 이름 재교체("계란 2개로 바꿔줘")도 자연스럽게 처리
        ## 비교는 전부 정규화된 대표명 기준 ("달걀 빼줘"로 "계란"도 제거됨)
        remove_set = {normalize_ingredient_name(name) for name in update.remove_names}
        kept = [
            ing for ing in previous.ingredients
            if normalize_ingredient_name(ing.name) not in remove_set
        ]

        merged = _merge_deduped(kept, update.add)
        final_list = IngredientList(ingredients=merged)

    print(f"최종 재료 목록: {final_list.ingredients_name}")
    return {"ingredient_list": final_list}