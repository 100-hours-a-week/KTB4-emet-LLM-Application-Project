# SSE 스트리밍 전환 트러블슈팅 정리

**작성 일시: 2026-08-06 20:12**

> `POST /query`를 단발 JSON 응답에서 SSE(Server-Sent Events) 스트리밍으로 전환하면서
> (`feature/front/streaming` 브랜치) 발견하고 해결한 문제들 정리.

## 1. 배경

- LLM 폴백 체인(Claude → Google → vLLM) 특성상 응답까지 최악 30초 이상 걸릴 수 있어,
  그래프가 어느 노드를 실행 중인지 실시간으로 보여주기 위해 `/query`를 SSE로 전환
- 엔드포인트 경로/방식(`POST /query`)은 유지하고 응답만 스트리밍으로 변경

## 2. 설계 단계 — `stream_mode="updates"`의 시맨틱 지연

- `graph.astream(..., stream_mode="updates")`는 노드 실행이 **끝난 뒤** 그 결과를 내보냄 →
  진행 문구가 "지금 실행 중"이 아니라 "방금 끝난 노드"를 가리키는 한 박자 늦은 표시가 됨
- 대안으로 `astream_events()` + `on_chain_start`도 검토했으나, 이 프로젝트는 노드=LLM 호출 1회 구조가
  대부분이라 이벤트 세분화 이득 대비 구현 복잡도(이벤트 필터링, 동기 LLM 호출과의 호환성 검증)가 더 커서 기각
- **채택한 절충안**: `stream_mode="updates"`를 유지하되, `astream` 루프 진입 전에 진입 노드(`query_analysis`)
  문구를 먼저 한 번 보내서 "첫 노드 실행 중에는 아무 신호도 없는" 무신호 구간만 없앰 ([main.py](../main.py) `event_generator` 참고)

## 3. `NODE_DISPLAY_NAMES` 매핑 누락

- 그래프에 실제 존재하는 노드 `respond_undevopled`, `respond_unrealated`가 진행 문구 매핑에서 빠져 있었음
- 매핑에 없는 노드는 기본값("처리하는 중")으로 넘어가긴 하지만, 이 두 경로가 `query_analysis` 직후 흔한
  분기라 전용 문구를 채워 넣음

## 4. `final` 이벤트의 answer를 마지막 스트림 청크에서 꺼내면 안 되는 이유

- 최초 설계안은 `astream`의 마지막 청크(`chunk[node_name]`)에서 `answer`를 꺼내는 방식이었는데,
  그래프 구조가 바뀌어 병렬 노드가 생기면 어떤 청크가 "마지막"인지 신뢰할 수 없어짐
- **해결**: 그래프 실행이 끝난 뒤 `await app.state.rag.aget_state(config)`로 체크포인터에 저장된
  전체 상태를 다시 조회해서 `answer`를 꺼내도록 변경 → 노드 구조 변화에 안전

## 5. `rag_options` 상태 필드 미선언 (조용히 무시되던 버그)

- `nodes/nodes.py`의 `rag_adequacy_check`가 `{"rag_options": ...}`를 반환했지만
  `states.py`의 `OverrallState`에 `rag_options` 필드가 선언돼 있지 않았음
- LangGraph는 선언되지 않은 채널에 쓰기를 시도하면 예외 없이 `logger.warning`만 남기고 조용히 버림
  (`langgraph/pregel/_algo.py`: `"wrote to unknown channel {chan}, ignoring it"`)
- **증상**: `preview_recipe_options`가 읽는 `state.get("rag_options", [])`가 항상 빈 리스트로 평가되어,
  RAG로 이미 찾은 레시피 제목을 LLM 생성 시 제외하지 못함(중복 생성 가능)
- **해결**: `states.py`에 `rag_options: List[schems.RecipeOption]` 필드 추가

## 6. `ingredient_analysis` 이후 병렬 분기로 인한 중복 실행

- `nodes/analysis.py`의 `conditional_ingredient_analysis`가 `["preview_recipe_options", "retreiver_recipes"]`를
  반환해, "직접 요리 가능" 판정 시 두 경로가 **병렬로 동시 실행**되고 있었음
  - Path A(직행): `ingredient_analysis → preview_recipe_options → present_recipe_options → END`
  - Path B(RAG 경유): `ingredient_analysis → retreiver_recipes → build_rag_recipe_options → rag_adequacy_check → preview_recipe_options → present_recipe_options → END`
- 두 경로가 같은 노드(`preview_recipe_options`, `present_recipe_options`)로 수렴해서, LangGraph의
  Pregel 실행 모델상 **한 턴에 해당 노드들이 두 번씩 실행**됨
- git 히스토리로 추적한 결과, Path A는 `rag_adequacy_check`(동적 부족분 계산)가 도입되기 **이전**의
  "고정 비율(생성 1개 + RAG 4개)" 설계 잔재였음 (`preview_needed_count` 기본값 `1`이 그 화석)
