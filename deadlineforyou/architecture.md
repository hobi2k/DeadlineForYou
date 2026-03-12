# DeadlineForYou Architecture

## 1. 문서 목적

이 문서는 현재 `DeadlineForYou` 구현 기준으로 다음을 자세히 설명한다.

- 전체 시스템 구조
- FastAPI 구조
- 데이터베이스 구조
- Telegram bot 구조
- LLM provider 구조
- 기능과 동작 흐름
- 설계 의도
- 현재 한계와 확장 포인트

즉, 이 문서는 `blueprint.md`의 제품 설계가 아니라, 지금 코드가 실제로 어떻게 구성되어 있는지 정리한 구현 아키텍처 문서다.

## 2. 프로젝트 개요

`DeadlineForYou`는 프리랜서 번역가를 대상으로 하는 마감 집행 시스템이다.

핵심 개념은 단순하다.

1. 사용자의 회피 메시지를 입력받는다.
2. 현재 프로젝트 상태와 마감 압박을 계산한다.
3. `締切監督` 페르소나로 응답을 생성한다.
4. 사용자가 바로 행동하도록 작업과 타이머를 제시한다.

시스템은 두 개의 진입점을 가진다.

- REST API
- Telegram bot

이 둘은 서로 다른 UI일 뿐, 내부 비즈니스 로직은 같은 서비스 계층을 공유한다.

## 3. 전체 구조

### 3.1 상위 구성

```text
User
 ├─ Swagger UI / REST Client
 └─ Telegram Chat
         |
         v
  FastAPI / Telegram Adapter
         |
         v
  DeadlineCoachService
         |
         +─ Rule Engine
         +─ Prompt Builder
         +─ LLM Provider
         +─ SQLite Storage
```

### 3.2 실제 코드 구성

```text
deadlineforyou/
 ├─ main.py            # FastAPI 엔트리포인트
 ├─ telegram_bot.py    # Telegram polling bot 엔트리포인트
 ├─ mcp_server.py      # stdio 기반 MCP server 엔트리포인트
 ├─ service.py         # 핵심 오케스트레이션 계층
 ├─ storage.py         # SQLite 영속 계층
 ├─ rules.py           # 회피 감지 / 모드 판정 규칙
 ├─ providers.py       # openai / local / scripted provider
 ├─ tools.py           # 내부 tool registry와 MCP 노출 정의
 ├─ prompts.py         # 시스템 프롬프트와 컨텍스트 조립
 ├─ schemas.py         # API 입출력 스키마
 ├─ domain.py          # enum / dataclass 같은 도메인 타입
 ├─ config.py          # 환경 변수 설정
 └─ models/            # 로컬 모델 저장 위치
```

### 3.3 설계 원칙

- 입력 채널과 비즈니스 로직을 분리한다.
- 페르소나 생성은 LLM에 맡기되, 모드 판정은 규칙 엔진이 잡는다.
- 상태는 SQLite에 저장해 API와 Telegram이 동시에 공유한다.
- LLM provider는 인터페이스를 통일해 교체 가능하게 둔다.

## 4. 실행 구조

### 4.1 FastAPI 실행

실행 모듈:

- `deadlineforyou.main`

역할:

- HTTP 요청 수신
- 요청 본문 검증
- 서비스 계층 호출
- 응답 스키마 직렬화

### 4.2 Telegram bot 실행

실행 모듈:

- `deadlineforyou.telegram_bot`

역할:

- 텔레그램 명령 처리
- 텔레그램 사용자를 내부 user 레코드와 연결
- 세션 시작 / 보고 / 일반 메시지 응답 처리
- 타이머 후속 메시지 전송

### 4.3 공용 의존성

FastAPI, Telegram bot, MCP server는 모두 아래를 공유한다.

- `Settings`
- `Database`
- `LLMProvider`
- `DeadlineCoachService`

즉, UI가 달라도 코칭 로직은 동일하다.

## 5. 설정 구조

