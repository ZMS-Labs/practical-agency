from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from practical_agency.capability_discovery import CapabilityDescriptor, Persistence
from practical_agency.checkpoint_store import FileCheckpointStore
from practical_agency.coordinator import (
    CoordinationDecision,
    MissionCoordinator,
    normalize_invocation,
)
from practical_agency.manifest_model import MissionManifest
from practical_agency.state_machine import MissionEvent, apply_event


def _manifest(status: str = "active") -> MissionManifest:
    payload = {
        "schema": "mission-manifest@1",
        "mission_id": "mission-001",
        "revision": 2,
        "authority": {
            "operator_ref": "operator:test",
            "instruction": "Create and verify the example artifact.",
            "amendments": [],
            "permissions": ["repository:write"],
            "protected_state": ["unrelated files"],
            "acceptable_costs": ["one feature branch"],
            "escalation_required_for": ["destructive action"],
            "revoked": False,
            "revocation_reason": None,
        },
        "outcome": {
            "desired_state": "The example artifact exists and validates.",
            "completion_proof": ["validator passes"],
            "integrity_guards": ["runtime reads the canonical artifact"],
            "scope_proof": ["diff contains only intended files"],
            "stop_conditions": ["operator revokes authority"],
        },
        "truth": {
            "subject_refs": ["repo:example@rev-1"],
            "verified_facts": [],
            "assumptions": [],
            "contradictions": [],
            "unknowns": [{"claim": "artifact hash unknown", "load_bearing": True}],
        },
        "state": {
            "status": status,
            "completed_actions": [],
            "current_frontier": ["write example"],
            "blockers": [],
            "next_action": "write example",
        },
        "capabilities": {
            "discovered_at": None,
            "available": [],
            "invoked": [],
            "unavailable": [],
            "degraded": [],
        },
        "continuity": {
            "prior_checkpoint": "checkpoint://mission-001/0001",
            "durable_artifacts": [],
            "decisions": [],
            "external_handoffs": [],
            "watch_commissions": [],
        },
        "integrity": {
            "actor_may_self_accept": False,
            "required_gates": [],
            "unresolved_verdicts": [],
            "completion_acceptor": "acceptor:independent",
        },
    }
    return MissionManifest.from_dict(payload)


class _Adapter:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def dispatch(self, request: dict) -> dict:
        self.calls.append(request)
        return {
            "status": "completed",
            "artifact_refs": ["examples/out.txt"],
            "observed_effects": ["examples/out.txt"],
            "external_ref": "receipt:1",
        }


