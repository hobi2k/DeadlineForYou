# MCP 구조와 구현 방법

기준일: 2026-03-11

이 문서는 `MCP(Model Context Protocol)`가 무엇인지, 어떤 구조로 동작하는지, 실제로 어떻게 구현하는지 정리한 문서다.

목표는 세 가지다.

1. MCP의 구조를 이해한다.
2. MCP 서버와 클라이언트가 각각 무엇을 하는지 이해한다.
3. 실제 구현 순서를 잡는다.

이 문서는 현재 공개된 공식 MCP 문서와 사양을 기준으로 작성했다.

## 1. MCP란 무엇인가

MCP는 AI 애플리케이션이 외부 시스템과 표준 방식으로 연결되도록 만드는 공개 프로토콜이다.

쉽게 말하면:

- LLM 앱이
- 파일, 데이터베이스, API, 툴, 워크플로와 연결될 때
- 매번 제각각 붙이지 않고
- 같은 방식으로 연결하게 해주는 표준

공식 문서는 MCP를 AI 애플리케이션용 `USB-C` 같은 표준 포트에 비유한다.

즉:

- AI 앱이 `host`
- 연결 로직이 `client`
- 데이터/툴 제공자가 `server`

이 구조를 공유한다.

## 2. MCP가 필요한 이유

MCP가 없으면 보통 이런 문제가 생긴다.

- 앱마다 플러그인 구조가 다름
- 도구 연결 방식이 다름
- 파일/DB/API 연결을 매번 새로 구현해야 함
- 한 번 만든 연동을 다른 AI 앱에 재사용하기 어려움

MCP가 있으면 다음이 가능해진다.

- 한 번 만든 서버를 여러 AI 클라이언트가 재사용
- 툴, 리소스, 프롬프트를 표준 방식으로 노출
- AI 앱이 외부 문맥과 작업 능력을 일관되게 확보

## 3. 핵심 참여자 구조

MCP는 client-server 구조지만, 실제로는 `host`가 한 단계 더 있다.

### 3.1 Host

Host는 실제 AI 애플리케이션이다.

예:

- Claude Desktop
- Claude Code
- ChatGPT 계열 클라이언트
- VS Code 기반 AI 도구
- Cursor 같은 편집기

Host는 사용자가 직접 만나는 앱이다.

### 3.2 Client

Client는 host 내부에서 MCP 서버와 연결을 담당하는 커넥터다.

중요한 점:

- host 하나가 여러 MCP 서버에 연결할 수 있다
- 서버마다 별도 client 연결이 유지된다

즉, host 안에는 서버별 MCP client가 여러 개 존재할 수 있다.

### 3.3 Server

Server는 실제 컨텍스트와 기능을 제공하는 쪽이다.

예:

- 파일 시스템 서버
- Git 서버
- DB 서버
- Notion 서버
- 계산기/검색/API 실행 서버

서버는 보통 다음 중 하나 이상을 제공한다.

- Resources
- Tools
- Prompts

## 4. MCP의 큰 구조

```text
사용자
  |
  v
AI Host Application
  |
  +-- MCP Client A ---- MCP Server A
  |
  +-- MCP Client B ---- MCP Server B
  |
  +-- MCP Client C ---- MCP Server C
```

의미:

- 사용자는 Host와 대화한다
- Host는 내부적으로 각 서버와 별도 연결을 유지한다
- 각 서버는 자기 기능만 표준 형태로 노출한다

## 5. 프로토콜 구조

공식 사양 기준 MCP는 `JSON-RPC 2.0`을 사용한다.

즉 메시지는 기본적으로 아래 셋 중 하나다.

- request
- response
- notification

### 5.1 request

상대에게 어떤 작업을 요청할 때 사용한다.

예:

- `tools/list`
- `tools/call`
- `resources/read`
- `prompts/get`

### 5.2 response

요청에 대한 결과를 반환한다.

예:

- 툴 목록
- 리소스 내용
- 툴 실행 결과

### 5.3 notification

응답이 필요 없는 상태 변경 알림이다.

예:

- 목록이 바뀌었음
- 특정 리소스가 갱신됐음

## 6. MCP의 표준 전송 방식

공식 사양 기준 현재 표준 transport는 두 가지다.

### 6.1 stdio

가장 흔하고, 로컬 개발에서 가장 단순하다.

구조:

- client가 server 프로세스를 subprocess로 띄운다
- server는 `stdin`으로 JSON-RPC를 읽는다
- server는 `stdout`으로 JSON-RPC를 쓴다

주의:

