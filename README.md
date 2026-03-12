![DeadlineForYou banner](assets/banner.svg)

# DeadlineForYou

`DeadlineForYou`는 프리랜서 번역가를 다시 작업 화면으로 밀어 넣는 로컬 마감 집행 시스템이다.  
핵심 캐릭터는 마감 집행관 `締切監督`이고, 목표는 위로가 아니라 `즉시 착수`다.

현재 구현 범위:

- FastAPI 백엔드
- Telegram bot 어댑터
- SQLite 저장소
- 로컬 코칭 모델
- 로컬 번역 모델
- 로컬 이미지 생성 모델
- 내부 tool calling 루프

## 구성 요약

- 코칭 모델: `deadlineforyou/models/saya_rp_4b_v3`
- 대체 코칭 모델: `deadlineforyou/models/qwen3_4b_instruct`
- 번역 모델: `deadlineforyou/models/rosetta_4b`
- 이미지 모델: `deadlineforyou/models/sdxl_turbo`
- 테스트 fallback: `scripted`

기본 구조:

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

## 설치

```bash
cd /home/hosung/pytorch-demo/DeadlineForYou
uv venv
source .venv/bin/activate
uv pip install -e .
cp .env.example .env
```

모델이 아직 없으면 먼저 받는다.

```bash
uv run initialize.py
uv run initialize.py --target image
```

`initialize.py` 기본 동작:

- `coach`: `ahnhs2k/saya_rp_4b_v3`
- `translation`: `yanolja/YanoljaNEXT-Rosetta-4B`

대체 코칭 모델을 받고 싶으면:

```bash
uv run initialize.py --target coach_qwen
```

- `coach_qwen`: `Qwen/Qwen3-4B-Instruct-2507`

이미지 모델은 선택적으로 추가 다운로드:

- `image`: `stabilityai/sdxl-turbo`

## 실행

### API 서버

```bash
uv run uvicorn deadlineforyou.main:app --reload
```

접속 주소:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

### Telegram bot

`.env`에 텔레그램 토큰을 넣는다.

```env
DFY_TELEGRAM_BOT_TOKEN=123456:ABC...
```

실행:

```bash
uv run python -m deadlineforyou.telegram_bot
```

주의:

- API와 Telegram bot은 각각 단독 실행 가능하다.
- 둘 다 같은 SQLite 파일을 공유한다.
- 이미지 생성까지 같이 쓰면 GPU 메모리가 빠듯할 수 있다.

## 환경 변수

기본 핵심 설정:

```env
DFY_DATABASE_PATH=data/deadlineforyou.db

DFY_LLM_PROVIDER=local
DFY_LOCAL_MODEL_PATH=deadlineforyou/models/saya_rp_4b_v3
DFY_LOCAL_DEVICE_MAP=auto
DFY_LOCAL_MAX_NEW_TOKENS=220
DFY_LOCAL_TEMPERATURE=0.7

DFY_TRANSLATION_PROVIDER=local
DFY_TRANSLATION_LOCAL_MODEL_PATH=deadlineforyou/models/rosetta_4b
DFY_TRANSLATION_LAZY_LOAD=true
DFY_TRANSLATION_LOCAL_MAX_NEW_TOKENS=256
DFY_TRANSLATION_LOCAL_TEMPERATURE=0.2

DFY_IMAGE_PROVIDER=local
DFY_IMAGE_LOCAL_MODEL_PATH=deadlineforyou/models/sdxl_turbo
DFY_IMAGE_LAZY_LOAD=true
DFY_IMAGE_UNLOAD_AFTER_GENERATION=true
DFY_IMAGE_ENABLE_MODEL_CPU_OFFLOAD=true
DFY_IMAGE_RELEASE_TRANSLATION_BEFORE_GENERATION=true
DFY_IMAGE_DEVICE=cuda
DFY_IMAGE_NUM_INFERENCE_STEPS=4
DFY_IMAGE_GUIDANCE_SCALE=0.0
DFY_IMAGE_OUTPUT_DIR=data/generated_images
```

지원 provider:

- 코칭: `local`, `scripted`
- 번역: `local`, `scripted`, `inherit`
- 이미지: `local`, `none`

## 메모리 전략

현재 구조는 메모리 절약을 위해 기능별 provider를 분리했다.

