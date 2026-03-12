from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from deadlineforyou.domain import SessionStatus


SUPPORTED_LANGUAGE_CODES = {"ko", "jp", "en", "ch"}


def _normalize_language_code(value: str) -> str:
    """_normalize_language_code

    Args:
        value: 입력된 언어 코드 문자열.

    Returns:
        str: 정규화된 언어 코드.
    """
    normalized = value.strip().lower()
    aliases = {
        "ja": "jp",
        "zh": "ch",
        "cn": "ch",
    }
    return aliases.get(normalized, normalized)


class UserCreate(BaseModel):
    platform_user_id: str
    nickname: str
    timezone: str = "Asia/Seoul"
    tone_preference: str = "strict"


class UserResponse(BaseModel):
    id: int
    platform_user_id: str
    nickname: str
    timezone: str
    tone_preference: str
    created_at: datetime


class ProjectCreate(BaseModel):
    user_id: int
    title: str
    source_language: str = "jp"
    target_language: str = "ko"
    total_units: int = Field(gt=0)
    completed_units: int = 0
    deadline_at: datetime
    unit_label: str = "문장"

    @field_validator("source_language", "target_language")
    @classmethod
    def validate_language_code(cls, value: str) -> str:
        """validate_language_code

        Args:
            value: 입력된 언어 코드 문자열.

        Returns:
            str: 검증이 끝난 언어 코드.
        """
        normalized = _normalize_language_code(value)
        if normalized not in SUPPORTED_LANGUAGE_CODES:
            raise ValueError("지원 언어 코드는 ko, jp, en, ch만 가능하다.")
        return normalized


class ProjectUpdate(BaseModel):
    completed_units: int | None = None
    total_units: int | None = Field(default=None, gt=0)
    deadline_at: datetime | None = None
    status: str | None = None


class ProjectResponse(BaseModel):
    id: int
    user_id: int
    title: str
    source_language: str
    target_language: str
    total_units: int
    completed_units: int
    deadline_at: datetime
    unit_label: str
    status: str
    created_at: datetime


class ChatRequest(BaseModel):
    user_id: int
    message: str
    project_id: int | None = None


class ChatResponse(BaseModel):
    reply: str
    timer_minutes: int
    executed_tools: list[str] = []
    tool_results: dict[str, dict] = {}


class SessionCreate(BaseModel):
    user_id: int
    project_id: int | None = None
    duration_minutes: int = Field(ge=1, le=180)
    mode: str = "timer"


class SessionComplete(BaseModel):
    result_text: str
    completed_units_delta: int = 0


class SessionResponse(BaseModel):
    id: int
    user_id: int
    project_id: int | None
    mode: str
    duration_minutes: int
    status: SessionStatus
    started_at: datetime
    ends_at: datetime
    ended_at: datetime | None
    reported_result: str | None


class DailyReportResponse(BaseModel):
    user_id: int
    date: str
    focus_minutes: int
    completed_units: int
    summary: str


class TranslateRequest(BaseModel):
    text: str
    source_language: str = "jp"
    target_language: str = "ko"
    style: str = "natural"

    @field_validator("source_language", "target_language")
    @classmethod
    def validate_language_code(cls, value: str) -> str:
        """validate_language_code

        Args:
            value: 입력된 언어 코드 문자열.

        Returns:
            str: 검증이 끝난 언어 코드.
        """
        normalized = _normalize_language_code(value)
        if normalized not in SUPPORTED_LANGUAGE_CODES:
            raise ValueError("지원 언어 코드는 ko, jp, en, ch만 가능하다.")
        return normalized


class TranslateResponse(BaseModel):
    provider: str
    source_language: str
    target_language: str
    style: str
    translated_text: str


class ImageGenerateRequest(BaseModel):
    prompt: str
    size: str = "512x512"
    style: str = "illustration"


class ImageGenerateResponse(BaseModel):
    provider: str | None = None
    prompt: str | None = None
    style: str | None = None
    size: str | None = None
    file_path: str | None = None
    error: str | None = None
    message: str | None = None
