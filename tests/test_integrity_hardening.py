from __future__ import annotations

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping

from practical_agency.capability_discovery import CapabilityDescriptor, Persistence
from practical_agency.checkpoint_store import (
    CheckpointError,
    CheckpointReceipt,
    FileCheckpointStore,
    reconcile_observations,
)
from practical_agency.coordinator import (
    CoordinationError,
    apply_capability_result,
    coordinate_once,
    dispatch_once,
)
from practical_agency.manifest_model import MissionManifest
from practical_agency.state_machine import MissionEvent, TransitionError, apply_event
from practical_agency.validation import validate_manifest_dict
from practical_agency.watch_commission import (
    CommissionIntegrationError,
    accept_external_commission,
    disable_commissions_for_revocation,
    handle_crossing_event,
    prepare_disabled,
)
from tests.helpers import clone_payload


class ExecutionAdapter:
    def __init__(self, result: Mapping[str, Any]) -> None:
        self.result = dict(result)
        self.calls: list[dict[str, Any]] = []

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(copy.deepcopy(request))
        return copy.deepcopy(self.result)


class WatchAdapter:
    def __init__(self) -> None:
        self.prepare_calls = 0
        self.disabled: list[str] = []

    def prepare_disabled(self, commission: Mapping[str, Any]) -> Mapping[str, Any]:
        self.prepare_calls += 1
        return {
            "mechanism_ref": "fixture://watch/1",
            "substrate_kind": "fixture",
            "substrate": "isolated-fixture-adapter",
            "persistence_receipt_ref": "external-fixture://persistence/1",
            "block_evidence": {
                "detail": "kill switch has not yet been exercised",
                "observed_at": "2026-08-07T12:00:00Z",
                "receipt_ref": "external-fixture://block/1",
            },
            "coverage_limits": [
                "isolated fixture only",
                "production coverage unestablished",
            ],
        }

    def exercise_kill_switch(self, mechanism_ref: str) -> Mapping[str, Any]:
        return {
            "mechanism_ref": mechanism_ref,
            "exercise_receipt_ref": "external-fixture://kill/1",
            "observed_stopped": True,
        }

    def enable_for_proof(self, mechanism_ref: str, authority_ref: str) -> Mapping[str, Any]:
        return {
            "mechanism_ref": mechanism_ref,
            "authority_ref": authority_ref,
            "enabled": True,
        }

    def perform_safe_crossing(
        self, mechanism_ref: str, proof_spec: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        return {"mechanism_ref": mechanism_ref, "alert_received": True}

    def disable(self, mechanism_ref: str) -> Mapping[str, Any]:
        self.disabled.append(mechanism_ref)
        return {
            "mechanism_ref": mechanism_ref,
            "disabled": True,
            "observed_at": "2026-08-07T14:00:00Z",
            "disable_receipt_ref": "external-fixture://disable/1",
        }


def active_manifest() -> MissionManifest:
    payload = clone_payload()
    payload["revision"] = 2
    payload["state"]["status"] = "active"
    payload["continuity"]["prior_checkpoint"] = "checkpoint:1"
    return MissionManifest.from_dict(payload)


def capability(*permissions: str) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability_id="fixture-reader",
        kind="skill",
        source_ref="fixture://skill",
        source_sha256="a" * 64,
        description="Use for one bounded fixture question.",
        input_contract=None,
        output_contract=None,
        authority_required=permissions,
        persistence=Persistence.SESSION,
        independence="actor",
        availability="available",
        degradation_reason=None,
    )


def capability_result(decision: Any, **overrides: Any) -> dict[str, Any]:
    assert decision.request is not None
    assert decision.return_point is not None
    result: dict[str, Any] = {
        "schema": "capability-result@1",
        "request_id": decision.request["request_id"],
        "status": "completed",
        "verdict": None,
        "artifact_refs": [],
        "observed_effects": [],
        "returned_control_point": decision.return_point.to_dict(),
        "coverage_limits": [],
    }
    result.update(overrides)
    return result


