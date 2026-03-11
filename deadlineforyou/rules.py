from __future__ import annotations

from datetime import UTC, datetime

from deadlineforyou.domain import CoachingMode, RuleEvaluation


AVOIDANCE_PATTERNS = {
    "하기 싫": ("resistance", 2),
    "귀찮": ("resistance", 2),
    "나중": ("delay", 2),
    "내일": ("delay", 2),
    "졸려": ("fatigue", 1),
    "피곤": ("fatigue", 1),
    "유튜브": ("escape", 3),
    "도망": ("escape", 3),
    "못 하겠": ("freeze", 2),
}


def detect_avoidance(text: str) -> tuple[int, str]:
    """detect_avoidance

    Args:
        text: 검사할 사용자 원문 메시지.

    Returns:
        tuple[int, str]: 누적 회피 심각도 점수와 마지막으로 매칭된 분류.
    """
    hits = 0
    category = "none"
    for pattern, (matched_category, severity) in AVOIDANCE_PATTERNS.items():
        if pattern in text:
            hits += severity
            category = matched_category
    return hits, category


def evaluate_mode(user_message: str, project: dict | None, recent_avoidance_count: int) -> RuleEvaluation:
    """evaluate_mode

    Args:
        user_message: 최신 사용자 메시지.
        project: 활성 프로젝트 스냅샷. 없을 수 있다.
        recent_avoidance_count: 오늘 기록된 회피 이벤트 수.

    Returns:
        RuleEvaluation: 다음 응답에 사용할 모드, 긴급도, 타이머, 코칭 힌트.
    """
    lowered = user_message.strip()
    avoidance_hits, _ = detect_avoidance(lowered)

    hours_left = 999
    completion_ratio = 0.0
    if project:
        deadline_at = datetime.fromisoformat(project["deadline_at"]).astimezone(UTC)
        remaining = deadline_at - datetime.now(UTC)
        hours_left = max(int(remaining.total_seconds() // 3600), 0)
        total_units = max(project["total_units"], 1)
        completion_ratio = project["completed_units"] / total_units

    # 긴급도는 즉시 드러난 회피 신호와 실제 마감 압박을 함께 반영한다.
    urgency_score = avoidance_hits + recent_avoidance_count
    if hours_left <= 24:
        urgency_score += 2
    if hours_left <= 6:
        urgency_score += 3
    if completion_ratio < 0.4:
        urgency_score += 1

    if hours_left <= 6:
        mode = CoachingMode.boss_mode
        timer_minutes = 25
    elif avoidance_hits >= 2:
        mode = CoachingMode.force_start
        timer_minutes = 10
    elif "졸려" in lowered or "피곤" in lowered:
        mode = CoachingMode.cold_support
        timer_minutes = 15
    elif recent_avoidance_count >= 2:
        mode = CoachingMode.reality_check
        timer_minutes = 15
    else:
        mode = CoachingMode.default
        timer_minutes = 10

    if mode == CoachingMode.boss_mode:
        action_hint = "25분 번역, 5분 정리, 25분 번역으로 바로 들어가라."
        report_hint = "끝나면 완료 분량을 숫자로 보고하게 만들어라."
    elif mode == CoachingMode.force_start:
        action_hint = "파일 열기, 첫 문장 번역, 타이머 시작처럼 실패하기 어려운 최소 행동을 지시하라."
        report_hint = "시작했는지 즉시 보고하게 만들어라."
    elif mode == CoachingMode.cold_support:
        action_hint = "힘듦을 인정하되 15분만 하는 구조 복구 세션을 지시하라."
        report_hint = "몇 줄 했는지 보고하게 만들어라."
    elif mode == CoachingMode.reality_check:
        action_hint = "회피 비용을 짧게 지적하고 지금 당장 할 번역 블록을 제시하라."
        report_hint = "10~15분 후 진행률 보고를 요구하라."
    else:
        action_hint = "현재 작업을 작게 쪼개고 지금 시작할 액션을 제시하라."
        report_hint = "짧은 완료 보고를 요구하라."

    return RuleEvaluation(
        mode=mode,
        urgency_score=urgency_score,
        avoidance_hits=avoidance_hits,
        timer_minutes=timer_minutes,
        action_hint=action_hint,
        report_hint=report_hint,
    )
