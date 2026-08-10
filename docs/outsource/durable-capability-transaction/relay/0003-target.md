schema: outsource-relay@1
work_id: durable-capability-transaction
based_on_commit: 578cb9ee3165c899af26da1111163effa19949fc
status: PARTIAL
summary: |
  Stage 1 is complete as a tests-only advisory patch. One focused test module adds 13 adversarial tests covering all DCT requirements through real controller, checkpoint, state-machine, and MCP paths, with mocks restricted to underlying file and network observation seams. The repository was not modified and no tests or runtime probes were executed.
work_product: |
  diff --git a/tests/test_durable_capability_transaction.py b/tests/test_durable_capability_transaction.py
  new file mode 100644
  --- /dev/null
  +++ b/tests/test_durable_capability_transaction.py
  @@ -0,0 +1,872 @@
  +from __future__ import annotations
  +
  +import json
  +import re
  +import shutil
  +import socket
  +import tempfile
  +import unittest
  +from collections.abc import Mapping
  +from contextlib import contextmanager
  +from copy import deepcopy
  +from pathlib import Path
  +from typing import Any
  +from unittest.mock import patch
  +
  +import practical_agency.capability_operations as capability_operations
  +from practical_agency.checkpoint_store import FileCheckpointStore
  +from practical_agency.controller import ControllerError, ManifestController
  +from practical_agency.host_evidence import write_host_context, write_host_gate
  +from practical_agency.manifest_model import MissionManifest
  +from practical_agency.mcp_server import McpServer, ProtocolError
  +from practical_agency.mission_repository import discover_active_mission
  +from practical_agency.state_machine import TransitionError, apply_event_data
  +from tests.helpers import minimal_payload, record_fixture_verifier_result
  +
  +
  +ROOT = Path(__file__).resolve().parents[1]
  +
  +
  +def _type_ok(value: object, expected: object) -> bool:
  +    if isinstance(expected, list):
  +        return any(_type_ok(value, item) for item in expected)
  +    checks = {
  +        "object": lambda: isinstance(value, dict),
  +        "array": lambda: isinstance(value, list),
  +        "string": lambda: isinstance(value, str),
  +        "integer": lambda: isinstance(value, int) and not isinstance(value, bool),
  +        "boolean": lambda: isinstance(value, bool),
  +        "null": lambda: value is None,
  +    }
  +    return checks.get(str(expected), lambda: True)()
  +
  +
  +def _schema_errors(value: object, schema: Mapping[str, Any], path: str = "$") -> list[str]:
  +    errors: list[str] = []
  +    if "const" in schema and value != schema["const"]:
  +        errors.append(f"{path}: const")
  +    if isinstance(schema.get("enum"), list) and value not in schema["enum"]:
  +        errors.append(f"{path}: enum")
  +    if "type" in schema and not _type_ok(value, schema["type"]):
  +        return [*errors, f"{path}: type"]
  +
  +    if isinstance(value, dict):
  +        properties = schema.get("properties", {})
  +        required = schema.get("required", [])
  +        if isinstance(required, list):
  +            errors.extend(
  +                f"{path}: missing {key}" for key in required if key not in value
  +            )
  +        if schema.get("additionalProperties") is False and isinstance(
  +            properties, Mapping
  +        ):
  +            errors.extend(
  +                f"{path}: extra {key}" for key in value if key not in properties
  +            )
  +        if isinstance(properties, Mapping):
  +            for key, child in value.items():
  +                if isinstance(properties.get(key), Mapping):
  +                    errors.extend(
  +                        _schema_errors(child, properties[key], f"{path}.{key}")
  +                    )
  +
  +    if isinstance(value, list):
  +        minimum = schema.get("minItems")
  +        if isinstance(minimum, int) and len(value) < minimum:
  +            errors.append(f"{path}: minItems")
  +        if isinstance(schema.get("items"), Mapping):
  +            for index, child in enumerate(value):
  +                errors.extend(
  +                    _schema_errors(child, schema["items"], f"{path}[{index}]")
  +                )
  +
  +    if isinstance(value, str):
  +        minimum = schema.get("minLength")
  +        if isinstance(minimum, int) and len(value) < minimum:
  +            errors.append(f"{path}: minLength")
  +        pattern = schema.get("pattern")
  +        if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
  +            errors.append(f"{path}: pattern")
  +
  +    if isinstance(value, int) and not isinstance(value, bool):
  +        minimum = schema.get("minimum")
  +        if isinstance(minimum, int) and value < minimum:
  +            errors.append(f"{path}: minimum")
  +    return errors
  +
  +
  +class _HttpResponse:
  +    status = 200
  +
  +    def __init__(self, url: str) -> None:
  +        self.url = url
  +
  +    def __enter__(self) -> "_HttpResponse":
  +        return self
  +
  +    def __exit__(self, *_: object) -> None:
  +        return None
  +
  +    def geturl(self) -> str:
  +        return self.url
  +
  +    def read(self) -> bytes:
  +        return b"network observation"
  +
  +
  +class DurableCapabilityTransactionRedTests(unittest.TestCase):
  +    def _runtime(self, base: Path) -> Path:
  +        runtime = base / "runtime"
  +        shutil.copytree(ROOT / "hooks", runtime / "hooks")
  +        shutil.copytree(
  +            ROOT / "practical_agency",
  +            runtime / "practical_agency",
  +            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
  +        )
  +        shutil.copytree(ROOT / "skills", runtime / "skills")
  +        descriptor = runtime / "skills" / "dynamic-reader" / "SKILL.md"
  +        descriptor.parent.mkdir(parents=True)
  +        descriptor.write_text(
  +            "---\n"
  +            "name: dynamic-reader\n"
  +            "description: Observe one bounded source without mutation.\n"
  +            "metadata:\n"
  +            "  kind: skill\n"
  +            "  persistence: session\n"
  +            "  independence: actor\n"
  +            "  authority_required: [repository:read]\n"
  +            "  input_contract: contracts/capability-request.schema.json\n"
  +            "  output_contract: contracts/capability-result.schema.json\n"
  +            "---\n\n# Dynamic reader\n",
  +            encoding="utf-8",
  +        )
  +        return runtime
  +
  +    def _setup(
  +        self,
  +        base: Path,
  +        *,
  +        permissions: list[str] | None = None,
  +        protected_state: list[str] | None = None,
  +        acceptable_costs: list[str] | None = None,
  +        escalation_required_for: list[str] | None = None,
  +    ) -> tuple[Path, Path, ManifestController]:
  +        runtime = self._runtime(base)
  +        workspace = base / "workspace"
  +        workspace.mkdir()
  +        (workspace / ".git").mkdir()
  +        (workspace / "evidence.txt").write_text("authorized evidence", encoding="utf-8")
  +        (workspace / "secret.txt").write_text("out-of-scope secret", encoding="utf-8")
  +
  +        payload = minimal_payload()
  +        payload["mission_id"] = "durable-capability-mission"
  +        payload["revision"] = 1
  +        payload["authority"]["permissions"] = list(
  +            permissions or ["repository:read", "network:read"]
  +        )
  +        payload["authority"]["protected_state"] = list(
  +            protected_state or ["mutation:any"]
  +        )
  +        payload["authority"]["acceptable_costs"] = list(
  +            acceptable_costs or ["bounded reads"]
  +        )
  +        payload["authority"]["escalation_required_for"] = list(
  +            escalation_required_for or ["mutation:any"]
  +        )
  +        payload["state"] = {
  +            "status": "active",
  +            "completed_actions": [],
  +            "current_frontier": ["inspect the bounded evidence"],
  +            "blockers": [],
  +            "next_action": "inspect the bounded evidence",
  +        }
  +        payload["continuity"]["prior_checkpoint"] = "fixture:capability-r1"
  +        payload["integrity"]["completion_acceptor"] = "reviewer:independent"
  +        manifest = MissionManifest.from_dict(payload)
  +        FileCheckpointStore(
  +            workspace / "missions" / manifest.mission_id / "checkpoints"
  +        ).save(manifest)
  +        return runtime, workspace, ManifestController(plugin_root=runtime)
  +
  +    def _refs(
  +        self, workspace: Path, runtime: Path, operation: str, turn: str
  +    ) -> dict[str, str]:
  +        context = write_host_context(
  +            workspace_root=workspace,
  +            prompt="$manifest exercise the durable capability transaction",
  +            session_id="dct-red",
  +            turn_id=turn,
  +            plugin_root=runtime,
  +        )
  +        gate = write_host_gate(
  +            context_ref=context.path,
  +            tool_name=f"mcp__practical_agency__{operation}",
  +            tool_use_id=f"tool-{turn}",
  +            session_id="dct-red",
  +            turn_id=turn,
  +            workspace_root=workspace,
  +            lock_reason="explicit-manifest-intent",
  +            decision="allow-controller",
  +            plugin_root=runtime,
  +        )
  +        return {"_host_context_ref": context.path, "_host_gate_ref": gate.path}
  +
  +    @staticmethod
  +    def _intent(operation: str, target: str) -> dict[str, object]:
  +        permission = "network:read" if operation.startswith("web.") else "repository:read"
  +        return {
  +            "bounded_question_or_action": f"{operation}:{target}",
  +            "requested_permissions": [permission],
  +            "requested_effects": [target],
  +            "estimated_costs": ["bounded reads"],
  +            "timeout_or_stop_condition": "stop after one bounded observation",
  +        }
  +
  +    def _issue(
  +        self,
  +        controller: ManifestController,
  +        workspace: Path,
  +        runtime: Path,
  +        *,
  +        operation: str = "file.read",
  +        target: str = "evidence.txt",
  +        scope: list[str] | None = None,
  +        turn: str = "issue",
  +    ) -> dict[str, Any]:
  +        return controller.manifest_capability_issue(
  +            capability_id="dynamic-reader",
  +            blocking_condition="inspect the bounded evidence",
  +            admitted_operation=operation,
  +            evidence_scope=list(scope or [target]),
  +            request=self._intent(operation, target),
  +            **self._refs(
  +                workspace, runtime, "manifest_capability_issue", turn
  +            ),
  +        )
  +
  +    @staticmethod
  +    def _grant_id(issued: Mapping[str, Any]) -> str:
  +        if isinstance(issued.get("grant_id"), str):
  +            return str(issued["grant_id"])
  +        grant = issued.get("grant")
  +        if isinstance(grant, Mapping) and isinstance(grant.get("grant_id"), str):
  +            return str(grant["grant_id"])
  +        raise AssertionError(f"missing grant_id: {issued!r}")
  +
  +    @staticmethod
  +    def _legacy_grant(issued: Mapping[str, Any]) -> dict[str, Any] | None:
  +        grant = issued.get("grant")
  +        return deepcopy(dict(grant)) if isinstance(grant, Mapping) else None
  +
  +    def _execute(
  +        self,
  +        controller: ManifestController,
  +        workspace: Path,
  +        runtime: Path,
  +        issued: Mapping[str, Any],
  +        *,
  +        operation: str,
  +        target: str,
  +        refs: list[str] | None = None,
  +        evidence: Mapping[str, str] | None = None,
  +        legacy_grant: Mapping[str, Any] | None = None,
  +        turn: str,
  +    ) -> dict[str, Any]:
  +        arguments = {
  +            "operation": operation,
  +            "target": target,
  +            "evidence_refs": list(refs or [target]),
  +            "evidence_payload": dict(evidence) if evidence is not None else None,
  +            **self._refs(
  +                workspace, runtime, "manifest_capability_execute", turn
  +            ),
  +        }
  +        try:
  +            return controller.manifest_capability_execute(
  +                grant_id=self._grant_id(issued), **arguments
  +            )
  +        except TypeError as error:
  +            if "unexpected keyword argument 'grant_id'" not in str(error):
  +                raise
  +            grant = (
  +                deepcopy(dict(legacy_grant))
  +                if isinstance(legacy_grant, Mapping)
  +                else self._legacy_grant(issued)
  +            )
  +            if grant is None:
  +                raise
  +            return controller.manifest_capability_execute(grant=grant, **arguments)
  +
  +    @staticmethod
  +    def _record(manifest: MissionManifest, grant_id: str) -> Mapping[str, Any]:
  +        records = [
  +            item
  +            for item in manifest.capabilities.get("invoked", [])
  +            if isinstance(item, Mapping) and item.get("grant_id") == grant_id
  +        ]
  +        if len(records) != 1:
  +            raise AssertionError(f"expected one transaction {grant_id}: {records!r}")
  +        return records[0]
  +
  +    @contextmanager
  +    def _count_reads(self, *targets: Path):
  +        calls: list[str] = []
  +        expected = {target.resolve() for target in targets}
  +        original = Path.read_text
  +
  +        def counted(path: Path, *args: object, **kwargs: object) -> str:
  +            if path.resolve() in expected:
  +                calls.append(str(path))
  +            return original(path, *args, **kwargs)
  +
  +        with patch.object(Path, "read_text", new=counted):
  +            yield calls
  +
  +    @staticmethod
  +    def _mcp_call(
  +        server: McpServer, request_id: int, name: str, arguments: Mapping[str, Any]
  +    ) -> tuple[dict[str, Any] | None, ProtocolError | None]:
  +        try:
  +            response = server.handle(
  +                {
  +                    "jsonrpc": "2.0",
  +                    "id": request_id,
  +                    "method": "tools/call",
  +                    "params": {"name": name, "arguments": dict(arguments)},
  +                }
  +            )
  +        except ProtocolError as error:
  +            return None, error
  +        if not isinstance(response, dict):
  +            raise AssertionError(f"MCP returned no response for {name}")
  +        return response, None
  +
  +    @staticmethod
  +    def _tools(server: McpServer) -> dict[str, Mapping[str, Any]]:
  +        response = server.handle(
  +            {"jsonrpc": "2.0", "id": 99, "method": "tools/list", "params": {}}
  +        )
  +        if not isinstance(response, Mapping):
  +            raise AssertionError("MCP tools/list returned no response")
  +        return {
  +            str(tool["name"]): tool for tool in response["result"]["tools"]
  +        }
  +
  +    def test_forged_same_id_wider_scope_refuses_before_file_observation(self) -> None:
  +        with tempfile.TemporaryDirectory() as temp:
  +            runtime, workspace, controller = self._setup(Path(temp))
  +            issued = self._issue(controller, workspace, runtime)
  +            forged = self._legacy_grant(issued) or {
  +                "grant_id": self._grant_id(issued),
  +                "evidence_scope": [],
  +            }
  +            forged["evidence_scope"] = ["secret.txt"]
  +            refusal = None
  +            with self._count_reads(
  +                workspace / "evidence.txt", workspace / "secret.txt"
  +            ) as reads:
  +                try:
  +                    self._execute(
  +                        controller,
  +                        workspace,
  +                        runtime,
  +                        issued,
  +                        operation="file.read",
  +                        target="secret.txt",
  +                        refs=["secret.txt"],
  +                        legacy_grant=forged,
  +                        turn="forged-scope",
  +                    )
  +                except ControllerError as error:
  +                    refusal = error
  +
  +            latest = discover_active_mission(workspace).manifest
  +            result = self._record(latest, self._grant_id(issued)).get("result")
  +            self.assertEqual(reads, [])
  +            self.assertFalse(
  +                isinstance(result, Mapping) and result.get("status") == "completed"
  +            )
  +            self.assertEqual(str(refusal), "TARGET_NOT_IN_EVIDENCE_SCOPE")
  +
  +    def test_stale_descriptor_refuses_before_file_observation(self) -> None:
  +        with tempfile.TemporaryDirectory() as temp:
  +            runtime, workspace, controller = self._setup(Path(temp))
  +            issued = self._issue(controller, workspace, runtime)
  +            descriptor = runtime / "skills" / "dynamic-reader" / "SKILL.md"
  +            descriptor.write_text(
  +                descriptor.read_text(encoding="utf-8") + "\nDescriptor drift.\n",
  +                encoding="utf-8",
  +            )
  +            refusal = None
  +            with self._count_reads(workspace / "evidence.txt") as reads:
  +                try:
  +                    self._execute(
  +                        controller,
  +                        workspace,
  +                        runtime,
  +                        issued,
  +                        operation="file.read",
  +                        target="evidence.txt",
  +                        refs=["evidence.txt"],
  +                        turn="stale-descriptor",
  +                    )
  +                except ControllerError as error:
  +                    refusal = error
  +
  +            latest = discover_active_mission(workspace).manifest
  +            result = self._record(latest, self._grant_id(issued)).get("result")
  +            self.assertEqual(reads, [])
  +            self.assertFalse(
  +                isinstance(result, Mapping) and result.get("status") == "completed"
  +            )
  +            self.assertEqual(str(refusal), "CAPABILITY_DESCRIPTOR_MISMATCH")
  +
  +    def test_missing_authority_refuses_before_file_observation(self) -> None:
  +        scenarios = [
  +            (
  +                {"permissions": ["network:read"]},
  +                "PERMISSION_NOT_GRANTED:repository:read",
  +            ),
  +            (
  +                {"protected_state": ["evidence.txt"]},
  +                "PROTECTED_STATE_VIOLATION:evidence.txt",
  +            ),
  +            (
  +                {"acceptable_costs": ["one local write"]},
  +                "COST_NOT_AUTHORIZED:bounded reads",
  +            ),
  +            (
  +                {"escalation_required_for": ["evidence.txt"]},
  +                "ESCALATION_REQUIRED:evidence.txt",
  +            ),
  +        ]
  +        for overrides, expected in scenarios:
  +            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp:
  +                runtime, workspace, controller = self._setup(
  +                    Path(temp), **overrides
  +                )
  +                refusal = None
  +                with self._count_reads(workspace / "evidence.txt") as reads:
  +                    try:
  +                        issued = self._issue(controller, workspace, runtime)
  +                        self._execute(
  +                            controller,
  +                            workspace,
  +                            runtime,
  +                            issued,
  +                            operation="file.read",
  +                            target="evidence.txt",
  +                            refs=["evidence.txt"],
  +                            turn=f"authority-{expected.split(':')[0]}",
  +                        )
  +                    except ControllerError as error:
  +                        refusal = error
  +
  +                latest = discover_active_mission(workspace).manifest
  +                self.assertEqual(reads, [])
  +                self.assertEqual(str(refusal), expected)
  +                for item in latest.capabilities.get("invoked", []):
  +                    if isinstance(item, Mapping) and isinstance(
  +                        item.get("result"), Mapping
  +                    ):
  +                        self.assertEqual(
  +                            item["result"].get("observed_effects", []), []
  +                        )
  +
  +    def test_valid_local_read_requires_canonical_grant_id_and_one_observation(self) -> None:
  +        with tempfile.TemporaryDirectory() as temp:
  +            runtime, workspace, controller = self._setup(Path(temp))
  +            issued = self._issue(controller, workspace, runtime)
  +            response = None
  +            call_error = None
  +            with self._count_reads(workspace / "evidence.txt") as reads:
  +                try:
  +                    response = controller.manifest_capability_execute(
  +                        grant_id=self._grant_id(issued),
  +                        operation="file.read",
  +                        target="evidence.txt",
  +                        evidence_refs=["evidence.txt"],
  +                        evidence_payload=None,
  +                        **self._refs(
  +                            workspace,
  +                            runtime,
  +                            "manifest_capability_execute",
  +                            "valid-grant-id",
  +                        ),
  +                    )
  +                except (TypeError, ControllerError) as error:
  +                    call_error = error
  +
  +            record = self._record(
  +                discover_active_mission(workspace).manifest,
  +                self._grant_id(issued),
  +            )
  +            self.assertIsNone(call_error)
  +            self.assertIsNotNone(response)
  +            self.assertEqual(len(reads), 1)
  +            self.assertIsInstance(record.get("result"), Mapping)
  +
  +    def test_fresh_copy_replay_after_controller_replacement_observes_once(self) -> None:
  +        with tempfile.TemporaryDirectory() as temp:
  +            runtime, workspace, first = self._setup(Path(temp))
  +            issued = self._issue(first, workspace, runtime)
  +            replay_payload = deepcopy(dict(issued))
  +            legacy = self._legacy_grant(issued)
  +            refusal = None
  +            with self._count_reads(workspace / "evidence.txt") as reads:
  +                self._execute(
  +                    first,
  +                    workspace,
  +                    runtime,
  +                    issued,
  +                    operation="file.read",
  +                    target="evidence.txt",
  +                    refs=["evidence.txt"],
  +                    legacy_grant=deepcopy(legacy),
  +                    turn="first-execution",
  +                )
  +                first_result = deepcopy(
  +                    self._record(
  +                        discover_active_mission(workspace).manifest,
  +                        self._grant_id(issued),
  +                    ).get("result")
  +                )
  +                replacement = ManifestController(plugin_root=runtime)
  +                try:
  +                    self._execute(
  +                        replacement,
  +                        workspace,
  +                        runtime,
  +                        replay_payload,
  +                        operation="file.read",
  +                        target="evidence.txt",
  +                        refs=["evidence.txt"],
  +                        legacy_grant=deepcopy(legacy),
  +                        turn="replay",
  +                    )
  +                except (ControllerError, TransitionError) as error:
  +                    refusal = error
  +
  +            replayed_result = self._record(
  +                discover_active_mission(workspace).manifest,
  +                self._grant_id(issued),
  +            ).get("result")
  +            self.assertNotEqual(
  +                first.process_instance_id, replacement.process_instance_id
  +            )
  +            self.assertEqual(len(reads), 1)
  +            self.assertEqual(replayed_result, first_result)
  +            self.assertEqual(str(refusal), "CAPABILITY_RESULT_REPLAY")
  +
  +    def test_web_operation_refuses_before_retrieval_resolution_or_network(self) -> None:
  +        with tempfile.TemporaryDirectory() as temp:
  +            runtime, workspace, controller = self._setup(Path(temp))
  +            url = "https://example.test/source"
  +            source = f"source:{url}"
  +            refusal = None
  +            with (
  +                patch(
  +                    "practical_agency.capability_operations._retrieve_web",
  +                    wraps=capability_operations._retrieve_web,
  +                ) as retrieve,
  +                patch(
  +                    "practical_agency.capability_operations.socket.getaddrinfo",
  +                    return_value=[
  +                        (
  +                            socket.AF_INET,
  +                            socket.SOCK_STREAM,
  +                            socket.IPPROTO_TCP,
  +                            "",
  +                            ("93.184.216.34", 0),
  +                        )
  +                    ],
  +                ) as resolver,
  +                patch(
  +                    "practical_agency.capability_operations.urllib.request.urlopen",
  +                    return_value=_HttpResponse(url),
  +                ) as network,
  +            ):
  +                try:
  +                    issued = self._issue(
  +                        controller,
  +                        workspace,
  +                        runtime,
  +                        operation="web.open",
  +                        target=url,
  +                        scope=[url, source],
  +                        turn="issue-web",
  +                    )
  +                    self._execute(
  +                        controller,
  +                        workspace,
  +                        runtime,
  +                        issued,
  +                        operation="web.open",
  +                        target=url,
  +                        refs=[source],
  +                        evidence={source: "caller source bytes"},
  +                        turn="execute-web",
  +                    )
  +                except ControllerError as error:
  +                    refusal = error
  +
  +            latest = discover_active_mission(workspace).manifest
  +            self.assertEqual(retrieve.call_count, 0)
  +            self.assertEqual(resolver.call_count, 0)
  +            self.assertEqual(network.call_count, 0)
  +            self.assertEqual(str(refusal), "WEB_OPERATION_DISABLED")
  +            for item in latest.capabilities.get("invoked", []):
  +                if isinstance(item, Mapping) and isinstance(
  +                    item.get("result"), Mapping
  +                ):
  +                    self.assertEqual(item["result"].get("observed_effects", []), [])
  +
  +    def test_mcp_tool_list_removes_injection_surfaces_and_caller_grant(self) -> None:
  +        with tempfile.TemporaryDirectory() as temp:
  +            tools = self._tools(McpServer(plugin_root=self._runtime(Path(temp))))
  +            self.assertNotIn("manifest_capability_request", tools)
  +            self.assertNotIn("manifest_capability_result", tools)
  +            execute = tools["manifest_capability_execute"]["inputSchema"]
  +            self.assertIn("grant_id", execute["required"])
  +            self.assertNotIn("grant", execute["properties"])
  +            self.assertIn("reason", tools["manifest_accept"]["inputSchema"]["properties"])
  +
  +    def test_mcp_caller_grant_refuses_before_file_or_checkpoint_effect(self) -> None:
  +        with tempfile.TemporaryDirectory() as temp:
  +            runtime, workspace, controller = self._setup(Path(temp))
  +            issued = self._issue(controller, workspace, runtime)
  +            caller_grant = self._legacy_grant(issued) or {
  +                "schema": "capability-grant@1",
  +                "grant_id": self._grant_id(issued),
  +            }
  +            before = discover_active_mission(workspace).manifest.to_dict()
  +            server = McpServer(plugin_root=runtime)
  +            with self._count_reads(workspace / "evidence.txt") as reads:
  +                response, error = self._mcp_call(
  +                    server,
  +                    2,
  +                    "manifest_capability_execute",
  +                    {
  +                        "grant": caller_grant,
  +                        "operation": "file.read",
  +                        "target": "evidence.txt",
  +                        "evidence_refs": ["evidence.txt"],
  +                        **self._refs(
  +                            workspace,
  +                            runtime,
  +                            "manifest_capability_execute",
  +                            "mcp-caller-grant",
  +                        ),
  +                    },
  +                )
  +
  +            self.assertEqual(reads, [])
  +            self.assertEqual(
  +                discover_active_mission(workspace).manifest.to_dict(), before
  +            )
  +            self.assertIsNone(response)
  +            self.assertEqual(str(error), "MCP_PROTOCOL_ERROR")
  +            execute = self._tools(server)["manifest_capability_execute"]["inputSchema"]
  +            self.assertIn("grant_id", execute["required"])
  +            self.assertNotIn("grant", execute["properties"])
  +
  +    def test_mcp_direct_request_injection_refuses_before_checkpoint_change(self) -> None:
  +        with tempfile.TemporaryDirectory() as temp:
  +            runtime, workspace, controller = self._setup(Path(temp))
  +            issued = self._issue(controller, workspace, runtime)
  +            current = discover_active_mission(workspace).manifest
  +            forged = self._legacy_grant(issued) or {
  +                "schema": "capability-grant@1",
  +                "grant_id": "grant-caller-injected",
  +            }
  +            forged["grant_id"] = "grant-caller-injected"
  +            forged["mission_revision"] = current.revision
  +            forged.setdefault("return_point", {})["revision"] = current.revision
  +            forged["evidence_scope"] = ["secret.txt"]
  +            before = current.to_dict()
  +            server = McpServer(plugin_root=runtime)
  +
  +            response, error = self._mcp_call(
  +                server,
  +                3,
  +                "manifest_capability_request",
  +                {
  +                    "grant": forged,
  +                    "request": self._intent("file.read", "secret.txt"),
  +                    **self._refs(
  +                        workspace,
  +                        runtime,
  +                        "manifest_capability_request",
  +                        "mcp-request-injection",
  +                    ),
  +                },
  +            )
  +
  +            self.assertEqual(
  +                discover_active_mission(workspace).manifest.to_dict(), before
  +            )
  +            self.assertIsNone(response)
  +            self.assertEqual(str(error), "MCP_PROTOCOL_ERROR")
  +            self.assertNotIn("manifest_capability_request", self._tools(server))
  +
  +    def test_mcp_direct_result_injection_refuses_before_checkpoint_change(self) -> None:
  +        with tempfile.TemporaryDirectory() as temp:
  +            runtime, workspace, controller = self._setup(Path(temp))
  +            issued = self._issue(controller, workspace, runtime)
  +            current = discover_active_mission(workspace).manifest
  +            record = self._record(current, self._grant_id(issued))
  +            grant = record.get("grant")
  +            request = record.get("request")
  +            return_point = (
  +                grant.get("return_point")
  +                if isinstance(grant, Mapping)
  +                else request.get("return_point")
  +                if isinstance(request, Mapping)
  +                else {}
  +            )
  +            before = current.to_dict()
  +            server = McpServer(plugin_root=runtime)
  +
  +            response, error = self._mcp_call(
  +                server,
  +                4,
  +                "manifest_capability_result",
  +                {
  +                    "grant_id": self._grant_id(issued),
  +                    "result": {
  +                        "schema": "capability-result@1",
  +                        "verdict": "PASS",
  +                        "returned_control_point": return_point,
  +                        "coverage_limits": ["caller assertion only"],
  +                        "evidence_refs": ["evidence.txt"],
  +                        "observed_effects": [],
  +                    },
  +                    **self._refs(
  +                        workspace,
  +                        runtime,
  +                        "manifest_capability_result",
  +                        "mcp-result-injection",
  +                    ),
  +                },
  +            )
  +
  +            self.assertEqual(
  +                discover_active_mission(workspace).manifest.to_dict(), before
  +            )
  +            self.assertIsNone(response)
  +            self.assertEqual(str(error), "MCP_PROTOCOL_ERROR")
  +            self.assertNotIn("manifest_capability_result", self._tools(server))
  +
  +    def test_persisted_request_and_result_cannot_violate_strict_schemas(self) -> None:
  +        with tempfile.TemporaryDirectory() as temp:
  +            runtime, workspace, controller = self._setup(Path(temp))
  +            issued = self._issue(controller, workspace, runtime)
  +            self._execute(
  +                controller,
  +                workspace,
  +                runtime,
  +                issued,
  +                operation="file.read",
  +                target="evidence.txt",
  +                refs=["evidence.txt"],
  +                turn="schema-execution",
  +            )
  +            record = self._record(
  +                discover_active_mission(workspace).manifest,
  +                self._grant_id(issued),
  +            )
  +            request, result = record.get("request"), record.get("result")
  +            self.assertIsInstance(request, Mapping)
  +            self.assertIsInstance(result, Mapping)
  +            assert isinstance(request, Mapping) and isinstance(result, Mapping)
  +            request_schema = json.loads(
  +                (ROOT / "contracts" / "capability-request.schema.json").read_text()
  +            )
  +            result_schema = json.loads(
  +                (ROOT / "contracts" / "capability-result.schema.json").read_text()
  +            )
  +
  +            self.assertEqual(_schema_errors(request, request_schema), [])
  +            self.assertEqual(_schema_errors(result, result_schema), [])
  +            self.assertEqual(
  +                request["expected_output_contract"],
  +                "contracts/capability-result.schema.json",
  +            )
  +            self.assertEqual(result["request_id"], request["request_id"])
  +            self.assertEqual(result["status"], "completed")
  +            self.assertEqual(result["returned_control_point"], request["return_point"])
  +            self.assertTrue(result["observed_effects"])
  +
  +    def _assert_negative_verdict(
  +        self, verdict: str, reason: str, expected_status: str
  +    ) -> None:
  +        with tempfile.TemporaryDirectory() as temp:
  +            runtime, workspace, _ = self._setup(Path(temp))
  +            manifest = discover_active_mission(workspace).manifest
  +            manifest = record_fixture_verifier_result(manifest)
  +            manifest = apply_event_data(
  +                manifest, "begin_verification", "mission-steward", {}
  +            )
  +            FileCheckpointStore(
  +                workspace / "missions" / manifest.mission_id / "checkpoints"
  +            ).save(manifest)
  +            controller = ManifestController(plugin_root=runtime)
  +            response = None
  +            call_error = None
  +            try:
  +                response = controller.manifest_accept(
  +                    acceptor_ref="reviewer:independent",
  +                    verdict=verdict,
  +                    reason=reason,
  +                    separation_assurance="declared-role-separation",
  +                    **self._refs(
  +                        workspace,
  +                        runtime,
  +                        "manifest_accept",
  +                        f"negative-{verdict.lower()}",
  +                    ),
  +                )
  +            except (ControllerError, TypeError) as error:
  +                call_error = error
  +
  +            latest = discover_active_mission(workspace).manifest
  +            marker = f"{verdict}:{reason}"
  +            rejections = [
  +                item
  +                for item in latest.continuity.get("decisions", [])
  +                if isinstance(item, Mapping)
  +                and item.get("kind") == "completion-rejection"
  +            ]
  +            self.assertEqual(latest.state["status"], expected_status)
  +            self.assertNotEqual(latest.state["status"], "completed")
  +            self.assertIn(marker, latest.integrity["unresolved_verdicts"])
  +            self.assertIn(marker, latest.state["blockers"])
  +            self.assertEqual(len(rejections), 1)
  +            self.assertEqual(rejections[0]["verdict"], verdict)
  +            self.assertEqual(rejections[0]["reason"], reason)
  +            self.assertTrue(rejections[0]["evidence_refs"])
  +            self.assertTrue(rejections[0]["coverage_limits"])
  +            self.assertIsNone(call_error)
  +            self.assertIsNotNone(response)
  +            assert response is not None
  +            self.assertEqual(response["mission_status"], expected_status)
  +            self.assertEqual(response["verdict"], verdict)
  +            self.assertEqual(response["reason"], reason)
  +            self.assertTrue(response["evidence_refs"])
  +            self.assertTrue(response["coverage_limits"])
  +
  +    def test_independent_fail_verdict_is_durable_without_completion(self) -> None:
  +        self._assert_negative_verdict(
  +            "FAIL", "artifact proof contradicted", "active"
  +        )
  +
  +    def test_independent_inconclusive_verdict_is_durable_without_completion(
  +        self,
  +    ) -> None:
  +        self._assert_negative_verdict(
  +            "INCONCLUSIVE", "observer coverage is incomplete", "blocked"
  +        )
  +
  +
  +if __name__ == "__main__":
  +    unittest.main()
