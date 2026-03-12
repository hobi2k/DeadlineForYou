![DeadlineForYou banner](assets/banner.svg)

# DeadlineForYou

`DeadlineForYou`는 프리랜서 번역가를 작업 화면으로 다시 밀어 넣는 로컬 마감 집행 시스템이다.  
핵심 캐릭터는 마감 집행관 `締切監督`이며, 목표는 위로가 아니라 `즉시 착수`다.

현재 구현 범위:

- FastAPI 백엔드
- Telegram bot 어댑터
- SQLite 저장소
- 상태 기반 코칭 채팅
- 내부 tool calling 루프
- 프로젝트 등록 / 수정 / 조회
- 작업 세션 시작 / 완료 / 일일 리포트
- 로컬 번역 모델 연동
- 로컬 이미지 생성 모델 연동

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
         +─ Rule Engine
         +─ Prompt Builder
         +─ Local Providers
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

`DeadlineForYou`는 단순한 채팅 봇이 아니다.  
사용자 메시지, 프로젝트 마감, 현재 진행률, 오늘 회피 횟수를 같이 보고 다음 행동을 정한다.

기본 흐름:

1. 사용자 메시지를 받는다.
2. 현재 활성 프로젝트를 찾는다.
3. 회피 표현이 있는지 감지한다.
4. 마감까지 남은 시간과 진행률을 계산한다.
5. 규칙 엔진이 현재 코칭 모드를 고른다.
6. `締切監督` 페르소나가 그 모드에 맞는 답변을 만든다.
7. 필요하면 내부 도구를 호출해 세션 시작, 리포트 조회, 번역, 이미지 생성을 수행한다.

즉, 이 시스템은 `대화 + 상태판단 + 행동 지시 + 기록`을 한 번에 묶어 둔 구조다.

## 코칭 응답은 이렇게 달라진다

현재 시스템은 복잡한 모드 이름을 드러내지 않는다.  
대신 상황에 따라 답변 강도와 권장 타이머가 달라진다.

대표적으로:

- 마감이 멀면 짧은 착수 지시
- 회피 표현이 강하면 더 작은 작업 단위 제시
- 피로 표현이 있으면 조금 더 짧고 복구 중심의 지시
- 마감이 `6시간 이하`면 더 강한 압박과 `25분` 권장 타이머

즉, 사용자가 외워야 하는 건 모드 이름이 아니라 `지금 바로 뭘 하면 되는지`다.

## 자동 응답 규칙

현재 규칙 엔진 기준으로는 아래처럼 동작한다.

- 마감 `6시간 이하`면 더 강한 압박 답변과 `25분` 권장 타이머
- 회피 표현이 강하면 더 작은 행동 단위를 제시
- 피로 표현이면 조금 더 짧은 복구형 지시를 제시
- 오늘 회피 기록이 많으면 현실적인 경고를 더 강하게 붙인다

즉, 사용자가 어떤 기분인지뿐 아니라 `실제 마감 압박`도 같이 본다.

## 세션은 `/timer` 하나로 쓴다

수동 세션은 고정 명령 여러 개 대신 `/timer <분>` 하나로 정리했다.

예:

- `/timer 10`
- `/timer 25`
- `/timer 45`

동작:

1. 지정한 분 수로 세션 생성
2. 시간이 끝나면 알림 전송
3. 사용자는 `/report <작업량>`으로 결과 보고
4. 보고 숫자가 프로젝트 진행량에 반영

사용 기준:

- 빨리 착수만 만들고 싶다 -> `/timer 10`
- 보통 집중 블록이 필요하다 -> `/timer 25`
- 길게 몰아치고 싶다 -> `/timer 45`

중요한 점:

- 이제 예전의 고정 타이머 명령을 외울 필요가 없다.
- 수동 세션은 그냥 “몇 분 할지”만 정하면 된다.
- 긴 세션은 내부적으로 더 강한 세션 모드로 저장될 수 있지만, 사용자 입장에서는 `/timer`만 쓰면 된다.

## 텔레그램 버튼을 왜 이렇게 만들었는가

하단 버튼은 두 역할로 나뉜다.

- 즉시 실행 버튼
- 양식 안내 버튼

인자가 필요한 명령은 입력창 자동 채우기가 아니라 예시 메시지를 보여준다.  
이건 현재 텔레그램 일반 봇의 UI 제약 때문이다.

