"""
요리 이름 직접 검색 흐름.

재료 나열 없이 특정 요리 이름을 대며 그 레시피를 요청하는 경우 전용.
RAG로 먼저 찾아보고, 후보들 중 요청 이름과 실질적으로 같은 요리를 LLM으로 판정한 뒤
(같은 요리의 여러 버전이면 전부) 그대로 보여주고, 하나도 없으면 LLM이 새로 생성한다.
선택 화면 전에 레시피 본문(재료+조리순서)까지 이미 확보해두고,
"선택"은 finalize_recipe/fetch_rag_recipe의 캐시 조회로 처리한다.
"""

import uuid

from schems import (
    RecipeOption,
    RecipeList,
    StructuredRecipe,
    IngredientAnalysisResult,
    NameMatchResult,
    NameGenerationResult,
)

import llm
from templates import name_search_prompts
from states import OverrallState
from rag.web_search import web_search
from . import recipes as recipes_module
from .recipes import parse_recipe_docs
from .analysis import build_combination_warnings

from dotenv import load_dotenv
load_dotenv()

## 이름 검색용 후보 개수. 전역 retriever의 RETRIEVER_K(=12)가 이미 12개를 가져오므로
## 추가 검색 비용 없이 그대로 12개까지 판정 후보로 쓴다.
NAME_SEARCH_CANDIDATES = 12


def _extract_ingredient_names(recipe: StructuredRecipe) -> list[str]:
    """StructuredRecipe.ingredients에서 이름만 뽑는다. (전체 재료 — 부족분 계산 없음)"""
    return [item[0] for item in recipe.ingredients if item and item[0]]


def _is_valid_recipe(recipe: StructuredRecipe) -> bool:
    """요리에 필요한 필수 정보(제목/재료/조리순서)가 전부 채워져 있는지 검사.
    LLM 호출 없는 순수 필드 검증 — 정규화 과정에서 필드가 비어 저장된
    불량 RAG 문서를 이름 매칭 판정 전에 걸러내기 위함."""
    if not recipe.title or not recipe.title.strip():
        return False
    if not _extract_ingredient_names(recipe):
        return False
    if not recipe.steps or not recipe.steps.strip():
        return False
    return True


## 요리 이름으로 RAG 검색
async def search_by_name(state: OverrallState):
    print("\n현재노드: search_by_name\n")

    dish_name = state["query_type"].dish_name
    docs = await recipes_module.retriever.ainvoke(dish_name)

    ## recipe_options는 이 흐름의 시작점이므로 여기서 턴 초기화도 함께 처리한다.
    ## (reset_recipe_options 노드는 재료 흐름의 conditional_has_previous에 라우팅이
    ##  묶여 있어 그대로 재사용하기 애매해서, 이 노드가 직접 None을 반환해 리셋한다)
    if not docs:
        print("[DEBUG] 이름 검색 결과 없음")
        return {"recipe_options": None, "retrieved_recipes": RecipeList(recipes=[])}

    candidates = parse_recipe_docs(docs)[:NAME_SEARCH_CANDIDATES]
    print(f"[DEBUG] 이름 검색 후보 {len(candidates)}개: {[c.title for c in candidates]}")

    return {"recipe_options": None, "retrieved_recipes": RecipeList(recipes=candidates)}


## 정규화 불량(필수 필드 누락) 후보를 이름 매칭 판정 전에 제거. LLM 호출 없음.
def filter_valid_candidates(state: OverrallState):
    print("\n현재노드: filter_valid_candidates\n")

    candidates = state["retrieved_recipes"].recipes
    valid = [r for r in candidates if _is_valid_recipe(r)]

    dropped = [r.recipe_id for r in candidates if not _is_valid_recipe(r)]
    if dropped:
        print(f"[DEBUG] 정규화 불량 후보 {len(dropped)}개 제외: {dropped}")

    return {"retrieved_recipes": RecipeList(recipes=valid)}


## 후보 제목들과 요청 요리 이름을 LLM으로 비교 판정
def judge_name_match(state: OverrallState):
    print("\n현재노드: judge_name_match\n")

    candidates = state["retrieved_recipes"].recipes
    dish_name = state["query_type"].dish_name

    if not candidates:
        print("[DEBUG] 후보 없음 -> 생성 분기로")
        return {"name_match_result": NameMatchResult(matched_recipe_ids=[])}

    candidates_str = "\n".join(f"- recipe_id={c.recipe_id}: {c.title}" for c in candidates)
    query_name_match = name_search_prompts.name_match_prompt.format(
        candidates=candidates_str,
        dish_name=dish_name,
    )

    result = llm.invoke_structured(
        NameMatchResult, query_name_match, fallback=NameMatchResult(matched_recipe_ids=[])
    )

    print(f"[DEBUG] name_match_result: {result}")
    return {"name_match_result": result}


