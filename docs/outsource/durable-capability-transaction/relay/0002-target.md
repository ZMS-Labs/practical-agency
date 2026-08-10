schema: outsource-relay@1
work_id: durable-capability-transaction
based_on_commit: 578cb9ee3165c899af26da1111163effa19949fc
status: PARTIAL
summary: |
Stage 1 tests-only patch prepared from the exact packet revision. It adds focused controller/checkpoint adversarial tests plus real stdio MCP surface tests for canonical grant authority, pre-observation refusal, durable one-use replay resistance, strict runtime contracts, disabled web transport, and reason-bearing negative verdict preservation. No production code is included, and no tests or runtime probes were executed.
work_product: |
diff --git a/tests/test_durable_capability_transaction.py b/tests/test_durable_capability_transaction.py
new file mode 100644
--- /dev/null
+++ b/tests/test_durable_capability_transaction.py
@@ -0,0 +1,726 @@
+from future import annotations
+
+import json
+import re
+import shutil
+import tempfile
+import unittest
+from collections.abc import Iterator, Mapping
+from contextlib import contextmanager
+from copy import deepcopy
+from pathlib import Path
+from typing import Any
+from unittest.mock import patch
+
+from practical_agency.checkpoint_store import FileCheckpointStore
+from practical_agency.controller import ControllerError, ManifestController
+from practical_agency.host_evidence import write_host_context, write_host_gate
+from practical_agency.manifest_model import MissionManifest
+from practical_agency.mission_repository import discover_active_mission
+from practical_agency.state_machine import apply_event_data
+from tests.helpers import minimal_payload, record_fixture_verifier_result
+
+
+ROOT = Path(file).resolve().parents[1]
+
+
+def _value_has_type(value: object, expected: str) -> bool:

if expected == "object":

   return isinstance(value, dict)

if expected == "array":

   return isinstance(value, list)

if expected == "string":

   return isinstance(value, str)

if expected == "integer":

   return isinstance(value, int) and not isinstance(value, bool)

if expected == "null":

   return value is None

raise AssertionError(f"unsupported test schema type: {expected}")

+def _assert_schema_instance(

case: unittest.TestCase,

value: object,

schema: Mapping[str, Any],

*,

path: str = "$",
+) -> None:

if "const" in schema:

   case.assertEqual(value, schema["const"], f"{path}: const mismatch")

if "enum" in schema:

   case.assertIn(value, schema["enum"], f"{path}: enum mismatch")

expected_type = schema.get("type")

if isinstance(expected_type, list):

   case.assertTrue(
       any(
           isinstance(item, str) and _value_has_type(value, item)
           for item in expected_type
       ),
       f"{path}: expected one of {expected_type!r}, got {type(value).__name__}",
   )
   if value is None:
       return

elif isinstance(expected_type, str):

   case.assertTrue(
       _value_has_type(value, expected_type),
       f"{path}: expected {expected_type}, got {type(value).__name__}",
   )

if expected_type == "object":

   assert isinstance(value, dict)
   properties = schema.get("properties", {})
   required = schema.get("required", [])
   case.assertIsInstance(properties, Mapping, f"{path}: properties must be an object")
   case.assertIsInstance(required, list, f"{path}: required must be an array")
   for key in required:
       case.assertIn(key, value, f"{path}: missing required property {key!r}")
   if schema.get("additionalProperties") is False:
       case.assertEqual(
           set(value) - set(properties),
           set(),
           f"{path}: unexpected properties",
       )
   for key, item in value.items():
       child = properties.get(key)
       if isinstance(child, Mapping):
           _assert_schema_instance(case, item, child, path=f"{path}.{key}")

elif expected_type == "array":

   assert isinstance(value, list)
   minimum = int(schema.get("minItems", 0))
   case.assertGreaterEqual(len(value), minimum, f"{path}: too few items")
   item_schema = schema.get("items")
   if isinstance(item_schema, Mapping):
       for index, item in enumerate(value):
           _assert_schema_instance(
               case, item, item_schema, path=f"{path}[{index}]"
           )

elif expected_type == "string":

   assert isinstance(value, str)
   case.assertGreaterEqual(
       len(value), int(schema.get("minLength", 0)), f"{path}: string too short"
   )
   pattern = schema.get("pattern")
   if isinstance(pattern, str):
       case.assertIsNotNone(
           re.fullmatch(pattern, value), f"{path}: pattern mismatch"
       )

elif expected_type == "integer":

   assert isinstance(value, int) and not isinstance(value, bool)
   if "minimum" in schema:
       case.assertGreaterEqual(value, int(schema["minimum"]), f"{path}: below minimum")

