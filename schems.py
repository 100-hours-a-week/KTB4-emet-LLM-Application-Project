from pydantic import BaseModel, Field, model_validator, computed_field
from typing import Literal, List
## 
class StructuredRecipe(BaseModel):
    recipe_id: str | None = Field(default=None, description="레시피 고유 id (원본 파일명의 '_' 앞 숫자) 또는 생성된 레시피는 앞에G가 붙음(예) G123, G324)")
    title: str = Field(description="요리 이름 (부제의 재료가 있으면 '재료 요리이름' 형태)")
    servings: int = Field(description="분량 (인분)")
    cook_time: int = Field(description="조리시간 (분, 5분 단위)")
    ingredients: List[List] = Field(
        description="재료+양념 리스트. [재료명, 양, 단위]. 비수치 표현은 [재료명, -1, '']"
    )
    steps: str = Field(description="조리순서 (Tip 이후 제외, 줄바꿈으로 단계 구분)")


class RecipeType(BaseModel):
    recipe_type : Literal["generated_recipe", "add_ingredients_recipe", "rejected_recipe"] = Field(description="현재 레시피의 상태 분기점 판단 필드")
    

## 생성레시피: 정형화 레시피 포함 
class GeneratedRecipe(BaseModel):

    recipe_type : Literal["generated_recipe", "add_ingredients_recipe", "rejected_recipe"] = Field(description="현재 레시피의 상태 분기점 판단 필드")
    structured_recipe:StructuredRecipe | None = Field(default=None ,description="생성된 정형화 레시피 ")
    needed_ingredients: List[str] | None = Field(default=None, description="추출된 재료를 제외한 추가 재료 리스트")

class RecipeList(BaseModel):
    recipes: List[StructuredRecipe] = Field(description="추출된 레시피 목록 (빈 문서는 제외)")

## query_analysis
class QueryType(BaseModel):
    type: Literal["레시피 추천", "레시피 반응", "NONETYPE", "NONE"] = Field(
        description="사용자 질의의 분류 타입"
    )

class Ingredient(BaseModel):
    name: str = Field(description="재료명/조미료명 ex) 밥,계란,돼지고기,김,후추,소금,설탕,식용유")
    amount:float | None = Field(description="재료/조미료의 양 ex)0.5,1/3,1,4")
    amount_unit:str | None = Field(description="재료/조미료 측정 단위 ex) T,t,g,개,EA")
    
    @model_validator(mode="before")
    @classmethod
    def validator(cls,answer_ingredients):
        if len(answer_ingredients) == 3 : 
            return {"name":answer_ingredients[0], "amount":float(answer_ingredients[1]), "amount_unit":answer_ingredients[2]}

        raise ValueError("...")

    

class IngredientList(BaseModel):
    ingredients: List[Ingredient] = Field(description="사용자/레시피의 재료 양 단위")

    @computed_field
    @property
    def is_empty(self) -> bool:
        """재료가 하나도 없으면 True / 하나라도 있으면 False"""
        return len(self.ingredients) == 0

    @computed_field
    @property
    def ingredients_name(self) -> List[str]:
        """사용자/레시피의 재료 이름 (ingredients에서 자동 추출)"""
        return [ingredient.name for ingredient in self.ingredients]

## ======================================================================================================================================================== ##
## ======================================================================================================================================================== ##
## ======================================================================================================================================================== ##
## ======================================================================================================================================================== ##
## == made by claude == ##
## ======================================================================================================================================================== ##
## ======================================================================================================================================================== ##
## ======================================================================================================================================================== ##
## ======================================================================================================================================================== ##


class RecipeOption(BaseModel):
    """사용자에게 제시할 예비 선택지 한 항목 (LLM 생성 / RAG 탐색 공통)."""
    title: str = Field(description="요리 이름")
    source: Literal["generated", "rag"] = Field(
        description="이 옵션의 출처: LLM이 생성했는지, RAG 문서 탐색으로 찾았는지"
    )
    recipe_id: str | None = Field(
        default=None,
        description="RAG 탐색 결과인 경우 원본 레시피 id (StructuredRecipe.recipe_id와 동일, 정식 레시피 재조회용)",
    )
    needed_ingredients: List[str] = Field(
        default_factory=list,
        description="추가로 필요한 재료명 리스트. 추가 재료가 없으면 빈 리스트([]) = '없음'",
    )
 
 
class RecipeOptionList(BaseModel):
    """LLM 생성 옵션 + RAG 탐색 옵션을 합친 최종 선택지 목록."""
    options: List[RecipeOption] = Field(description="사용자가 고를 수 있는 전체 요리 선택지 목록")