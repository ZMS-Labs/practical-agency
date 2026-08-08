from __future__ import annotations

import importlib.util
import json
import os
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

from practical_agency.watch_commission import (
    accept_external_commission,
    prepare_disabled,
)

UPSTREAM_WATCH_COMMIT = "6e26484a9cae7629b233734fe5121137ba9168a8"


class FixtureAdapter:
    def prepare_disabled(self, commission: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "mechanism_ref": "fixture://watch/upstream-1",
            "substrate_kind": "fixture",
            "substrate": "isolated-fixture-adapter",
            "persistence_receipt_ref": "external-fixture://persistence/upstream-1",
            "block_evidence": {
                "detail": "the real fixture mechanism exists but its kill switch is not yet exercised",
                "observed_at": "2026-08-07T18:00:00Z",
                "receipt_ref": "external-fixture://block/upstream-1",
            },
            "coverage_limits": [
                "isolated fixture only",
                "production coverage unestablished",
            ],
        }

    def exercise_kill_switch(self, mechanism_ref: str) -> Mapping[str, Any]:
        raise NotImplementedError

    def enable_for_proof(self, mechanism_ref: str, authority_ref: str) -> Mapping[str, Any]:
        raise NotImplementedError

    def perform_safe_crossing(
        self, mechanism_ref: str, proof_spec: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        raise NotImplementedError

    def disable(self, mechanism_ref: str) -> Mapping[str, Any]:
        raise NotImplementedError


def declared_commission() -> dict[str, Any]:
    return {
        "schema": "watch-commission@1",
        "commission_id": "wc-upstream-interop-001",
        "subject": {"ref": "service:fixture", "revision": "rev-1"},
        "bound": {
            "expression": "free_space_percent < 15",
            "units": "percent",
            "direction": "below",
            "threshold": 15,
        },
        "probe": {
            "mechanism": "external fixture metric query",
            "cadence_or_event": "every 5 minutes",
            "failure_modes": ["timeout", "authentication failure"],
        },
        "destination": {
            "ref": "recipient:fixture",
            "reachable": False,
            "reachability_receipt_ref": None,
        },
        "external_observer": {
            "substrate_kind": None,
            "substrate": None,
            "mechanism_ref": None,
            "persistence_receipt_ref": None,
            "persistent_outside_session": False,
            "enabled": False,
        },
        "kill_switch": {
            "procedure_ref": "fixture://disable/upstream-1",
            "exercised": False,
            "exercise_receipt_ref": None,
        },
        "proof": {
            "authorized_by": None,
            "authorization_ref": None,
            "safe_crossing": None,
            "production_path": False,
            "bound_crossed": False,
            "alert_received": False,
            "received_at": None,
            "alert_receipt_ref": None,
        },
        "failure": {
            "kind": None,
            "detail": None,
            "observed_at": None,
            "receipt_ref": None,
        },
        "block_evidence": {
            "detail": None,
            "observed_at": None,
            "receipt_ref": None,
        },
        "state": "DECLARED",
        "block_reason": None,
        "reprove_after": None,
        "handoff": {"on_crossing": ["triage", "decision-ledger"]},
        "coverage_limits": [
            "isolated fixture only",
            "production coverage unestablished",
        ],
    }


class UpstreamWatchCommissionTests(unittest.TestCase):
    upstream_root: Path
    verifier: ModuleType

    @classmethod
    def setUpClass(cls) -> None:
        configured = os.environ.get("PRACTICAL_AGENCY_UPSTREAM_WATCH_ROOT")
        required = os.environ.get("PRACTICAL_AGENCY_REQUIRE_UPSTREAM_WATCH") == "1"
        if not configured:
            if required:
                raise AssertionError("PRACTICAL_AGENCY_UPSTREAM_WATCH_ROOT is required")
            raise unittest.SkipTest("pinned upstream watch contract not mounted")
        cls.upstream_root = Path(configured).resolve()
        verifier_path = cls.upstream_root / "verify_watch_commission.py"
        if not verifier_path.is_file():
            raise AssertionError(f"upstream verifier missing: {verifier_path}")
        spec = importlib.util.spec_from_file_location(
            "pinned_upstream_watch_commission", verifier_path
        )
        if spec is None or spec.loader is None:
            raise AssertionError("could not load pinned upstream verifier")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not callable(getattr(module, "validate_record", None)):
            raise AssertionError("pinned upstream validate_record is unavailable")
        cls.verifier = module

    def test_exact_pinned_revision_is_declared_by_the_integration(self) -> None:
        self.assertEqual(
            UPSTREAM_WATCH_COMMIT,
            "6e26484a9cae7629b233734fe5121137ba9168a8",
        )

    def test_entire_upstream_example_corpus_preserves_its_oracles(self) -> None:
        examples = sorted((self.upstream_root / "examples").glob("*.json"))
        self.assertTrue(examples)
        for path in examples:
            payload = json.loads(path.read_text(encoding="utf-8"))
            expected = payload.pop("_expected")
            result = accept_external_commission(
                payload, self.verifier.validate_record
            )
            if expected == "ACCEPT":
                self.assertEqual(
                    result.status,
                    "VERIFIED_EXTERNAL_CONTRACT",
                    (path.name, result.errors),
                )
            else:
                self.assertEqual(
                    result.status,
                    "REJECTED_EXTERNAL_CONTRACT",
                    path.name,
                )

    def test_real_upstream_verifier_accepts_practical_agency_preparation(self) -> None:
        result = prepare_disabled(
            declared_commission(), FixtureAdapter(), self.verifier.validate_record
        )
        self.assertEqual(result.status, "VERIFIED_EXTERNAL_CONTRACT", result.errors)
        self.assertEqual(result.record["state"], "BLOCKED")
        self.assertEqual(result.record["block_reason"], "KILL_SWITCH_UNPROVEN")
        self.assertEqual(
            result.record["external_observer"]["mechanism_ref"],
            "fixture://watch/upstream-1",
        )

    def test_upstream_contract_rejects_manifest_as_post_crossing_custody(self) -> None:
        examples = self.upstream_root / "examples"
        source = next(examples.glob("valid-proven.json"))
        payload = json.loads(source.read_text(encoding="utf-8"))
        payload.pop("_expected", None)
        payload["handoff"] = {"on_crossing": ["manifest"]}
        errors = self.verifier.validate_record(payload)
        self.assertTrue(
            any(error.startswith("INVALID_POST_CROSSING_HANDOFF:") for error in errors),
            errors,
        )


if __name__ == "__main__":
    unittest.main()
