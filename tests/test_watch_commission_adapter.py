from __future__ import annotations

import unittest
from typing import Any, Mapping

from practical_agency.manifest_model import MissionManifest
from practical_agency.watch_commission import (
    CommissionIntegrationError,
    accept_external_commission,
    disable_commissions_for_revocation,
    exercise_kill_switch,
    handle_crossing_event,
    prepare_disabled,
    retain_commission,
)
from tests.helpers import clone_payload


class FakeAdapter:
    def __init__(self) -> None:
        self.disabled: list[str] = []

    def prepare_disabled(self, commission: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "mechanism_ref": "fixture://watch/1",
            "substrate_kind": "fixture",
            "substrate": "isolated-fixture-adapter",
            "persistence_receipt_ref": "external-fixture://persistence/1",
            "block_evidence": {
                "detail": "kill switch has not yet been exercised",
                "observed_at": "2026-08-07T12:00:00Z",
                "receipt_ref": "external-fixture://block/1",
            },
            "coverage_limits": ["isolated fixture only", "production coverage unestablished"],
        }

    def exercise_kill_switch(self, mechanism_ref: str) -> Mapping[str, Any]:
        return {
            "mechanism_ref": mechanism_ref,
            "exercise_receipt_ref": "external-fixture://kill/1",
            "observed_stopped": True,
        }

    def enable_for_proof(self, mechanism_ref: str, authority_ref: str) -> Mapping[str, Any]:
        return {"mechanism_ref": mechanism_ref, "authority_ref": authority_ref, "enabled": True}

    def perform_safe_crossing(self, mechanism_ref: str, proof_spec: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"mechanism_ref": mechanism_ref, "alert_received": True}

    def disable(self, mechanism_ref: str) -> Mapping[str, Any]:
        self.disabled.append(mechanism_ref)
        return {
            "mechanism_ref": mechanism_ref,
            "disabled": True,
            "observed_at": "2026-08-07T14:00:00Z",
            "disable_receipt_ref": "external-fixture://disable/1",
        }


def base_commission() -> dict[str, Any]:
    return {
        "schema": "watch-commission@1",
        "commission_id": "wc-1",
        "state": "DECLARED",
        "block_reason": None,
        "block_evidence": {"detail": None, "observed_at": None, "receipt_ref": None},
        "external_observer": {
            "substrate_kind": None,
            "substrate": None,
            "mechanism_ref": None,
            "persistence_receipt_ref": None,
            "persistent_outside_session": False,
            "enabled": False,
        },
        "kill_switch": {"procedure_ref": "fixture://disable", "exercised": False, "exercise_receipt_ref": None},
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
        "coverage_limits": [],
    }


def strict_fixture_verifier(record: Mapping[str, Any]) -> list[str]:
    state = record.get("state")
    if state == "DECLARED":
        return []
    if state == "BLOCKED" and record.get("block_reason") == "KILL_SWITCH_UNPROVEN":
        observer = record.get("external_observer", {})
        evidence = record.get("block_evidence", {})
        limits = record.get("coverage_limits", [])
        if (
            isinstance(observer, Mapping)
            and observer.get("mechanism_ref")
            and observer.get("persistent_outside_session") is True
            and observer.get("enabled") is False
            and isinstance(evidence, Mapping)
            and evidence.get("receipt_ref")
            and "production coverage unestablished" in limits
        ):
            return []
    if state == "INERT":
        observer = record.get("external_observer", {})
        kill = record.get("kill_switch", {})
        limits = record.get("coverage_limits", [])
        if (
            isinstance(observer, Mapping)
            and isinstance(kill, Mapping)
            and observer.get("mechanism_ref")
            and observer.get("persistent_outside_session") is True
            and observer.get("enabled") is False
            and kill.get("exercised") is True
            and kill.get("exercise_receipt_ref")
            and "production coverage unestablished" in limits
        ):
            return []
    if state == "BLOCKED" and record.get("block_reason") == "NO_EXECUTION_SUBSTRATE":
        return []
    return ["UPSTREAM_VERIFIER_REJECTED"]