설정 파일:

- `deadlineforyou/config.py`

환경 변수 접두사:

- `DFY_`

핵심 설정:

- `DFY_DATABASE_PATH`
- `DFY_LLM_PROVIDER`
- `DFY_LLM_MODEL`
- `DFY_OPENAI_API_KEY`
- `DFY_LOCAL_MODEL_PATH`
- `DFY_LOCAL_DEVICE_MAP`
- `DFY_LOCAL_MAX_NEW_TOKENS`
- `DFY_LOCAL_TEMPERATURE`
- `DFY_TELEGRAM_BOT_TOKEN`

설계 포인트:

- `.env` 기반으로 로컬 개발을 단순화했다.
- provider 전환은 환경 변수만 바꾸면 된다.
- 로컬 모델 경로는 프로젝트 내부 `deadlineforyou/models/saya_rp_4b_v3`를 기본값으로 둔다.

## 6. API 구조

API 엔트리:

- `deadlineforyou/main.py`

### 6.1 앱 생명주기

FastAPI는 `lifespan()`에서 아래를 생성한다.

1. `Settings`
2. `Database`
3. `LLMProvider`
4. `DeadlineCoachService`

이 서비스 인스턴스는 `app.state.service`에 저장된다.

### 6.2 API 엔드포인트 목록

#### `GET /health`

역할:

- 서버 상태 확인

응답:

```json
{"status":"ok"}
```

#### `POST /users`

역할:

- 내부 사용자 생성

입력:

- `platform_user_id`
- `nickname`
- `timezone`
- `tone_preference`

#### `POST /projects`

역할:

- 프로젝트 생성

입력:

- `user_id`
- `title`
- `source_language`
- `target_language`
- `total_units`
- `completed_units`
- `deadline_at`
- `unit_label`

#### `GET /users/{user_id}/projects`

역할:

- 사용자의 프로젝트 목록 조회

정렬:

- 마감 순 오름차순

#### `PATCH /projects/{project_id}`

역할:

- 진행량 / 총량 / 마감 / 상태 수정

수정 가능 필드:

- `completed_units`
- `total_units`
- `deadline_at`
- `status`

#### `POST /chat`

역할:

- 핵심 코칭 엔드포인트
- 사용자 메시지를 받아 페르소나 답변 생성

입력:

- `user_id`
- `message`
- `project_id` optional

출력:

- `reply`
- `mode`
- `urgency_score`
- `timer_minutes`
- `action_hint`
- `report_hint`
- `executed_tools`

#### `POST /sessions`

역할:

- 작업 세션 생성

입력:

- `user_id`
- `project_id`
- `duration_minutes`
- `mode`

#### `GET /sessions/{session_id}`

역할:

- 세션 상태 조회

특징:

- 만료 시 자동으로 `expired` 상태로 전환될 수 있다.

#### `POST /sessions/{session_id}/complete`

역할:

- 세션 종료 보고
- 프로젝트 진행량 반영

입력:

- `result_text`
- `completed_units_delta`

#### `GET /users/{user_id}/daily-report`

역할:

- 오늘의 집중 시간 / 완료량 / 회피 횟수 집계

#### `GET /meta/providers`

역할:

- 현재 provider 설정 점검

용도:

- 디버깅
- 프론트엔드 연동 확인

## 7. 데이터베이스 구조

저장소 구현 파일:

- `deadlineforyou/storage.py`

DB 엔진:

- SQLite

접근 방식:

- 표준 라이브러리 `sqlite3`
- `sqlite3.Row` 기반 row mapping

### 7.1 테이블 개요

#### users

목적:

- 내부 사용자 저장

컬럼:

- `id`
- `platform_user_id`
- `nickname`
- `timezone`
- `tone_preference`
- `created_at`

특징:

- `platform_user_id`는 unique다.
- Telegram 사용자는 `telegram-{telegram_user_id}` 형식으로 저장된다.

#### projects

목적:

- 번역 프로젝트 저장

