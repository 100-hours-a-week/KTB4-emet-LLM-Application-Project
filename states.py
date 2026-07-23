from typing_extensions import TypedDict,Annotated
import operator
from langgraph.graph import StateGraph, MessagesState
from langgraph.graph.message import add_messages
import nodes.nodes as nodes

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
    ingredient_list: nodes.IngredientList
    ## 생성된 레시피(재료 검토 -> 레시피 생성)
    generated_recipe:nodes.GeneratedRecipe
    ## 검색된 레시피 리스트()
    retrieved_recipes: nodes.RecipeList

    ## ---- 아직 미사용 ----

    ## loops
    ### total_loop
    total_loop:int

