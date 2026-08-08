from __future__ import annotations

import unittest
from dataclasses import replace

from practical_agency.manifest_model import MissionManifest
from practical_agency.state_machine import (
    MissionEvent,
    TransitionError,
    apply_event,
    apply_event_data,
)
from tests.helpers import clone_payload


class StateMachineTests(unittest.TestCase):
    def draft(self) -> MissionManifest:
        return MissionManifest.from_dict(clone_payload())

    def active(self) -> MissionManifest:
        return apply_event_data(
            self.draft(),
            "approve", "operator:test", {"checkpoint_ref": "checkpoint:1"},
        )

    def observed(self, manifest: MissionManifest) -> MissionManifest:
        return apply_event_data(
            manifest,
            "record_observation", "observer:test", {
                    "artifact_ref": "artifact:validator-pass",
                    "fact": {"subject_ref": "repo:example@rev-1", "value": "validated"},
                },
        )

    def verdict(self, verdict: str, **extra: object) -> dict[str, object]:
        return {
            "verdict": verdict,
            "evidence_refs": ["artifact:independent-review"],
            "coverage_limits": ["fixture review only"],
            **extra,
        }

    def test_approve_increments_revision_and_preserves_instruction(self) -> None:
        before = self.draft()
        after = self.active()
        self.assertEqual(after.revision, 2)
        self.assertEqual(after.state["status"], "active")
        self.assertEqual(after.authority["instruction"], before.authority["instruction"])

    def test_invalid_transition_is_closed(self) -> None:
        with self.assertRaisesRegex(TransitionError, "INVALID_TRANSITION"):
            apply_event_data(self.draft(), "accept", "reviewer:test", {"verdict": "PASS"})

    def test_revoked_mission_refuses_action_record(self) -> None:
        revoked = apply_event_data(self.active(), "revoke", "operator:test", {"reason": "stop"})
        with self.assertRaisesRegex(TransitionError, "AUTHORITY_REVOKED"):
            apply_event_data(revoked, "record_action", "mission-steward", {"action_ref": "artifact:1"})

    def test_amendments_append_without_replacing_instruction(self) -> None:
        original = self.draft()
        changed = apply_event_data(
            original,
            "amend_authority", "operator:test", {"amendment": "Allow repository:read", "permissions_add": ["repository:read"]},
        )
        self.assertEqual(changed.authority["instruction"], original.authority["instruction"])
        self.assertEqual(changed.authority["amendments"], ["Allow repository:read"])
        self.assertIn("repository:read", changed.authority["permissions"])

    def test_self_acceptance_is_rejected_and_independent_acceptance_succeeds(self) -> None:
        payload = clone_payload()
        payload["integrity"]["completion_acceptor"] = "reviewer:test"
        active = apply_event_data(
            MissionManifest.from_dict(payload),
            "approve", "operator:test", {"checkpoint_ref": "checkpoint:1"},
        )
        observed = self.observed(active)
        verifying = apply_event_data(observed, "begin_verification", "mission-steward", {})
        with self.assertRaisesRegex(TransitionError, "INDEPENDENT_ACCEPTANCE_REQUIRED"):
            apply_event_data(
                verifying,
                "accept", "mission-steward", self.verdict("PASS"),
            )
        completed = apply_event_data(
            verifying,
            "accept", "reviewer:test", self.verdict("PASS"),
        )
        self.assertEqual(completed.state["status"], "completed")
        self.assertEqual(
            completed.continuity["decisions"][-1]["evidence_refs"],
            ["artifact:independent-review"],
        )

    def test_begin_verification_requires_all_completion_proof_refs(self) -> None:
        payload = clone_payload()
        payload["integrity"]["completion_acceptor"] = "reviewer:test"
        active = apply_event_data(
            MissionManifest.from_dict(payload),
            "approve", "operator:test", {"checkpoint_ref": "checkpoint:1"},
        )
        with self.assertRaisesRegex(TransitionError, "PROOF_BUNDLE_NOT_READY"):
            apply_event_data(active, "begin_verification", "mission-steward", {})

    def test_reject_cannot_be_rewritten_as_completion(self) -> None:
        payload = clone_payload()
        payload["integrity"]["completion_acceptor"] = "reviewer:test"
        active = apply_event_data(
            MissionManifest.from_dict(payload),
            "approve", "operator:test", {"checkpoint_ref": "checkpoint:1"},
        )
        verifying = apply_event_data(
            self.observed(active),
            "begin_verification", "mission-steward", {},
        )
        rejected = apply_event_data(
            verifying,
            "reject", "reviewer:test", self.verdict("FAIL", reason="wrong"),
        )
        self.assertNotEqual(rejected.state["status"], "completed")
        self.assertIn("FAIL:wrong", rejected.integrity["unresolved_verdicts"])
        self.assertEqual(
            rejected.continuity["decisions"][-1]["coverage_limits"],
            ["fixture review only"],
        )


    def test_event_envelope_is_revision_bound_and_schema_complete(self) -> None:
        draft = self.draft()
        event = MissionEvent.for_manifest(
            draft,
            "approve",
            "operator:test",
            {"checkpoint_ref": "checkpoint:1"},
            event_id="event-envelope-1",
            observed_at="2026-08-08T07:00:00Z",
        )
        self.assertEqual(
            set(event.to_dict()),
            {
                "schema",
                "event_id",
                "mission_id",
                "expected_revision",
                "kind",
                "actor_ref",
                "data",
                "observed_at",
            },
        )
        self.assertEqual(event.mission_id, draft.mission_id)
        self.assertEqual(event.expected_revision, draft.revision)

    def test_cross_mission_event_is_refused_before_mutation(self) -> None:
        draft = self.draft()
        event = MissionEvent.for_manifest(
            draft,
            "approve",
            "operator:test",
            {"checkpoint_ref": "checkpoint:1"},
            event_id="event-cross-mission",
        )
        with self.assertRaisesRegex(TransitionError, "EVENT_MISSION_MISMATCH"):
            apply_event(draft, replace(event, mission_id="other-mission"))
        self.assertEqual(draft.state["status"], "draft")

    def test_stale_event_is_refused_before_mutation(self) -> None:
        draft = self.draft()
        event = MissionEvent.for_manifest(
            draft,
            "approve",
            "operator:test",
            {"checkpoint_ref": "checkpoint:1"},
            event_id="event-stale",
        )
        with self.assertRaisesRegex(TransitionError, "EVENT_REVISION_MISMATCH"):
            apply_event(draft, replace(event, expected_revision=draft.revision + 1))

    def test_event_id_replay_is_refused(self) -> None:
        draft = self.draft()
        event = MissionEvent.for_manifest(
            draft,
            "approve",
            "operator:test",
            {"checkpoint_ref": "checkpoint:1"},
            event_id="event-replay",
        )
        active = apply_event(draft, event)
        replay = replace(
            event,
            expected_revision=active.revision,
            kind="record_action",
            actor_ref="mission-steward",
            data={"action_ref": "artifact:replay"},
        )
        with self.assertRaisesRegex(TransitionError, "EVENT_REPLAY"):
            apply_event(active, replay)

    def execution_request(self, revision: int) -> dict[str, object]:
        return {
            "schema": "execution-request@1",
            "request_id": f"mission-001:r{revision}:fixture:execution:f0",
            "mission_id": "mission-001",
            "mission_revision": revision,
            "capability_id": "fixture",
            "requested_permissions": ["repository:write"],
            "requested_effects": ["intended files"],
            "estimated_costs": ["one feature branch"],
            "action": "write one artifact",
        }

    def execution_receipt(
        self, request: dict[str, object]
    ) -> dict[str, object]:
        return {
            "schema": "execution-receipt@1",
            "request_id": request["request_id"],
            "mission_id": request["mission_id"],
            "mission_revision": request["mission_revision"],
            "adapter_ref": "fixture://adapter",
            "status": "completed",
            "artifact_refs": ["artifact:receipt-proof"],
            "observed_effects": [{"kind": "fixture"}],
            "external_receipt_ref": "fixture://receipt/one",
            "coverage_limits": ["fixture only"],
        }

    def test_execution_receipt_is_revision_bound_and_persisted(self) -> None:
        active = self.active()
        request = self.execution_request(active.revision)
        receipt = self.execution_receipt(request)
        updated = apply_event_data(
            active,
            "record_execution_receipt",
            "mission-steward",
            {"receipt": receipt, "request": request},
        )
        stored = updated.continuity["execution_receipts"][-1]
        self.assertEqual(stored["request"], request)
        self.assertEqual(stored["recorded_at_revision"], updated.revision)
        self.assertIn("artifact:receipt-proof", updated.continuity["durable_artifacts"])

    def test_execution_receipt_request_mismatch_is_refused(self) -> None:
        active = self.active()
        request = self.execution_request(active.revision)
        receipt = self.execution_receipt(request)
        receipt["request_id"] = "other-request"
        with self.assertRaisesRegex(TransitionError, "EXECUTION_RECEIPT_REQUEST_MISMATCH"):
            apply_event_data(
                active,
                "record_execution_receipt",
                "mission-steward",
                {"receipt": receipt, "request": request},
            )

    def test_execution_receipt_replay_is_refused(self) -> None:
        active = self.active()
        request = self.execution_request(active.revision)
        receipt = self.execution_receipt(request)
        updated = apply_event_data(
            active,
            "record_execution_receipt",
            "mission-steward",
            {"receipt": receipt, "request": request},
        )
        replay_request = self.execution_request(updated.revision)
        replay_request["request_id"] = request["request_id"]
        replay_receipt = self.execution_receipt(replay_request)
        with self.assertRaisesRegex(TransitionError, "EXECUTION_RECEIPT_REPLAY"):
            apply_event_data(
                updated,
                "record_execution_receipt",
                "mission-steward",
                {"receipt": replay_receipt, "request": replay_request},
            )


if __name__ == "__main__":
    unittest.main()