컬럼:

- `id`
- `user_id`
- `title`
- `source_language`
- `target_language`
- `total_units`
- `completed_units`
- `deadline_at`
- `unit_label`
- `status`
- `created_at`

설계 포인트:

- 현재 활성 프로젝트는 `status='active'`로 구분한다.
- 텔레그램 봇은 가장 가까운 active 프로젝트를 기본 대상으로 본다.

#### sessions

목적:

- 타이머 기반 작업 세션 저장

컬럼:

- `id`
- `user_id`
- `project_id`
- `mode`
- `duration_minutes`
- `status`
- `started_at`
- `ends_at`
- `ended_at`
- `reported_result`
- `completed_units_delta`

상태값:

- `active`
- `completed`
- `cancelled`
- `expired`

설계 포인트:

- 세션 완료 시 프로젝트 진행량을 자동 반영한다.
- 세션 조회 시 `ends_at`이 지났으면 lazy expiration을 적용한다.

#### messages

목적:

- 최근 대화 이력 저장

컬럼:

- `id`
- `user_id`
- `project_id`
- `role`
- `content`
- `created_at`

용도:

- LLM prompt에 최근 대화 문맥을 재주입

#### avoidance_events

목적:

- 회피 행동 기록

컬럼:

- `id`
- `user_id`
- `project_id`
- `trigger_text`
- `category`
- `severity`
- `created_at`

용도:

- 오늘 회피 횟수 계산
- 규칙 엔진 입력 강화
- 일일 리포트 생성

### 7.2 DB 접근 메서드 분류

#### 사용자 관련

- `create_user`
- `get_user`
- `get_user_by_platform_id`

#### 프로젝트 관련

- `create_project`
- `get_project`
- `list_projects_for_user`
- `get_active_project_for_user`
- `update_project`

#### 세션 관련

- `create_session`
- `get_session`
- `complete_session`

#### 대화 기록 관련

- `add_message`
- `recent_messages`

#### 회피 이벤트 관련

- `add_avoidance_event`
- `today_avoidance_events`

#### 집계 관련

- `today_completed_sessions`

## 8. 도메인 구조

도메인 파일:

- `deadlineforyou/domain.py`

### 8.1 CoachingMode

현재 정의된 모드:

- `default`
- `reality_check`
- `force_start`
- `cold_support`
- `boss_mode`

의미:

- `default`: 기본 코칭
- `reality_check`: 미루는 비용을 직시시키는 모드
- `force_start`: 시작 저항을 강제로 쪼개는 모드
- `cold_support`: 피로 상태를 짧게 다독이며 밀어붙이는 모드
- `boss_mode`: 마감이 극단적으로 가까운 경우

### 8.2 SessionStatus

상태값:

- `active`
- `completed`
- `cancelled`
- `expired`

### 8.3 RuleEvaluation

규칙 엔진 결과 구조:

- `mode`
- `urgency_score`
- `avoidance_hits`
- `timer_minutes`
- `action_hint`
- `report_hint`

이 구조는 서비스 계층과 API 응답에 직접 사용된다.

## 9. 스키마 구조

스키마 파일:

- `deadlineforyou/schemas.py`

역할:

- FastAPI 요청/응답 검증
- 타입 강제
- 자동 OpenAPI 문서 생성

### 9.1 요청 스키마

- `UserCreate`
- `ProjectCreate`
- `ProjectUpdate`
- `ChatRequest`
- `SessionCreate`
- `SessionComplete`

### 9.2 응답 스키마

- `UserResponse`
- `ProjectResponse`
- `ChatResponse`
- `SessionResponse`
- `DailyReportResponse`

설계 포인트:

- `SessionCreate.mode`는 `CoachingMode` enum을 사용한다.
- `ProjectCreate.total_units`와 `SessionCreate.duration_minutes`에는 validation이 있다.

## 10. Rule Engine 구조

규칙 엔진 파일:

- `deadlineforyou/rules.py`

