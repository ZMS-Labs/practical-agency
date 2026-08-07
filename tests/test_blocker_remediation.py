from __future__ import annotations

import unittest

from practical_agency.capability_discovery import CapabilityDescriptor, Persistence
from practical_agency.coordinator import coordinate_once
from practical_agency.manifest_model import MissionManifest
from tests.helpers import clone_payload


def remediation_manifest() -> MissionManifest:
    payload = clone_payload()
    payload["revision"] = 4
    payload["state"]["status"] = "active"
    payload["state"]["blockers"] = [
        "RECONCILIATION:CONTRADICTED:artifact:canonical"
    ]
    payload["state"]["next_action"] = "repair live state for artifact:canonical"
    payload["continuity"]["prior_checkpoint"] = "checkpoint:3"
    payload["integrity"]["unresolved_verdicts"] = [
        "RECONCILIATION:CONTRADICTED:artifact:canonical"
    ]
    return MissionManifest.from_dict(payload)


def execution(action: str) -> dict[str, object]:
    return {
        "capability_id": "fixture-writer",
        "requested_permissions": ["repository:write"],
        "requested_effects": ["intended files"],
        "estimated_costs": ["one feature branch"],
        "action": action,
    }


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
    def test_unrelated_execution_is_refused_while_blockers_bear_load(self) -> None:
        decision = coordinate_once(
            remediation_manifest(),
            execution_request=execution("write another unrelated artifact"),
            checkpoint_store=object(),
        )
        self.assertEqual(decision.kind, "BLOCK")
        self.assertIn("EXACT_REMEDIATION_ACTION_REQUIRED", decision.reason)

    def test_exact_recorded_remediation_action_may_dispatch(self) -> None:
        manifest = remediation_manifest()
        decision = coordinate_once(
            manifest,
            execution_request=execution(manifest.state["next_action"]),
            checkpoint_store=object(),
        )
        self.assertEqual(decision.kind, "DISPATCH")
        self.assertEqual(
            decision.request["action"], "repair live state for artifact:canonical"
        )

    def test_capability_request_cannot_displace_pending_remediation(self) -> None:
        decision = coordinate_once(
            remediation_manifest(),
            unresolved_condition="Investigate something else",
            selected_capability=capability(),
            checkpoint_store=object(),
        )
        self.assertEqual(decision.kind, "BLOCK")
        self.assertIn("EXACT_REMEDIATION_ACTION_REQUIRED", decision.reason)

    def test_completion_cannot_bypass_pending_remediation(self) -> None:
        decision = coordinate_once(
            remediation_manifest(),
            completion_proposed=True,
            checkpoint_store=object(),
        )
        self.assertEqual(decision.kind, "BLOCK")
        self.assertIn("EXACT_REMEDIATION_ACTION_REQUIRED", decision.reason)


if __name__ == "__main__":
    unittest.main()
