# DeadlineForYou Architecture

## 1. 문서 목적

이 문서는 현재 코드 기준의 실제 구현 구조를 설명한다.

포함 범위:

- 전체 시스템 구조
- API 구조
- 데이터베이스 구조
- Telegram bot 구조
- provider 분리 구조
- 내부 tool calling 흐름
- 번역 / 이미지 생성 흐름
- 현재 제약과 운영 포인트

이 문서는 설계 아이디어 모음이 아니라, 지금 코드가 실제로 어떻게 돌아가는지 정리한 구현 문서다.

## 2. 시스템 개요

`DeadlineForYou`는 프리랜서 번역가의 회피를 줄이고, 프로젝트 상태를 보면서 즉시 행동 지시를 내리는 로컬 마감 집행 시스템이다.

핵심 동작:

1. 사용자 메시지 수신
2. 현재 프로젝트와 회피 상태 계산
3. 규칙 엔진으로 모드 판정
4. `締切監督` 페르소나 답변 생성
5. 필요하면 내부 tool 호출
6. 세션 / 진행량 / 리포트에 반영

추가 기능:

- 짧은 텍스트 번역
- 프롬프트 기반 이미지 생성

## 3. 상위 구조

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
         +─ Translation Provider
         +─ Image Provider
         +─ SQLite Storage
```

설계 포인트:

- 입력 채널은 둘이지만 비즈니스 로직은 하나다.
- 코칭, 번역, 이미지 생성을 provider 레이어에서 분리했다.
- 상태는 SQLite 하나에 저장한다.

## 4. 코드 구조

```text
deadlineforyou/
 ├─ main.py
 ├─ telegram_bot.py
 ├─ service.py
 ├─ storage.py
 ├─ rules.py
 ├─ prompts.py
 ├─ providers.py
 ├─ tools.py
 ├─ schemas.py
 ├─ domain.py
 ├─ config.py
 └─ models/