### 10.1 회피 감지

현재 감지 패턴:

- `하기 싫`
- `귀찮`
- `나중`
- `내일`
- `졸려`
- `피곤`
- `유튜브`
- `도망`
- `못 하겠`

출력:

- 심각도 점수
- 회피 분류

분류 예:

- `resistance`
- `delay`
- `fatigue`
- `escape`
- `freeze`

### 10.2 모드 판정

입력:

- 최신 메시지
- 프로젝트 상태
- 오늘 회피 이벤트 수

판단 요소:

- 메시지 자체의 회피 신호
- 마감까지 남은 시간
- 현재 진행률
- 오늘 회피 누적 횟수

결과:

- 코칭 모드
- 타이머 길이
- 액션 지시 힌트
- 보고 요청 힌트

### 10.3 판정 기준 요약

- 마감 6시간 이내면 `boss_mode`
- 회피 신호가 강하면 `force_start`
- 졸림/피로 표현이면 `cold_support`
- 오늘 회피 누적이 많으면 `reality_check`
- 그 외는 `default`

## 11. Prompt 구조

프롬프트 파일:

- `deadlineforyou/prompts.py`

### 11.1 SYSTEM_PROMPT

내용:

- `締切監督` 페르소나 정의
- 말투 원칙
- 행동 규칙
- 금지 규칙

### 11.2 build_context_block

역할:

- 사용자 상태
- 프로젝트 상태
- 규칙 엔진 힌트

를 하나의 컨텍스트 문자열로 조합한다.

실제 구조:

```text
[USER STATE]
...

[PROJECT STATE]
...

[RULE ENGINE]
...
```

이 구조는 provider의 system message에 함께 주입된다.

## 12. LLM Provider 구조

provider 파일:

- `deadlineforyou/providers.py`

### 12.1 공통 인터페이스

`LLMProvider.generate(...)`

입력:

- `system_prompt`
- `context_block`
- `history`
- `user_message`

출력:

- 문자열 답변

### 12.2 OpenAIProvider

역할:

- OpenAI chat completions 호출

특징:

- `DFY_OPENAI_API_KEY` 필요
- `DFY_LLM_MODEL` 사용

### 12.3 LocalOpenAICompatibleProvider

이름은 그렇지만 현재 구현은 외부 호환 서버가 아니라 직접 로컬 모델을 로딩한다.

역할:

- `deadlineforyou/models/saya_rp_4b_v3`를 `transformers`로 로드
- chat template 적용
- 생성 토큰만 잘라서 반환

특징:

- `Qwen3ForCausalLM` 계열
- `device_map=auto`
- `torch_dtype="auto"`
- `max_new_tokens`, `temperature` 환경 변수 제어

### 12.4 ScriptedFallbackProvider

역할:

- 실제 모델 없이 고정 응답 반환

용도:

- 초기 API 확인
- 구조 smoke test
- 모델 없이 UI 확인

### 12.5 provider 선택 방식

`build_provider(settings)`가 `settings.llm_provider`에 따라 아래 중 하나를 선택한다.

- `openai`
- `local`
- `scripted`

## 13. 서비스 계층 구조

서비스 파일:

- `deadlineforyou/service.py`

`DeadlineCoachService`는 이 프로젝트의 핵심 오케스트레이터다.

### 13.1 역할

- 데이터 조회
- 회피 이벤트 기록
- 규칙 엔진 호출
- 프롬프트 컨텍스트 구성
- LLM provider 호출
- 메시지 저장
- 세션 및 리포트 집계

### 13.2 주요 메서드

#### 사용자

- `create_user`
- `get_or_create_user`

`get_or_create_user`는 Telegram bot에서 특히 중요하다.

이유:

- 텔레그램 사용자는 별도 회원가입 없이 자동으로 내부 user 레코드와 연결된다.

#### 프로젝트

- `create_project`
- `list_projects`
- `update_project`

#### 세션

