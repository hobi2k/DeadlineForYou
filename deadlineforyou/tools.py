from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


ToolExecutor = Callable[[dict[str, Any]], dict[str, Any]]

EMPTY_OBJECT_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}
SESSION_COMMON_PROPERTIES = {
    "duration_minutes": {"type": "integer", "minimum": 1, "maximum": 180},
}
SESSION_COMPLETE_PROPERTIES = {
    "session_id": {"type": "integer"},
    "completed_units_delta": {"type": "integer", "minimum": 0},
    "result_text": {"type": "string"},
}
TRANSLATION_PROPERTIES = {
    "text": {"type": "string"},
    "source_language": {"type": "string"},
    "target_language": {"type": "string"},
    "style": {"type": "string"},
}
IMAGE_PROPERTIES = {
    "prompt": {"type": "string"},
    "size": {"type": "string"},
    "style": {"type": "string"},
}


@dataclass(slots=True)
class DeadlineTool:
    name: str
    description: str
    parameters: dict[str, Any]
    execute: ToolExecutor

    def tool_call_schema(self) -> dict[str, Any]:
        """tool_call_schema

        Args:
            없음.

        Returns:
            dict[str, Any]: tool calling 형식에 맞춘 함수 스키마.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

@dataclass(slots=True)
class ToolContext:
    service: Any
    user_id: int
    project_id: int | None = None


def _session_start_result(session: dict, duration_minutes: int, include_instruction: bool) -> dict[str, Any]:
    """_session_start_result

    Args:
        session: 생성된 세션 레코드.
        duration_minutes: 시작한 세션 길이.
        include_instruction: 채팅용 안내 문구 포함 여부.

    Returns:
        dict[str, Any]: 세션 시작 결과 페이로드.
    """
    payload: dict[str, Any] = {"session": session}
    if include_instruction:
        payload["instruction"] = f"{duration_minutes}분 세션을 시작했다. 끝나면 보고를 요구하라."
    return payload


def _session_complete_result(session: dict | None, include_instruction: bool) -> dict[str, Any]:
    """_session_complete_result

    Args:
        session: 완료 처리된 세션 레코드.
        include_instruction: 채팅용 안내 문구 포함 여부.

    Returns:
        dict[str, Any]: 세션 완료 결과 페이로드.
    """
    if session is None:
        return {"error": "session_not_found"}

    payload: dict[str, Any] = {"session": session}
    if include_instruction:
        payload["instruction"] = "완료 처리 결과를 반영해 다음 작업을 바로 제시하라."
    return payload


def _translate(service: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    """_translate

    Args:
        service: DeadlineCoachService 인스턴스.
        arguments: 번역 도구 인자.

    Returns:
        dict[str, Any]: 번역 결과.
    """
    return service.translate_text(
        text=str(arguments["text"]),
        source_language=str(arguments.get("source_language", "ja")),
        target_language=str(arguments.get("target_language", "ko")),
        style=str(arguments.get("style", "natural")),
    )


def _generate_image(service: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    """_generate_image

    Args:
        service: DeadlineCoachService 인스턴스.
        arguments: 이미지 생성 도구 인자.

    Returns:
        dict[str, Any]: 이미지 생성 결과.
    """
    return service.generate_image(
        prompt=str(arguments["prompt"]),
        size=str(arguments.get("size", "512x512")),
        style=str(arguments.get("style", "illustration")),
    )


def _tool_parameter_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    """_tool_parameter_schema

    Args:
        properties: JSON Schema의 속성 정의.
        required: 필수 속성 이름 목록.

    Returns:
        dict[str, Any]: 공통 형식의 도구 인자 스키마.
    """
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _build_chat_tool_specs(context: ToolContext) -> list[DeadlineTool]:
    """_build_chat_tool_specs

    Args:
        context: 현재 사용자 문맥이 바인딩된 도구 컨텍스트.

    Returns:
        list[DeadlineTool]: 채팅 루프에서 사용할 도구 목록.
    """

    def get_active_project(_: dict[str, Any]) -> dict[str, Any]:
        project = context.service.get_active_project(context.user_id, context.project_id)
        return project or {"active_project": None}

    def start_focus_session(arguments: dict[str, Any]) -> dict[str, Any]:
        duration_minutes = int(arguments.get("duration_minutes", 10))
        project = context.service.get_active_project(context.user_id, context.project_id)
        session = context.service.start_session(
            context.user_id,
            project["id"] if project else None,
            duration_minutes,
            "timer",
        )
        return _session_start_result(session, duration_minutes, include_instruction=True)

    def complete_focus_session(arguments: dict[str, Any]) -> dict[str, Any]:
        session = context.service.complete_session(
            int(arguments["session_id"]),
            str(arguments.get("result_text", "세션 완료")),
            int(arguments.get("completed_units_delta", 0)),
        )
        return _session_complete_result(session, include_instruction=True)

    def get_daily_report(_: dict[str, Any]) -> dict[str, Any]:
        return context.service.build_daily_report(context.user_id)

    def list_projects(_: dict[str, Any]) -> dict[str, Any]:
        return {"projects": context.service.list_projects(context.user_id)}

    return [
        DeadlineTool(
            name="get_active_project",
            description="현재 사용자의 활성 번역 프로젝트 상태를 조회한다.",
            parameters=EMPTY_OBJECT_SCHEMA,
            execute=get_active_project,
        ),
        DeadlineTool(
            name="start_focus_session",
            description="집중 세션을 시작하고 세션 ID와 종료 시각을 반환한다.",
            parameters=_tool_parameter_schema(SESSION_COMMON_PROPERTIES, ["duration_minutes"]),
            execute=start_focus_session,
        ),
        DeadlineTool(
            name="complete_focus_session",
            description="세션을 완료 처리하고 프로젝트 진행량을 반영한다.",
            parameters=_tool_parameter_schema(SESSION_COMPLETE_PROPERTIES, ["session_id"]),
            execute=complete_focus_session,
        ),
        DeadlineTool(
            name="get_daily_report",
            description="현재 사용자의 오늘 리포트를 조회한다.",
            parameters=EMPTY_OBJECT_SCHEMA,
            execute=get_daily_report,
        ),
        DeadlineTool(
            name="list_projects",
            description="현재 사용자의 프로젝트 목록을 조회한다.",
            parameters=EMPTY_OBJECT_SCHEMA,
            execute=list_projects,
        ),
        DeadlineTool(
            name="translate_text",
            description="짧은 텍스트를 번역한다.",
            parameters=_tool_parameter_schema(TRANSLATION_PROPERTIES, ["text"]),
            execute=lambda arguments: _translate(context.service, arguments),
        ),
        DeadlineTool(
            name="generate_image",
            description="프롬프트 기반 이미지를 생성한다. 별도 이미지 provider가 필요하다.",
            parameters=_tool_parameter_schema(IMAGE_PROPERTIES, ["prompt"]),
            execute=lambda arguments: _generate_image(context.service, arguments),
        ),
    ]


def _tool_map(tools: list[DeadlineTool]) -> dict[str, DeadlineTool]:
    """_tool_map

    Args:
        tools: 도구 객체 목록.

    Returns:
        dict[str, DeadlineTool]: 이름 기준 도구 매핑.
    """
    return {tool.name: tool for tool in tools}


def build_bound_chat_tools(service: Any, user_id: int, project_id: int | None) -> dict[str, DeadlineTool]:
    """build_bound_chat_tools

    Args:
        service: DeadlineCoachService 인스턴스.
        user_id: 현재 대화 사용자 식별자.
        project_id: 현재 대화에 연결된 프로젝트 식별자.

    Returns:
        dict[str, DeadlineTool]: 현재 사용자 문맥에 묶인 tool registry.
    """
    return _tool_map(_build_chat_tool_specs(ToolContext(service=service, user_id=user_id, project_id=project_id)))
