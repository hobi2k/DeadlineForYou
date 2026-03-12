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

이 문서는 아이디어 문서가 아니라, 지금 코드가 실제로 어떻게 돌아가는지 정리한 구현 문서다.

## 2. 시스템 개요

`DeadlineForYou`는 프리랜서 번역가의 프로젝트 상태를 보면서 즉시 행동 지시를 내리는 로컬 마감 집행 시스템이다.

핵심 동작:

1. 사용자 메시지 수신
2. 현재 활성 프로젝트 조회
3. 최근 대화와 프로젝트 상태 조합
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
         +─ Prompt Builder
         +─ Local Coach Provider
         +─ Local Translation Provider
         +─ Local Image Provider
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
- `prompts.py`: 시스템 프롬프트와 컨텍스트 조립
- `providers.py`: 코칭 / 번역 / 이미지 provider
- `tools.py`: 내부 tool registry
- `schemas.py`: API 요청 / 응답 스키마
- `domain.py`: dataclass 등 도메인 타입
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
- 프로젝트 등록 명령 처리
- 타이머 시작 / 보고 처리
- 코칭 / 번역 / 이미지 생성 호출
- 10분 진행 압박과 미보고 재촉 스케줄링

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
- `timer_minutes`
- `executed_tools`
- `tool_results`

`executed_tools`는 내부 tool calling 루프에서 실제 실행된 도구 이름 목록이다.  
`tool_results`는 번역, 이미지 생성 같은 실행 결과를 담는다.

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

`mode` 컬럼은 현재 사실상 `timer` 값을 저장하는 단순 구분용이다.

### messages

- `id`
- `user_id`
- `project_id`
- `role`
- `content`
- `created_at`

용도:

- 최근 대화 이력 재주입

## 9. 서비스 계층 구조

핵심 파일:

- `deadlineforyou/service.py`

`DeadlineCoachService`의 역할:

- 사용자와 프로젝트 조회
- 최근 대화 기록 적재
- 권장 타이머 계산
- 코칭 프롬프트 조립
- 내부 tool 실행 루프 처리
- 번역 / 이미지 생성 오케스트레이션
- 세션 완료 후 진행량 반영

## 10. 권장 타이머 계산

현재 권장 타이머 계산은 `service.py` 내부에서 직접 처리한다.

입력:

- 활성 프로젝트의 마감 시각
- 총량 대비 완료량

출력:

- `timer_minutes`

기본 기준:

- 마감이 `6시간 이하`면 `25`
- 완료율이 낮으면 `15`
- 그 외는 `10`

중요:

- 회피 패턴 매칭은 더 이상 없다.
- 긴급도 점수도 없다.
- 복잡한 모드 분기는 없다.
- 사용자의 저항감이나 피로감은 LLM이 대화 문맥으로 직접 판단한다.

## 11. 프롬프트 구조

핵심 파일:

- `deadlineforyou/prompts.py`

프롬프트에 들어가는 정보:

- 시스템 페르소나
- 현재 프로젝트 상태
- 남은 분량
- 최근 대화
- 권장 타이머
- 필요한 경우 tool 사용 지시

프롬프트는 `締切監督` 톤을 유지하되, 답변 끝을 행동 지시로 마무리하도록 유도한다.

## 12. Provider 구조

핵심 파일:

- `deadlineforyou/providers.py`

현재 provider는 세 갈래다.

### 12.1 코칭 provider

역할:

- 일반 대화 응답 생성
- 10분 진행 압박 생성
- 미보고 재촉 생성
- `/report` 이후 다음 지시 생성

기본 모델:

- `saya_rp_4b_v3`

대체 모델:

- `Qwen3-4B-Instruct-2507`

### 12.2 번역 provider

역할:

- `/translate`
- API `POST /translate`
- 내부 tool calling 번역 호출

기본 모델:

- `rosetta_4b`

특징:

- lazy loading
- 코칭 모델과 분리

### 12.3 이미지 provider

역할:

- `/image`
- API `POST /images/generate`
- 내부 tool calling 이미지 호출

기본 모델:

- `sdxl_turbo`

특징:

- lazy loading
- 생성 후 unload 가능
- CPU offload 지원

## 13. 내부 Tool Calling

핵심 파일:

- `deadlineforyou/tools.py`

현재 내부 tool 예시:

- 활성 프로젝트 조회
- 프로젝트 목록 조회
- 일일 리포트 조회
- 번역 실행
- 이미지 생성 실행

역할:

- 대화 모델이 필요할 때 구조화된 함수를 호출
- 텍스트 응답과 실제 작업 실행을 분리

