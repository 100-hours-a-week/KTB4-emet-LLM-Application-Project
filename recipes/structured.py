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


import ingestion.loader as loader
import ingestion.template as template


load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "google")



class StructuredRecipe(BaseModel):
    recipe_id: str | None = Field(default=None, description="레시피 고유 id (원본 파일명의 '_' 앞 숫자) 또는 생성된 레시피는 앞에G가 붙음")
    title: str = Field(description="요리 이름 (부제의 재료가 있으면 '재료 요리이름' 형태)")
    servings: int = Field(description="분량 (인분)")
    cook_time: int = Field(description="조리시간 (분, 5분 단위)")
    ingredients: List[Tuple[str, float, str]] = Field(
        description="재료+양념 리스트. [재료명, 양, 단위]. 비수치 표현은 [재료명, -1, '']"
    )
    steps: str = Field(description="조리순서 (Tip 이후 제외, 줄바꿈으로 단계 구분)")


async def recipe2strutured(recipe_text: str, max_retries: int = 2) -> StructuredRecipe:
    llm_model = loader.llm_loader()
    recipe2strutured_model = llm_model.with_structured_output(StructuredRecipe, method="json_schema")
    query_strutured_recipe = template.recipe2strutured_prompt.format(recipe=recipe_text)

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return await recipe2strutured_model.ainvoke(query_strutured_recipe)
        except Exception as e:
            last_error = e
            print(f"[재시도 {attempt + 1}/{max_retries}] {e}")

    raise last_error


def extract_recipe_id(source_path: str) -> str:
    stem = Path(source_path).stem
    match = re.match(r"(\d+)_", stem)
    return match.group(1) if match else stem


def save_recipe_json(recipe: StructuredRecipe, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    file_path = out_dir / f"{recipe.recipe_id}.json"
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(recipe.model_dump(), f, ensure_ascii=False, indent=2)


async def process_recipe(doc, out_dir: Path) -> None:
    ## 파일명에서 추출
    recipe_id = extract_recipe_id(doc.metadata.get("source", "unknown"))
    """
    ## 파일 이름 검증 코드
    source = doc.metadata.get("source", "unknown")
    print(f"[디버그] source: {source}")   # 실제로 들어오는 값 확인용
    recipe_id = extract_recipe_id(source)
    """
    
    try:
        structured_recipe = await recipe2strutured(doc.page_content)
        structured_recipe.recipe_id = recipe_id
        save_recipe_json(structured_recipe, out_dir)
        print(f"[성공] {recipe_id} - {structured_recipe.title}")
    except Exception as e:
        print(f"[실패] {recipe_id}: {e}")
    

# 기존 병렬 처리 버전 (동시에 여러 문서를 LLM에 요청)
async def load_recipe_pdf_parallel():
    original_recipes = loader.fileloader_distributor(5)
    out_dir = Path(__file__).resolve().parent / "structured_recipes"

    await asyncio.gather(
        *(process_recipe(doc, out_dir) for doc in original_recipes)
    )


# 새로 추가한 직렬 처리 버전 (문서를 하나씩 순서대로 처리)
async def load_recipe_pdf_serial():
    original_recipes = loader.fileloader_distributor(5)
    out_dir = Path(__file__).resolve().parent / "structured_recipes"

    for doc in original_recipes:
        await process_recipe(doc, out_dir)


if __name__ == "__main__":
    print("\n작업 시작.")
    # 필요에 따라 아래 둘 중 하나로 바꿔서 실행
    asyncio.run(load_recipe_pdf_serial())
    # asyncio.run(load_recipe_pdf_parallel())
    print("\n작업 종료.")