+@contextmanager
+def _observed_target_reads(target: Path) -> Iterator[list[Path]]:

observed: list[Path] = []

identity = target.resolve()

original = Path.read_text

def read_text(path: Path, *args: object, **kwargs: object) -> str:

   if path.resolve() == identity:
       observed.append(identity)
   return original(path, *args, **kwargs)

with patch.object(Path, "read_text", read_text):

   yield observed

+class DurableCapabilityTransactionTests(unittest.TestCase):

def _workspace(self, temp: str) -> Path:

   workspace = Path(temp) / "workspace"
   workspace.mkdir()
   (workspace / ".git").mkdir()
   return workspace

def _plugin_root(self, temp: str) -> tuple[Path, Path]:

   plugin_root = Path(temp) / "plugin"
   plugin_root.mkdir()
   shutil.copytree(ROOT / "practical_agency", plugin_root / "practical_agency")
   shutil.copytree(ROOT / "hooks", plugin_root / "hooks")
   skill_path = plugin_root / "skills" / "dynamic-reader" / "SKILL.md"
   skill_path.parent.mkdir(parents=True)
   skill_path.write_text(
       """---

+name: dynamic-reader
+description: Read one exact evidence target under mission authority.
+metadata:

kind: skill

persistence: session

independence: actor

authority_required: [repository:read]

input_contract: contracts/capability-request.schema.json

output_contract: contracts/capability-result.schema.json
+---

+# dynamic-reader
+
+Read only the exact target authorized by the durable mission transaction.
+""",

       encoding="utf-8",
   )
   return plugin_root, skill_path

def _host_refs(

   self,
   workspace: Path,
   plugin_root: Path,
   operation: str,
   *,
   turn: str,
   prompt: str | None = None,

) -> dict[str, str]:

   context = write_host_context(
       workspace_root=workspace,
       prompt=prompt or f"$manifest {operation}",
       session_id="session-durable-capability",
       turn_id=turn,
       plugin_root=plugin_root,
   )
   gate = write_host_gate(
       context_ref=context.path,
       tool_name=f"mcp__practical_agency__{operation}",
       tool_use_id=f"tool-{turn}-{operation}",
       session_id="session-durable-capability",
       turn_id=turn,
       workspace_root=workspace,
       lock_reason="explicit-manifest-intent",
       decision="allow-controller",
       plugin_root=plugin_root,
   )
   return {
       "_host_context_ref": context.path,
       "_host_gate_ref": gate.path,
   }

def _definition(self, permissions: list[str]) -> dict[str, object]:

   return {
       "instruction": "Authorize one exact durable capability transaction.",
       "desired_state": "The bounded evidence is observed at most once.",
       "governed_artifacts": [
           {
               "path": "outcome.md",
               "content": "# Capability outcome\n",
           }
       ],
       "permissions": list(permissions),
       "protected_state": [
           "secret.txt",
           "every target outside the canonical capability request",
       ],
       "acceptable_costs": ["one bounded local observation"],
       "escalation_required_for": ["any wider scope or second use"],
       "stop_conditions": ["any named refusal"],
       "completion_acceptor": "acceptor:operator-review",
   }

def _authorized(

   self,
   workspace: Path,
   plugin_root: Path,
   *,
   permissions: list[str],

) -> ManifestController:

   controller = ManifestController(plugin_root=plugin_root)
   defined = controller.manifest_define(
       definition=self._definition(permissions),
       **self._host_refs(
           workspace,
           plugin_root,
           "manifest_define",
           turn="define",
       ),
   )
   contract_hash = str(defined["authority_contract_sha256"])
   controller.manifest_authorize(
       authority_contract_sha256=contract_hash,
       **self._host_refs(
           workspace,
           plugin_root,
           "manifest_authorize",
           turn="authorize",
           prompt=f"approve manifest {contract_hash}",
       ),
   )
   return controller

def _issue(

   self,
   controller: ManifestController,
   workspace: Path,
   plugin_root: Path,
   *,
   operation: str,
   target: str,
   evidence_scope: list[str] | None = None,
   turn: str,

) -> dict[str, Any]:

   return controller.manifest_capability_issue(
       capability_id="dynamic-reader",
       blocking_condition=f"observe {target}",
       admitted_operation=operation,
       evidence_scope=list(evidence_scope or [target]),
       request={
           "bounded_question_or_action": f"{operation} {target} exactly once",
           "expected_output_contract": "contracts/capability-result.schema.json",
           "timeout_or_stop_condition": "stop after one observation or any refusal",
       },
       **self._host_refs(
           workspace,
           plugin_root,
           "manifest_capability_issue",
           turn=turn,
       ),
   )

