from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from practical_agency import state_machine
from practical_agency.checkpoint_store import CheckpointError, CheckpointStore
from practical_agency.manifest_model import MissionManifest
from practical_agency.state_machine import TransitionError, reopen_for_contradiction, transition
from practical_agency.validation import validate_manifest_dict
from tests.helpers import active_payload


GATE_REF = "gate://validator/pass"
PROOF_REF = "proof://bundle/one"
SUBJECT_REF = "artifact://canonical"


def active_with_gate(*, include_gate: bool = True) -> MissionManifest:
    payload = active_payload()
    payload["integrity"]["material_work_actors"] = ["steward:test"]
    payload["integrity"]["required_gates"] = [GATE_REF]
    payload["continuity"]["durable_artifacts"] = [GATE_REF] if include_gate else []
    return MissionManifest.from_dict(payload)


def completed_manifest() -> MissionManifest:
    verifying = transition(
        active_with_gate(),
        "verifying",
        actor_ref="steward:test",
        evidence_ref=PROOF_REF,
        reason="proof bundle ready",
    )
    return transition(
        verifying,
        "completed",
        actor_ref="reviewer:test",
        evidence_ref="acceptance://pass/one",
        reason="independent pass",
        independent=True,
    )


class RuntimeManifestShapeTests(unittest.TestCase):
    def test_runtime_validator_rejects_non_object_operational_entries(self) -> None:
        payload = active_payload()
        payload["truth"]["verified_facts"] = ["not-an-object"]
        payload["state"]["blockers"] = ["not-an-object"]
        payload["capabilities"]["available"] = ["not-an-object"]
        payload["continuity"]["decisions"] = ["not-an-object"]
        payload["integrity"]["unresolved_verdicts"] = ["not-an-object"]
        errors = validate_manifest_dict(payload)
        for field in (
            "truth.verified_facts",
            "state.blockers",
            "capabilities.available",
            "continuity.decisions",
            "integrity.unresolved_verdicts",
        ):
            self.assertTrue(any(field in error for error in errors), (field, errors))
        with self.assertRaises(ValueError):
            MissionManifest.from_dict(payload)


class CheckpointPathIntegrityTests(unittest.TestCase):
    def test_latest_pointer_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(Path(tmp) / "checkpoints")
            receipt = store.save(MissionManifest.from_dict(active_payload()))
            pointer = receipt.path.parent / "LATEST"
            outside = Path(tmp) / "outside-pointer.json"
            outside.write_bytes(pointer.read_bytes())
            pointer.unlink()
            pointer.symlink_to(outside)
            with self.assertRaisesRegex(CheckpointError, "CHECKPOINT_SYMLINK_FORBIDDEN"):
                store.load_latest("mission-001")

    def test_checkpoint_content_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(Path(tmp) / "checkpoints")
            receipt = store.save(MissionManifest.from_dict(active_payload()))
            outside = Path(tmp) / "outside-checkpoint.json"
            outside.write_bytes(receipt.path.read_bytes())
            receipt.path.unlink()
            receipt.path.symlink_to(outside)
            with self.assertRaisesRegex(CheckpointError, "CHECKPOINT_SYMLINK_FORBIDDEN"):
                store.load_latest("mission-001")


class VerificationEvidenceTests(unittest.TestCase):
    def test_verification_refuses_missing_required_gate(self) -> None:
        with self.assertRaisesRegex(TransitionError, "REQUIRED_GATES_MISSING"):
            transition(
                active_with_gate(include_gate=False),
                "verifying",
                actor_ref="steward:test",
                evidence_ref=PROOF_REF,
                reason="proof bundle ready",
            )

    def test_verification_retains_the_frozen_proof_bundle(self) -> None:
        verifying = transition(
            active_with_gate(),
            "verifying",
            actor_ref="steward:test",
            evidence_ref=PROOF_REF,
            reason="proof bundle ready",
        )
        self.assertIn(PROOF_REF, verifying.continuity["durable_artifacts"])