- 코칭 모델은 시작 시 로드
- 번역 모델은 첫 번역 요청 시 lazy loading
- 이미지 모델은 첫 이미지 요청 시 lazy loading
- 이미지 생성 전 번역 모델을 먼저 unload 가능
- 이미지 생성 후 이미지 모델을 unload 가능

권장:

- 이미지 생성 테스트 중엔 API와 Telegram을 동시에 띄우지 않는 편이 안전하다.
- `SDXL-Turbo`는 `512x512`, `4 step` 기본값으로 둔다.

## 시스템이 어떻게 동작하는가

이 시스템은 단순한 채팅 봇이 아니다.  
현재 프로젝트 상태와 최근 대화를 같이 보고, 지금 바로 할 행동을 정한다.

기본 흐름:

1. 사용자 메시지를 받는다.
2. 현재 활성 프로젝트를 찾는다.
3. 남은 분량과 마감 시각을 확인한다.
4. 최근 대화와 프로젝트 상태를 프롬프트에 넣는다.
5. `締切監督`가 답변을 생성한다.
6. 필요하면 내부 도구를 호출해 세션 시작, 번역, 이미지 생성, 리포트 조회를 수행한다.

즉, 이 시스템은 `대화 + 상태 확인 + 행동 지시 + 기록`을 한 번에 묶어 둔 구조다.

## 핵심 사용 흐름

가장 기본적인 사용 순서는 이렇다.

1. 프로젝트 등록
2. `/status`로 현재 상태 확인
3. `/timer <분>`으로 작업 세션 시작
4. 세션 도중 10분마다 압박 메시지 수신
5. 세션 종료 후 `/report <작업량>`으로 완료 보고
6. 봇이 다음 지시를 다시 내림

프로젝트 등록은 두 방식 모두 가능하다.

- 명령으로 등록: `/deadline_add 게임 시나리오 번역 | jp | ko | 120 | 2026-03-14 18:00 | 문장`
- 줄만 보내서 등록: `게임 시나리오 번역 | jp | ko | 120 | 2026-03-14 18:00 | 문장`

지원 언어 코드는 `ko`, `jp`, `en`, `ch`만 받는다.  
`ja`는 `jp`, `zh`와 `cn`은 `ch`로 자동 정규화한다.

프로젝트 등록 항목 뜻:

- `게임 시나리오 번역`: 프로젝트 제목
- `jp`: 원문 언어
- `ko`: 목표 언어
- `120`: 프로젝트 전체 분량
- `2026-03-14 18:00`: 이 프로젝트의 최종 마감 시각
- `문장`: 분량 단위

즉 여기 들어가는 시간은 `/timer` 시간이 아니라 `프로젝트 마감 시간`이다.

## 타이머와 보고 구조

수동 세션은 `/timer <분>` 하나만 쓴다.

예:

- `/timer 10`
- `/timer 25`
- `/timer 45`

동작:

1. 지정한 분 수로 세션 생성
2. 세션이 10분 이상이면 10분마다 압박 메시지 전송
3. 세션 종료 시 `/report <작업량>` 보고 요청
4. 사용자가 보고하지 않으면 10분마다 다시 재촉
5. 사용자가 `/report`를 보내면 완료량이 프로젝트에 반영되고 다음 지시가 생성됨

`/report` 숫자 뜻:

- `/report 8`이면 이번 세션에서 `8단위`를 끝냈다는 뜻이다.
- 여기서 단위는 프로젝트 등록 때 넣은 `문장`, `페이지`, `줄` 같은 단위다.
- 숫자가 없으면 완료 보고로 처리하지 않는다.

중요한 점:

- 예전의 `/start10`, `/start15`, `/pomodoro` 같은 고정 명령은 없다.
- 사용자는 그냥 몇 분 할지만 정하면 된다.
- 중간 압박과 미보고 재촉도 지금은 LLM이 만든다.

## 코칭 모델은 언제 호출되는가

코칭 모델은 아래 경우에만 호출된다.

- 일반 텔레그램 대화
- API `POST /chat`
- 10분 진행 알림
- 세션 종료 후 미보고 재촉
- `/report` 후 다음 지시 생성

반대로 코칭 모델을 쓰지 않는 곳:

- `/timer` 시작 확인
- `/status`
- `/deadline_add`, `/deadline_list`
- `/translate`
- `/image`

