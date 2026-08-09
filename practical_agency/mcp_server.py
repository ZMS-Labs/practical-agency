"""Strict newline-delimited JSON-RPC bridge for the manifest controller."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

from practical_agency.controller import ControllerError, ManifestController


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_VERSION = "2025-03-26"
HOST_PROPERTIES = {
    "_host_context_ref": {"type": "string", "minLength": 1},
    "_host_gate_ref": {"type": "string", "minLength": 1},
}
STRING_LIST = {
    "type": "array",
    "minItems": 1,
    "items": {"type": "string", "minLength": 1},
}
DEFINITION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "instruction",
        "desired_state",
        "governed_artifacts",
        "permissions",
        "protected_state",
        "acceptable_costs",
        "escalation_required_for",
        "stop_conditions",
        "completion_acceptor",
    ],
    "properties": {
        "instruction": {"type": "string", "minLength": 1},
        "desired_state": {"type": "string", "minLength": 1},
        "governed_artifacts": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path", "content"],
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "content": {"type": "string"},
                },
            },
        },
        "permissions": STRING_LIST,
        "protected_state": STRING_LIST,
        "acceptable_costs": STRING_LIST,
        "escalation_required_for": STRING_LIST,
        "stop_conditions": STRING_LIST,
        "completion_acceptor": {"type": "string", "minLength": 1},
    },
}


def _closed_schema(
    properties: Mapping[str, Any], required: tuple[str, ...] = ()
) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {**properties, **HOST_PROPERTIES},
        "required": list(required),
    }


TOOLS = [
    {
        "name": "manifest_engage",
        "description": "Discover and reconcile the one durable mission in the host workspace.",
        "inputSchema": _closed_schema({}),
    },
    {
        "name": "manifest_define",
        "description": "Create one durable draft from a closed operator-facing definition.",
        "inputSchema": _closed_schema(
            {"definition": DEFINITION_SCHEMA}, ("definition",)
        ),
    },
    {
        "name": "manifest_authorize",
        "description": "Authorize exactly the durable authority contract named by its digest.",
        "inputSchema": _closed_schema(
            {
                "authority_contract_sha256": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                }
            },
            ("authority_contract_sha256",),
        ),
    },
    {
        "name": "manifest_dispatch",
        "description": "Dispatch the single bounded effect derived from durable mission state.",
        "inputSchema": _closed_schema({}),
    },
    {
        "name": "manifest_verify",
        "description": "Verify live artifact and receipt bindings using a typed verifier.",
        "inputSchema": _closed_schema(
            {"profile": {"type": "string", "enum": ["artifact-bindings"]}}
        ),
    },
    {
        "name": "manifest_accept",
        "description": "Record a non-steward acceptance verdict with honest separation assurance.",
        "inputSchema": _closed_schema(
            {
                "acceptor_ref": {"type": "string", "minLength": 1},
                "verdict": {"type": "string", "enum": ["PASS", "FAIL", "INCONCLUSIVE"]},
                "separation_assurance": {
                    "type": "string",
                    "enum": ["declared-role-separation", "externally-proven"],
                },
                "principal_evidence_ref": {"type": "string", "minLength": 1},
            },
            ("acceptor_ref", "verdict", "separation_assurance"),
        ),
    },
]
TOOL_BY_NAME = {tool["name"]: tool for tool in TOOLS}


class ProtocolError(RuntimeError):
    """A malformed or unsupported MCP protocol request."""


def _without_request_meta(params: object) -> object:
    if not isinstance(params, dict):
        return params
    if "_meta" not in params:
        return params
    if not isinstance(params["_meta"], dict):
        raise ProtocolError("MCP_PROTOCOL_ERROR")
    return {key: value for key, value in params.items() if key != "_meta"}


def _validate(value: object, schema: Mapping[str, Any]) -> bool:
    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(value, dict):
            return False
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, Mapping) or not all(key in value for key in required):
            return False
        if schema.get("additionalProperties") is False and not set(value).issubset(
            properties
        ):
            return False
        return all(
            key in properties and _validate(item, properties[key])
            for key, item in value.items()
        )
    if expected_type == "array":
        if not isinstance(value, list) or len(value) < int(schema.get("minItems", 0)):
            return False
        item_schema = schema.get("items")
        return isinstance(item_schema, Mapping) and all(
            _validate(item, item_schema) for item in value
        )
    if expected_type == "string":
        if not isinstance(value, str) or len(value) < int(schema.get("minLength", 0)):
            return False
        allowed = schema.get("enum")
        pattern = schema.get("pattern")
        if isinstance(allowed, list) and value not in allowed:
            return False
        if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
            return False
        return True
    return False


def _protocol_error(request_id: object) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": -32600,
            "message": "MCP_PROTOCOL_ERROR",
            "data": {"code": "MCP_PROTOCOL_ERROR"},
        },
    }


def _tool_result(payload: Mapping[str, Any], *, is_error: bool) -> dict[str, Any]:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "content": [{"type": "text", "text": encoded}],
        "structuredContent": dict(payload),
        "isError": is_error,
    }


class McpServer:
    def __init__(self, plugin_root: Path | str = PLUGIN_ROOT) -> None:
        self.controller = ManifestController(plugin_root=plugin_root)

    def _call_tool(self, params: object) -> dict[str, Any]:
        if not isinstance(params, dict) or set(params) != {"name", "arguments"}:
            raise ProtocolError("MCP_PROTOCOL_ERROR")
        name = params.get("name")
        arguments = params.get("arguments")
        if not isinstance(name, str) or name not in TOOL_BY_NAME:
            raise ProtocolError("MCP_PROTOCOL_ERROR")
        schema = TOOL_BY_NAME[name]["inputSchema"]
        if not _validate(arguments, schema):
            raise ProtocolError("MCP_PROTOCOL_ERROR")
        try:
            result = getattr(self.controller, name)(**arguments)
        except ControllerError as error:
            message = str(error) or "CONTROLLER_REFUSED"
            return _tool_result(
                {"code": message.split(":", 1)[0], "message": message},
                is_error=True,
            )
        return _tool_result(result, is_error=False)

    def handle(self, message: object) -> dict[str, Any] | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            raise ProtocolError("MCP_PROTOCOL_ERROR")
        if set(message) - {"jsonrpc", "id", "method", "params"}:
            raise ProtocolError("MCP_PROTOCOL_ERROR")
        method = message.get("method")
        params = _without_request_meta(message.get("params", {}))
        if not isinstance(method, str):
            raise ProtocolError("MCP_PROTOCOL_ERROR")
        if "id" not in message:
            if method == "notifications/initialized" and (
                params == {} or params is None
            ):
                return None
            raise ProtocolError("MCP_PROTOCOL_ERROR")
        request_id = message["id"]
        if method == "initialize":
            if not isinstance(params, dict):
                raise ProtocolError("MCP_PROTOCOL_ERROR")
            result = {
                "protocolVersion": str(params.get("protocolVersion", PROTOCOL_VERSION)),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": "practical-agency",
                    "version": "0.1.0",
                    "processInstanceId": self.controller.process_instance_id,
                },
            }
        elif method == "ping":
            if params != {}:
                raise ProtocolError("MCP_PROTOCOL_ERROR")
            result = {}
        elif method == "tools/list":
            if params != {}:
                raise ProtocolError("MCP_PROTOCOL_ERROR")
            result = {"tools": TOOLS}
        elif method == "tools/call":
            result = self._call_tool(params)
        else:
            raise ProtocolError("MCP_PROTOCOL_ERROR")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}


def serve() -> int:
    server = McpServer()
    for raw_line in sys.stdin:
        request_id: object = None
        try:
            message = json.loads(raw_line)
            if isinstance(message, dict):
                request_id = message.get("id")
            response = server.handle(message)
        except (json.JSONDecodeError, ProtocolError):
            response = _protocol_error(request_id)
        except Exception as error:  # pragma: no cover - fail-closed process boundary
            print(f"practical-agency mcp internal error: {type(error).__name__}", file=sys.stderr)
            response = _protocol_error(request_id)
        if response is not None:
            print(
                json.dumps(
                    response,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
