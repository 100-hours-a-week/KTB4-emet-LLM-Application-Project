import os
from schems import StructuredRecipe, IngredientAnalysisResult, RecipeList, QueryType, Ingredient,IngredientList,StructuredRecipe,RecipeOption,RecipeOptionList, IngredientFeasibility
import json
from langchain_core.messages import HumanMessage, AIMessage
from langsmith import Client
from pydantic import ValidationError

import ingestion.loader as loader
import ingestion.template as template
import eval.eval_data as eval_data
from states import OverrallState
from . import recipe_options_build

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

## 최근 대화 몇 턴을 프롬프트에 넣을 텍스트로 정리
def _format_recent_context(messages, max_turns=3):
    if not messages:
        return "(이전 대화 없음)"
 
    recent = messages[-(max_turns * 2):]
    lines = []
    for m in recent:
        role = "사용자" if m.type == "human" else "AI"
        lines.append(f"{role}: {m.content}")
 
    return "\n".join(lines) if lines else "(이전 대화 없음)"

## 질의 분석
def query_analysis(state: OverrallState):
    print("현재노드: query_analysis")
    llm_model = loader.llm_loader()
    query_analysis_model = llm_model.with_structured_output(QueryType, method="json_schema")
 
    recent_context = _format_recent_context(state.get("messages", []))
    query_analysis_query = template.query_analysis_prompt.format(
        query=state["query"],
        recent_context=recent_context,
    )
 
    result = query_analysis_model.invoke(query_analysis_query)
 
    print(type(result), result)
 
    return {"query_type": result.type}


## 다음 노드 선택
def conditional_query_type(state: OverrallState):
    print("현재 컨디셔널함수:conditional_query_type")
    print(f"query_type: {state["query_type"]}")
    print(state["query_type"])
    if state["query_type"] == "레시피 추천":
        return "extract_ingredient"
    elif state["query_type"] == "레시피 선택":
            return "select_recipe_option" 
    elif state["query_type"] == "레시피 반응":
        return "undeveloped"
    elif state["query_type"] == "NONETYPE":
        return "undeveloped"
    elif state["query_type"] == "NONE":
        return "undeveloped"
    
    return "undeveloped"


## 질의 또는 레시피문서에서 재료 추출
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

## 추출한 재료 검토
def ingredient_analysis(state: OverrallState):
    print("현재노드: ingredient_analysis")

    llm_model = loader.llm_loader()
    ingredient_analysis_model = llm_model.with_structured_output(
        IngredientFeasibility, method="json_schema"
    )
    query_ingredient_analysis = template.ingredient_analysis_prompt.format(
        ingredients=state["ingredient_list"].ingredients_name
    )

    try:
        result = ingredient_analysis_model.invoke(query_ingredient_analysis)
        ingredient_analysis_result = IngredientAnalysisResult(
            feasibility=result.feasibility,
            structured_recipe=None,
            needed_ingredients=None,
        )
    except ValidationError as e:
        print(f"검증 실패: {e}")
        ## 판정 실패 시 안전하게 "생성 불가"로 처리 (undeveloped로 라우팅됨)
        ingredient_analysis_result = IngredientAnalysisResult(
            feasibility="not_cookable",
            structured_recipe=None,
            needed_ingredients=None,
        )

    print(f"\n\ningredient_analysis_result: {ingredient_analysis_result}\n\n")

    return {"ingredient_analysis_result": ingredient_analysis_result}


## 다음 노드 선택
def conditional_ingredient_analysis(state: OverrallState):
 
    print("현재 컨디셔널함수: conditional_ingredient_analysis")
    feasibility = state["ingredient_analysis_result"].feasibility
    print(f"ingredient_analysis_result.feasibility: {feasibility}")
 
    if feasibility in ("directly_cookable", "needs_more_ingredients"):
        return ["preview_recipe_options", "retreiver_recipes"]
 
    elif feasibility == "not_cookable":
        print("배달이나 시켜드십쇼. ㅋㅋㅋㅋㅋㅋㅋㅋ")
        return "undeveloped"
 
    return "undeveloped"



