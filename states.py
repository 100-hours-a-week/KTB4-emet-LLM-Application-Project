from typing import List
from typing_extensions import TypedDict,Annotated
import operator
from langgraph.graph import StateGraph, MessagesState
from langgraph.graph.message import add_messages
import schems

## recipe_options 전용 reducer: None이 오면 목록을 비우고(턴 간 누적 방지),
## 리스트면 이어붙임 (preview/RAG 병렬 노드 결과 병합은 기존과 동일)
def add_or_reset(left, right):
    if right is None:
        return []
    return (left or []) + right



## 기본 메세지 스테이트 -> 리팩토링에서 노드 진행에 따라 메시지 구분해서 분리예정
class OverrallState(MessagesState):
    thread_id: str
    ## 질의 입력
    query: str
    ## 질의 분석(질의 타입과 이유)
    query_type: schems.QueryType
    ## 질의 대답
    answer: str
    ## 질의에서 추추된 재료 리스트(재료 추출)
    ingredient_list: schems.IngredientList
    ## 이번 턴 발화가 재료 목록에 가하는 변경 diff (extract 계열 노드가 쓰는 임시 필드)
    ingredient_update: schems.IngredientUpdate
    ## 재료 분석 분기점 판정 결과 (ingredient_analysis 노드 → 조건부 분기용)
    ingredient_analysis_result: schems.IngredientAnalysisResult
    ## 검색된 레시피 리스트()
    retrieved_recipes: schems.RecipeList
    ## 레시피 이름 검색 흐름 전용: RAG 후보들과 요청 요리명이 같은지 판정한 결과
    name_match_result: schems.NameMatchResult
    ## RAG 적정성 평가(rag_adequacy_check)를 통과한 레시피 옵션 (preview_recipe_options가 LLM 생성 시 제목 중복 방지용으로 사용)
    rag_options: List[schems.RecipeOption]
    ## RAG 적정성 평가에서 계산한, LLM이 추가로 생성해야 할 개수
    preview_needed_count: int
    ## 레시피 이름과 재료정보 리스트 (None 업데이트 시 초기화되는 커스텀 reducer)
    recipe_options: Annotated[List[schems.RecipeOption], add_or_reset]
    ## 선택된 레시피
    selected_option: schems.RecipeOption
    ## 선택된 레시피의 내용 
    structured_recipe: schems.StructuredRecipe
    ## 이번 세션에서 완성 생성된(finalize_recipe) 레시피 캐시.
    finalized_recipes: dict[str, schems.StructuredRecipe]
    ## 이번 대화에서 이미 보여준 RAG 레시피의 recipe_id 누적.
    ## "다른 거 없어?" 재요청 시 rag_adequacy_check가 재검색 후보에서 제외하는 데 사용.
    shown_rag_ids: List[str]
    ## 이번 대화에서 이미 보여준 레시피 제목 누적 (RAG+생성 전체).
    ## LLM 재생성 시 같은 제목을 다시 만들지 않도록 excluded_titles에 합쳐서 사용.
    shown_titles: List[str]
    ## 이름 검색 생성 폴백(generate_recipe_by_name)에서, 웹 검색 결과 근거로
    ## 실존하지 않는 요리로 판단된 경우의 사유. present_recipe_options가
    ## recipe_options가 비었을 때 이 값이 있으면 더 구체적인 안내를 준다.
    invalid_dish_reason: str | None
 


    ## ---- 아직 미사용 ----

    ## loops
    ### total_loop
    total_loop:int