def _schema(self, name: str) -> Mapping[str, Any]:

   payload = json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))
   self.assertIsInstance(payload, dict)
   return payload

def _assert_no_completed_effect(

   self, workspace: Path, *, grant_id: str | None = None

) -> None:

   latest = discover_active_mission(workspace).manifest
   records = [
       item
       for item in latest.capabilities.get("invoked", [])
       if isinstance(item, Mapping)
       and (grant_id is None or item.get("grant_id") == grant_id)
   ]
   if grant_id is not None:
       self.assertEqual(len(records), 1)
   for record in records:
       result = record.get("result")
       if result is None:
           continue
       self.assertIsInstance(result, Mapping)
       _assert_schema_instance(
           self,
           result,
           self._schema("capability-result.schema.json"),
       )
       self.assertIn(result.get("status"), {"declined", "blocked", "failed"})
       self.assertEqual(result.get("observed_effects"), [])

def _save_verifying_manifest(self, workspace: Path) -> MissionManifest:

   payload = minimal_payload()
   payload["mission_id"] = "verdict-mission"
   payload["integrity"]["completion_acceptor"] = "acceptor:operator-review"
   manifest = MissionManifest.from_dict(payload)
   manifest = apply_event_data(
       manifest,
       "approve",
       "operator:test",
       {"checkpoint_ref": "checkpoint:fixture"},
   )
   manifest = record_fixture_verifier_result(manifest)
   manifest = apply_event_data(
       manifest,
       "begin_verification",
       "mission-steward",
       {},
   )
   FileCheckpointStore(
       workspace / "missions" / manifest.mission_id / "checkpoints"
   ).save(manifest)
   return manifest

def test_forged_same_id_grant_cannot_widen_scope_before_observation(self) -> None:

   with tempfile.TemporaryDirectory() as temp:
       workspace = self._workspace(temp)
       plugin_root, _ = self._plugin_root(temp)
       (workspace / "evidence.txt").write_text("allowed", encoding="utf-8")
       secret = workspace / "secret.txt"
       secret.write_text("protected", encoding="utf-8")
       controller = self._authorized(
           workspace, plugin_root, permissions=["repository:read"]
       )
       issued = self._issue(
           controller,
           workspace,
           plugin_root,
           operation="file.read",
           target="evidence.txt",
           turn="issue-forgery",
       )
       canonical = deepcopy(issued["grant"])
       forged = deepcopy(canonical)
       forged["evidence_scope"] = ["secret.txt"]
       refusal: str | None = None
       with _observed_target_reads(secret) as reads:
           try:
               controller.manifest_capability_execute(
                   grant=forged,
                   operation="file.read",
                   target="secret.txt",
                   evidence_refs=["secret.txt"],
                   **self._host_refs(
                       workspace,
                       plugin_root,
                       "manifest_capability_execute",
                       turn="execute-forgery",
                   ),
               )
           except ControllerError as error:
               refusal = str(error)
       self.assertEqual(reads, [])
       self.assertEqual(refusal, "CAPABILITY_GRANT_MISMATCH")
       self._assert_no_completed_effect(
           workspace, grant_id=str(canonical["grant_id"])
       )

def test_stale_descriptor_is_refused_before_file_observation(self) -> None:

   with tempfile.TemporaryDirectory() as temp:
       workspace = self._workspace(temp)
       plugin_root, skill_path = self._plugin_root(temp)
       target = workspace / "evidence.txt"
       target.write_text("proof", encoding="utf-8")
       controller = self._authorized(
           workspace, plugin_root, permissions=["repository:read"]
       )
       issued = self._issue(
           controller,
           workspace,
           plugin_root,
           operation="file.read",
           target="evidence.txt",
           turn="issue-stale-descriptor",
       )
       skill_path.write_text(
           skill_path.read_text(encoding="utf-8") + "\nDescriptor changed.\n",
           encoding="utf-8",
       )
       refusal: str | None = None
       with _observed_target_reads(target) as reads:
           try:
               controller.manifest_capability_execute(
                   grant=deepcopy(issued["grant"]),
                   operation="file.read",
                   target="evidence.txt",
                   evidence_refs=["evidence.txt"],
                   **self._host_refs(
                       workspace,
                       plugin_root,
                       "manifest_capability_execute",
                       turn="execute-stale-descriptor",
                   ),
               )
           except ControllerError as error:
               refusal = str(error)
       self.assertEqual(reads, [])
       self.assertEqual(refusal, "CAPABILITY_DESCRIPTOR_MISMATCH")
       self._assert_no_completed_effect(
           workspace, grant_id=str(issued["grant"]["grant_id"])
       )

