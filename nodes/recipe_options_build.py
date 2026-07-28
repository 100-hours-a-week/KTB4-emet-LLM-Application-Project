from typing import List, Set

from schems import StructuredRecipe, RecipeList, RecipeOption


def compute_missing_ingredients(
    recipe_ingredient_names: Set[str],
    user_ingredient_names: Set[str],
) -> List[str]:
    """
    레시피 재료명 집합에서 사용자 재료명 집합을 뺀 차집합(=부족한 재료)을 계산.
    이름이 정확히 일치해야 "있다"고 판단됨 (예: "대파" != "파").
    """
    missing = recipe_ingredient_names - user_ingredient_names
    return sorted(missing)


def _extract_ingredient_names(recipe: StructuredRecipe) -> Set[str]:
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


def build_rag_recipe_options(
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
        recipe_names_set = _extract_ingredient_names(recipe)

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