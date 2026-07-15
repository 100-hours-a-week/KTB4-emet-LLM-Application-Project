import os
from typing import Literal,List,Tuple
from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, AIMessage
from langsmith import Client

import loader
import template
import eval_data
from states import OverrallState

from dotenv import load_dotenv
load_dotenv()

## graph.py에서 초기화된 retriever가 주입됩니다.
retriever = None

DATASET_NAME = os.environ["LANGSMITH_PROJECT"]
EVAL_QUESTIONS = eval_data.EVAL_QUESTIONS

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "google")

## 미개발구간 출력
## 개발 진행중인 구간은 주석형태로 표시
def undeveloped(state: OverrallState):
    print("해당 구간은 아직 미개발입니다. 감사합니다.")
    return {"answer": f"죄송합니다. 해당 기능은 아직 개발 중입니다.{state["query_type"]}"}

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

## query_analysis
class QueryType(BaseModel):
    type: Literal["레시피 추천", "레시피 반응", "NONETYPE", "NONE"] = Field(
        description="사용자 질의의 분류 타입"
    )

def format_docs(ds):
    return "\n\n".join(d.page_content for d in ds)


async def node_retreive(state: OverrallState):
    print("현재노드: node_retreive")
    global retriever
    docs = await retriever.ainvoke(state["query"])
    print(f"[DEBUG] 검색된 문서 수: {len(docs)}")
    print(f"[DEBUG] 내용 미리보기: {[d.page_content[:50] for d in docs]}")
    return {"documents": format_docs(docs)}




## 질의 분석
def query_analysis(state: OverrallState):
    # node_prompt -> now -> retreiver_recipes
    #                    -> generate_recipes
    # 쿼리 내용을 기준으로 쿼리 타입을 분석
    print(LLM_PROVIDER)
    print("현재노드: query_analysis")
    llm_model = loader.llm_loader()
    query_analysis_model = llm_model.with_structured_output(QueryType, method="json_schema" )
    query_analysis = template.query_analysis_prompt.format(query=state["query"])

    result = query_analysis_model.invoke(query_analysis)

    print(type(result), result)

    return {"query_type": result}

## 다음 노드 선택
def conditional_query_type(state: OverrallState):
    
    print("현재 컨디셔널함수:conditional_query_type")
    print(f"query_type: {state["query_type"]}")
    if state["query_type"] == "레시피 추천":
        return ["retreiver_recipes", "generate_recipes"]
    elif state["query_type"] == "레시피 반응":
        return "undeveloped"
    elif state["query_type"] == "NONETYPE":
        return "undeveloped"
    elif state["query_type"] == "NONE":
        return "undeveloped"
    
    return "undeveloped"

## 재료 기반 레시피 검색
async def retreiver_recipes(state: OverrallState):
    ## query_analysis -> now -> confirm_ingrediant
    recipes = []
    global retriever
    
    ## undeveloped(): query -> ingrediant
    query = state["query"]
    docs = await retriever.ainvoke(query)
    print(f"[DEBUG] 검색된 레시피 수: {len(docs)}")
    print(f"[DEBUG] 레시피 미리보기: {[d.page_content[:50] for d in docs]}")

    return {"recipes": format_docs(recipes)}


## 재료 기반 레시피 생성
def generate_recipes(state: OverrallState):
    ## query_analysis -> now -> node_llm -> confirm_ingrediant

    ## undeveloped(): query -> ingrediant
    ## query_reipes = template.generate_recipes_prompt.format(query=state["query"], ingrediant=state["ingrediant"])
    query = template.recipe_answer_prompt.format(context=state["documents"], query=state["query"])

    return {"query": query}


## 레시피 정형화()
def recipe2strutured(state: OverrallState):
    # 쿼리 내용을 기준으로 쿼리 타입을 분석
    print(LLM_PROVIDER)
    print("현재노드: recipe2strutured")
    
    llm_model = loader.llm_loader()
    recipe2strutured_model = llm_model.with_structured_output(StructuredRecipe, method="json_schema" )
    strutured_recipe = template.query_analysis_prompt.format(query=state["query"])

    result = recipe2strutured_model.invoke(query_analysis)

    print(type(result), result)

    return {"query_type": result}



