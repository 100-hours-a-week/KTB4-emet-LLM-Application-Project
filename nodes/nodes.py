import os
from typing import Literal,List,Tuple
from pydantic import BaseModel, Field, model_validator

from langchain_core.messages import HumanMessage, AIMessage
from langsmith import Client

import ingestion.loader as loader
import ingestion.template as template
import eval.eval_data as eval_data
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
    recipe_id: str | None = Field(default=None, description="레시피 고유 id (원본 파일명의 '_' 앞 숫자) 또는 생성된 레시피는 앞에G가 붙음(예) G123, G324)")
    title: str = Field(description="요리 이름 (부제의 재료가 있으면 '재료 요리이름' 형태)")
    servings: int = Field(description="분량 (인분)")
    cook_time: int = Field(description="조리시간 (분, 5분 단위)")
    ingredients: List[Tuple[str, float, str]] = Field(
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
    amount:float = Field(description="재료/조미료의 양 ex)0.5,1/3,1,4")
    amount_unit:str = Field(description="재료/조미료 측정 단위 ex) T,t,g,개,EA")
    
    @model_validator(mode="before")
    @classmethod
    def validator(cls,answer_ingredients):
        if len(answer_ingredients) == 3 : 
            return {"name":answer_ingredients[0], "amount":float(answer_ingredients[1]), "amount_unit":answer_ingredients[2]}

        raise ValueError("...")


    

class IngredientList(BaseModel):
    is_empty: bool =Field(description="재료가 하나도 없으면 True/재료가 하나라도 있으면 False")
    ingredients: List[Ingredient] = Field(description="사용자/레시피의 재료 양 단위")
    ingredients_type: List[str] = Field(description="사용자레시피의 재료 이름")

    def genrerate_type(self):
        self.ingredients_type = []
        for ingredient in self.ingredients:
           self.ingredients_type.append(ingredient.name)



def format_docs(ds):
    return "\n\n".join(d.page_content for d in ds)


## 질의 분석
def query_analysis(state: OverrallState):
    # node_prompt -> now -> retreiver_recipes
    #                    -> generate_recipe
    # 쿼리 내용을 기준으로 쿼리 타입을 분석
    print(LLM_PROVIDER)
    print("현재노드: query_analysis")
    llm_model = loader.llm_loader()
    query_analysis_model = llm_model.with_structured_output(QueryType, method="json_schema" )
    query_analysis = template.query_analysis_prompt.format(query=state["query"])

    result = query_analysis_model.invoke(query_analysis)

    print(type(result), result)

    return {"query_type": result.type}

## 다음 노드 선택
def conditional_query_type(state: OverrallState):
    print("현재 컨디셔널함수:conditional_query_type")
    print(f"query_type: {state["query_type"]}")
    print(state["query_type"])
    if state["query_type"] == "레시피 추천":
        return "extract_ingredient"
        #return ["retreiver_recipes", "generate_recipes"]
    elif state["query_type"] == "레시피 반응":
        return "undeveloped"
    elif state["query_type"] == "NONETYPE":
        return "undeveloped"
    elif state["query_type"] == "NONE":
        return "undeveloped"
    
    return "undeveloped"

## 질의 또는 레시피문서에서 재료 추출 -> 개발중
def extract_ingredient(state: OverrallState):
    print("현재노드: extract_ingredient")

    ## 이전 노드가 무엇인지 확인 필요!
    ## 질의분석 노드에서 왔다면 레시피 추출이 목적

    llm_model = loader.llm_loader()
    extract_ingredient_model = llm_model.with_structured_output(IngredientList, method="json_schema" )
    query_extract_ingredient = template.extract_ingredient_prompt.format(query=state["query"])
    try:
        result = extract_ingredient_model.invoke(query_extract_ingredient)
        print(type(result), result)
    except ValueError as e:
        print(f"검증 실패: {e}")
        result = IngredientList(is_empty=True, ingredients=[])

    return {"ingredient_list": result}

def ingredient_analysis(state: OverrallState):
    print("현재노드: ingredient_analysis")
    
    llm_model = loader.llm_loader()
    ingredient_analysis_model = llm_model.with_structured_output(RecipeType, method="json_schema" )
    query_ingredient_analysis = template.ingredient_analysis_prompt.format(ingredients=state["ingredient_list"].ingredients_type)
    try:
        result = ingredient_analysis_model.invoke(query_ingredient_analysis)
        generated_recipe = GeneratedRecipe(recipe_type=result.recipe_type, structured_recipe=None, needed_ingredients=None)
    except ValueError as e:
        print(f"검증 실패: {e}")
        generated_recipe = GeneratedRecipe()
    
    print(f"generated_recipe: {generated_recipe}")

    return {"generated_recipe": generated_recipe}



## 다음 노드 선택 -미완성-
def conditional_ingredient_analysis(state: OverrallState):

    print("현재 컨디셔널함수:conditional_query_type")
    recipe_type = state["generated_recipe"].recipe_type
    print(f"generated_recipe.recipe_type: {recipe_type}")

    ## 헷갈리지 말기 recipe_type == "generated_recipe" , 노드는 "generate_recipe"
    if recipe_type == "generated_recipe":
        return "generate_recipe"
    
    elif recipe_type == "add_ingredients_reipe":
        return "undeveloped"
    
    elif recipe_type == "rejecte_recipe":
        return "undeveloped"
    
    return "undeveloped"





## 재료 기반 레시피 검색
async def retreiver_recipes(state: OverrallState):
    print("현재노드: retreiver_recipes")
    ## query_analysis -> now -> confirm_ingredient
    recipes = []
    global retriever
    
    ingredient_types = state["ingredient_list"].ingredients_type
    print(ingredient_types)
    recipss = await retriever.ainvoke(ingredient_types)
    print(f"[DEBUG] 검색된 레시피 수: {len(recipss )}")
    print(f"[DEBUG] 레시피 미리보기: {[r.page_content[:50] for r in recipss ]}")

    return {"retrieved_recipes": format_docs(recipes)}


## 재료 기반 레시피 생성
def generate_recipe(state: OverrallState):
    print("현재노드: generate_recipe")
    ## query_analysis -> now -> node_llm -> confirm_ingrediant

    ## undeveloped(): query -> ingrediant
    ## query_reipes = template.generate_recipe_prompt.format(query=state["query"], ingrediant=state["ingrediant"])
    ingredient_types = state["ingredient_list"].ingredients_type
    query = template.generate_recipe_prompt.format(ingredients=ingredient_types)
    getnerate_recipe_model = loader.llm_loader()
    ingredients = state["ingredient_list"].ingredients_type
    query_getnerate_recipe = template.generate_recipe_prompt.format(ingredients=ingredients)

    try:
        result = getnerate_recipe_model.invoke(query_getnerate_recipe)
        print(type(result), result)
    except ValueError as e:
        print(f"생성 실패: {e}")
        result = IngredientList(is_empty=True, ingredients=[])

    return {"query": query}

 
## 레시피 정형화()
def recipe2strutured(state: OverrallState):
    # 쿼리 내용을 기준으로 쿼리 타입을 분석
    print(LLM_PROVIDER)
    print("현재노드: recipe2strutured")
    
    llm_model = loader.llm_loader()
    recipe2strutured_model = llm_model.with_structured_output(IngredientList, method="json_schema" )
    strutured_recipe = template.query_analysis_prompt.format(query=state["query"])
    
    result = recipe2strutured_model.invoke(query_analysis)

    print(type(result), result)

    return {"ingrdeient": result}



## <-------------------------------------------------- < 미사용 > ------------------------------------------>



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


    
