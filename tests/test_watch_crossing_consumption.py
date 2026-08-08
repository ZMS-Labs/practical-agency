from __future__ import annotations

import unittest

from practical_agency.manifest_model import MissionManifest
from practical_agency.mission_os import propose_replan_slice
from practical_agency.state_machine import TransitionError, apply_event_data
from practical_agency.watch_commission import handle_crossing_event
from tests.helpers import clone_payload


class WatchCrossingConsumptionTests(unittest.TestCase):
    def test_crossing_cannot_reopen_completed_mission_twice(self) -> None:
        payload = clone_payload()
        payload["revision"] = 5
        payload["state"]["status"] = "completed"
        payload["state"]["current_frontier"] = []
        payload["state"]["next_action"] = None
        payload["continuity"]["prior_checkpoint"] = "checkpoint:4"
        payload["integrity"]["completion_acceptor"] = "reviewer:test"
        payload["continuity"]["watch_commissions"] = [
            {
                "commission_id": "wc-1",
                "state": "PROVEN",
                "external_observer": {"enabled": True},
            }
        ]
        manifest = MissionManifest.from_dict(payload)
        event_ref = "external-event://single-use"
        observed = handle_crossing_event(
            manifest,
            {
                "commission_id": "wc-1",
                "event_ref": event_ref,
                "observed_at": "2026-08-08T16:00:00Z",
            },
        )

        first_proposal = propose_replan_slice(
            observed,
            new_frontier=["assess the observed crossing"],
            contradiction_refs=[event_ref],
        )
        reopened = apply_event_data(
            observed,
            "apply_mission_os",
            "mission-steward",
            first_proposal.to_event_data(),
        )
        self.assertEqual(reopened.state["status"], "active")

        reclosed_payload = reopened.to_dict()
        reclosed_payload["revision"] = reopened.revision + 1
        reclosed_payload["state"]["status"] = "completed"
        reclosed_payload["state"]["current_frontier"] = []
        reclosed_payload["state"]["next_action"] = None
        reclosed = MissionManifest.from_dict(reclosed_payload)

        replayed_proposal = propose_replan_slice(
            reclosed,
            new_frontier=["reopen from the same crossing again"],
            contradiction_refs=[event_ref],
        )
        with self.assertRaisesRegex(
            TransitionError, "WATCH_CROSSING_ALREADY_CONSUMED"
        ):
            apply_event_data(
                reclosed,
                "apply_mission_os",
                "mission-steward",
                replayed_proposal.to_event_data(),
            )


if __name__ == "__main__":
    unittest.main()
