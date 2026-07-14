from typing_extensions import TypedDict,Annotated
import operator
from langgraph.graph import StateGraph, MessagesState
from langgraph.graph.message import add_messages

## 예제 연습용 
class StateExample(MessagesState):
    count: Annotated[int, add_count]
    results: Annotated[list[str], operator.add]
    message: str   

def add_count(a: int, b: int) -> int:
    return a+b


## {messages,tool_calls_count,final_answer} add_messages Reducer 상속됨
## 0.0.1
class OverrallState_1(MessagesState):
    thread_id: str
    documents:str
    query: str
    answer: str
    type:str
    #message: list
    ## "JUDGE"
    reference: str
    prediction: str
    score:float

    ## check loop
    loop:int



## add multi documnets
class OverrallState(MessagesState):
    thread_id: str
    documents:str
    ingrediant: list

    recipes = list
    recipes_state = list
    recipes_craftable:str
    recipes_not_craftable:str

    query_type:str
    query: str

    answer: str
    type:str
    #message: list
    ## "JUDGE"
    reference: str
    prediction: str
    score:float

    ## check loop
    loop:int

