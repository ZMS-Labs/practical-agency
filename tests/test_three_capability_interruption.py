from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from practical_agency.capability_grants import issue_grant
from practical_agency.capability_operations import execute_read
from practical_agency.manifest_model import MissionManifest
from practical_agency.state_machine import apply_event_data
from tests.helpers import clone_payload
from tests.helpers import record_fixture_verifier_result


class ThreeCapabilityInterruptionTests(unittest.TestCase):
    def test_three_classes_survive_restart_and_retain_typed_results(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "evidence.txt").write_text("file-proof", encoding="utf-8")
            payload = clone_payload()
            payload["integrity"]["completion_acceptor"] = "reviewer:independent"
            manifest = MissionManifest.from_dict(payload)
            manifest = apply_event_data(manifest, "approve", "operator:test", {"checkpoint_ref": "checkpoint:1"})
            cases = [
                ("file.read", "evidence.txt", ["evidence.txt"]),
                ("resource.read", "evidence.txt", ["evidence.txt"]),
                ("web.open", "https://example.test/source", ["https://example.test/source", "source:https://example.test/source"]),
            ]
            for index, (operation, target, evidence_scope) in enumerate(cases):
                point = {"mission_id": manifest.mission_id, "revision": manifest.revision, "frontier_index": 0, "label": manifest.state["current_frontier"][0]}
                grant = issue_grant({
                    "mission_id": manifest.mission_id, "mission_revision": manifest.revision,
                    "capability_id": f"descriptor-{index}", "capability_descriptor_sha256": (str(index) + "d" * 63),
                    "blocking_condition": f"bounded-{operation}", "return_point": point,
                    "admitted_operation": operation, "evidence_scope": evidence_scope,
                    "mutation": False, "expires_after_use": True,
                })
                manifest = apply_event_data(manifest, "record_capability_request", "mission-steward", {"grant": grant, "request": {"operation": operation}})
                # Simulate interruption: the next operation uses the reloaded manifest object.
                reloaded = MissionManifest.from_dict(manifest.to_dict())
                result = execute_read(grant, mission_id=reloaded.mission_id, mission_revision=grant["mission_revision"], operation=operation, target=target, workspace=root, evidence_refs=evidence_scope[1:] if operation == "web.open" else [target], evidence_payload={"source:https://example.test/source":"Example Domain"} if operation == "web.open" else None)
                manifest = apply_event_data(reloaded, "record_capability_result", "capability:result", {"grant_id": grant["grant_id"], "result": result})
                self.assertEqual(manifest.capabilities["invoked"][-1]["result"]["verdict"], "PASS")
            self.assertEqual(len(manifest.capabilities["invoked"]), 3)
            self.assertEqual(manifest.authority["instruction"], clone_payload()["authority"]["instruction"])
            manifest = record_fixture_verifier_result(manifest)
            manifest = apply_event_data(manifest, "begin_verification", "mission-steward", {})
            completed = apply_event_data(
                manifest,
                "accept",
                "reviewer:independent",
                {
                    "verdict": "PASS",
                    "evidence_refs": ["artifact:independent-review"],
                    "coverage_limits": ["deterministic fixture only"],
                    "separation_assurance": "declared-role-separation",
                },
            )
            self.assertEqual(completed.state["status"], "completed")


if __name__ == "__main__":
    unittest.main()
