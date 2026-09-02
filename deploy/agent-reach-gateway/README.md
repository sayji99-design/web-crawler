# Agent Reach Wiki Gateway

개인용 클라우드 리서치 게이트웨이 배포 패키지입니다.

## 목표
- 휴대폰·노트북·데스크탑에서 동일한 자연어 리서치 진입점 제공
- Agent Reach를 공개 웹, YouTube, GitHub, RSS, Exa 검색의 백엔드 선택기/진단기로 사용
- 로그인·Cookie가 필요한 서비스는 자동 로그인하지 않고 추가 설정 필요 상태로 분리
- 향후 ChatGPT/Codex/Gemini 등 상위 에이전트가 이 API를 호출하고 결과를 LLM_WIKI에 저장

## 보안 원칙
- `GATEWAY_TOKEN` 없이는 `/doctor`, `/research` 사용 불가
- 비밀번호·토큰·Cookie를 코드/저장소에 저장하지 않음
- Twitter/X, Reddit, Instagram, Facebook, 小红书, 雪球은 기본적으로 인증 설정 필요 상태 반환
- 시스템 방화벽 해제·보안 설정 약화·임의 우회 금지

## 엔드포인트
- `GET /health` : 공개 상태 확인
- `GET /doctor` : Agent Reach doctor JSON (Bearer token 필요)
- `POST /research` : 자연어/URL 기반 리서치 라우팅 (Bearer token 필요)
- `POST /mcp` : ChatGPT Plugin용 Streamable HTTP MCP (OAuth/PKCE 인증)

## ChatGPT 자동 호출 연결
1. ChatGPT 설정에서 Developer mode를 켭니다.
2. Plugins에서 새 연결을 만들고 MCP URL에
   `https://agent-reach-wiki-gateway.onrender.com/mcp`를 입력합니다.
3. 연결 승인 화면에서 Render의 `GATEWAY_TOKEN`을 한 번 입력합니다.
4. 새 대화의 도구 메뉴에서 Agent Reach를 활성화합니다.

도구 설명은 최신 외부 정보, 다중 출처, URL, GitHub, YouTube, RSS 조사가
필요할 때 호출하고 단순 대화·창작·재작성에는 호출하지 않도록 설계되어 있습니다.

## 배포
루트의 `render.yaml`은 Render Free Web Service용 Blueprint입니다. 무료 서비스는 유휴 시 sleep하며 다음 요청에서 다시 기동될 수 있습니다. 로컬 파일은 영구 저장소로 취급하지 않습니다.

## 현재 지원
- 일반 웹 URL → Jina Reader
- 일반 검색 → Exa via mcporter
- YouTube URL/검색 → yt-dlp 또는 Exa fallback
- GitHub URL/검색 → GitHub CLI
- RSS → feedparser

## 추가 설정 필요
- GitHub의 높은 API 한도/비공개 저장소: GitHub 인증 토큰
- Reddit: 로그인/Cookie
- Twitter/X: auth_token + ct0
- Instagram/Facebook: 브라우저 세션 기반 도구 권장
- 小红书: 명시적 사용자 세션/Cookie 경로

## Wiki 연동 계약
상위 에이전트는 먼저 LLM_WIKI/MASTER DB를 확인하고, 외부 최신성·다중 출처 검증이 필요한 경우에만 이 Gateway를 호출합니다. 수집 결과는 출처 URL·수집 시각·라우팅 경로와 함께 `08_SOURCE`에 보존하고, 반복 활용 가치가 있는 지식만 `01_KNOWLEDGE`로 승격합니다.
