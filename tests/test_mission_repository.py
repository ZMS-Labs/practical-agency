from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from practical_agency.checkpoint_store import FileCheckpointStore
from practical_agency.manifest_model import MissionManifest
from practical_agency.mission_repository import (
    MissionDiscoveryError,
    discover_active_mission,
)
from practical_agency.state_machine import apply_event_data
from tests.helpers import clone_payload


class MissionRepositoryTests(unittest.TestCase):
    def _save_active(self, workspace: Path, mission_id: str) -> None:
        payload = clone_payload()
        payload["mission_id"] = mission_id
        draft = MissionManifest.from_dict(payload)
        store = FileCheckpointStore(workspace / "missions" / mission_id / "checkpoints")
        draft_receipt = store.save(draft)
        active = apply_event_data(
            draft,
            "approve",
            "operator:test",
            {"checkpoint_ref": draft_receipt.path},
        )
        store.save(active)

    def _save_cancelled(self, workspace: Path, mission_id: str) -> None:
        payload = clone_payload()
        payload["mission_id"] = mission_id
        payload["state"]["status"] = "cancelled"
        payload["state"]["current_frontier"] = []
        payload["state"]["next_action"] = None
        store = FileCheckpointStore(workspace / "missions" / mission_id / "checkpoints")
        store.save(MissionManifest.from_dict(payload))

    def test_discovers_the_only_unfinished_mission_from_workspace_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            self._save_cancelled(workspace, "old-mission")
            self._save_active(workspace, "active-mission")

            discovered = discover_active_mission(workspace)

            self.assertEqual(discovered.manifest.mission_id, "active-mission")
            self.assertEqual(discovered.manifest.state["status"], "active")
            self.assertEqual(
                discovered.mission_dir,
                (workspace / "missions" / "active-mission").resolve(),
            )
            self.assertEqual(discovered.receipt.revision, 2)

    def test_multiple_unfinished_missions_fail_closed_as_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            self._save_active(workspace, "mission-a")
            self._save_active(workspace, "mission-b")

            with self.assertRaisesRegex(
                MissionDiscoveryError,
                "ACTIVE_MISSION_AMBIGUOUS:mission-a,mission-b",
            ):
                discover_active_mission(workspace)

    def test_directory_name_must_match_checkpoint_receipt_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            payload = clone_payload()
            payload["mission_id"] = "receipt-mission"
            store = FileCheckpointStore(
                workspace / "missions" / "renamed-directory" / "checkpoints"
            )
            store.save(MissionManifest.from_dict(payload))

            with self.assertRaisesRegex(
                MissionDiscoveryError,
                "ACTIVE_MISSION_DIRECTORY_MISMATCH:renamed-directory:receipt-mission",
            ):
                discover_active_mission(workspace)


if __name__ == "__main__":
    unittest.main()
