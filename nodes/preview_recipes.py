import uuid
from typing import List, Set

from langchain_core.messages import HumanMessage, AIMessage

from schems import StructuredRecipe, RecipeList, RecipeOption, RecipeOptionList
from ingredient_synonyms import is_ingredient_satisfied

import llm
from templates import preview_recipes_prompts
from states import OverrallState
import os
from dotenv import load_dotenv
load_dotenv()

from ingredient_synonyms import is_ingredient_satisfied, SPECIALTY_INGREDIENTS

## 적합 판정 시 threshold(%) 기준
PREVIEW_TOTAL_COUNT = int(os.getenv("PREVIEW_TOTAL_COUNT")) 
GOOD_THRESHOLD_SMALL = 80   ## 재료 6~9개 레시피
GOOD_THRESHOLD_LARGE = 70   ## 재료 10개 이상 레시피
 
## present_recipe_options와 select_recipe_option이 반드시 같은 정렬 기준을 써야 번호가 일치함
def sort_options(options):
    return sorted(options, key=lambda o: len(o.needed_ingredients))


def compute_missing_ingredients(
    recipe_ingredient_names: Set[str],
    user_ingredient_names: Set[str],
) -> List[str]:
    """
    레시피 재료명 중 사용자 재료로 충족되지 않는 것(=부족한 재료)을 계산.
    동의어("계란"="달걀")와 상위/하위 개념(청사과 보유 -> 사과 요구 충족)을
    ingredient_synonyms 사전 기준으로 반영한다.
    """
    missing = [
        req for req in recipe_ingredient_names
        if not any(is_ingredient_satisfied(req, owned) for owned in user_ingredient_names)
    ]
    return sorted(missing)


def extract_ingredient_names(recipe: StructuredRecipe) -> Set[str]:
    """
    StructuredRecipe.ingredients ([name, amount, unit] 2D list)에서
    이름(0번 인덱스)만 뽑아 집합으로 반환.
    """
    names = set()
    for item in recipe.ingredients:
        if not item:
            continue
        name = item[0]
        if name:
            names.add(name)
    return names


def build_options_from_recipes(
    retrieved_recipes: RecipeList,
    user_ingredient_names: List[str],
) -> List[RecipeOption]:
    """
    RAG 검색 결과(RecipeList)를 RecipeOption 리스트로 변환.
    LLM 호출 없이 순수 집합 비교로 needed_ingredients를 계산한다.
    """
    user_names_set = set(user_ingredient_names)
    options: List[RecipeOption] = []

    for recipe in retrieved_recipes.recipes:
        recipe_names_set = extract_ingredient_names(recipe)

        if not recipe_names_set:
            continue

        needed = compute_missing_ingredients(recipe_names_set, user_names_set)

        options.append(
            RecipeOption(
                title=recipe.title,
                source="rag",
                recipe_id=recipe.recipe_id,
                needed_ingredients=needed,
            )
        )

    return options


## 추가 재료 레시피 이름과 추가 재료추출
def preview_recipe_options(state: OverrallState):
    print("\n현재노드: preview_recipe_options\n")
 
    needed_count = state.get("preview_needed_count", 1)
 
    if needed_count <= 0:
        print("부족분 없음 -> LLM 생성 건너뜀")
        return {"recipe_options": []}
 
    excluded_titles = [opt.title for opt in state.get("rag_options", [])]
 
    query_preview_recipe = preview_recipes_prompts.options_prompt.format(
        option_count=needed_count,
        ingredients=state["ingredient_list"].ingredients_name,
        excluded_titles=excluded_titles,
    )
 
    result = llm.invoke_structured(
        RecipeOptionList, query_preview_recipe, fallback=RecipeOptionList(options=[])
    )
 
    ## 각 generated 옵션에 고유 recipe_id 부여 (캐시 조회/저장용 키로 사용됨)
    for opt in result.options:
        opt.recipe_id = uuid.uuid4().hex[:8]
 
    print(f"\n\ngenerated_options: {result}\n\n")
 
    return {"recipe_options": result.options}


## RAG 레시피 문서를 레시피옵션으로 추출
def build_rag_recipe_options(state: OverrallState):
    print("\n현재노드: build_rag_recipe_options\n")

    recipe_options = build_options_from_recipes(
        state["retrieved_recipes"],
        state["ingredient_list"].ingredients_name,
    )
    return {"recipe_options": recipe_options}


