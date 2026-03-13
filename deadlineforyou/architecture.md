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
- 파일 기반 작업 추적
- 자동 작업량 계산과 플래너
- 번역 / 이미지 / 파일 번역 보조 흐름

## 2. 시스템 개요

`DeadlineForYou`는 프리랜서 번역가의 프로젝트, 파일, 세션 상태를 보면서 즉시 행동 지시를 내리는 로컬 마감 집행 시스템이다.

핵심 동작:

1. 사용자 메시지 수신
2. 활성 프로젝트 조회
3. 프로젝트 파일과 남은 분량 집계
4. 최근 대화와 상태를 조합해 프롬프트 구성
5. `締切監督` 답변 생성
6. 필요하면 tool calling으로 번역 / 이미지 / 세션 / 조회 도구 실행

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
- 프로젝트는 숫자만이 아니라 파일 단위로 관리한다.

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
- `domain.py`: 공통 타입
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
- 프로젝트 수정 / 삭제 / 전환 처리
- 파일 업로드 처리
- 타이머 시작 / 보고 처리
- 자동 체크인 발송
- 코칭 / 번역 / 이미지 / 파일 보조 번역 호출

### 5.3 공용 의존성

둘 다 공통으로 사용하는 것:

- `Settings`
- `Database`
- `DeadlineCoachService`
- provider 계층

## 6. API 구조

엔드포인트:

- `GET /health`
- `POST /users`
- `POST /projects`
- `GET /users/{user_id}/projects`
- `PATCH /projects/{project_id}`
- `DELETE /projects/{project_id}`
- `GET /projects/{project_id}/overview`
- `GET /projects/{project_id}/planner`
- `GET /projects/{project_id}/workload`
- `POST /project-files`
- `GET /projects/{project_id}/files`
- `PATCH /project-files/{file_id}`
- `POST /project-files/{file_id}/assist-translation`
- `POST /chat`
- `POST /translate`
- `POST /images/generate`
- `POST /sessions`
- `GET /sessions/{session_id}`
- `POST /sessions/{session_id}/complete`
- `GET /users/{user_id}/daily-report`
- `GET /meta/providers`

`/chat` 반환:

- `reply`
- `timer_minutes`
- `executed_tools`
- `tool_results`

즉 일반 대화에서도 모델이 번역 / 이미지 tool을 호출하면 API 응답에 그 결과가 같이 들어간다.

## 7. 데이터베이스 구조

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

### project_files

- `id`
- `project_id`
- `name`
- `source_text`
- `translated_text`
- `source_chars`
- `source_lines`
- `source_segments`
- `translated_chars`
- `translated_lines`
- `translated_segments`
- `status`
- `due_at`
- `created_at`
- `updated_at`

이 테이블이 파일 기반 추적의 핵심이다.

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

### messages

- `id`
- `user_id`
- `project_id`
- `role`
- `content`
- `created_at`

### reminder_logs

- `id`
- `user_id`
- `reminder_type`
- `reminder_date`
- `created_at`

이 테이블은 같은 시간대 자동 체크인이 하루에 중복 발송되지 않게 막는다.

## 8. 자동 작업량 계산

`storage.py`의 `_text_metrics()`가 텍스트에서 자동 집계를 만든다.

집계 대상:

- 글자 수
- 줄 수
- 세그먼트 수

적용 지점:

- `create_project_file()`
- `update_project_file()`
- `project_workload_summary()`

파일이 추가되거나 수정되면 `_recalculate_project_progress()`가 파일 세그먼트 합을 프로젝트 `total_units`, `completed_units`에 다시 반영한다.

즉 프로젝트 총량은 파일 집계와 동기화된다.

## 9. 마감 역산 플래너

`service.py`의 `_planner_snapshot()`가 플래너 계산을 담당한다.

입력:

- 프로젝트 총량
- 완료량
- 마감 시각
- 파일 기반 남은 파일 수
- 파일 기반 밀린 파일 수

출력:

- `remaining_units`
- `remaining_days`
- `required_units_per_day`
- `required_units_per_hour`
- `file_backlog_count`
- `delayed_file_count`
- `summary`

이 값은:

- `/status`
- `/deadline_list`
- `/projects/{id}/planner`
- `/projects/{id}/overview`
- LLM 프롬프트의 timer guide

