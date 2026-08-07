from __future__ import annotations

import unittest

from practical_agency.authority import (
    ActionRequest,
    apply_amendment,
    evaluate_action,
    revoke_authority,
)
from practical_agency.manifest_model import MissionManifest
from tests.helpers import active_payload


class AuthorityTests(unittest.TestCase):
    def manifest(self) -> MissionManifest:
        return MissionManifest.from_dict(active_payload())

    def test_allowlisted_action_is_authorized(self) -> None:
        request = ActionRequest(
            action_id="write-example",
            description="write the example file",
            required_permissions=("repository:write",),
            touches=("examples/output.json",),
            costs=("one feature branch",),
            consequential=False,
            irreversible=False,
            authority_ref="approval:test",
            stop_condition="stop on write failure",
        )
        decision = evaluate_action(self.manifest(), request)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.code, "AUTHORIZED")

    def test_missing_permission_is_denied(self) -> None:
        request = ActionRequest(
            action_id="deploy",
            description="deploy production",
            required_permissions=("production:deploy",),
            touches=("production",),
            costs=(),
            consequential=True,
            irreversible=False,
            authority_ref="approval:test",
            stop_condition="stop on deploy error",
        )
        decision = evaluate_action(self.manifest(), request)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "PERMISSION_NOT_GRANTED")

    def test_protected_state_is_denied(self) -> None:
        request = ActionRequest(
            action_id="touch-unrelated",
            description="modify protected unrelated files",
            required_permissions=("repository:write",),
            touches=("unrelated files",),
            costs=(),
            consequential=False,
            irreversible=False,
            authority_ref="approval:test",
            stop_condition="stop",
        )
        decision = evaluate_action(self.manifest(), request)
        self.assertEqual(decision.code, "PROTECTED_STATE")

    def test_unaccepted_cost_is_denied(self) -> None:
        request = ActionRequest(
            action_id="spend",
            description="use paid compute",
            required_permissions=("repository:write",),
            touches=("examples/output.json",),
            costs=("paid compute",),
            consequential=False,
            irreversible=False,
            authority_ref="approval:test",
            stop_condition="stop",
        )
        decision = evaluate_action(self.manifest(), request)
        self.assertEqual(decision.code, "COST_NOT_ACCEPTED")

    def test_consequential_action_needs_explicit_authority_reference(self) -> None:
        request = ActionRequest(
            action_id="consequential",
            description="make a consequential change",
            required_permissions=("repository:write",),
            touches=("examples/output.json",),
            costs=(),
            consequential=True,
            irreversible=False,
            authority_ref=None,
            stop_condition="stop",
        )
        decision = evaluate_action(self.manifest(), request)
        self.assertEqual(decision.code, "AUTHORITY_RECEIPT_REQUIRED")

    def test_irreversible_action_requires_escalation(self) -> None:
        request = ActionRequest(
            action_id="delete",
            description="destructive action",
            required_permissions=("repository:write",),
            touches=("examples/output.json",),
            costs=(),
            consequential=True,
            irreversible=True,
            authority_ref="approval:test",
            stop_condition="stop",
        )
        decision = evaluate_action(self.manifest(), request)
        self.assertEqual(decision.code, "ESCALATION_REQUIRED")

    def test_revoked_authority_stops_all_dispatch(self) -> None:
        revoked = revoke_authority(
            self.manifest(),
            operator_ref="operator:test",
            reason="stop now",
            authorization_ref="approval:revoke-1",
            recorded_at="2026-08-07T17:10:00Z",
        )
        request = ActionRequest(
            action_id="write-example",
            description="write the example file",
            required_permissions=("repository:write",),
            touches=("examples/output.json",),
            costs=("one feature branch",),
            consequential=False,
            irreversible=False,
            authority_ref="approval:test",
            stop_condition="stop",
        )
        decision = evaluate_action(revoked, request)
        self.assertEqual(decision.code, "AUTHORITY_REVOKED")
        self.assertEqual(revoked.state["status"], "cancelled")

    def test_amendment_is_append_only_and_preserves_original_instruction(self) -> None:
        manifest = self.manifest()
        amended = apply_amendment(
            manifest,
            instruction="Also produce a receipt.",
            authorized_by="operator:test",
            authorization_ref="approval:amend-1",
            recorded_at="2026-08-07T17:00:00Z",
        )
        self.assertEqual(amended.authority["instruction"], manifest.authority["instruction"])
        self.assertEqual(amended.authority["amendments"][-1]["instruction"], "Also produce a receipt.")
        self.assertEqual(amended.revision, manifest.revision + 1)

    def test_revocation_requires_durable_authority_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "REVOCATION_RECEIPT_REQUIRED"):
            revoke_authority(
                self.manifest(),
                operator_ref="operator:test",
                reason="stop now",
                authorization_ref="",
                recorded_at="2026-08-07T17:10:00Z",
            )
        with self.assertRaisesRegex(ValueError, "REVOCATION_TIME_REQUIRED"):
            revoke_authority(
                self.manifest(),
                operator_ref="operator:test",
                reason="stop now",
                authorization_ref="approval:revoke-1",
                recorded_at="",
            )

    def test_amendment_requires_nonempty_instruction_and_time(self) -> None:
        with self.assertRaisesRegex(ValueError, "AMENDMENT_REQUIRED"):
            apply_amendment(
                self.manifest(),
                instruction="   ",
                authorized_by="operator:test",
                authorization_ref="approval:amend-1",
                recorded_at="2026-08-07T17:00:00Z",
            )
        with self.assertRaisesRegex(ValueError, "AMENDMENT_TIME_REQUIRED"):
            apply_amendment(
                self.manifest(),
                instruction="Add a receipt.",
                authorized_by="operator:test",
                authorization_ref="approval:amend-1",
                recorded_at="",
            )

    def test_dispatch_requires_an_active_mission(self) -> None:
        payload = active_payload()
        payload["state"]["status"] = "paused"
        payload["state"]["blockers"] = [{"kind": "pause", "reason": "operator pause"}]
        manifest = MissionManifest.from_dict(payload)
        request = ActionRequest(
            action_id="write-example",
            description="write the example file",
            required_permissions=("repository:write",),
            touches=("examples/output.json",),
            costs=("one feature branch",),
            consequential=False,
            irreversible=False,
            authority_ref="approval:test",
            stop_condition="stop on write failure",
        )
        decision = evaluate_action(manifest, request)
        self.assertEqual(decision.code, "MISSION_NOT_ACTIVE")


if __name__ == "__main__":
    unittest.main()