evidence: |
  Execution status: NOT RUN. All RED outcomes below are source-derived expectations from the packet commit.

  Test-to-defect matrix and expected baseline RED:
  1. test_forged_same_id_wider_scope_refuses_before_file_observation
     Defect: manifest_capability_execute trusts a caller-carried same-ID grant whose evidence_scope was widened.
     Expected baseline RED: secret.txt is read once, no TARGET_NOT_IN_EVIDENCE_SCOPE refusal occurs, and the canonical durable record accepts the result.
  2. test_stale_descriptor_refuses_before_file_observation
     Defect: execution does not re-observe the current descriptor digest before I/O.
     Expected baseline RED: evidence.txt is read once and no CAPABILITY_DESCRIPTOR_MISMATCH refusal occurs.
  3. test_missing_authority_refuses_before_file_observation
     Defect: descriptor authority, mission permission, protected state, acceptable cost, and escalation boundaries are not enforced end to end.
     Expected baseline RED: each of the four subcases performs one file observation and returns no named authority refusal.
  4. test_valid_local_read_requires_canonical_grant_id_and_one_observation
     Defect: the valid local-read path is not expressible through canonical grant_id authority.
     Expected baseline RED: the current controller rejects grant_id as an unexpected keyword before the wished-for API can execute.
  5. test_fresh_copy_replay_after_controller_replacement_observes_once
     Defect: a fresh copy of the original grant survives controller replacement and repeats I/O before durable result replay is noticed.
     Expected baseline RED: the read counter reaches two; only afterward does CAPABILITY_RESULT_REPLAY surface.
  6. test_web_operation_refuses_before_retrieval_resolution_or_network
     Defect: web.open remains network-active.
     Expected baseline RED: retrieval, DNS resolution, and urlopen are each called, and WEB_OPERATION_DISABLED is not returned.
  7. test_mcp_tool_list_removes_injection_surfaces_and_caller_grant
     Defect: MCP still advertises direct request/result tools, execute still exposes caller grant JSON, and acceptance has no reason field.
     Expected baseline RED: the forbidden tools and grant property are present and grant_id/reason are absent.
  8. test_mcp_caller_grant_refuses_before_file_or_checkpoint_effect
     Defect: the public execute schema still models caller-owned grant authority.
     Expected baseline RED: the current custom validator already protocol-refuses the non-empty object with zero effect, but the test remains RED because tools/list still requires grant and lacks grant_id.
  9. test_mcp_direct_request_injection_refuses_before_checkpoint_change
     Defect: manifest_capability_request remains an advertised injection surface.
     Expected baseline RED: the current custom validator protocol-refuses the non-empty payload without changing the checkpoint, but the tool remains listed.
  10. test_mcp_direct_result_injection_refuses_before_checkpoint_change
      Defect: manifest_capability_result remains an advertised caller-result surface.
      Expected baseline RED: the current custom validator protocol-refuses the non-empty payload without changing the checkpoint, but the tool remains listed.
  11. test_persisted_request_and_result_cannot_violate_strict_schemas
      Defect: the checkpoint stores the raw caller request and the transient grant result rather than schema-conforming runtime objects.
      Expected baseline RED: capability-request@1 reports missing canonical fields plus extra intent fields; capability-result@1 reports missing request_id/status/artifact_refs and extra grant/evidence fields.
  12. test_independent_fail_verdict_is_durable_without_completion
      Defect: manifest_accept cannot route the existing reason-bearing FAIL transition.
      Expected baseline RED: reason is an unexpected keyword and the checkpoint remains verifying with no durable completion-rejection.
  13. test_independent_inconclusive_verdict_is_durable_without_completion
      Defect: manifest_accept cannot route the existing reason-bearing INCONCLUSIVE transition.
      Expected baseline RED: reason is an unexpected keyword and the checkpoint remains verifying rather than blocked.

  Repository-content contradiction reported:
  The packet describes request/result as reachable MCP injection tools. They are advertised and dispatchable by name, but the packet-commit custom _validate implementation treats a nested schema of only type: object as accepting only an empty object. Therefore substantive non-empty injection payloads currently fail at the MCP protocol layer even though the controller methods themselves remain weak. The tests preserve that zero-state-change behavior and independently require removal of the advertised surfaces, so no packet decision is silently weakened.
