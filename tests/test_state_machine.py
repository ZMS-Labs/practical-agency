from __future__ import annotations

import unittest

from practical_agency.authority import revoke_authority
from practical_agency.manifest_model import MissionManifest
from practical_agency.state_machine import TransitionError, reopen_for_contradiction, transition
from tests.helpers import active_payload, minimal_payload


class StateMachineTests(unittest.TestCase):
    def test_draft_approval_enters_active_and_increments_revision(self) -> None:
        manifest = MissionManifest.from_dict(minimal_payload())
        active = transition(
            manifest,
            "active",
            actor_ref="operator:test",
            evidence_ref="approval:test",
            reason="approved",
        )
        self.assertEqual(active.state["status"], "active")
        self.assertEqual(active.revision, 2)
        self.assertEqual(active.state["current_frontier"], ("advance mission",))
        self.assertEqual(active.state["next_action"], "advance mission")

    def test_illegal_transition_is_rejected(self) -> None:
        manifest = MissionManifest.from_dict(minimal_payload())
        with self.assertRaisesRegex(TransitionError, "ILLEGAL_TRANSITION"):
            transition(manifest, "completed", actor_ref="reviewer:test", evidence_ref="accept:test")

    def test_blocked_requires_reason(self) -> None:
        manifest = MissionManifest.from_dict(active_payload())
        with self.assertRaisesRegex(TransitionError, "BLOCK_REASON_REQUIRED"):
            transition(manifest, "blocked", actor_ref="steward:test", evidence_ref="probe:test")

    def test_verifying_does_not_self_promote_to_complete(self) -> None:
        manifest = MissionManifest.from_dict(active_payload())
        verifying = transition(
            manifest,
            "verifying",
            actor_ref="steward:test",
            evidence_ref="proof-bundle:test",
            reason="proof bundle ready",
        )
        with self.assertRaisesRegex(TransitionError, "INDEPENDENT_ACCEPTOR_REQUIRED"):
            transition(
                verifying,
                "completed",
                actor_ref="steward:test",
                evidence_ref="accept:test",
                independent=True,
            )

    def test_independent_acceptor_can_complete(self) -> None:
        payload = active_payload()
        payload["integrity"]["material_work_actors"] = ["steward:test"]
        manifest = MissionManifest.from_dict(payload)
        verifying = transition(
            manifest,
            "verifying",
            actor_ref="steward:test",
            evidence_ref="proof-bundle:test",
            reason="proof bundle ready",
        )
        completed = transition(
            verifying,
            "completed",
            actor_ref="reviewer:test",
            evidence_ref="accept:test",
            reason="independent pass",
            independent=True,
        )
        self.assertEqual(completed.state["status"], "completed")
        self.assertEqual(completed.integrity["completion_acceptor"], "reviewer:test")
        self.assertIsNone(completed.state["next_action"])

    def test_completion_rejects_material_work_actor(self) -> None:
        payload = active_payload()
        payload["integrity"]["material_work_actors"] = ["reviewer:test"]
        verifying = transition(
            MissionManifest.from_dict(payload),
            "verifying",
            actor_ref="steward:test",
            evidence_ref="proof:test",
        )
        with self.assertRaisesRegex(TransitionError, "INDEPENDENT_ACCEPTOR_REQUIRED"):
            transition(
                verifying,
                "completed",
                actor_ref="reviewer:test",
                evidence_ref="accept:test",
                independent=True,
            )

    def test_live_contradiction_reopens_completed_mission(self) -> None:
        payload = active_payload()
        payload["integrity"]["material_work_actors"] = ["steward:test"]
        verifying = transition(
            MissionManifest.from_dict(payload),
            "verifying",
            actor_ref="steward:test",
            evidence_ref="proof:test",
        )
        completed = transition(
            verifying,
            "completed",
            actor_ref="reviewer:test",
            evidence_ref="accept:test",
            independent=True,
        )
        reopened = reopen_for_contradiction(
            completed,
            contradiction={"claim": "artifact hash", "observed": "changed"},
            observed_by="observer:test",
            evidence_ref="observation:test",
        )
        self.assertEqual(reopened.state["status"], "active")
        self.assertTrue(reopened.truth["contradictions"])
        self.assertIsNone(reopened.integrity["completion_acceptor"])

    def test_generic_transition_cannot_cancel_without_operator_revocation(self) -> None:
        manifest = MissionManifest.from_dict(active_payload())
        with self.assertRaisesRegex(TransitionError, "REVOCATION_REQUIRED"):
            transition(
                manifest,
                "cancelled",
                actor_ref="steward:test",
                evidence_ref="receipt:test",
                reason="agent decided to stop permanently",
            )

    def test_terminal_cancelled_mission_cannot_resume_without_new_authority(self) -> None:
        manifest = MissionManifest.from_dict(active_payload())
        cancelled = revoke_authority(
            manifest,
            operator_ref="operator:test",
            reason="operator revoked authority",
            authorization_ref="approval:revoke",
            recorded_at="2026-08-07T17:15:00Z",
        )
        with self.assertRaisesRegex(TransitionError, "TERMINAL_STATE"):
            transition(cancelled, "active", actor_ref="operator:test", evidence_ref="new:test")


if __name__ == "__main__":
    unittest.main()