현재 안내 버튼:

- `프로젝트 등록 양식`
- `번역 양식`
- `이미지 양식`

버튼을 누르면 “이 형식으로 보내라”는 예시가 오고, 사용자는 그 줄을 복사해서 수정해 보내는 구조다.

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

`POST /chat` 응답에는 `executed_tools`가 포함될 수 있다.  
이 값은 내부 tool calling 루프에서 실제 실행된 도구 이름 목록이다.

### Swagger로 실험하기

1. `POST /users`
2. `POST /projects`
3. `POST /chat`
4. 필요하면 `POST /translate`, `POST /images/generate`
5. `POST /sessions`, `POST /sessions/{session_id}/complete`
6. `GET /users/{user_id}/daily-report`

예시 입력:

### `POST /users`

```json
{
  "platform_user_id": "test-user-1",
  "nickname": "hosung"
}
```

### `POST /projects`

```json
{
  "user_id": 1,
  "title": "게임 시나리오 번역",
  "source_language": "ja",
  "target_language": "ko",
  "total_units": 120,
  "completed_units": 20,
  "deadline_at": "2026-03-12T18:00:00+09:00",
  "unit_label": "문장"
}
```

### `POST /chat`

```json
{
  "user_id": 1,
  "message": "하기 싫다"
}
```

### `POST /translate`

```json
{
  "text": "締切は明日の18時です。",
  "source_language": "ja",
  "target_language": "ko",
  "style": "natural"
}
```

### `POST /images/generate`

```json
{
  "prompt": "deadline enforcer poster, black and orange warning stripes",
  "size": "512x512",
  "style": "illustration"
}
```

## Telegram 사용

현재 텔레그램에서 가능한 것:

- `/start`
- `/help`
- `/deadline_add`
- `/deadline_list`
- `/status`
- `/timer <분>`
- `/report <숫자>`
- `/translate <원문>`
- `/image <프롬프트>`
- 일반 텍스트 코칭

### 버튼 동작

텔레그램 하단 버튼은 두 종류다.

- 바로 실행되는 명령 버튼
  - `/deadline_list`
  - `/status`
  - `/help`
- 안내용 양식 버튼
  - `프로젝트 등록 양식`
  - `타이머 시작 양식`
  - `번역 양식`
  - `이미지 양식`

양식 버튼은 예시 커맨드를 메시지로 보내준다.  
텔레그램 일반 봇은 입력창에 명령을 미리 채워 넣는 방식은 지원하지 않아서, 현재는 `복사해서 수정하는 흐름`으로 설계되어 있다.

### 권장 사용 순서

1. `/start`
2. `프로젝트 등록 양식` 버튼 확인
3. 예시를 복사해서 `/deadline_add ...` 전송
4. `/status`
5. `타이머 시작 양식` 버튼 확인
6. `/timer 25`
7. `/report 8`
8. 필요하면 `/translate ...` 또는 `/image ...`

### `/deadline_add` 형식

```text
/deadline_add <제목> | <원문 언어> | <목표 언어> | <총량> | <YYYY-MM-DD HH:MM> | <단위>
```

예:

```text
/deadline_add 게임 시나리오 번역 | ja | ko | 120 | 2026-03-14 18:00 | 문장
```

## 안정성 메모

- 번역과 이미지 생성은 `asyncio.to_thread(...)`로 돌려 텔레그램 이벤트 루프를 덜 막는다.
- 이미지 전송은 timeout을 늘려 둔다.
- 그래도 `sendPhoto` timeout이 나면 파일 경로를 텍스트로 알려주는 fallback이 있다.
- `rosetta_4b`는 현재 `Gemma3` 계열 로컬 체크포인트 특성 때문에 tokenizer fallback과 `token_type_ids` 제거 처리를 포함한다.

## 구현 메모

- 규칙 엔진: `deadlineforyou/rules.py`
- 프롬프트: `deadlineforyou/prompts.py`
- provider: `deadlineforyou/providers.py`
- 서비스: `deadlineforyou/service.py`
- API 진입점: `deadlineforyou/main.py`
- Telegram 진입점: `deadlineforyou/telegram_bot.py`
- 구현 아키텍처 문서: `deadlineforyou/architecture.md`
