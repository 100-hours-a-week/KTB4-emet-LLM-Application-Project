 
import asyncio
import os
from dotenv import load_dotenv
 
from langsmith import Client
from langsmith.evaluation import aevaluate
 
from graph import build_generate
 
load_dotenv()
 
DATASET_NAME = "recipe-rag-eval"
 
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
 
 
def get_or_create_dataset(client: Client):
    existing = list(client.list_datasets(dataset_name=DATASET_NAME))
    if existing:
        print(f"기존 Dataset 사용: {existing[0].id}")
        return existing[0]
 
    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description="레시피 RAG 답변 품질 평가용",
    )
    client.create_examples(
        dataset_id=dataset.id,
        inputs=[{"question": ex["question"]} for ex in EVAL_QUESTIONS],
        outputs=[{"answer": ex["answer"]} for ex in EVAL_QUESTIONS],
    )
    print(f"새로운 Dataset 생성 및 Example {len(EVAL_QUESTIONS)}건 추가 완료: {dataset.id}")
    return dataset
 
 
async def target(inputs: dict) -> dict:
    graph = build_generate()
    result = await graph.ainvoke({
        "type":"JUDGE",
        "query": inputs["question"],
        "messages": [],
    })
    
    return {"answer": result["answer"]}
 
 
def correctness(outputs: dict, reference_outputs: dict) -> dict:
    predicted = outputs.get("answer", "")
    expected = reference_outputs.get("answer", "")
    return {
        "key": "correctness",
        "score": expected.strip() in predicted,
    }
 
 ## 평가자
def accuracy_summary(outputs: list, reference_outputs: list) -> dict:
    scores = [
        reference_outputs[i]["answer"].strip() in outputs[i]["answer"]
        for i in range(len(outputs))
    ]
    return {
        "key": "accuracy_rate",
        "score": sum(scores) / len(scores) if scores else 0.0,
    }
 
 
async def run_eval():
    client = Client()
    dataset = get_or_create_dataset(client)
 
    results = await aevaluate(
        target,
        data=dataset.name,
        evaluators=[correctness],
        summary_evaluators=[accuracy_summary],
        experiment_prefix="recipe-rag-batch",
        description="레시피 RAG 파이프라인 평가",
        metadata={"collection": os.environ.get("collection_name", "test_db1")},
    )
 
    print("평가 완료. LangSmith 대시보드에서 실험 결과를 확인하세요.")
    return results
 
 
if __name__ == "__main__":
    asyncio.run(run_eval())