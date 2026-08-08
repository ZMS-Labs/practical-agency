from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from practical_agency.capability_discovery import CapabilityDescriptor, Persistence
from practical_agency.checkpoint_store import FileCheckpointStore
from practical_agency.coordinator import (
    CoordinationError,
    apply_capability_result,
    coordinate_once,
    dispatch_once,
    normalize_invocation_intent,
)
from practical_agency.manifest_model import MissionManifest
from practical_agency.state_machine import MissionEvent, apply_event
from tests.helpers import clone_payload


class MemoryAdapter:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(request)
        return {
            "schema": "execution-receipt@1",
            "request_id": request["request_id"],
            "mission_id": request["mission_id"],
            "mission_revision": request["mission_revision"],
            "adapter_ref": "fixture://memory-adapter",
            "status": "completed",
            "artifact_refs": ["artifact:one"],
            "observed_effects": [],
            "external_receipt_ref": "fixture://execution/one",
            "coverage_limits": ["in-memory fixture only"],
        }


def capability(availability: str = "available") -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability_id="fixture",
        kind="skill",
        source_ref="fixture://skill",
        source_sha256="a" * 64,
        description="Use for the bounded fixture question.",
        input_contract=None,
        output_contract=None,
        authority_required=("repository:write",),
        persistence=Persistence.SESSION,
        independence="actor",
        availability=availability,
        degradation_reason=None if availability == "available" else "NOT_LOADED",
    )


