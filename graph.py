import os
from glob import glob
from dotenv import load_dotenv

import asyncio
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langgraph.graph import MessagesState,StateGraph,START, END
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate

import loader
import splitter
from vectorstore import VectorStore
from states import OverrollState

load_dotenv()


collection_name = "test_db1"
retriever_k = 5

embedding = GoogleGenerativeAIEmbeddings(
        model = "models/gemini-embedding-001",
        google_api_key=os.environ["GOOGLE_API_KEY"]
    )


def init_vdb(embedding,collection_name,k):
    document = loader.fileloader_distributor()
    splitted_docs = splitter.Token_splitter(document)
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
    
    prompt_template = ChatPromptTemplate.from_messages([
    ("system",
     "다음 문서를 근거로 사용자 질문에 답하세요. "
     "근거가 부족하면 '주어진 자료에서는 확인할 수 없습니다.'라고 답하세요.\n\n"
     "{context}"),
    ("human", "{question}"),
    ])

    rag_query = prompt_template.format(context=state["documents"], question=state["query"])

    return {"query": rag_query}


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

    return state




def build_struct(): 
    builder = StateGraph(OverrollState)

    builder.add_node("node_retreive", node_retreive)
    builder.add_node("node_prompt", node_prompt)
    builder.add_node("node_llm", node_llm)


    builder.add_edge(START, "node_retreive")
    builder.add_edge("node_retreive", "node_prompt")
    builder.add_edge("node_prompt", "node_llm")
    builder.add_edge("node_llm", END)

    return builder.compile()

async def run():
    graph = build_struct()

    ## 스트리밍으로 변경예정
    result = await graph.ainvoke({
    "query": "쌀밥,계란,대파,소금으로 만들 수 있는 요리 레시피 알려줘.",
    "messages": []
    })
    #print(result["query"])
    #print(result["answer"])
    #print(result["messages"])


if __name__ == "__main__":
    asyncio.run(run()) 