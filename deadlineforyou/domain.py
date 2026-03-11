from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class CoachingMode(StrEnum):
    default = "default"
    reality_check = "reality_check"
    force_start = "force_start"
    cold_support = "cold_support"
    boss_mode = "boss_mode"


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
class RuleEvaluation:
    mode: CoachingMode
    urgency_score: int
    avoidance_hits: int
    timer_minutes: int
    action_hint: str
    report_hint: str