- `stdout`에는 MCP 메시지 외의 것을 쓰면 안 된다
- 로그는 `stderr`로 보내는 게 맞다
- 줄바꿈 규칙을 지켜야 한다

언제 쓰나:

- 로컬 개발
- 단일 사용자의 로컬 툴
- Claude Desktop 같은 로컬 연결

### 6.2 Streamable HTTP

이 방식은 server가 독립 프로세스로 떠 있고 여러 연결을 처리할 수 있다.

구조:

- HTTP POST/GET 사용
- 필요하면 SSE로 서버 메시지를 스트리밍 가능

언제 쓰나:

- 원격 서버
- 여러 클라이언트 연결
- SaaS형 MCP 서버

### 6.3 어떤 transport를 먼저 선택해야 하나

처음 구현한다면 보통 이렇게 간다.

- 로컬 개발용: `stdio`
- 팀 공유나 원격 서비스용: `Streamable HTTP`

초보 구현에서는 `stdio`가 훨씬 단순하다.

## 7. MCP 서버가 제공하는 3가지 핵심 primitive

MCP 서버는 보통 아래 세 가지를 노출한다.

## 7.1 Resources

Resources는 모델이나 앱이 참고할 `문맥 데이터`다.

예:

- 파일 내용
- 데이터베이스 스키마
- 특정 문서
- 설정 정보
- 도메인별 상태 데이터

핵심 특징:

- 각 리소스는 URI로 식별된다
- 앱이 명시적으로 고르거나 자동으로 포함할 수 있다

예시 감각:

- `file:///project/README.md`
- `db://schema/users`
- `notion://page/abc123`

리소스는 보통 “읽을 문맥”에 가깝다.

## 7.2 Tools

Tools는 모델이 실행할 수 있는 함수다.

예:

- 검색
- 계산
- 파일 생성
- 외부 API 호출
- DB 조회
- 배포 트리거

핵심 특징:

- 모델이 자동으로 발견하고 호출할 수 있다
- 입력 스키마를 JSON Schema 형태로 정의한다
- 실제 실행 위험이 있으므로 human-in-the-loop가 중요하다

즉, tools는 “행동”이다.

## 7.3 Prompts

Prompts는 사용자나 앱이 재사용할 수 있는 템플릿형 메시지/워크플로다.

예:

- 코드 리뷰 프롬프트
- 회의 요약 프롬프트
- 버그 리포트 생성 프롬프트

핵심 특징:

- 보통 사용자가 명시적으로 선택한다
- slash command처럼 노출될 수 있다

즉, prompts는 “재사용 가능한 대화 템플릿”이다.

## 8. 서버 capability 선언

MCP에서 서버는 자신이 무엇을 지원하는지 capability로 선언한다.

예:

- `tools`
- `resources`
- `prompts`

추가 옵션 예:

- `listChanged`
- `subscribe`

의미:

- `listChanged`: 도구/리소스/프롬프트 목록이 바뀌면 알림을 보낼 수 있음
- `subscribe`: 특정 리소스 변경을 구독할 수 있음

즉, capability는 “이 서버가 무슨 기능을 제공하는가”에 대한 계약이다.

## 9. 클라이언트 쪽 기능

공식 사양 기준, client 쪽도 몇 가지 기능을 제공할 수 있다.

- `Roots`
- `Sampling`
- `Elicitation`

### 9.1 Roots

서버가 “어디까지 접근 가능한가” 같은 경계를 물어볼 수 있는 기능이다.

예:

- 어떤 디렉터리 아래만 작업 가능한지
- 어떤 URI 범위까지 허용되는지

### 9.2 Sampling

서버가 다시 LLM 호출을 요청하는 구조다.

쉽게 말하면:

- 서버가 자체적으로 뭔가 판단하려고
- host 쪽 모델 샘플링을 요청하는 기능

이건 강력하지만 민감하므로 사용자 승인과 통제가 중요하다.

### 9.3 Elicitation

서버가 사용자에게 추가 정보를 요청하도록 host에 요구하는 기능이다.

예:

- “배포할 환경을 선택하세요”
- “이 작업을 정말 실행할까요?”

## 10. 초기 연결 흐름

MCP는 상태 없는 단순 REST가 아니라 `상태 있는 연결`을 전제로 한다.

초기화 흐름은 대략 이렇게 이해하면 된다.

1. host가 server에 연결
2. capability 교환
3. protocol version 협상
4. 이후 tools/resources/prompts 목록 조회
5. 필요 시 호출/구독/알림 처리

