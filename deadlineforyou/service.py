from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import json
from sqlite3 import Row
from typing import Any

from deadlineforyou.config import get_settings
from deadlineforyou.domain import CoachingMode, RuleEvaluation
from deadlineforyou.prompts import SYSTEM_PROMPT, build_context_block
from deadlineforyou.providers import (
    ImageProvider,
    LLMProvider,
    TranslationProvider,
    build_image_provider,
    build_translation_provider,
)
from deadlineforyou.rules import detect_avoidance, evaluate_mode
from deadlineforyou.storage import Database
from deadlineforyou.tools import build_bound_chat_tools


def _row_to_dict(row: Row | None) -> dict | None:
    """_row_to_dict

    Args:
        row: SQLite row 객체 또는 None.

    Returns:
        dict | None: API 직렬화를 위한 일반 딕셔너리. 없으면 None.
    """
    return dict(row) if row else None


class DeadlineCoachService:
    def __init__(self, database: Database, provider: LLMProvider) -> None:
        """__init__

        Args:
            database: 사용자, 프로젝트, 세션, 메시지 기록을 저장하는 영속 계층.
            provider: 페르소나 응답을 생성하는 LLM provider.

        Returns:
            None: 서비스 메서드에서 공통으로 쓸 의존성을 저장한다.
        """
        self.database = database
        self.provider = provider
        self.settings = get_settings()
        self.translation_provider: TranslationProvider = build_translation_provider(
            self.settings,
            fallback_provider=provider,
        )
        self.image_provider: ImageProvider = build_image_provider(self.settings)

    def create_user(self, payload: dict) -> dict:
        """create_user

        Args:
            payload: 사용자 생성 페이로드.

        Returns:
            dict: 저장된 사용자 레코드.
        """
        return dict(self.database.create_user(payload))

    def get_or_create_user(self, platform_user_id: str, nickname: str, timezone: str = "Asia/Seoul") -> dict:
        """get_or_create_user

        Args:
            platform_user_id: 외부 플랫폼에서 전달된 사용자 식별자.
            nickname: 기본 닉네임으로 사용할 문자열.
            timezone: 사용자 기본 시간대.

        Returns:
            dict: 이미 존재하거나 새로 생성된 사용자 레코드.
        """
        user = self.database.get_user_by_platform_id(platform_user_id)
        if user:
            return dict(user)
        return self.create_user(
            {
                "platform_user_id": platform_user_id,
                "nickname": nickname,
                "timezone": timezone,
                "tone_preference": "strict",
            }
        )

    def create_project(self, payload: dict) -> dict:
        """create_project

        Args:
            payload: 프로젝트 생성 페이로드.

        Returns:
            dict: 저장된 프로젝트 레코드.
        """
        return dict(self.database.create_project(payload))

    def list_projects(self, user_id: int) -> list[dict]:
        """list_projects

        Args:
            user_id: 내부 사용자 식별자.

        Returns:
            list[dict]: 사용자가 소유한 전체 프로젝트 목록.
        """
        return [dict(row) for row in self.database.list_projects_for_user(user_id)]

    def update_project(self, project_id: int, updates: dict) -> dict | None:
        """update_project

        Args:
            project_id: 대상 프로젝트 식별자.
            updates: 부분 업데이트 페이로드.

        Returns:
            dict | None: 프로젝트를 찾으면 갱신된 레코드, 없으면 None.
        """
        return _row_to_dict(self.database.update_project(project_id, updates))

    def start_session(self, user_id: int, project_id: int | None, duration_minutes: int, mode: CoachingMode) -> dict:
        """start_session

        Args:
            user_id: 내부 사용자 식별자.
            project_id: 세션이 특정 프로젝트에 묶여 있으면 그 식별자.
            duration_minutes: 예정된 세션 길이(분).
            mode: 세션에 연결할 코칭 모드.

        Returns:
            dict: 저장된 세션 레코드.
        """
        session = self.database.create_session(user_id, project_id, mode=mode, duration_minutes=duration_minutes)
        return dict(session)

    def complete_session(self, session_id: int, result_text: str, completed_units_delta: int) -> dict | None:
        """complete_session

        Args:
            session_id: 대상 세션 식별자.
            result_text: 사용자가 보고한 결과 텍스트.
            completed_units_delta: 연결된 프로젝트에 반영할 진행량 증가분.

        Returns:
            dict | None: 세션을 찾으면 완료 처리된 레코드, 없으면 None.
        """
        session = self.database.complete_session(session_id, result_text, completed_units_delta)
        return _row_to_dict(session)

    def get_session(self, session_id: int) -> dict | None:
        """get_session

        Args:
            session_id: 대상 세션 식별자.

        Returns:
            dict | None: 세션 레코드. 없으면 None.
        """
        return _row_to_dict(self.database.get_session(session_id))

    def get_active_project(self, user_id: int, project_id: int | None = None) -> dict | None:
        """get_active_project

        Args:
            user_id: 내부 사용자 식별자.
            project_id: 명시적 프로젝트 식별자. 없으면 active 프로젝트를 찾는다.

        Returns:
            dict | None: 활성 프로젝트 레코드 또는 None.
        """
        row = self.database.get_project(project_id) if project_id else self.database.get_active_project_for_user(user_id)
        return _row_to_dict(row)

    def chat(self, user_id: int, message: str, project_id: int | None = None) -> tuple[str, RuleEvaluation, list[str]]:
        """chat

        Args:
            user_id: 내부 사용자 식별자.
            message: 최신 사용자 메시지.
            project_id: 호출자가 명시적으로 넘긴 프로젝트 식별자.

        Returns:
            tuple[str, RuleEvaluation, list[str]]: 생성된 답변, 규칙 엔진 평가 결과, 실행된 tool 이름 목록.
        """
        project = self.get_active_project(user_id, project_id)

        recent_avoidance_events = self.database.today_avoidance_events(user_id)
        evaluation = evaluate_mode(message, project, recent_avoidance_count=len(recent_avoidance_events))
        avoidance_hits, category = detect_avoidance(message)
        if avoidance_hits:
            self.database.add_avoidance_event(user_id, project["id"] if project else None, message, category, avoidance_hits)

        history_rows = self.database.recent_messages(user_id)
        history = [{"role": row["role"], "content": row["content"]} for row in history_rows]

        # 모델 호출 전에 현재 사용자 상태, 프로젝트 상태, 규칙 힌트를 구조화해서 묶는다.
        user_snapshot = self._build_user_snapshot(user_id)
        project_snapshot = self._build_project_snapshot(project)
        rule_snapshot = self._build_rule_snapshot(evaluation)
        context_block = build_context_block(user_snapshot, project_snapshot, rule_snapshot)

        # 다음 턴에서 최근 문맥을 재사용할 수 있도록 사용자/봇 메시지를 모두 저장한다.
        self.database.add_message(user_id, project["id"] if project else None, "user", message)
        tools = build_bound_chat_tools(self, user_id, project["id"] if project else None)
        tool_schemas = [tool.tool_call_schema() for tool in tools.values()] if self.provider.supports_tool_calling() else None
        messages: list[dict[str, Any]] = [*history, {"role": "user", "content": message}]
        executed_tools: list[str] = []
        reply = ""

        for _ in range(3):
            result = self.provider.generate_turn(SYSTEM_PROMPT, context_block, messages, tool_schemas)
            if result.tool_calls:
                assistant_tool_calls = []
                for tool_call in result.tool_calls:
                    executed_tools.append(tool_call.name)
                    assistant_tool_calls.append(
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.name,
                                "arguments": json.dumps(tool_call.arguments, ensure_ascii=False),
                            },
                        }
                    )
                messages.append({"role": "assistant", "content": result.text or "", "tool_calls": assistant_tool_calls})

                for tool_call in result.tool_calls:
                    tool = tools.get(tool_call.name)
                    if tool is None:
                        payload = {"error": f"unknown_tool:{tool_call.name}"}
                    else:
                        try:
                            payload = tool.execute(tool_call.arguments)
                        except Exception as exc:  # noqa: BLE001
                            payload = {"error": str(exc), "tool": tool_call.name}
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(payload, ensure_ascii=False),
                        }
                    )
                continue

            reply = result.text
            break

        if not reply:
            reply = "도구 실행까진 했는데 아직 네 보고가 없다. 지금 상태를 짧게 다시 말해."
        self.database.add_message(user_id, project["id"] if project else None, "assistant", reply)
        return reply, evaluation, executed_tools

    def build_daily_report(self, user_id: int) -> dict:
        """build_daily_report

        Args:
            user_id: 내부 사용자 식별자.

        Returns:
            dict: 세션, 진행량, 회피 행동을 모은 일일 집계 리포트.
        """
        sessions = self.database.today_completed_sessions(user_id)
        avoidance_events = self.database.today_avoidance_events(user_id)
        focus_minutes = sum(row["duration_minutes"] for row in sessions)
        completed_units = sum(row["completed_units_delta"] for row in sessions)
        excuses = [row["trigger_text"] for row in avoidance_events]
        top_excuse = Counter(excuses).most_common(1)[0][0] if excuses else None

        summary = (
            f"오늘 집중 {focus_minutes}분, 완료 {completed_units}단위, 회피 {len(avoidance_events)}회. "
            f"가장 많이 남긴 변명: {top_excuse or '없음'}."
        )

        return {
            "user_id": user_id,
            "date": datetime.now(UTC).date().isoformat(),
            "focus_minutes": focus_minutes,
            "completed_units": completed_units,
            "avoidance_count": len(avoidance_events),
            "top_excuse": top_excuse,
            "summary": summary,
        }

    def translate_text(
        self,
        text: str,
        source_language: str = "ja",
        target_language: str = "ko",
        style: str = "natural",
    ) -> dict:
        """translate_text

        Args:
            text: 번역할 원문.
            source_language: 원문 언어.
            target_language: 목표 언어.
            style: 번역 스타일 힌트.

        Returns:
            dict: 번역 결과와 메타데이터.
        """
        return self.translation_provider.translate_text(
            text=text,
            source_language=source_language,
            target_language=target_language,
            style=style,
        )

    def generate_image(
        self,
        prompt: str,
        size: str = "512x512",
        style: str = "illustration",
    ) -> dict:
        """generate_image

        Args:
            prompt: 이미지 생성 프롬프트.
            size: 생성 이미지 크기.
            style: 이미지 스타일 힌트.

        Returns:
            dict: 저장 경로 또는 오류를 포함한 결과.
        """
        if self.settings.image_release_translation_before_generation:
            self.translation_provider.unload()
        return self.image_provider.generate_image(prompt=prompt, size=size, style=style)

    def _build_user_snapshot(self, user_id: int) -> str:
        """_build_user_snapshot

        Args:
            user_id: 내부 사용자 식별자.

        Returns:
            str: 프롬프트 주입용 사용자 상태 요약 문자열.
        """
        user = self.database.get_user(user_id)
        if not user:
            return "unknown user"
        sessions = self.database.today_completed_sessions(user_id)
        return (
            f"nickname={user['nickname']}\n"
            f"timezone={user['timezone']}\n"
            f"tone_preference={user['tone_preference']}\n"
            f"today_completed_sessions={len(sessions)}"
        )

    def _build_project_snapshot(self, project: dict | None) -> str:
        """_build_project_snapshot

        Args:
            project: 활성 프로젝트 스냅샷 또는 None.

        Returns:
            str: 프롬프트 주입용 프로젝트 상태 요약 문자열.
        """
        if not project:
            return "active_project=none"
        deadline_at = datetime.fromisoformat(project["deadline_at"]).astimezone(UTC)
        remaining = deadline_at - datetime.now(UTC)
        hours_left = max(round(remaining.total_seconds() / 3600, 1), 0.0)
        return (
            f"title={project['title']}\n"
            f"progress={project['completed_units']}/{project['total_units']} {project['unit_label']}\n"
            f"deadline_at={project['deadline_at']}\n"
            f"hours_left={hours_left}\n"
            f"status={project['status']}"
        )

    def _build_rule_snapshot(self, evaluation: RuleEvaluation) -> str:
        """_build_rule_snapshot

        Args:
            evaluation: 현재 턴에 대한 규칙 엔진 출력.

        Returns:
            str: 프롬프트 주입용 규칙 가이드 요약 문자열.
        """
        return (
            f"mode={evaluation.mode.value}\n"
            f"urgency_score={evaluation.urgency_score}\n"
            f"timer_minutes={evaluation.timer_minutes}\n"
            f"action_hint={evaluation.action_hint}\n"
            f"report_hint={evaluation.report_hint}"
        )