```

모듈 역할:

- `main.py`: FastAPI 엔트리포인트
- `telegram_bot.py`: polling 기반 Telegram bot
- `service.py`: 핵심 오케스트레이터
- `storage.py`: SQLite 영속 계층
- `rules.py`: 회피 감지 / 모드 평가
- `prompts.py`: 시스템 프롬프트와 컨텍스트 조립
- `providers.py`: 코칭 / 번역 / 이미지 provider
- `tools.py`: 내부 tool registry
- `schemas.py`: API 요청 / 응답 스키마
- `domain.py`: enum, dataclass 등 도메인 타입
- `config.py`: 환경 변수 설정

## 5. 실행 구조

### 5.1 API 서버

실행 모듈:

- `deadlineforyou.main`

역할:

- HTTP 요청 처리
- 스키마 검증
- 서비스 호출
- JSON 응답 반환

### 5.2 Telegram bot

실행 모듈:

- `deadlineforyou.telegram_bot`

역할:

- 텔레그램 사용자 자동 등록
- 세션 명령 처리
- 프로젝트 등록 명령 처리
- 코칭 / 번역 / 이미지 생성 호출
- 후속 보고 알림

### 5.3 공용 의존성

둘 다 공통으로 사용하는 것:

- `Settings`
- `Database`
- `DeadlineCoachService`
- provider 계층

즉, UI만 다르고 동작 핵심은 동일하다.

## 6. 설정 구조

설정 파일:

- `deadlineforyou/config.py`

환경 변수 접두사:

- `DFY_`

주요 설정:

- `DFY_DATABASE_PATH`
- `DFY_LLM_PROVIDER`
- `DFY_LOCAL_MODEL_PATH`
- `DFY_LOCAL_DEVICE_MAP`
- `DFY_LOCAL_MAX_NEW_TOKENS`
- `DFY_LOCAL_TEMPERATURE`
- `DFY_TRANSLATION_PROVIDER`
- `DFY_TRANSLATION_LOCAL_MODEL_PATH`
- `DFY_TRANSLATION_LAZY_LOAD`
- `DFY_TRANSLATION_LOCAL_MAX_NEW_TOKENS`
- `DFY_TRANSLATION_LOCAL_TEMPERATURE`
- `DFY_IMAGE_PROVIDER`
- `DFY_IMAGE_LOCAL_MODEL_PATH`
- `DFY_IMAGE_LAZY_LOAD`
- `DFY_IMAGE_UNLOAD_AFTER_GENERATION`
- `DFY_IMAGE_ENABLE_MODEL_CPU_OFFLOAD`
- `DFY_IMAGE_RELEASE_TRANSLATION_BEFORE_GENERATION`
- `DFY_IMAGE_DEVICE`
- `DFY_IMAGE_NUM_INFERENCE_STEPS`
- `DFY_IMAGE_GUIDANCE_SCALE`
- `DFY_IMAGE_NEGATIVE_PROMPT`
- `DFY_IMAGE_SEED`
- `DFY_IMAGE_OUTPUT_DIR`
- `DFY_TELEGRAM_BOT_TOKEN`

지원 provider:

- 코칭: `local`, `scripted`
- 번역: `local`, `scripted`, `inherit`
- 이미지: `local`, `none`

## 7. API 구조

엔트리 파일:

- `deadlineforyou/main.py`

### 7.1 앱 생명주기

`lifespan()`에서 생성되는 것:

1. `Settings`
2. `Database`
3. `LLMProvider`
4. `DeadlineCoachService`

서비스는 `app.state.service`에 저장된다.

### 7.2 엔드포인트

- `GET /health`
- `POST /users`
- `POST /projects`
- `GET /users/{user_id}/projects`
- `PATCH /projects/{project_id}`
- `POST /chat`
- `POST /translate`
- `POST /images/generate`
- `POST /sessions`
- `GET /sessions/{session_id}`
- `POST /sessions/{session_id}/complete`
- `GET /users/{user_id}/daily-report`
- `GET /meta/providers`

### 7.3 `/chat` 특징

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

`executed_tools`는 내부 tool calling 루프에서 실제 실행된 도구 이름 목록이다.

## 8. 데이터베이스 구조

저장소 파일:

- `deadlineforyou/storage.py`

DB 엔진:

- SQLite

테이블:

### users

- `id`
- `platform_user_id`
- `nickname`
- `timezone`
- `tone_preference`
- `created_at`

특징:

- `platform_user_id`는 unique
- Telegram 사용자는 `telegram-{telegram_user_id}` 형식

### projects

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

특징:

- 활성 프로젝트는 `status='active'`
- 텔레그램에서는 active 프로젝트를 기본 대상으로 사용

### sessions

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

### messages

- `id`
- `user_id`
- `project_id`
- `role`
- `content`
- `created_at`

용도:

- 최근 대화 이력 재주입

### avoidance_events

- `id`
- `user_id`
- `project_id`
- `trigger_text`
- `category`
- `severity`
- `created_at`

용도:

- 회피 누적 횟수 집계
- 일일 리포트 보강
- 코칭 모드 판정 강화

## 9. 도메인 구조

정의 파일:

- `deadlineforyou/domain.py`

### CoachingMode

- `default`
- `reality_check`
- `force_start`
- `cold_support`
- `boss_mode`

### SessionStatus

- `active`
- `completed`
- `cancelled`
- `expired`

### RuleEvaluation

포함 필드:

- `mode`
- `urgency_score`
- `avoidance_hits`
- `timer_minutes`
- `action_hint`
- `report_hint`

## 10. 규칙 엔진 구조

파일:

- `deadlineforyou/rules.py`

역할:

- 회피 표현 감지
- 마감 압박 계산
- 코칭 모드 선택
- 기본 타이머 길이 제안

주요 감지 표현:

- `하기 싫`
- `귀찮`
- `나중`
- `내일`
- `졸려`
- `피곤`
- `유튜브`
- `도망`
- `못 하겠`

기본 판정:

- 마감 6시간 이내면 `boss_mode`
- 강한 회피는 `force_start`
- 피로 표현은 `cold_support`
- 누적 회피가 많으면 `reality_check`

## 11. 프롬프트 구조

파일:

- `deadlineforyou/prompts.py`

핵심:

- `SYSTEM_PROMPT`
- `build_context_block(...)`

`SYSTEM_PROMPT`는 `締切監督` 페르소나 정의를 담고, `build_context_block`은 아래 정보를 텍스트 블록으로 조립한다.

- 사용자 상태
- 프로젝트 상태
- 규칙 엔진 힌트

## 12. Provider 구조

파일:

- `deadlineforyou/providers.py`

### 12.1 코칭 provider

공통 인터페이스:

- `LLMProvider`

구현체:

- `LocalLLMProvider`
- `ScriptedFallbackProvider`

`LocalLLMProvider` 특징:

- `saya_rp_4b_v3` 사용
- 필요하면 `qwen3_4b_instruct` 같은 대체 Qwen 체크포인트로 교체 가능
- `Qwen` 계열 chat template 적용
- tool calling 결과 파싱 지원

### 12.2 번역 provider

공통 인터페이스:

- `TranslationProvider`

구현체:

- `LazyLocalTranslationProvider`
- `InheritedTranslationProvider`
- `ScriptedTranslationProvider`

현재 기본 번역 provider:

- `rosetta_4b`

특징:

- lazy loading
- `Gemma3` 계열 체크포인트 대응
- tokenizer fallback 포함
- `token_type_ids` 제거 처리 포함

### 12.3 이미지 provider

공통 인터페이스:

- `ImageProvider`

구현체:

- `LocalSDXLTurboProvider`
- `NullImageProvider`

현재 기본 이미지 provider:

- `SDXL-Turbo`

특징:

- lazy loading
- 생성 후 unload 가능
- CPU offload 지원
- 기본 생성값: `512x512`, `4 step`

## 13. 서비스 계층 구조

파일:

- `deadlineforyou/service.py`

`DeadlineCoachService` 역할:

- 데이터 조회 / 저장
- 회피 이벤트 기록
- 규칙 엔진 호출
- 프롬프트 컨텍스트 구성
- provider 호출
- 세션 / 리포트 집계

### 13.1 주요 메서드

- `create_user`
- `get_or_create_user`
- `create_project`
- `list_projects`
- `update_project`
- `start_session`
- `complete_session`
- `get_session`
- `get_active_project`
- `chat`
- `build_daily_report`
- `translate_text`
- `generate_image`

### 13.2 `chat()` 흐름

1. 활성 프로젝트 조회
2. 최근 회피 이벤트 조회
3. 규칙 평가
4. 회피 이벤트 저장
5. 최근 메시지 이력 조회
6. 사용자 / 프로젝트 / 규칙 스냅샷 구성
7. 컨텍스트 블록 생성
8. 사용자 메시지 저장
9. 내부 tool registry 구성
10. provider 호출
11. tool call 있으면 실행 후 다시 provider 호출
12. 최종 답변 저장

즉, 단순 LLM 호출이 아니라 상태 기반 루프다.

## 14. 내부 tool calling 구조

파일:

- `deadlineforyou/tools.py`

용도:

- 코칭 모델이 내부 도구를 호출할 수 있게 함

현재 채팅 바인딩 도구 예:

- `get_active_project`
- `list_projects`
- `start_focus_session`
- `complete_focus_session`
- `get_daily_report`
- `translate_text`
- `generate_image`

이 구조는 외부 프로토콜용이 아니라, 현재 서비스 내부 루프 전용이다.

## 15. Telegram bot 구조

파일:

- `deadlineforyou/telegram_bot.py`

실행 방식:

- polling

### 15.1 시작 시 구성

`build_application()`에서:

1. 텔레그램 토큰 확인
2. `Application` 생성
3. 공용 `DeadlineCoachService` 생성
4. 명령 핸들러 등록
5. 에러 핸들러 등록

### 15.2 명령

- `/start`
- `/help`
- `/deadline_add`
- `/deadline_list`
- `/status`
- `/translate`
- `/image`
- `/start10`
- `/start15`
- `/pomodoro`
- `/report`

### 15.3 버튼 UX

하단 키보드는 혼합 구조다.

- 즉시 실행 버튼
  - `/deadline_list`
  - `/status`
  - `/help`
  - `/start10`
  - `/start15`
  - `/pomodoro`
- 안내 버튼
  - `프로젝트 등록 양식`
  - `번역 양식`
  - `이미지 양식`

안내 버튼을 누르면 예시 커맨드를 메시지로 보내준다.  
입력창 자동 채우기는 일반 텔레그램 봇에서 지원하지 않기 때문에 현재 구조는 `예시 안내 -> 복사 수정` 흐름이다.

### 15.4 안정성 처리

- 로컬 무거운 작업은 `asyncio.to_thread(...)` 사용
- 이미지 업로드 timeout 확장
- `sendPhoto` timeout 시 파일 경로를 텍스트로 반환
- 전역 에러 핸들러에서 사용자 메시지와 로그를 남김

### 15.5 세션 알림

`JobQueue` 사용 시:

- 세션 종료 후 `/report` 유도 메시지 전송

주의:

- 프로세스 재시작 시 메모리 기반 예약은 사라질 수 있다.

## 16. 사용자 흐름

### 16.1 API 흐름

```text
POST /users
 -> POST /projects
 -> POST /chat
 -> POST /sessions
 -> POST /sessions/{id}/complete
 -> GET /users/{id}/daily-report
