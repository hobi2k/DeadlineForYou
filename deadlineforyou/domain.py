from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from enum import StrEnum


class SessionStatus(StrEnum):
    active = "active"
    completed = "completed"
    cancelled = "cancelled"
    expired = "expired"


def utcnow() -> datetime:
    """utcnow

    Returns:
        datetime: 현재 UTC 시각.
    """
    return datetime.now(UTC)


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class GenerationResult:
    text: str
    tool_calls: list[ToolCall]