## 다음 노드 선택
def conditional_name_match(state: OverrallState):
    print("현재 컨디셔널함수: conditional_name_match")
    if state["name_match_result"].matched_recipe_ids:
        return "resolve_rag_name_match"
    return "generate_recipe_by_name"


## RAG 적합: 매칭된 레시피(들)를 그대로 옵션으로 확정 (1개 또는 여러 개)
def resolve_rag_name_match(state: OverrallState):
    print("\n현재노드: resolve_rag_name_match\n")

    matched_ids = state["name_match_result"].matched_recipe_ids
    candidates_by_id = {r.recipe_id: r for r in state["retrieved_recipes"].recipes}

    options = []
    warnings = []
    for matched_id in matched_ids:
        matched = candidates_by_id.get(matched_id)
        if matched is None:
            ## judge가 후보 목록에 없는 recipe_id를 지어낸 경우에 대한 방어
            print(f"[WARN] matched_recipe_id={matched_id} 후보 목록에서 못 찾음 -> 제외")
            continue

        ingredient_names = _extract_ingredient_names(matched)
        options.append(RecipeOption(
            title=matched.title,
            source="rag",
            recipe_id=matched.recipe_id,
            ## 이 흐름은 "부족분"이 아니라 레시피의 전체 재료를 보여준다
            ## (present_recipe_options가 query_type으로 문구를 분기해서 표시함)
            needed_ingredients=ingredient_names,
        ))
        ## 후보마다 별개의 레시피라 재료를 합쳐서 궁합을 보면 서로 무관한 재료끼리
        ## 오탐 경고가 생길 수 있어, 레시피별로 각각 계산 후 합친다.
        for w in build_combination_warnings(ingredient_names) or []:
            if w not in warnings:
                warnings.append(w)

    if not options:
        ## 매칭된 id 전부가 후보 목록에 없던 경우(=전부 지어낸 경우)에 대한 방어
        print("[WARN] 매칭된 recipe_id를 후보 목록에서 하나도 못 찾음 -> 생성으로 폴백")
        return generate_recipe_by_name(state)

    ingredient_analysis_result = IngredientAnalysisResult(
        feasibility="directly_cookable",
        reason=None,
        combination_warnings=warnings,
    )

    return {
        "recipe_options": options,
        "ingredient_analysis_result": ingredient_analysis_result,
    }


## RAG 부적합: 웹 검색으로 실존 여부를 먼저 확인한 뒤, 실존하는 요리면 검색 결과를
## 반영해서 레시피를 생성. 검색 근거가 없으면 지어내지 않고 "실존하지 않는 요리"로 응답.
def generate_recipe_by_name(state: OverrallState):
    print("\n현재노드: generate_recipe_by_name\n")

    dish_name = state["query_type"].dish_name
    search_results = web_search(dish_name)
    print(f"[DEBUG] 웹 검색 결과 길이: {len(search_results)}자")

    query_generate = name_search_prompts.generate_recipe_by_name_prompt.format(
        dish_name=dish_name,
        search_results=search_results or "(검색 결과 없음)",
    )

    result = llm.invoke_structured(NameGenerationResult, query_generate, fallback=None)

    if result is None:
        print("[WARN] 이름 기반 레시피 생성 실패")
        ## recipe_options는 search_by_name에서 이미 리셋된 상태로 남아있어
        ## present_recipe_options가 "찾지 못했어요" 메시지로 안전하게 처리한다.
        return {}

    if not result.is_real_dish:
        reason = result.invalid_reason or "검색 결과에서 실존 근거를 찾지 못했습니다."
        print(f"[DEBUG] 실존하지 않는 요리로 판단: {reason}")
        return {"invalid_dish_reason": reason}

    structured = result.recipe
    if structured is None:
        print("[WARN] is_real_dish=True인데 recipe가 비어있음 -> 생성 실패로 처리")
        return {}

    if not structured.recipe_id:
        structured.recipe_id = f"G{uuid.uuid4().hex[:8]}"

    option_id = uuid.uuid4().hex[:8]
    ingredient_names = _extract_ingredient_names(structured)
    option = RecipeOption(
        title=structured.title,
        source="generated",
        recipe_id=option_id,
        needed_ingredients=ingredient_names,
    )

    ## 선택 전에 이미 완성본을 확보해뒀으므로 finalize_recipe 캐시를 미리 채워서,
    ## 사용자가 "선택"할 때 재생성 없이 캐시 적중으로 바로 나가도록 한다.
    cache_key = f"generated:{option_id}"
    finalized_recipes = state.get("finalized_recipes", {})

    ingredient_analysis_result = IngredientAnalysisResult(
        feasibility="directly_cookable",
        reason=None,
        combination_warnings=build_combination_warnings(ingredient_names),
    )

    return {
        "recipe_options": [option],
        "finalized_recipes": {**finalized_recipes, cache_key: structured},
        "ingredient_analysis_result": ingredient_analysis_result,
    }
