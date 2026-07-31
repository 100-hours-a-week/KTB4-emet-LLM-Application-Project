from schems import IngredientList

import llm
from templates import ingredients_prompts
from states import OverrallState

from dotenv import load_dotenv
load_dotenv()


## 질의 또는 레시피문서에서 재료 추출
async def extract_ingredient(state: OverrallState):
    print("현재노드: extract_ingredient")

    ## 이전 노드가 무엇인지 확인 필요!
    ## 질의분석 노드에서 왔다면 레시피 추출이 목적

    query_extract_ingredient = ingredients_prompts.extract_prompt.format(query=state["query"])

    # is_empty는 @computed_field로 ingredients 기반 자동 계산되므로 생성자에 넘기지 않음
    result = await llm.ainvoke_structured(
        IngredientList, query_extract_ingredient, fallback=IngredientList(ingredients=[])
    )

    return {"ingredient_list": result}


def conditional_ingredient_action(state: OverrallState):



    return


def judge_ingredient_action (state: OverrallState):




    return


def remove_ingredient(state: OverrallState):





    return
