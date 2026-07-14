import os
from glob import glob
from dotenv import load_dotenv

import asyncio
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langgraph.graph import MessagesState,StateGraph,START, END
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate

from langsmith.evaluation import aevaluate
from langsmith import Client


import loader
import splitter
from vectorstore import VectorStore
from states import OverrallState

load_dotenv()

THRESHOLD = 0.01
MAXLOOP = 3
collection_name = "test_db3"
retriever_k = 5

embedding = GoogleGenerativeAIEmbeddings(
        model = "models/gemini-embedding-001",
        google_api_key=os.environ["GOOGLE_API_KEY"]
    )
DATASET_NAME = os.environ["LANGSMITH_PROJECT"]
EVAL_QUESTIONS = [
    {
        "question": "알고있는 볶음밥 레시피를 알려주세요.?",
        "answer":   "김치볶음밥, 고추장볶음밥, 중국집 볶음밥, 한라산 볶음밥입니다.",
    },
    {
        "question": "볶음밥에 반드시 들어가는 재료는 무엇이 있나요?",
        "answer":   "밥, 식용유 입니다.",
    },
    {
        "question": "볶음밥은 계란이 반드시 필요한가요?",
        "answer":   "볶음밥은 계란이 있으면 좋지만, 반드시 필요하지는 않습니다.",
    },
    {
        "question": "흰밥, 계란, 대파, 간장 ,소금으로는 무엇을 만들 수 있나요?",
        "answer":   "계란 볶음밥을 만들 수 있습니다.",
    },
    {
        "question": "볶음밥 조리 시간은 보통 몇분 인가요?",
        "answer":   "볶음밥 조리 시가은 평균 15분 입니다.",
    },
    {
        "question": "계란, 당근으로 무엇을 만들 수 있나요?",
        "answer":   "만들 수 있는 요리가 없습니다. 밥과 조미료를 추가하시면 계란 야채 볶음밥을 만들 수 있습니다.",
    },
    {
        "question": "밥,계란, 김으로 무엇을 만들 수 있나요?",
        "answer":   "계란볶음밥을 만들 수 있습니다.",
    },
]

def init_vdb(embedding,collection_name,k):
    document = loader.fileloader_distributor()
    ## splitted_docs = splitter.Token_splitter(document)
    ## pdf문서 1개를 문서 취급
    splitted_docs = document
    print(os.environ["DB_PATH"])
    vdb = VectorStore(splitted_docs, embedding, collection_name,  os.environ["DB_PATH"])
    retriever = vdb.retriever(k=k)

    return vdb, retriever

_, retriever = init_vdb(embedding, collection_name, retriever_k)

def format_docs(ds):
    return "\n\n".join(d.page_content for d in ds)

## ---- <node> ----##

## 삭제 예정 -> retreiver
async def node_retreive(state:OverrallState):
    global retriever
    docs = await retriever.ainvoke(state["query"])
    print(f"[DEBUG] 검색된 문서 수: {len(docs)}")
    print(f"[DEBUG] 내용 미리보기: {[d.page_content[:50] for d in docs]}")
    return {"documents": format_docs(docs)}




