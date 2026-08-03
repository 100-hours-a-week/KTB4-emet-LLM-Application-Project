import os
## 호출결과 캐싱해주는 데코레이터
from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI

from dotenv import load_dotenv
load_dotenv()

## fallback "미지정"과 "폴백값이 None인 경우"를 구분하기 위한 센티널
NO_FALLBACK = object()

## LLM 인스턴스 반환
@lru_cache
def get_llm(provider: str | None = None, model: str | None = None):
    """provider/model 조합별로 1회만 생성하고 재사용하는 LLM 팩토리."""
    provider = (provider or os.getenv("LLM_PROVIDER", "google")).lower()

    if provider == "claude":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model or os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8"),
            max_tokens=16000,
        )
    elif provider == "vllm":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model or os.getenv("LLM_MODEL_NAME"),
            base_url=os.getenv("LLM_BASE_URL"),
            api_key=os.getenv("LLM_API_KEY"),
            max_tokens=16000,
        )

    ## 자체학습모델("self" provider) 연동 예정 자리 -> self_model/ 폴더 참고
    return ChatGoogleGenerativeAI(
        model=model or os.getenv("GOOGLE_MODEL", "gemini-flash-latest"),
        google_api_key=os.getenv("GOOGLE_API_KEY"),
    )

## 자동 전환 폴백 체인
@lru_cache
def get_llm_with_fallback(model: str | None = None):
    """
    Claude -> Google -> vLLM 순으로 자동 폴백되는 LLM 반환.
    (모든 예외에서 폴백)
    """
    claude = get_llm("claude", model)
    google = get_llm("google", model)
    vllm = get_llm("vllm", model)
    return claude.with_fallbacks([google, vllm])


def invoke_structured(schema, prompt, *, fallback=NO_FALLBACK, provider=None, model=None):
    """
    구조화 출력 질의-응답 헬퍼 (동기).
    provider 미지정 시 Claude->Google->vLLM 자동 폴백 체인을 사용한다.
    fallback을 지정하면 (체인 전체가) 실패 시 그 값을 반환하고, 미지정 시 예외를 그대로 전파한다.
    """
    llm = get_llm_with_fallback(model) if provider is None else get_llm(provider, model)
    # 각 모델마다 json 정형화 포멧 응답받도록 설정 
    structured_model = llm.with_structured_output(schema, method="json_schema")

    try:
        return structured_model.invoke(prompt)
    except Exception as e:
        if fallback is NO_FALLBACK:
            raise
        print(f"[invoke_structured] {schema.__name__} 호출 실패: {e}")
        return fallback


async def ainvoke_structured(schema, prompt, *, fallback=NO_FALLBACK, provider=None, model=None):
    """
    구조화 출력 질의-응답 헬퍼 (비동기).
    provider 미지정 시 Claude->Google->vLLM 자동 폴백 체인을 사용한다.
    fallback을 지정하면 (체인 전체가) 실패 시 그 값을 반환하고, 미지정 시 예외를 그대로 전파한다.
    """
    llm = get_llm_with_fallback(model) if provider is None else get_llm(provider, model)
    structured_model = llm.with_structured_output(schema, method="json_schema")
    try:
        return await structured_model.ainvoke(prompt)
    except Exception as e:
        if fallback is NO_FALLBACK:
            raise
        print(f"[ainvoke_structured] {schema.__name__} 호출 실패: {e}")
        return fallback