def test_missing_descriptor_authority_is_refused_before_observation(self) -> None:

   with tempfile.TemporaryDirectory() as temp:
       workspace = self._workspace(temp)
       plugin_root, _ = self._plugin_root(temp)
       target = workspace / "evidence.txt"
       target.write_text("proof", encoding="utf-8")
       controller = self._authorized(
           workspace, plugin_root, permissions=["repository:write"]
       )
       issued: dict[str, Any] | None = None
       refusal: str | None = None
       with _observed_target_reads(target) as reads:
           try:
               issued = self._issue(
                   controller,
                   workspace,
                   plugin_root,
                   operation="file.read",
                   target="evidence.txt",
                   turn="issue-without-authority",
               )
               controller.manifest_capability_execute(
                   grant=deepcopy(issued["grant"]),
                   operation="file.read",
                   target="evidence.txt",
                   evidence_refs=["evidence.txt"],
                   **self._host_refs(
                       workspace,
                       plugin_root,
                       "manifest_capability_execute",
                       turn="execute-without-authority",
                   ),
               )
           except ControllerError as error:
               refusal = str(error)
       self.assertEqual(reads, [])
       self.assertEqual(refusal, "CAPABILITY_AUTHORITY_REQUIRED")
       self._assert_no_completed_effect(
           workspace,
           grant_id=(
               str(issued["grant"]["grant_id"]) if issued is not None else None
           ),
       )

def test_fresh_copy_replay_after_controller_replacement_has_one_effect(self) -> None:

   with tempfile.TemporaryDirectory() as temp:
       workspace = self._workspace(temp)
       plugin_root, _ = self._plugin_root(temp)
       target = workspace / "evidence.txt"
       target.write_text("proof", encoding="utf-8")
       first = self._authorized(
           workspace, plugin_root, permissions=["repository:read"]
       )
       issued = self._issue(
           first,
           workspace,
           plugin_root,
           operation="file.read",
           target="evidence.txt",
           turn="issue-replay",
       )
       serialized_grant = json.dumps(issued["grant"], sort_keys=True)
       refusal: str | None = None
       with _observed_target_reads(target) as reads:
           first.manifest_capability_execute(
               grant=json.loads(serialized_grant),
               operation="file.read",
               target="evidence.txt",
               evidence_refs=["evidence.txt"],
               **self._host_refs(
                   workspace,
                   plugin_root,
                   "manifest_capability_execute",
                   turn="execute-first",
               ),
           )
           replacement = ManifestController(plugin_root=plugin_root)
           try:
               replacement.manifest_capability_execute(
                   grant=json.loads(serialized_grant),
                   operation="file.read",
                   target="evidence.txt",
                   evidence_refs=["evidence.txt"],
                   **self._host_refs(
                       workspace,
                       plugin_root,
                       "manifest_capability_execute",
                       turn="execute-replay",
                   ),
               )
           except ControllerError as error:
               refusal = str(error)
       self.assertEqual(reads, [target.resolve()])
       self.assertEqual(refusal, "GRANT_REPLAYED")
       latest = discover_active_mission(workspace).manifest
       records = [
           item
           for item in latest.capabilities["invoked"]
           if item.get("grant_id") == issued["grant"]["grant_id"]
       ]
       self.assertEqual(len(records), 1)
       self.assertIsNotNone(records[0]["result"])
       self.assertEqual(len(records[0]["result"]["observed_effects"]), 1)

def test_issued_runtime_request_matches_committed_strict_schema(self) -> None:

   with tempfile.TemporaryDirectory() as temp:
       workspace = self._workspace(temp)
       plugin_root, _ = self._plugin_root(temp)
       (workspace / "evidence.txt").write_text("proof", encoding="utf-8")
       controller = self._authorized(
           workspace, plugin_root, permissions=["repository:read"]
       )
       issued = self._issue(
           controller,
           workspace,
           plugin_root,
           operation="file.read",
           target="evidence.txt",
           turn="issue-schema-request",
       )
       latest = discover_active_mission(workspace).manifest
       record = latest.capabilities["invoked"][0]
       request = record["request"]
       _assert_schema_instance(
           self,
           request,
           self._schema("capability-request.schema.json"),
       )
       self.assertEqual(request["mission_id"], latest.mission_id)
       self.assertEqual(
           request["mission_revision"], issued["grant"]["mission_revision"]
       )
       self.assertEqual(request["capability_id"], "dynamic-reader")
       self.assertEqual(
           request["capability_source_sha256"],
           issued["grant"]["capability_descriptor_sha256"],
       )
       self.assertEqual(request["return_point"], issued["grant"]["return_point"])
       self.assertIsInstance(request["authority_receipt"], str)
       self.assertTrue(request["authority_receipt"])

