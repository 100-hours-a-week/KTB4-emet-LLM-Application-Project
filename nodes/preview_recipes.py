from typing import List, Set

from langchain_core.messages import HumanMessage, AIMessage

from schems import StructuredRecipe, RecipeList, RecipeOption, RecipeOptionList
from ingredient_synonyms import is_ingredient_satisfied

import llm
from templates import preview_recipes_prompts
from states import OverrallState

from dotenv import load_dotenv
load_dotenv()


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

    query_preview_recipe = preview_recipes_prompts.options_prompt.format(
        option_count= 1,
        ingredients=state["ingredient_list"].ingredients_name
        )

    result = llm.invoke_structured(
        RecipeOptionList, query_preview_recipe, fallback=RecipeOptionList(options=[])
    )

    print(f"\n\nrecipe_options: {result}\n\n")

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
def present_recipe_options (state:OverrallState):
    print("\n현재노드: present_recipe_options\n")

    options = state["recipe_options"]

    if not options:
        return {
            "answer": "죄송해요, 지금 가진 재료로 제안할 수 있는 요리를 찾지 못했어요."
        }

    ## 추가재료가 없는(=바로 만들 수 있는) 옵션을 우선 배치(추가재료가 적은순)
    sorted_options = sort_options(options)

    lines = ["다음 중 어떤 요리로 하시겠어요?\n"]
    for idx, option in enumerate(sorted_options, start=1):
        if option.needed_ingredients:
            needed_str = ", ".join(option.needed_ingredients)
            lines.append(f"{idx}. {option.title} (추가 재료 필요: {needed_str})")
        else:
            lines.append(f"{idx}. {option.title} (추가 재료 없음)")

    answer = "\n".join(lines)
    print(f"\n\npresent_recipe_options answer:\n{answer}\n\n")

    return {
        "answer": answer,
        "messages": [HumanMessage(content=state["query"]), AIMessage(content=answer)],
    }
