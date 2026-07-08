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
class OverrollState(MessagesState):
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