def test_valid_bounded_local_read_executes_once_and_persists_schema_result(

   self,

) -> None:

   with tempfile.TemporaryDirectory() as temp:
       workspace = self._workspace(temp)
       plugin_root, _ = self._plugin_root(temp)
       target = workspace / "evidence.txt"
       target.write_text("proof", encoding="utf-8")
       controller = self._authorized(
           workspace, plugin_root, permissions=["repository:read"]
       )
       issued = self._issue(
           controller,
           workspace,
           plugin_root,
           operation="file.read",
           target="evidence.txt",
           turn="issue-valid",
       )
       with _observed_target_reads(target) as reads:
           response = controller.manifest_capability_execute(
               grant_id=str(issued["grant"]["grant_id"]),
               **self._host_refs(
                   workspace,
                   plugin_root,
                   "manifest_capability_execute",
                   turn="execute-valid",
               ),
           )
       self.assertEqual(reads, [target.resolve()])
       result = response["result"]
       _assert_schema_instance(
           self,
           result,
           self._schema("capability-result.schema.json"),
       )
       latest = discover_active_mission(workspace).manifest
       record = next(
           item
           for item in latest.capabilities["invoked"]
           if item["grant_id"] == issued["grant"]["grant_id"]
       )
       self.assertEqual(record["result"], result)
       self.assertEqual(result["request_id"], record["request"]["request_id"])
       self.assertEqual(result["status"], "completed")
       self.assertTrue(result["artifact_refs"])
       self.assertEqual(len(result["observed_effects"]), 1)

def test_web_operation_is_disabled_before_resolver_or_network_call(self) -> None:

   with tempfile.TemporaryDirectory() as temp:
       workspace = self._workspace(temp)
       plugin_root, _ = self._plugin_root(temp)
       controller = self._authorized(
           workspace,
           plugin_root,
           permissions=["repository:read", "network:read"],
       )
       target = "https://example.test/source"
       source_ref = f"source:{target}"
       issued: dict[str, Any] | None = None
       refusal: str | None = None
       with (
           patch(
               "practical_agency.capability_operations.socket.getaddrinfo",
               return_value=[
                   (2, 1, 6, "", ("93.184.216.34", 443)),
               ],
           ) as resolver,
           patch(
               "practical_agency.capability_operations.urllib.request.urlopen"
           ) as open_url,
       ):
           response = open_url.return_value.__enter__.return_value
           response.geturl.return_value = target
           response.status = 200
           response.read.return_value = b"observed"
           try:
               issued = self._issue(
                   controller,
                   workspace,
                   plugin_root,
                   operation="web.open",
                   target=target,
                   evidence_scope=[target, source_ref],
                   turn="issue-web-disabled",
               )
               controller.manifest_capability_execute(
                   grant=deepcopy(issued["grant"]),
                   operation="web.open",
                   target=target,
                   evidence_refs=[source_ref],
                   evidence_payload={source_ref: "observed"},
                   **self._host_refs(
                       workspace,
                       plugin_root,
                       "manifest_capability_execute",
                       turn="execute-web-disabled",
                   ),
               )
           except ControllerError as error:
               refusal = str(error)
       self.assertEqual(resolver.call_count, 0)
       self.assertEqual(open_url.call_count, 0)
       self.assertEqual(refusal, "WEB_OPERATION_DISABLED")
       self._assert_no_completed_effect(
           workspace,
           grant_id=(
               str(issued["grant"]["grant_id"]) if issued is not None else None
           ),
       )

def test_controller_durably_preserves_fail_and_inconclusive_verdicts(

   self,

) -> None:

   cases = (("FAIL", "active"), ("INCONCLUSIVE", "blocked"))
   for verdict, expected_status in cases:
       with self.subTest(verdict=verdict), tempfile.TemporaryDirectory() as temp:
           workspace = self._workspace(temp)
           verifying = self._save_verifying_manifest(workspace)
           evidence_ref = str(
               verifying.continuity["verifier_results"][-1]["result_ref"]
           )
           reason = f"{verdict.lower()} independent review"
           coverage_limits = ["fixture review; no external principal proof"]
           controller = ManifestController(plugin_root=ROOT)
           controller.manifest_accept(
               acceptor_ref="acceptor:operator-review",
               verdict=verdict,
               reason=reason,
               evidence_refs=[evidence_ref],
               coverage_limits=coverage_limits,
               separation_assurance="declared-role-separation",
               **self._host_refs(
                   workspace,
                   ROOT,
                   "manifest_accept",
                   turn=f"accept-{verdict.lower()}",
               ),
           )
           latest = discover_active_mission(workspace).manifest
           self.assertEqual(latest.state["status"], expected_status)
           marker = f"{verdict}:{reason}"
           self.assertIn(marker, latest.integrity["unresolved_verdicts"])
           self.assertIn(marker, latest.state["blockers"])
           decision = latest.continuity["decisions"][-1]
           self.assertEqual(decision["kind"], "completion-rejection")
           self.assertEqual(decision["verdict"], verdict)
           self.assertEqual(decision["reason"], reason)
           self.assertEqual(decision["evidence_refs"], [evidence_ref])
           self.assertEqual(decision["coverage_limits"], coverage_limits)

