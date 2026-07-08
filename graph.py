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
from states import OverrollState

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
async def node_retreive(state:OverrollState):
    global retriever
    docs = await retriever.ainvoke(state["query"])
    print(f"[DEBUG] 검색된 문서 수: {len(docs)}")
    print(f"[DEBUG] 내용 미리보기: {[d.page_content[:50] for d in docs]}")
    return {"documents": format_docs(docs)}


async def node_prompt(state:OverrollState):
    
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
         "문서들의 레시피를 확인하고, 주어진 재료들로만으로 요리 가능한 레시피를 우선적으로 답해줘. "
         "레시피에서 추가재료가 필요하다면 추가재료가 적은순으로 레시피를 답해줘.  "
         "모든 문서들의 레시피가 불가능하다면 재료들을 근거로 새로운 레시피를 만들되 맛과 식감을 생각하고 답하세요."
         "사용자가 제시한 재료들로 요리가 불가능하다면 '현재 재료는 요리가 불가능합니다. 추가 재료가 필요합니다'라고 답하세요. "
         "문서들의 레시피 재료를 확인하고, 추가 재료가 적은 순으로 필요한 추가재료와 레시피를 답하세요. "
         "요리와 관련된 질문이 아니라면 '죄송합니다. 저는 요리관련 정보만 제공합니다'를 답하세요\n\n"),
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


async def node_llm(state:OverrollState):
    
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
def route_after_eval(state: OverrollState) -> str:
    # 미구현 state["score"] >= THRESHOLD 
    if state["type"] != None or state["loop"] < MAXLOOP:
        return "END"
    else:
        loop+=1
        return "node_retreive"

def build_generate(): 
    
    graph_main = StateGraph(OverrollState)
    
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

    