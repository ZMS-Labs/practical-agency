from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import patch

import practical_agency.capability_operations as capability_operations
import practical_agency.controller as controller_module
from practical_agency.checkpoint_store import FileCheckpointStore
from practical_agency.controller import ControllerError, ManifestController
from practical_agency.host_evidence import write_host_context, write_host_gate
from practical_agency.manifest_model import MissionManifest
from practical_agency.mcp_server import McpServer, ProtocolError
from practical_agency.mission_repository import discover_active_mission
from practical_agency.state_machine import TransitionError, apply_event_data
from tests.helpers import minimal_payload, record_fixture_verifier_result


ROOT = Path(__file__).resolve().parents[1]


def _type_ok(value: object, expected: object) -> bool:
    if isinstance(expected, list):
        return any(_type_ok(value, item) for item in expected)
    checks = {
        "object": lambda: isinstance(value, dict),
        "array": lambda: isinstance(value, list),
        "string": lambda: isinstance(value, str),
        "integer": lambda: isinstance(value, int) and not isinstance(value, bool),
        "boolean": lambda: isinstance(value, bool),
        "null": lambda: value is None,
    }
    return checks.get(str(expected), lambda: True)()


def _schema_errors(value: object, schema: Mapping[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: const")
    if isinstance(schema.get("enum"), list) and value not in schema["enum"]:
        errors.append(f"{path}: enum")
    if "type" in schema and not _type_ok(value, schema["type"]):
        return [*errors, f"{path}: type"]

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if isinstance(required, list):
            errors.extend(
                f"{path}: missing {key}" for key in required if key not in value
            )
        if schema.get("additionalProperties") is False and isinstance(
            properties, Mapping
        ):
            errors.extend(
                f"{path}: extra {key}" for key in value if key not in properties
            )
        if isinstance(properties, Mapping):
            for key, child in value.items():
                if isinstance(properties.get(key), Mapping):
                    errors.extend(
                        _schema_errors(child, properties[key], f"{path}.{key}")
                    )

    if isinstance(value, list):
        minimum = schema.get("minItems")
        if isinstance(minimum, int) and len(value) < minimum:
            errors.append(f"{path}: minItems")
        if isinstance(schema.get("items"), Mapping):
            for index, child in enumerate(value):
                errors.extend(
                    _schema_errors(child, schema["items"], f"{path}[{index}]")
                )

    if isinstance(value, str):
        minimum = schema.get("minLength")
        if isinstance(minimum, int) and len(value) < minimum:
            errors.append(f"{path}: minLength")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
            errors.append(f"{path}: pattern")

    if isinstance(value, int) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if isinstance(minimum, int) and value < minimum:
            errors.append(f"{path}: minimum")
    return errors


class _HttpResponse:
    status = 200

    def __init__(self, url: str) -> None:
        self.url = url

    def __enter__(self) -> "_HttpResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def geturl(self) -> str:
        return self.url

    def read(self) -> bytes:
        return b"network observation"


_ORPHAN_WORKER = "--orphan-worker"
_EXIT_BEFORE_READ = 91
_EXIT_AFTER_READ = 92


def _run_orphan_worker(arguments: list[str]) -> None:
    action, runtime, workspace, journal, context_ref, gate_ref, *grant = arguments
    runtime_path = Path(runtime)
    workspace_path = Path(workspace)
    journal_path = Path(journal)
    target = (workspace_path / "evidence.txt").resolve()
    original_read_text = Path.read_text

    def observed_read(path: Path, *args: object, **kwargs: object) -> str:
        if path.resolve() == target:
            descriptor = os.open(
                journal_path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600
            )
            try:
                os.write(descriptor, b"read\n")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return original_read_text(path, *args, **kwargs)

    Path.read_text = observed_read
    controller = ManifestController(plugin_root=runtime_path)
    refs = {
        "_host_context_ref": context_ref,
        "_host_gate_ref": gate_ref,
    }
    try:
        if action.startswith("crash-"):
            original_execute_read = controller_module.execute_read

            def forced_exit(*args: object, **kwargs: object) -> None:
                if action == "crash-after-read":
                    original_execute_read(*args, **kwargs)
                    os._exit(_EXIT_AFTER_READ)
                os._exit(_EXIT_BEFORE_READ)

            controller_module.execute_read = forced_exit
        if action == "engage":
            result = controller.manifest_engage(**refs)
        elif action == "issue":
            result = controller.manifest_capability_issue(
                capability_id="dynamic-reader",
                blocking_condition="inspect the bounded evidence",
                admitted_operation="file.read",
                evidence_scope=["evidence.txt"],
                request={
                    "bounded_question_or_action": "file.read:evidence.txt",
                    "requested_permissions": ["repository:read"],
                    "requested_effects": ["evidence.txt"],
                    "estimated_costs": ["bounded reads"],
                    "timeout_or_stop_condition": "stop after one bounded observation",
                },
                **refs,
            )
        else:
            result = controller.manifest_capability_execute(
                grant_id=grant[0],
                operation="file.read",
                target="evidence.txt",
                evidence_refs=["evidence.txt"],
                evidence_payload=None,
                **refs,
            )
    except RuntimeError as error:
        print(json.dumps({"error": str(error)}), flush=True)
    else:
        print(json.dumps({"result": result}), flush=True)


class DurableCapabilityTransactionRedTests(unittest.TestCase):
    def _runtime(self, base: Path) -> Path:
        runtime = base / "runtime"
        shutil.copytree(ROOT / "hooks", runtime / "hooks")
        shutil.copytree(
            ROOT / "practical_agency",
            runtime / "practical_agency",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        shutil.copytree(ROOT / "skills", runtime / "skills")
        descriptor = runtime / "skills" / "dynamic-reader" / "SKILL.md"
        descriptor.parent.mkdir(parents=True)
        descriptor.write_text(
            "---\n"
            "name: dynamic-reader\n"
            "description: Observe one bounded source without mutation.\n"
            "metadata:\n"
            "  kind: skill\n"
            "  persistence: session\n"
            "  independence: actor\n"
            "  authority_required: [repository:read]\n"
            "  input_contract: contracts/capability-request.schema.json\n"
            "  output_contract: contracts/capability-result.schema.json\n"
            "---\n\n# Dynamic reader\n",
            encoding="utf-8",
        )
        return runtime

    def _setup(
        self,
        base: Path,
        *,
        permissions: list[str] | None = None,
        protected_state: list[str] | None = None,
        acceptable_costs: list[str] | None = None,
        escalation_required_for: list[str] | None = None,
    ) -> tuple[Path, Path, ManifestController]:
        runtime = self._runtime(base)
        workspace = base / "workspace"
        workspace.mkdir()
        (workspace / ".git").mkdir()
        (workspace / "evidence.txt").write_text("authorized evidence", encoding="utf-8")
        (workspace / "secret.txt").write_text("out-of-scope secret", encoding="utf-8")

        payload = minimal_payload()
        payload["mission_id"] = "durable-capability-mission"
        payload["revision"] = 1
        payload["authority"]["permissions"] = list(
            permissions or ["repository:read", "network:read"]
        )
        payload["authority"]["protected_state"] = list(
            protected_state or ["mutation:any"]
        )
        payload["authority"]["acceptable_costs"] = list(
            acceptable_costs or ["bounded reads"]
        )
        payload["authority"]["escalation_required_for"] = list(
            escalation_required_for or ["mutation:any"]
        )
        payload["state"] = {
            "status": "active",
            "completed_actions": [],
            "current_frontier": ["inspect the bounded evidence"],
            "blockers": [],
            "next_action": "inspect the bounded evidence",
        }
        payload["continuity"]["prior_checkpoint"] = "fixture:capability-r1"
        payload["integrity"]["completion_acceptor"] = "reviewer:independent"
        manifest = MissionManifest.from_dict(payload)
        FileCheckpointStore(
            workspace / "missions" / manifest.mission_id / "checkpoints"
        ).save(manifest)
        return runtime, workspace, ManifestController(plugin_root=runtime)

    def _refs(
        self, workspace: Path, runtime: Path, operation: str, turn: str
    ) -> dict[str, str]:
        context = write_host_context(
            workspace_root=workspace,
            prompt="$manifest exercise the durable capability transaction",
            session_id="dct-red",
            turn_id=turn,
            plugin_root=runtime,
        )
        gate = write_host_gate(
            context_ref=context.path,
            tool_name=f"mcp__practical_agency__{operation}",
            tool_use_id=f"tool-{turn}",
            session_id="dct-red",
            turn_id=turn,
            workspace_root=workspace,
            lock_reason="explicit-manifest-intent",
            decision="allow-controller",
            plugin_root=runtime,
        )
        return {"_host_context_ref": context.path, "_host_gate_ref": gate.path}

    @staticmethod
    def _intent(operation: str, target: str) -> dict[str, object]:
        permission = "network:read" if operation.startswith("web.") else "repository:read"
        return {
            "bounded_question_or_action": f"{operation}:{target}",
            "requested_permissions": [permission],
            "requested_effects": [target],
            "estimated_costs": ["bounded reads"],
            "timeout_or_stop_condition": "stop after one bounded observation",
        }

    def _issue(
        self,
        controller: ManifestController,
        workspace: Path,
        runtime: Path,
        *,
        operation: str = "file.read",
        target: str = "evidence.txt",
        scope: list[str] | None = None,
        turn: str = "issue",
    ) -> dict[str, Any]:
        return controller.manifest_capability_issue(
            capability_id="dynamic-reader",
            blocking_condition="inspect the bounded evidence",
            admitted_operation=operation,
            evidence_scope=list(scope or [target]),
            request=self._intent(operation, target),
            **self._refs(
                workspace, runtime, "manifest_capability_issue", turn
            ),
        )

    @staticmethod
    def _grant_id(issued: Mapping[str, Any]) -> str:
        if isinstance(issued.get("grant_id"), str):
            return str(issued["grant_id"])
        grant = issued.get("grant")
        if isinstance(grant, Mapping) and isinstance(grant.get("grant_id"), str):
            return str(grant["grant_id"])
        raise AssertionError(f"missing grant_id: {issued!r}")

    @staticmethod
    def _legacy_grant(issued: Mapping[str, Any]) -> dict[str, Any] | None:
        grant = issued.get("grant")
        return deepcopy(dict(grant)) if isinstance(grant, Mapping) else None

    def _execute(
        self,
        controller: ManifestController,
        workspace: Path,
        runtime: Path,
        issued: Mapping[str, Any],
        *,
        operation: str,
        target: str,
        refs: list[str] | None = None,
        evidence: Mapping[str, str] | None = None,
        legacy_grant: Mapping[str, Any] | None = None,
        turn: str,
    ) -> dict[str, Any]:
        arguments = {
            "operation": operation,
            "target": target,
            "evidence_refs": list(refs or [target]),
            "evidence_payload": dict(evidence) if evidence is not None else None,
            **self._refs(
                workspace, runtime, "manifest_capability_execute", turn
            ),
        }
        try:
            return controller.manifest_capability_execute(
                grant_id=self._grant_id(issued), **arguments
            )
        except TypeError as error:
            if "unexpected keyword argument 'grant_id'" not in str(error):
                raise
            grant = (
                deepcopy(dict(legacy_grant))
                if isinstance(legacy_grant, Mapping)
                else self._legacy_grant(issued)
            )
            if grant is None:
                raise
            return controller.manifest_capability_execute(grant=grant, **arguments)

    @staticmethod
    def _record(manifest: MissionManifest, grant_id: str) -> Mapping[str, Any]:
        records = [
            item
            for item in manifest.capabilities.get("invoked", [])
            if isinstance(item, Mapping) and item.get("grant_id") == grant_id
        ]
        if len(records) != 1:
            raise AssertionError(f"expected one transaction {grant_id}: {records!r}")
        return records[0]

    @contextmanager
    def _count_reads(self, *targets: Path):
        calls: list[str] = []
        expected = {target.resolve() for target in targets}
        original = Path.read_text

        def counted(path: Path, *args: object, **kwargs: object) -> str:
            if path.resolve() in expected:
                calls.append(str(path))
            return original(path, *args, **kwargs)

        with patch.object(Path, "read_text", new=counted):
            yield calls

    @staticmethod
    def _read_count(journal: Path) -> int:
        return (
            len(journal.read_text(encoding="utf-8").splitlines())
            if journal.exists()
            else 0
        )

    def _orphan_process(
        self,
        runtime: Path,
        workspace: Path,
        journal: Path,
        action: str,
        turn: str,
        grant_id: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        operation = {
            "engage": "manifest_engage",
            "issue": "manifest_capability_issue",
        }.get(action, "manifest_capability_execute")
        refs = self._refs(workspace, runtime, operation, turn)
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            _ORPHAN_WORKER,
            action,
            str(runtime),
            str(workspace),
            str(journal),
            refs["_host_context_ref"],
            refs["_host_gate_ref"],
        ]
        if grant_id is not None:
            command.append(grant_id)
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join([str(runtime), str(ROOT)])
        return subprocess.run(
            command,
            cwd=runtime,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    @staticmethod
    def _worker_payload(
        completed: subprocess.CompletedProcess[str],
    ) -> dict[str, Any]:
        if completed.returncode != 0:
            raise AssertionError(
                f"returncode={completed.returncode} "
                f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
            )
        payload = json.loads(completed.stdout)
        if not isinstance(payload, dict):
            raise AssertionError(f"worker payload is not an object: {payload!r}")
        return payload

    def _assert_orphan_fails_closed(
        self,
        *,
        crash_action: str,
        expected_exit: int,
        reads_after_crash: int,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            runtime, workspace, controller = self._setup(base)
            issued = self._issue(
                controller,
                workspace,
                runtime,
                turn=f"{crash_action}-issue",
            )
            grant_id = self._grant_id(issued)
            journal = base / "observations.log"

            crash = self._orphan_process(
                runtime,
                workspace,
                journal,
                crash_action,
                f"{crash_action}-execute",
                grant_id,
            )
            self.assertEqual(
                crash.returncode,
                expected_exit,
                f"stdout={crash.stdout!r} stderr={crash.stderr!r}",
            )
            begun = discover_active_mission(workspace).manifest
            begun_record = self._record(begun, grant_id)
            self.assertEqual(begun_record.get("execution_state"), "in_progress")
            self.assertIsNone(begun_record.get("result"))
            self.assertIs(begun_record["grant"].get("used"), True)
            self.assertEqual(self._read_count(journal), reads_after_crash)

            engagement = self._worker_payload(
                self._orphan_process(
                    runtime,
                    workspace,
                    journal,
                    "engage",
                    f"{crash_action}-engage",
                )
            )["result"]
            recovered = discover_active_mission(workspace).manifest
            recovered_record = self._record(recovered, grant_id)
            reads_after_engage = self._read_count(journal)
            marker = f"CAPABILITY_EFFECT_UNKNOWN:{grant_id}"

            retry = self._worker_payload(
                self._orphan_process(
                    runtime,
                    workspace,
                    journal,
                    "execute",
                    f"{crash_action}-retry",
                    grant_id,
                )
            )
            replacement_issue = self._worker_payload(
                self._orphan_process(
                    runtime,
                    workspace,
                    journal,
                    "issue",
                    f"{crash_action}-replacement-issue",
                )
            )
            replacement_execute: dict[str, Any] | None = None
            replacement = replacement_issue.get("result")
            if isinstance(replacement, Mapping):
                replacement_execute = self._worker_payload(
                    self._orphan_process(
                        runtime,
                        workspace,
                        journal,
                        "execute",
                        f"{crash_action}-replacement-execute",
                        self._grant_id(replacement),
                    )
                )

            final = discover_active_mission(workspace).manifest
            final_record = self._record(final, grant_id)
            observed = {
                "recovery_checkpoint_created": recovered.revision > begun.revision,
                "engagement_revision": engagement.get("revision"),
                "recovered_execution_state": recovered_record.get(
                    "execution_state"
                ),
                "recovered_result": recovered_record.get("result"),
                "recovered_status": recovered.state.get("status"),
                "recovered_blocker": marker
                in recovered.state.get("blockers", []),
                "recovered_unresolved": marker
                in recovered.integrity.get("unresolved_verdicts", []),
                "reads_after_engage": reads_after_engage,
                "execution_state": final_record.get("execution_state"),
                "grant_used": final_record["grant"].get("used"),
                "result": final_record.get("result"),
                "mission_status": final.state.get("status"),
                "engagement_status": engagement.get("mission_status"),
                "blocker": marker in final.state.get("blockers", []),
                "unresolved": marker
                in final.integrity.get("unresolved_verdicts", []),
                "result_artifact": f"capability-result:{grant_id}"
                in final.continuity.get("durable_artifacts", []),
                "result_decision": any(
                    isinstance(item, Mapping)
                    and item.get("kind") == "capability-result"
                    and item.get("grant_id") == grant_id
                    for item in final.continuity.get("decisions", [])
                ),
                "original_retry_refused": "error" in retry
                and "result" not in retry,
                "replacement_issue_error": replacement_issue.get("error"),
                "replacement_execute": (
                    "not-issued"
                    if replacement_execute is None
                    else replacement_execute.get("error")
                    or "executed"
                ),
                "observation_count": self._read_count(journal),
                "grant_ids": [
                    item.get("grant_id")
                    for item in final.capabilities.get("invoked", [])
                    if isinstance(item, Mapping)
                ],
            }
            self.assertEqual(
                observed,
                {
                    "recovery_checkpoint_created": True,
                    "engagement_revision": recovered.revision,
                    "recovered_execution_state": "unknown",
                    "recovered_result": None,
                    "recovered_status": "blocked",
                    "recovered_blocker": True,
                    "recovered_unresolved": True,
                    "reads_after_engage": reads_after_crash,
                    "execution_state": "unknown",
                    "grant_used": True,
                    "result": None,
                    "mission_status": "blocked",
                    "engagement_status": "blocked",
                    "blocker": True,
                    "unresolved": True,
                    "result_artifact": False,
                    "result_decision": False,
                    "original_retry_refused": True,
                    "replacement_issue_error": marker,
                    "replacement_execute": "not-issued",
                    "observation_count": reads_after_crash,
                    "grant_ids": [grant_id],
                },
            )

    @staticmethod
    def _mcp_call(
        server: McpServer, request_id: int, name: str, arguments: Mapping[str, Any]
    ) -> tuple[dict[str, Any] | None, ProtocolError | None]:
        try:
            response = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": dict(arguments)},
                }
            )
        except ProtocolError as error:
            return None, error
        if not isinstance(response, dict):
            raise AssertionError(f"MCP returned no response for {name}")
        return response, None

    @staticmethod
    def _tools(server: McpServer) -> dict[str, Mapping[str, Any]]:
        response = server.handle(
            {"jsonrpc": "2.0", "id": 99, "method": "tools/list", "params": {}}
        )
        if not isinstance(response, Mapping):
            raise AssertionError("MCP tools/list returned no response")
        return {
            str(tool["name"]): tool for tool in response["result"]["tools"]
        }

    def test_forged_same_id_wider_scope_refuses_before_file_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime, workspace, controller = self._setup(Path(temp))
            issued = self._issue(controller, workspace, runtime)
            forged = self._legacy_grant(issued) or {
                "grant_id": self._grant_id(issued),
                "evidence_scope": [],
            }
            forged["evidence_scope"] = ["secret.txt"]
            refusal = None
            with self._count_reads(
                workspace / "evidence.txt", workspace / "secret.txt"
            ) as reads:
                try:
                    self._execute(
                        controller,
                        workspace,
                        runtime,
                        issued,
                        operation="file.read",
                        target="secret.txt",
                        refs=["secret.txt"],
                        legacy_grant=forged,
                        turn="forged-scope",
                    )
                except ControllerError as error:
                    refusal = error

            latest = discover_active_mission(workspace).manifest
            result = self._record(latest, self._grant_id(issued)).get("result")
            self.assertEqual(reads, [])
            self.assertFalse(
                isinstance(result, Mapping) and result.get("status") == "completed"
            )
            self.assertEqual(str(refusal), "TARGET_NOT_IN_EVIDENCE_SCOPE")

    def test_stale_descriptor_refuses_before_file_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime, workspace, controller = self._setup(Path(temp))
            issued = self._issue(controller, workspace, runtime)
            descriptor = runtime / "skills" / "dynamic-reader" / "SKILL.md"
            descriptor.write_text(
                descriptor.read_text(encoding="utf-8") + "\nDescriptor drift.\n",
                encoding="utf-8",
            )
            refusal = None
            with self._count_reads(workspace / "evidence.txt") as reads:
                try:
                    self._execute(
                        controller,
                        workspace,
                        runtime,
                        issued,
                        operation="file.read",
                        target="evidence.txt",
                        refs=["evidence.txt"],
                        turn="stale-descriptor",
                    )
                except ControllerError as error:
                    refusal = error

            latest = discover_active_mission(workspace).manifest
            result = self._record(latest, self._grant_id(issued)).get("result")
            self.assertEqual(reads, [])
            self.assertFalse(
                isinstance(result, Mapping) and result.get("status") == "completed"
            )
            self.assertEqual(str(refusal), "CAPABILITY_DESCRIPTOR_MISMATCH")

    def test_missing_authority_refuses_before_file_observation(self) -> None:
        scenarios = [
            (
                {"permissions": ["network:read"]},
                "PERMISSION_NOT_GRANTED:repository:read",
            ),
            (
                {"protected_state": ["evidence.txt"]},
                "PROTECTED_STATE_VIOLATION:evidence.txt",
            ),
            (
                {"acceptable_costs": ["one local write"]},
                "COST_NOT_AUTHORIZED:bounded reads",
            ),
            (
                {"escalation_required_for": ["evidence.txt"]},
                "ESCALATION_REQUIRED:evidence.txt",
            ),
        ]
        for overrides, expected in scenarios:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp:
                runtime, workspace, controller = self._setup(
                    Path(temp), **overrides
                )
                refusal = None
                with self._count_reads(workspace / "evidence.txt") as reads:
                    try:
                        issued = self._issue(controller, workspace, runtime)
                        self._execute(
                            controller,
                            workspace,
                            runtime,
                            issued,
                            operation="file.read",
                            target="evidence.txt",
                            refs=["evidence.txt"],
                            turn=f"authority-{expected.split(':')[0]}",
                        )
                    except ControllerError as error:
                        refusal = error

                latest = discover_active_mission(workspace).manifest
                self.assertEqual(reads, [])
                self.assertEqual(str(refusal), expected)
                for item in latest.capabilities.get("invoked", []):
                    if isinstance(item, Mapping) and isinstance(
                        item.get("result"), Mapping
                    ):
                        self.assertEqual(
                            item["result"].get("observed_effects", []), []
                        )

    def test_valid_local_read_requires_canonical_grant_id_and_one_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime, workspace, controller = self._setup(Path(temp))
            issued = self._issue(controller, workspace, runtime)
            response = None
            call_error = None
            with self._count_reads(workspace / "evidence.txt") as reads:
                try:
                    response = controller.manifest_capability_execute(
                        grant_id=self._grant_id(issued),
                        operation="file.read",
                        target="evidence.txt",
                        evidence_refs=["evidence.txt"],
                        evidence_payload=None,
                        **self._refs(
                            workspace,
                            runtime,
                            "manifest_capability_execute",
                            "valid-grant-id",
                        ),
                    )
                except (TypeError, ControllerError) as error:
                    call_error = error

            record = self._record(
                discover_active_mission(workspace).manifest,
                self._grant_id(issued),
            )
            self.assertIsNone(call_error)
            self.assertIsNotNone(response)
            self.assertEqual(len(reads), 1)
            self.assertIsInstance(record.get("result"), Mapping)

    def test_fresh_copy_replay_after_controller_replacement_observes_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime, workspace, first = self._setup(Path(temp))
            issued = self._issue(first, workspace, runtime)
            replay_payload = deepcopy(dict(issued))
            legacy = self._legacy_grant(issued)
            refusal = None
            with self._count_reads(workspace / "evidence.txt") as reads:
                self._execute(
                    first,
                    workspace,
                    runtime,
                    issued,
                    operation="file.read",
                    target="evidence.txt",
                    refs=["evidence.txt"],
                    legacy_grant=deepcopy(legacy),
                    turn="first-execution",
                )
                first_result = deepcopy(
                    self._record(
                        discover_active_mission(workspace).manifest,
                        self._grant_id(issued),
                    ).get("result")
                )
                replacement = ManifestController(plugin_root=runtime)
                try:
                    self._execute(
                        replacement,
                        workspace,
                        runtime,
                        replay_payload,
                        operation="file.read",
                        target="evidence.txt",
                        refs=["evidence.txt"],
                        legacy_grant=deepcopy(legacy),
                        turn="replay",
                    )
                except (ControllerError, TransitionError) as error:
                    refusal = error

            replayed_result = self._record(
                discover_active_mission(workspace).manifest,
                self._grant_id(issued),
            ).get("result")
            self.assertNotEqual(
                first.process_instance_id, replacement.process_instance_id
            )
            self.assertEqual(len(reads), 1)
            self.assertEqual(replayed_result, first_result)
            self.assertEqual(str(refusal), "CAPABILITY_RESULT_REPLAY")

    def test_orphaned_execution_before_target_read_fails_closed(self) -> None:
        self._assert_orphan_fails_closed(
            crash_action="crash-before-read",
            expected_exit=_EXIT_BEFORE_READ,
            reads_after_crash=0,
        )

    def test_orphaned_execution_after_one_target_read_fails_closed(self) -> None:
        self._assert_orphan_fails_closed(
            crash_action="crash-after-read",
            expected_exit=_EXIT_AFTER_READ,
            reads_after_crash=1,
        )

    def test_web_operation_refuses_before_retrieval_resolution_or_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime, workspace, controller = self._setup(Path(temp))
            url = "https://example.test/source"
            source = f"source:{url}"
            refusal = None
            with (
                patch(
                    "practical_agency.capability_operations._retrieve_web",
                    wraps=capability_operations._retrieve_web,
                ) as retrieve,
                patch(
                    "practical_agency.capability_operations.socket.getaddrinfo",
                    return_value=[
                        (
                            socket.AF_INET,
                            socket.SOCK_STREAM,
                            socket.IPPROTO_TCP,
                            "",
                            ("93.184.216.34", 0),
                        )
                    ],
                ) as resolver,
                patch(
                    "practical_agency.capability_operations.urllib.request.urlopen",
                    return_value=_HttpResponse(url),
                ) as network,
            ):
                try:
                    issued = self._issue(
                        controller,
                        workspace,
                        runtime,
                        operation="web.open",
                        target=url,
                        scope=[url, source],
                        turn="issue-web",
                    )
                    self._execute(
                        controller,
                        workspace,
                        runtime,
                        issued,
                        operation="web.open",
                        target=url,
                        refs=[source],
                        evidence={source: "caller source bytes"},
                        turn="execute-web",
                    )
                except ControllerError as error:
                    refusal = error

            latest = discover_active_mission(workspace).manifest
            self.assertEqual(retrieve.call_count, 0)
            self.assertEqual(resolver.call_count, 0)
            self.assertEqual(network.call_count, 0)
            self.assertEqual(str(refusal), "WEB_OPERATION_DISABLED")
            for item in latest.capabilities.get("invoked", []):
                if isinstance(item, Mapping) and isinstance(
                    item.get("result"), Mapping
                ):
                    self.assertEqual(item["result"].get("observed_effects", []), [])

    def test_mcp_tool_list_removes_injection_surfaces_and_caller_grant(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            tools = self._tools(McpServer(plugin_root=self._runtime(Path(temp))))
            self.assertNotIn("manifest_capability_request", tools)
            self.assertNotIn("manifest_capability_result", tools)
            execute = tools["manifest_capability_execute"]["inputSchema"]
            self.assertIn("grant_id", execute["required"])
            self.assertNotIn("grant", execute["properties"])
            self.assertIn("reason", tools["manifest_accept"]["inputSchema"]["properties"])

    def test_mcp_caller_grant_refuses_before_file_or_checkpoint_effect(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime, workspace, controller = self._setup(Path(temp))
            issued = self._issue(controller, workspace, runtime)
            caller_grant = self._legacy_grant(issued) or {
                "schema": "capability-grant@1",
                "grant_id": self._grant_id(issued),
            }
            before = discover_active_mission(workspace).manifest.to_dict()
            server = McpServer(plugin_root=runtime)
            with self._count_reads(workspace / "evidence.txt") as reads:
                response, error = self._mcp_call(
                    server,
                    2,
                    "manifest_capability_execute",
                    {
                        "grant": caller_grant,
                        "operation": "file.read",
                        "target": "evidence.txt",
                        "evidence_refs": ["evidence.txt"],
                        **self._refs(
                            workspace,
                            runtime,
                            "manifest_capability_execute",
                            "mcp-caller-grant",
                        ),
                    },
                )

            self.assertEqual(reads, [])
            self.assertEqual(
                discover_active_mission(workspace).manifest.to_dict(), before
            )
            self.assertIsNone(response)
            self.assertEqual(str(error), "MCP_PROTOCOL_ERROR")
            execute = self._tools(server)["manifest_capability_execute"]["inputSchema"]
            self.assertIn("grant_id", execute["required"])
            self.assertNotIn("grant", execute["properties"])

    def test_mcp_direct_request_injection_refuses_before_checkpoint_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime, workspace, controller = self._setup(Path(temp))
            issued = self._issue(controller, workspace, runtime)
            current = discover_active_mission(workspace).manifest
            forged = self._legacy_grant(issued) or {
                "schema": "capability-grant@1",
                "grant_id": "grant-caller-injected",
            }
            forged["grant_id"] = "grant-caller-injected"
            forged["mission_revision"] = current.revision
            forged.setdefault("return_point", {})["revision"] = current.revision
            forged["evidence_scope"] = ["secret.txt"]
            before = current.to_dict()
            server = McpServer(plugin_root=runtime)

            response, error = self._mcp_call(
                server,
                3,
                "manifest_capability_request",
                {
                    "grant": forged,
                    "request": self._intent("file.read", "secret.txt"),
                    **self._refs(
                        workspace,
                        runtime,
                        "manifest_capability_request",
                        "mcp-request-injection",
                    ),
                },
            )

            self.assertEqual(
                discover_active_mission(workspace).manifest.to_dict(), before
            )
            self.assertIsNone(response)
            self.assertEqual(str(error), "MCP_PROTOCOL_ERROR")
            self.assertNotIn("manifest_capability_request", self._tools(server))

    def test_mcp_direct_result_injection_refuses_before_checkpoint_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime, workspace, controller = self._setup(Path(temp))
            issued = self._issue(controller, workspace, runtime)
            current = discover_active_mission(workspace).manifest
            record = self._record(current, self._grant_id(issued))
            grant = record.get("grant")
            request = record.get("request")
            return_point = (
                grant.get("return_point")
                if isinstance(grant, Mapping)
                else request.get("return_point")
                if isinstance(request, Mapping)
                else {}
            )
            before = current.to_dict()
            server = McpServer(plugin_root=runtime)

            response, error = self._mcp_call(
                server,
                4,
                "manifest_capability_result",
                {
                    "grant_id": self._grant_id(issued),
                    "result": {
                        "schema": "capability-result@1",
                        "verdict": "PASS",
                        "returned_control_point": return_point,
                        "coverage_limits": ["caller assertion only"],
                        "evidence_refs": ["evidence.txt"],
                        "observed_effects": [],
                    },
                    **self._refs(
                        workspace,
                        runtime,
                        "manifest_capability_result",
                        "mcp-result-injection",
                    ),
                },
            )

            self.assertEqual(
                discover_active_mission(workspace).manifest.to_dict(), before
            )
            self.assertIsNone(response)
            self.assertEqual(str(error), "MCP_PROTOCOL_ERROR")
            self.assertNotIn("manifest_capability_result", self._tools(server))

    def test_persisted_request_and_result_cannot_violate_strict_schemas(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime, workspace, controller = self._setup(Path(temp))
            issued = self._issue(controller, workspace, runtime)
            self._execute(
                controller,
                workspace,
                runtime,
                issued,
                operation="file.read",
                target="evidence.txt",
                refs=["evidence.txt"],
                turn="schema-execution",
            )
            record = self._record(
                discover_active_mission(workspace).manifest,
                self._grant_id(issued),
            )
            request, result = record.get("request"), record.get("result")
            self.assertIsInstance(request, Mapping)
            self.assertIsInstance(result, Mapping)
            assert isinstance(request, Mapping) and isinstance(result, Mapping)
            request_schema = json.loads(
                (ROOT / "contracts" / "capability-request.schema.json").read_text()
            )
            result_schema = json.loads(
                (ROOT / "contracts" / "capability-result.schema.json").read_text()
            )

            self.assertEqual(_schema_errors(request, request_schema), [])
            self.assertEqual(_schema_errors(result, result_schema), [])
            self.assertEqual(
                request["expected_output_contract"],
                "contracts/capability-result.schema.json",
            )
            self.assertEqual(result["request_id"], request["request_id"])
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["returned_control_point"], request["return_point"])
            self.assertTrue(result["observed_effects"])

    def _assert_negative_verdict(
        self, verdict: str, reason: str, expected_status: str
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime, workspace, _ = self._setup(Path(temp))
            manifest = discover_active_mission(workspace).manifest
            manifest = record_fixture_verifier_result(manifest)
            manifest = apply_event_data(
                manifest, "begin_verification", "mission-steward", {}
            )
            FileCheckpointStore(
                workspace / "missions" / manifest.mission_id / "checkpoints"
            ).save(manifest)
            controller = ManifestController(plugin_root=runtime)
            response = None
            call_error = None
            try:
                response = controller.manifest_accept(
                    acceptor_ref="reviewer:independent",
                    verdict=verdict,
                    reason=reason,
                    separation_assurance="declared-role-separation",
                    **self._refs(
                        workspace,
                        runtime,
                        "manifest_accept",
                        f"negative-{verdict.lower()}",
                    ),
                )
            except (ControllerError, TypeError) as error:
                call_error = error

            latest = discover_active_mission(workspace).manifest
            marker = f"{verdict}:{reason}"
            rejections = [
                item
                for item in latest.continuity.get("decisions", [])
                if isinstance(item, Mapping)
                and item.get("kind") == "completion-rejection"
            ]
            self.assertEqual(latest.state["status"], expected_status)
            self.assertNotEqual(latest.state["status"], "completed")
            self.assertIn(marker, latest.integrity["unresolved_verdicts"])
            self.assertIn(marker, latest.state["blockers"])
            self.assertEqual(len(rejections), 1)
            self.assertEqual(rejections[0]["verdict"], verdict)
            self.assertEqual(rejections[0]["reason"], reason)
            self.assertTrue(rejections[0]["evidence_refs"])
            self.assertTrue(rejections[0]["coverage_limits"])
            self.assertIsNone(call_error)
            self.assertIsNotNone(response)
            assert response is not None
            self.assertEqual(response["mission_status"], expected_status)
            self.assertEqual(response["verdict"], verdict)
            self.assertEqual(response["reason"], reason)
            self.assertTrue(response["evidence_refs"])
            self.assertTrue(response["coverage_limits"])

    def test_independent_fail_verdict_is_durable_without_completion(self) -> None:
        self._assert_negative_verdict(
            "FAIL", "artifact proof contradicted", "active"
        )

    def test_independent_inconclusive_verdict_is_durable_without_completion(
        self,
    ) -> None:
        self._assert_negative_verdict(
            "INCONCLUSIVE", "observer coverage is incomplete", "blocked"
        )


if __name__ == "__main__":
    if sys.argv[1:2] == [_ORPHAN_WORKER]:
        _run_orphan_worker(sys.argv[2:])
    else:
        unittest.main()
