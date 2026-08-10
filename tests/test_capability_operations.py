from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from practical_agency.capability_grants import issue_grant
from practical_agency.capability_operations import execute_read, CapabilityOperationError


class CapabilityOperationTests(unittest.TestCase):
    def _grant(self, operation: str, scope: str):
        return issue_grant({
            "mission_id": "m1", "mission_revision": 2, "capability_id": "reader",
            "capability_descriptor_sha256": "b" * 64,
            "blocking_condition": "bounded inspection",
            "return_point": {"mission_id":"m1","revision":2,"frontier_index":0,"label":"bounded inspection"},
            "admitted_operation": operation, "evidence_scope": [scope],
            "mutation": False, "expires_after_use": True,
        })

    def test_exact_file_and_resource_reads_are_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "evidence.txt").write_text("proof", encoding="utf-8")
            for operation in ("file.read", "resource.read"):
                grant = self._grant(operation, "evidence.txt")
                result = execute_read(grant, mission_id="m1", mission_revision=2,
                                      operation=operation, target="evidence.txt", workspace=root,
                                      evidence_refs=["evidence.txt"])
                self.assertEqual(result["verdict"], "PASS")
                self.assertEqual(result["observed_effects"][0]["content"], "proof")

    def test_declared_web_read_requires_retained_source_evidence(self):
        grant = self._grant("web.open", "https://example.test/source")
        grant["evidence_scope"].append("source:https://example.test/source")
        result = execute_read(grant, mission_id="m1", mission_revision=2,
                              operation="web.open", target="https://example.test/source",
                              workspace=Path("."), evidence_refs=["source:https://example.test/source"],
                              evidence_payload={"source:https://example.test/source": "Example Domain"})
        self.assertEqual(result["verdict"], "PASS")
        with self.assertRaisesRegex(CapabilityOperationError, "SOURCE_EVIDENCE_REQUIRED"):
            execute_read(self._grant("web.open", "https://example.test/source"), mission_id="m1", mission_revision=2,
                         operation="web.open", target="https://example.test/source", workspace=Path("."))

    def test_shell_and_ungranted_target_are_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "evidence.txt").write_text("proof", encoding="utf-8")
            with self.assertRaisesRegex(CapabilityOperationError, "OPERATION_NOT_READ_ONLY"):
                execute_read(self._grant("shell", "evidence.txt"), mission_id="m1", mission_revision=2,
                             operation="shell", target="evidence.txt", workspace=root)
            with self.assertRaisesRegex(CapabilityOperationError, "TARGET_NOT_IN_EVIDENCE_SCOPE"):
                execute_read(self._grant("file.read", "evidence.txt"), mission_id="m1", mission_revision=2,
                             operation="file.read", target="other.txt", workspace=root)
