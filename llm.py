import os

from langchain_google_genai import ChatGoogleGenerativeAI

from dotenv import load_dotenv
load_dotenv()


def llm_loader():
    provider = os.getenv("LLM_PROVIDER", "google").lower()
    #print(f"LLM Provider: {provider}")
    if provider == "claude":
        from langchain_anthropic import ChatAnthropic
        # API 키는 ANTHROPIC_API_KEY 환경변수에서 자동으로 읽음
        return ChatAnthropic(
            model=os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8"),
            max_tokens=16000,
        )
    ## 자체학습모델("self" provider) 연동 예정 자리 -> self_model/ 폴더 참고
    return ChatGoogleGenerativeAI(
        model=os.getenv("GOOGLE_MODEL", "gemini-2.5-flash"),
        google_api_key=os.getenv("GOOGLE_API_KEY"),
    )
