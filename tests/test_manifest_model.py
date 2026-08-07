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
                "material_work_actors": [],
                "required_gates": [],
                "unresolved_verdicts": [],
                "completion_acceptor": None,
                "acceptance_receipt_ref": None,
            },
        }

    def test_minimal_manifest_is_valid(self) -> None:
        self.assertEqual(validate_manifest_dict(self.minimal_payload()), [])

    def test_operator_instruction_round_trips_verbatim(self) -> None:
        payload = self.minimal_payload()
        authority = payload["authority"]
        assert isinstance(authority, dict)
        authority["instruction"] = "Keep  two spaces\nand this newline."
        manifest = MissionManifest.from_dict(payload)
        decoded = json.loads(manifest.to_canonical_json())
        self.assertEqual(decoded["authority"]["instruction"], authority["instruction"])

    def test_nested_state_is_defensively_copied(self) -> None:
        payload = self.minimal_payload()
        manifest = MissionManifest.from_dict(payload)
        authority = payload["authority"]
        assert isinstance(authority, dict)
        authority["instruction"] = "mutated"
        self.assertEqual(manifest.authority["instruction"], "Create and verify the example artifact.")
        exported = manifest.to_dict()
        exported["authority"]["instruction"] = "mutated again"
        self.assertEqual(manifest.authority["instruction"], "Create and verify the example artifact.")

    def test_manifest_nested_state_is_immutable(self) -> None:
        manifest = MissionManifest.from_dict(self.minimal_payload())
        with self.assertRaises(TypeError):
            manifest.authority["instruction"] = "mutated"
        with self.assertRaises(AttributeError):
            manifest.authority["permissions"].append("admin")
        with self.assertRaises(AttributeError):
            manifest.state["blockers"].append({"code": "hidden"})

    def test_self_acceptance_is_rejected(self) -> None:
        payload = self.minimal_payload()
        integrity = payload["integrity"]
        assert isinstance(integrity, dict)
        integrity["actor_may_self_accept"] = True
        errors = validate_manifest_dict(payload)
        self.assertTrue(any(error.startswith("SELF_ACCEPTANCE_FORBIDDEN:") for error in errors))

    def test_revision_must_be_positive_and_not_boolean(self) -> None:
        for value in (0, -1, True):
            with self.subTest(value=value):
                payload = self.minimal_payload()
                payload["revision"] = value
                errors = validate_manifest_dict(payload)
                self.assertTrue(any(error.startswith("INVALID_REVISION:") for error in errors))

    def test_status_enum_is_closed(self) -> None:
        payload = self.minimal_payload()
        state = payload["state"]
        assert isinstance(state, dict)
        state["status"] = "mostly-done"
        errors = validate_manifest_dict(payload)
        self.assertTrue(any(error.startswith("INVALID_STATUS:") for error in errors))

    def test_unknown_top_level_field_is_rejected(self) -> None:
        payload = self.minimal_payload()
        payload["surprise"] = True
        errors = validate_manifest_dict(payload)
        self.assertTrue(any(error.startswith("UNEXPECTED_TOP_LEVEL_FIELD:") for error in errors))

    def test_completed_requires_independent_acceptance_receipt(self) -> None:
        payload = self.minimal_payload()
        state = payload["state"]
        assert isinstance(state, dict)
        state["status"] = "completed"
        errors = validate_manifest_dict(payload)
        self.assertTrue(any(error.startswith("COMPLETION_ACCEPTOR_REQUIRED:") for error in errors))
        self.assertTrue(any(error.startswith("ACCEPTANCE_RECEIPT_REQUIRED:") for error in errors))

    def test_example_file_is_valid(self) -> None:
        path = Path(__file__).parents[1] / "examples" / "minimal-mission.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(validate_manifest_dict(payload), [])

    def test_status_enum_values_are_stable(self) -> None:
        self.assertEqual(
            {status.value for status in MissionStatus},
            {"draft", "active", "paused", "blocked", "verifying", "completed", "cancelled"},
        )

    def test_declared_string_lists_reject_non_strings(self) -> None:
        payload = self.minimal_payload()
        payload["authority"]["permissions"] = [{"not": "a string"}]
        payload["outcome"]["completion_proof"] = [42]
        errors = validate_manifest_dict(payload)
        self.assertTrue(any(error.startswith("INVALID_STRING_LIST: authority.permissions") for error in errors))
        self.assertTrue(any(error.startswith("INVALID_STRING_LIST: outcome.completion_proof") for error in errors))

    def test_cancelled_state_requires_recorded_revocation(self) -> None:
        payload = self.minimal_payload()
        payload["state"]["status"] = "cancelled"
        payload["state"]["next_action"] = None
        errors = validate_manifest_dict(payload)
        self.assertTrue(any(error.startswith("CANCELLED_REQUIRES_REVOCATION") for error in errors))

    def test_revoked_manifest_requires_receipted_revocation_decision(self) -> None:
        payload = self.minimal_payload()
        payload["authority"]["revoked"] = True
        payload["authority"]["revocation_reason"] = "operator stopped the mission"
        payload["state"]["status"] = "cancelled"
        payload["state"]["next_action"] = None
        errors = validate_manifest_dict(payload)
        self.assertTrue(any(error.startswith("REVOCATION_DECISION_REQUIRED") for error in errors))

    def test_reference_and_frontier_lists_reject_non_strings(self) -> None:
        payload = self.minimal_payload()
        payload["state"]["current_frontier"] = [42]
        payload["continuity"]["durable_artifacts"] = [{"bad": "ref"}]
        payload["integrity"]["required_gates"] = [False]
        errors = validate_manifest_dict(payload)
        for field in (
            "state.current_frontier",
            "continuity.durable_artifacts",
            "integrity.required_gates",
        ):
            self.assertTrue(
                any(error.startswith(f"INVALID_STRING_LIST: {field}") for error in errors),
                (field, errors),
            )

    def test_authority_amendments_are_receipted_and_ordered(self) -> None:
        payload = self.minimal_payload()
        payload["revision"] = 3
        payload["authority"]["amendments"] = [
            {
                "revision": 3,
                "instruction": "Add a receipt.",
                "authorized_by": "operator:test",
                "authorization_ref": "approval:amend",
                "recorded_at": "2026-08-07T17:00:00Z",
            },
            {
                "revision": 2,
                "instruction": "Out of order.",
                "authorized_by": "operator:test",
                "authorization_ref": "approval:older",
                "recorded_at": "2026-08-07T16:00:00Z",
            },
        ]
        errors = validate_manifest_dict(payload)
        self.assertTrue(any(error.startswith("INVALID_AMENDMENT_ORDER") for error in errors))
        del payload["authority"]["amendments"][0]["authorization_ref"]
        errors = validate_manifest_dict(payload)
        self.assertTrue(any(error.startswith("INVALID_AMENDMENT") for error in errors))


if __name__ == "__main__":
    unittest.main()
