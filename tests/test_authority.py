from __future__ import annotations

import unittest

from practical_agency.authority import authorize_action
from practical_agency.manifest_model import MissionManifest
from tests.helpers import clone_payload


class AuthorityTests(unittest.TestCase):
    def manifest(self) -> MissionManifest:
        return MissionManifest.from_dict(clone_payload())

    def test_authorized_action_returns_no_refusals(self) -> None:
        self.assertEqual(
            authorize_action(
                self.manifest(),
                capability_id="fixture:writer",
                requested_permissions=["repository:write"],
                requested_effects=["intended files"],
                estimated_costs=["one feature branch"],
            ),
            [],
        )

    def test_revoked_authority_refuses_action(self) -> None:
        payload = clone_payload()
        payload["authority"]["revoked"] = True
        payload["authority"]["revocation_reason"] = "stop"
        payload["state"]["status"] = "cancelled"
        errors = authorize_action(MissionManifest.from_dict(payload), "fixture", [], [], [])
        self.assertIn("AUTHORITY_REVOKED", errors)

    def test_ungranted_permission_is_named(self) -> None:
        self.assertIn(
            "PERMISSION_NOT_GRANTED:network:write",
            authorize_action(self.manifest(), "fixture", ["network:write"], [], []),
        )

    def test_protected_state_violation_is_named(self) -> None:
        self.assertIn(
            "PROTECTED_STATE_VIOLATION:unrelated files",
            authorize_action(self.manifest(), "fixture", [], ["unrelated files"], []),
        )

    def test_unauthorized_cost_is_named(self) -> None:
        self.assertIn(
            "COST_NOT_AUTHORIZED:paid cloud runtime",
            authorize_action(self.manifest(), "fixture", [], [], ["paid cloud runtime"]),
        )

    def test_escalation_requirement_is_named(self) -> None:
        self.assertIn(
            "ESCALATION_REQUIRED:destructive action",
            authorize_action(self.manifest(), "fixture", [], ["destructive action"], []),
        )


if __name__ == "__main__":
    unittest.main()
