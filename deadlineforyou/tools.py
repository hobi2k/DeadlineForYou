from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from deadlineforyou.domain import CoachingMode


ToolExecutor = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(slots=True)
class DeadlineTool:
    name: str
    description: str
    parameters: dict[str, Any]
    execute: ToolExecutor

    def openai_schema(self) -> dict[str, Any]:
        """openai_schema

        Args:
            없음.

        Returns:
            dict[str, Any]: OpenAI tool calling 형식에 맞춘 함수 스키마.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def mcp_schema(self) -> dict[str, Any]:
        """mcp_schema

        Args:
            없음.

        Returns:
            dict[str, Any]: MCP tools/list 응답에 넣을 도구 스키마.
        """
        return {
            "name": self.name,
            "title": self.name,
            "description": self.description,
            "inputSchema": self.parameters,
        }


def _normalize_mode(value: str) -> CoachingMode:
    """_normalize_mode

    Args:
        value: 문자열 모드 값.

    Returns:
        CoachingMode: 유효한 코칭 모드 enum.
    """
    return CoachingMode(value)


def build_bound_chat_tools(service: Any, user_id: int, project_id: int | None) -> dict[str, DeadlineTool]:
    """build_bound_chat_tools

    Args:
        service: DeadlineCoachService 인스턴스.
        user_id: 현재 대화 사용자 식별자.
        project_id: 현재 대화에 연결된 프로젝트 식별자.

    Returns:
        dict[str, DeadlineTool]: 현재 사용자 문맥에 묶인 tool registry.
    """

    def get_active_project(_: dict[str, Any]) -> dict[str, Any]:
        project = service.get_active_project(user_id, project_id)
        return project or {"active_project": None}

    def start_focus_session(arguments: dict[str, Any]) -> dict[str, Any]:
        duration_minutes = int(arguments.get("duration_minutes", 10))
        mode = _normalize_mode(arguments.get("mode", CoachingMode.force_start.value))
        project = service.get_active_project(user_id, project_id)
        session = service.start_session(user_id, project["id"] if project else None, duration_minutes, mode)
        return {
            "session": session,
            "instruction": f"{duration_minutes}분 세션을 시작했다. 끝나면 보고를 요구하라.",
        }

    def complete_focus_session(arguments: dict[str, Any]) -> dict[str, Any]:
        session_id = int(arguments["session_id"])
        completed_units_delta = int(arguments.get("completed_units_delta", 0))
        result_text = str(arguments.get("result_text", "세션 완료"))
        session = service.complete_session(session_id, result_text, completed_units_delta)
        return {
            "session": session,
            "instruction": "완료 처리 결과를 반영해 다음 작업을 바로 제시하라.",
        }

    def get_daily_report(_: dict[str, Any]) -> dict[str, Any]:
        return service.build_daily_report(user_id)

    def list_projects(_: dict[str, Any]) -> dict[str, Any]:
        return {"projects": service.list_projects(user_id)}

    return {
        "get_active_project": DeadlineTool(
            name="get_active_project",
            description="현재 사용자의 활성 번역 프로젝트 상태를 조회한다.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            execute=get_active_project,
        ),
        "start_focus_session": DeadlineTool(
            name="start_focus_session",
            description="집중 세션을 시작하고 세션 ID와 종료 시각을 반환한다.",
            parameters={
                "type": "object",
                "properties": {
                    "duration_minutes": {"type": "integer", "minimum": 1, "maximum": 180},
                    "mode": {"type": "string", "enum": [mode.value for mode in CoachingMode]},
                },
                "required": ["duration_minutes", "mode"],
                "additionalProperties": False,
            },
            execute=start_focus_session,
        ),
        "complete_focus_session": DeadlineTool(
            name="complete_focus_session",
            description="세션을 완료 처리하고 프로젝트 진행량을 반영한다.",
            parameters={
                "type": "object",
                "properties": {
                    "session_id": {"type": "integer"},
                    "completed_units_delta": {"type": "integer", "minimum": 0},
                    "result_text": {"type": "string"},
                },
                "required": ["session_id"],
                "additionalProperties": False,
            },
            execute=complete_focus_session,
        ),
        "get_daily_report": DeadlineTool(
            name="get_daily_report",
            description="현재 사용자의 오늘 리포트를 조회한다.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            execute=get_daily_report,
        ),
        "list_projects": DeadlineTool(
            name="list_projects",
            description="현재 사용자의 프로젝트 목록을 조회한다.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            execute=list_projects,
        ),
    }


def build_mcp_tools(service: Any) -> dict[str, DeadlineTool]:
    """build_mcp_tools

    Args:
        service: DeadlineCoachService 인스턴스.

    Returns:
        dict[str, DeadlineTool]: MCP 서버에서 노출할 범용 tool registry.
    """

    def get_active_project(arguments: dict[str, Any]) -> dict[str, Any]:
        user_id = int(arguments["user_id"])
        project_id = arguments.get("project_id")
        return service.get_active_project(user_id, int(project_id) if project_id is not None else None) or {"active_project": None}

    def list_projects(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"projects": service.list_projects(int(arguments["user_id"]))}

    def start_focus_session(arguments: dict[str, Any]) -> dict[str, Any]:
        user_id = int(arguments["user_id"])
        duration_minutes = int(arguments["duration_minutes"])
        project_id = arguments.get("project_id")
        mode = _normalize_mode(arguments["mode"])
        return service.start_session(user_id, int(project_id) if project_id is not None else None, duration_minutes, mode)

    def complete_focus_session(arguments: dict[str, Any]) -> dict[str, Any]:
        session = service.complete_session(
            int(arguments["session_id"]),
            str(arguments.get("result_text", "세션 완료")),
            int(arguments.get("completed_units_delta", 0)),
        )
        return session or {"error": "session_not_found"}

    def get_daily_report(arguments: dict[str, Any]) -> dict[str, Any]:
        return service.build_daily_report(int(arguments["user_id"]))

    return {
        "get_active_project": DeadlineTool(
            name="get_active_project",
            description="사용자의 활성 프로젝트 상태를 조회한다.",
            parameters={
                "type": "object",
                "properties": {"user_id": {"type": "integer"}, "project_id": {"type": "integer"}},
                "required": ["user_id"],
                "additionalProperties": False,
            },
            execute=get_active_project,
        ),
        "list_projects": DeadlineTool(
            name="list_projects",
            description="사용자의 프로젝트 목록을 조회한다.",
            parameters={
                "type": "object",
                "properties": {"user_id": {"type": "integer"}},
                "required": ["user_id"],
                "additionalProperties": False,
            },
            execute=list_projects,
        ),
        "start_focus_session": DeadlineTool(
            name="start_focus_session",
            description="집중 세션을 시작한다.",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer"},
                    "project_id": {"type": "integer"},
                    "duration_minutes": {"type": "integer", "minimum": 1, "maximum": 180},
                    "mode": {"type": "string", "enum": [mode.value for mode in CoachingMode]},
                },
                "required": ["user_id", "duration_minutes", "mode"],
                "additionalProperties": False,
            },
            execute=start_focus_session,
        ),
        "complete_focus_session": DeadlineTool(
            name="complete_focus_session",
            description="세션을 완료 처리한다.",
            parameters={
                "type": "object",
                "properties": {
                    "session_id": {"type": "integer"},
                    "completed_units_delta": {"type": "integer", "minimum": 0},
                    "result_text": {"type": "string"},
                },
                "required": ["session_id"],
                "additionalProperties": False,
            },
            execute=complete_focus_session,
        ),
        "get_daily_report": DeadlineTool(
            name="get_daily_report",
            description="사용자의 일일 리포트를 조회한다.",
            parameters={
                "type": "object",
                "properties": {"user_id": {"type": "integer"}},
                "required": ["user_id"],
                "additionalProperties": False,
            },
            execute=get_daily_report,
        ),
    }


def build_mcp_resources(service: Any) -> list[dict[str, str]]:
    """build_mcp_resources

    Args:
        service: DeadlineCoachService 인스턴스.

    Returns:
        list[dict[str, str]]: MCP에서 노출할 정적 리소스 메타데이터 목록.
    """
    del service
    return [
        {"uri": "deadline://schema/users", "name": "users_schema", "description": "DeadlineForYou users 테이블 개요", "mimeType": "application/json"},
        {"uri": "deadline://schema/projects", "name": "projects_schema", "description": "DeadlineForYou projects 테이블 개요", "mimeType": "application/json"},
        {"uri": "deadline://schema/sessions", "name": "sessions_schema", "description": "DeadlineForYou sessions 테이블 개요", "mimeType": "application/json"},
    ]


def read_mcp_resource(uri: str) -> str:
    """read_mcp_resource

    Args:
        uri: 조회할 resource URI.

    Returns:
        str: 리소스 문자열 콘텐츠.
    """
    resources = {
        "deadline://schema/users": json.dumps({"columns": ["id", "platform_user_id", "nickname", "timezone", "tone_preference", "created_at"], "purpose": "내부 사용자 저장"}, ensure_ascii=False),
        "deadline://schema/projects": json.dumps({"columns": ["id", "user_id", "title", "source_language", "target_language", "total_units", "completed_units", "deadline_at", "unit_label", "status", "created_at"], "purpose": "번역 프로젝트 저장"}, ensure_ascii=False),
        "deadline://schema/sessions": json.dumps({"columns": ["id", "user_id", "project_id", "mode", "duration_minutes", "status", "started_at", "ends_at", "ended_at", "reported_result", "completed_units_delta"], "purpose": "집중 세션 및 보고 저장"}, ensure_ascii=False),
    }
    if uri not in resources:
        raise KeyError(uri)
    return resources[uri]