def declared_commission() -> dict[str, Any]:
    return {
        "schema": "watch-commission@1",
        "commission_id": "wc-1",
        "subject": {"ref": "service:example", "revision": "rev-1"},
        "bound": {
            "expression": "free_space_percent < 15",
            "units": "percent",
            "direction": "below",
            "threshold": 15,
        },
        "probe": {
            "mechanism": "external metric query",
            "cadence_or_event": "every 5 minutes",
            "failure_modes": ["timeout"],
        },
        "destination": {
            "ref": "recipient:test",
            "reachable": False,
            "reachability_receipt_ref": None,
        },
        "external_observer": {
            "substrate_kind": None,
            "substrate": None,
            "mechanism_ref": None,
            "persistence_receipt_ref": None,
            "persistent_outside_session": False,
            "enabled": False,
        },
        "kill_switch": {
            "procedure_ref": "fixture://disable",
            "exercised": False,
            "exercise_receipt_ref": None,
        },
        "proof": {
            "authorized_by": None,
            "authorization_ref": None,
            "safe_crossing": None,
            "production_path": False,
            "bound_crossed": False,
            "alert_received": False,
            "received_at": None,
            "alert_receipt_ref": None,
        },
        "failure": {
            "kind": None,
            "detail": None,
            "observed_at": None,
            "receipt_ref": None,
        },
        "block_evidence": {
            "detail": None,
            "observed_at": None,
            "receipt_ref": None,
        },
        "state": "DECLARED",
        "block_reason": None,
        "reprove_after": None,
        "handoff": {"on_crossing": ["triage", "decision-ledger"]},
        "coverage_limits": ["isolated fixture; no production provider claimed"],
    }


def proven_commission() -> dict[str, Any]:
    record = declared_commission()
    record["destination"] = {
        "ref": "recipient:test",
        "reachable": True,
        "reachability_receipt_ref": "external-fixture://destination/1",
    }
    record["external_observer"] = {
        "substrate_kind": "fixture",
        "substrate": "isolated-fixture-adapter",
        "mechanism_ref": "fixture://watch/1",
        "persistence_receipt_ref": "external-fixture://persistence/1",
        "persistent_outside_session": True,
        "enabled": True,
    }
    record["kill_switch"] = {
        "procedure_ref": "fixture://disable",
        "exercised": True,
        "exercise_receipt_ref": "external-fixture://kill/1",
    }
    record["proof"] = {
        "authorized_by": "operator:test",
        "authorization_ref": "external-fixture://authority/1",
        "safe_crossing": "reversible fixture threshold override",
        "production_path": True,
        "bound_crossed": True,
        "alert_received": True,
        "received_at": "2026-08-07T12:05:00Z",
        "alert_receipt_ref": "external-fixture://alert/1",
    }
    record["state"] = "PROVEN"
    record["reprove_after"] = "2026-09-07T12:05:00Z"
    return record


def fixture_watch_verifier(record: Mapping[str, Any]) -> list[str]:
    if record.get("schema") != "watch-commission@1":
        return ["INVALID_SCHEMA"]
    if record.get("state") == "DECLARED":
        return []
    if record.get("state") == "BLOCKED" and record.get("block_reason") == "KILL_SWITCH_UNPROVEN":
        return []
    if record.get("state") in {"INERT", "PROVEN"}:
        return []
    return ["FIXTURE_REJECTED"]


