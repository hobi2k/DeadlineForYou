from __future__ import annotations

from datetime import UTC, datetime

from deadlineforyou.domain import RuleEvaluation

def evaluate_mode(user_message: str, project: dict | None) -> RuleEvaluation:
    """evaluate_mode

    Args:
        user_message: 최신 사용자 메시지.
        project: 활성 프로젝트 스냅샷. 없을 수 있다.

    Returns:
        RuleEvaluation: 현재 프로젝트 상태를 바탕으로 정한 기본 타이머 정보.
    """
    del user_message

    hours_left = 999
    completion_ratio = 0.0
    if project:
        deadline_at = datetime.fromisoformat(project["deadline_at"]).astimezone(UTC)
        remaining = deadline_at - datetime.now(UTC)
        hours_left = max(int(remaining.total_seconds() // 3600), 0)
        total_units = max(project["total_units"], 1)
        completion_ratio = project["completed_units"] / total_units

    if hours_left <= 6:
        timer_minutes = 25
    elif completion_ratio < 0.4:
        timer_minutes = 15
    else:
        timer_minutes = 10

    return RuleEvaluation(
        timer_minutes=timer_minutes,
    )
