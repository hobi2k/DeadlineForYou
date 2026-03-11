# DeadlineForYou

`DeadlineForYou`는 프리랜서 번역가를 작업 화면으로 다시 밀어 넣는 마감 집행 API다.

현재 구현 범위:

- FastAPI 기반 백엔드
- Telegram bot 어댑터
- SQLite 저장소
- 마감 프로젝트 등록/수정
- 작업 세션 시작/완료
- `締切監督` 페르소나 채팅
- `OpenAI API`와 프로젝트 내장 로컬 모델 둘 다 지원

## 실행

### 1. API 서버 실행

```bash
cd /home/hosung/pytorch-demo/DeadlineForYou
uv venv
source .venv/bin/activate
uv pip install -e .
cp .env.example .env
uv run uvicorn deadlineforyou.main:app --reload
```

기본값은 `scripted` provider라서 API 키 없이도 동작한다.

서버가 뜨면 브라우저에서 아래 주소로 들어간다.

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

### 2. Telegram bot 실행

`.env`에 텔레그램 봇 토큰을 넣는다.

```env
DFY_TELEGRAM_BOT_TOKEN=123456:ABC...
```

그 다음 별도 터미널에서 실행한다.

```bash
cd /home/hosung/pytorch-demo/DeadlineForYou
source .venv/bin/activate
uv run python -m deadlineforyou.telegram_bot
```

주의:

- API 서버와 Telegram bot은 각각 따로 띄우는 편이 관리하기 쉽다.
- 둘 다 같은 SQLite 파일을 사용하므로 사용자/프로젝트 데이터가 공유된다.

## Provider 설정

### provider 차이

- `scripted`: 모델을 전혀 호출하지 않고, 코드에 고정된 규칙형 응답을 반환한다. 설치 직후 API 구조 확인이나 로컬 개발 smoke test에 적합하다.
- `local`: 프로젝트 안의 `deadlineforyou/models/saya_rp_4b_v3`를 `transformers`로 직접 로드해 실제 생성형 응답을 만든다. GPU/메모리 자원을 사용한다.
- `openai`: OpenAI API를 호출해 응답을 생성한다. 로컬 GPU는 필요 없지만 API 키와 네트워크가 필요하다.

### 1. GPT API 버전

`.env`:

```env
DFY_LLM_PROVIDER=openai
DFY_OPENAI_API_KEY=sk-...
DFY_LLM_MODEL=gpt-4.1-mini
```

### 2. 로컬 LLM 버전

프로젝트에 포함된 `qwen3` 기반 `saya_rp_4b_v3`를 직접 로드한다.

`.env`:

```env
DFY_LLM_PROVIDER=local
DFY_LOCAL_MODEL_PATH=deadlineforyou/models/saya_rp_4b_v3
DFY_LOCAL_DEVICE_MAP=auto
DFY_LOCAL_MAX_NEW_TOKENS=220
DFY_LOCAL_TEMPERATURE=0.7
```

주의:

- `saya_rp_4b_v3`는 `Qwen3ForCausalLM` 기반이다.
- 로컬 모드는 `transformers`로 직접 로드한다.
- GPU가 있으면 `device_map=auto`로 두는 편이 맞고, 메모리가 부족하면 별도 양자화 구성이 필요하다.

## 주요 엔드포인트

- `POST /users`
- `POST /projects`
- `PATCH /projects/{project_id}`
- `POST /chat`
- `POST /sessions`
- `POST /sessions/{session_id}/complete`
- `GET /users/{user_id}/daily-report`

## 텔레그램에서 실험하기

현재 텔레그램 bot에서 가능한 것은 아래와 같다.

- `/start` : 텔레그램 사용자 자동 등록
- `/help` : 명령 목록 확인
- `/status` : 현재 활성 프로젝트와 오늘 요약 확인
- `/start10` : 10분 강제 시동 세션 시작
- `/start15` : 15분 구조 복구 세션 시작
- `/pomodoro` : 25분 세션 시작
- `/report 8` : 마지막 세션 작업량 보고
- 일반 텍스트 메시지 : `締切監督` 코칭 응답

권장 실험 순서:

1. BotFather에서 토큰을 발급받아 `.env`에 `DFY_TELEGRAM_BOT_TOKEN`을 넣는다.
2. bot 프로세스를 실행한다.
3. 텔레그램에서 봇 채팅을 열고 `/start`를 입력한다.
4. `/status`를 눌러 현재 프로젝트 상태를 확인한다.
5. `하기 싫다` 같은 평문 메시지를 보내 응답 톤을 본다.
6. `/start10`으로 세션을 시작하고, 종료 알림이 오면 `/report 8`처럼 보고한다.

중요:

- 텔레그램 bot은 사용자를 자동 생성하지만 프로젝트 생성 명령은 아직 없다.
- 따라서 첫 프로젝트는 Swagger UI 또는 REST API에서 먼저 만들어야 한다.
- 프로젝트가 없으면 `/status`에서 그 사실을 알려준다.

## 웹 UI에서 실험하기

REST API 전용 웹 UI는 FastAPI가 기본 제공하는 Swagger UI를 쓰면 된다.

주소:

- `http://127.0.0.1:8000/docs`

실험 순서:

1. `POST /users`를 열고 `Try it out`을 누른다.
2. 아래 JSON으로 사용자를 만든다.
3. 응답에서 `id`를 확인한다.
4. `POST /projects`에서 방금 받은 `user_id`로 프로젝트를 만든다.
5. `POST /chat`에서 메시지를 보내 응답 말투와 `mode`, `timer_minutes`를 확인한다.
6. 필요하면 `POST /sessions`와 `POST /sessions/{session_id}/complete`까지 시험한다.
7. 마지막으로 `GET /users/{user_id}/daily-report`에서 집계 결과를 본다.

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
  "title": "일본어 게임 시나리오 번역",
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

확인 포인트:

- `reply`가 `締切監督` 말투에 맞는지
- `mode`가 상황에 따라 바뀌는지
- `timer_minutes`가 적절히 추천되는지
- 세션 완료 후 진행량이 반영되는지

## curl로 실험하기

### 사용자 생성

```bash
curl -X POST http://127.0.0.1:8000/users \
  -H "Content-Type: application/json" \
  -d '{"platform_user_id":"telegram-1","nickname":"hosung"}'
```

### 프로젝트 생성

```bash
curl -X POST http://127.0.0.1:8000/projects \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "title": "게임 시나리오 번역",
    "total_units": 120,
    "completed_units": 20,
    "deadline_at": "2026-03-12T18:00:00+09:00",
    "unit_label": "문장"
  }'
```

### 코칭 요청

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":1,"message":"하기 싫다"}'
```

## 구현 메모

- 제품 규칙은 `deadlineforyou/rules.py`
- LLM 연결부는 `deadlineforyou/providers.py`
- 핵심 오케스트레이션은 `deadlineforyou/service.py`
- API 진입점은 `deadlineforyou/main.py`