class IntegrityHardeningTests(unittest.TestCase):
    def test_manifest_rejects_runtime_dangerous_type_mismatches(self) -> None:
        cases = [
            (("authority", "permissions"), [{}]),
            (("truth", "subject_refs"), [1]),
            (("continuity", "durable_artifacts"), [{}]),
            (("integrity", "required_gates"), [False]),
            (("continuity", "decisions"), ["not-an-object"]),
        ]
        for path, value in cases:
            payload = clone_payload()
            payload[path[0]][path[1]] = value
            errors = validate_manifest_dict(payload)
            self.assertTrue(
                any(
                    error.startswith(("INVALID_STRING_LIST:", "INVALID_OBJECT_LIST:"))
                    for error in errors
                ),
                (path, errors),
            )

        payload = clone_payload()
        payload["continuity"]["prior_checkpoint"] = []
        self.assertTrue(
            any(
                error.startswith("INVALID_OPTIONAL_STRING:")
                for error in validate_manifest_dict(payload)
            )
        )

    def test_checkpoint_receipt_refuses_string_coercion(self) -> None:
        base = {
            "schema": "checkpoint-receipt@1",
            "mission_id": "mission-001",
            "revision": 1,
            "path": "/tmp/checkpoint.json",
            "sha256": "0" * 64,
            "created_at": "2026-08-07T12:00:00Z",
        }
        for field, value in (
            ("mission_id", ["mission-001"]),
            ("path", ["checkpoint.json"]),
            ("sha256", ["0" * 64]),
            ("created_at", ["2026-08-07T12:00:00Z"]),
        ):
            payload = dict(base)
            payload[field] = value
            with self.assertRaisesRegex(CheckpointError, "INVALID_CHECKPOINT_RECEIPT"):
                CheckpointReceipt.from_dict(payload)

    def test_checkpoint_symlink_cannot_escape_store_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = FileCheckpointStore(root / "store")
            manifest = MissionManifest.from_dict(clone_payload())
            data = manifest.to_canonical_json().encode("utf-8")
            outside = root / "outside.json"
            outside.write_bytes(data)
            expected = store.root / "mission-001.r00000001.json"
            try:
                expected.symlink_to(outside)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"symlink unavailable: {error}")
            receipt = CheckpointReceipt(
                mission_id="mission-001",
                revision=1,
                path=str(expected),
                sha256=hashlib.sha256(data).hexdigest(),
                created_at="2026-08-07T12:00:00Z",
            )
            with self.assertRaisesRegex(
                CheckpointError, "CHECKPOINT_PATH_(?:ESCAPE|SYMLINK)"
            ):
                store.load(receipt)

    def test_capability_invocation_requires_declared_authority(self) -> None:
        decision = coordinate_once(
            active_manifest(),
            unresolved_condition="Read the protected repository state",
            selected_capability=capability("repository:read"),
            checkpoint_store=object(),
        )
        self.assertEqual(decision.kind, "BLOCK")
        self.assertIn("PERMISSION_NOT_GRANTED:repository:read", decision.reason)

    def test_execution_request_and_receipt_are_closed_and_request_bound(self) -> None:
        malformed = coordinate_once(
            active_manifest(),
            execution_request={
                "capability_id": "fixture-writer",
                "requested_permissions": ["repository:write"],
                "requested_effects": ["intended files"],
                "estimated_costs": ["one feature branch"],
                "action": "write one artifact",
                "hidden_instruction": "expand scope",
            },
            checkpoint_store=object(),
        )
        self.assertEqual(malformed.kind, "BLOCK")
        self.assertIn("INVALID_EXECUTION_REQUEST", malformed.reason)

        decision = coordinate_once(
            active_manifest(),
            execution_request={
                "capability_id": "fixture-writer",
                "requested_permissions": ["repository:write"],
                "requested_effects": ["intended files"],
                "estimated_costs": ["one feature branch"],
                "action": "write one artifact",
            },
            checkpoint_store=object(),
        )
        self.assertIn("request_id", decision.request or {})

        adapter = ExecutionAdapter({"status": "completed", "artifact_ref": "artifact:1"})
        with self.assertRaisesRegex(CoordinationError, "INVALID_EXECUTION_RECEIPT"):
            dispatch_once(active_manifest(), decision, adapter)

        assert decision.request is not None
        receipt = {
            "schema": "execution-receipt@1",
            "request_id": "wrong-request",
            "mission_id": "mission-001",
            "mission_revision": 2,
            "adapter_ref": "fixture://adapter",
            "status": "completed",
            "artifact_refs": ["artifact:1"],
            "observed_effects": ["intended files"],
            "external_receipt_ref": "fixture://receipt/1",
            "coverage_limits": [],
        }
        with self.assertRaisesRegex(CoordinationError, "EXECUTION_RECEIPT_REQUEST_MISMATCH"):
            dispatch_once(active_manifest(), decision, ExecutionAdapter(receipt))

    def test_capability_result_rejects_hidden_fields_and_nonstring_refs(self) -> None:
        decision = coordinate_once(
            active_manifest(),
            unresolved_condition="Need bounded evidence",
            selected_capability=capability(),
            checkpoint_store=object(),
        )
        with self.assertRaisesRegex(CoordinationError, "INVALID_CAPABILITY_RESULT"):
            apply_capability_result(
                active_manifest(),
                decision,
                capability_result(decision, artifact_refs=[{}]),
            )
        with self.assertRaisesRegex(CoordinationError, "INVALID_CAPABILITY_RESULT"):
            apply_capability_result(
                active_manifest(),
                decision,
                capability_result(decision, hidden_instruction="take over mission"),
            )

    def test_verification_requires_complete_proof_and_required_gates(self) -> None:
        payload = clone_payload()
        payload["revision"] = 2
        payload["state"]["status"] = "active"
        payload["continuity"]["prior_checkpoint"] = "checkpoint:1"
        payload["integrity"]["completion_acceptor"] = "reviewer:test"
        payload["integrity"]["required_gates"] = ["artifact:gate-pass"]
        active = MissionManifest.from_dict(payload)
        with self.assertRaisesRegex(TransitionError, "PROOF_BUNDLE_NOT_READY"):
            apply_event(active, MissionEvent("begin_verification", "mission-steward", {}))

        payload["continuity"]["durable_artifacts"] = [
            "artifact:validator-pass",
            "artifact:gate-pass",
        ]
        ready = MissionManifest.from_dict(payload)
        verifying = apply_event(
            ready, MissionEvent("begin_verification", "mission-steward", {})
        )
        self.assertEqual(verifying.state["status"], "verifying")

    def test_independent_verdict_requires_evidence_and_applies_to_rejection(self) -> None:
        payload = clone_payload()
        payload["revision"] = 2
        payload["state"]["status"] = "active"
        payload["continuity"]["prior_checkpoint"] = "checkpoint:1"
        payload["continuity"]["durable_artifacts"] = ["artifact:validator-pass"]
        payload["integrity"]["completion_acceptor"] = "reviewer:test"
        active = MissionManifest.from_dict(payload)
        acted = apply_event(
            active,
            MissionEvent(
                "record_action",
                "worker:test",
                {"action_ref": "artifact:material-work"},
            ),
        )
        verifying = apply_event(
            acted, MissionEvent("begin_verification", "mission-steward", {})
        )

        with self.assertRaisesRegex(TransitionError, "ACCEPTANCE_EVIDENCE_REQUIRED"):
            apply_event(
                verifying,
                MissionEvent("accept", "reviewer:test", {"verdict": "PASS"}),
            )
        with self.assertRaisesRegex(TransitionError, "INDEPENDENT_ACCEPTANCE_REQUIRED"):
            apply_event(
                verifying,
                MissionEvent(
                    "reject",
                    "worker:test",
                    {
                        "verdict": "FAIL",
                        "reason": "wrong",
                        "evidence_refs": ["artifact:review"],
                        "coverage_limits": [],
                    },
                ),
            )

        rejected = apply_event(
            verifying,
            MissionEvent(
                "reject",
                "reviewer:test",
                {
                    "verdict": "FAIL",
                    "reason": "wrong",
                    "evidence_refs": ["artifact:review"],
                    "coverage_limits": ["fixture only"],
                },
            ),
        )
        decision = rejected.continuity["decisions"][-1]
        self.assertEqual(decision["evidence_refs"], ["artifact:review"])
        self.assertEqual(decision["coverage_limits"], ["fixture only"])

    def test_reconciliation_reopens_and_invalidates_proof_until_reobserved(self) -> None:
        from practical_agency.checkpoint_store import apply_reconciliation_findings

        payload = clone_payload()
        payload["revision"] = 5
        payload["state"]["status"] = "completed"
        payload["continuity"]["prior_checkpoint"] = "checkpoint:4"
        payload["continuity"]["durable_artifacts"] = ["artifact:validator-pass"]
        payload["truth"]["verified_facts"] = [
            {"subject_ref": "artifact:canonical", "value": "hash-a"}
        ]
        payload["integrity"]["completion_acceptor"] = "reviewer:test"
        completed = MissionManifest.from_dict(payload)
        findings = reconcile_observations(
            completed, {"artifact:canonical": "hash-b"}
        )
        reopened = apply_reconciliation_findings(completed, findings)
        self.assertEqual(reopened.state["status"], "blocked")
        self.assertNotIn(
            "artifact:validator-pass", reopened.continuity["durable_artifacts"]
        )
        self.assertTrue(reopened.integrity["unresolved_verdicts"])

        blocker = reopened.state["blockers"][0]
        with self.assertRaisesRegex(
            TransitionError, "RECONCILIATION_OBSERVATION_REQUIRED"
        ):
            apply_event(
                reopened,
                MissionEvent("unblock", "mission-steward", {"reason": blocker}),
            )

        repaired = apply_event(
            reopened,
            MissionEvent(
                "record_observation",
                "observer:test",
                {
                    "artifact_ref": "artifact:validator-pass",
                    "fact": {
                        "subject_ref": "artifact:canonical",
                        "value": "hash-b",
                    },
                },
            ),
        )
        self.assertEqual(repaired.state["status"], "active")
        self.assertEqual(repaired.integrity["unresolved_verdicts"], [])
        self.assertIn(
            "artifact:validator-pass", repaired.continuity["durable_artifacts"]
        )

    def test_watch_prepare_refuses_unverified_contract_before_adapter_dispatch(self) -> None:
        adapter = WatchAdapter()
        result = prepare_disabled(declared_commission(), adapter, None)
        self.assertEqual(result.status, "UNVERIFIED_EXTERNAL_CONTRACT")
        self.assertEqual(adapter.prepare_calls, 0)

        rejected = prepare_disabled(
            declared_commission(), adapter, lambda record: ["rejected"]
        )
        self.assertEqual(rejected.status, "REJECTED_EXTERNAL_CONTRACT")
        self.assertEqual(adapter.prepare_calls, 0)

        prepared = prepare_disabled(
            declared_commission(), adapter, fixture_watch_verifier
        )
        self.assertEqual(prepared.status, "VERIFIED_EXTERNAL_CONTRACT")
        self.assertEqual(prepared.record["state"], "BLOCKED")
        self.assertEqual(adapter.prepare_calls, 1)

    def test_crossing_cannot_reactivate_revoked_or_inactive_commission(self) -> None:
        payload = clone_payload()
        payload["revision"] = 5
        payload["state"]["status"] = "completed"
        payload["continuity"]["prior_checkpoint"] = "checkpoint:4"
        payload["integrity"]["completion_acceptor"] = "reviewer:test"
        inert = proven_commission()
        inert["state"] = "INERT"
        inert["external_observer"]["enabled"] = False
        payload["continuity"]["watch_commissions"] = [inert]
        with self.assertRaisesRegex(CommissionIntegrationError, "COMMISSION_NOT_ACTIVE"):
            handle_crossing_event(
                MissionManifest.from_dict(payload),
                {
                    "commission_id": "wc-1",
                    "event_ref": "external-event://1",
                    "observed_at": "2026-08-07T13:00:00Z",
                },
            )

        payload["authority"]["revoked"] = True
        payload["authority"]["revocation_reason"] = "stop"
        payload["state"]["status"] = "cancelled"
        payload["continuity"]["watch_commissions"] = [proven_commission()]
        with self.assertRaisesRegex(CommissionIntegrationError, "AUTHORITY_REVOKED"):
            handle_crossing_event(
                MissionManifest.from_dict(payload),
                {
                    "commission_id": "wc-1",
                    "event_ref": "external-event://1",
                    "observed_at": "2026-08-07T13:00:00Z",
                },
            )

    def test_revocation_disable_requires_revocation_and_updates_current_state(self) -> None:
        payload = clone_payload()
        payload["continuity"]["watch_commissions"] = [proven_commission()]
        adapter = WatchAdapter()
        with self.assertRaisesRegex(CommissionIntegrationError, "AUTHORITY_NOT_REVOKED"):
            disable_commissions_for_revocation(
                MissionManifest.from_dict(payload), adapter
            )
        self.assertEqual(adapter.disabled, [])

        payload["authority"]["revoked"] = True
        payload["authority"]["revocation_reason"] = "stop"
        payload["state"]["status"] = "cancelled"
        revoked = MissionManifest.from_dict(payload)
        updated, receipts = disable_commissions_for_revocation(revoked, adapter)
        retained = updated.continuity["watch_commissions"][0]
        self.assertEqual(retained["state"], "INERT")
        self.assertFalse(retained["external_observer"]["enabled"])
        self.assertTrue(retained["proof"]["alert_received"])
        self.assertEqual(receipts[0]["disable_receipt_ref"], "external-fixture://disable/1")


if __name__ == "__main__":
    unittest.main()
