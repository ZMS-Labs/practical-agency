from __future__ import annotations

import unittest

from practical_agency.deferred_interest import validate_deferred_interest
from practical_agency.manifest_model import MissionManifest
from practical_agency.validation import validate_manifest_dict
from tests.helpers import clone_payload


class DeferredInterestTests(unittest.TestCase):
    def test_missing_suggested_next_key_rejected(self) -> None:
        item = {
            "schema": "deferred-interest@1",
            "mission_id": "mission-001",
            "summary": "parked thread",
            "criticality": "low",
            "why_not_now": "not on critical path",
            "subject_refs": [],
            "created_at_revision": 1,
            "status": "open",
        }
        errors = validate_deferred_interest(item, mission_id="mission-001")
        self.assertTrue(any("DEFERRED_INTEREST_MISSING_FIELD" in e for e in errors))

    def test_high_requires_subject_refs(self) -> None:
        errors = validate_deferred_interest(
            {
                "schema": "deferred-interest@1",
                "mission_id": "mission-001",
                "summary": "parked thread",
                "criticality": "high",
                "why_not_now": "not on critical path",
                "suggested_next": None,
                "subject_refs": [],
                "created_at_revision": 1,
                "status": "open",
            },
            mission_id="mission-001",
        )
        self.assertTrue(any("SUBJECT_REFS_REQUIRED" in e for e in errors))

    def test_manifest_accepts_deferred_interests_array(self) -> None:
        payload = clone_payload()
        payload["continuity"]["deferred_interests"] = [
            {
                "schema": "deferred-interest@1",
                "mission_id": "mission-001",
                "summary": "nice-to-have note",
                "criticality": "low",
                "why_not_now": "not required for completion proof",
                "suggested_next": None,
                "subject_refs": [],
                "created_at_revision": 1,
                "status": "open",
            }
        ]
        self.assertEqual(validate_manifest_dict(payload), [])
        MissionManifest.from_dict(payload)

    def test_unknown_continuity_field_still_rejected(self) -> None:
        payload = clone_payload()
        payload["continuity"]["not_a_real_field"] = []
        self.assertTrue(
            any(e.startswith("UNKNOWN_FIELD:") for e in validate_manifest_dict(payload))
        )


if __name__ == "__main__":
    unittest.main()