즉, 첫 연결에서 “너는 뭘 할 수 있고, 나는 뭘 지원한다”를 먼저 맞춘다.

## 11. 메시지 흐름 예시

### 11.1 Tool discovery

흐름:

1. client가 `tools/list` 요청
2. server가 tool 목록 반환
3. host가 UI나 모델 문맥에 반영

### 11.2 Tool execution

흐름:

1. 모델이 어떤 tool이 필요하다고 판단
2. host가 사용자 승인 또는 정책 검사
3. client가 `tools/call`
4. server가 실제 작업 수행
5. 결과를 response로 반환

### 11.3 Resource read

흐름:

1. client가 리소스 목록을 조회
2. 특정 URI를 선택
3. `resources/read` 요청
4. server가 내용 반환
5. host가 모델 문맥으로 사용

### 11.4 Prompt usage

흐름:

1. client가 `prompts/list`
2. 사용자가 prompt 선택
3. `prompts/get`
4. 서버가 템플릿 메시지 반환
5. host가 대화에 삽입

## 12. 구현할 때 무엇을 먼저 만들어야 하나

MCP 구현은 보통 아래 순서로 가면 된다.

### 12.1 1단계: 서버를 만들지, 클라이언트를 만들지 결정

대부분의 개발자는 먼저 `MCP server`를 만든다.

이유:

- host는 이미 존재하는 경우가 많다
- 우리는 보통 “내 데이터/내 툴을 AI에 붙이고 싶다”가 목적이다

즉:

- Claude Desktop, Claude Code, ChatGPT 같은 host가 이미 있음
- 우리는 그들이 붙을 서버를 만드는 편이 자연스럽다

### 12.2 2단계: transport 결정

처음에는 `stdio`를 권장한다.

이유:

- subprocess 기반이라 단순함
- 로컬 테스트가 빠름
- inspector 같은 개발 도구와 붙이기 쉬움

### 12.3 3단계: primitive 선택

처음부터 다 만들 필요는 없다.

보통 우선순위는 이렇다.

1. `tools`
2. `resources`
3. `prompts`

많은 경우 가장 먼저 가치가 나는 건 tools다.

예:

- DB 조회 tool
- 파일 읽기 tool
- API 호출 tool

## 13. MCP 서버 구현 방법

## 13.1 가장 단순한 설계

```text
MCP Server
 ├─ capability 선언
 ├─ tools/list
 ├─ tools/call
 ├─ resources/list
 ├─ resources/read
 ├─ prompts/list
 └─ prompts/get
```

처음에는 이 중 일부만 구현해도 된다.

### 13.2 서버 내부 구조 권장안

```text
server/
 ├─ transport layer
 ├─ protocol handlers
 ├─ tool registry
 ├─ resource registry
 ├─ prompt registry
 ├─ business services
 └─ auth / safety checks
```

역할 분리:

- transport layer: stdio 또는 HTTP 연결 처리
- protocol handlers: JSON-RPC 메서드 분기
- registries: 도구/리소스/프롬프트 목록 관리
- business services: 실제 비즈니스 로직
- auth/safety: 권한, 승인, 제한

### 13.3 Tools 구현 시 핵심

Tool 하나는 보통 아래 정보로 구성된다.

- `name`
- `title`
- `description`
- `inputSchema`
- 실행 함수

중요:

- 이름은 안정적으로 유지해야 한다
- description은 모델이 읽기 때문에 명확해야 한다
- inputSchema는 엄격하게 정의해야 한다

### 13.4 Resources 구현 시 핵심

Resource 하나는 보통 아래 개념을 가진다.

- `uri`
- `name`
- `description`
- 읽기 함수

중요:

- URI 체계를 일관되게 설계해야 한다
- “목록 조회”와 “실제 읽기”를 분리하는 편이 좋다

### 13.5 Prompts 구현 시 핵심

Prompt는 보통 아래를 가진다.

- `name`
- `title`
- `description`
- `arguments`
- prompt 생성 함수

중요:

- prompts는 보통 tool보다 사용자 직접 선택형에 가깝다
- slash command 같은 UX와 잘 맞는다

## 14. MCP 클라이언트 구현 방법

클라이언트를 직접 만드는 경우는 상대적으로 적지만, 구조는 중요하다.

클라이언트가 해야 하는 일:

1. 서버 프로세스 실행 또는 원격 연결
2. 초기화 핸드셰이크
3. capability 파악
4. tools/resources/prompts 목록 조회
5. 실제 요청 전송
6. 응답/알림/오류 처리

클라이언트에서 중요한 포인트:

