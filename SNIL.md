# Something New I Learn

## Library & Module

- from contextlib import asynccontextmanager
    - 비동기 컨텍스트 매니저 생성 데코레이터 모듈
    -  주로 FastAPI의 lifeapn 이벤트에 사용
- from glob import glob
    - 와일드 카드 패턴과 일치하는 파일 경로의 리스트 리턴
    * glob(): 와일드 카드 패턴과 일치하는 파일 리스트 리턴하는 함수
- from dotenv import load_dotenv
    - .env 파일을 읽어서 환경변수로 등록
    - API 키 숨길때 사용

- from langchain_google_genai import GoogleGenerativeAIEmbeddings
    * GoogleGenerativeAIEmbeddings(
        model = model_name,  ## model_name 설정
        google_api_key = your_api_key ## 발급받은 키 설정
    ) : Google의 텍스트 임베딩 모델 초기화 및 생성

- from langchain_chroma import Chroma
    * Chroma.from_documents(docs, embedding): 새로운 VDB 생성
        - docs: 문서
        - embedding: 문서 임베딩 모델
    * vectorstore.add_documents(docs): 기존 VDB에 문서 추가
    * vectorstore.as_retriever(search_kwargs={"k": retriever_k}): 체인에 사용할 Retriever 객체로 변환
        - search_kwargs={"k": retriever_k}: retriever_k만큼의 유사 문서 검색

- from langsmith.evaluation import aevaluate
    * aevaluate(
        target = 평가 대상이 되는 async 함수,
        data=질문 답변 데이터셋,
        evaluators=평가자 함수 목록,
        summary_evaluators=전체 평가자,
        experiment_prefix=실험 이름의 접두사,
        description=간단 설명,
        max_concurrency=병령처리쓰레드생성수,
        metadata=부가정보태그,
    )

- HumanMessage
    - 사용자 -> 모델로 전송하는 메시지
    * HumanMessage(self,content: str | list[str | dict[Any, Any]] | None = None,
content_blocks: list[types.ContentBlock] | None = None, **kwargs: Any = {})
- AIMessage
    - 모델 -> 사용자로 전송하는 메시지



## Function
- os.getenv(field_name, default): 환경변수의 값을 리턴하는 함수
    - field_name :환경변수 이름
    - default: 해당 환경변수가 없을 경우 기본적으로 사용할 값
