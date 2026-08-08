from __future__ import annotations

import unittest

from practical_agency.manifest_model import MissionManifest
from practical_agency.mission_os import bind_mission_os_proposal, propose_replan_slice
from practical_agency.state_machine import TransitionError, apply_event_data
from tests.helpers import clone_payload


class ReplanContradictionBoundaryTests(unittest.TestCase):
    def active(self) -> MissionManifest:
        payload = clone_payload()
        payload["revision"] = 2
        payload["state"]["status"] = "active"
        payload["state"]["current_frontier"] = ["write authorized artifact"]
        payload["state"]["next_action"] = "write authorized artifact"
        payload["continuity"]["prior_checkpoint"] = "checkpoint:1"
        return MissionManifest.from_dict(payload)

    def test_proposer_rejects_generic_basis_as_contradiction(self) -> None:
        with self.assertRaisesRegex(ValueError, "REPLAN_CONTRADICTION_UNRESOLVED"):
            propose_replan_slice(
                self.active(),
                new_frontier=["invent unrelated replan"],
                contradiction_refs=["authority:instruction"],
            )

    def test_apply_rejects_bound_generic_basis_as_contradiction(self) -> None:
        manifest = self.active()
        proposal = bind_mission_os_proposal(
            manifest,
            "replan_slice",
            {
                "labels": ["invent unrelated replan"],
                "basis_refs": ["authority:instruction"],
                "replace_range": [0, 1],
                "contradiction_refs": ["authority:instruction"],
            },
        )
        with self.assertRaisesRegex(
            TransitionError, "REPLAN_CONTRADICTION_UNRESOLVED"
        ):
            apply_event_data(
                manifest,
                "apply_mission_os",
                "mission-steward",
                proposal.to_event_data(),
            )


if __name__ == "__main__":
    unittest.main()
