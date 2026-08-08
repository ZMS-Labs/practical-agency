from __future__ import annotations

import unittest

from practical_agency.manifest_model import MissionManifest
from practical_agency.state_machine import MissionEvent, TransitionError, apply_event
from tests.helpers import clone_payload


class ApplyMissionOsTests(unittest.TestCase):
    def active(self) -> MissionManifest:
        payload = clone_payload()
        payload["revision"] = 2
        payload["state"]["status"] = "active"
        payload["state"]["current_frontier"] = ["write authorized artifact"]
        payload["state"]["next_action"] = "write authorized artifact"
        payload["continuity"]["prior_checkpoint"] = "checkpoint:1"
        payload["continuity"]["deferred_interests"] = []
        return MissionManifest.from_dict(payload)

    def test_apply_frontier_patch_writes_sole_carrier(self) -> None:
        updated = apply_event(
            self.active(),
            MissionEvent(
                "apply_mission_os",
                "mission-steward",
                {
                    "proposal_kind": "frontier_patch",
                    "labels": ["write authorized artifact", "verify receipt"],
                },
            ),
        )
        self.assertEqual(
            updated.state["current_frontier"],
            ["write authorized artifact", "verify receipt"],
        )
        self.assertEqual(updated.state["next_action"], "write authorized artifact")
        self.assertEqual(updated.revision, 3)
        kinds = [d.get("kind") for d in updated.continuity["decisions"]]
        self.assertIn("mission-os-apply", kinds)

    def test_apply_does_not_change_instruction_or_desired_state(self) -> None:
        manifest = self.active()
        updated = apply_event(
            manifest,
            MissionEvent(
                "apply_mission_os",
                "mission-steward",
                {
                    "proposal_kind": "frontier_patch",
                    "labels": ["write authorized artifact"],
                },
            ),
        )
        self.assertEqual(
            updated.authority["instruction"], manifest.authority["instruction"]
        )
        self.assertEqual(
            updated.outcome["desired_state"], manifest.outcome["desired_state"]
        )

    def test_defer_persists_interest(self) -> None:
        interest = {
            "schema": "deferred-interest@1",
            "mission_id": "mission-001",
            "summary": "explore alternate doc layout",
            "criticality": "low",
            "why_not_now": "not required for completion proof",
            "suggested_next": None,
            "subject_refs": [],
            "created_at_revision": 2,
            "status": "open",
        }
        updated = apply_event(
            self.active(),
            MissionEvent(
                "apply_mission_os",
                "mission-steward",
                {"proposal_kind": "defer", "interest": interest},
            ),
        )
        self.assertEqual(len(updated.continuity["deferred_interests"]), 1)
        self.assertEqual(
            updated.state["current_frontier"], ["write authorized artifact"]
        )

    def test_high_absorb_without_amendment_refused(self) -> None:
        payload = clone_payload()
        payload["revision"] = 2
        payload["state"]["status"] = "active"
        payload["continuity"]["prior_checkpoint"] = "checkpoint:1"
        payload["continuity"]["deferred_interests"] = [
            {
                "schema": "deferred-interest@1",
                "mission_id": "mission-001",
                "summary": "touch protected area later",
                "criticality": "high",
                "why_not_now": "not now",
                "suggested_next": "rewrite unrelated files",
                "subject_refs": ["repo:example@rev-1"],
                "created_at_revision": 2,
                "status": "open",
            }
        ]
        manifest = MissionManifest.from_dict(payload)
        with self.assertRaisesRegex(TransitionError, "HIGH_ABSORB_AMENDMENT_REQUIRED"):
            apply_event(
                manifest,
                MissionEvent(
                    "apply_mission_os",
                    "operator:test",
                    {"proposal_kind": "absorb", "interest_index": 0},
                ),
            )

    def test_high_absorb_with_amendment_marks_absorbed_without_frontier_smuggle(self) -> None:
        payload = clone_payload()
        payload["revision"] = 2
        payload["state"]["status"] = "active"
        payload["state"]["current_frontier"] = ["write authorized artifact"]
        payload["continuity"]["prior_checkpoint"] = "checkpoint:1"
        payload["continuity"]["deferred_interests"] = [
            {
                "schema": "deferred-interest@1",
                "mission_id": "mission-001",
                "summary": "touch protected area later",
                "criticality": "high",
                "why_not_now": "not now",
                "suggested_next": "rewrite unrelated files",
                "subject_refs": ["repo:example@rev-1"],
                "created_at_revision": 2,
                "status": "open",
            }
        ]
        manifest = MissionManifest.from_dict(payload)
        updated = apply_event(
            manifest,
            MissionEvent(
                "apply_mission_os",
                "operator:test",
                {
                    "proposal_kind": "absorb",
                    "interest_index": 0,
                    "amendment": "Operator approves absorbing high deferred interest for later scheduling only.",
                },
            ),
        )
        self.assertEqual(updated.continuity["deferred_interests"][0]["status"], "absorbed")
        self.assertEqual(updated.state["current_frontier"], ["write authorized artifact"])
        self.assertNotIn(
            "rewrite unrelated files", updated.state["current_frontier"]
        )


if __name__ == "__main__":
    unittest.main()
