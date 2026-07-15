
"""
uv run -m recipes.structured
"""
import asyncio
import os
import re
from pathlib import Path
from dotenv import load_dotenv

from typing import Literal,List,Tuple,Union
from pydantic import BaseModel,TypeAdapter, Field
import json


import loader
import template


load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "google")





## 
class StructuredRecipe(BaseModel):
    title: str = Field(description="요리 이름 (부제의 재료가 있으면 '재료 요리이름' 형태)")
    servings: int = Field(description="분량 (인분)")
    cook_time: int = Field(description="조리시간 (분, 5분 단위)")
    ingredients: List[Tuple[str, float, str]] = Field(
        description="재료+양념 리스트. [재료명, 양, 단위]. 비수치 표현은 [재료명, -1, '']"
    )
    steps: str = Field(description="조리순서 (Tip 이후 제외, 줄바꿈으로 단계 구분)")

class RecipeList(BaseModel):
    recipes: List[StructuredRecipe] = Field(description="추출된 레시피 목록 (빈 문서는 제외)")



async def load_recipe_pdf():
    pdf_path = "/original_recipes"
    original_recipes = loader.fileloader_distributor(5)
    structured_recipe_list = []
    for original_recipe in original_recipes:
        print(original_recipe)
        print("\n\n")
        structured_recipe = recipe2strutured(original_recipe)
        ##structured_recipe_list.append(structured_recipe)
        recipes2json(structured_recipe)


def parse_recipes(raw: Union[str, list]) -> List[StructuredRecipe]:
    data = json.loads(raw) if isinstance(raw, str) else raw
    return TypeAdapter(List[StructuredRecipe]).validate_python(data)


## 레시피 정형화
def recipe2strutured(original_recipe):
    # 쿼리 내용을 기준으로 쿼리 타입을 분석
    print(LLM_PROVIDER)
    print("현재노드: recipe2strutured")
    print("\n\n")

    llm_model = loader.llm_loader()
    recipe2strutured_model = llm_model.with_structured_output(StructuredRecipe, method="json_schema" )
    query_strutured_recipe = template.recipe2strutured_prompt.format(recipe=original_recipe)
    strutured_recipe = recipe2strutured_model.invoke(query_strutured_recipe)

    print(strutured_recipe)
    print("\n\n")

    return parse_recipes(strutured_recipe)


async def recipes2json(recipes: List[StructuredRecipe]) -> None:
    out_path = Path("/structured_recipes")
    out_path.mkdir(parents=True, exist_ok=True)

    for idx, recipe in enumerate(recipes, start=1):
        slug = re.sub(r"[^0-9a-zA-Z가-힣]+", "_", recipe.title).strip("_") or "untitled"
        file_path = out_path / f"{idx:03d}_{slug}.json"
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(recipe.model_dump(), f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    print("\n작업 시작.")
    asyncio.run(load_recipe_pdf())
    print("\n작업 종료.")
"""
[{"title": "고추장 볶음밥", "servings": 1, "cook_time": 5, "ingredients": [["계란", 2.0, "개"], ["찬밥", 1.0, "공기"], ["고추장", 1.0, "T"], ["매실청", 1.0, "T"], ["참기름", 1.0, "T"], ["김가루", 1.0, "줌"]], "steps": "1. 1인분에 계란 2알을 준비합니다. 후라이팬에 식용유를 살짝 두르고, 원하는 면을 익혀줍니다.\n2. 바닥이 어느 정도 익으면 뭉개서 스크램블처럼 만듭니다.\n3. 계란 스크램블이 완성되면 밥을 넣고 함께 볶아줍니다.\n4. 고추장 1T와 매실청 1T를 넣고 비비듯이 볶습니다.\n5. 고추장이 밥과 잘 어우러지면 참기름을 넣고 조금 더 볶습니다.\n6. 김가루를 넣고 잘 섞어줍니다."}]
"""