from __future__ import annotations

import json
import sys
from typing import Any

from deadlineforyou.config import get_settings
from deadlineforyou.providers import build_provider
from deadlineforyou.service import DeadlineCoachService
from deadlineforyou.storage import Database
from deadlineforyou.tools import build_mcp_resources, build_mcp_tools, read_mcp_resource


def build_service() -> DeadlineCoachService:
    """build_service

    Args:
        없음.

    Returns:
        DeadlineCoachService: MCP 서버가 사용할 서비스 인스턴스.
    """
    settings = get_settings()
    database = Database(settings.database_path)
    provider = build_provider(settings)
    return DeadlineCoachService(database, provider)


class MCPServer:
    def __init__(self, service: DeadlineCoachService) -> None:
        """__init__

        Args:
            service: DeadlineCoachService 인스턴스.

        Returns:
            None: stdio 기반 MCP 서버 상태를 초기화한다.
        """
        self.service = service
        self.tools = build_mcp_tools(service)
        self.resources = build_mcp_resources(service)

    def handle(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """handle

        Args:
            payload: 입력 JSON-RPC 메시지.

        Returns:
            dict[str, Any] | None: 응답 메시지. notification이면 None.
        """
        method = payload.get("method")
        msg_id = payload.get("id")
        params = payload.get("params", {})

        if method == "initialize":
            return self._response(
                msg_id,
                {
                    "protocolVersion": "2025-06-18",
                    "serverInfo": {"name": "deadlineforyou-mcp", "version": "0.1.0"},
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"listChanged": False, "subscribe": False},
                        "prompts": {"listChanged": False},
                    },
                },
            )
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return self._response(msg_id, {"tools": [tool.mcp_schema() for tool in self.tools.values()]})
        if method == "tools/call":
            name = params["name"]
            arguments = params.get("arguments", {})
            tool = self.tools.get(name)
            if tool is None:
                return self._error(msg_id, -32601, f"Unknown tool: {name}")
            try:
                result = tool.execute(arguments)
            except Exception as exc:  # noqa: BLE001
                return self._error(msg_id, -32000, str(exc))
            return self._response(
                msg_id,
                {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}], "isError": False},
            )
        if method == "resources/list":
            return self._response(msg_id, {"resources": self.resources})
        if method == "resources/read":
            uri = params["uri"]
            try:
                content = read_mcp_resource(uri)
            except KeyError:
                return self._error(msg_id, -32001, f"Unknown resource: {uri}")
            return self._response(
                msg_id,
                {"contents": [{"uri": uri, "mimeType": "application/json", "text": content}]},
            )
        if method == "prompts/list":
            return self._response(
                msg_id,
                {
                    "prompts": [
                        {
                            "name": "force_start_coaching",
                            "title": "force_start_coaching",
                            "description": "작업 강제 시작형 코칭 템플릿",
                            "arguments": [{"name": "user_message", "required": True}],
                        }
                    ]
                },
            )
        if method == "prompts/get":
            if params["name"] != "force_start_coaching":
                return self._error(msg_id, -32002, f"Unknown prompt: {params['name']}")
            user_message = next((item["value"] for item in params.get("arguments", []) if item["name"] == "user_message"), "")
            return self._response(
                msg_id,
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": {
                                "type": "text",
                                "text": f"사용자 메시지: {user_message}\n지금 당장 시작하게 만드는 강제 시작형 코칭을 생성하라.",
                            },
                        }
                    ]
                },
            )
        return self._error(msg_id, -32601, f"Unknown method: {method}")

    def _response(self, msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        """_response

        Args:
            msg_id: JSON-RPC 요청 ID.
            result: 응답 result 객체.

        Returns:
            dict[str, Any]: JSON-RPC 성공 응답.
        """
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def _error(self, msg_id: Any, code: int, message: str) -> dict[str, Any]:
        """_error

        Args:
            msg_id: JSON-RPC 요청 ID.
            code: JSON-RPC 오류 코드.
            message: 오류 메시지.

        Returns:
            dict[str, Any]: JSON-RPC 오류 응답.
        """
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def main() -> None:
    """main

    Args:
        없음.

    Returns:
        None: stdio 루프를 시작해 MCP JSON-RPC 메시지를 처리한다.
    """
    server = MCPServer(build_service())
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
            response = server.handle(payload)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except Exception as exc:  # noqa: BLE001
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32099, "message": str(exc)}}, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
