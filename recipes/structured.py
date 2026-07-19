"""
- 올라마 켜진상태여야함
uv run -m recipes.structured
"""
import asyncio
import os
import re
from pathlib import Path
from dotenv import load_dotenv

from typing import List, Tuple
from pydantic import BaseModel, Field
import json


import loader
import template


load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "google")


class StructuredRecipe(BaseModel):
    title: str = Field(description="요리 이름 (부제의 재료가 있으면 '재료 요리이름' 형태)")
    servings: int = Field(description="분량 (인분)")
    cook_time: int = Field(description="조리시간 (분, 5분 단위)")
    ingredients: List[Tuple[str, float, str]] = Field(
        description="재료+양념 리스트. [재료명, 양, 단위]. 비수치 표현은 [재료명, -1, '']"
    )
    steps: str = Field(description="조리순서 (Tip 이후 제외, 줄바꿈으로 단계 구분)")


async def recipe2strutured(original_recipe) -> StructuredRecipe:
    print(LLM_PROVIDER)
    print("현재노드: recipe2strutured")
    print("\n\n")

    llm_model = loader.llm_loader()
    recipe2strutured_model = llm_model.with_structured_output(StructuredRecipe, method="json_schema")
    query_strutured_recipe = template.recipe2strutured_prompt.format(recipe=original_recipe)

    # with_structured_output이 이미 StructuredRecipe로 검증해서 반환하므로
    # parse_recipes(TypeAdapter 리스트 검증)를 다시 걸면 단일 객체 vs 리스트 타입 불일치로 죽음
    structured_recipe = await recipe2strutured_model.ainvoke(query_strutured_recipe)

    print(structured_recipe)
    print("\n\n")

    return structured_recipe


async def recipes2json(recipes: List[StructuredRecipe]) -> None:
    out_path = Path("/structured_recipes")
    out_path.mkdir(parents=True, exist_ok=True)

    for idx, recipe in enumerate(recipes, start=1):
        slug = re.sub(r"[^0-9a-zA-Z가-힣]+", "_", recipe.title).strip("_") or "untitled"
        file_path = out_path / f"{idx:03d}_{slug}.json"
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(recipe.model_dump(), f, ensure_ascii=False, indent=2)


async def load_recipe_pdf():
    original_recipes = loader.fileloader_distributor(5)

    # 여러 문서를 동시에 처리
    structured_recipes = await asyncio.gather(
        *(recipe2strutured(recipe) for recipe in original_recipes)
    )

    # 단일 객체가 아니라 리스트로 한 번에 저장
    await recipes2json(list(structured_recipes))


if __name__ == "__main__":
    print("\n작업 시작.")
    asyncio.run(load_recipe_pdf())
    print("\n작업 종료.")