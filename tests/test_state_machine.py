from __future__ import annotations

import unittest

from practical_agency.manifest_model import MissionManifest
from practical_agency.state_machine import MissionEvent, TransitionError, apply_event
from tests.helpers import clone_payload


class StateMachineTests(unittest.TestCase):
    def draft(self) -> MissionManifest:
        return MissionManifest.from_dict(clone_payload())

    def active(self) -> MissionManifest:
        return apply_event(
            self.draft(),
            MissionEvent("approve", "operator:test", {"checkpoint_ref": "checkpoint:1"}),
        )

    def observed(self, manifest: MissionManifest) -> MissionManifest:
        return apply_event(
            manifest,
            MissionEvent(
                "record_observation",
                "observer:test",
                {
                    "artifact_ref": "artifact:validator-pass",
                    "fact": {"subject_ref": "repo:example@rev-1", "value": "validated"},
                },
            ),
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
            apply_event(self.draft(), MissionEvent("accept", "reviewer:test", {"verdict": "PASS"}))

    def test_revoked_mission_refuses_action_record(self) -> None:
        revoked = apply_event(self.active(), MissionEvent("revoke", "operator:test", {"reason": "stop"}))
        with self.assertRaisesRegex(TransitionError, "AUTHORITY_REVOKED"):
            apply_event(revoked, MissionEvent("record_action", "mission-steward", {"action_ref": "artifact:1"}))

    def test_amendments_append_without_replacing_instruction(self) -> None:
        original = self.draft()
        changed = apply_event(
            original,
            MissionEvent(
                "amend_authority",
                "operator:test",
                {"amendment": "Allow repository:read", "permissions_add": ["repository:read"]},
            ),
        )
        self.assertEqual(changed.authority["instruction"], original.authority["instruction"])
        self.assertEqual(changed.authority["amendments"], ["Allow repository:read"])
        self.assertIn("repository:read", changed.authority["permissions"])

    def test_self_acceptance_is_rejected_and_independent_acceptance_succeeds(self) -> None:
        payload = clone_payload()
        payload["integrity"]["completion_acceptor"] = "reviewer:test"
        active = apply_event(
            MissionManifest.from_dict(payload),
            MissionEvent("approve", "operator:test", {"checkpoint_ref": "checkpoint:1"}),
        )
        observed = self.observed(active)
        verifying = apply_event(observed, MissionEvent("begin_verification", "mission-steward", {}))
        with self.assertRaisesRegex(TransitionError, "INDEPENDENT_ACCEPTANCE_REQUIRED"):
            apply_event(
                verifying,
                MissionEvent("accept", "mission-steward", self.verdict("PASS")),
            )
        completed = apply_event(
            verifying,
            MissionEvent("accept", "reviewer:test", self.verdict("PASS")),
        )
        self.assertEqual(completed.state["status"], "completed")
        self.assertEqual(
            completed.continuity["decisions"][-1]["evidence_refs"],
            ["artifact:independent-review"],
        )

    def test_begin_verification_requires_all_completion_proof_refs(self) -> None:
        payload = clone_payload()
        payload["integrity"]["completion_acceptor"] = "reviewer:test"
        active = apply_event(
            MissionManifest.from_dict(payload),
            MissionEvent("approve", "operator:test", {"checkpoint_ref": "checkpoint:1"}),
        )
        with self.assertRaisesRegex(TransitionError, "PROOF_BUNDLE_NOT_READY"):
            apply_event(active, MissionEvent("begin_verification", "mission-steward", {}))

    def test_reject_cannot_be_rewritten_as_completion(self) -> None:
        payload = clone_payload()
        payload["integrity"]["completion_acceptor"] = "reviewer:test"
        active = apply_event(
            MissionManifest.from_dict(payload),
            MissionEvent("approve", "operator:test", {"checkpoint_ref": "checkpoint:1"}),
        )
        verifying = apply_event(
            self.observed(active),
            MissionEvent("begin_verification", "mission-steward", {}),
        )
        rejected = apply_event(
            verifying,
            MissionEvent(
                "reject",
                "reviewer:test",
                self.verdict("FAIL", reason="wrong"),
            ),
        )
        self.assertNotEqual(rejected.state["status"], "completed")
        self.assertIn("FAIL:wrong", rejected.integrity["unresolved_verdicts"])
        self.assertEqual(
            rejected.continuity["decisions"][-1]["coverage_limits"],
            ["fixture review only"],
        )


if __name__ == "__main__":
    unittest.main()
