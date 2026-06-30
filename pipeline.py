# RAG's pipeline
import os
from glob import glob
from dotenv import load_dotenv

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough



import loader
import splitter
from vectorstore import VectorStore

load_dotenv()

DB_PATH = "./database/"
collection_name = "test_db"
retriever_k = 5

document = loader.fileloader_distributor()
splitted_docs = splitter.Token_splitter(document)

embedding = GoogleGenerativeAIEmbeddings(
        model = "models/gemini-embedding-001",
        google_api_key=os.environ["GOOGLE_API_KEY"]
)

vdb = VectorStore(splitted_docs, embedding, collection_name,  DB_PATH)

retriever = vdb.retriever(k=retriever_k)


# 수정 필요
prompt = ChatPromptTemplate.from_messages([
    ("system",
     "다음 문서를 근거로 사용자 질문에 답하세요. "
     "근거가 부족하면 '주어진 자료에서는 확인할 수 없습니다.'라고 답하세요.\n\n"
     "{context}"),
    ("human", "{question}"),
])


llm = loader.llm_loader()

def format_docs(ds):
    return "\n\n".join(d.page_content for d in ds)

rag = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)

print(rag.invoke("볶음밥 재료는 무엇인가요?"))

print("RAG 파이프라인 완료")

## -------- 수정 필요 -------- ##
from langsmith.evaluation import evaluate
from langsmith import Client

DATASET_NAME = os.environ["LANGSMITH_PROJECT"]


client = Client()

EVAL_QUESTIONS = [
    {
        "question": "볶음밥 종류를 말해주세요.?",
        "answer":   "김치볶음밥, 고추장볶음밥, 중국집 볶음밥, 한라산 볶음밥입니다.",
    },
    {
        "question": "볶음밥에 자주 들어가는 재료는 무엇인가요?",
        "answer":   "밥, 계란, 김, 참기름이 있습니다.",
    },
    {
        "question": "볶음밥은 불이 필요한가요?",
        "answer":   "볶음밥은 불이 필요합니다.",
    },
    {
                "question": "볶음밥은 필수 재료로 물이 필요한가요?",
        "answer":   "볶음밥은 물이 필수로 필요없습니다.",
    },
    {
        "question": "볶음밥 조리 시간은 보통 몇분 인가요?",
        "answer":   "볶음밥 조리 시가은 평균 15분 입니다.",
    },
]
print(f"검증 질문 수: {len(EVAL_QUESTIONS)}")

existing = [d for d in client.list_datasets(dataset_name=DATASET_NAME)]

inputs  = [{"question": ex["question"]} for ex in EVAL_QUESTIONS]
outputs = [{"answer":   ex["answer"]}   for ex in EVAL_QUESTIONS]

if existing:
    dataset = existing[0]
    print(f"기존 Dataset 사용: {dataset.id}")
else:
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

loaded = client.read_dataset(dataset_name=DATASET_NAME)

examples = list(client.list_examples(dataset_id=loaded.id))
print(f"총 Example 수: {len(examples)}")

for ex in examples[:3]:
    print("Q:", ex.inputs["question"])
    print("A:", ex.outputs["answer"] if ex.outputs else "(없음)")
    print()

def target(inputs):
    return {"answer": rag.invoke(inputs["question"])}

def contains_expected_keyword(run, example):
    pred = run.outputs.get("answer", "")
    expected = example.outputs.get("answer", "")

    # === 기대 답변에서 명사로 보이는 단어 한두 개를 키워드로 사용 ===
    keywords = [w for w in expected.split() if len(w) >= 2][:2]
    hit = all(k in pred for k in keywords)

    return {
        "key": "contains_expected_keyword",
        "score": 1 if hit else 0,
        "comment": f"필수 키워드 {keywords} 포함 여부",
    }

JUDGE_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "당신은 답변 품질을 평가하는 채점자입니다.\n"
     "아래 기대 답변(reference)과 모델 답변(prediction)을 비교하고,\n"
     "의미가 일치하면 1, 부분적으로만 일치하면 0.5, 무관하면 0을 점수로 매기세요.\n"
     "응답은 반드시 첫 줄에 0/0.5/1 중 하나의 숫자만, 둘째 줄부터 짧은 이유를 적으세요."),
    ("human",
     "질문: {question}\n\n"
     "기대 답변: {reference}\n\n"
     "모델 답변: {prediction}"),
])

judge_chain = JUDGE_PROMPT | llm | StrOutputParser()

def llm_judge(run, example):
    reply = judge_chain.invoke({
        "question": example.inputs["question"],
        "reference": example.outputs["answer"],
        "prediction": run.outputs["answer"],
    })
    # === 첫 줄의 숫자만 점수로 사용 ===
    first_line = reply.strip().splitlines()[0].strip()
    try:
        score = float(first_line)
    except ValueError:
        score = 0
    return {
        "key": "llm_judge_semantic_match",
        "score": score,
        "comment": reply,
    }

result = evaluate(
    target,
    data=DATASET_NAME,
    evaluators=[contains_expected_keyword, llm_judge],
    experiment_prefix="v1-baseline",
)

print(result)
# def main():
#     print("Hello from rag-project!")


# if __name__ == "__main__":
#     main()