class CoordinatorTests(unittest.TestCase):
    def test_normalize_helix_and_manifest_this(self) -> None:
        self.assertEqual(normalize_invocation("helix it"), "manifest")
        self.assertEqual(normalize_invocation("manifest this"), "manifest")

    def test_routine_checkable_action_can_dispatch(self) -> None:
        manifest = _manifest()
        manifest = MissionManifest.from_dict(
            {
                **manifest.to_dict(),
                "truth": {
                    "subject_refs": [],
                    "verified_facts": [],
                    "assumptions": [],
                    "contradictions": [],
                    "unknowns": [],
                },
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = FileCheckpointStore(Path(tmp))
            adapter = _Adapter()
            coordinator = MissionCoordinator(store=store, adapter=adapter)
            decision, updated = coordinator.step(
                manifest,
                capabilities=[],
                operator_capability_id="filesystem.write",
            )
            self.assertEqual(decision.kind, "DISPATCH")
            self.assertEqual(len(adapter.calls), 1)
            self.assertGreater(updated.revision, manifest.revision)

    def test_load_bearing_unknown_requests_capability(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FileCheckpointStore(Path(tmp))
            coordinator = MissionCoordinator(store=store, adapter=_Adapter())
            caps = [
                CapabilityDescriptor(
                    capability_id="probe",
                    kind="skill",
                    source_ref="skills/probe/SKILL.md",
                    source_sha256="a" * 64,
                    description="Probe unknown claims.",
                    input_contract=None,
                    output_contract=None,
                    authority_required=(),
                    persistence=Persistence.PROMPT,
                    independence="member",
                    availability="available",
                    degradation_reason=None,
                )
            ]
            decision, updated = coordinator.step(
                _manifest(),
                capabilities=caps,
                operator_capability_id=None,
            )
            self.assertEqual(decision.kind, "REQUEST_CAPABILITY")
            self.assertIsNotNone(decision.return_point)
            self.assertEqual(decision.return_point.label, "write example")
            self.assertEqual(updated.state["status"], "active")

    def test_unavailable_capability_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FileCheckpointStore(Path(tmp))
            coordinator = MissionCoordinator(store=store, adapter=_Adapter())
            caps = [
                CapabilityDescriptor(
                    capability_id="missing",
                    kind="skill",
                    source_ref="skills/missing/SKILL.md",
                    source_sha256="b" * 64,
                    description="",
                    input_contract=None,
                    output_contract=None,
                    authority_required=(),
                    persistence=Persistence.PROMPT,
                    independence="member",
                    availability="unavailable",
                    degradation_reason="EMPTY_DESCRIPTION",
                )
            ]
            decision, updated = coordinator.step(
                _manifest(),
                capabilities=caps,
                operator_capability_id="missing",
            )
            self.assertEqual(decision.kind, "BLOCK")
            self.assertEqual(updated.state["status"], "blocked")

    def test_no_authority_means_no_dispatch(self) -> None:
        draft = apply_event(
            MissionManifest.from_dict(
                {
                    **_manifest("draft").to_dict(),
                    "revision": 1,
                    "state": {
                        "status": "draft",
                        "completed_actions": [],
                        "current_frontier": ["obtain approval"],
                        "blockers": [],
                        "next_action": "obtain approval",
                    },
                    "continuity": {
                        "prior_checkpoint": None,
                        "durable_artifacts": [],
                        "decisions": [],
                        "external_handoffs": [],
                        "watch_commissions": [],
                    },
                    "truth": {
                        "subject_refs": [],
                        "verified_facts": [],
                        "assumptions": [],
                        "contradictions": [],
                        "unknowns": [],
                    },
                }
            ),
            MissionEvent(kind="revoke", actor_ref="operator:test", detail={"reason": "stop"}),
        )
        with tempfile.TemporaryDirectory() as tmp:
            coordinator = MissionCoordinator(
                store=FileCheckpointStore(Path(tmp)),
                adapter=_Adapter(),
            )
            decision, _updated = coordinator.step(
                draft,
                capabilities=[],
                operator_capability_id="filesystem.write",
            )
            self.assertEqual(decision.kind, "BLOCK")
            self.assertIn("AUTHORITY", decision.reason)

    def test_completion_proposal_enters_verifying(self) -> None:
        manifest = MissionManifest.from_dict(
            {
                **_manifest().to_dict(),
                "truth": {
                    "subject_refs": [],
                    "verified_facts": [],
                    "assumptions": [],
                    "contradictions": [],
                    "unknowns": [],
                },
                "continuity": {
                    "prior_checkpoint": "checkpoint://mission-001/0001",
                    "durable_artifacts": ["validator passes"],
                    "decisions": [],
                    "external_handoffs": [],
                    "watch_commissions": [],
                },
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            coordinator = MissionCoordinator(
                store=FileCheckpointStore(Path(tmp)),
                adapter=_Adapter(),
            )
            decision, updated = coordinator.step(
                manifest,
                capabilities=[],
                operator_capability_id=None,
                propose_completion=True,
            )
            self.assertEqual(decision.kind, "VERIFY")
            self.assertEqual(updated.state["status"], "verifying")

    def test_self_accept_rejected(self) -> None:
        verifying = apply_event(
            _manifest(),
            MissionEvent(
                kind="begin_verification",
                actor_ref="mission-steward",
                artifact_refs=["validator passes"],
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            coordinator = MissionCoordinator(
                store=FileCheckpointStore(Path(tmp)),
                adapter=_Adapter(),
            )
            with self.assertRaisesRegex(Exception, "INDEPENDENT_ACCEPTANCE_REQUIRED"):
                coordinator.accept(
                    verifying,
                    actor_ref="mission-steward",
                    verdict="PASS",
                    artifact_refs=["validator passes"],
                )


if __name__ == "__main__":
    unittest.main()
