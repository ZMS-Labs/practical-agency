from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_controller_process_proof.py"


class ControllerProcessResumeTests(unittest.TestCase):
    def test_three_processes_resume_repair_and_verify_external_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pa-process-proof-") as temp:
            root = Path(temp)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / ".git").mkdir()
            report_path = root / "controller-process-proof.json"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--workspace",
                    str(workspace),
                    "--report",
                    str(report_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["schema"], "controller-process-proof@1")
            self.assertEqual(len(report["process_instance_ids"]), 3)
            self.assertEqual(len(set(report["process_instance_ids"])), 3)
            self.assertEqual(report["mission_path_inputs"], 0)
            self.assertEqual(report["workspace_path_inputs"], 0)
            self.assertIn(
                report["drift_reason"],
                ["UNRECEIPTED_WORKSPACE_DRIFT", "ARTIFACT_HASH_MISMATCH"],
            )
            self.assertEqual(report["direct_adapter_bypass"], "BROKER_DISPATCH_REQUIRED")
            self.assertEqual(report["final_status"], "completed")
            self.assertEqual(
                report["acceptance_assurance"], "declared-role-separation"
            )
            self.assertIn("INDEPENDENT_ACCEPTANCE_REQUIRED", report["refusal_codes"])
            self.assertEqual(len(report["checkpoint_hashes"]), 3)
            self.assertTrue(all(len(digest) == 64 for digest in report["checkpoint_hashes"]))
            self.assertGreaterEqual(len(report["verifier_result_refs"]), 2)
            self.assertGreaterEqual(report["hook_subprocess_calls"], 10)

            receipt_path = Path(report["external_receipt_ref"])
            self.assertTrue(receipt_path.is_file())
            receipt_bytes = receipt_path.read_bytes()
            self.assertEqual(
                hashlib.sha256(receipt_bytes).hexdigest(),
                report["external_receipt_sha256"],
            )
            receipt = json.loads(receipt_bytes)
            binding = report["receipt_binding"]
            self.assertEqual(receipt["mission_id"], report["mission_id"])
            self.assertEqual(receipt["mission_id"], binding["mission_id"])
            self.assertEqual(receipt["mission_revision"], binding["mission_revision"])
            self.assertEqual(receipt["request_id"], binding["request_id"])
            self.assertIn(
                "distinct principal identity is not proven",
                report["claim_limits"],
            )


if __name__ == "__main__":
    unittest.main()