- **문제**: `rag_adequacy_check`가 부족분을 계산하기도 전에 무조건 LLM을 한 번 더 호출(비용/지연 낭비),
  `present_recipe_options`가 두 번 실행되며 `answer`를 경쟁적으로 덮어씀
- **해결**: `conditional_ingredient_analysis`에서 Path A 반환을 제거하고 `"retreiver_recipes"` 단일 문자열만
  반환하도록 수정. Path B 혼자서도 "RAG 결과 없음" 케이스까지 이미 커버하고 있어 기능 손실 없음.
  `graph.py`의 죽은 `path_map` 엔트리(`"preview_recipe_options": "preview_recipe_options"`)도 함께 정리

## 7. 500 에러 — `QueryType` msgpack 역직렬화 차단

```
Blocked deserialization of schems.QueryType - not in allowed_msgpack_modules.
Add to allowed_msgpack_modules to allow: [('schems', 'QueryType')]
```

- `graph.py`의 체크포인터(`JsonPlusSerializer`)는 보안상 msgpack으로 저장된 pydantic 객체를 다시 읽어들일 때
  `allowed_msgpack_modules`에 등록된 클래스만 허용함. `states.py`의 `query_type: schems.QueryType` 필드가
  이 allowlist에서 빠져 있었음
- **왜 이번에 처음 터졌는가**: 저장(쓰기)은 항상 허용되고, 읽기(역직렬화) 시점에만 막힘. 4번 항목에서 추가한
  `aget_state()` 호출이 매 요청 끝에 체크포인트를 다시 읽어들이면서 이 경로를 처음으로(그것도 매번) 타게 됨
  (원래도 같은 thread_id로 두 번째 턴을 이어가면 언젠가 터질 잠재 버그였음)
- **부수 증상**: 프론트에서 진행 상황이 안 보인 것처럼 느껴진 이유 — 에러가 나면 `error` 이벤트를 받은
  프론트가 로딩 말풍선(그때까지 쌓인 progress 텍스트 포함)을 통째로 `remove()`해버려서, 실제로는 그래프가
  끝까지 실행되며 progress를 다 보냈어도 화면엔 흔적이 안 남음
- **해결**: `allowed_msgpack_modules`에 `("schems", "QueryType")` 추가

## 8. 프론트 SSE 파싱 에러

```
Unexpected token 'd', "data: {"ty"... is not valid JSON
```

- 원인은 코드 버그가 아니라 **브라우저 캐시**: `data: {...}` 형태의 SSE 텍스트를 예전 버전 JS(`res.json()`으로
  통째 파싱)가 그대로 파싱하려다 난 에러
- `FileResponse`가 `Cache-Control` 헤더를 지정하지 않아 브라우저가 재검증 없이 캐시를 그대로 쓴 게 원인
- **해결**: `/` 라우트의 `FileResponse`에 `headers={"Cache-Control": "no-cache"}` 추가 → 이후엔 하드 리프레시 없이
  일반 새로고침만으로 최신 정적 파일이 반영됨

## 9. 세션(스레드) 메모리 누적 대응

- `MemorySaver`(`InMemorySaver`) 공식 문서: "디버깅/테스트 용도로만 사용, 프로덕션은 `PostgresSaver` 권장"
- 앱 생애주기 동안 단일 인스턴스를 모든 사용자가 공유하며, 스레드별 체크포인트가 절대 지워지지 않고
  계속 쌓임(슈퍼스텝마다 새 체크포인트 생성) → 베타테스트처럼 멀티유저로 오래 띄워두면 메모리가 우상향
- 완전한 영속성(재시작 후에도 대화 보존)까지는 필요 없고 "세션 동안만 대화가 온전하면 된다"는 요구사항에 맞춰
  아래 3가지로 대응:
  1. **명시적 정리**: "새 대화" 클릭 시 프론트가 `DELETE /session/{thread_id}`를 호출해
     `checkpointer.adelete_thread()`로 이전 스레드 즉시 삭제
  2. **유휴 스레드 TTL 스윕**: 탭을 그냥 닫아버리는 경우를 위해, `/query` 호출마다 마지막 활동 시각을 기록해두고
     백그라운드 태스크가 30분마다 2시간 이상 유휴 상태인 스레드를 정리 (env로 조정 가능)
  3. **운영 안전판**: `deploy.yml`의 `docker run`에 `--restart unless-stopped` 추가 — 메모리 문제로
     컨테이너가 죽어도 자동 재기동되도록

## 관련 커밋

- `/query`를 SSE 스트리밍으로 전환하고 관련 버그 수정 (2~7번 항목)
- 유휴 세션 정리, 컨테이너 재시작 정책, 새 대화 시 세션 삭제 추가 (9번 항목)