requirements: |
  DCT-001: COVERED. The diff adds only tests/test_durable_capability_transaction.py; no production, skill, schema, or fixture hunks.
  DCT-002: COVERED by forged-scope, stale-descriptor, and four missing-authority subcases, all with zero-observation assertions.
  DCT-003: COVERED by a fresh copied payload, replacement ManifestController, real latest checkpoint, and exact one-read assertion.
  DCT-004: COVERED by real McpServer tools/list and tools/call tests for caller grant, direct request, and direct result surfaces, with checkpoint immutability assertions.
  DCT-005: COVERED by validating the persisted request/result objects against the committed repository schemas with a test-local standard-library validator.
  DCT-006: COVERED by a named WEB_OPERATION_DISABLED expectation and zero retrieval, resolver, and urlopen calls.
  DCT-007: COVERED by separate FAIL and INCONCLUSIVE controller tests that inspect durable reason, evidence, coverage limits, blockers, unresolved verdicts, and non-completed state.
  DCT-008: COVERED by a positive grant_id controller test asserting exactly one local observation and a persisted result.
  DCT-009: COVERED. Controller, FileCheckpointStore, mission discovery, state transitions, and McpServer are production objects; patching is limited to Path.read_text and web retrieval/resolution/network seams.

  Implementation state: OPEN. Stage 1 cannot be COMPLETE until the origin proves RED, publishes Stage 2, implements the transaction, and proves GREEN.