+if name == "main":

unittest.main()
diff --git a/tests/test_mcp_server.py b/tests/test_mcp_server.py
--- a/tests/test_mcp_server.py
+++ b/tests/test_mcp_server.py
@@ -21,9 +21,7 @@
}
TOOL_NAMES = [
"manifest_engage",

"manifest_capability_request",
"manifest_capability_issue",

"manifest_capability_result",
"manifest_capability_execute",
"manifest_clarify",
"manifest_define",
@@ -130,7 +128,7 @@
(workspace / ".git").mkdir()
return workspace

def test_real_stdio_server_initializes_and_lists_only_manifest_operations(self) -> None:

def test_real_stdio_server_lists_no_capability_injection_surfaces(self) -> None:
with tempfile.TemporaryDirectory() as temp:
workspace = self._workspace(temp)
with StdioServer(workspace) as server:
@@ -156,6 +154,22 @@
self.assertIn("_host_context_ref", schema["properties"])
self.assertIn("_host_gate_ref", schema["properties"])

           execute_tool = next(
               tool
               for tool in tools
               if tool["name"] == "manifest_capability_execute"
           )
           execute_schema = execute_tool["inputSchema"]
           for forbidden in (
               "grant",
               "operation",
               "target",
               "evidence_refs",
               "evidence_payload",
           ):
               self.assertNotIn(forbidden, execute_schema["properties"])
           self.assertEqual(execute_schema["required"], ["grant_id"])

def test_successful_tool_call_uses_hook_injected_refs(self) -> None:
with tempfile.TemporaryDirectory() as temp:
workspace = self._workspace(temp)
@@ -216,6 +230,63 @@
)
self.assertEqual(list(workspace.glob("missions//checkpoints/.json")), [])

def test_removed_capability_request_and_result_tools_fail_closed(self) -> None:

   with tempfile.TemporaryDirectory() as temp:
       workspace = self._workspace(temp)
       calls = (
           (
               "manifest_capability_request",
               {"grant": {}, "request": {}},
           ),
           (
               "manifest_capability_result",
               {"grant_id": "forged-grant", "result": {}},
           ),
       )
       with StdioServer(workspace) as server:
           for request_id, (name, arguments) in enumerate(calls, start=1):
               with self.subTest(name=name):
                   response = server.request(
                       request_id,
                       "tools/call",
                       {"name": name, "arguments": arguments},
                   )
                   self.assertEqual(
                       response["error"]["data"]["code"],
                       "MCP_PROTOCOL_ERROR",
                   )
       self.assertEqual(
           list(workspace.glob("missions/*/checkpoints/*.json")),
           [],
       )

def test_execute_rejects_caller_owned_grant_at_mcp_schema_boundary(self) -> None:

   with tempfile.TemporaryDirectory() as temp:
       workspace = self._workspace(temp)
       with StdioServer(workspace) as server:
           response = server.request(

+ 1,

               "tools/call",
               {
                   "name": "manifest_capability_execute",
                   "arguments": {
                       "grant": {"grant_id": "caller-forged"},
                       "operation": "file.read",
                       "target": "evidence.txt",
                   },
               },
           )
           self.assertEqual(
               response["error"]["data"]["code"],
               "MCP_PROTOCOL_ERROR",
           )
       self.assertEqual(
           list(workspace.glob("missions/*/checkpoints/*.json")),
           [],
       )

def test_codex_request_metadata_is_allowed_on_tool_listing_and_calls(self) -> None:
with tempfile.TemporaryDirectory() as temp:
workspace = self._workspace(temp)
evidence: |
TEST-TO-DEFECT MATRIX; ALL BASELINE FAILURES BELOW ARE SOURCE-DERIVED EXPECTATIONS, NOT EXECUTION CLAIMS.