class CoordinatorTests(unittest.TestCase):
    def active(self) -> MissionManifest:
        payload = clone_payload()
        payload["revision"] = 2
        payload["state"]["status"] = "active"
        payload["continuity"]["prior_checkpoint"] = "checkpoint:1"
        return MissionManifest.from_dict(payload)

    def test_routine_direct_action_does_not_manufacture_epistemic_request(self) -> None:
        decision = coordinate_once(
            self.active(),
            execution_request={
                "capability_id": "fixture",
                "requested_permissions": ["repository:write"],
                "requested_effects": ["intended files"],
                "estimated_costs": ["one feature branch"],
                "action": "write one artifact",
            },
            checkpoint_store=object(),
        )
        self.assertEqual(decision.kind, "DISPATCH")
        self.assertIn("request_id", decision.request)

    def test_unresolved_claim_requests_capability_and_preserves_return_point(self) -> None:
        decision = coordinate_once(
            self.active(),
            unresolved_condition="Which revision bears load?",
            selected_capability=capability(),
            frontier_index=3,
            checkpoint_store=object(),
        )
        self.assertEqual(decision.kind, "REQUEST_CAPABILITY")
        self.assertEqual(decision.return_point.frontier_index, 3)
        self.assertEqual(decision.request["capability_id"], "fixture")

    def test_unavailable_capability_becomes_visible_block(self) -> None:
        decision = coordinate_once(
            self.active(),
            unresolved_condition="Need evidence",
            selected_capability=capability("unavailable"),
            checkpoint_store=object(),
        )
        self.assertEqual(decision.kind, "BLOCK")
        self.assertIn("NOT_LOADED", decision.reason)

    def test_one_decision_dispatches_at_most_once(self) -> None:
        adapter = MemoryAdapter()
        decision = coordinate_once(
            self.active(),
            execution_request={
                "capability_id": "fixture",
                "requested_permissions": ["repository:write"],
                "requested_effects": ["intended files"],
                "estimated_costs": ["one feature branch"],
                "action": "write",
            },
            checkpoint_store=object(),
        )
        receipt = dispatch_once(self.active(), decision, adapter)
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(receipt["request_id"], decision.request["request_id"])

    def test_no_authority_means_no_dispatch(self) -> None:
        decision = coordinate_once(
            self.active(),
            execution_request={
                "capability_id": "fixture",
                "requested_permissions": ["network:write"],
                "requested_effects": [],
                "estimated_costs": [],
                "action": "write network",
            },
            checkpoint_store=object(),
        )
        self.assertEqual(decision.kind, "BLOCK")
        self.assertIn("PERMISSION_NOT_GRANTED", decision.reason)

    def test_missing_store_is_visible_session_only_degradation(self) -> None:
        decision = coordinate_once(
            self.active(),
            execution_request={
                "capability_id": "fixture",
                "requested_permissions": ["repository:write"],
                "requested_effects": ["intended files"],
                "estimated_costs": ["one feature branch"],
                "action": "write",
            },
            checkpoint_store=None,
        )
        self.assertEqual(decision.kind, "DISPATCH")
        self.assertIn("SESSION_BOUNDED", decision.reason)

    def test_completion_proposal_enters_verify_not_complete(self) -> None:
        decision = coordinate_once(self.active(), completion_proposed=True, checkpoint_store=object())
        self.assertEqual(decision.kind, "VERIFY")

    def test_capability_result_returns_to_exact_point(self) -> None:
        decision = coordinate_once(
            self.active(),
            unresolved_condition="Need evidence",
            selected_capability=capability(),
            frontier_index=2,
            checkpoint_store=object(),
        )
        updated = apply_capability_result(
            self.active(),
            decision,
            {
                "schema": "capability-result@1",
                "request_id": decision.request["request_id"],
                "status": "completed",
                "artifact_refs": ["artifact:x"],
                "observed_effects": [],
                "returned_control_point": decision.return_point.to_dict(),
                "coverage_limits": [],
            },
        )
        self.assertEqual(updated.state["next_action"], decision.return_point.label)
        self.assertIn("artifact:x", updated.continuity["durable_artifacts"])

    def test_no_go_result_is_not_rewritten(self) -> None:
        decision = coordinate_once(
            self.active(), unresolved_condition="Gate", selected_capability=capability(), checkpoint_store=object()
        )
        updated = apply_capability_result(
            self.active(),
            decision,
            {
                "schema": "capability-result@1",
                "request_id": decision.request["request_id"],
                "status": "completed",
                "verdict": "NO-GO",
                "artifact_refs": [],
                "observed_effects": [],
                "returned_control_point": decision.return_point.to_dict(),
                "coverage_limits": [],
            },
        )
        self.assertEqual(updated.state["status"], "blocked")
        self.assertIn("NO-GO", updated.integrity["unresolved_verdicts"])

    def test_unknown_capability_result_status_is_rejected(self) -> None:
        decision = coordinate_once(
            self.active(), unresolved_condition="Gate", selected_capability=capability(), checkpoint_store=object()
        )
        with self.assertRaisesRegex(CoordinationError, "INVALID_CAPABILITY_RESULT:status"):
            apply_capability_result(
                self.active(),
                decision,
                {
                    "schema": "capability-result@1",
                    "request_id": decision.request["request_id"],
                    "status": "banana",
                    "artifact_refs": [],
                    "observed_effects": [],
                    "returned_control_point": decision.return_point.to_dict(),
                    "coverage_limits": [],
                },
            )

    def test_capability_result_request_id_must_match(self) -> None:
        decision = coordinate_once(
            self.active(), unresolved_condition="Gate", selected_capability=capability(), checkpoint_store=object()
        )
        with self.assertRaisesRegex(CoordinationError, "CAPABILITY_RESULT_REQUEST_MISMATCH"):
            apply_capability_result(
                self.active(),
                decision,
                {
                    "schema": "capability-result@1",
                    "request_id": "other-request",
                    "status": "completed",
                    "artifact_refs": [],
                    "observed_effects": [],
                    "returned_control_point": decision.return_point.to_dict(),
                    "coverage_limits": [],
                },
            )

    def test_wrong_return_point_is_rejected(self) -> None:
        decision = coordinate_once(
            self.active(), unresolved_condition="Gate", selected_capability=capability(), checkpoint_store=object()
        )
        with self.assertRaisesRegex(CoordinationError, "RETURN_POINT_MISMATCH"):
            apply_capability_result(
                self.active(),
                decision,
                {
                    "schema": "capability-result@1",
                    "request_id": decision.request["request_id"],
                    "status": "completed",
                    "artifact_refs": [],
                    "observed_effects": [],
                    "returned_control_point": {"mission_id": "other"},
                    "coverage_limits": [],
                },
            )

    def test_dispatch_blocked_without_applied_frontier_when_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = FileCheckpointStore(Path(temp))
            active = self.active()
            decision = coordinate_once(
                active,
                execution_request={
                    "capability_id": "fixture",
                    "requested_permissions": ["repository:write"],
                    "requested_effects": ["intended files"],
                    "estimated_costs": ["one feature branch"],
                    "action": "write one artifact",
                },
                checkpoint_store=store,
                require_applied_frontier=True,
            )
            self.assertEqual(decision.kind, "BLOCK")
            self.assertIn("MISSION_OS_APPLY_REQUIRED", decision.reason)

    def test_dispatch_allowed_after_frontier_apply_at_current_revision(self) -> None:
        manifest = apply_event(
            self.active(),
            MissionEvent(
                "apply_mission_os",
                "mission-steward",
                {
                    "proposal_kind": "frontier_patch",
                    "labels": ["write authorized artifact", "verify receipt"],
                },
            ),
        )
        decision = coordinate_once(
            manifest,
            execution_request={
                "capability_id": "fixture",
                "requested_permissions": ["repository:write"],
                "requested_effects": ["intended files"],
                "estimated_costs": ["one feature branch"],
                "action": "write one artifact",
            },
            checkpoint_store=object(),
            require_applied_frontier=True,
        )
        self.assertEqual(decision.kind, "DISPATCH")

    def test_dispatch_allowed_after_frontier_apply_then_defer(self) -> None:
        """Defer bumps revision; prior frontier apply still satisfies the gate."""
        manifest = apply_event(
            self.active(),
            MissionEvent(
                "apply_mission_os",
                "mission-steward",
                {
                    "proposal_kind": "frontier_patch",
                    "labels": ["write authorized artifact"],
                },
            ),
        )
        interest = {
            "schema": "deferred-interest@1",
            "mission_id": "mission-001",
            "summary": "optional docs polish",
            "criticality": "low",
            "why_not_now": "not required for completion proof",
            "suggested_next": None,
            "subject_refs": [],
            "created_at_revision": manifest.revision,
            "status": "open",
        }
        after_defer = apply_event(
            manifest,
            MissionEvent(
                "apply_mission_os",
                "mission-steward",
                {"proposal_kind": "defer", "interest": interest},
            ),
        )
        self.assertGreater(after_defer.revision, manifest.revision)
        decision = coordinate_once(
            after_defer,
            execution_request={
                "capability_id": "fixture",
                "requested_permissions": ["repository:write"],
                "requested_effects": ["intended files"],
                "estimated_costs": ["one feature branch"],
                "action": "write one artifact",
            },
            checkpoint_store=object(),
            require_applied_frontier=True,
        )
        self.assertEqual(decision.kind, "DISPATCH")

    def test_stale_return_point_after_replan_mismatches(self) -> None:
        manifest = self.active()
        manifest = MissionManifest.from_dict(
            {
                **manifest.to_dict(),
                "state": {
                    **manifest.state,
                    "current_frontier": ["label-a", "step-two"],
                    "next_action": "label-a",
                },
            }
        )
        decision = coordinate_once(
            manifest,
            unresolved_condition="Bounded question",
            selected_capability=capability(),
            frontier_index=0,
            checkpoint_store=object(),
        )
        self.assertEqual(decision.return_point.label, "label-a")
        replanned = apply_event(
            manifest,
            MissionEvent(
                "apply_mission_os",
                "mission-steward",
                {
                    "proposal_kind": "replan_slice",
                    "labels": ["label-b", "step-two"],
                    "contradiction_refs": ["truth:example"],
                },
            ),
        )
        self.assertEqual(replanned.state["current_frontier"][0], "label-b")
        with self.assertRaisesRegex(CoordinationError, "RETURN_POINT_MISMATCH"):
            apply_capability_result(
                replanned,
                decision,
                {
                    "schema": "capability-result@1",
                    "request_id": decision.request["request_id"],
                    "status": "completed",
                    "artifact_refs": [],
                    "observed_effects": [],
                    "returned_control_point": decision.return_point.to_dict(),
                    "coverage_limits": [],
                },
            )

    def test_helix_and_manifest_phrases_normalize_to_same_intent(self) -> None:
        self.assertEqual(normalize_invocation_intent("helix it"), "manifest")
        self.assertEqual(normalize_invocation_intent("manifest this"), "manifest")


if __name__ == "__main__":
    unittest.main()
