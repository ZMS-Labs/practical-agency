from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from practical_agency.checkpoint_store import CheckpointError, FileCheckpointStore, reconcile_observations
from practical_agency.manifest_model import MissionManifest
from tests.helpers import clone_payload


class CheckpointStoreTests(unittest.TestCase):
    def manifest(self, revision: int = 1) -> MissionManifest:
        payload = clone_payload()
        payload["revision"] = revision
        if revision > 1:
            payload["state"]["status"] = "active"
            payload["continuity"]["prior_checkpoint"] = f"checkpoint:{revision - 1}"
        return MissionManifest.from_dict(payload)

    def test_save_uses_atomic_replace_and_hashes_exact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = FileCheckpointStore(Path(temp))
            original_replace = os.replace
            calls: list[tuple[object, object]] = []

            def recording_replace(src: object, dst: object) -> None:
                calls.append((src, dst))
                original_replace(src, dst)

            with patch("practical_agency.checkpoint_store.os.replace", side_effect=recording_replace):
                receipt = store.save(self.manifest())
            self.assertGreaterEqual(len(calls), 2)
            data = Path(receipt.path).read_bytes()
            self.assertEqual(receipt.sha256, hashlib.sha256(data).hexdigest())
            self.assertIn("00000001", Path(receipt.path).name)

    def test_load_rejects_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = FileCheckpointStore(Path(temp))
            receipt = store.save(self.manifest())
            Path(receipt.path).write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(CheckpointError, "CHECKPOINT_HASH_MISMATCH"):
                store.load(receipt)

    def test_load_latest_returns_highest_valid_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = FileCheckpointStore(Path(temp))
            store.save(self.manifest(1))
            second = store.save(self.manifest(2))
            latest = store.load_latest("mission-001")
            self.assertIsNotNone(latest)
            manifest, receipt = latest or (None, None)
            self.assertEqual(manifest.revision, 2)
            self.assertEqual(receipt.sha256, second.sha256)

    def test_invalid_highest_revision_is_not_silently_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = FileCheckpointStore(Path(temp))
            store.save(self.manifest(1))
            second = store.save(self.manifest(2))
            Path(second.path).write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(CheckpointError, "CHECKPOINT_HASH_MISMATCH"):
                store.load_latest("mission-001")

    def test_stray_temp_and_summary_files_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = FileCheckpointStore(root)
            root.joinpath("mission-001.partial.tmp").write_text("partial", encoding="utf-8")
            root.joinpath("mission-001.summary.json").write_text(json.dumps(clone_payload()), encoding="utf-8")
            self.assertIsNone(store.load_latest("mission-001"))

    def test_existing_revision_cannot_be_overwritten_with_different_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = FileCheckpointStore(Path(temp))
            store.save(self.manifest())
            payload = clone_payload()
            payload["authority"]["instruction"] = "different"
            with self.assertRaisesRegex(CheckpointError, "CHECKPOINT_REVISION_COLLISION"):
                store.save(MissionManifest.from_dict(payload))

    def test_reconciliation_returns_live_contradiction(self) -> None:
        payload = clone_payload()
        payload["truth"]["verified_facts"] = [{"subject_ref": "artifact:one", "value": "hash-a"}]
        findings = reconcile_observations(MissionManifest.from_dict(payload), {"artifact:one": "hash-b"})
        self.assertEqual(findings[0].classification, "CONTRADICTED")
        self.assertEqual(findings[0].checkpoint_value, "hash-a")


if __name__ == "__main__":
    unittest.main()
