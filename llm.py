import os
import time
import contextvars
from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI

from dotenv import load_dotenv
load_dotenv()

## fallback "미지정"과 "폴백값이 None인 경우"를 구분하기 위한 센티널
NO_FALLBACK = object()

## 폴백 순서 (provider 미지정 시 이 순서대로 직접 시도)
FALLBACK_ORDER = ("claude", "google")

## 요청(턴) 하나 동안 발생한 LLM 호출 기록. main.py의 /query 핸들러가 요청 시작 시
## set([])으로 초기화하고, 끝날 때 get()으로 수집해서 대화 로그 DB에 남긴다.
## 호출부(invoke_structured/ainvoke_structured) 수십 곳을 개별로 안 건드리고
## 여기 한 곳만 손대면 되도록 contextvar로 구성 (호출 시그니처 변경 없음).
llm_call_log: contextvars.ContextVar[list | None] = contextvars.ContextVar(
    "llm_call_log", default=None
)


def _record_call(schema_name: str, provider: str | None, elapsed: float) -> None:
    log = llm_call_log.get()
    if log is not None:
        log.append({"schema": schema_name, "provider": provider, "elapsed_ms": round(elapsed * 1000)})


## LLM 인스턴스 반환
@lru_cache
def get_llm(provider: str | None = None, model: str | None = None):
    """provider/model 조합별로 1회만 생성하고 재사용하는 LLM 팩토리."""
    provider = (provider or os.getenv("LLM_PROVIDER", "google")).lower()

    if provider == "claude":
        from langchain_anthropic import ChatAnthropic
        resolved_model = model or os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8")
        return ChatAnthropic(
            model=resolved_model,
            max_tokens=2000,
            max_retries=0,
            timeout=15,
        )
    ## 자체학습모델("self" provider) 연동 예정 자리 -> self_model/ 폴더 참고
    resolved_model = model or os.getenv("GOOGLE_MODEL", "gemini-3.5-flash-lite")
    return ChatGoogleGenerativeAI(
        model=resolved_model,
        google_api_key=os.getenv("GOOGLE_API_KEY"),
    )


def _try_providers_sync(schema, prompt, providers, model):
    """동기: 주어진 provider 목록을 순서대로 시도. 성공하면 (결과, provider) 반환.
    전부 실패하면 None 반환."""
    for p in providers:
        llm = get_llm(p, model)
        structured_model = llm.with_structured_output(schema, method="json_schema")
        start = time.time()
        print(f"[LLM DEBUG] provider={p}, prompt={repr(prompt)[:500]}")  # 이 줄 추가
        try:
            result = structured_model.invoke(prompt)
            elapsed = time.time() - start
            print(f"[LLM] {schema.__name__} 호출 성공 (provider={p}), 소요시간={elapsed:.2f}s")
            return result, p
        except Exception as e:
            elapsed = time.time() - start
            print(f"[LLM] {schema.__name__} 호출 실패 (provider={p}), 소요시간={elapsed:.2f}s: {e}")
            continue
    return None, None


async def _try_providers_async(schema, prompt, providers, model):
    """비동기 버전. 동일한 순차 시도 + 로그 패턴."""
    for p in providers:
        llm = get_llm(p, model)
        structured_model = llm.with_structured_output(schema, method="json_schema")
        start = time.time()
        try:
            result = await structured_model.ainvoke(prompt)
            elapsed = time.time() - start
            print(f"[LLM] {schema.__name__} 호출 성공 (provider={p}), 소요시간={elapsed:.2f}s")
            return result, p
        except Exception as e:
            elapsed = time.time() - start
            print(f"[LLM] {schema.__name__} 호출 실패 (provider={p}), 소요시간={elapsed:.2f}s: {e}")
            continue
    return None, None


def invoke_structured(schema, prompt, *, fallback=NO_FALLBACK, provider=None, model=None):
    """
    구조화 출력 질의-응답 헬퍼 (동기).
    provider 미지정 시 Claude->Google 순으로 직접 순차 시도하며,
    각 provider의 성공/실패가 개별적으로 터미널에 로그로 남는다.
    fallback을 지정하면 전체 실패 시 그 값을 반환하고, 미지정 시 예외를 전파한다.
    """
    providers = [provider] if provider is not None else list(FALLBACK_ORDER)

    start = time.time()
    result, used_provider = _try_providers_sync(schema, prompt, providers, model)
    _record_call(schema.__name__, used_provider, time.time() - start)

    if result is not None:
        return result

    print(f"[LLM] {schema.__name__} 전체 provider 실패 (시도한 provider: {providers})")
    if fallback is NO_FALLBACK:
        raise RuntimeError(f"{schema.__name__}: 모든 provider({providers}) 호출 실패")
    return fallback


async def ainvoke_structured(schema, prompt, *, fallback=NO_FALLBACK, provider=None, model=None):
    """
    구조화 출력 질의-응답 헬퍼 (비동기).
    provider 미지정 시 Claude->Google 순으로 직접 순차 시도하며,
    각 provider의 성공/실패가 개별적으로 터미널에 로그로 남는다.
    fallback을 지정하면 전체 실패 시 그 값을 반환하고, 미지정 시 예외를 전파한다.
    """
    providers = [provider] if provider is not None else list(FALLBACK_ORDER)

    start = time.time()
    result, used_provider = await _try_providers_async(schema, prompt, providers, model)
    _record_call(schema.__name__, used_provider, time.time() - start)

    if result is not None:
        return result

    print(f"[LLM] {schema.__name__} 전체 provider 실패 (시도한 provider: {providers})")
    if fallback is NO_FALLBACK:
        raise RuntimeError(f"{schema.__name__}: 모든 provider({providers}) 호출 실패")
    return fallback