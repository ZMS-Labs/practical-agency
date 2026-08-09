from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from practical_agency.governed_workspace import (
    GovernedWorkspaceError,
    capture_baseline,
    find_unreceipted_drift,
    normalize_governed_paths,
)
from practical_agency.manifest_model import MissionManifest
from tests.helpers import clone_payload


class GovernedWorkspaceTests(unittest.TestCase):
    def _workspace(self, temp: str) -> Path:
        workspace = Path(temp) / "workspace"
        workspace.mkdir()
        (workspace / ".git").mkdir()
        return workspace

    def test_paths_reject_escape_directory_symlink_and_missions_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            (workspace / "docs").mkdir()
            external = Path(temp) / "external"
            external.mkdir()
            link = workspace / "link"
            try:
                os.symlink(external, link, target_is_directory=True)
            except OSError:
                link = None

            candidates = ["../x", "/absolute", "missions/x", "docs"]
            if link is not None:
                candidates.append("link/child.txt")
            for candidate in candidates:
                with self.subTest(candidate=candidate):
                    with self.assertRaises(GovernedWorkspaceError):
                        normalize_governed_paths(workspace, [candidate])

    def test_existing_dirty_bytes_are_baseline_not_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            target = workspace / "docs" / "alpha.md"
            target.parent.mkdir()
            target.write_bytes(b"operator bytes\n")

            baseline = capture_baseline(workspace, ["docs/alpha.md"])

            self.assertEqual(
                baseline["baseline"][0]["state"],
                {
                    "kind": "regular-file",
                    "bytes": 15,
                    "sha256": hashlib.sha256(b"operator bytes\n").hexdigest(),
                },
            )
            self.assertEqual(find_unreceipted_drift(workspace, baseline, []), [])

    def test_committed_effect_is_subtracted_but_later_drift_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            target = workspace / "docs" / "alpha.md"
            target.parent.mkdir()
            baseline = capture_baseline(workspace, ["docs/alpha.md"])
            approved = b"approved bytes\n"
            target.write_bytes(approved)
            receipt = {
                "status": "completed",
                "observed_effects": [
                    {
                        "kind": "text-artifact-written",
                        "relpath": "docs/alpha.md",
                        "sha256": hashlib.sha256(approved).hexdigest(),
                        "bytes": len(approved),
                    }
                ],
            }

            self.assertEqual(
                find_unreceipted_drift(workspace, baseline, [receipt]),
                [],
            )

            target.write_bytes(b"planted drift\n")
            findings = find_unreceipted_drift(workspace, baseline, [receipt])
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].path, "docs/alpha.md")
            self.assertEqual(findings[0].reason_code, "UNRECEIPTED_WORKSPACE_DRIFT")

    def test_replaced_existing_parent_is_drift_even_when_file_bytes_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            target = workspace / "docs" / "alpha.md"
            target.parent.mkdir()
            target.write_bytes(b"same bytes\n")
            baseline = capture_baseline(workspace, ["docs/alpha.md"])

            target.parent.rename(workspace / "old-docs")
            target.parent.mkdir()
            target.write_bytes(b"same bytes\n")

            findings = find_unreceipted_drift(workspace, baseline, [])
            self.assertEqual(
                [(item.path, item.reason_code) for item in findings],
                [("docs/alpha.md", "UNRECEIPTED_WORKSPACE_DRIFT")],
            )

    def test_governed_baseline_round_trips_in_closed_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            baseline = capture_baseline(workspace, ["docs/alpha.md"])
            payload = clone_payload()
            payload["continuity"]["governed_workspace"] = baseline

            manifest = MissionManifest.from_dict(payload)

            self.assertEqual(manifest.continuity["governed_workspace"], baseline)


if __name__ == "__main__":
    unittest.main()
