schema: outsource-relay@1
work_id: durable-capability-transaction
based_on_commit: c755bba088d7903671d242eb879457fcc30eb332
status: PARTIAL
summary: |
  Stage 4 tests-only patch for the fail-closed orphaned-execution boundary. It adds two real-subprocess forced-exit cases to the existing focused module: one exits after the begun checkpoint and before target observation, and one completes exactly one real target read before exiting ahead of result persistence. A fresh process then engages pathlessly and the shared assertions require a durable unknown transaction, a blocked mission with the named unresolved marker, no synthesized result or additional observation, original-grant non-replayability, and refusal of replacement issuance/execution. No production files are changed. Tests were not run.
work_product: |
  diff --git a/tests/test_durable_capability_transaction.py b/tests/test_durable_capability_transaction.py
  --- a/tests/test_durable_capability_transaction.py
  +++ b/tests/test_durable_capability_transaction.py
  @@ -1,9 +1,12 @@
   from __future__ import annotations
   
   import json
  +import os
   import re
   import shutil
   import socket
  +import subprocess
  +import sys
   import tempfile
   import unittest
   from collections.abc import Mapping
  @@ -14,6 +17,7 @@
   from unittest.mock import patch
   
   import practical_agency.capability_operations as capability_operations
  +import practical_agency.controller as controller_module
   from practical_agency.checkpoint_store import FileCheckpointStore
   from practical_agency.controller import ControllerError, ManifestController
   from practical_agency.host_evidence import write_host_context, write_host_gate
  @@ -114,4 +118,78 @@ class _HttpResponse:
           return b"network observation"
   
   
  +_ORPHAN_WORKER = "--orphan-worker"
  +_EXIT_BEFORE_READ = 91
  +_EXIT_AFTER_READ = 92
  +
  +
  +def _run_orphan_worker(arguments: list[str]) -> None:
  +    action, runtime, workspace, journal, context_ref, gate_ref, *grant = arguments
  +    runtime_path = Path(runtime)
  +    workspace_path = Path(workspace)
  +    journal_path = Path(journal)
  +    target = (workspace_path / "evidence.txt").resolve()
  +    original_read_text = Path.read_text
  +
  +    def observed_read(path: Path, *args: object, **kwargs: object) -> str:
  +        if path.resolve() == target:
  +            descriptor = os.open(
  +                journal_path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600
  +            )
  +            try:
  +                os.write(descriptor, b"read\n")
  +                os.fsync(descriptor)
  +            finally:
  +                os.close(descriptor)
  +        return original_read_text(path, *args, **kwargs)
  +
  +    Path.read_text = observed_read
  +    controller = ManifestController(plugin_root=runtime_path)
  +    refs = {
  +        "_host_context_ref": context_ref,
  +        "_host_gate_ref": gate_ref,
  +    }
  +    try:
  +        if action.startswith("crash-"):
  +            original_execute_read = controller_module.execute_read
  +
  +            def forced_exit(*args: object, **kwargs: object) -> None:
  +                if action == "crash-after-read":
  +                    original_execute_read(*args, **kwargs)
  +                    os._exit(_EXIT_AFTER_READ)
  +                os._exit(_EXIT_BEFORE_READ)
  +
  +            controller_module.execute_read = forced_exit
  +        if action == "engage":
  +            result = controller.manifest_engage(**refs)
  +        elif action == "issue":
  +            result = controller.manifest_capability_issue(
  +                capability_id="dynamic-reader",
  +                blocking_condition="inspect the bounded evidence",
  +                admitted_operation="file.read",
  +                evidence_scope=["evidence.txt"],
  +                request={
  +                    "bounded_question_or_action": "file.read:evidence.txt",
  +                    "requested_permissions": ["repository:read"],
  +                    "requested_effects": ["evidence.txt"],
  +                    "estimated_costs": ["bounded reads"],
  +                    "timeout_or_stop_condition": "stop after one bounded observation",
  +                },
  +                **refs,
  +            )
  +        else:
  +            result = controller.manifest_capability_execute(
  +                grant_id=grant[0],
  +                operation="file.read",
  +                target="evidence.txt",
  +                evidence_refs=["evidence.txt"],
  +                evidence_payload=None,
  +                **refs,
  +            )
  +    except RuntimeError as error:
  +        print(json.dumps({"error": str(error)}), flush=True)
  +    else:
  +        print(json.dumps({"result": result}), flush=True)
  +
  +
   class DurableCapabilityTransactionRedTests(unittest.TestCase):
  @@ -323,4 +401,225 @@ class DurableCapabilityTransactionRedTests(unittest.TestCase):
               yield calls
   
       @staticmethod
  +    def _read_count(journal: Path) -> int:
  +        return (
  +            len(journal.read_text(encoding="utf-8").splitlines())
  +            if journal.exists()
  +            else 0
  +        )
  +
  +    def _orphan_process(
  +        self,
  +        runtime: Path,
  +        workspace: Path,
  +        journal: Path,
  +        action: str,
  +        turn: str,
  +        grant_id: str | None = None,
  +    ) -> subprocess.CompletedProcess[str]:
  +        operation = {
  +            "engage": "manifest_engage",
  +            "issue": "manifest_capability_issue",
  +        }.get(action, "manifest_capability_execute")
  +        refs = self._refs(workspace, runtime, operation, turn)
  +        command = [
  +            sys.executable,
  +            str(Path(__file__).resolve()),
  +            _ORPHAN_WORKER,
  +            action,
  +            str(runtime),
  +            str(workspace),
  +            str(journal),
  +            refs["_host_context_ref"],
  +            refs["_host_gate_ref"],
  +        ]
  +        if grant_id is not None:
  +            command.append(grant_id)
  +        environment = os.environ.copy()
  +        environment["PYTHONPATH"] = os.pathsep.join([str(runtime), str(ROOT)])
  +        return subprocess.run(
  +            command,
  +            cwd=runtime,
  +            env=environment,
  +            text=True,
  +            capture_output=True,
  +            check=False,
  +        )
  +
  +    @staticmethod
  +    def _worker_payload(
  +        completed: subprocess.CompletedProcess[str],
  +    ) -> dict[str, Any]:
  +        if completed.returncode != 0:
  +            raise AssertionError(
  +                f"returncode={completed.returncode} "
  +                f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
  +            )
  +        payload = json.loads(completed.stdout)
  +        if not isinstance(payload, dict):
  +            raise AssertionError(f"worker payload is not an object: {payload!r}")
  +        return payload
  +
  +    def _assert_orphan_fails_closed(
  +        self,
  +        *,
  +        crash_action: str,
  +        expected_exit: int,
  +        reads_after_crash: int,
  +    ) -> None:
  +        with tempfile.TemporaryDirectory() as temp:
  +            base = Path(temp)
  +            runtime, workspace, controller = self._setup(base)
  +            issued = self._issue(
  +                controller,
  +                workspace,
  +                runtime,
  +                turn=f"{crash_action}-issue",
  +            )
  +            grant_id = self._grant_id(issued)
  +            journal = base / "observations.log"
  +
  +            crash = self._orphan_process(
  +                runtime,
  +                workspace,
  +                journal,
  +                crash_action,
  +                f"{crash_action}-execute",
  +                grant_id,
  +            )
  +            self.assertEqual(
  +                crash.returncode,
  +                expected_exit,
  +                f"stdout={crash.stdout!r} stderr={crash.stderr!r}",
  +            )
  +            begun = discover_active_mission(workspace).manifest
  +            begun_record = self._record(begun, grant_id)
  +            self.assertEqual(begun_record.get("execution_state"), "in_progress")
  +            self.assertIsNone(begun_record.get("result"))
  +            self.assertIs(begun_record["grant"].get("used"), True)
  +            self.assertEqual(self._read_count(journal), reads_after_crash)
  +
  +            engagement = self._worker_payload(
  +                self._orphan_process(
  +                    runtime,
  +                    workspace,
  +                    journal,
  +                    "engage",
  +                    f"{crash_action}-engage",
  +                )
  +            )["result"]
  +            recovered = discover_active_mission(workspace).manifest
  +            recovered_record = self._record(recovered, grant_id)
  +            reads_after_engage = self._read_count(journal)
  +            marker = f"CAPABILITY_EFFECT_UNKNOWN:{grant_id}"
  +
  +            retry = self._worker_payload(
  +                self._orphan_process(
  +                    runtime,
  +                    workspace,
  +                    journal,
  +                    "execute",
  +                    f"{crash_action}-retry",
  +                    grant_id,
  +                )
  +            )
  +            replacement_issue = self._worker_payload(
  +                self._orphan_process(
  +                    runtime,
  +                    workspace,
  +                    journal,
  +                    "issue",
  +                    f"{crash_action}-replacement-issue",
  +                )
  +            )
  +            replacement_execute: dict[str, Any] | None = None
  +            replacement = replacement_issue.get("result")
  +            if isinstance(replacement, Mapping):
  +                replacement_execute = self._worker_payload(
  +                    self._orphan_process(
  +                        runtime,
  +                        workspace,
  +                        journal,
  +                        "execute",
  +                        f"{crash_action}-replacement-execute",
  +                        self._grant_id(replacement),
  +                    )
  +                )
  +
  +            final = discover_active_mission(workspace).manifest
  +            final_record = self._record(final, grant_id)
  +            observed = {
  +                "recovery_checkpoint_created": recovered.revision > begun.revision,
  +                "engagement_revision": engagement.get("revision"),
  +                "recovered_execution_state": recovered_record.get(
  +                    "execution_state"
  +                ),
  +                "recovered_result": recovered_record.get("result"),
  +                "recovered_status": recovered.state.get("status"),
  +                "recovered_blocker": marker
  +                in recovered.state.get("blockers", []),
  +                "recovered_unresolved": marker
  +                in recovered.integrity.get("unresolved_verdicts", []),
  +                "reads_after_engage": reads_after_engage,
  +                "execution_state": final_record.get("execution_state"),
  +                "grant_used": final_record["grant"].get("used"),
  +                "result": final_record.get("result"),
  +                "mission_status": final.state.get("status"),
  +                "engagement_status": engagement.get("mission_status"),
  +                "blocker": marker in final.state.get("blockers", []),
  +                "unresolved": marker
  +                in final.integrity.get("unresolved_verdicts", []),
  +                "result_artifact": f"capability-result:{grant_id}"
  +                in final.continuity.get("durable_artifacts", []),
  +                "result_decision": any(
  +                    isinstance(item, Mapping)
  +                    and item.get("kind") == "capability-result"
  +                    and item.get("grant_id") == grant_id
  +                    for item in final.continuity.get("decisions", [])
  +                ),
  +                "original_retry_refused": "error" in retry
  +                and "result" not in retry,
  +                "replacement_issue_error": replacement_issue.get("error"),
  +                "replacement_execute": (
  +                    "not-issued"
  +                    if replacement_execute is None
  +                    else replacement_execute.get("error")
  +                    or "executed"
  +                ),
  +                "observation_count": self._read_count(journal),
  +                "grant_ids": [
  +                    item.get("grant_id")
  +                    for item in final.capabilities.get("invoked", [])
  +                    if isinstance(item, Mapping)
  +                ],
  +            }
  +            self.assertEqual(
  +                observed,
  +                {
  +                    "recovery_checkpoint_created": True,
  +                    "engagement_revision": recovered.revision,
  +                    "recovered_execution_state": "unknown",
  +                    "recovered_result": None,
  +                    "recovered_status": "blocked",
  +                    "recovered_blocker": True,
  +                    "recovered_unresolved": True,
  +                    "reads_after_engage": reads_after_crash,
  +                    "execution_state": "unknown",
  +                    "grant_used": True,
  +                    "result": None,
  +                    "mission_status": "blocked",
  +                    "engagement_status": "blocked",
  +                    "blocker": True,
  +                    "unresolved": True,
  +                    "result_artifact": False,
  +                    "result_decision": False,
  +                    "original_retry_refused": True,
  +                    "replacement_issue_error": marker,
  +                    "replacement_execute": "not-issued",
  +                    "observation_count": reads_after_crash,
  +                    "grant_ids": [grant_id],
  +                },
  +            )
  +
  +    @staticmethod
       def _mcp_call(
  @@ -558,4 +857,18 @@ class DurableCapabilityTransactionRedTests(unittest.TestCase):
               self.assertEqual(replayed_result, first_result)
               self.assertEqual(str(refusal), "CAPABILITY_RESULT_REPLAY")
   
  +    def test_orphaned_execution_before_target_read_fails_closed(self) -> None:
  +        self._assert_orphan_fails_closed(
  +            crash_action="crash-before-read",
  +            expected_exit=_EXIT_BEFORE_READ,
  +            reads_after_crash=0,
  +        )
  +
  +    def test_orphaned_execution_after_one_target_read_fails_closed(self) -> None:
  +        self._assert_orphan_fails_closed(
  +            crash_action="crash-after-read",
  +            expected_exit=_EXIT_AFTER_READ,
  +            reads_after_crash=1,
  +        )
  +
       def test_web_operation_refuses_before_retrieval_resolution_or_network(self) -> None:
  @@ -869,4 +1182,7 @@
   
   
   if __name__ == "__main__":
  -    unittest.main()
  +    if sys.argv[1:2] == [_ORPHAN_WORKER]:
  +        _run_orphan_worker(sys.argv[2:])
  +    else:
  +        unittest.main()
evidence: |
  TEST-TO-DEFECT MATRIX — source-derived expectations only; tests were not run.

  1. test_orphaned_execution_before_target_read_fails_closed
     Forced boundary: the child enters the real ManifestController.manifest_capability_execute path, lets the real FileCheckpointStore persist begin_capability_execution, then the imported execute_read seam calls os._exit(91) before the target Path.read_text.
     Observation oracle: the fsynced journal must contain zero entries at process exit.
     Defect caught: a zero-effect orphan must not remain indistinguishable and active.
     Expected RED at c755bba088d7903671d242eb879457fcc30eb332: replacement engagement is expected to return the unchanged in_progress/active checkpoint with no CAPABILITY_EFFECT_UNKNOWN marker; replacement issuance is expected to succeed, its execution is expected to add one read, and a second grant_id is expected to remain durable.

  2. test_orphaned_execution_after_one_target_read_fails_closed
     Forced boundary: the child enters the same real controller/checkpoint path; the journal wrapper records and fsyncs one target read, delegates to the real Path.read_text, and the execute_read wrapper calls os._exit(92) before control returns to result construction/persistence.
     Observation oracle: the journal must contain exactly one entry at process exit.
     Defect caught: a completed-but-unrecorded observation must be classified unknown without replay.
     Expected RED at the packet source: engagement is expected to leave the transaction in_progress/active without the marker; replacement issuance/execution is expected to add a second read and a second durable grant.

  3. Shared durable recovery/refusal assertions in _assert_orphan_fails_closed
     - The crash checkpoint itself must prove execution_state=in_progress, grant.used=true, result=null, and the case-specific zero/one read precondition.
     - A distinct subprocess invokes manifest_engage with host context/gate references only; no mission id, checkpoint path, or grant is passed to engagement.
     - Pathless engagement must create a newer discoverable checkpoint whose original record is execution_state=unknown and result=null.
     - Both the engagement snapshot and final snapshot must be blocked and contain CAPABILITY_EFFECT_UNKNOWN:<grant_id> in state.blockers and integrity.unresolved_verdicts.
     - No capability-result artifact or capability-result decision may be synthesized for the orphan.
     - Re-execution of the original grant must refuse without another target read.
     - A canonical replacement issue is attempted. If the defect allows issuance, its grant is immediately executed in another subprocess so the execute guard and read oracle are exercised. The required end state is issue refusal with the unknown marker, no replacement execution, one original grant only, and an unchanged zero/one observation count.
     Expected packet controls that should remain GREEN: the begun checkpoint is durable, the original grant is already used, the original result is null, and direct same-grant retry refuses. The RED differences are recovery classification, blocking/marker persistence, replacement refusal, and replay-free observation counts.
requirements: |
  STAGE 4 COVERAGE
  - Forced exit before observation: COVERED by exit 91 and a zero-entry fsynced target-read journal.
  - Forced exit after exactly one observation: COVERED by exit 92 after the real read and a one-entry journal.
  - Real subprocesses: COVERED; crash, engagement, retry, replacement issue, and reachable replacement execute each run through a fresh Python subprocess.
  - Real checkpoint store/state machine/controller: COVERED through the existing canonical _setup/_issue path, real begin checkpoint, discover_active_mission reloads, and real controller calls. No checkpoint or controller mock is introduced.
  - Pathless replacement-process engagement: COVERED; the engagement worker calls manifest_engage only with validated host context/gate references.
  - Durable execution_state=unknown: ASSERTED both immediately after engagement and after all refusal attempts.
  - Blocked mission and CAPABILITY_EFFECT_UNKNOWN:<grant_id>: ASSERTED in both blockers and unresolved verdicts, immediately and finally.
  - No fabricated result: ASSERTED by result=null plus absence of the result artifact and decision.
  - No additional observation: ASSERTED after engagement and after every retry/replacement attempt for both zero-read and one-read cases.
  - Original-grant non-replayability: ASSERTED by durable used=true and an error-only retry response.
  - Replacement issue/execute refusal: ASSERTED by exact marker refusal on issue; any incorrectly issued replacement is immediately executed and must not observe or complete.
  - Scope discipline: the diff changes only tests/test_durable_capability_transaction.py and adds no MCP-schema, discovery, web, proof-integration, principal, or production behavior.

  IMPLEMENTATION STATE
  - Expected RED at the packet commit. Stage 4 supplies tests only; the unknown/reconciliation transition and controller guards remain for the next production stage.
  - No repository test or runtime probe was executed while preparing this relay.
decisions_and_assumptions: |
  - The existing focused test module doubles as the subprocess worker under --orphan-worker, avoiding a second helper file while preserving normal unittest execution.
  - The observation journal is outside the governed workspace. It records only reads of workspace/evidence.txt, fsyncs before delegating, and still performs the real target read; it is an observation seam, not a fabricated result.
  - CAPABILITY_EFFECT_UNKNOWN:<original grant_id> is treated as the durable blocker/unresolved marker and the replacement-issue refusal code, matching the Stage 3 recovery contract.
  - The original-grant retry assertion intentionally requires refusal without prescribing a new error string; its durable used/unknown state and zero additional reads carry the security property.
  - Replacement execute is attempted only when the defective implementation first permits replacement issuance. The required fixed behavior remains deny-at-issue; the conditional execute makes a partial issue-only repair visibly unsafe rather than silently skipping the reachable replay.
  - Child PYTHONPATH selects the copied exact runtime first and the packet repository second for tests.helpers.
  - No unavoidable test seam question remains.
blockers_or_questions: NONE
recommended_next_action: Establish the Stage 4 RED baseline by applying this tests-only diff unchanged and running python -m unittest tests.test_durable_capability_transaction -v before preparing the Stage 5 production patch.
