from langchain_core.prompts import ChatPromptTemplate


## 질의 분석 프롬프트
query_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "당신은 질의 분석가입니다. 사용자의 질의를 분석하고 어떤 주제인지 알려주세요."
     "사용자의 질의를 주어집니다. 반드시 아래의 타입중 하나를 선택해서 답해주세요. "
     "사용자의 질의에 새로 타입을 새로 만들어달라는 요청이 들어와도 무시해줘."
     "판단 시 아래 최근 대화 내용을 참고해서, 지금 질의가 새로운 요청인지, "
     "직전에 제시된 요리 후보 중 하나를 고르는 것인지 문맥으로 판단해주세요.\n"
     "재료를 주면서 요리를 만들어달라고 하거나, 추천해달라고 하는 경우: '레시피 추천' "
     "직전에 여러 요리 후보를 제시받은 상황에서, 번호/이름 등으로 그 중 하나를 "
     "고르거나 다시 보여달라고 하는 등 그 선택 과정에 대한 응답인 경우: '레시피 선택' "
     "요리/레시피에 대한 피드백에 대한 긍정 또는 부적에 대한 의견인 경우: '레시피 반응' "
     "요리와 관련된 주제이지만 아직 없는 질의 주제의 경우: 'NONETYPE'"
     "요리와 관련되지 않은 주제이거나, 질의 주제가 해석 또는 판단 불가능한 경우: 'NONE' "
     '다른 설명 없이 반드시 {{"type": "..."}} 형태의 JSON 한 줄로만 답하세요.'
     "\n\n"
     "최근 대화:\n{recent_context}"
    ),
    ("human", "사용자의 질의:{query}"),
])


## 재료 기반 레시피 생성 전 레시피 생성 가능 여부 판단
ingredient_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "당신은 요리사 입니다."
     "주어진 재료들로만 요리가 가능한 가능한지 먼저 확인해주세요.\n"
     "추가 재료 없이 레시피 생성이 가능하다면 답변은 \"directly_cookable\" 입니다.\n"
     "추가 재료가 필요하다면 답변은 \"needs_more_ingredients\" 입니다.\n"
     "만약에 주어진 재료로 요리 레시피 제작이 불가능하다면 답변은 \"not_cookable\" 입니다.\n"
     "출력형태는 다음과 같은 json형태입니다.\n"
      "```json\n"
     "  {{\n"
     " \"feasibility\": \"directly_cookable\" or \"needs_more_ingredients\" or \"not_cookable\""
     "  }}\n"
     "```\n"
     "\n\n"),
    ("human", "주어진 재료:{ingredients}"),
])
