import os
import asyncio

from dotenv import load_dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langgraph.graph import StateGraph, START, END

import ingestion.loader as loader
import nodes.nodes as nodes
from states import OverrallState
from ingestion.vectorstore import VectorStore

load_dotenv()

THRESHOLD = 0.01
MAXLOOP = 3
COLLECTION_NAME = "test_db3"
RETRIEVER_K = 5

embedding = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    google_api_key=os.environ["GOOGLE_API_KEY"],
)


def init_vdb(embedding, collection_name, k):
    document = loader.fileloader_distributor()
    ## splitted_docs = splitter.Token_splitter(document)
    ## pdf문서 1개를 문서 취급
    splitted_docs = document
    print(os.environ["DB_PATH"])
    vdb = VectorStore(splitted_docs, embedding, collection_name, os.environ["DB_PATH"])
    retriever = vdb.retriever(k=k)

    return vdb, retriever


## nodes 모듈의 전역 retriever에 주입
_, nodes.retriever = init_vdb(embedding, COLLECTION_NAME, RETRIEVER_K)


## conditional function
def route_after_eval(state: OverrallState) -> str:
    # 미구현 state["score"] >= THRESHOLD
    if state["type"] != None or state["loop"] < MAXLOOP:
        return "END"
    else:
        loop += 1
        return "node_retreive"


## 재료 기반 레시피 흐름 그래프
def build():
    graph_test = StateGraph(OverrallState)

    graph_test.add_node("query_analysis", nodes.query_analysis)
    graph_test.add_node("retreiver_recipes", nodes.retreiver_recipes)
    graph_test.add_node("generate_recipe", nodes.generate_recipe)
    graph_test.add_node("node_llm", nodes.node_llm)
    graph_test.add_node("extract_ingredient",nodes.extract_ingredient)
    graph_test.add_node("ingredient_analysis", nodes.ingredient_analysis)
    graph_test.add_node("undeveloped", nodes.undeveloped)
    

    graph_test.add_edge(START, "query_analysis")
    graph_test.add_conditional_edges("query_analysis", 
        nodes.conditional_query_type,
                path_map={
                    "extract_ingredient":"extract_ingredient",
                    "retreiver_recipes": "retreiver_recipes",
                    "generate_recipe": "generate_recipe",
                    "undeveloped": "undeveloped",
                    }
                )
    
    graph_test.add_edge("extract_ingredient","retreiver_recipes")
    graph_test.add_edge("extract_ingredient","ingredient_analysis")
    ## 미완성 추가 매핑 노드 필요
    graph_test.add_conditional_edges("ingredient_analysis", 
        nodes.conditional_ingredient_analysis,
                path_map={
                    "generate_recipe":"generate_recipe",
                    "undeveloped": "undeveloped",
                    }
                )
    
    graph_test.add_edge("retreiver_recipes",END)
   
    ## 임시 엣지
    graph_test.add_edge("generate_recipe",END)
    ## 리얼 엣지
    #graph_test.add_edge("generate_recipe","node_llm")
    #graph_test.add_edge("node_llm", END)

    

    return graph_test.compile()

async def run_graph():
    #graph = build_generate()
    graph = build()
    ## 스트리밍으로 변경예정

    result = await graph.ainvoke({
        "type": "RECIPE",
        "query": "",
        "messages": [],
        "loop": 0
        })
    #print(result["query"])
    #print(result["answer"])
    #print(result["messages"])


##if __name__ == "__main__":

  ##  asyncio.run(run_graph())