- `start_session`
- `complete_session`
- `get_session`

#### 코칭

- `chat`

#### 집계

- `build_daily_report`

### 13.3 `chat()` 상세 흐름

`chat()`은 시스템 전체에서 가장 중요한 함수다.

흐름:

1. `project_id`가 있으면 해당 프로젝트 조회
2. 없으면 사용자의 active 프로젝트 조회
3. 오늘 회피 이벤트 수 조회
4. `evaluate_mode()` 실행
5. 메시지 자체 회피 감지 후 `avoidance_events` 저장
6. 최근 메시지 이력 조회
7. 사용자 / 프로젝트 / 규칙 스냅샷 생성
8. `build_context_block()`으로 컨텍스트 조립
9. 사용자 메시지 저장
10. provider 호출
11. 모델 답변 저장
12. 답변 문자열과 규칙 평가 반환

즉, 단순 챗봇 호출이 아니라 상태 기반 오케스트레이션이다.

## 14. Telegram bot 구조

Telegram bot 파일:

- `deadlineforyou/telegram_bot.py`

실행 방식:

- polling

### 14.1 봇 시작 시 구성

`build_application()`이 아래를 수행한다.

1. 텔레그램 토큰 확인
2. `Application` 생성
3. 공용 `DeadlineCoachService` 생성
4. 핸들러 등록

### 14.2 Telegram 명령 구조

#### `/start`

역할:

- 사용자 자동 등록
- 사용 가능한 명령 안내

#### `/help`

역할:

- 명령 목록 출력

#### `/status`

역할:

- 현재 active 프로젝트 상태 표시
- 오늘 집중 시간과 회피 횟수 표시

제한:

- 프로젝트 생성 명령은 아직 없기 때문에, 프로젝트가 없으면 API에서 먼저 만들어야 한다.

#### `/start10`

역할:

- `force_start` 모드 10분 세션 시작

#### `/start15`

역할:

- `cold_support` 모드 15분 세션 시작

#### `/pomodoro`

역할:

- `boss_mode` 25분 세션 시작

#### `/report <숫자>`

역할:

- 마지막 세션 완료 처리
- 작업량 증가 반영
- 후속 코칭 답변 생성

예:

- `/report 8`

의미:

- 이번 세션에서 8단위를 처리했다고 보고

### 14.3 일반 텍스트 메시지 처리

핸들러:

- `text_message`

흐름:

1. 텔레그램 사용자를 내부 user로 보장
2. `service.chat()` 호출
3. 생성 답변을 그대로 reply

### 14.4 타이머 후속 메시지

핸들러:

- `send_session_followup`

동작:

- `/start10`, `/start15`, `/pomodoro` 호출 시 `job_queue.run_once()` 등록
- 세션 종료 시점에 `/report`를 유도하는 메시지를 전송

설계 포인트:

- 세션 알림은 Telegram job queue에 맡긴다.
- 실제 세션 상태 저장은 SQLite가 담당한다.

즉, 알림은 메모리 스케줄러, 기록은 DB라는 분리 구조다.

## 15. 사용자 흐름

### 15.1 API 기반 흐름

```text
사용자 생성
 -> 프로젝트 생성
 -> /chat 호출
 -> 응답 확인
 -> /sessions 생성
 -> /sessions/{id}/complete
 -> /daily-report 확인
```

### 15.2 Telegram 기반 흐름

```text
/start
 -> 내부 user 자동 생성
 -> /status
 -> 일반 메시지 또는 /start10
 -> 세션 종료 알림
 -> /report 8
 -> 다음 코칭 응답
```

### 15.3 로컬 모델 기반 흐름

```text
uv run initialize.py
 -> deadlineforyou/models/saya_rp_4b_v3 다운로드
 -> DFY_LLM_PROVIDER=local
 -> API 또는 Telegram bot 실행
 -> service.chat()
 -> Local provider.generate()
 -> 로컬 모델 응답 생성
```

## 16. 기능 정리