```

### 16.2 Telegram 흐름

```text
/start
 -> 프로젝트 등록 양식 버튼 확인
 -> /deadline_add ...
 -> /status
 -> /start10
 -> /report 8
 -> 필요하면 /translate ...
 -> 필요하면 /image ...
```

### 16.3 이미지 생성 흐름

```text
/image or POST /images/generate
 -> 필요 시 번역 모델 unload
 -> SDXL-Turbo lazy load
 -> 이미지 생성
 -> PNG 저장
 -> Telegram 전송 또는 file_path 반환
 -> 필요 시 이미지 모델 unload
```

## 17. 현재 장점

- API와 Telegram이 같은 서비스 계층을 공유한다.
- 코칭 / 번역 / 이미지 provider를 분리해 메모리 제어가 가능하다.
- SQLite 하나로 상태를 단순하게 관리한다.
- 규칙 엔진과 생성 모델을 결합해 말투와 행동 지시를 분리한다.

## 18. 현재 한계

- SQLite 기반이라 단일 인스턴스 운영에 가깝다.
- 텔레그램 입력창 자동 채우기는 지원하지 않는다.
- 로컬 이미지 생성은 여전히 느릴 수 있다.
- Telegram JobQueue 알림은 프로세스 재시작에 취약하다.
- 번역 모델 로딩은 체크포인트 특성상 환경 차이에 민감하다.

## 19. 운영 시 권장 사항

- GPU 메모리가 빡빡하면 API와 Telegram을 동시에 띄우지 않는다.
- 이미지 테스트는 `512x512`, `4 step` 기본값을 유지한다.
- 텔레그램 사용자 경험 설명은 `/help`에 모으고, 버튼은 빠른 진입용으로만 쓴다.