class ReconciliationIntegrityTests(unittest.TestCase):
    def test_contradiction_reopens_with_load_bearing_remediation_state(self) -> None:
        completed = completed_manifest()
        reopened = reopen_for_contradiction(
            completed,
            contradiction={
                "subject_ref": SUBJECT_REF,
                "kind": "artifact-hash-mismatch",
                "expected": "sha256:old",
                "observed": "sha256:new",
            },
            observed_by="observer:test",
            evidence_ref="observation://contradiction/one",
        )
        self.assertEqual(reopened.state["status"], "active")
        self.assertEqual(reopened.state["next_action"], "reconcile live-state contradiction")
        self.assertTrue(reopened.state["blockers"])
        self.assertTrue(reopened.integrity["unresolved_verdicts"])
        self.assertNotIn(GATE_REF, reopened.continuity["durable_artifacts"])
        self.assertNotIn(PROOF_REF, reopened.continuity["durable_artifacts"])
        self.assertIsNone(reopened.integrity["completion_acceptor"])
        self.assertIsNone(reopened.integrity["acceptance_receipt_ref"])

    def test_reconciliation_observation_clears_only_the_matching_contradiction(self) -> None:
        reopened = reopen_for_contradiction(
            completed_manifest(),
            contradiction={
                "subject_ref": SUBJECT_REF,
                "kind": "artifact-hash-mismatch",
                "expected": "sha256:old",
                "observed": "sha256:new",
            },
            observed_by="observer:test",
            evidence_ref="observation://contradiction/one",
        )
        reconcile = getattr(state_machine, "record_reconciliation_observation", None)
        self.assertTrue(callable(reconcile), "record_reconciliation_observation is missing")
        resolved = reconcile(
            reopened,
            subject_ref=SUBJECT_REF,
            observed_by="observer:test",
            evidence_ref="observation://reconciled/one",
            restored_gate_refs=(GATE_REF,),
        )
        self.assertEqual(resolved.state["status"], "active")
        self.assertEqual(resolved.state["blockers"], ())
        self.assertEqual(resolved.integrity["unresolved_verdicts"], ())
        self.assertIn(GATE_REF, resolved.continuity["durable_artifacts"])
        self.assertIn("observation://reconciled/one", resolved.continuity["durable_artifacts"])


class IndependentVerdictTests(unittest.TestCase):
    def _record(self, **kwargs: object) -> MissionManifest:
        record = getattr(state_machine, "record_acceptance_verdict", None)
        self.assertTrue(callable(record), "record_acceptance_verdict is missing")
        verifying = transition(
            active_with_gate(),
            "verifying",
            actor_ref="steward:test",
            evidence_ref=PROOF_REF,
            reason="proof bundle ready",
        )
        return record(verifying, **kwargs)

    def test_fail_verdict_returns_control_with_receipted_blocker(self) -> None:
        failed = self._record(
            verdict="FAIL",
            actor_ref="reviewer:test",
            evidence_refs=("review://fail/one",),
            coverage_limits=("isolated fixture",),
            reason="required behavior contradicted",
        )
        self.assertEqual(failed.state["status"], "active")
        self.assertTrue(failed.state["blockers"])
        self.assertTrue(failed.integrity["unresolved_verdicts"])
        decision = failed.continuity["decisions"][-1]
        self.assertEqual(decision["verdict"], "FAIL")
        self.assertEqual(decision["evidence_refs"], ("review://fail/one",))

    def test_inconclusive_verdict_blocks_without_granting_completion(self) -> None:
        inconclusive = self._record(
            verdict="INCONCLUSIVE",
            actor_ref="reviewer:test",
            evidence_refs=("review://inconclusive/one",),
            coverage_limits=("production runtime unavailable",),
            reason="runtime evidence unavailable",
        )
        self.assertEqual(inconclusive.state["status"], "blocked")
        self.assertIsNone(inconclusive.integrity["completion_acceptor"])

    def test_non_pass_verdict_requires_independence_and_evidence(self) -> None:
        for kwargs, code in (
            (
                {
                    "verdict": "FAIL",
                    "actor_ref": "steward:test",
                    "evidence_refs": ("review://fail/self",),
                    "coverage_limits": (),
                    "reason": "self review",
                },
                "INDEPENDENT_ACCEPTOR_REQUIRED",
            ),
            (
                {
                    "verdict": "INCONCLUSIVE",
                    "actor_ref": "reviewer:test",
                    "evidence_refs": (),
                    "coverage_limits": (),
                    "reason": "no evidence",
                },
                "ACCEPTANCE_EVIDENCE_REQUIRED",
            ),
        ):
            with self.subTest(code=code):
                with self.assertRaisesRegex(TransitionError, code):
                    self._record(**kwargs)


if __name__ == "__main__":
    unittest.main()
