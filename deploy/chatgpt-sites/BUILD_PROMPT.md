@Sites

`LLM Wiki Research Hub`라는 개인용 반응형 웹사이트를 만들어줘.

목적: 사용자가 Agent Reach라는 내부 도구를 의식하지 않고 자연어로 리서치 요청을 입력하면, 서버 측 프록시를 통해 Agent Reach Gateway를 호출하고 결과를 보기 쉽게 표시한다.

필수 보안:
- `AGENT_REACH_GATEWAY_URL`과 `AGENT_REACH_GATEWAY_TOKEN`은 Sites Secrets에만 저장한다.
- 토큰을 브라우저 JavaScript, HTML, 로그, Network response에 절대 노출하지 않는다.
- 브라우저가 Gateway를 직접 호출하지 말고 Site server-side endpoint `/api/research`, `/api/doctor`를 통해 호출한다.
- 초기 공유 범위는 소유자 전용으로 유지한다.
- X/Instagram/Reddit 등 로그인·Cookie 필요 서비스는 자동 로그인하지 않는다.

화면:
- 제목: LLM Wiki Research Hub
- 큰 자연어 입력창
- 정보원: 자동 / 웹 / YouTube / GitHub / RSS
- 예시 버튼 4개
  1. 최근 AI 교육 트렌드 조사해
  2. YouTube에서 NotebookLM 활용 사례 찾아줘
  3. GitHub에서 강의에 쓸 만한 최신 오픈소스 찾아줘
  4. 이 URL 읽고 핵심 정리해
- 결과를 요약/출처/URL/수집시각/상태 카드로 표시
- Gateway 연결 상태와 doctor 상태를 READY / CONFIG_REQUIRED / AUTH_REQUIRED 배지로 표시
- `Wiki에 저장` 버튼은 현재 disabled 처리하고 `Wiki 쓰기 연결 준비 중`이라고 안내
- 모바일 360px에서도 편하게 사용할 수 있게 큰 글씨와 최소 44px 버튼 높이 적용

서버 측 동작:
- POST `/api/research` → `${AGENT_REACH_GATEWAY_URL}/research`
- Authorization: `Bearer ${AGENT_REACH_GATEWAY_TOKEN}`
- body: `{query, source, limit: 5}`
- GET `/api/health` → `${AGENT_REACH_GATEWAY_URL}/health`
- GET `/api/doctor` → `${AGENT_REACH_GATEWAY_URL}/doctor` with Bearer token
- Gateway의 raw JSON은 그대로 보여주지 말고 사용자 친화적으로 정규화한다.

디자인:
- 개인 지식관리 도구 느낌의 깔끔한 대시보드
- 설명은 짧고 개조식
- Agent Reach 명칭은 시스템 상태 화면 외에는 전면에 강조하지 않는다.
- 결과 출처는 클릭 가능하게 표시

완료 시 private preview를 만들고 모바일 QA까지 수행하되, 공개 Publish는 하지 말고 소유자 전용 상태로 둔다.
