"""Bounded filesystem artifact adapter must leave external durable receipts."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from practical_agency.coordinator import coordinate_once, dispatch_once
from practical_agency.filesystem_artifact import (
    FilesystemArtifactAdapter,
    FilesystemArtifactError,
    inspect_filesystem_receipt,
    verify_filesystem_receipt,
)
from practical_agency.manifest_model import MissionManifest
from practical_agency.proof import VerifierResult
from practical_agency.state_machine import apply_event_data
from tests.helpers import clone_payload, mission_os_event


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


def _broker_dispatch(
    adapter: FilesystemArtifactAdapter,
    **overrides: object,
) -> tuple[dict[str, object], dict[str, object]]:
    requested = _request(**overrides)
    payload = clone_payload()
    payload["mission_id"] = str(requested["mission_id"])
    payload["authority"]["permissions"] = list(requested["requested_permissions"])
    payload["authority"]["acceptable_costs"] = list(requested["estimated_costs"])
    draft = MissionManifest.from_dict(payload)
    active = apply_event_data(
        draft,
        "approve",
        "operator:test",
        {"checkpoint_ref": "checkpoint:filesystem-adapter-test"},
    )
    active = apply_event_data(
        active,
        "apply_mission_os",
        "mission-steward",
        mission_os_event(
            active,
            "frontier_patch",
            {"labels": ["exercise bounded filesystem adapter"]},
        ),
    )
    decision = coordinate_once(
        active,
        execution_request={
            key: requested[key]
            for key in (
                "capability_id",
                "requested_permissions",
                "requested_effects",
                "estimated_costs",
                "action",
            )
        },
        checkpoint_store=object(),
    )
    result = dispatch_once(active, decision, adapter)
    return result, dict(decision.request or {})


class FilesystemArtifactAdapterTests(unittest.TestCase):
    def test_adapter_construction_has_no_filesystem_effect(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "not-created"

            adapter = FilesystemArtifactAdapter(root)

            self.assertFalse(root.exists())
            with self.assertRaisesRegex(
                FilesystemArtifactError,
                "BROKER_DISPATCH_REQUIRED",
            ):
                adapter.dispatch(_request())
            self.assertFalse(root.exists())

    def test_direct_dispatch_without_broker_grant_is_rejected_before_effect(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            adapter = FilesystemArtifactAdapter(root)

            with self.assertRaisesRegex(
                FilesystemArtifactError,
                "BROKER_DISPATCH_REQUIRED",
            ):
                adapter.dispatch(_request())

            self.assertFalse((root / "mission-artifacts" / "note.txt").exists())
            self.assertEqual(list((root / ".receipts").glob("*.json")), [])

    def test_write_creates_artifact_and_on_disk_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            adapter = FilesystemArtifactAdapter(root)
            receipt, _ = _broker_dispatch(adapter)
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
            blocked, _ = _broker_dispatch(
                adapter,
                requested_effects=[
                    "relpath:../escape.txt",
                    "utf8:nope",
                ],
            )
            self.assertEqual(blocked["status"], "blocked")
            self.assertIsNone(blocked["external_receipt_ref"])
            other, _ = _broker_dispatch(
                adapter,
                requested_effects=[
                    "relpath:etc/passwd",
                    "utf8:nope",
                ],
            )
            self.assertEqual(other["status"], "blocked")

    def test_unknown_action_is_declined_without_shell(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            adapter = FilesystemArtifactAdapter(Path(temp))
            declined, _ = _broker_dispatch(adapter, action="shell")
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
            receipt, _ = _broker_dispatch(adapter)
            external = Path(str(receipt["external_receipt_ref"]))
            self.assertEqual(external.parent, (root / ".receipts").resolve())
            self.assertNotIn("/", external.name)
            self.assertEqual(len(external.stem), 64)

    def test_failure_before_effect_leaves_failed_journal_and_no_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            adapter = FilesystemArtifactAdapter(root, fail_at="before_effect")
            with self.assertRaisesRegex(FilesystemArtifactError, "INJECTED_BEFORE_EFFECT"):
                _broker_dispatch(adapter)
            self.assertFalse((root / "mission-artifacts" / "note.txt").exists())
            journals = list((root / ".receipts").glob("*.json"))
            self.assertEqual(len(journals), 1)
            self.assertEqual(json.loads(journals[0].read_text())["state"], "failed")

    def test_failure_after_effect_is_visible_as_uncertain_not_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            adapter = FilesystemArtifactAdapter(root, fail_at="after_effect")
            with self.assertRaisesRegex(FilesystemArtifactError, "INJECTED_AFTER_EFFECT"):
                _broker_dispatch(adapter)
            self.assertTrue((root / "mission-artifacts" / "note.txt").is_file())
            journal = next((root / ".receipts").glob("*.json"))
            self.assertEqual(json.loads(journal.read_text())["state"], "uncertain")

    def test_receipt_verifier_recomputes_artifact_hash_and_rejects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            adapter = FilesystemArtifactAdapter(root)
            result, request = _broker_dispatch(adapter)
            verified = verify_filesystem_receipt(
                str(result["external_receipt_ref"]), request, root
            )
            self.assertIsInstance(verified, VerifierResult)
            self.assertEqual(verified.status, "verified")
            self.assertEqual(verified.proof_ref, "file:mission-artifacts/note.txt")
            self.assertEqual(
                verified.observation["observed_sha256"],
                result["observed_effects"][0]["sha256"],
            )
            (root / "mission-artifacts" / "note.txt").write_text("tampered")
            contradiction = inspect_filesystem_receipt(
                str(result["external_receipt_ref"]), request, root
            )
            self.assertIsInstance(contradiction, VerifierResult)
            self.assertEqual(contradiction.status, "contradicted")
            self.assertEqual(contradiction.reason_code, "ARTIFACT_HASH_MISMATCH")
            with self.assertRaisesRegex(FilesystemArtifactError, "ARTIFACT_HASH_MISMATCH"):
                verify_filesystem_receipt(
                    str(result["external_receipt_ref"]), request, root
                )

    def test_committed_request_replay_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first, _ = _broker_dispatch(FilesystemArtifactAdapter(root))
            replay, _ = _broker_dispatch(
                FilesystemArtifactAdapter(root, fail_at="before_effect")
            )
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
            _broker_dispatch(adapter)
            with self.assertRaisesRegex(FilesystemArtifactError, "REQUEST_ID_COLLISION"):
                _broker_dispatch(
                    adapter,
                    requested_effects=[
                        "relpath:mission-artifacts/note.txt",
                        "utf8:different content",
                    ],
                )

    def test_missing_external_receipt_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result, request = _broker_dispatch(FilesystemArtifactAdapter(root))
            Path(str(result["external_receipt_ref"])).unlink()
            with self.assertRaisesRegex(FilesystemArtifactError, "RECEIPT_NOT_FOUND"):
                verify_filesystem_receipt(
                    str(result["external_receipt_ref"]), request, root
                )


if __name__ == "__main__":
    unittest.main()
