from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping

from practical_agency.authority import ActionRequest
from practical_agency.capability_discovery import FileSystemSkillProvider
from practical_agency.checkpoint_store import CheckpointStore
from practical_agency.coordinator import CapabilityResult, MissionCoordinator
from practical_agency.manifest_model import MissionManifest
from practical_agency.state_machine import (
    TransitionError,
    record_reconciliation_observation,
    reopen_for_contradiction,
    transition,
)
from tests.helpers import minimal_payload


class ArtifactAdapter:
    adapter_ref = "fixture://artifact-adapter"

    def __init__(self, path: Path, contents: list[str]) -> None:
        self.path = path
        self.contents = list(contents)
        self.calls = 0

    def dispatch(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        content = self.contents[self.calls]
        self.calls += 1
        self.path.write_text(content, encoding="utf-8")
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        return {
            "schema": "execution-receipt@1",
            "request_id": request["request_id"],
            "adapter_ref": self.adapter_ref,
            "status": "completed",
            "observed_effects": [
                {"kind": "file-sha256", "path": self.path.name, "sha256": digest}
            ],
            "artifact_refs": [f"artifact://{self.path.name}@sha256:{digest}"],
            "recorded_at": f"2026-08-07T18:0{self.calls}:00Z",
            "coverage_limits": ["isolated in-process fixture"],
        }


def action(action_id: str, description: str) -> ActionRequest:
    return ActionRequest(
        action_id=action_id,
        description=description,
        required_permissions=("repository:write",),
        touches=("examples/output.txt",),
        costs=("one feature branch",),
        consequential=False,
        irreversible=False,
        authority_ref="approval://mission-001",
        stop_condition="stop on adapter failure",
    )


class EndToEndMissionTests(unittest.TestCase):
    def test_resumable_mission_reopens_and_completes_independently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = CheckpointStore(root / "checkpoints")
            artifact = root / "output.txt"
            original_instruction = "Create and verify the example artifact."

            payload = minimal_payload()
            payload["authority"]["instruction"] = original_instruction
            draft = MissionManifest.from_dict(payload)
            active = transition(
                draft,
                "active",
                actor_ref="operator:test",
                evidence_ref="approval://mission-001",
                reason="mission approved",
            )
            store.save(active, events=[{"kind": "mission-approved"}])

            skill_root = root / "capabilities"
            skill = skill_root / "fixture-review"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: fixture-review\ndescription: Use to review the isolated fixture.\n---\n# Fixture\n",
                encoding="utf-8",
            )
            capabilities = FileSystemSkillProvider(skill_root).discover()
            self.assertEqual([item.capability_id for item in capabilities], ["fixture-review"])

            coordinator = MissionCoordinator(
                checkpoint_store=store,
                clock=lambda: "2026-08-07T18:00:00Z",
            )
            decision = coordinator.decide(
                active,
                capabilities=capabilities,
                named_condition="Confirm the fixture action is bounded and reversible.",
                requested_capability_id="fixture-review",
            )
            assert decision.request is not None and decision.return_point is not None
            reviewed = coordinator.apply_capability_result(
                active,
                decision,
                CapabilityResult(
                    request_id=decision.request["request_id"],
                    status="completed",
                    artifact_refs=("fixture://review/pass",),
                    observed_effects=({"verdict": "PASS"},),
                    returned_control_point=decision.return_point,
                    coverage_limits=("isolated fixture",),
                ),
            )
            store.save(reviewed, events=[{"kind": "capability-return"}])

            adapter = ArtifactAdapter(artifact, ["version-one\n", "corrected\n"])
            first, first_receipt = coordinator.dispatch_one(
                reviewed,
                action("create", "create example artifact"),
                adapter=adapter,
                actor_ref="steward:test",
            )
            expected_first_hash = hashlib.sha256(b"version-one\n").hexdigest()
            self.assertEqual(first_receipt["observed_effects"][0]["sha256"], expected_first_hash)

            # Simulate a new process: discard all mission objects and reload only durable bytes.
            del draft, active, reviewed, first, decision, coordinator
            resumed, resumed_checkpoint = store.load_latest("mission-001")
            self.assertEqual(resumed_checkpoint.revision, resumed.revision)
            self.assertEqual(resumed.authority["instruction"], original_instruction)

            artifact.write_text("contradicted-live-state\n", encoding="utf-8")
            live_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
            reopened = reopen_for_contradiction(
                resumed,
                contradiction={
                    "subject_ref": "artifact://output.txt",
                    "kind": "artifact-hash-mismatch",
                    "expected": expected_first_hash,
                    "observed": live_hash,
                },
                observed_by="observer:test",
                evidence_ref=f"artifact://output.txt@sha256:{live_hash}",
            )
            store.save(reopened, events=[{"kind": "live-contradiction"}])

            coordinator = MissionCoordinator(
                checkpoint_store=store,
                clock=lambda: "2026-08-07T18:05:00Z",
            )
            corrected, correction_receipt = coordinator.dispatch_one(
                reopened,
                action("repair", "reconcile live-state contradiction"),
                adapter=adapter,
                actor_ref="steward:test",
            )
            expected_final_hash = hashlib.sha256(b"corrected\n").hexdigest()
            self.assertEqual(correction_receipt["observed_effects"][0]["sha256"], expected_final_hash)

            reconciled = record_reconciliation_observation(
                corrected,
                subject_ref="artifact://output.txt",
                observed_by="observer:test",
                evidence_ref=f"artifact://output.txt@sha256:{expected_final_hash}",
            )
            store.save(reconciled, events=[{"kind": "live-state-reconciled"}])

            verifying = coordinator.propose_verification(
                reconciled,
                actor_ref="steward:test",
                proof_bundle_ref=f"proof://output.txt@sha256:{expected_final_hash}",
            )
            store.save(verifying, events=[{"kind": "proof-bundle-frozen"}])

            with self.assertRaisesRegex(TransitionError, "INDEPENDENT_ACCEPTOR_REQUIRED"):
                transition(
                    verifying,
                    "completed",
                    actor_ref="steward:test",
                    evidence_ref="acceptance://self",
                    independent=True,
                )

            completed = transition(
                verifying,
                "completed",
                actor_ref="acceptor:independent",
                evidence_ref="acceptance://independent/pass",
                independent=True,
            )
            store.save(completed, events=[{"kind": "independent-acceptance"}])

            final, final_checkpoint = store.load_latest("mission-001")
            self.assertEqual(final.state["status"], "completed")
            self.assertEqual(final.integrity["completion_acceptor"], "acceptor:independent")
            self.assertEqual(final.authority["instruction"], original_instruction)
            self.assertEqual(artifact.read_text(encoding="utf-8"), "corrected\n")
            self.assertEqual(final_checkpoint.revision, final.revision)
            self.assertEqual(adapter.calls, 2)


if __name__ == "__main__":
    unittest.main()