## 레시피 재료 검토
## 현재 버전: LLM에게 질문해서 재료가 부족한지 아닌지 판단
## 다음 버전: 정형화된 레시피에서 재료만 추출해서 직접비교
async def confirm_ingrediant(state: OverrallState):
    ## retreiver_recipes -> now ->
    ## generate_recipes -> node_llm ->
    ui = state["ingrediant"]
    recipes = state["recipes"]
    recipes_state = []
    llm_model = loader.llm_loader()

    for recipe in recipes:
        query_ingrediant = template.confirm_ingrediant_prompt.format(recipe=recipe, ingrediant=state["ingrediant"])
        human_msg = HumanMessage(content=query_ingrediant)
        recipe_state = llm_model.ainvoke(human_msg)
        recipes_state.append(recipe_state)

    return {"recipes_state": format_docs(recipes_state)}

    """
    #다음버전
    ## -1: 재료 부족 , 0: 재료 충분(잉여있음) 1:재료 정확히 일치
    ingrediant_state = 0

    recipes_craftable = []
    recipes_not_craftable = []

    ## 레시피 문서에서 재료 추출

    ## 추출한 재료들 [[양파,감자,당근,], [쌀밥,계란,김], ...]
    recipes_ingrediant = []
    for ri  in recipes_ingrediant:

        ## 1) 재료부족
        if ri - ui == [] :
            ingrediant_state = -1

        ## 2) 재료 충분(잉여있음)

        ## 3) 재료 정확히 일치
        elif ri == ui:
            ingrediant_state = 1
    """


async def node_prompt(state: OverrallState):

    type = state["type"]

    if type == "GENERATE":
        query = template.generate_answer_prompt.format(context=state["documents"], query=state["query"])
        print("This is GENERATE Prompt.")

    elif type == "RECIPE":
        query = template.recipe_answer_prompt.format(context=state["documents"], query=state["query"])
        print("This is Recipe Prompt.")

    elif type == "JUDGE":
        query = template.judge_prompt.format(query=state["query"], reference=state["reference"], prediction=state["prediction"])
        print("This is NONE Prompt.")

    else:
        print("This is JUDGE Prompt.")

    return {"query": query}


async def node_llm(state: OverrallState):
    
    llm_model = loader.llm_loader()
    human_msg = HumanMessage(content=state["query"])
    full_messages = state["messages"] + [human_msg]

    answer = ""
    async for chunk in llm_model.astream(full_messages):
        print(chunk.content, end="", flush=True)
        answer += chunk.content

    ai_msg = AIMessage(content=answer)

    return {"messages": [human_msg, ai_msg], "answer": answer}


async def node_evaluate(state: OverrallState):
    client = Client()
    print(f"검증 질문 수: {len(EVAL_QUESTIONS)}")

    existing = [d for d in client.list_datasets(dataset_name=DATASET_NAME)]

    inputs = [{"question": ex["question"]} for ex in EVAL_QUESTIONS]
    outputs = [{"answer": ex["answer"]} for ex in EVAL_QUESTIONS]

    ## 검증 질문 DB 존재
    if existing:
        dataset = existing[0]
        print(f"기존 Dataset 사용: {dataset.id}")
    else:
        ## 검증질문 생성
        dataset = client.create_dataset(
            dataset_name=DATASET_NAME,
            description="볶음밥 RAG 답변 품질 평가용",
        )
        print(f"새 Dataset 생성: {dataset.id}")
        client.create_examples(
            dataset_id=dataset.id,
            inputs=inputs,
            outputs=outputs,
        )
        print(f"Example {len(EVAL_QUESTIONS)}건 추가 완료")

    ## 검증질문 불러오기
    loaded = client.read_dataset(dataset_name=DATASET_NAME)
    examples = list(client.list_examples(dataset_id=loaded.id))
    print(f"총 Example 수: {len(examples)}")

    for ex in examples[:3]:
        print("Q:", ex.inputs["question"])
        print("A:", ex.outputs["answer"] if ex.outputs else "(없음)")
        print()

    return state


    
