# LLM Wiki Research Hub — ChatGPT Sites Brief

Status: READY_FOR_SITES_BUILD
Updated: 2026-09-03

## 목적
사용자가 Agent Reach를 의식하지 않고 휴대폰·노트북·데스크탑에서 평소처럼 자연어로 조사 요청을 입력하는 단일 UI를 제공한다.

## 핵심 아키텍처

사용자 → ChatGPT Sites UI → Sites server-side proxy → Agent Reach Gateway → 외부 정보원 → 결과 → Wiki 저장/승격 흐름

중요: 브라우저 JavaScript에서 `GATEWAY_TOKEN`을 직접 보관하거나 Gateway에 직접 Bearer 요청을 보내지 않는다. 비밀값은 Sites의 server-side secret으로만 저장하고, 서버 측 프록시가 Gateway를 호출한다.

## 초기 공개 범위
- 기본 공유: 소유자 전용 또는 제한 공유
- 공개 인터넷 게시: 초기에는 금지
- 인증형 정보원(X/Instagram/Reddit 등): 초기 비활성
- 개인정보/민감정보 입력 안내 표시

## 화면 구성
1. 상단: `LLM Wiki Research Hub`
2. 큰 자연어 입력창
3. 빠른 예시 버튼
   - 최근 AI 교육 트렌드 조사해
   - YouTube에서 NotebookLM 활용 사례 찾아줘
   - GitHub에서 강의에 쓸 만한 최신 오픈소스 찾아줘
   - 이 URL 읽고 핵심 정리해
4. 정보원 선택: 자동 / 웹 / YouTube / GitHub / RSS
5. 결과 카드
   - 요약
   - 사용 정보원
   - 출처/URL
   - 수집 시각
   - 상태
6. `Wiki에 저장` 버튼은 Gateway/Wiki write endpoint가 준비되기 전에는 disabled로 표시하고 `준비 중` 안내
7. 시스템 상태 영역
   - Gateway 연결 상태
   - Agent Reach doctor 상태
   - READY / CONFIG_REQUIRED / AUTH_REQUIRED 표기

## Site server-side API 계약

### POST /api/research
Site의 서버 측 코드가 다음 Gateway 요청을 수행한다.

Target: `${AGENT_REACH_GATEWAY_URL}/research`
Headers:
- `Authorization: Bearer ${AGENT_REACH_GATEWAY_TOKEN}`
- `Content-Type: application/json`

Body:
```json
{
  "query": "사용자 질문",
  "source": "auto",
  "limit": 5
}
```

브라우저에는 Gateway URL과 Token을 반환하지 않는다.

### GET /api/health
Target: `${AGENT_REACH_GATEWAY_URL}/health`
- health endpoint는 인증 없이 연결성만 확인한다.

### GET /api/doctor
Target: `${AGENT_REACH_GATEWAY_URL}/doctor`
- server-side에서 Bearer Token을 붙인다.
- 원본 doctor JSON 중 사용자에게 필요한 상태만 정규화해 반환한다.

## 필요한 Sites Secrets
- `AGENT_REACH_GATEWAY_URL`
- `AGENT_REACH_GATEWAY_TOKEN`

절대 Site 코드/HTML/JS/로그/Google Drive Wiki에 하드코딩하지 않는다.

## UX 규칙
- Agent Reach라는 내부 도구명은 기본 UI에서 강조하지 않는다.
- 사용자는 자연어 질문만 입력하면 된다.
- 외부 조사가 필요하지 않은 질문은 향후 Wiki 우선 조회 라우터가 처리한다.
- 로그인/Cookie가 필요한 서비스 요청은 자동 로그인하지 않고 `추가 연결 필요`로 표시한다.
- 특정 URL에서 대량·반복·표형 데이터를 수집하는 요청은 `WEB_CRAWLER_V1` 경로로 안내/라우팅한다.

## 모바일
- 360px 폭에서 입력창, 결과 카드, 상태 배지 깨짐 금지
- 버튼 최소 높이 44px
- 결과 URL은 줄바꿈
- 긴 JSON을 기본 화면에 직접 노출하지 않는다.

## 완료 기준
- Site preview 생성
- 모바일 QA
- `/api/health` 연결 성공
- `/api/research` 샘플 요청 성공
- Gateway Token이 브라우저 source/network response에 노출되지 않음
- doctor 상태 표시 성공
- 이후 제한 공유 또는 개인용 Publish
