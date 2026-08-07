from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from practical_agency.checkpoint_store import CheckpointError, CheckpointStore
from practical_agency.manifest_model import MissionManifest
from tests.helpers import active_payload


class CheckpointStoreTests(unittest.TestCase):
    def manifest(self, revision: int = 2) -> MissionManifest:
        payload = active_payload()
        payload["revision"] = revision
        return MissionManifest.from_dict(payload)


    def rewrite_bundle_and_pointer(self, receipt, bundle: dict[str, object]) -> None:
        data = (
            json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()
        filename = f"r{bundle['revision']:08d}-{digest[:12]}.json"
        replacement = receipt.path.parent / filename
        replacement.write_bytes(data)
        if replacement != receipt.path:
            receipt.path.unlink()
        pointer = {
            "schema": "checkpoint-pointer@1",
            "mission_id": bundle["mission_id"],
            "revision": bundle["revision"],
            "sha256": digest,
            "filename": filename,
        }
        (receipt.path.parent / "LATEST").write_text(
            json.dumps(pointer), encoding="utf-8"
        )

    def test_save_and_load_latest_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(Path(tmp))
            manifest = self.manifest()
            receipt = store.save(manifest, events=[{"kind": "test"}], receipts=[{"ref": "receipt:test"}])
            loaded, loaded_receipt = store.load_latest(manifest.mission_id)
            self.assertEqual(loaded.to_dict(), manifest.to_dict())
            self.assertEqual(loaded_receipt.sha256, receipt.sha256)
            self.assertEqual(loaded_receipt.revision, manifest.revision)

    def test_checkpoint_bundle_is_content_addressed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(Path(tmp))
            receipt = store.save(self.manifest())
            self.assertIn(receipt.sha256[:12], receipt.path.name)
            bundle = json.loads(receipt.path.read_text(encoding="utf-8"))
            self.assertEqual(bundle["schema"], "checkpoint@1")

    def test_tampered_bundle_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(Path(tmp))
            receipt = store.save(self.manifest())
            receipt.path.write_text(receipt.path.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaisesRegex(CheckpointError, "CHECKSUM_MISMATCH"):
                store.load_latest("mission-001")

    def test_non_monotonic_revision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(Path(tmp))
            store.save(self.manifest(revision=3))
            with self.assertRaisesRegex(CheckpointError, "NON_MONOTONIC_REVISION"):
                store.save(self.manifest(revision=2))

    def test_same_revision_with_different_content_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(Path(tmp))
            manifest = self.manifest(revision=3)
            store.save(manifest)
            payload = manifest.to_dict()
            payload["state"]["next_action"] = "different"
            with self.assertRaisesRegex(CheckpointError, "REVISION_CONFLICT"):
                store.save(MissionManifest.from_dict(payload))

    def test_pointer_failure_preserves_previous_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(Path(tmp))
            first = store.save(self.manifest(revision=2))
            second_manifest = self.manifest(revision=3)
            original_replace = os.replace

            def fail_pointer(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
                if Path(dst).name == "LATEST":
                    raise OSError("injected pointer failure")
                original_replace(src, dst)

            with mock.patch("practical_agency.checkpoint_store.os.replace", side_effect=fail_pointer):
                with self.assertRaisesRegex(CheckpointError, "CHECKPOINT_WRITE_FAILED"):
                    store.save(second_manifest)
            loaded, receipt = store.load_latest("mission-001")
            self.assertEqual(loaded.revision, 2)
            self.assertEqual(receipt.sha256, first.sha256)

    def test_orphan_temp_files_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(Path(tmp))
            receipt = store.save(self.manifest())
            (receipt.path.parent / ".orphan.tmp").write_text("garbage", encoding="utf-8")
            loaded, _ = store.load_latest("mission-001")
            self.assertEqual(loaded.revision, 2)

    def test_mission_id_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(Path(tmp))
            payload = active_payload()
            payload["mission_id"] = "../escape"
            with self.assertRaisesRegex(CheckpointError, "UNSAFE_MISSION_ID"):
                store.save(MissionManifest.from_dict(payload))

    def test_prior_checkpoint_is_bound_into_next_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(Path(tmp))
            first = store.save(self.manifest(revision=2))
            second = store.save(self.manifest(revision=3))
            bundle = json.loads(second.path.read_text(encoding="utf-8"))
            self.assertEqual(bundle["prior_checkpoint"], first.sha256)

    def test_pointer_path_traversal_is_rejected_before_file_access(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(Path(tmp))
            manifest = self.manifest(2)
            store.save(manifest)
            pointer_path = Path(tmp) / manifest.mission_id / "LATEST"
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
            pointer["filename"] = "../../outside.json"
            pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
            with self.assertRaisesRegex(CheckpointError, "INVALID_POINTER"):
                store.load_latest(manifest.mission_id)

    def test_pointer_field_types_are_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(Path(tmp))
            manifest = self.manifest(2)
            store.save(manifest)
            pointer_path = Path(tmp) / manifest.mission_id / "LATEST"
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
            for field, value in (("revision", True), ("sha256", "not-a-sha"), ("mission_id", "other")):
                with self.subTest(field=field):
                    changed = dict(pointer)
                    changed[field] = value
                    pointer_path.write_text(json.dumps(changed), encoding="utf-8")
                    with self.assertRaisesRegex(CheckpointError, "INVALID_POINTER"):
                        store.load_latest(manifest.mission_id)
            pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    def test_nested_manifest_identity_and_revision_must_match_bundle(self) -> None:
        for field, value in (("revision", 1), ("mission_id", "other-mission")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                store = CheckpointStore(Path(tmp))
                receipt = store.save(self.manifest(revision=2))
                bundle = json.loads(receipt.path.read_text(encoding="utf-8"))
                bundle["manifest"][field] = value
                self.rewrite_bundle_and_pointer(receipt, bundle)
                with self.assertRaisesRegex(CheckpointError, "MANIFEST_BUNDLE_MISMATCH"):
                    store.load_latest("mission-001")

    def test_checkpoint_bundle_shape_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(Path(tmp))
            receipt = store.save(self.manifest())
            bundle = json.loads(receipt.path.read_text(encoding="utf-8"))
            bundle["unexpected"] = "hidden state"
            self.rewrite_bundle_and_pointer(receipt, bundle)
            with self.assertRaisesRegex(CheckpointError, "INVALID_CHECKPOINT"):
                store.load_latest("mission-001")


if __name__ == "__main__":
    unittest.main()