현재 구현된 기능:

- 사용자 생성
- 프로젝트 생성
- 프로젝트 수정
- 상태 기반 코칭
- 회피 감지
- 세션 생성
- 세션 완료 반영
- 일일 리포트
- Telegram 사용자 자동 등록
- Telegram 세션 타이머
- local / openai / scripted provider 전환

아직 구현되지 않은 기능:

- Telegram에서 프로젝트 생성
- Telegram에서 마감 수정
- 다중 프로젝트 전환 명령
- 관리자 페이지
- 웹 프론트엔드
- 장기 기억 / 통계 시각화

## 17. 설계의 장점

### 17.1 채널 분리

API와 Telegram이 서비스 계층을 공유하므로 중복 로직이 적다.

### 17.2 provider 교체 용이

OpenAI, 로컬 모델, scripted를 쉽게 바꿀 수 있다.

### 17.3 단순한 저장 구조

SQLite 하나로 프로젝트, 세션, 메시지, 회피 기록을 다룬다.

### 17.4 규칙 + 생성 결합

말투는 생성형 모델이 담당하고, 행동 강제는 규칙 엔진이 보정한다.

## 18. 현재 한계

### 18.1 DB 규모

현재는 SQLite라서 단일 인스턴스 운영에 적합하다.

### 18.2 Telegram 기능 범위

프로젝트 생성까지 텔레그램에서 끝나지 않는다.

### 18.3 타이머 영속성

Telegram job queue는 프로세스 재시작 시 메모리 스케줄이 사라진다.

즉:

- 세션 기록은 남음
- 후속 알림 예약은 날아갈 수 있음

### 18.4 인증 / 권한 체계

현재 REST API는 별도 인증이 없다.

### 18.5 모델 로딩 비용

로컬 provider는 프로세스 시작 시 모델을 메모리에 적재하므로 초기 로딩이 무겁다.

## 19. MCP와 Tool Calling 설계

현재 구현은 단순 텍스트 응답기에서 한 단계 더 나아가 `tool calling`과 `MCP server` 구조를 포함한다.

### 19.1 왜 tool calling으로 가는가

기존 방식:

- 모델이 응답만 생성
- 실제 상태 조회와 세션 생성은 UI 또는 서버 코드가 따로 처리

tool calling 방식:

- 모델이 필요할 때 도구를 호출
- 서버가 실제 상태를 읽고 세션을 생성
- 그 결과를 다시 모델에 넣어 최종 응답을 생성

즉, 모델은 더 이상 말만 하는 존재가 아니라 상태를 읽고 행동을 트리거하는 에이전트가 된다.

### 19.2 이 프로젝트에서의 이점

- 말과 실제 상태가 연결된다
- 세션 시작, 완료, 리포트 조회를 모델이 직접 호출 가능하다
- 텔레그램, REST API, 향후 MCP host가 같은 도구 집합을 재사용한다
- 임의 문자열 파싱보다 입력 구조가 안정적이다
- “지금 10분 세션 시작해” 같은 말이 실제 세션 생성으로 이어질 수 있다
- 향후 승인 흐름과 권한 제어를 넣기 쉽다

### 19.3 내부 tool calling 구조

구현 파일:

- `deadlineforyou/tools.py`
- `deadlineforyou/providers.py`
- `deadlineforyou/service.py`

구조:

```text
chat()
 -> bound tool registry 생성
 -> provider.generate_turn(..., tools=...)
 -> 모델이 tool call 반환
 -> 서버가 tool 실행
 -> tool 결과를 다시 messages에 추가
 -> 모델 최종 응답 생성
```

### 19.4 현재 제공되는 내부 도구

현재 채팅 루프에서 사용할 수 있는 도구:

- `get_active_project`
- `start_focus_session`
- `complete_focus_session`
- `get_daily_report`
- `list_projects`

이 도구들은 현재 사용자 문맥에 바인딩된다.

즉:

