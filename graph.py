import asyncio
from pathlib import Path

from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

import rag.loader as loader
import nodes.nodes as nodes
from states import OverrallState
from rag.config import COLLECTION_NAME, RETRIEVER_K, get_embedding, get_db_path
from rag.vectorstore import VectorStore

from nodes import analysis, ingredients, preview_recipes, recipes, name_search
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

## 실행 위치(cwd)와 무관하게 프로젝트 루트 기준으로 .env 로딩
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

embedding = get_embedding()


def init_vdb(embedding, collection_name, k):
    document = loader.fileloader_distributor()
    ## 레시피 문서 1개를 문서 1개로 취급 (청킹 없음)
    splitted_docs = document
    db_path = get_db_path()
    print(db_path)
    vdb = VectorStore(splitted_docs, embedding, collection_name, db_path)
    retriever = vdb.retriever(k=k)

    return vdb, retriever


## recipes 모듈의 전역 retriever에 주입
_, recipes.retriever = init_vdb(embedding, COLLECTION_NAME, RETRIEVER_K)


## 재료 기반 레시피 흐름 그래프
def build():
    graph_test = StateGraph(OverrallState)

    graph_test.add_node("undeveloped", nodes.undeveloped)
    graph_test.add_node("query_analysis", analysis.query_analysis)
    graph_test.add_node("respond_undevopled", nodes.respond_undevopled)
    graph_test.add_node("respond_unrealated", nodes.respond_unrealated)

    graph_test.add_node("retreiver_recipes", recipes.retreiver_recipes)
    graph_test.add_node("reset_recipe_options", ingredients.reset_recipe_options)
    graph_test.add_node("extract_ingredient", ingredients.extract_ingredient)
    graph_test.add_node("extract_ingredient_update", ingredients.extract_ingredient_update)
    graph_test.add_node("apply_ingredient_modification", ingredients.apply_ingredient_modification)
    graph_test.add_node("ingredient_analysis", analysis.ingredient_analysis)
    graph_test.add_node("respond_infeasible", nodes.respond_infeasible)
    graph_test.add_node("preview_recipe_options", preview_recipes.preview_recipe_options)
    graph_test.add_node("rag_adequacy_check", nodes.rag_adequacy_check)
    graph_test.add_node("present_recipe_options", preview_recipes.present_recipe_options)
    
    graph_test.add_node("select_recipe_option", recipes.select_recipe_option)
    graph_test.add_node("finalize_recipe", recipes.finalize_recipe)
    graph_test.add_node("fetch_rag_recipe", recipes.fetch_rag_recipe)

    ## 요리 이름 직접 검색 흐름
    graph_test.add_node("search_by_name", name_search.search_by_name)
    graph_test.add_node("filter_valid_candidates", name_search.filter_valid_candidates)
    graph_test.add_node("judge_name_match", name_search.judge_name_match)
    graph_test.add_node("resolve_rag_name_match", name_search.resolve_rag_name_match)
    graph_test.add_node("generate_recipe_by_name", name_search.generate_recipe_by_name)

    
    graph_test.add_edge(START, "query_analysis")
    graph_test.add_conditional_edges(
        "query_analysis",
        analysis.conditional_query_type,
        path_map={
            "reset_recipe_options": "reset_recipe_options",
            "retreiver_recipes": "retreiver_recipes",
            "select_recipe_option": "select_recipe_option",
            "search_by_name": "search_by_name",
            "respond_undevopled": "respond_undevopled",
            "respond_unrealated":"respond_unrealated",
        },
    )
    graph_test.add_edge("respond_undevopled", END)
    graph_test.add_edge("respond_unrealated", END)

    ## 재료 변경 처리: 옵션 초기화 -> (첫 턴 추출 / 변경 diff 추출) -> 목록 반영
    graph_test.add_conditional_edges(
        "reset_recipe_options",
        ingredients.conditional_has_previous,
        path_map={
            "extract_ingredient": "extract_ingredient",
            "extract_ingredient_update": "extract_ingredient_update",
        },
    )
    graph_test.add_edge("extract_ingredient", "apply_ingredient_modification")
    graph_test.add_edge("extract_ingredient_update", "apply_ingredient_modification")
    graph_test.add_edge("apply_ingredient_modification", "ingredient_analysis")
    graph_test.add_conditional_edges(
        "ingredient_analysis",
        analysis.conditional_ingredient_analysis,
        path_map={
            "retreiver_recipes": "retreiver_recipes",
            "respond_infeasible": "respond_infeasible",
        },
    )
    graph_test.add_edge("respond_infeasible", END)

    
    graph_test.add_edge("retreiver_recipes", "rag_adequacy_check")

    graph_test.add_edge("preview_recipe_options", "present_recipe_options")
    graph_test.add_edge("rag_adequacy_check", "preview_recipe_options")
    graph_test.add_edge("present_recipe_options", END)

    ## 요리 이름 직접 검색 흐름: RAG 검색 -> 이름 일치 판정 -> (적합/부적합) -> 프리뷰
    graph_test.add_edge("search_by_name", "filter_valid_candidates")
    graph_test.add_edge("filter_valid_candidates", "judge_name_match")
    graph_test.add_conditional_edges(
        "judge_name_match",
        name_search.conditional_name_match,
        path_map={
            "resolve_rag_name_match": "resolve_rag_name_match",
            "generate_recipe_by_name": "generate_recipe_by_name",
        },
    )
    graph_test.add_edge("resolve_rag_name_match", "present_recipe_options")
    graph_test.add_edge("generate_recipe_by_name", "present_recipe_options")
 
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
 
    checkpointer = MemorySaver(
        serde=JsonPlusSerializer(
            allowed_msgpack_modules=[
                ("schems", "RecipeList"),
                ("schems", "RecipeOption"),
                ("schems", "StructuredRecipe"),
                ("schems", "IngredientList"),
                ("schems", "Ingredient"),
                ("schems", "IngredientUpdate"),
                ("schems", "IngredientAnalysisResult"),
                ("schems", "QueryType"),
                ("schems", "NameMatchResult"),
            ]
        )
    )
    return graph_test.compile(checkpointer=checkpointer)