async def node_prompt(state:OverrallState):
    
    type = state["type"] 

    if type == "GENERATE":
        prompt_template = ChatPromptTemplate.from_messages([
        ("system",
         "다음 문서를 근거로 사용자 질문에 답하세요. "
         "근거가 부족하면 '주어진 자료에서는 확인할 수 없습니다.'라고 답하세요.\n\n"
         "{context}"),
        ("human", "{query}"),
        ])
        query = prompt_template.format(context=state["documents"], query=state["query"])
        print("This is GENERATE Prompt.")

    elif type == "RECIPE":
        prompt_template = ChatPromptTemplate.from_messages([
        ("system",
         "당신은 각종 요리 레시피를 알고 있는 요리전문가 입니다. "
         "질문이 요리레시피와 관련된 내용이 아니라면 '죄송합니다. 저는 요리 레시피 관련 정보만 제공합니다'를 답하세요. "
         "사용자가 건네준 재료들로 재료들 만으로 주어진 문서안의 레시피의 재료들과 비교하여 요리 가능한 레시피를 우선적으로 답해주세요. "
         "레시피에서 추가재료가 필요하다면 추가재료가 적은순으로 레시피를 답해줘.  "
         "모든 문서들의 레시피가 불가능하다면 재료들을 근거로 새로운 레시피를 만들되 맛과 식감을 생각하고 답하세요."
         "사용자가 제시한 재료들로 요리가 불가능하다면 '현재 재료는 요리가 불가능합니다. 추가 재료가 필요합니다'라고 답하세요. "
         "문서들의 레시피 재료를 확인하고, 추가 재료가 적은 순으로 필요한 추가재료와 레시피를 답하세요. "
         "\n\n"),
        ("human", "{query}"),
        ])
        query = prompt_template.format(context=state["documents"], query=state["query"])
        print("This is Recipe Prompt.")

    elif type == "JUDGE" :
        prompt_template = ChatPromptTemplate.from_messages([
        ("system",
         "당신은 답변 품질을 평가하는 채점자입니다.\n"
         "아래 기대 답변(reference)과 모델 답변(prediction)을 비교하고,\n"
         "의미가 일치하면 1, 부분적으로만 일치하면 0.5, 무관하면 0을 점수로 매기세요.\n"
         "응답은 반드시 첫 줄에 0/0.5/1 중 하나의 숫자만, 둘째 줄부터 짧은 이유를 적으세요."),
        ("human",
         "질문: {query}\n\n"
         "기대 답변: {reference}\n\n"
         "모델 답변: {prediction}"),
        ])
        query = prompt_template.format(query=state["query"], reference = state["reference"], prediction = state["prediction"])
        print("This is NONE Prompt.")

    else:
        print("This is JUDGE Prompt.")


    return {"query": query}

## 질의 분석 (조건함수)
def query_analysis(state:OverrallState):
    # node_prompt -> now -> retreiver_recipes
    #                    -> generate_recipes
    # 쿼리 내용을 기준으로 쿼리 타입을 분석
    ## 쿼리 분석해서 프롬프트로 노드로 전달
    ### 1) 레시피 추천
    ### 2) 레시피 반응

    return {"query_type":"type"}


## 재료 기반 레시피 검색
async def retreiver_recipes(state:OverrallState):
    ## query_analysis -> now -> confirm_ingrediant
    recipes = []
    global retriever
    ingrediant = state["ingrediant"]
    docs = await retriever.ainvoke(ingrediant)
    print(f"[DEBUG] 검색된 레시피 수: {len(docs)}")
    print(f"[DEBUG] 레시피 미리보기: {[d.page_content[:50] for d in docs]}")

    return {"recipes": format_docs(recipes)}

## 재료 기반 레시피 생성
## 미완성 노드
def generate_recipes(state:OverrallState):
    ## query_analysis -> now -> node_llm -> confirm_ingrediant
    recipes = []

    prompt_template = ChatPromptTemplate.from_messages([
        ("system",
         "주어진 재료로 요리가 가능한 레시피 제작이 가능한지 먼저 확인해주세요."
         "만약에 주어진 재료로 요리 레시피 제작이 불가능하다면 '재료가 부족합니다. 추가재료가 필요합니다.'를 출력합니다."
         "그리고 최대한 적게 새로운 재료들을 추가해서 레시피를 만들어주세요.  추가 재료는 식용이 가능한 정상적인 재료입니다."
         "사용자가 건네준 재료들로 요리가 가능하다면, 다음의 조건을 만족하는 요리 레시피를 만들어주세요. "
         "1. 만든 레시피는 사람이 정상적으로 먹을 수 있다. " 
         "2. 들어간 재료의 조합 또는 조리법에 문제가 없어야합니다. "
         "3. 괴식이 아니어야합니다."
         "4. 정상적이지 않은 재료가 있다면 레시피에서 제외해주세요."
         "5. 이 세상에 존재하지 않는 요리가 아닌, 기존에 존재하는 음식의 종류여야합니다."
         "6. 최대 30분이내 요리가 완성되는 요리여야합니다."
         ## 레시피 생성형태 -> RAG 문서와 동일하게 생성해야함!!!
         ## 현재는 str 형태 -> 최종형태는 json형태
         "\n\n"),
        ("human", "주어진 재료:{ingrediant}"),
        ])
    query_reipes = prompt_template.format(query=state["query"], ingrediant=state["ingrediant"])


    return {"query": format_docs(query_reipes)}


