"""Bounded filesystem artifact adapter must leave external durable receipts."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from practical_agency.filesystem_artifact import (
    FilesystemArtifactAdapter,
    FilesystemArtifactError,
    verify_filesystem_receipt,
)


def _request(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": "execution-request@1",
        "request_id": "mission-1:r2:fs:write:f0",
        "mission_id": "mission-1",
        "mission_revision": 2,
        "capability_id": "filesystem-artifact",
        "requested_permissions": ["repository:write"],
        "requested_effects": [
            "relpath:mission-artifacts/note.txt",
            "utf8:hello from authorized mission",
        ],
        "estimated_costs": ["one local artifact write"],
        "action": "write-text",
    }
    payload.update(overrides)
    return payload


class FilesystemArtifactAdapterTests(unittest.TestCase):
    def test_write_creates_artifact_and_on_disk_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            adapter = FilesystemArtifactAdapter(root)
            receipt = adapter.dispatch(_request())
            self.assertEqual(receipt["schema"], "execution-receipt@1")
            self.assertEqual(receipt["status"], "completed")
            self.assertEqual(receipt["adapter_ref"], "filesystem-artifact@1")
            artifact = root / "mission-artifacts" / "note.txt"
            self.assertEqual(
                artifact.read_text(encoding="utf-8"),
                "hello from authorized mission",
            )
            external = Path(str(receipt["external_receipt_ref"]))
            self.assertTrue(external.is_file())
            self.assertTrue(str(external).startswith(str(root.resolve())))
            body = json.loads(external.read_text(encoding="utf-8"))
            self.assertEqual(body["artifact_sha256"], receipt["observed_effects"][0]["sha256"])
            self.assertEqual(body["relpath"], "mission-artifacts/note.txt")

    def test_path_escape_and_disallowed_prefix_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            adapter = FilesystemArtifactAdapter(root)
            blocked = adapter.dispatch(
                _request(
                    requested_effects=[
                        "relpath:../escape.txt",
                        "utf8:nope",
                    ]
                )
            )
            self.assertEqual(blocked["status"], "blocked")
            self.assertIsNone(blocked["external_receipt_ref"])
            other = adapter.dispatch(
                _request(
                    requested_effects=[
                        "relpath:etc/passwd",
                        "utf8:nope",
                    ]
                )
            )
            self.assertEqual(other["status"], "blocked")

    def test_unknown_action_is_declined_without_shell(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            adapter = FilesystemArtifactAdapter(Path(temp))
            declined = adapter.dispatch(_request(action="shell"))
            self.assertEqual(declined["status"], "declined")
            self.assertIn("no arbitrary shell", " ".join(declined["coverage_limits"]).lower())

    def test_end_to_end_mission_can_use_filesystem_adapter(self) -> None:
        from practical_agency.checkpoint_store import FileCheckpointStore
        from practical_agency.coordinator import coordinate_once, dispatch_once
        from practical_agency.manifest_model import MissionManifest
        from practical_agency.state_machine import apply_event_data
        from tests.helpers import clone_payload, mission_os_event

        payload = clone_payload()
        payload["integrity"]["completion_acceptor"] = "reviewer:test"
        payload["authority"]["permissions"] = ["repository:write"]
        payload["authority"]["acceptable_costs"] = [
            "one feature branch",
            "one local artifact write",
        ]
        draft = MissionManifest.from_dict(payload)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = FileCheckpointStore(root / "checkpoints")
            first = store.save(draft)
            active = apply_event_data(
                draft,
                "approve", "operator:test", {"checkpoint_ref": first.path},
            )
            active = apply_event_data(
                active,
                "apply_mission_os",
                "mission-steward",
                mission_os_event(
                    active,
                    "frontier_patch",
                    {"labels": ["write filesystem artifact"]},
                ),
            )
            adapter = FilesystemArtifactAdapter(root / "world")
            decision = coordinate_once(
                active,
                execution_request={
                    "capability_id": "filesystem-artifact",
                    "requested_permissions": ["repository:write"],
                    "requested_effects": [
                        "relpath:mission-artifacts/from-mission.txt",
                        "utf8:world effect",
                    ],
                    "estimated_costs": ["one local artifact write"],
                    "action": "write-text",
                },
                checkpoint_store=store,
            )
            result = dispatch_once(active, decision, adapter)
            self.assertEqual(result["status"], "completed")
            written = root / "world" / "mission-artifacts" / "from-mission.txt"
            self.assertEqual(written.read_text(encoding="utf-8"), "world effect")
            self.assertTrue(Path(str(result["external_receipt_ref"])).is_file())

    def test_receipt_filename_is_digest_not_request_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            adapter = FilesystemArtifactAdapter(root)
            receipt = adapter.dispatch(_request(request_id="mission/unsafe:request"))
            external = Path(str(receipt["external_receipt_ref"]))
            self.assertEqual(external.parent, (root / ".receipts").resolve())
            self.assertNotIn("/", external.name)
            self.assertEqual(len(external.stem), 64)

    def test_failure_before_effect_leaves_failed_journal_and_no_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            adapter = FilesystemArtifactAdapter(root, fail_at="before_effect")
            with self.assertRaisesRegex(FilesystemArtifactError, "INJECTED_BEFORE_EFFECT"):
                adapter.dispatch(_request())
            self.assertFalse((root / "mission-artifacts" / "note.txt").exists())
            journals = list((root / ".receipts").glob("*.json"))
            self.assertEqual(len(journals), 1)
            self.assertEqual(json.loads(journals[0].read_text())["state"], "failed")

    def test_failure_after_effect_is_visible_as_uncertain_not_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            adapter = FilesystemArtifactAdapter(root, fail_at="after_effect")
            with self.assertRaisesRegex(FilesystemArtifactError, "INJECTED_AFTER_EFFECT"):
                adapter.dispatch(_request())
            self.assertTrue((root / "mission-artifacts" / "note.txt").is_file())
            journal = next((root / ".receipts").glob("*.json"))
            self.assertEqual(json.loads(journal.read_text())["state"], "uncertain")

    def test_receipt_verifier_recomputes_artifact_hash_and_rejects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            adapter = FilesystemArtifactAdapter(root)
            result = adapter.dispatch(_request())
            verified = verify_filesystem_receipt(
                str(result["external_receipt_ref"]), _request(), root
            )
            self.assertEqual(verified["state"], "committed")
            (root / "mission-artifacts" / "note.txt").write_text("tampered")
            with self.assertRaisesRegex(FilesystemArtifactError, "ARTIFACT_HASH_MISMATCH"):
                verify_filesystem_receipt(
                    str(result["external_receipt_ref"]), _request(), root
                )

    def test_committed_request_replay_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = FilesystemArtifactAdapter(root).dispatch(_request())
            replay = FilesystemArtifactAdapter(
                root, fail_at="before_effect"
            ).dispatch(_request())
            self.assertEqual(replay["status"], "completed")
            self.assertEqual(
                replay["external_receipt_ref"], first["external_receipt_ref"]
            )
            self.assertIn(
                "replayed idempotently", " ".join(replay["coverage_limits"])
            )

    def test_same_request_id_with_different_payload_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            adapter = FilesystemArtifactAdapter(root)
            adapter.dispatch(_request())
            with self.assertRaisesRegex(FilesystemArtifactError, "REQUEST_ID_COLLISION"):
                adapter.dispatch(
                    _request(
                        requested_effects=[
                            "relpath:mission-artifacts/note.txt",
                            "utf8:different content",
                        ]
                    )
                )

    def test_missing_external_receipt_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = FilesystemArtifactAdapter(root).dispatch(_request())
            Path(str(result["external_receipt_ref"])).unlink()
            with self.assertRaisesRegex(FilesystemArtifactError, "RECEIPT_NOT_FOUND"):
                verify_filesystem_receipt(
                    str(result["external_receipt_ref"]), _request(), root
                )


if __name__ == "__main__":
    unittest.main()
