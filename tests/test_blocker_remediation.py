from __future__ import annotations

import unittest

from practical_agency.authority import ActionRequest
from practical_agency.capability_discovery import CapabilityDescriptor, Persistence
from practical_agency.coordinator import MissionCoordinator
from practical_agency.manifest_model import MissionManifest
from tests.helpers import active_payload


REMEDIATION = "repair live state for artifact:canonical"


def remediation_manifest(*, next_action: str | None = REMEDIATION) -> MissionManifest:
    payload = active_payload()
    payload["state"]["blockers"] = [
        {
            "code": "RECONCILIATION_CONTRADICTED",
            "subject_ref": "artifact:canonical",
            "evidence_ref": "observation:contradiction",
        }
    ]
    payload["state"]["next_action"] = next_action
    payload["integrity"]["unresolved_verdicts"] = [
        {
            "verdict": "CONTRADICTED",
            "subject_ref": "artifact:canonical",
            "evidence_ref": "observation:contradiction",
        }
    ]
    return MissionManifest.from_dict(payload)


def execution(description: str) -> ActionRequest:
    return ActionRequest(
        action_id="repair-live-state",
        description=description,
        required_permissions=("repository:write",),
        touches=("intended files",),
        costs=("one feature branch",),
        consequential=False,
        irreversible=False,
        authority_ref="authority:repair",
        stop_condition="stop after the one recorded remediation action",
    )


def capability() -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability_id="fixture-reader",
        kind="skill",
        source_ref="fixture://skill",
        source_sha256="a" * 64,
        description="Use for one bounded fixture question.",
        input_contract=None,
        output_contract=None,
        authority_required=(),
        persistence=Persistence.SESSION,
        independence="actor",
        availability="available",
        degradation_reason=None,
    )


class BlockerRemediationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.coordinator = MissionCoordinator(checkpoint_store=object())

    def test_unrelated_execution_is_refused_while_blockers_bear_load(self) -> None:
        decision = self.coordinator.decide(
            remediation_manifest(),
            execution_request=execution("write another unrelated artifact"),
        )
        self.assertEqual(decision.kind, "BLOCK")
        self.assertIn("EXACT_REMEDIATION_ACTION_REQUIRED", decision.reason)

    def test_exact_recorded_remediation_action_may_dispatch(self) -> None:
        decision = self.coordinator.decide(
            remediation_manifest(),
            execution_request=execution(REMEDIATION),
        )
        self.assertEqual(decision.kind, "DISPATCH")

    def test_capability_request_cannot_displace_pending_remediation(self) -> None:
        decision = self.coordinator.decide(
            remediation_manifest(),
            capabilities=(capability(),),
            named_condition="Investigate something else",
            requested_capability_id="fixture-reader",
        )
        self.assertEqual(decision.kind, "BLOCK")
        self.assertIn("EXACT_REMEDIATION_ACTION_REQUIRED", decision.reason)

    def test_verification_cannot_bypass_pending_remediation(self) -> None:
        decision = self.coordinator.decide(
            remediation_manifest(),
            proof_bundle_ready=True,
        )
        self.assertEqual(decision.kind, "BLOCK")
        self.assertIn("EXACT_REMEDIATION_ACTION_REQUIRED", decision.reason)

    def test_blockers_without_a_recorded_remediation_fail_closed(self) -> None:
        decision = self.coordinator.decide(
            remediation_manifest(next_action=None),
            execution_request=execution(REMEDIATION),
        )
        self.assertEqual(decision.kind, "BLOCK")
        self.assertIn("REMEDIATION_ACTION_MISSING", decision.reason)


if __name__ == "__main__":
    unittest.main()
