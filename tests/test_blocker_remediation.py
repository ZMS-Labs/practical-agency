from __future__ import annotations

import unittest

from practical_agency.capability_discovery import CapabilityDescriptor, Persistence
from practical_agency.coordinator import (
    CoordinationDecision,
    CoordinationError,
    ReturnPoint,
    coordinate_once,
    dispatch_once,
)
from practical_agency.manifest_model import MissionManifest
from practical_agency.mission_os import frontier_sha256
from practical_agency.state_machine import TransitionError, apply_event_data
from tests.helpers import clone_payload


def remediation_manifest(*, next_action: str | None = "repair live state for artifact:canonical") -> MissionManifest:
    payload = clone_payload()
    payload["revision"] = 4
    payload["state"]["status"] = "active"
    payload["state"]["blockers"] = [
        "RECONCILIATION:CONTRADICTED:artifact:canonical"
    ]
    payload["state"]["next_action"] = next_action
    payload["continuity"]["prior_checkpoint"] = "checkpoint:3"
    payload["integrity"]["unresolved_verdicts"] = [
        "RECONCILIATION:CONTRADICTED:artifact:canonical"
    ]
    payload["integrity"]["completion_acceptor"] = "reviewer:test"
    payload["continuity"]["durable_artifacts"] = ["artifact:validator-pass"]
    payload["continuity"]["decisions"].append(
        {
            "kind": "mission-os-apply",
            "proposal_kind": "frontier_patch",
            "proposal_id": "proposal-before-remediation",
            "base_revision": 1,
            "payload_sha256": "a" * 64,
            "at_revision": 2,
            "frontier_sha256": frontier_sha256(payload["state"]["current_frontier"]),
        }
    )
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


class MustNotRunAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def dispatch(self, request: dict[str, object]) -> dict[str, object]:
        self.calls += 1
        raise AssertionError("adapter must not run while remediation blocks the request")


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
            execution_request=execution(str(manifest.state["next_action"])),
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

    def test_verification_cannot_bypass_pending_remediation(self) -> None:
        decision = coordinate_once(
            remediation_manifest(),
            completion_proposed=True,
            checkpoint_store=object(),
        )
        self.assertEqual(decision.kind, "BLOCK")
        self.assertIn("EXACT_REMEDIATION_ACTION_REQUIRED", decision.reason)

    def test_blockers_without_a_recorded_remediation_fail_closed(self) -> None:
        decision = coordinate_once(
            remediation_manifest(next_action=None),
            execution_request=execution("repair live state for artifact:canonical"),
            checkpoint_store=object(),
        )
        self.assertEqual(decision.kind, "BLOCK")
        self.assertIn("REMEDIATION_ACTION_MISSING", decision.reason)

    def test_direct_dispatch_cannot_bypass_pending_remediation(self) -> None:
        adapter = MustNotRunAdapter()
        manifest = remediation_manifest()
        forged = CoordinationDecision(
            kind="DISPATCH",
            reason="forged",
            request={
                "schema": "execution-request@1",
                "request_id": "forged-request",
                "mission_id": manifest.mission_id,
                "mission_revision": manifest.revision,
                "capability_id": "fixture-writer",
                "action": "write another unrelated artifact",
                "requested_permissions": ["repository:write"],
                "requested_effects": ["intended files"],
                "estimated_costs": ["one feature branch"],
                "authority_check": "authorized",
                "return_point": ReturnPoint(
                    mission_id=manifest.mission_id,
                    revision=manifest.revision,
                    frontier_index=0,
                    label="forged",
                ).to_dict(),
            },
            return_point=ReturnPoint(
                mission_id=manifest.mission_id,
                revision=manifest.revision,
                frontier_index=0,
                label="forged",
            ),
        )
        with self.assertRaisesRegex(CoordinationError, "DECISION_NOT_ISSUED"):
            dispatch_once(manifest, forged, adapter)
        self.assertEqual(adapter.calls, 0)

    def test_lifecycle_transition_cannot_bypass_pending_remediation(self) -> None:
        with self.assertRaisesRegex(TransitionError, "UNRESOLVED_BLOCKERS"):
            apply_event_data(
                remediation_manifest(),
                "begin_verification",
                "mission-steward",
                {},
            )


if __name__ == "__main__":
    unittest.main()
