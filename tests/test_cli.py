from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from practical_agency.cli import main as cli_main


class CliBridgeTests(unittest.TestCase):
    def test_full_cli_mission_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            mission_dir = Path(temp) / "test-mission"

            # 1. init
            rc = cli_main([
                "init",
                "--mission-id", "cli-mission-001",
                "--intent", "Prove CLI bridge mission lifecycle.",
                "--acceptor", "reviewer:operator-pass",
                "--operator", "operator:test",
                "--out", str(mission_dir),
            ])
            self.assertEqual(rc, 0)
            self.assertTrue((mission_dir / "checkpoints").exists())

            # 2. status
            rc = cli_main(["status", "--mission-dir", str(mission_dir)])
            self.assertEqual(rc, 0)

            # 3. approve
            rc = cli_main([
                "approve",
                "--mission-dir", str(mission_dir),
                "--operator", "operator:test",
            ])
            self.assertEqual(rc, 0)

            # 4. dispatch-file
            rc = cli_main([
                "dispatch-file",
                "--mission-dir", str(mission_dir),
                "--relpath", "mission-artifacts/cli-proof.txt",
                "--content", "Hello from CLI bridge!",
            ])
            self.assertEqual(rc, 0)
            self.assertTrue((mission_dir / "adapter_data" / "mission-artifacts" / "cli-proof.txt").exists())

            # 5. verify
            rc = cli_main([
                "verify",
                "--mission-dir", str(mission_dir),
            ])
            self.assertEqual(rc, 0)

            # 6. accept (declared role separation)
            rc = cli_main([
                "accept",
                "--mission-dir", str(mission_dir),
                "--acceptor", "reviewer:operator-pass",
                "--verdict", "PASS",
            ])
            self.assertEqual(rc, 0)

    def test_generic_command_dispatch_is_not_a_cli_surface(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            cli_main(["dispatch-cmd", "--help"])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