class WatchCommissionAdapterTests(unittest.TestCase):
    def manifest(self) -> MissionManifest:
        return MissionManifest.from_dict(clone_payload())

    def test_blocked_no_substrate_is_retained_without_adapter_dispatch(self) -> None:
        record = base_commission()
        record["state"] = "BLOCKED"
        record["block_reason"] = "NO_EXECUTION_SUBSTRATE"
        record["block_evidence"] = {
            "detail": "no persistent provider is available",
            "observed_at": "2026-08-07T12:00:00Z",
            "receipt_ref": "external-discovery://none/1",
        }
        accepted = accept_external_commission(record, strict_fixture_verifier)
        updated = retain_commission(self.manifest(), accepted)
        self.assertEqual(updated.continuity["watch_commissions"][0]["state"], "BLOCKED")

    def test_prepared_mechanism_remains_blocked_until_kill_switch_proven(self) -> None:
        adapter = FakeAdapter()
        prepared = prepare_disabled(base_commission(), adapter, strict_fixture_verifier)
        self.assertEqual(prepared.status, "VERIFIED_EXTERNAL_CONTRACT")
        self.assertEqual(prepared.record["state"], "BLOCKED")
        self.assertEqual(prepared.record["block_reason"], "KILL_SWITCH_UNPROVEN")
        inert = exercise_kill_switch(prepared, adapter, strict_fixture_verifier)
        self.assertEqual(inert.record["state"], "INERT")
        self.assertEqual(inert.status, "VERIFIED_EXTERNAL_CONTRACT")

    def test_steward_cannot_synthesize_proven_without_upstream_verifier(self) -> None:
        record = base_commission()
        record["state"] = "PROVEN"
        unverified = accept_external_commission(record, None)
        self.assertEqual(unverified.status, "UNVERIFIED_EXTERNAL_CONTRACT")
        with self.assertRaisesRegex(CommissionIntegrationError, "UNVERIFIED_EXTERNAL_CONTRACT"):
            retain_commission(self.manifest(), unverified)

    def test_rejected_external_record_is_not_retained(self) -> None:
        rejected = accept_external_commission(base_commission(), lambda record: ["REJECTED"])
        self.assertEqual(rejected.status, "REJECTED_EXTERNAL_CONTRACT")
        with self.assertRaises(CommissionIntegrationError):
            retain_commission(self.manifest(), rejected)

    def test_crossing_event_reopens_mission_frontier(self) -> None:
        payload = clone_payload()
        payload["revision"] = 5
        payload["state"]["status"] = "completed"
        payload["continuity"]["prior_checkpoint"] = "checkpoint:4"
        payload["integrity"]["completion_acceptor"] = "reviewer:test"
        payload["continuity"]["watch_commissions"] = [
            {
                "commission_id": "wc-1",
                "state": "PROVEN",
                "external_observer": {"enabled": True},
            }
        ]
        manifest = MissionManifest.from_dict(payload)
        reopened = handle_crossing_event(
            manifest,
            {
                "commission_id": "wc-1",
                "event_ref": "external-event://1",
                "observed_at": "2026-08-07T13:00:00Z",
            },
        )
        self.assertEqual(reopened.state["status"], "active")
        self.assertIn("triage crossing for commission wc-1", reopened.state["current_frontier"])

    def test_crossing_requires_a_retained_commission(self) -> None:
        payload = clone_payload()
        payload["revision"] = 5
        payload["state"]["status"] = "completed"
        payload["continuity"]["prior_checkpoint"] = "checkpoint:4"
        payload["integrity"]["completion_acceptor"] = "reviewer:test"
        manifest = MissionManifest.from_dict(payload)
        with self.assertRaisesRegex(CommissionIntegrationError, "COMMISSION_NOT_RETAINED"):
            handle_crossing_event(
                manifest,
                {
                    "commission_id": "missing",
                    "event_ref": "external-event://1",
                    "observed_at": "2026-08-07T13:00:00Z",
                },
            )

    def test_crossing_requires_an_operating_retained_commission(self) -> None:
        payload = clone_payload()
        payload["revision"] = 5
        payload["state"]["status"] = "completed"
        payload["continuity"]["prior_checkpoint"] = "checkpoint:4"
        payload["integrity"]["completion_acceptor"] = "reviewer:test"
        payload["continuity"]["watch_commissions"] = [
            {
                "commission_id": "wc-1",
                "state": "BLOCKED",
                "external_observer": {"enabled": False},
            }
        ]
        manifest = MissionManifest.from_dict(payload)
        with self.assertRaisesRegex(CommissionIntegrationError, "COMMISSION_NOT_OPERATING"):
            handle_crossing_event(
                manifest,
                {
                    "commission_id": "wc-1",
                    "event_ref": "external-event://1",
                    "observed_at": "2026-08-07T13:00:00Z",
                },
            )

    def test_revocation_disables_retained_mechanisms(self) -> None:
        payload = clone_payload()
        payload["authority"]["revoked"] = True
        payload["authority"]["revocation_reason"] = "operator stop"
        payload["state"]["status"] = "cancelled"
        record = base_commission()
        record["state"] = "PROVEN"
        record["external_observer"]["mechanism_ref"] = "fixture://watch/1"
        record["external_observer"]["enabled"] = True
        record["proof"]["alert_received"] = True
        payload["continuity"]["watch_commissions"] = [record]
        adapter = FakeAdapter()
        updated, receipts = disable_commissions_for_revocation(
            MissionManifest.from_dict(payload), adapter
        )
        self.assertEqual(adapter.disabled, ["fixture://watch/1"])
        self.assertTrue(receipts[0]["disabled"])
        retained = updated.continuity["watch_commissions"][0]
        self.assertEqual(retained["state"], "INERT")
        self.assertFalse(retained["external_observer"]["enabled"])
        self.assertTrue(retained["proof"]["alert_received"])


if __name__ == "__main__":
    unittest.main()
