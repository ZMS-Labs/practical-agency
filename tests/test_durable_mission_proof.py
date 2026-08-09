from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from practical_agency.checkpoint_store import FileCheckpointStore


ROOT = Path(__file__).resolve().parents[1]


class DurableMissionProofTests(unittest.TestCase):
    def test_process_restart_detects_drift_repairs_and_third_process_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "run_durable_mission_proof.py"),
                    "run",
                    "--workspace-root",
                    str(workspace),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(completed.stdout.strip().splitlines()[-1])
            self.assertEqual(report["schema"], "durable-mission-proof@1")
            self.assertEqual(report["process_a_exit_code"], 86)
            self.assertEqual(report["drift_detection"], "ARTIFACT_HASH_MISMATCH")
            self.assertEqual(report["final_status"], "completed")
            self.assertEqual(
                report["acceptance_assurance"],
                "declared-role-separation",
            )

            mission_id = report["mission_id"]
            store = FileCheckpointStore(
                workspace / "missions" / mission_id / "checkpoints"
            )
            loaded = store.load_latest(mission_id)
            self.assertIsNotNone(loaded)
            final, receipt = loaded
            self.assertEqual(final.state["status"], "completed")
            self.assertEqual(receipt.sha256, report["final_checkpoint_sha256"])
            self.assertEqual(
                [item["status"] for item in final.continuity["verifier_results"]],
                ["verified", "contradicted", "verified", "verified"],
            )
            final_execution = final.continuity["execution_receipts"][-1]
            self.assertEqual(
                final_execution["external_receipt_ref"],
                report["external_receipt_ref"],
            )
            acceptance = final.continuity["decisions"][-1]
            self.assertEqual(acceptance["kind"], "completion-acceptance")
            self.assertEqual(
                acceptance["separation_assurance"],
                "declared-role-separation",
            )


if __name__ == "__main__":
    unittest.main()
