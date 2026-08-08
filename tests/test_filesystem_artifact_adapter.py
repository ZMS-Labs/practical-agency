"""Bounded filesystem artifact adapter must leave external durable receipts."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from practical_agency.filesystem_artifact import FilesystemArtifactAdapter


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
        from practical_agency.state_machine import MissionEvent, apply_event
        from tests.helpers import clone_payload

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
            active = apply_event(
                draft,
                MissionEvent(
                    "approve",
                    "operator:test",
                    {"checkpoint_ref": first.path},
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


if __name__ == "__main__":
    unittest.main()
