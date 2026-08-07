from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from practical_agency.manifest_model import MissionManifest, MissionStatus, load_manifest
from practical_agency.validation import validate_manifest_dict
from tests.helpers import clone_payload


class MissionManifestTests(unittest.TestCase):
    def test_minimal_manifest_is_valid(self) -> None:
        self.assertEqual(validate_manifest_dict(clone_payload()), [])

    def test_operator_instruction_round_trips_verbatim(self) -> None:
        payload = clone_payload()
        payload["authority"]["instruction"] = "Keep  two spaces\nand this newline."
        manifest = MissionManifest.from_dict(payload)
        decoded = json.loads(manifest.to_canonical_json())
        self.assertEqual(decoded["authority"]["instruction"], payload["authority"]["instruction"])

    def test_nested_state_is_defensively_copied(self) -> None:
        payload = clone_payload()
        manifest = MissionManifest.from_dict(payload)
        payload["authority"]["instruction"] = "mutated"
        exported = manifest.to_dict()
        exported["authority"]["instruction"] = "also mutated"
        self.assertEqual(manifest.authority["instruction"], "Create and verify the example artifact.")

    def test_self_acceptance_is_rejected(self) -> None:
        payload = clone_payload()
        payload["integrity"]["actor_may_self_accept"] = True
        self.assertTrue(any(x.startswith("SELF_ACCEPTANCE_FORBIDDEN:") for x in validate_manifest_dict(payload)))

    def test_revision_must_be_positive_integer_not_boolean(self) -> None:
        for value in (0, -1, True):
            payload = clone_payload()
            payload["revision"] = value
            self.assertTrue(any(x.startswith("INVALID_REVISION:") for x in validate_manifest_dict(payload)))

    def test_status_enum_is_closed(self) -> None:
        payload = clone_payload()
        payload["state"]["status"] = "mostly-done"
        self.assertTrue(any(x.startswith("INVALID_STATUS:") for x in validate_manifest_dict(payload)))
        self.assertEqual(MissionStatus.ACTIVE.value, "active")

    def test_unknown_keys_are_rejected_at_governed_levels(self) -> None:
        payload = clone_payload()
        payload["authority"]["unbounded_power"] = True
        payload["surprise"] = {}
        errors = validate_manifest_dict(payload)
        self.assertTrue(any("authority.unbounded_power" in x for x in errors))
        self.assertTrue(any("surprise" in x for x in errors))

    def test_completed_requires_acceptor_and_no_unresolved_verdicts(self) -> None:
        payload = clone_payload()
        payload["state"]["status"] = "completed"
        payload["integrity"]["unresolved_verdicts"] = ["gate:unknown"]
        errors = validate_manifest_dict(payload)
        self.assertTrue(any(x.startswith("COMPLETION_ACCEPTOR_REQUIRED:") for x in errors))
        self.assertTrue(any(x.startswith("UNRESOLVED_VERDICTS:") for x in errors))

    def test_revoked_authority_cannot_remain_active(self) -> None:
        payload = clone_payload()
        payload["authority"]["revoked"] = True
        payload["authority"]["revocation_reason"] = "stop"
        payload["state"]["status"] = "active"
        self.assertTrue(any(x.startswith("REVOKED_STATE_INVALID:") for x in validate_manifest_dict(payload)))

    def test_active_revision_after_one_requires_prior_checkpoint(self) -> None:
        payload = clone_payload()
        payload["revision"] = 2
        payload["state"]["status"] = "active"
        self.assertTrue(any(x.startswith("PRIOR_CHECKPOINT_REQUIRED:") for x in validate_manifest_dict(payload)))

    def test_load_manifest_validates_and_reads_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "mission.json"
            path.write_text(json.dumps(clone_payload()), encoding="utf-8")
            manifest = load_manifest(path)
            self.assertEqual(manifest.mission_id, "mission-001")

    def test_example_file_is_valid(self) -> None:
        path = Path(__file__).parents[1] / "examples" / "minimal-mission.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(validate_manifest_dict(payload), [])


if __name__ == "__main__":
    unittest.main()