## 레시피 재료 검토
## 현재 버전: LLM에게 질문해서 재료가 부족한지 아닌지 판단
## 다음 버전: 정형화된 레시피에서 재료만 추출해서 직접비교
async def confirm_ingrediant(state:OverrallState):
    ## retreiver_recipes -> now ->
    ## generate_recipes -> node_llm ->
    ui = state["ingrediant"]
    recipes = state["recipes"]
    recipes_state = []
    llm_model = loader.llm_loader()
    prompt_template = ChatPromptTemplate.from_messages([
        ("system",
         "당신은 요리사 입니다."
         "현재 재료와 주어진 레시피의 재료를 비교하세요. "
         "다음 조건에 따라 레시피의 상태를 나누세요. "
         "1. 현재 재료는 레시피 재료를 불만족하면 레시피의 상태는 '재료 부족'입니다. "
         "2. 현재 재료는 레시피 재료를 만족하면서도 오히려 재료가 넘친다면 레시피의 상태는 '재료 충분(잉여있음)'"
         "3. 현재 재료와 레시피의 재료가 동일하다면 레시피의 상태는 '재료 정확히 일치'입니다. "
         "4. 그외의 레시피의 상태는 '문제 발생'입니다. "
         "조건을 충족한 레시피 상태에 따라 아래의 형태로 반환해주세요."
         "1번 조건의 레시피는 '[부족한재료1,부족한재료2,...,부족한재료n]'와 같은 형태로 반환해줘"
         "2번,3번,4번 조건은 상태를 반환해줘"
         "\n\n"),
        ("human", "현재 재료:{ingrediant}, 레시피: {recipe}"),
        ])
    

    for recipe in recipes:
        query_ingrediant = prompt_template.format(recipe=recipe, ingrediant=state["ingrediant"])
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


async def node_llm(state:OverrallState):
    
    llm_model = loader.llm_loader()
    human_msg = HumanMessage(content=state["query"])
    full_messages = state["messages"] + [human_msg] 

    answer = ""
    async for chunk in llm_model.astream(full_messages):
        print(chunk.content, end="",flush=True)
        answer += chunk.content

    ai_msg = AIMessage(content=answer)

    return {"messages": [human_msg, ai_msg], "answer": answer}




async def node_evaluate(state:StateGraph):
    client = Client()
    print(f"검증 질문 수: {len(EVAL_QUESTIONS)}")

    existing = [d for d in client.list_datasets(dataset_name=DATASET_NAME)]

    inputs  = [{"question": ex["question"]} for ex in EVAL_QUESTIONS]
    outputs = [{"answer":   ex["answer"]}   for ex in EVAL_QUESTIONS]

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

# conditional function 
def route_after_eval(state: OverrallState) -> str:
    # 미구현 state["score"] >= THRESHOLD 
    if state["type"] != None or state["loop"] < MAXLOOP:
        return "END"
    else:
        loop+=1
        return "node_retreive"



def build():
    graph_test = StateGraph(OverrallState)

    graph_test.add_node(query_analysis)
    graph_test.add_node(retreiver_recipes)
    graph_test.add_node(generate_recipes)
    
def build_generate(): 
    
    graph_main = StateGraph(OverrallState)
    
    graph_main.add_node("node_retreive", node_retreive)
    graph_main.add_node("node_prompt", node_prompt)
    graph_main.add_node("node_llm", node_llm)
    graph_main.add_node("node_evaluate", node_evaluate)

    graph_main.add_edge(START, "node_retreive")
    graph_main.add_edge("node_retreive", "node_prompt")
    graph_main.add_edge("node_prompt", "node_llm")
    graph_main.add_edge("node_llm", END)
    graph_main.add_conditional_edges("node_evaluate", route_after_eval,
        {"END": END, "node_retreive": "node_retreive"}
        )
    return graph_main.compile()

async def run_graph():
    graph = build_generate()

    ## 스트리밍으로 변경예정
    
    result = await graph.ainvoke({
        "type":"RECIPE",
        "query": "",
        "messages": [],
        "loop" : 0
        })
    #print(result["query"])
    #print(result["answer"])
    #print(result["messages"])


##if __name__ == "__main__":

  ##  asyncio.run(run_graph()) 

    