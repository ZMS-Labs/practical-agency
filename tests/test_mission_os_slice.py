"""Fixture path for mission OS first slice — NOT field v1."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from practical_agency.checkpoint_store import FileCheckpointStore
from practical_agency.coordinator import coordinate_once, dispatch_once
from practical_agency.filesystem_artifact import (
    FilesystemArtifactAdapter,
    verify_filesystem_receipt,
)
from practical_agency.manifest_model import MissionManifest
from practical_agency.mission_os import propose_defer, propose_frontier_patch
from practical_agency.state_machine import TransitionError, apply_event_data
from tests.helpers import clone_payload, mission_os_event


class MissionOsSliceTests(unittest.TestCase):
    def test_propose_apply_defer_filesystem_resume_independent_accept(self) -> None:
        original = "Manifest authorized text artifact under mission OS custody."
        payload = clone_payload()
        payload["authority"]["instruction"] = original
        payload["authority"]["acceptable_costs"] = [
            "one feature branch",
            "one local artifact write",
        ]
        payload["integrity"]["completion_acceptor"] = "reviewer:test"
        payload["outcome"]["completion_proof"] = ["artifact:validator-pass"]
        draft = MissionManifest.from_dict(payload)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = FileCheckpointStore(root / "checkpoints")
            world = root / "world"
            receipt0 = store.save(draft)
            active = apply_event_data(
                draft,
                "approve", "operator:test", {"checkpoint_ref": receipt0.path},
            )

            proposal = propose_frontier_patch(
                active,
                ["write authorized artifact", "observe receipt"],
            )
            active = apply_event_data(
                active,
                "apply_mission_os", "mission-steward", mission_os_event(active, proposal.kind, {**proposal.payload}),
            )

            defer_prop = propose_defer(
                active,
                {
                    "schema": "deferred-interest@1",
                    "mission_id": "mission-001",
                    "summary": "optional docs polish",
                    "criticality": "low",
                    "why_not_now": "not required for completion proof",
                    "suggested_next": None,
                    "subject_refs": [],
                    "created_at_revision": active.revision,
                    "critical_path_clearance": {"reason": "Recorded outside the current completion path.", "basis_refs": ["authority:instruction"]},
                    "status": "open",
                },
            )
            active = apply_event_data(
                active,
                "apply_mission_os", "mission-steward", mission_os_event(active, defer_prop.kind, {**defer_prop.payload}),
            )
            self.assertEqual(len(active.continuity["deferred_interests"]), 1)
            self.assertEqual(
                active.state["current_frontier"][0], "write authorized artifact"
            )

            adapter = FilesystemArtifactAdapter(world)
            decision = coordinate_once(
                active,
                execution_request={
                    "capability_id": "filesystem-artifact",
                    "requested_permissions": ["repository:write"],
                    "requested_effects": [
                        "relpath:mission-artifacts/os-slice.txt",
                        "utf8:os-slice-body",
                    ],
                    "estimated_costs": ["one local artifact write"],
                    "action": "write-text",
                },
                checkpoint_store=store,
                require_applied_frontier=True,
            )
            self.assertEqual(decision.kind, "DISPATCH")
            result = dispatch_once(active, decision, adapter)
            self.assertEqual(result["status"], "completed")

            recorded = apply_event_data(
                active,
                "record_execution_receipt",
                "mission-steward",
                {"receipt": result, "request": decision.request},
            )
            acted = apply_event_data(
                recorded,
                "record_action", "mission-steward", {"action_ref": result["artifact_refs"][0]},
            )
            observed = apply_event_data(
                acted,
                "record_observation", "observer:test", {
                        "artifact_ref": "artifact:validator-pass",
                        "fact": {
                            "subject_ref": "artifact:os-slice",
                            "value": "os-slice-body",
                        },
                    },
            )
            ckpt = store.save(observed)

            del draft, active, recorded, acted, observed, decision, result
            resumed = store.load(ckpt)
            self.assertEqual(resumed.authority["instruction"], original)
            self.assertEqual(len(resumed.continuity["deferred_interests"]), 1)
            self.assertEqual(len(resumed.continuity["execution_receipts"]), 1)
            persisted_receipt = resumed.continuity["execution_receipts"][0]
            verified_receipt = verify_filesystem_receipt(
                persisted_receipt["external_receipt_ref"],
                persisted_receipt["request"],
                world,
            )
            self.assertEqual(verified_receipt["state"], "committed")
            self.assertEqual(
                verified_receipt["artifact_sha256"],
                persisted_receipt["observed_effects"][0]["sha256"],
            )

            verifying = apply_event_data(
                resumed, "begin_verification", "mission-steward", {}
            )
            with self.assertRaisesRegex(
                TransitionError, "INDEPENDENT_ACCEPTANCE_REQUIRED"
            ):
                apply_event_data(
                    verifying,
                    "accept", "mission-steward", {
                            "verdict": "PASS",
                            "evidence_refs": ["artifact:validator-pass"],
                            "coverage_limits": ["fixture slice"],
                        },
                )
            completed = apply_event_data(
                verifying,
                "accept", "reviewer:test", {
                        "verdict": "PASS",
                        "evidence_refs": ["artifact:validator-pass"],
                        "coverage_limits": [
                            "fixture slice only — NOT field v1 / RELEASE-1.0.0"
                        ],
                    },
            )
            self.assertEqual(completed.state["status"], "completed")


if __name__ == "__main__":
    unittest.main()