## RAG 프리뷰레시피와 레시피 옵션의 프리퓨레시피 합쳐서 출력하는 노드
def present_recipe_options(state: OverrallState):
    print("\n현재노드: present_recipe_options\n")

    options = state["recipe_options"]

    if not options:
        return {
            "answer": "죄송해요, 지금 가진 재료로 제안할 수 있는 요리를 찾지 못했어요."
        }
    ## 현재 보유 재료 목록
    current_ingredients = state["ingredient_list"].ingredients_name
    ingredients_line = f"📋 현재 재료: {', '.join(current_ingredients)}\n"

    ## 추가재료가 없는(=바로 만들 수 있는) 옵션을 우선 배치(추가재료가 적은순)
    sorted_options = sort_options(options)
    sorted_options = sorted_options[:PREVIEW_TOTAL_COUNT]
    lines = [ingredients_line, "다음 중 어떤 요리로 하시겠어요?\n"]
    for idx, option in enumerate(sorted_options, start=1):
        if option.needed_ingredients:
            needed_str = ", ".join(option.needed_ingredients)
            lines.append(f"{idx}. {option.title} (추가 재료 필요: {needed_str})")
        else:
            lines.append(f"{idx}. {option.title} (추가 재료 없음)")

    ## 궁합이 안 좋다고 알려진 재료 조합이 있으면 안내 문구 추가
    warnings = state["ingredient_analysis_result"].combination_warnings
    if warnings:
        lines.append("\n💡 참고로 아래 재료 조합은 궁합이 안 좋다고 알려져 있어요:")
        for w in warnings:
            lines.append(f"- {w}")

    answer = "\n".join(lines)
    print(f"\n\npresent_recipe_options answer:\n{answer}\n\n")

    return {
        "answer": answer,
        "messages": [HumanMessage(content=state["query"]), AIMessage(content=answer)],
    }

def evaluate_rag_recipe(recipe_ingredient_names: list[str], user_ingredient_names: list[str]) -> str:
    """
    RAG로 찾은 레시피 하나가 지금 재료로 만들기에 적정한지 판정.
    LLM 호출 없음 (순수 계산).
 
    반환값: "적합" 또는 "부적합"
    """
    N = len(recipe_ingredient_names)
    if N == 0:
        return "부적합"
 
    ## 1단계: 특수 재료 게이트 (절대적 거부, 나머지 계산 안 함)
    for ing in recipe_ingredient_names:
        if ing in SPECIALTY_INGREDIENTS:
            return "부적합"
 
    ## 2단계: 재료 수가 적으면 간이 판정 (하나라도 맞으면 통과)
    if N < 3:
        has_match = any(
            is_ingredient_satisfied(req, owned)
            for req in recipe_ingredient_names
            for owned in user_ingredient_names
        )
        return "적합" if has_match else "부적합"
 
    ## 3단계: 재료 수가 많으면 점수제
    threshold = GOOD_THRESHOLD_SMALL if N < 10 else GOOD_THRESHOLD_LARGE
 
    score = 0.0
    for req in recipe_ingredient_names:
        satisfied = any(is_ingredient_satisfied(req, owned) for owned in user_ingredient_names)
        if satisfied:
            score += 1 / N
        else:
            ## 특수 재료가 아니라고 이미 1단계에서 확인됐으므로,
            ## 미보유 재료는 전부 "구할 수 있는 재료"로 간주해 절반 점수
            score += 1 / (2 * N)
 
    return "적합" if score * 100 >= threshold else "부적합"
 
 
def evaluate_rag_options(
    rag_recipes: list,  # StructuredRecipe 리스트 (retrieved_recipes.recipes)
    user_ingredient_names: list[str],
    max_count: int,
) -> tuple[list, int]:
    """
    RAG 레시피 전체를 순회하며 적정성 평가.
 
    반환값: (채택된 적합 레시피 리스트[최대 max_count개], 부족한 개수)
    """
    adequate = []
 
    for recipe in rag_recipes:
        recipe_names = [item[0] for item in recipe.ingredients if item]
        verdict = evaluate_rag_recipe(recipe_names, user_ingredient_names)
        if verdict == "적합":
            adequate.append(recipe)
 
    ## 적합 판정 전체를 needed_ingredients(부족 재료 수) 기준으로 정렬 후 상위 max_count개만 채택
    ## (compute_missing_ingredients는 build_rag_recipe_options에서 이미 계산되므로,
    ##  여기서는 간단히 재료 수 기준으로만 정렬. 필요 시 정확한 needed_ingredients 기준으로 교체)
    adequate_sorted = sorted(adequate, key=lambda r: len(r.ingredients))
    selected = adequate_sorted[:max_count]
 
    shortfall = max(max_count - len(selected), 0)
    return selected, shortfall
 