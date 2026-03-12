from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from deadlineforyou.config import get_settings
from deadlineforyou.providers import build_provider
from deadlineforyou.schemas import (
    ChatRequest,
    ChatResponse,
    DailyReportResponse,
    ImageGenerateRequest,
    ImageGenerateResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    SessionComplete,
    SessionCreate,
    SessionResponse,
    TranslateRequest,
    TranslateResponse,
    UserCreate,
    UserResponse,
)
from deadlineforyou.service import DeadlineCoachService
from deadlineforyou.storage import Database


@asynccontextmanager
async def lifespan(app: FastAPI):
    """lifespan

    Args:
        app: FastAPI 애플리케이션 인스턴스.

    Returns:
        None: API 생명주기 동안 쓸 공용 애플리케이션 상태를 초기화한다.
    """
    settings = get_settings()
    database = Database(settings.database_path)
    provider = build_provider(settings)
    app.state.service = DeadlineCoachService(database, provider)
    yield


app = FastAPI(title="DeadlineForYou", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    """healthcheck

    Args:
        없음.

    Returns:
        dict[str, str]: 최소 상태 확인 응답.
    """
    return {"status": "ok"}


@app.post("/users", response_model=UserResponse)
def create_user(payload: UserCreate):
    """create_user

    Args:
        payload: 사용자 생성 요청 본문.

    Returns:
        UserResponse: 저장된 사용자 응답 객체.
    """
    service: DeadlineCoachService = app.state.service
    return service.create_user(payload.model_dump())


@app.post("/projects", response_model=ProjectResponse)
def create_project(payload: ProjectCreate):
    """create_project

    Args:
        payload: 프로젝트 생성 요청 본문.

    Returns:
        ProjectResponse: 저장된 프로젝트 응답 객체.
    """
    service: DeadlineCoachService = app.state.service
    return service.create_project(payload.model_dump())


@app.get("/users/{user_id}/projects", response_model=list[ProjectResponse])
def list_projects(user_id: int):
    """list_projects

    Args:
        user_id: 내부 사용자 식별자.

    Returns:
        list[ProjectResponse]: 사용자가 소유한 프로젝트 목록.
    """
    service: DeadlineCoachService = app.state.service
    return service.list_projects(user_id)


@app.patch("/projects/{project_id}", response_model=ProjectResponse)
def update_project(project_id: int, payload: ProjectUpdate):
    """update_project

    Args:
        project_id: 대상 프로젝트 식별자.
        payload: 프로젝트 부분 수정 요청 본문.

    Returns:
        ProjectResponse: 갱신된 프로젝트 응답 객체.
    """
    service: DeadlineCoachService = app.state.service
    project = service.update_project(project_id, payload.model_dump(exclude_none=True))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):
    """chat

    Args:
        payload: 사용자 메시지와 선택적 프로젝트 바인딩이 담긴 채팅 요청 본문.

    Returns:
        ChatResponse: 페르소나 답변과 규칙 엔진 메타데이터.
    """
    service: DeadlineCoachService = app.state.service
    reply, timer_minutes, executed_tools, tool_results = service.chat(payload.user_id, payload.message, payload.project_id)
    return {
        "reply": reply,
        "timer_minutes": timer_minutes,
        "executed_tools": executed_tools,
        "tool_results": tool_results,
    }


@app.post("/sessions", response_model=SessionResponse)
def start_session(payload: SessionCreate):
    """start_session

    Args:
        payload: 세션 생성 요청 본문.

    Returns:
        SessionResponse: 저장된 세션 응답 객체.
    """
    service: DeadlineCoachService = app.state.service
    session = service.start_session(
        user_id=payload.user_id,
        project_id=payload.project_id,
        duration_minutes=payload.duration_minutes,
        mode=payload.mode,
    )
    return session


@app.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: int):
    """get_session

    Args:
        session_id: 세션 식별자.

    Returns:
        SessionResponse: 세션을 찾았을 때의 응답 객체.
    """
    service: DeadlineCoachService = app.state.service
    session = service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.post("/sessions/{session_id}/complete", response_model=SessionResponse)
def complete_session(session_id: int, payload: SessionComplete):
    """complete_session

    Args:
        session_id: 세션 식별자.
        payload: 세션 완료 요청 본문.

    Returns:
        SessionResponse: 완료 처리된 세션 응답 객체.
    """
    service: DeadlineCoachService = app.state.service
    session = service.complete_session(session_id, payload.result_text, payload.completed_units_delta)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.get("/users/{user_id}/daily-report", response_model=DailyReportResponse)
def daily_report(user_id: int):
    """daily_report

    Args:
        user_id: 내부 사용자 식별자.

    Returns:
        DailyReportResponse: 일일 생산성 집계 리포트.
    """
    service: DeadlineCoachService = app.state.service
    return service.build_daily_report(user_id)


@app.post("/translate", response_model=TranslateResponse)
def translate_text(payload: TranslateRequest):
    """translate_text

    Args:
        payload: 번역 요청 본문.

    Returns:
        TranslateResponse: 번역 결과와 번역 메타데이터.
    """
    service: DeadlineCoachService = app.state.service
    return service.translate_text(
        text=payload.text,
        source_language=payload.source_language,
        target_language=payload.target_language,
        style=payload.style,
    )


@app.post("/images/generate", response_model=ImageGenerateResponse)
def generate_image(payload: ImageGenerateRequest):
    """generate_image

    Args:
        payload: 이미지 생성 요청 본문.

    Returns:
        ImageGenerateResponse: 저장 경로나 오류 정보를 포함한 생성 결과.
    """
    service: DeadlineCoachService = app.state.service
    return service.generate_image(
        prompt=payload.prompt,
        size=payload.size,
        style=payload.style,
    )


@app.get("/meta/providers")
def provider_meta():
    """provider_meta

    Args:
        없음.

    Returns:
        dict: 디버깅과 클라이언트 연동에 쓸 provider 설정 요약.
    """
    settings = get_settings()
    return {
        "llm_provider": settings.llm_provider,
        "translation_provider": settings.translation_provider,
        "image_provider": settings.image_provider,
        "local_model_path": str(settings.local_model_path),
        "translation_local_model_path": str(settings.translation_local_model_path),
        "image_local_model_path": str(settings.image_local_model_path),
        "translation_lazy_load": settings.translation_lazy_load,
        "image_lazy_load": settings.image_lazy_load,
        "image_unload_after_generation": settings.image_unload_after_generation,
        "supports": ["local", "scripted", "local_images"],
        "recommended_session_types": ["timer"],
    }