- 채팅 중에는 `user_id`를 모델이 직접 알 필요가 없다
- 서버가 현재 사용자 기준으로 안전하게 실행한다

### 19.5 provider별 tool calling 처리

#### OpenAI provider

- OpenAI native tool calling 사용
- `chat.completions`에 `tools` 전달
- `message.tool_calls`를 파싱

#### Local provider

- Qwen3 chat template의 tool block 사용
- 모델 출력의 `<tool_call>...</tool_call>` 블록을 파싱
- 텍스트와 tool call을 분리

#### Scripted provider

- tool calling 미지원
- 고정 응답만 반환

### 19.6 API 응답에 반영된 정보

`POST /chat` 응답에는 이제 다음이 포함된다.

- `reply`
- `mode`
- `urgency_score`
- `timer_minutes`
- `action_hint`
- `report_hint`
- `executed_tools`

즉, 실제로 어떤 도구가 실행됐는지 디버깅과 검증이 가능하다.

### 19.7 MCP server 구조

구현 파일:

- `deadlineforyou/mcp_server.py`

현재 구현은 `stdio` 기반 JSON-RPC 루프다.

지원 메서드:

- `initialize`
- `tools/list`
- `tools/call`
- `resources/list`
- `resources/read`
- `prompts/list`
- `prompts/get`

### 19.8 MCP에서 노출하는 도구

현재 MCP 도구:

- `get_active_project`
- `list_projects`
- `start_focus_session`
- `complete_focus_session`
- `get_daily_report`

내부 chat용 tool과 차이:

- MCP 도구는 외부 host가 호출하므로 `user_id` 같은 인자를 직접 받는다
- chat용 bound tool은 현재 사용자 문맥에 묶여 있다

### 19.9 MCP에서 노출하는 리소스

현재 리소스:

- `deadline://schema/users`
- `deadline://schema/projects`
- `deadline://schema/sessions`

역할:

- 구조 설명용 정적 리소스
- host가 DB 스키마 문맥을 읽을 수 있게 함

### 19.10 MCP에서 노출하는 prompt

현재 prompt:

- `force_start_coaching`

역할:

- 강제 시작형 코칭 템플릿을 host에서 재사용할 수 있게 함

### 19.11 이 설계의 장점

- AI host가 바뀌어도 동일한 도구를 재사용 가능
- 내부 서비스 계층을 그대로 MCP tool로 노출 가능
- tool calling과 MCP가 같은 core를 공유하므로 중복 구현이 적다
- REST / Telegram / MCP의 기능 차이를 줄일 수 있다

### 19.12 현재 한계

- MCP 서버는 현재 stdio 기반 최소 구현이다
- Streamable HTTP transport는 아직 없다
- MCP 리소스는 아직 정적 스키마 수준이다
- Telegram 쪽 세션 알림은 여전히 메모리 스케줄러 기반이다
- 모든 provider가 tool calling 품질이 같지는 않다

## 20. 확장 방향

추천 확장 순서:

1. Telegram에서 `/deadline_add` 구현
2. `/project switch` 같은 active 프로젝트 전환 기능
3. 세션 후속 알림을 DB 기반 스케줄러로 승격
4. PostgreSQL 전환
5. 웹 프론트엔드 추가
6. 통계 대시보드 추가

## 21. 요약

현재 `DeadlineForYou`는 다음 구조를 가진다.

- 입력 채널: REST API, Telegram
- 코어 로직: `DeadlineCoachService`
- 규칙 판정: `rules.py`
- 페르소나 생성: `providers.py`
- 저장소: `storage.py` + SQLite
- 설정: `config.py`

핵심 흐름은 항상 같다.

```text
입력
 -> 상태 조회
 -> 회피 판정
 -> 모드 결정
 -> 프롬프트 조립
 -> LLM 응답 생성
 -> 기록 저장
 -> 다음 행동 지시
```

즉, 이 시스템은 단순 챗봇이 아니라 `상태 기반 마감 집행기`다.