tests/test_durable_capability_transaction.py::test_forged_same_id_grant_cannot_widen_scope_before_observation
Reachable defect: manifest_capability_execute trusts the caller-carried grant object. A copy retaining the real grant_id and return point can replace evidence_scope with protected secret.txt; execute_read reads that file before any durable canonical comparison.
Required proof: exact secret.txt Path.read_text count remains zero, refusal is CAPABILITY_GRANT_MISMATCH, and the canonical durable record contains no completed result.
Expected baseline RED: secret.txt is read, no CAPABILITY_GRANT_MISMATCH is raised, and a result can be recorded against the legitimate durable grant.

tests/test_durable_capability_transaction.py::test_stale_descriptor_is_refused_before_file_observation
Reachable defect: execution does not re-observe the descriptor digest saved at issue time.
Required proof: target read count remains zero, refusal is CAPABILITY_DESCRIPTOR_MISMATCH, and the pending durable record has no completed effect.
Expected baseline RED: the changed descriptor is not consulted and evidence.txt is read.

tests/test_durable_capability_transaction.py::test_missing_descriptor_authority_is_refused_before_observation
Reachable defect: descriptor authority_required is ignored by issue and execute; a mission with repository:write but without repository:read can perform the descriptor's read.
Required proof: target read count remains zero, refusal is CAPABILITY_AUTHORITY_REQUIRED, and no completed result is durable.
Expected baseline RED: issue succeeds, execute reads evidence.txt, and no authority refusal occurs.

tests/test_durable_capability_transaction.py::test_fresh_copy_replay_after_controller_replacement_has_one_effect
Reachable defect: used is mutated only on the transient input dictionary. A fresh JSON copy after checkpoint reload repeats the read before durable result replay is noticed.
Required proof: exactly one underlying Path.read_text across both controller instances, second call refuses GRANT_REPLAYED, and one durable result with one observation remains.
Expected baseline RED: the target is read twice; the second call reaches consume_grant only after observation and is expected to surface GRANT_STALE from the advanced manifest revision rather than durable GRANT_REPLAYED.

tests/test_durable_capability_transaction.py::test_issued_runtime_request_matches_committed_strict_schema
Reachable defect: manifest_capability_issue persists the caller's three-field mapping instead of a capability-request@1 object.
Required proof: the actual checkpointed request validates against contracts/capability-request.schema.json and binds mission revision, descriptor digest, return point, and a nonempty authority receipt.
Expected baseline RED: required schema fields are absent and the runtime object is not the committed closed contract.

tests/test_durable_capability_transaction.py::test_valid_bounded_local_read_executes_once_and_persists_schema_result
Reachable defect: there is no canonical grant_id-only controller execution path, and consume_grant emits a result incompatible with capability-result@1.
Required proof: one exact local read, a strict capability-result@1 returned and checkpointed, matching request_id, completed status, nonempty artifact_refs, and one observation.
Expected baseline RED: manifest_capability_execute has no grant_id-only API; the currently emitted object would also violate required fields and additionalProperties: false.

tests/test_durable_capability_transaction.py::test_web_operation_is_disabled_before_resolver_or_network_call
Reachable defect: web.open reaches socket.getaddrinfo and urllib.request.urlopen despite the packet decision to refuse web transport in this patch.
Required proof: resolver and urlopen call counts both remain zero, refusal is WEB_OPERATION_DISABLED, and no completed durable effect exists.
Expected baseline RED: current _retrieve_web resolves and opens the URL before any such refusal.

tests/test_durable_capability_transaction.py::test_controller_durably_preserves_fail_and_inconclusive_verdicts
Reachable defect: manifest_accept advertises FAIL and INCONCLUSIVE but supplies neither the reason-bearing controller inputs nor the state-machine reject transition.
Required proof: exact verdict, reason, evidence_refs, and coverage_limits are checkpointed as completion-rejection; FAIL returns the mission to active and INCONCLUSIVE to blocked, with unresolved markers preserved.
Expected baseline RED: the controller signature rejects the required reason/evidence/coverage arguments; with its current arguments it routes both verdicts to accept and the state machine requires PASS.

tests/test_mcp_server.py::test_real_stdio_server_lists_no_capability_injection_surfaces
Reachable defect: reachable MCP still lists manifest_capability_request and manifest_capability_result, while manifest_capability_execute exposes caller-owned grant, operation, target, and evidence fields.
Required proof: the injection tools are absent and execute requires only grant_id plus hook-injected host references.
Expected baseline RED: tool-name equality and execute-schema assertions fail against the current surface.

tests/test_mcp_server.py::test_removed_capability_request_and_result_tools_fail_closed
Reachable defect: callers can invoke direct request/result injection tools.
Required proof: real stdio calls fail at the MCP protocol boundary and create no checkpoint files.
Expected baseline RED: both names are recognized and dispatch far enough to return a controller HOST_GATE_UNAVAILABLE tool result rather than an unknown-tool MCP_PROTOCOL_ERROR.

