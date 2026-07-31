import os
import asyncio
from pathlib import Path

from dotenv import load_dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

import rag.loader as loader
import nodes.nodes as nodes
from states import OverrallState
from rag.vectorstore import VectorStore

from nodes import analysis, ingredients, preview_recipes, recipes


## 실행 위치(cwd)와 무관하게 프로젝트 루트 기준으로 .env 로딩
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

COLLECTION_NAME = "test_db3"
RETRIEVER_K = 5

embedding = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    google_api_key=os.environ["GOOGLE_API_KEY"],
)


def init_vdb(embedding, collection_name, k):
    document = loader.fileloader_distributor()
    ## 레시피 문서 1개를 문서 1개로 취급 (청킹 없음)
    splitted_docs = document
    ## DB_PATH가 상대경로여도 실행 위치와 무관하게 프로젝트 루트 기준으로 고정
    db_path = str((PROJECT_ROOT / os.getenv("DB_PATH", "data/vdb")).resolve())
    print(db_path)
    vdb = VectorStore(splitted_docs, embedding, collection_name, db_path)
    retriever = vdb.retriever(k=k)

    return vdb, retriever


## recipes 모듈의 전역 retriever에 주입
_, recipes.retriever = init_vdb(embedding, COLLECTION_NAME, RETRIEVER_K)


## 재료 기반 레시피 흐름 그래프
def build():
    graph_test = StateGraph(OverrallState)
 
    graph_test.add_node("query_analysis", analysis.query_analysis)
    graph_test.add_node("retreiver_recipes", recipes.retreiver_recipes)
    graph_test.add_node("extract_ingredient", ingredients.extract_ingredient)
    graph_test.add_node("ingredient_analysis", analysis.ingredient_analysis)
    graph_test.add_node("undeveloped", nodes.undeveloped)
    graph_test.add_node("preview_recipe_options", preview_recipes.preview_recipe_options)
    graph_test.add_node("build_rag_recipe_options", preview_recipes.build_rag_recipe_options)
    graph_test.add_node("present_recipe_options", preview_recipes.present_recipe_options)

    graph_test.add_node(
        "select_recipe_option", recipes.select_recipe_option
    )
    graph_test.add_node(
        "finalize_recipe", recipes.finalize_recipe
    )
    graph_test.add_node(
        "fetch_rag_recipe", recipes.fetch_rag_recipe
    )
 
    graph_test.add_edge(START, "query_analysis")
    graph_test.add_conditional_edges(
        "query_analysis",
        analysis.conditional_query_type,
        path_map={
            "extract_ingredient": "extract_ingredient",
            "retreiver_recipes": "retreiver_recipes",
            "select_recipe_option": "select_recipe_option",
            "undeveloped": "undeveloped",
        },
    )
 
    graph_test.add_edge("extract_ingredient", "ingredient_analysis")
    graph_test.add_conditional_edges(
        "ingredient_analysis",
        analysis.conditional_ingredient_analysis,
        path_map={
            "preview_recipe_options": "preview_recipe_options",
            "retreiver_recipes": "retreiver_recipes",
            "undeveloped": "undeveloped",
        },
    )
 
    graph_test.add_edge("retreiver_recipes", "build_rag_recipe_options")
 
    graph_test.add_edge("preview_recipe_options", "present_recipe_options")
    graph_test.add_edge("build_rag_recipe_options", "present_recipe_options")
    graph_test.add_edge("present_recipe_options", END)
 
    graph_test.add_conditional_edges(
        "select_recipe_option",
        recipes.conditional_select_recipe_option,
        path_map={
            "invalid": END,
            "finalize_recipe": "finalize_recipe",
            "fetch_rag_recipe": "fetch_rag_recipe",
        },
    )
    graph_test.add_edge("finalize_recipe", END)
    graph_test.add_edge("fetch_rag_recipe", END)
 
    graph_test.add_edge("undeveloped", END)
 
    checkpointer = MemorySaver()
    return graph_test.compile(checkpointer=checkpointer)