decisions_and_assumptions: |
  1. Test API decision: manifest_capability_execute replaces caller grant JSON with grant_id while retaining operation, target, and evidence arguments as untrusted match assertions. The checkpointed grant/request remains the only authority; any mismatch must refuse before observation.
  2. Baseline reachability shim: the private test helper retries the packet-commit grant= form only when Python reports that grant_id is an unexpected keyword. This lets the RED tests reach the verified pre-I/O defects. The dedicated positive grant_id test does not use the shim.
  3. The dynamic-reader descriptor exists only in a temporary copied plugin root. It adds no public skill or static inventory and binds authority_required repository:read plus the committed request/result contract paths.
  4. Authority mapping assumption: file.read requires repository:read; its exact target is the requested effect; its canonical estimated cost is bounded reads; an exact target appearing in protected_state or escalation_required_for triggers the existing authority.py refusal code.
  5. The request argument to manifest_capability_issue is treated as untrusted intent. Production must generate and persist the canonical request_id, mission binding, descriptor digest, authority receipt, output contract, and return point, and must not persist input-only requested_permissions/requested_effects/estimated_costs fields.
  6. Expected preserved refusal codes are TARGET_NOT_IN_EVIDENCE_SCOPE, CAPABILITY_DESCRIPTOR_MISMATCH, PERMISSION_NOT_GRANTED, PROTECTED_STATE_VIOLATION, COST_NOT_AUTHORIZED, ESCALATION_REQUIRED, CAPABILITY_RESULT_REPLAY, and MCP_PROTOCOL_ERROR. WEB_OPERATION_DISABLED is the one new named refusal required by the approved pre-network web decision.
  7. Negative verdicts remain on the existing manifest_accept MCP/controller surface: PASS uses accept; FAIL and INCONCLUSIVE require reason and route to the existing reject transition.
  8. No additional production test seam is required.
blockers_or_questions: NONE
recommended_next_action: |
  Apply this tests-only diff at 578cb9ee3165c899af26da1111163effa19949fc and run python -m unittest -v tests.test_durable_capability_transaction, recording that each failure matches the matrix before publishing the immutable Stage 2 implementation packet.
