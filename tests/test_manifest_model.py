from __future__ import annotations

import json
import unittest
from pathlib import Path

from practical_agency.manifest_model import MissionManifest, MissionStatus
from practical_agency.validation import validate_manifest_dict


class MissionManifestTests(unittest.TestCase):
    def minimal_payload(self) -> dict[str, object]:
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
                "completion_acceptor": None,
            },
        }

    def test_minimal_manifest_is_valid(self) -> None:
        self.assertEqual(validate_manifest_dict(self.minimal_payload()), [])

    def test_operator_instruction_round_trips_verbatim(self) -> None:
        payload = self.minimal_payload()
        payload["authority"]["instruction"] = "Keep  two spaces\nand this newline."
        manifest = MissionManifest.from_dict(payload)
        encoded = manifest.to_canonical_json()
        decoded = json.loads(encoded)
        self.assertEqual(decoded["authority"]["instruction"], payload["authority"]["instruction"])

    def test_self_acceptance_is_rejected(self) -> None:
        payload = self.minimal_payload()
        payload["integrity"]["actor_may_self_accept"] = True
        errors = validate_manifest_dict(payload)
        self.assertTrue(any(error.startswith("SELF_ACCEPTANCE_FORBIDDEN:") for error in errors))

    def test_revision_must_be_positive(self) -> None:
        payload = self.minimal_payload()
        payload["revision"] = 0
        errors = validate_manifest_dict(payload)
        self.assertTrue(any(error.startswith("INVALID_REVISION:") for error in errors))

    def test_status_enum_is_closed(self) -> None:
        payload = self.minimal_payload()
        payload["state"]["status"] = "mostly-done"
        errors = validate_manifest_dict(payload)
        self.assertTrue(any(error.startswith("INVALID_STATUS:") for error in errors))

    def test_example_file_is_valid(self) -> None:
        path = Path(__file__).parents[1] / "examples" / "minimal-mission.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(validate_manifest_dict(payload), [])

    def test_mission_status_enum_values(self) -> None:
        self.assertEqual(
            {status.value for status in MissionStatus},
            {
                "draft",
                "active",
                "paused",
                "blocked",
                "verifying",
                "completed",
                "cancelled",
            },
        )


if __name__ == "__main__":
    unittest.main()