tests/test_mcp_server.py::test_execute_rejects_caller_owned_grant_at_mcp_schema_boundary
Reachable defect: the reachable MCP execute schema accepts a caller-owned grant and caller-selected operation/target.
Required proof: the real stdio request is rejected as MCP_PROTOCOL_ERROR before controller state exists.
Expected baseline RED: the payload satisfies the current schema and reaches controller dispatch, returning HOST_GATE_UNAVAILABLE instead of a protocol refusal.

ANTI-PROXY CHARACTERISTICS:

Controller tests create and authorize a real mission, issue through the real descriptor provider, reload through FileCheckpointStore/discover_active_mission, and inspect durable invoked records.

Refusal tests spy only on the exact underlying target read or resolver/urlopen seams; they do not treat mock invocation as the behavioral result.

Replay uses a JSON-serialized fresh grant copy and a replacement ManifestController.

Contract tests validate the actual checkpointed/generated objects against the committed schema documents with a test-local validator for the exact schema vocabulary used by those documents.

MCP tests launch the real newline-delimited stdio server process and assert both advertised surface and call behavior.
requirements: |
DCT-001: COVERED. The unified diff changes only tests/test_durable_capability_transaction.py and tests/test_mcp_server.py; there are no production hunks.
DCT-002: COVERED BY RED TESTS. Forged same-ID/wider scope, descriptor drift, and absent descriptor authority each require a named pre-observation refusal and zero target reads.
DCT-003: COVERED BY RED TEST. Fresh JSON replay across controller replacement must leave exactly one underlying local observation and one durable result.
DCT-004: COVERED BY REAL MCP RED TESTS. Direct request/result tools must disappear, and caller-owned grant/operation/target input must fail at the MCP schema boundary.
DCT-005: COVERED BY RED TESTS. Actual checkpointed request and returned/persisted result objects are validated against the committed strict schemas.
DCT-006: COVERED BY RED TEST. web.open must return WEB_OPERATION_DISABLED before resolver or network access, with zero durable effect.
DCT-007: COVERED BY RED TEST. FAIL and INCONCLUSIVE must traverse the real controller/checkpoint/state-machine path with exact reason, evidence, coverage, and non-completed state.
DCT-008: COVERED BY RED TEST. A valid bounded local read is expressed through the wished-for canonical grant_id API and must occur exactly once.
DCT-009: COVERED. Tests use real controller, host receipts, descriptor discovery, checkpoint discovery, state transitions, and stdio MCP; mocks are limited to exact file/network effect seams.
IMPLEMENTATION STATE: OPEN. This Stage 1 patch is intentionally RED at the packet commit and supplies no production implementation.
decisions_and_assumptions: |

Canonical reachable MCP execution is grant_id-only. Operation, target, evidence scope, descriptor digest, authority binding, and return point must be loaded from the latest valid checkpoint rather than selected by the MCP caller.

Existing direct-controller grant dictionaries are retained in adversarial tests only as compatibility-shaped untrusted input. A future implementation may accept that shape internally, but must use only its grant_id to load durable authority, compare the supplied copy to the canonical record, and refuse any mismatch before observation. The public MCP surface does not expose that input.

New named refusals selected by the tests are CAPABILITY_GRANT_MISMATCH, CAPABILITY_AUTHORITY_REQUIRED, and WEB_OPERATION_DISABLED. Existing CAPABILITY_DESCRIPTOR_MISMATCH and GRANT_REPLAYED remain exact.

manifest_capability_issue may accept bounded caller intent, but it must synthesize and persist the complete strict capability-request@1 object, including a nonempty durable authority receipt.

The valid local-read result must use the committed capability-result@1 schema. Refusal paths may persist no result or a strict declined/blocked/failed result, but any persisted result must have zero observed_effects.

The smallest negative-verdict controller change is to route verdicts through the existing manifest_accept entry point because that reachable tool already advertises PASS, FAIL, and INCONCLUSIVE; FAIL/INCONCLUSIVE require reason, evidence_refs, and coverage_limits and must call the existing reject transition.

Path.read_text for the exact target and socket.getaddrinfo/urllib.request.urlopen are treated as the underlying observation seams already present in production; no new production seam is assumed.
blockers_or_questions: NONE
recommended_next_action: |
Apply this diff to the exact packet commit, run python -m unittest tests.test_durable_capability_transaction tests.test_mcp_server -v, and retain the observed focused RED output as the immutable prerequisite for the Stage 2 production packet.
