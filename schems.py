from pydantic import BaseModel, Field, model_validator, computed_field
from typing import Literal, List
## 
class StructuredRecipe(BaseModel):
    recipe_id: str | None = Field(default=None, description="레시피 고유 id (원본 파일명의 '_' 앞 숫자) 또는 생성된 레시피는 앞에G가 붙음(예) G123, G324)")
    title: str = Field(description="요리 이름 (부제의 재료가 있으면 '재료 요리이름' 형태)")
    servings: int = Field(description="분량 (인분)")
    cook_time: int = Field(description="조리시간 (분, 5분 단위)")
    ingredients: List[List[str | float]] = Field(
    description="재료+양념 리스트. [재료명, 양, 단위]. 비수치 표현은 [재료명, -1, '']")
    steps: str = Field(description="조리순서 (Tip 이후 제외, 줄바꿈으로 단계 구분)")

## 재료 요리 가능성 
class IngredientFeasibility(BaseModel):
    feasibility: Literal[
        "directly_cookable", "needs_more_ingredients", "not_cookable"
    ] = Field(description="현재 재료로 요리가 가능한지에 대한 판정 결과")
    reason: str | None = Field(
                default=None,
                description=(
                    "not_cookable일 때만 채움. 왜 요리가 불가능한지 구체적 이유. "
                    "예: 재료 수가 너무 적음 / 재료 조합이 요리로 성립하지 않음 / "
                    "먹을 수 없는 재료가 포함됨 / 구하기 힘든 고급 재료가 필요함 등"
                ),
            )
 
## 생성레시피: 정형화 레시피 포함 
class IngredientAnalysisResult(BaseModel):

    feasibility: Literal[
        "directly_cookable", "needs_more_ingredients", "not_cookable"
    ] = Field(description="현재 재료 기준 요리 가능 여부 판정")
    reason: str | None = Field(
        default=None,
        description="not_cookable일 때만 채움. 왜 요리가 불가능한지 구체적 이유.",
    )
    structured_recipe: StructuredRecipe | None = Field(
        default=None, description="생성된 정형화 레시피"
    )
    needed_ingredients: List[str] | None = Field(
        default=None, description="추출된 재료를 제외한 추가 재료 리스트"
    )
    combination_warnings: List[str] | None = Field(
        default=None,
        description="궁합이 좋지 않다고 알려진 재료 조합 경고 메시지 목록. 없으면 None.",
    )
    

class RecipeList(BaseModel):
    recipes: List[StructuredRecipe] = Field(description="추출된 레시피 목록 (빈 문서는 제외)")

## query_analysis
class QueryType(BaseModel):
    type: Literal["레시피 추천", "레시피 선택", "NONETYPE", "NONE"] = Field(
        description="사용자 질의의 분류 타입"
    )
    reason: str | None = Field(
        default= None,
        description="이 타입으로 판단한 이유, 'NONETYPE', 'NONE'인 경우 사용자에게 출력"
    )

class Ingredient(BaseModel):
    name: str = Field(description="재료명/조미료명 ex) 밥,계란,돼지고기,김,후추,소금,설탕,식용유")
    amount:float | None = Field(description="재료/조미료의 양 ex)0.5,1/3,1,4")
    amount_unit:str | None = Field(description="재료/조미료 측정 단위 ex) T,t,g,개,EA")
    
    @model_validator(mode="before")
    @classmethod
    def validator(cls,answer_ingredients):
        ## json_schema 구조화 출력은 dict 형태({"name": ..., "amount": ..., "amount_unit": ...})로 들어옴
        if isinstance(answer_ingredients, dict):
            return answer_ingredients
        ## 구버전(리스트 프롬프트) 형태 [재료명, 양, 단위]는 dict로 변환
        if isinstance(answer_ingredients, (list, tuple)) and len(answer_ingredients) == 3:
            name, amount, unit = answer_ingredients
            return {
                "name": name,
                "amount": float(amount) if amount not in (None, "") else None,
                "amount_unit": unit,
            }
        raise ValueError("재료는 dict 또는 [재료명, 양, 단위] 형태여야 합니다")

    

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


## extract_ingredient_update: 이번 발화가 기존 재료 목록에 가하는 변경(diff)
## swap("대파 대신 토마토")도 remove_names=[대파] + add=[토마토]로 표현 가능
class IngredientUpdate(BaseModel):
    mode: Literal["diff", "replace"] = Field(
        description=(
            "diff: 기존 목록에 add/remove_names만 반영, "
            "replace: 기존 목록을 무시하고 add로 통째로 교체"
        )
    )
    add: List[Ingredient] = Field(
        default_factory=list,
        description="추가하거나 새로 언급된 보유 재료 목록",
    )
    remove_names: List[str] = Field(
        default_factory=list,
        description="기존 목록에서 뺄 재료명 목록",
    )


class RecipeOption(BaseModel):
    """사용자에게 제시할 예비 선택지 한 항목 (LLM 생성 / RAG 탐색 공통)."""
    title: str = Field(description="요리 이름")
    source: Literal["generated", "rag"] = Field(
        description="이 옵션의 출처: LLM이 생성했는지, RAG 문서 탐색으로 찾았는지"
    )
    recipe_id: str | None = Field(
        default=None,
        description=(
            "고유 식별자. RAG 탐색 결과인 경우 원본 레시피 id "
            "(StructuredRecipe.recipe_id와 동일, 정식 레시피 재조회용). "
            "generated인 경우 preview_recipe_options에서 부여하는 임시 uuid "
            "(finalize_recipe 캐시 조회용, StructuredRecipe.recipe_id와는 무관)."
        ),
    )
    needed_ingredients: List[str] = Field(
        default_factory=list,
        description="추가로 필요한 재료명 리스트. 추가 재료가 없으면 빈 리스트([]) = '없음'",
    )
 
 
class RecipeOptionList(BaseModel):
    """LLM 생성 옵션 + RAG 탐색 옵션을 합친 최종 선택지 목록."""
    options: List[RecipeOption] = Field(description="사용자가 고를 수 있는 전체 요리 선택지 목록")



class OptionMatchResult(BaseModel):
    """사용자 발화가 옵션 목록 중 어떤 항목을 가리키는지 LLM이 판단한 결과."""
    selected_number: int | None = Field(
        default=None,
        description=(
            "사용자가 최종적으로 가리키는 옵션의 번호 (목록에 표시된 1부터 시작하는 번호). "
            "'2번 말고 3번'처럼 부정 표현이 섞여 있으면 최종적으로 원하는 번호를 반환. "
            "모호하거나 목록에 없는 요리를 말하면 반드시 null."
        ),
    )