import os
from schems import StructuredRecipe, RecipeType, GeneratedRecipe, RecipeList, QueryType, Ingredient,IngredientList

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
async def extract_ingredient(state: OverrallState):
    print("현재노드: extract_ingredient")

    ## 이전 노드가 무엇인지 확인 필요!
    ## 질의분석 노드에서 왔다면 레시피 추출이 목적

    llm_model = loader.llm_loader()
    extract_ingredient_model = llm_model.with_structured_output(IngredientList, method="json_schema")
    query_extract_ingredient = template.extract_ingredient_prompt.format(query=state["query"])
 
    try:
        result = await extract_ingredient_model.ainvoke(query_extract_ingredient)
        #print(type(result), result)
    except Exception as e:
        print(f"검증 실패: {e}")
        # is_empty는 @computed_field로 ingredients 기반 자동 계산되므로 생성자에 넘기지 않음
        result = IngredientList(ingredients=[])
 
    return {"ingredient_list": result}


def ingredient_analysis(state: OverrallState):
    print("현재노드: ingredient_analysis")
    
    llm_model = loader.llm_loader()
    ingredient_analysis_model = llm_model.with_structured_output(RecipeType, method="json_schema" )
    query_ingredient_analysis = template.ingredient_analysis_prompt.format(ingredients=state["ingredient_list"].ingredients_name)
    try:
        result = ingredient_analysis_model.invoke(query_ingredient_analysis)
        generated_recipe = GeneratedRecipe(recipe_type=result.recipe_type, structured_recipe=None, needed_ingredients=None)
    except ValueError as e:
        print(f"검증 실패: {e}")
        generated_recipe = GeneratedRecipe()
    
    print(f"\n\ngenerated_recipe: {generated_recipe}\n\n")

    return {"generated_recipe": generated_recipe}



## 다음 노드 선택 -미완성-
def conditional_ingredient_analysis(state: OverrallState):

    print("현재 컨디셔널함수:conditional_query_type")
    recipe_type = state["generated_recipe"].recipe_type
    print(f"generated_recipe.recipe_type: {recipe_type}")

    ## 헷갈리지 말기 recipe_type == "generated_recipe" , 노드는 "generate_recipe"
    if recipe_type == "generated_recipe":
        return "generate_recipe"
    
    elif recipe_type == "add_ingredients_recipe":
        return "undeveloped"
    
    elif recipe_type == "rejecte_recipe":
        return "undeveloped"
    
    return "undeveloped"





## 재료 기반 레시피 검색
async def retreiver_recipes(state: OverrallState):
    print("\n현재노드: retreiver_recipes\n")
    ## query_analysis -> now -> confirm_ingredient
    recipes = []
    global retriever
    
    ingredient_names = state["ingredient_list"].ingredients_name
    print(ingredient_names)
    recipes = await retriever.ainvoke(ingredient_names)
    print(f"[DEBUG] 검색된 레시피 수: {len(recipes)}")
    print(f"[DEBUG] 레시피 미리보기: {[r.page_content[:50] for r in recipes]}")

    return {"retrieved_recipes": format_docs(recipes)}


## 추가 재료 레시피 이름과 추가 재료추출
def preview_recipe_options(state: OverrallState):
    print("\n현재노드: preview_recipe_options\n")
    ## query_analysis -> now -> node_llm -> confirm_ingrediant

    ## undeveloped(): query -> ingrediant
    ## query_reipes = template.generate_recipe_prompt.format(query=state["query"], ingrediant=state["ingrediant"])
    llm_model = loader.llm_loader()
    ingredient_analysis_model = llm_model.with_structured_output(RecipeType, method="json_schema" )
    query_preview_recipe = template.ingredient_analysis_prompt.format(ingredients=state["ingredient_list"].ingredients_name)

    try:
        result = ingredient_analysis_model.invoke(query_preview_recipe)
        generated_recipe = GeneratedRecipe(recipe_type=result.recipe_type, structured_recipe=None, needed_ingredients=None)
    except ValueError as e:
        print(f"검증 실패: {e}")
        generated_recipe = GeneratedRecipe()
        
    print(f"\n\ngenerated_recipe: {generated_recipe}\n\n")
    
    return {"generated_recipe": generated_recipe}


## 재료 기반 레시피 생성
def generate_recipe(state: OverrallState):
    print("\n현재노드: generate_recipe\n")
    ## query_analysis -> now -> node_llm -> confirm_ingrediant

    ## undeveloped(): query -> ingrediant
    ## query_reipes = template.generate_recipe_prompt.format(query=state["query"], ingrediant=state["ingrediant"])
    getnerate_recipe_model = loader.llm_loader()
    ingredients = state["ingredient_list"].ingredients_name
    query_getnerate_recipe = template.generate_recipe_prompt.format(ingredients=ingredients)

    try:
        result = getnerate_recipe_model.invoke(query_getnerate_recipe)
        print(type(result), result)
    except ValueError as e:
        print(f"생성 실패: {e}")
        result = IngredientList(is_empty=True, ingredients=[])

    return {"query": query_getnerate_recipe}




 
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


    
