from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from practical_agency.capability_grants import issue_grant
from practical_agency.capability_operations import CapabilityOperationError, execute_read


def _grant(operation: str, scope: list[str]) -> dict[str, object]:
    return issue_grant({
        "mission_id": "trust-mission",
        "mission_revision": 3,
        "capability_id": "observed-reader",
        "capability_descriptor_sha256": "a" * 64,
        "blocking_condition": "bounded-observation",
        "return_point": {"mission_id": "trust-mission", "revision": 3, "frontier_index": 0, "label": "read"},
        "admitted_operation": operation,
        "evidence_scope": scope,
        "mutation": False,
        "expires_after_use": True,
    })


class CapabilityTrustBoundaryTests(unittest.TestCase):
    def test_file_read_rejects_alternate_path_identity_even_when_scope_matches(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "evidence.txt").write_text("proof", encoding="utf-8")
            grant = _grant("file.read", ["sub/../evidence.txt"])
            with self.assertRaisesRegex(CapabilityOperationError, "ALTERNATE_PATH_IDENTITY"):
                execute_read(grant, mission_id="trust-mission", mission_revision=3,
                             operation="file.read", target="sub/../evidence.txt",
                             workspace=root, evidence_refs=["sub/../evidence.txt"])

    def test_resource_read_requires_exact_resource_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            grant = _grant("resource.read", ["resource://mission/evidence"])
            with self.assertRaisesRegex(CapabilityOperationError, "RESOURCE_IDENTITY_REQUIRED"):
                execute_read(grant, mission_id="trust-mission", mission_revision=3,
                             operation="resource.read", target="resource://mission/evidence",
                             workspace=Path(temp), evidence_refs=["resource://mission/evidence"])

    def test_web_open_returns_observed_response_record_not_caller_assertion(self):
        grant = _grant("web.open", ["https://example.test/source", "source:https://example.test/source"])
        with patch("practical_agency.capability_operations._retrieve_web") as retrieve:
            retrieve.return_value = {
                "url": "https://example.test/source",
                "retrieved_at": "2026-08-09T00:00:00Z",
                "status": 200,
                "content": "observed",
            }
            result = execute_read(
                grant, mission_id="trust-mission", mission_revision=3,
                operation="web.open", target="https://example.test/source",
                workspace=Path(tempfile.gettempdir()),
                evidence_refs=["source:https://example.test/source"],
                evidence_payload={"source:https://example.test/source": "caller claim"},
            )
        record = result["observed_effects"][0]["response"]
        self.assertEqual(record["status"], 200)
        self.assertEqual(record["url"], "https://example.test/source")
        self.assertEqual(record["content_sha256"], "604cee807f644af47487bf2bbab442b94212ac5119f36f995f78e9e4694dae8c")


if __name__ == "__main__":
    unittest.main()
