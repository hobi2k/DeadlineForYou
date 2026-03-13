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


class ProjectFileCreate(BaseModel):
    project_id: int
    name: str
    source_text: str
    translated_text: str = ""
    due_at: datetime | None = None


class ProjectFileUpdate(BaseModel):
    name: str | None = None
    source_text: str | None = None
    translated_text: str | None = None
    due_at: datetime | None = None
    status: str | None = None


class ProjectFileResponse(BaseModel):
    id: int
    project_id: int
    name: str
    source_text: str
    translated_text: str
    source_chars: int
    source_lines: int
    source_segments: int
    translated_chars: int
    translated_lines: int
    translated_segments: int
    status: str
    due_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PlannerResponse(BaseModel):
    project_id: int
    remaining_units: int
    unit_label: str
    remaining_days: float
    required_units_per_day: float
    required_units_per_hour: float
    file_backlog_count: int
    delayed_file_count: int
    summary: str


class ProjectOverviewResponse(BaseModel):
    project: ProjectResponse
    planner: PlannerResponse
    file_count: int
    remaining_file_count: int
    delayed_file_count: int
    total_chars: int
    total_segments: int
    translated_chars: int
    translated_segments: int


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


class WorkloadSummaryResponse(BaseModel):
    project_id: int
    total_chars: int
    total_lines: int
    total_segments: int
    translated_chars: int
    translated_lines: int
    translated_segments: int
    remaining_chars: int
    remaining_segments: int
    file_count: int
    remaining_file_count: int
    delayed_file_count: int


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


class FileAssistTranslateRequest(BaseModel):
    source_language: str = "jp"
    target_language: str = "ko"
    style: str = "natural"
    max_chars: int = Field(default=1200, ge=1, le=8000)

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


class FileAssistTranslateResponse(BaseModel):
    file_id: int
    file_name: str
    source_language: str
    target_language: str
    translated_excerpt: str
    excerpt_chars: int


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
