from typing import List
from typing_extensions import TypedDict,Annotated
import operator
from langgraph.graph import StateGraph, MessagesState
from langgraph.graph.message import add_messages
import schems

## 예제 연습용 
class StateExample(MessagesState):
    count: Annotated[int, add_count]
    results: Annotated[list[str], operator.add]
    message: str   

def add_count(a: int, b: int) -> int:
    return a+b



## 기본 메세지 스테이트 -> 리팩토링에서 노드 진행에 따라 메시지 구분해서 분리예정
class OverrallState(MessagesState):
    thread_id: str
        ## 질의 입력
    query: str
    ## 질의 분석
    query_type:str
    ## 질의 대답
    answer: str
    ## 질의에서 추추된 재료 리스트(재료 추출)
    ingredient_list: schems.IngredientList
    ## 재료 분석 분기점 판정 결과 (ingredient_analysis 노드 → 조건부 분기용)
    ingredient_analysis_result:schems.IngredientAnalysisResult
    ## 검색된 레시피 리스트()
    retrieved_recipes: schems.RecipeList

    ## 레시피 이름과 재료정보 리스트
    recipe_options: Annotated[List[schems.RecipeOption], operator.add]
    ## 선택된 레시피
    selected_option: schems.RecipeOption
    ## 선택된 레시피의 내용 
    structured_recipe: schems.StructuredRecipe



    ## ---- 아직 미사용 ----

    ## loops
    ### total_loop
    total_loop:int