## 재료 기반 레시피 검색
async def retreiver_recipes(state: OverrallState):
    print("\n현재노드: retreiver_recipes\n")
    global retriever
 
    ingredient_names = state["ingredient_list"].ingredients_name
    print(ingredient_names)
 
    ## 재료가 하나도 추출되지 않았으면 검색 불가 (빈 쿼리는 임베딩 API가 400으로 거부)
    if not ingredient_names:
        print("[DEBUG] 추출된 재료 없음 -> 레시피 검색 건너뜀")
        return {"retrieved_recipes": RecipeList(recipes=[])}
 
    search_query = ", ".join(ingredient_names)
    docs = await retriever.ainvoke(search_query)
    print("DEBUG metadata:", docs[0].metadata)
    print(f"[DEBUG] 검색된 레시피 수: {len(docs)}")
    print(f"[DEBUG] 레시피 미리보기: {[d.page_content[:50] for d in docs]}")
 
    ## page_content는 StructuredRecipe 필드 그대로의 JSON 문자열이므로 파싱해서
    ## StructuredRecipe 인스턴스로 변환한다.
    recipes = []
    for d in docs:
        try:
            data = json.loads(d.page_content)
            recipes.append(StructuredRecipe(**data))
        except (json.JSONDecodeError, ValidationError) as e:
            ## 파싱 실패한 문서는 건너뛰고 계속 진행 (전체 검색을 중단시키지 않음)
            print(f"[WARN] 레시피 파싱 실패, 스킵: {e}")
            continue
 
    return {"retrieved_recipes": RecipeList(recipes=recipes)}
 


## 추가 재료 레시피 이름과 추가 재료추출
def preview_recipe_options(state: OverrallState):
    print("\n현재노드: preview_recipe_options\n")

    llm_model = loader.llm_loader()
    preview_recipe_options_model = llm_model.with_structured_output(RecipeOptionList, method="json_schema" )
    query_preview_recipe = template.preview_recipe_options_prompt.format(
        option_count= 1,
        ingredients=state["ingredient_list"].ingredients_name
        )

    try:
        result = preview_recipe_options_model.invoke(query_preview_recipe)
        print(f"type:{type(result)}")
        
    except ValueError as e:
        print(f"검증 실패: {e}")
        result = RecipeOptionList(options=[])
        
    print(f"\n\nrecipe_options: {result}\n\n")
    
    return {"recipe_options": result.options}


## RAG 레시피 문서를 레시피옵션으로 추출 
def build_rag_recipe_options(state: OverrallState):
    print("\n현재노드: build_rag_recipe_options\n")
 
    recipe_options = recipe_options_build.build_rag_recipe_options(
        state["retrieved_recipes"],
        state["ingredient_list"].ingredients_name,
    )
    return {"recipe_options": recipe_options}

## 재료 기반 레시피 생성
### 임시 미사용 노드
### -> 프리뷰레시피 옵션 -> 파이널 라이즈 
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


## RAG 프리뷰레시피와 레시피 옵션의 프리퓨레시피 합쳐서 출력하는 노드
def present_recipe_options (state:OverrallState):
    print("\n현재노드: present_recipe_options\n")
 
    options = state["recipe_options"]
 
    if not options:
        return {
            "answer": "죄송해요, 지금 가진 재료로 제안할 수 있는 요리를 찾지 못했어요."
        }
 
    ## 추가재료가 없는(=바로 만들 수 있는) 옵션을 우선 배치(추가재료가 적은순)
    sorted_options = sorted(options, key=lambda o: len(o.needed_ingredients))
 
    lines = ["다음 중 어떤 요리로 하시겠어요?\n"]
    for idx, option in enumerate(sorted_options, start=1):
        if option.needed_ingredients:
            needed_str = ", ".join(option.needed_ingredients)
            lines.append(f"{idx}. {option.title} (추가 재료 필요: {needed_str})")
        else:
            lines.append(f"{idx}. {option.title} (추가 재료 없음)")
 
    answer = "\n".join(lines)
    print(f"\n\npresent_recipe_options answer:\n{answer}\n\n")
 
    return {
        "answer": answer,
        "messages": [HumanMessage(content=state["query"]), AIMessage(content=answer)],
    }
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


    
