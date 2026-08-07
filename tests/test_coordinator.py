from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping

from practical_agency.authority import ActionRequest
from practical_agency.capability_discovery import CapabilityDescriptor, Persistence
from practical_agency.checkpoint_store import CheckpointStore
from practical_agency.coordinator import (
    CapabilityResult,
    MissionCoordinator,
    ReturnPoint,
    normalize_invocation,
)
from practical_agency.manifest_model import MissionManifest
from tests.helpers import active_payload


def capability(*, availability: str = "available", authority_required: tuple[str, ...] = ()) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability_id="cap:test",
        kind="skill",
        source_ref="fixture://cap/test",
        source_sha256="1" * 64,
        description="Use for the bounded test condition.",
        input_contract="capability-request@1",
        output_contract="capability-result@1",
        authority_required=authority_required,
        persistence=Persistence.PROMPT,
        independence="either",
        availability=availability,
        degradation_reason=None if availability == "available" else "fixture unavailable",
    )


def action(authority_ref: str | None = "approval:test") -> ActionRequest:
    return ActionRequest(
        action_id="write-example",
        description="write example artifact",
        required_permissions=("repository:write",),
        touches=("examples/output.json",),
        costs=("one feature branch",),
        consequential=False,
        irreversible=False,
        authority_ref=authority_ref,
        stop_condition="stop on adapter failure",
    )