## 14. Telegram bot 구조

핵심 파일:

- `deadlineforyou/telegram_bot.py`

### 14.1 주요 명령

- `/start`
- `/help`
- `/deadline_add`
- `/deadline_list`
- `/status`
- `/timer`
- `/report`
- `/translate`
- `/image`

### 14.2 버튼 구조

현재 버튼:

1. `프로젝트 등록 양식`
2. `/deadline_list`
3. `/status`
4. `/help`
5. `타이머 시작 양식`
6. `/report`
7. `번역 양식`
8. `이미지 양식`

원칙:

- 바로 실행 가능한 기능은 명령 버튼으로 둔다.
- 인자가 필요한 기능은 예시 메시지를 먼저 보여준다.
- 사용자는 그 예시를 복사해 수정해서 보낸다.
- 자세한 설명은 `/help`에 모은다.

프로젝트 등록은 두 경로를 모두 지원한다.

- `/deadline_add ...` 명령으로 등록
- `제목 | 원문 언어 | 목표 언어 | 총량 | 마감 | 단위` 형식의 일반 텍스트를 그대로 보내서 등록

지원 언어 코드는 `ko`, `jp`, `en`, `ch`만 허용한다.

### 14.3 타이머 동작

- `/timer <분>`으로 세션 시작
- 세션이 10분 이상이면 10분마다 진행 압박 메시지 전송
- 세션 종료 시 보고 요청
- 사용자가 제때 `/report`를 보내지 않으면 세션을 자동으로 `0` 완료 처리
- 자동 `0` 처리 후에는 새 `/timer <분>` 을 다시 시작하라고 재촉
- `/report`는 숫자 인자를 필수로 받는다.

진행 압박과 자동 `0` 처리 후 재시작 재촉은 현재 고정 문자열이 아니라 코칭 모델이 생성한다.

### 14.4 텔레그램 자연어 대화

일반 텍스트가 들어오면:

1. `service.chat()` 호출
2. 내부 tool이 실행될 수 있음
3. 번역 tool 결과가 있으면 번역 결과만 출력
3. 이미지 생성 tool 결과가 있으면 실제 사진 먼저 업로드
4. 이미지 요청인데 tool 호출이 실패하면 파일 경로나 헛응답 대신 재시도 안내 출력
5. 그 외에는 코치 텍스트 응답 전송

## 15. 번역 흐름

### Telegram

1. `/translate <원문언어> | <목표언어> | <원문>` 수신
2. 번역 provider 호출
3. 번역 결과 텍스트 반환

### API

1. `POST /translate`
2. 번역 provider 호출
3. JSON 응답 반환

## 16. 이미지 생성 흐름

### Telegram

1. `/image <프롬프트>` 수신
2. 생성 시작 안내 메시지 전송
3. 이미지 provider 호출
4. 생성 완료 후 실제 사진 업로드
5. 업로드 timeout 시 파일 경로 텍스트 fallback

### 자연어 tool 호출

1. 사용자가 일반 대화에서 이미지 생성을 요청
2. 내부 tool이 `generate_image` 실행
3. `tool_results`에 파일 경로 저장
4. Telegram 핸들러가 실제 이미지를 업로드

중요:

- 일반 대화의 번역/이미지 판단은 텔레그램 정규식이 아니라 LLM tool calling이 맡는다.
- 텔레그램은 tool 결과를 후처리하는 역할만 한다.

### API

1. `POST /images/generate`
2. 이미지 provider 호출
3. 생성 파일 경로와 메타데이터 반환

## 17. 일일 리포트

현재 리포트는 단순하다.

반환 정보:

- 날짜
- 집중 시간
- 완료량
- 요약 문장

즉, 복잡한 심리 통계 대신 실제 작업량 위주로 정리한다.

## 18. 현재 제약

- 텔레그램 일반 버튼은 입력창 자동 채우기를 지원하지 않는다.
- 로컬 번역과 이미지 생성은 첫 호출 시 로딩 시간이 있다.
- 로컬 이미지 생성은 여전히 느릴 수 있다.
- API와 Telegram을 동시에 띄우고 이미지까지 쓰면 메모리가 빡빡해질 수 있다.

## 19. 운영 포인트

- 실제 사용 채널은 Telegram이다.
- 기능 확인과 디버깅 채널은 FastAPI Swagger다.
- 코칭은 LLM이 대화 맥락으로 판단하고, 코드 쪽은 프로젝트 상태와 세션 루프를 관리한다.
- 타이머 이후 재촉 루프가 핵심 사용 흐름이다.
