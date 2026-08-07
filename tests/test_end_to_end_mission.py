from __future__ import annotations

import dataclasses
import tempfile
import unittest
from pathlib import Path

from practical_agency.capability_discovery import discover_capabilities
from practical_agency.checkpoint_store import FileCheckpointStore, reconcile_observations
from practical_agency.coordinator import MissionCoordinator
from practical_agency.manifest_model import MissionManifest
from practical_agency.state_machine import MissionEvent, TransitionError, apply_event
from practical_agency.validation import validate_manifest_dict


class _Adapter:
    def __init__(self) -> None:
        self.writes = 0

    def dispatch(self, request: dict) -> dict:
        self.writes += 1
        return {
            "status": "completed",
            "artifact_refs": ["examples/out.txt", "validator passes"],
            "observed_effects": ["examples/out.txt"],
            "external_ref": f"receipt:{self.writes}",
        }


INSTRUCTION = "Create and verify the example artifact."


def _new_draft() -> MissionManifest:
    payload = {
        "schema": "mission-manifest@1",
        "mission_id": "mission-e2e",
        "revision": 1,
        "authority": {
            "operator_ref": "operator:test",
            "instruction": INSTRUCTION,
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
            "subject_refs": ["artifact:examples/out.txt"],
            "verified_facts": [
                {"subject_ref": "artifact:examples/out.txt", "value": "missing"}
            ],
            "assumptions": [],
            "contradictions": [],
            "unknowns": [],
        },
        "state": {
            "status": "draft",
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
            "prior_checkpoint": None,
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
    assert validate_manifest_dict(payload) == []
    return MissionManifest.from_dict(payload)


class EndToEndMissionTests(unittest.TestCase):
    def test_resumable_independently_accepted_mission(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = FileCheckpointStore(root / "checkpoints")
            skills = root / "skills"
            skill = skills / "fixture-writer"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: fixture-writer\ndescription: Write the example artifact.\n---\n\n# fixture-writer\n",
                encoding="utf-8",
            )

            draft = _new_draft()
            store.save(draft)
            active = apply_event(
                draft, MissionEvent(kind="approve", actor_ref="operator:test")
            )
            store.save(active)

            caps = discover_capabilities([skills])
            self.assertEqual([cap.capability_id for cap in caps], ["fixture-writer"])

            adapter = _Adapter()
            coordinator = MissionCoordinator(store=store, adapter=adapter)
            decision, advanced = coordinator.step(
                active,
                capabilities=caps,
                operator_capability_id="fixture-writer",
            )
            self.assertEqual(decision.kind, "DISPATCH")
            self.assertEqual(adapter.writes, 1)
            revision_n = advanced.revision
            store.save(advanced)

            # Discard in-memory objects and reload.
            del draft, active, advanced, coordinator, adapter
            loaded, receipt = store.load_latest("mission-e2e")
            self.assertEqual(loaded.revision, revision_n)
            self.assertEqual(loaded.authority["instruction"], INSTRUCTION)
            self.assertTrue(receipt.sha256)

            findings = reconcile_observations(
                loaded, {"artifact:examples/out.txt": "present"}
            )
            self.assertTrue(any(item.classification == "CONTRADICTED" for item in findings))
            reopened = apply_event(
                loaded,
                MissionEvent(
                    kind="record_observation",
                    actor_ref="mission-steward",
                    detail={
                        "reconciliation": [
                            dataclasses.asdict(finding) for finding in findings
                        ]
                    },
                    artifact_refs=["examples/out.txt"],
                ),
            )
            adapter = _Adapter()
            coordinator = MissionCoordinator(store=store, adapter=adapter)
            _decision, corrected = coordinator.step(
                reopened,
                capabilities=caps,
                operator_capability_id="fixture-writer",
            )
            self.assertEqual(adapter.writes, 1)

            verifying_decision, verifying = coordinator.step(
                corrected,
                capabilities=caps,
                propose_completion=True,
            )
            self.assertEqual(verifying_decision.kind, "VERIFY")
            self.assertEqual(verifying.state["status"], "verifying")

            with self.assertRaisesRegex(TransitionError, "INDEPENDENT_ACCEPTANCE_REQUIRED"):
                coordinator.accept(
                    verifying,
                    actor_ref="mission-steward",
                    verdict="PASS",
                    artifact_refs=["validator passes"],
                )

            completed = coordinator.accept(
                verifying,
                actor_ref="acceptor:independent",
                verdict="PASS",
                artifact_refs=["validator passes"],
            )
            self.assertEqual(completed.state["status"], "completed")
            final, _final_receipt = store.load_latest("mission-e2e")
            self.assertEqual(final.state["status"], "completed")
            self.assertEqual(final.authority["instruction"], INSTRUCTION)


if __name__ == "__main__":
    unittest.main()