class FakeAdapter:
    adapter_ref = "fixture://adapter"

    def __init__(self) -> None:
        self.calls: list[Mapping[str, Any]] = []

    def dispatch(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append(request)
        return {
            "schema": "execution-receipt@1",
            "request_id": request["request_id"],
            "adapter_ref": self.adapter_ref,
            "status": "completed",
            "observed_effects": [{"kind": "file", "sha256": "2" * 64}],
            "artifact_refs": ["artifact://output"],
            "recorded_at": "2026-08-07T17:30:00Z",
            "coverage_limits": ["fixture adapter"],
        }


class CoordinatorTests(unittest.TestCase):
    def manifest(self) -> MissionManifest:
        return MissionManifest.from_dict(active_payload())

    def test_routine_directly_checkable_action_dispatches_without_epistemic_ceremony(self) -> None:
        decision = MissionCoordinator().decide(self.manifest(), execution_request=action())
        self.assertEqual(decision.kind, "DISPATCH")
        self.assertIsNone(decision.return_point)

    def test_unresolved_condition_produces_bounded_capability_request(self) -> None:
        decision = MissionCoordinator().decide(
            self.manifest(),
            capabilities=[capability()],
            named_condition="Determine whether the proof bundle is complete.",
            requested_capability_id="cap:test",
        )
        self.assertEqual(decision.kind, "REQUEST_CAPABILITY")
        assert decision.request is not None
        self.assertEqual(decision.request["capability_id"], "cap:test")
        self.assertEqual(decision.request["bounded_request"], "Determine whether the proof bundle is complete.")
        self.assertIsNotNone(decision.return_point)

    def test_capability_result_restores_exact_return_point(self) -> None:
        coordinator = MissionCoordinator()
        manifest = self.manifest()
        decision = coordinator.decide(
            manifest,
            capabilities=[capability()],
            named_condition="Check the condition.",
            requested_capability_id="cap:test",
        )
        assert decision.request is not None and decision.return_point is not None
        result = CapabilityResult(
            request_id=decision.request["request_id"],
            status="completed",
            artifact_refs=("artifact://answer",),
            observed_effects=({"verdict": "PASS"},),
            returned_control_point=decision.return_point,
            coverage_limits=(),
        )
        updated = coordinator.apply_capability_result(manifest, decision, result)
        self.assertEqual(updated.state["next_action"], manifest.state["next_action"])
        self.assertEqual(updated.capabilities["invoked"][-1]["status"], "completed")

    def test_wrong_return_point_is_rejected(self) -> None:
        coordinator = MissionCoordinator()
        manifest = self.manifest()
        decision = coordinator.decide(
            manifest,
            capabilities=[capability()],
            named_condition="Check.",
            requested_capability_id="cap:test",
        )
        assert decision.request is not None and decision.return_point is not None
        result = CapabilityResult(
            request_id=decision.request["request_id"],
            status="completed",
            artifact_refs=(),
            observed_effects=(),
            returned_control_point=ReturnPoint(manifest.mission_id, 999, 0, "wrong"),
            coverage_limits=(),
        )
        with self.assertRaisesRegex(ValueError, "RETURN_POINT_MISMATCH"):
            coordinator.apply_capability_result(manifest, decision, result)

    def test_unavailable_capability_is_visible_block(self) -> None:
        decision = MissionCoordinator().decide(
            self.manifest(),
            capabilities=[capability(availability="unavailable")],
            named_condition="Check.",
            requested_capability_id="cap:test",
        )
        self.assertEqual(decision.kind, "BLOCK")
        self.assertIn("unavailable", decision.reason)

    def test_one_dispatch_call_per_coordination_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter = FakeAdapter()
            coordinator = MissionCoordinator(
                checkpoint_store=CheckpointStore(Path(tmp)),
                clock=lambda: "2026-08-07T17:45:00Z",
            )
            updated, receipt = coordinator.dispatch_one(
                self.manifest(), action(), adapter=adapter, actor_ref="steward:test"
            )
            self.assertEqual(len(adapter.calls), 1)
            self.assertEqual(receipt["status"], "completed")
            self.assertEqual(updated.revision, 3)

    def test_missing_authority_blocks_without_adapter_call(self) -> None:
        adapter = FakeAdapter()
        updated, receipt = MissionCoordinator(clock=lambda: "2026-08-07T17:46:00Z").dispatch_one(
            self.manifest(), action(authority_ref=None), adapter=adapter, actor_ref="steward:test"
        )
        self.assertEqual(adapter.calls, [])
        self.assertEqual(receipt["status"], "blocked")
        self.assertEqual(receipt["recorded_at"], "2026-08-07T17:46:00Z")
        self.assertEqual(updated.state["status"], "blocked")

    def test_malformed_execution_receipt_is_rejected_fail_closed(self) -> None:
        class MalformedAdapter(FakeAdapter):
            def dispatch(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
                receipt = dict(super().dispatch(request))
                receipt["recorded_at"] = None
                receipt["artifact_refs"] = "artifact://not-a-list"
                return receipt

        with self.assertRaisesRegex(ValueError, "INVALID_EXECUTION_RECEIPT"):
            MissionCoordinator().dispatch_one(
                self.manifest(),
                action(),
                adapter=MalformedAdapter(),
                actor_ref="steward:test",
            )

    def test_no_checkpoint_store_is_visible_session_bounded_degradation(self) -> None:
        adapter = FakeAdapter()
        updated, receipt = MissionCoordinator().dispatch_one(
            self.manifest(), action(), adapter=adapter, actor_ref="steward:test"
        )
        self.assertIn("SESSION_BOUNDED_NO_CHECKPOINT_STORE", receipt["coverage_limits"])
        self.assertTrue(any(item.get("code") == "SESSION_BOUNDED_NO_CHECKPOINT_STORE" for item in updated.capabilities["degraded"]))

    def test_completion_proposal_enters_verifying_not_completed(self) -> None:
        verifying = MissionCoordinator().propose_verification(
            self.manifest(), actor_ref="steward:test", proof_bundle_ref="proof://bundle"
        )
        self.assertEqual(verifying.state["status"], "verifying")
        self.assertIsNone(verifying.integrity["completion_acceptor"])

    def test_no_go_verdict_is_preserved_and_blocks(self) -> None:
        coordinator = MissionCoordinator()
        manifest = self.manifest()
        decision = coordinator.decide(
            manifest,
            capabilities=[capability()],
            named_condition="Review frozen subject.",
            requested_capability_id="cap:test",
        )
        assert decision.request is not None and decision.return_point is not None
        result = CapabilityResult(
            request_id=decision.request["request_id"],
            status="completed",
            artifact_refs=("artifact://verdict",),
            observed_effects=({"verdict": "NO-GO"},),
            returned_control_point=decision.return_point,
            coverage_limits=(),
        )
        updated = coordinator.apply_capability_result(manifest, decision, result)
        self.assertEqual(updated.state["status"], "blocked")
        self.assertEqual(updated.capabilities["invoked"][-1]["observed_effects"][0]["verdict"], "NO-GO")

    def test_capability_authority_requirement_is_enforced_and_receipted(self) -> None:
        manifest = self.manifest()
        descriptor = capability(authority_required=("secrets:read",))
        denied = MissionCoordinator().decide(
            manifest,
            capabilities=[descriptor],
            named_condition="Read the bounded secret.",
            requested_capability_id="cap:test",
            capability_authority_ref="approval://capability",
        )
        self.assertEqual(denied.kind, "BLOCK")
        self.assertIn("CAPABILITY_AUTHORITY_NOT_GRANTED", denied.reason)

        payload = manifest.to_dict()
        payload["authority"]["permissions"].append("secrets:read")
        authorized_manifest = MissionManifest.from_dict(payload)
        missing_receipt = MissionCoordinator().decide(
            authorized_manifest,
            capabilities=[descriptor],
            named_condition="Read the bounded secret.",
            requested_capability_id="cap:test",
        )
        self.assertEqual(missing_receipt.kind, "BLOCK")
        self.assertIn("CAPABILITY_AUTHORITY_RECEIPT_REQUIRED", missing_receipt.reason)

        allowed = MissionCoordinator().decide(
            authorized_manifest,
            capabilities=[descriptor],
            named_condition="Read the bounded secret.",
            requested_capability_id="cap:test",
            capability_authority_ref="approval://capability",
        )
        self.assertEqual(allowed.kind, "REQUEST_CAPABILITY")
        assert allowed.request is not None
        self.assertEqual(allowed.request["authority_ref"], "approval://capability")

    def test_helix_and_manifest_normalize_to_same_intent(self) -> None:
        self.assertEqual(normalize_invocation("helix it"), "manifest")
        self.assertEqual(normalize_invocation("manifest this"), "manifest")

    def test_stale_capability_result_cannot_apply_to_newer_revision(self) -> None:
        coordinator = MissionCoordinator()
        manifest = self.manifest()
        decision = coordinator.decide(
            manifest,
            capabilities=[capability()],
            named_condition="Check the frozen revision.",
            requested_capability_id="cap:test",
        )
        assert decision.request is not None and decision.return_point is not None
        advanced_payload = manifest.to_dict()
        advanced_payload["revision"] = manifest.revision + 1
        advanced = MissionManifest.from_dict(advanced_payload)
        result = CapabilityResult(
            request_id=decision.request["request_id"],
            status="completed",
            artifact_refs=(),
            observed_effects=(),
            returned_control_point=decision.return_point,
            coverage_limits=(),
        )
        with self.assertRaisesRegex(ValueError, "STALE_CAPABILITY_RESULT"):
            coordinator.apply_capability_result(advanced, decision, result)

    def test_malformed_capability_result_is_rejected_fail_closed(self) -> None:
        coordinator = MissionCoordinator()
        manifest = self.manifest()
        decision = coordinator.decide(
            manifest,
            capabilities=[capability()],
            named_condition="Check the result shape.",
            requested_capability_id="cap:test",
        )
        assert decision.request is not None and decision.return_point is not None
        result = CapabilityResult(
            request_id=decision.request["request_id"],
            status="completed",
            artifact_refs=(42,),  # type: ignore[arg-type]
            observed_effects=("not-an-object",),  # type: ignore[arg-type]
            returned_control_point=decision.return_point,
            coverage_limits=(),
        )
        with self.assertRaisesRegex(ValueError, "INVALID_CAPABILITY_RESULT"):
            coordinator.apply_capability_result(manifest, decision, result)

    def test_adapter_exception_becomes_checkpointed_failed_receipt(self) -> None:
        class ExplodingAdapter(FakeAdapter):
            def dispatch(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
                self.calls.append(request)
                raise RuntimeError("fixture explosion")

        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(Path(tmp))
            coordinator = MissionCoordinator(
                checkpoint_store=store, clock=lambda: "2026-08-07T18:00:00Z"
            )
            updated, receipt = coordinator.dispatch_one(
                self.manifest(), action(), adapter=ExplodingAdapter(), actor_ref="steward:test"
            )
            self.assertEqual(updated.state["status"], "blocked")
            self.assertEqual(receipt["status"], "failed")
            self.assertIn("ADAPTER_EXCEPTION", receipt["coverage_limits"][0])
            loaded, _ = store.load_latest(updated.mission_id)
            self.assertEqual(loaded.revision, updated.revision)

    def test_authority_denial_is_checkpointed_when_store_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(Path(tmp))
            updated, receipt = MissionCoordinator(
                checkpoint_store=store, clock=lambda: "2026-08-07T18:01:00Z"
            ).dispatch_one(
                self.manifest(),
                action(authority_ref=None),
                adapter=FakeAdapter(),
                actor_ref="steward:test",
            )
            self.assertEqual(receipt["status"], "blocked")
            loaded, _ = store.load_latest(updated.mission_id)
            self.assertEqual(loaded.revision, updated.revision)

    def test_paused_mission_dispatch_is_denied_without_state_rewrite(self) -> None:
        payload = active_payload()
        payload["state"]["status"] = "paused"
        payload["state"]["blockers"] = [{"kind": "pause", "reason": "operator pause"}]
        manifest = MissionManifest.from_dict(payload)
        adapter = FakeAdapter()
        updated, receipt = MissionCoordinator(
            clock=lambda: "2026-08-07T18:02:00Z"
        ).dispatch_one(
            manifest, action(), adapter=adapter, actor_ref="steward:test"
        )
        self.assertEqual(adapter.calls, [])
        self.assertEqual(receipt["status"], "blocked")
        self.assertEqual(updated.revision, manifest.revision)
        self.assertEqual(updated.state["status"], "paused")


if __name__ == "__main__":
    unittest.main()
