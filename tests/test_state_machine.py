from __future__ import annotations

import copy
import unittest

from practical_agency.manifest_model import MissionManifest
from practical_agency.state_machine import MissionEvent, TransitionError, apply_event


def _draft_payload() -> dict:
    return {
        "schema": "mission-manifest@1",
        "mission_id": "mission-001",
        "revision": 1,
        "authority": {
            "operator_ref": "operator:test",
            "instruction": "Create and verify the example artifact.",
            "amendments": [],
            "permissions": ["repository:write"],
            "protected_state": ["unrelated files"],
            "acceptable_costs": ["one feature branch"],
            "escalation_required_for": ["destructive action"],
            "revoked": False,
            "revocation_reason": None,
        },
        "outcome": {
            "desired_state": "The example artifact exists and validates.",
            "completion_proof": ["validator passes"],
            "integrity_guards": ["runtime reads the canonical artifact"],
            "scope_proof": ["diff contains only intended files"],
            "stop_conditions": ["operator revokes authority"],
        },
        "truth": {
            "subject_refs": ["repo:example@rev-1"],
            "verified_facts": [],
            "assumptions": [],
            "contradictions": [],
            "unknowns": [],
        },
        "state": {
            "status": "draft",
            "completed_actions": [],
            "current_frontier": ["obtain approval"],
            "blockers": [],
            "next_action": "obtain approval",
        },
        "capabilities": {
            "discovered_at": None,
            "available": [],
            "invoked": [],
            "unavailable": [],
            "degraded": [],
        },
        "continuity": {
            "prior_checkpoint": None,
            "durable_artifacts": [],
            "decisions": [],
            "external_handoffs": [],
            "watch_commissions": [],
        },
        "integrity": {
            "actor_may_self_accept": False,
            "required_gates": [],
            "unresolved_verdicts": [],
            "completion_acceptor": "acceptor:independent",
        },
    }


def _event(kind: str, **kwargs) -> MissionEvent:
    base = {
        "kind": kind,
        "actor_ref": kwargs.pop("actor_ref", "operator:test"),
        "detail": kwargs.pop("detail", {}),
        "artifact_refs": kwargs.pop("artifact_refs", []),
        "verdict": kwargs.pop("verdict", None),
    }
    base.update(kwargs)
    return MissionEvent(**base)


class StateMachineTests(unittest.TestCase):
    def test_approve_moves_draft_to_active(self) -> None:
        manifest = MissionManifest.from_dict(_draft_payload())
        next_manifest = apply_event(manifest, _event("approve"))
        self.assertEqual(next_manifest.state["status"], "active")
        self.assertEqual(next_manifest.revision, 2)
        self.assertEqual(
            next_manifest.authority["instruction"],
            manifest.authority["instruction"],
        )

    def test_pause_resume_round_trip(self) -> None:
        active = apply_event(MissionManifest.from_dict(_draft_payload()), _event("approve"))
        paused = apply_event(active, _event("pause", actor_ref="mission-steward"))
        self.assertEqual(paused.state["status"], "paused")
        resumed = apply_event(paused, _event("resume", actor_ref="operator:test"))
        self.assertEqual(resumed.state["status"], "active")

    def test_steward_cannot_self_complete(self) -> None:
        active = apply_event(MissionManifest.from_dict(_draft_payload()), _event("approve"))
        verifying = apply_event(
            active,
            _event(
                "begin_verification",
                actor_ref="mission-steward",
                artifact_refs=["validator passes"],
            ),
        )
        with self.assertRaisesRegex(TransitionError, "INDEPENDENT_ACCEPTANCE_REQUIRED"):
            apply_event(
                verifying,
                _event(
                    "accept",
                    actor_ref="mission-steward",
                    verdict="PASS",
                    artifact_refs=["validator passes"],
                ),
            )

    def test_independent_accept_completes(self) -> None:
        active = apply_event(MissionManifest.from_dict(_draft_payload()), _event("approve"))
        verifying = apply_event(
            active,
            _event(
                "begin_verification",
                actor_ref="mission-steward",
                artifact_refs=["validator passes"],
            ),
        )
        # record proof artifact into continuity via observation
        observed = apply_event(
            verifying,
            _event(
                "record_observation",
                actor_ref="mission-steward",
                artifact_refs=["validator passes"],
                detail={"note": "proof present"},
            ),
        )
        completed = apply_event(
            observed,
            _event(
                "accept",
                actor_ref="acceptor:independent",
                verdict="PASS",
                artifact_refs=["validator passes"],
            ),
        )
        self.assertEqual(completed.state["status"], "completed")
        self.assertEqual(
            completed.authority["instruction"],
            "Create and verify the example artifact.",
        )

    def test_revoked_blocks_dispatch_style_events(self) -> None:
        active = apply_event(MissionManifest.from_dict(_draft_payload()), _event("approve"))
        revoked = apply_event(
            active,
            _event("revoke", actor_ref="operator:test", detail={"reason": "stop"}),
        )
        self.assertEqual(revoked.state["status"], "blocked")
        with self.assertRaisesRegex(TransitionError, "AUTHORITY_REVOKED"):
            apply_event(
                revoked,
                _event(
                    "record_action",
                    actor_ref="mission-steward",
                    detail={"action": "dispatch"},
                ),
            )

    def test_amendments_append_not_replace(self) -> None:
        active = apply_event(MissionManifest.from_dict(_draft_payload()), _event("approve"))
        amended = apply_event(
            active,
            _event(
                "amend_authority",
                actor_ref="operator:test",
                detail={"amendment": "Also keep the README accurate."},
            ),
        )
        self.assertEqual(
            amended.authority["instruction"],
            "Create and verify the example artifact.",
        )
        self.assertEqual(
            amended.authority["amendments"],
            ["Also keep the README accurate."],
        )
        again = apply_event(
            amended,
            _event(
                "amend_authority",
                actor_ref="operator:test",
                detail={"amendment": "And leave LICENSE untouched."},
            ),
        )
        self.assertEqual(
            again.authority["amendments"],
            [
                "Also keep the README accurate.",
                "And leave LICENSE untouched.",
            ],
        )

    def test_reject_returns_to_active(self) -> None:
        active = apply_event(MissionManifest.from_dict(_draft_payload()), _event("approve"))
        verifying = apply_event(
            active,
            _event(
                "begin_verification",
                actor_ref="mission-steward",
                artifact_refs=["validator passes"],
            ),
        )
        rejected = apply_event(
            verifying,
            _event(
                "reject",
                actor_ref="acceptor:independent",
                verdict="FAIL",
                detail={"reason": "proof incomplete"},
            ),
        )
        self.assertEqual(rejected.state["status"], "active")

    def test_cancel_from_draft(self) -> None:
        cancelled = apply_event(
            MissionManifest.from_dict(_draft_payload()),
            _event("cancel", actor_ref="operator:test"),
        )
        self.assertEqual(cancelled.state["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