에 사용된다.

## 10. 세션과 리마인더 구조

세션 생성:

- `/timer <분>`
- `POST /sessions`
- `start_focus_session` tool

세션 종료:

- `/report <숫자>`
- `POST /sessions/{id}/complete`
- `complete_focus_session` tool

리마인더 흐름:

1. 세션이 10분 이상이면 10분마다 진행 압박
2. 세션 종료 시 미보고면 `AUTO_REPORT_0`으로 자동 마감
3. 자동 마감 후 새 `/timer` 시작 재촉
4. `CHECKIN_HOURS = (10, 15, 21)` 기준 자동 체크인

자동 체크인은 `telegram_bot.py`의 `send_daily_checkin()`에서 돈다.

## 11. Telegram 구조

핵심 명령:

- `/start`
- `/help`
- `/deadline_add`
- `/deadline_update`
- `/deadline_delete`
- `/deadline_list`
- `/deadline_switch`
- `/status`
- `/timer`
- `/report`
- `/translate`
- `/image`
- `/file_assist`

버튼:

- `프로젝트 등록 양식`
- `프로젝트 수정 양식`
- `프로젝트 삭제 양식`
- `프로젝트 목록`
- `프로젝트 전환 양식`
- `현재 상태`
- `타이머 시작 양식`
- `작업 보고 안내`
- `번역 양식`
- `이미지 양식`
- `파일 번역 보조 양식`
- `도움말`

일반 텍스트 처리:

1. 버튼 라벨 메시지인지 확인
2. 프로젝트 등록 형식인지 확인
3. 아니면 `service.chat()`로 전달
4. LLM이 tool calling을 하면 tool 결과 후처리
5. 번역이면 번역 결과만 보냄
6. 이미지면 실제 이미지를 업로드
7. 그 외엔 코치 텍스트 전송

문서 업로드 처리:

- `filters.Document.ALL`
- 현재는 `.txt` 중심
- 활성 프로젝트가 있어야 등록
- 업로드 직후 파일 ID와 자동 집계 결과를 알려줌

## 12. Service 계층

핵심 클래스:

- `DeadlineCoachService`

주요 메서드:

- `chat()`
- `coach_nudge()`
- `create_project()`
- `create_project_file()`
- `list_project_files()`
- `update_project_file()`
- `project_workload_summary()`
- `build_project_planner()`
- `build_project_overview()`
- `assist_file_translation()`
- `translate_text()`
- `generate_image()`

`chat()` 역할:

1. 활성 프로젝트 조회
2. 권장 타이머 계산
3. 프로젝트 / 파일 / 플래너 스냅샷 생성
4. 최근 대화 불러오기
5. tool registry 구성
6. provider 호출
7. tool loop 수행
8. 최종 답변 및 tool 결과 반환

## 13. Tool calling 구조

tool 정의 위치:

- `deadlineforyou/tools.py`

현재 핵심 tool:

- `get_active_project`
- `start_focus_session`
- `complete_focus_session`
- `get_daily_report`
- `list_projects`
- `get_project_overview`
- `translate_text`
- `generate_image`
- `assist_file_translation`

일반 대화의 번역 / 이미지 / 파일 보조 번역 요청은 이 tool 집합을 통해 처리된다.

## 14. Provider 구조

provider 정의 위치:

- `deadlineforyou/providers.py`

역할 분리:

- 코칭 provider
- 번역 provider
- 이미지 provider

메모리 전략:

- 코칭 모델은 상주
- 번역 모델은 lazy loading
- 이미지 모델은 lazy loading
- 이미지 생성 후 unload 가능
- 이미지 생성 전 번역 모델 unload 가능

## 15. 현재 한계

- 텔레그램 파일 업로드는 현재 `.txt` 중심이다.
- 파일 번역 보조는 현재 업로드된 파일의 앞부분 최대 `1500자`를 번역해서 `.txt` 결과물로 돌려준다.
- 프로젝트 등록 자체는 아직 텍스트 입력 기반이고, 완전한 버튼형 입력 폼은 아니다.
- 자동 체크인은 봇 프로세스가 떠 있어야 동작한다.

## 16. 확장 포인트

- 더 많은 파일 포맷 지원
- 용어집 / 스타일가이드
- 프로젝트별 주간 리포트
- 웹 대시보드
