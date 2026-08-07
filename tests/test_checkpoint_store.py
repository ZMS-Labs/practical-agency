from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from practical_agency.checkpoint_store import (
    FileCheckpointStore,
    ReconciliationFinding,
    reconcile_observations,
)
from practical_agency.manifest_model import MissionManifest
from practical_agency.state_machine import MissionEvent, apply_event


def _draft() -> MissionManifest:
    payload = {
        "schema": "mission-manifest@1",
        "mission_id": "mission-001",
        "revision": 1,
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
            "verified_facts": [{"subject_ref": "repo:example@rev-1", "value": "clean"}],
            "assumptions": [],
            "contradictions": [],
            "unknowns": [],
        },
        "state": {
            "status": "draft",
            "completed_actions": [],
            "current_frontier": ["obtain approval"],
            "blockers": [],
            "next_action": "obtain approval",
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
    return MissionManifest.from_dict(payload)


class CheckpointStoreTests(unittest.TestCase):
    def test_atomic_save_and_load_latest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FileCheckpointStore(Path(tmp))
            draft = _draft()
            receipt = store.save(draft)
            self.assertTrue(receipt.path.endswith("mission-001-0001.json"))
            loaded, loaded_receipt = store.load_latest("mission-001")
            self.assertEqual(loaded.revision, 1)
            self.assertEqual(loaded_receipt.sha256, receipt.sha256)
            self.assertEqual(
                loaded.authority["instruction"],
                "Create and verify the example artifact.",
            )

    def test_receipt_hash_matches_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FileCheckpointStore(Path(tmp))
            receipt = store.save(_draft())
            raw = Path(receipt.path).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), receipt.sha256)

    def test_hash_mismatch_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FileCheckpointStore(Path(tmp))
            receipt = store.save(_draft())
            path = Path(receipt.path)
            path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "CHECKPOINT_HASH_MISMATCH"):
                store.load(receipt)

    def test_higher_revision_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FileCheckpointStore(Path(tmp))
            draft = _draft()
            store.save(draft)
            active = apply_event(
                draft,
                MissionEvent(kind="approve", actor_ref="operator:test"),
            )
            store.save(active)
            loaded, receipt = store.load_latest("mission-001")
            self.assertEqual(loaded.revision, 2)
            self.assertIn("0002", receipt.path)

    def test_stray_temp_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = FileCheckpointStore(root)
            store.save(_draft())
            (root / "mission-001-0009.json.tmp").write_text("partial", encoding="utf-8")
            loaded, receipt = store.load_latest("mission-001")
            self.assertEqual(loaded.revision, 1)
            self.assertIn("0001", receipt.path)

    def test_summary_cannot_substitute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = FileCheckpointStore(root)
            (root / "mission-001-summary.md").write_text("# summary", encoding="utf-8")
            self.assertIsNone(store.load_latest("mission-001"))

    def test_overwrite_different_bytes_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FileCheckpointStore(Path(tmp))
            draft = _draft()
            store.save(draft)
            mutated = draft.to_dict()
            mutated["authority"]["instruction"] = "tampered"
            with self.assertRaisesRegex(ValueError, "CHECKPOINT_IMMUTABLE"):
                store.save(MissionManifest.from_dict(mutated))

    def test_reconciliation_contradiction(self) -> None:
        draft = _draft()
        findings = reconcile_observations(
            draft,
            observations={"repo:example@rev-1": "dirty"},
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].classification, "CONTRADICTED")
        self.assertIsInstance(findings[0], ReconciliationFinding)


if __name__ == "__main__":
    unittest.main()