즉, 코칭 모델은 평상 대화만이 아니라 `압박 메시지`와 `다음 지시` 생성에도 들어간다.

## 번역과 이미지 생성

이 시스템은 코칭 외에도 짧은 번역과 이미지 생성을 처리할 수 있다.

### 번역

- Telegram: `/translate <원문언어> | <목표언어> | <원문>`
- API: `POST /translate`

코칭 모델과 별도로 `rosetta_4b`를 사용한다.

### 이미지 생성

- Telegram: `/image <프롬프트>`
- API: `POST /images/generate`

이미지 요청은 `sdxl_turbo`를 사용한다.  
텔레그램 자연어 대화에서 이미지 생성 도구가 실행되면, 파일 경로만 보내는 게 아니라 실제 이미지를 업로드한다.

## 텔레그램 사용법

`/start`를 누르면 하단 버튼이 보인다.

현재 버튼:

1. `프로젝트 등록 양식`
2. `/deadline_list`
3. `/status`
4. `/help`
5. `타이머 시작 양식`
6. `/report`
7. `번역 양식`
8. `이미지 양식`

버튼은 두 종류다.

- 바로 실행하는 버튼: `/deadline_list`, `/status`, `/help`, `/report`
- 예시를 보여주는 버튼: `프로젝트 등록 양식`, `타이머 시작 양식`, `번역 양식`, `이미지 양식`

예시 버튼은 직접 실행하지 않고 형식을 보여준다.  
사용자는 그 예시를 복사해서 필요한 부분만 바꿔 보내면 된다.

처음 쓰는 사람 기준으로는 이렇게 보면 된다.

- `프로젝트 등록 양식`: 프로젝트 추가 예시 한 줄을 보여준다.
- `/deadline_list`: 내가 등록한 프로젝트 목록을 보여준다.
- `/status`: 현재 활성 프로젝트와 오늘 작업량을 보여준다.
- `/help`: 전체 사용법을 다시 보여준다.
- `타이머 시작 양식`: `/timer` 예시를 보여준다.
- `/report`: 완료 보고 명령 설명을 보여준다. 직접 누르는 버튼이라기보다 사용법 확인용에 가깝다.
- `번역 양식`: `/translate` 예시를 보여준다.
- `이미지 양식`: `/image` 예시를 보여준다.

예:

- 프로젝트 등록 양식 -> `/deadline_add 게임 시나리오 번역 | jp | ko | 120 | 2026-03-14 18:00 | 문장`
- 또는 -> `게임 시나리오 번역 | jp | ko | 120 | 2026-03-14 18:00 | 문장`
- 타이머 시작 양식 -> `/timer 25`
- 번역 양식 -> `/translate jp | en | 締切は明日の18時です。`
- 이미지 양식 -> `/image deadline enforcer poster, black and orange warning stripes`

## API 사용

주요 엔드포인트:

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

Swagger UI에서 추천 실험 순서:

1. `POST /users`
2. `POST /projects`
3. `POST /chat`
4. `POST /sessions`
5. `POST /sessions/{session_id}/complete`
6. `GET /users/{user_id}/daily-report`

## `/chat` 응답

`POST /chat` 응답에는 아래 정보가 들어간다.

- `reply`
- `timer_minutes`
- `executed_tools`
- `tool_results`

`executed_tools`는 내부에서 실제 실행된 도구 이름 목록이다.  
`tool_results`는 번역, 이미지 생성 같은 도구 실행 결과를 담는다.

## 일일 리포트

현재 일일 리포트는 단순하다.

- 집중 시간
- 완료량

즉, 지금 구조는 복잡한 심리 통계보다 `오늘 몇 분 했고 얼마나 끝냈는지`에 집중한다.

## 현재 제약

- 텔레그램 일반 버튼은 입력창 자동 채우기를 지원하지 않는다.
- 로컬 이미지 생성은 여전히 느릴 수 있다.
- 번역과 이미지 모델은 처음 호출 시 로딩 시간이 있다.
- 로컬 모델 세 개를 한꺼번에 강하게 쓰면 GPU 메모리가 빡빡할 수 있다.

## 관련 문서

- 구현 구조: [deadlineforyou/architecture.md](deadlineforyou/architecture.md)
- 제품 설계 개요: [blueprint.md](blueprint.md)
- 설치/에이전트 도구 문서: [docs/opencode.md](docs/opencode.md)
