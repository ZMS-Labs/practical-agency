from __future__ import annotations

import unittest

from practical_agency.manifest_model import MissionManifest
from practical_agency.mission_os import propose_frontier_patch
from practical_agency.state_machine import TransitionError, apply_event_data
from tests.helpers import clone_payload, mission_os_event


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
        updated = apply_event_data(
            self.active(),
            "apply_mission_os", "mission-steward", mission_os_event(self.active(), "frontier_patch", {"labels": ["write authorized artifact", "verify receipt"]}),
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
        updated = apply_event_data(
            manifest,
            "apply_mission_os", "mission-steward", mission_os_event(manifest, "frontier_patch", {"labels": ["write authorized artifact"]}),
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
            "critical_path_clearance": {"reason": "Recorded outside the current completion path.", "basis_refs": ["authority:instruction"]},
            "status": "open",
        }
        updated = apply_event_data(
            self.active(),
            "apply_mission_os", "mission-steward", mission_os_event(self.active(), "defer", {"interest": interest}),
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
            apply_event_data(
                manifest,
                "apply_mission_os", "operator:test", mission_os_event(manifest, "absorb", {"interest_index": 0}),
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
        updated = apply_event_data(
            manifest,
            "apply_mission_os", "operator:test", mission_os_event(manifest, "absorb", {"interest_index": 0, "amendment": "Operator approves absorbing high deferred interest for later scheduling only."}),
        )
        self.assertEqual(updated.continuity["deferred_interests"][0]["status"], "absorbed")
        self.assertEqual(updated.state["current_frontier"], ["write authorized artifact"])
        self.assertNotIn(
            "rewrite unrelated files", updated.state["current_frontier"]
        )

    def test_non_steward_cannot_apply_frontier_patch(self) -> None:
        with self.assertRaisesRegex(TransitionError, "MISSION_STEWARD_REQUIRED"):
            apply_event_data(
                self.active(),
                "apply_mission_os", "capability:writer", mission_os_event(self.active(), "frontier_patch", {"labels": ["write authorized artifact"]}),
            )

    def test_non_steward_cannot_apply_defer(self) -> None:
        interest = {
            "schema": "deferred-interest@1",
            "mission_id": "mission-001",
            "summary": "explore alternate doc layout",
            "criticality": "low",
            "why_not_now": "not required for completion proof",
            "suggested_next": None,
            "subject_refs": [],
            "created_at_revision": 2,
            "critical_path_clearance": {"reason": "Recorded outside the current completion path.", "basis_refs": ["authority:instruction"]},
            "status": "open",
        }
        with self.assertRaisesRegex(TransitionError, "MISSION_STEWARD_REQUIRED"):
            apply_event_data(
                self.active(),
                "apply_mission_os", "operator:test", mission_os_event(self.active(), "defer", {"interest": interest}),
            )

    def test_non_steward_cannot_absorb_low_criticality(self) -> None:
        payload = clone_payload()
        payload["revision"] = 2
        payload["state"]["status"] = "active"
        payload["continuity"]["prior_checkpoint"] = "checkpoint:1"
        payload["continuity"]["deferred_interests"] = [
            {
                "schema": "deferred-interest@1",
                "mission_id": "mission-001",
                "summary": "minor follow-up",
                "criticality": "low",
                "why_not_now": "not now",
                "suggested_next": None,
                "subject_refs": [],
                "created_at_revision": 2,
                "status": "open",
            }
        ]
        manifest = MissionManifest.from_dict(payload)
        with self.assertRaisesRegex(TransitionError, "MISSION_STEWARD_REQUIRED"):
            apply_event_data(
                manifest,
                "apply_mission_os", "operator:test", mission_os_event(manifest, "absorb", {"interest_index": 0}),
            )

    def test_replan_slice_cites_existing_contradiction_without_inventing_it(self) -> None:
        payload = self.active().to_dict()
        payload["truth"]["contradictions"] = ["contradiction:layout-a"]
        manifest = MissionManifest.from_dict(payload)
        updated = apply_event_data(
            manifest,
            "apply_mission_os", "mission-steward", mission_os_event(manifest, "replan_slice", {"labels": ["reconcile truth", "write authorized artifact"], "contradiction_refs": ["contradiction:layout-a"]}),
        )
        self.assertEqual(updated.truth["contradictions"], ["contradiction:layout-a"])
        decisions = [
            d
            for d in updated.continuity["decisions"]
            if d.get("kind") == "mission-os-apply"
        ]
        self.assertEqual(decisions[-1]["proposal_kind"], "replan_slice")
        self.assertEqual(
            decisions[-1]["contradiction_refs"], ["contradiction:layout-a"]
        )

    def test_return_rebind_records_decision_without_changing_frontier(self) -> None:
        manifest = self.active()
        frontier_before = list(manifest.state["current_frontier"])
        updated = apply_event_data(
            manifest,
            "apply_mission_os", "mission-steward", mission_os_event(manifest, "return_rebind", {"invalidate": [{"subject_ref": "artifact:stale", "reason": "superseded"}]}),
        )
        self.assertEqual(updated.state["current_frontier"], frontier_before)
        decisions = [
            d
            for d in updated.continuity["decisions"]
            if d.get("kind") == "mission-os-apply"
            and d.get("proposal_kind") == "return_rebind"
        ]
        self.assertEqual(len(decisions), 1)
        self.assertEqual(
            decisions[0]["invalidate"],
            [{"subject_ref": "artifact:stale", "reason": "superseded"}],
        )

    def test_tampered_bound_proposal_is_refused(self) -> None:
        manifest = self.active()
        proposal = propose_frontier_patch(
            manifest,
            ["write authorized artifact"],
            basis_refs=["authority:instruction"],
        )
        tampered = proposal.to_dict()
        tampered["content"]["labels"] = ["invented objective"]
        with self.assertRaisesRegex(TransitionError, "MISSION_OS_PROPOSAL_HASH_MISMATCH"):
            apply_event_data(
                manifest,
                "apply_mission_os",
                "mission-steward",
                {"proposal": tampered},
            )

    def test_cross_mission_and_stale_proposals_are_refused(self) -> None:
        manifest = self.active()
        proposal = propose_frontier_patch(
            manifest,
            ["write authorized artifact"],
            basis_refs=["authority:instruction"],
        )
        cross = proposal.to_dict()
        cross["mission_id"] = "other-mission"
        with self.assertRaisesRegex(TransitionError, "MISSION_OS_PROPOSAL_MISSION_MISMATCH"):
            apply_event_data(
                manifest, "apply_mission_os", "mission-steward", {"proposal": cross}
            )
        stale = proposal.to_dict()
        stale["base_revision"] = manifest.revision - 1
        with self.assertRaisesRegex(TransitionError, "MISSION_OS_PROPOSAL_REVISION_MISMATCH"):
            apply_event_data(
                manifest, "apply_mission_os", "mission-steward", {"proposal": stale}
            )


if __name__ == "__main__":
    unittest.main()
