from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from practical_agency.host_evidence import write_host_context, write_host_gate


ROOT = Path(__file__).resolve().parents[1]
INITIALIZE_PARAMS = {
    "protocolVersion": "2025-03-26",
    "capabilities": {},
    "clientInfo": {"name": "practical-agency-tests", "version": "1"},
}
TOOL_NAMES = [
    "manifest_engage",
    "manifest_capability_request",
    "manifest_capability_issue",
    "manifest_capability_result",
    "manifest_capability_execute",
    "manifest_clarify",
    "manifest_define",
    "manifest_authorize",
    "manifest_dispatch",
    "manifest_verify",
    "manifest_accept",
]


class StdioServer:
    def __init__(self, cwd: Path) -> None:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(
            [str(ROOT), environment.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
        self.process = subprocess.Popen(
            [sys.executable, "-m", "practical_agency.mcp_server"],
            cwd=cwd,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.responses: queue.Queue[str] = queue.Queue()
        assert self.process.stdout is not None
        self.reader = threading.Thread(
            target=self._read_stdout,
            args=(self.process.stdout,),
            daemon=True,
        )
        self.reader.start()

    def _read_stdout(self, stream: object) -> None:
        for line in stream:  # type: ignore[union-attr]
            self.responses.put(line)

    def send(self, message: dict[str, object]) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def request(
        self, request_id: int, method: str, params: dict[str, object]
    ) -> dict[str, object]:
        self.send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        try:
            line = self.responses.get(timeout=5)
        except queue.Empty as error:
            stderr = ""
            if self.process.poll() is not None and self.process.stderr is not None:
                stderr = self.process.stderr.read()
            raise AssertionError(f"server produced no response: {stderr}") from error
        response = json.loads(line)
        self.assert_protocol_frame(response)
        if response.get("id") != request_id:
            raise AssertionError(f"unexpected response id: {response}")
        return response

    @staticmethod
    def assert_protocol_frame(response: object) -> None:
        if not isinstance(response, dict) or response.get("jsonrpc") != "2.0":
            raise AssertionError(f"stdout contained a non-protocol frame: {response!r}")

    def close(self) -> None:
        if self.process.stdin is not None:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5)
        if self.process.returncode != 0:
            stderr = self.process.stderr.read() if self.process.stderr else ""
            raise AssertionError(
                f"server exited with {self.process.returncode}: {stderr}"
            )
        if self.process.stdout is not None:
            self.process.stdout.close()
        if self.process.stderr is not None:
            self.process.stderr.close()

    def __enter__(self) -> "StdioServer":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class McpServerProcessTests(unittest.TestCase):
    def _workspace(self, temp: str) -> Path:
        workspace = Path(temp) / "workspace"
        workspace.mkdir()
        (workspace / ".git").mkdir()
        return workspace

    def test_real_stdio_server_initializes_and_lists_only_manifest_operations(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            with StdioServer(workspace) as server:
                initialized = server.request(1, "initialize", INITIALIZE_PARAMS)
                server_info = initialized["result"]["serverInfo"]
                self.assertEqual(server_info["name"], "practical-agency")
                self.assertTrue(server_info["processInstanceId"])

                server.send(
                    {"jsonrpc": "2.0", "method": "notifications/initialized"}
                )
                pinged = server.request(2, "ping", {})
                self.assertEqual(pinged["result"], {})

                listed = server.request(3, "tools/list", {})
                tools = listed["result"]["tools"]
                self.assertEqual([tool["name"] for tool in tools], TOOL_NAMES)
                for tool in tools:
                    schema = tool["inputSchema"]
                    self.assertFalse(schema["additionalProperties"])
                    self.assertNotIn("workspace_root", schema["properties"])
                    self.assertNotIn("mission_id", schema["properties"])
                    self.assertIn("_host_context_ref", schema["properties"])
                    self.assertIn("_host_gate_ref", schema["properties"])

    def test_successful_tool_call_uses_hook_injected_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            context = write_host_context(
                workspace_root=workspace,
                prompt="$manifest start a mission",
                session_id="session-mcp",
                turn_id="turn-engage",
                plugin_root=ROOT,
            )
            gate = write_host_gate(
                context_ref=context.path,
                tool_name="mcp__practical_agency__manifest_engage",
                tool_use_id="tool-engage",
                session_id="session-mcp",
                turn_id="turn-engage",
                workspace_root=workspace,
                lock_reason="explicit-manifest-intent",
                decision="allow-controller",
                plugin_root=ROOT,
            )

            with StdioServer(workspace) as server:
                response = server.request(
                    1,
                    "tools/call",
                    {
                        "name": "manifest_engage",
                        "arguments": {
                            "_host_context_ref": context.path,
                            "_host_gate_ref": gate.path,
                        },
                    },
                )

                result = response["result"]
                self.assertFalse(result["isError"])
                self.assertEqual(
                    result["structuredContent"]["status"],
                    "MISSION_DEFINITION_REQUIRED",
                )
                self.assertTrue(result["structuredContent"]["process_instance_id"])

    def test_tool_call_returns_named_refusal_without_advancing_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            with StdioServer(workspace) as server:
                response = server.request(
                    1,
                    "tools/call",
                    {"name": "manifest_dispatch", "arguments": {}},
                )

                result = response["result"]
                self.assertTrue(result["isError"])
                self.assertEqual(
                    result["structuredContent"]["code"], "HOST_GATE_UNAVAILABLE"
                )
                self.assertEqual(list(workspace.glob("missions/*/checkpoints/*.json")), [])

    def test_codex_request_metadata_is_allowed_on_tool_listing_and_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            with StdioServer(workspace) as server:
                listed = server.request(
                    1,
                    "tools/list",
                    {"_meta": {"progressToken": 0}},
                )
                self.assertEqual(
                    [tool["name"] for tool in listed["result"]["tools"]],
                    TOOL_NAMES,
                )

                called = server.request(
                    2,
                    "tools/call",
                    {
                        "name": "manifest_dispatch",
                        "arguments": {},
                        "_meta": {"progressToken": 1},
                    },
                )
                self.assertEqual(
                    called["result"]["structuredContent"]["code"],
                    "HOST_GATE_UNAVAILABLE",
                )

    def test_unknown_method_and_malformed_tool_arguments_fail_as_protocol_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            with StdioServer(workspace) as server:
                unknown = server.request(1, "resources/list", {})
                self.assertEqual(
                    unknown["error"]["data"]["code"], "MCP_PROTOCOL_ERROR"
                )

                malformed = server.request(
                    2,
                    "tools/call",
                    {"name": "manifest_dispatch", "arguments": {"path": "escape"}},
                )
                self.assertEqual(
                    malformed["error"]["data"]["code"], "MCP_PROTOCOL_ERROR"
                )


if __name__ == "__main__":
    unittest.main()