- 연결 수명 관리
- 타임아웃
- 재시도
- 사용자 승인 UI
- 호출 로그

## 15. 보안과 승인 구조

공식 문서는 MCP가 강력한 만큼 보안과 사용자 통제를 매우 중요하게 본다.

핵심 원칙:

### 15.1 사용자 동의

- 어떤 데이터가 노출되는지 사용자가 알아야 한다
- 어떤 tool이 실행되는지 사용자가 알아야 한다

### 15.2 데이터 프라이버시

- 사용자 데이터는 무단 전송하면 안 된다
- host는 서버에 데이터를 넘기기 전에 명시적 통제를 제공해야 한다

### 15.3 Tool safety

- tool은 사실상 임의 코드 실행 경로가 될 수 있다
- 그래서 특히 주의해야 한다

### 15.4 Sampling 통제

- 서버가 추가 LLM 호출을 유도하는 경우 사용자 승인과 통제가 필요하다

실무 해석:

- 읽기 전용과 쓰기 도구를 분리
- destructive tool은 별도 확인
- 민감 데이터 접근은 whitelist 기반

## 16. 구현 시 추천 절차

처음 MCP 서버를 만들 때 추천 절차는 이렇다.

### 1단계

도메인 결정

예:

- 파일 탐색
- 번역 프로젝트 관리
- DB 질의
- 문서 검색

### 2단계

가장 작은 tool 1개 구현

예:

- `get_status`
- `list_projects`
- `search_notes`

### 3단계

`stdio` transport로 로컬 연결

### 4단계

MCP Inspector로 테스트

### 5단계

필요하면 resources 추가

### 6단계

필요하면 prompts 추가

### 7단계

권한/승인/로그 구조 추가

### 8단계

원격 서버가 필요하면 Streamable HTTP로 확장

## 17. MCP를 언제 쓰는 게 맞나

다음 조건이면 MCP가 매우 잘 맞는다.

- 여러 AI host에서 재사용하고 싶다
- 툴/리소스/프롬프트를 표준 방식으로 노출하고 싶다
- 일회성 API 연동이 아니라 장기적으로 확장 가능한 구조가 필요하다

반대로 이런 경우는 MCP가 과할 수 있다.

- 특정 앱 하나에만 매우 단순한 API 연결
- tool 하나만 임시로 붙이면 되는 경우
- host/client/server 구분까지 갈 필요가 없는 경우

즉, MCP는 “장기적으로 재사용 가능한 AI 연결 계층”이 필요할 때 빛난다.

## 18. DeadlineForYou에 MCP를 적용한다면

이 프로젝트에 MCP를 붙인다면 대략 이런 구조가 가능하다.

### Resources

- 활성 프로젝트 상태
- 오늘의 세션 기록
- 마감 리포트
- 회피 이벤트 통계

예시 URI:

- `deadline://projects/active`
- `deadline://reports/today`
- `deadline://sessions/latest`

### Tools

- `start_session`
- `complete_session`
- `update_project_progress`
- `generate_deadline_report`

### Prompts

- `force_start_coaching`
- `boss_mode_coaching`
- `cold_support_coaching`

즉, `DeadlineForYou`는 MCP server로 확장하기 좋은 구조다.

이유:

- 이미 서비스 계층이 분리되어 있음
- 데이터 모델이 명확함
- tools/resources/prompts로 잘 분해 가능함

## 19. 요약

MCP는 단순한 “플러그인 API”가 아니라 다음을 표준화한 구조다.

- AI host와 외부 시스템 연결 방식
- context 제공 방식
- tool 실행 방식
- prompt 재사용 방식

핵심 이해 포인트는 이것뿐이다.

1. Host / Client / Server를 구분한다
2. JSON-RPC 2.0 기반이다
3. 표준 transport는 `stdio`, `Streamable HTTP`
4. 서버는 `resources`, `tools`, `prompts`를 제공한다
5. 구현은 보통 `stdio + tools`부터 시작하는 게 가장 쉽다

## 20. 공식 문서

- Intro: https://modelcontextprotocol.io/docs/getting-started/intro
- Specification: https://modelcontextprotocol.io/specification/2025-06-18
- Architecture: https://modelcontextprotocol.io/docs/learn/architecture
- Transports: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- Tools: https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- Resources: https://modelcontextprotocol.io/specification/2025-06-18/server/resources
- Prompts: https://modelcontextprotocol.io/specification/2025-06-18/server/prompts
- GitHub: https://github.com/modelcontextprotocol/modelcontextprotocol
