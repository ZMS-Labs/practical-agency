from __future__ import annotations

import unittest

from practical_agency.capability_grants import (
    CapabilityGrantError,
    consume_grant,
    issue_grant,
)


class CapabilityGrantTests(unittest.TestCase):
    def _grant(self, **overrides):
        base = {
            "mission_id": "mission-1",
            "mission_revision": 7,
            "capability_id": "reader",
            "capability_descriptor_sha256": "a" * 64,
            "blocking_condition": "inspect the bounded evidence",
            "return_point": {
                "mission_id": "mission-1",
                "revision": 7,
                "frontier_index": 0,
                "label": "inspect the bounded evidence",
            },
            "admitted_operation": "file.read",
            "evidence_scope": ["file:docs/evidence.md"],
            "mutation": False,
            "expires_after_use": True,
        }
        base.update(overrides)
        return base

    def test_descriptor_derived_grant_is_one_use_and_mission_bound(self):
        grant = issue_grant(self._grant())
        self.assertEqual(grant["mission_id"], "mission-1")
        result = consume_grant(
            grant,
            mission_id="mission-1",
            mission_revision=7,
            operation="file.read",
            evidence_refs=["file:docs/evidence.md"],
        )
        self.assertEqual(result["verdict"], "PASS")
        with self.assertRaisesRegex(CapabilityGrantError, "GRANT_REPLAYED"):
            consume_grant(grant, mission_id="mission-1", mission_revision=7,
                          operation="file.read", evidence_refs=["file:docs/evidence.md"])

    def test_stale_cross_mission_and_ungranted_operations_refuse(self):
        grant = issue_grant(self._grant())
        for kwargs, code in [
            ({"mission_id": "mission-1", "mission_revision": 8, "operation": "file.read"}, "GRANT_STALE"),
            ({"mission_id": "mission-2", "mission_revision": 7, "operation": "file.read"}, "GRANT_MISSION_MISMATCH"),
            ({"mission_id": "mission-1", "mission_revision": 7, "operation": "file.write"}, "GRANT_OPERATION_NOT_ADMITTED"),
        ]:
            with self.subTest(code=code), self.assertRaisesRegex(CapabilityGrantError, code):
                consume_grant(grant, evidence_refs=["file:docs/evidence.md"], **kwargs)

    def test_mutation_and_missing_evidence_are_refused(self):
        grant = issue_grant(self._grant())
        with self.assertRaisesRegex(CapabilityGrantError, "GRANT_MUTATION_FORBIDDEN"):
            consume_grant(grant, mission_id="mission-1", mission_revision=7,
                          operation="file.read", evidence_refs=["file:docs/evidence.md"], mutation=True)
        grant = issue_grant(self._grant())
        with self.assertRaisesRegex(CapabilityGrantError, "GRANT_EVIDENCE_REQUIRED"):
            consume_grant(grant, mission_id="mission-1", mission_revision=7,
                          operation="file.read", evidence_refs=[])

    def test_wrong_return_point_or_revocation_refuses(self):
        grant = issue_grant(self._grant())
        with self.assertRaisesRegex(CapabilityGrantError, "GRANT_RETURN_POINT_MISMATCH"):
            consume_grant(grant, mission_id="mission-1", mission_revision=7,
                          operation="file.read", evidence_refs=["file:docs/evidence.md"],
                          return_point={"mission_id":"mission-1","revision":6,"frontier_index":0,"label":"inspect the bounded evidence"})
        grant = issue_grant(self._grant())
        grant["revoked"] = True
        with self.assertRaisesRegex(CapabilityGrantError, "GRANT_REVOKED"):
            consume_grant(grant, mission_id="mission-1", mission_revision=7,
                          operation="file.read", evidence_refs=["file:docs/evidence.md"])


if __name__ == "__main__":
    unittest.main()
