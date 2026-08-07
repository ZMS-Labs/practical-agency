from __future__ import annotations

import copy
import unittest
from typing import Any, Mapping

from practical_agency.manifest_model import MissionManifest
from practical_agency.watch_commission import WatchCommissionCustodian
from tests.helpers import active_payload


def blocked_record() -> dict[str, Any]:
    return {
        "schema": "watch-commission@1",
        "commission_id": "wc-001",
        "state": "BLOCKED",
        "block_reason": "NO_EXECUTION_SUBSTRATE",
        "external_observer": {"mechanism_ref": None, "enabled": False},
        "proof": {"alert_received": False},
    }


def declared_record() -> dict[str, Any]:
    record = blocked_record()
    record["state"] = "DECLARED"
    record["block_reason"] = None
    return record


def proven_record() -> dict[str, Any]:
    return {
        "schema": "watch-commission@1",
        "commission_id": "wc-001",
        "state": "PROVEN",
        "block_reason": None,
        "external_observer": {"mechanism_ref": "fixture://watch/1", "enabled": True},
        "proof": {"alert_received": True, "receipt_ref": "fixture://receipt/alert"},
    }


def fake_verifier(record: Mapping[str, Any]) -> list[str]:
    if record.get("schema") != "watch-commission@1":
        return ["INVALID_SCHEMA"]
    state = record.get("state")
    observer = record.get("external_observer")
    proof = record.get("proof")
    if not isinstance(observer, Mapping) or not isinstance(proof, Mapping):
        return ["INVALID_SHAPE"]
    if state == "PROVEN":
        if not observer.get("mechanism_ref") or observer.get("enabled") is not True:
            return ["EXTERNAL_MECHANISM_REQUIRED"]
        if proof.get("alert_received") is not True or not proof.get("receipt_ref"):
            return ["ALERT_RECEIPT_REQUIRED"]
    if state == "BLOCKED" and not record.get("block_reason"):
        return ["BLOCK_REASON_REQUIRED"]
    if state == "INERT" and observer.get("enabled") is not False:
        return ["INERT_MUST_BE_DISABLED"]
    return []


class FakeAdapter:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def prepare_disabled(self, commission: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append("prepare_disabled")
        candidate = copy.deepcopy(dict(commission))
        candidate["state"] = "BLOCKED"
        candidate["block_reason"] = "KILL_SWITCH_UNPROVEN"
        candidate["external_observer"] = {"mechanism_ref": "fixture://watch/1", "enabled": False}
        return {"record": candidate, "receipt_refs": ["fixture://receipt/prepared"]}

    def exercise_kill_switch(self, mechanism_ref: str) -> Mapping[str, Any]:
        self.calls.append("exercise_kill_switch")
        candidate = declared_record()
        candidate["state"] = "INERT"
        candidate["external_observer"] = {"mechanism_ref": mechanism_ref, "enabled": False}
        return {"record": candidate, "receipt_refs": ["fixture://receipt/kill"]}

    def enable_for_proof(self, mechanism_ref: str, authority_ref: str) -> Mapping[str, Any]:
        self.calls.append("enable_for_proof")
        candidate = declared_record()
        candidate["state"] = "INERT"
        candidate["external_observer"] = {"mechanism_ref": mechanism_ref, "enabled": True}
        return {"record": candidate, "receipt_refs": [authority_ref]}

    def perform_safe_crossing(self, mechanism_ref: str, proof_spec: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append("perform_safe_crossing")
        return {"record": proven_record(), "receipt_refs": ["fixture://receipt/proof"]}

    def disable(self, mechanism_ref: str) -> Mapping[str, Any]:
        self.calls.append("disable")
        candidate = proven_record()
        candidate["state"] = "INERT"
        candidate["external_observer"]["enabled"] = False
        return {"record": candidate, "receipt_refs": ["fixture://receipt/disabled"]}


class WatchCommissionAdapterTests(unittest.TestCase):
    def test_blocked_no_substrate_is_retained_without_dispatch(self) -> None:
        adapter = FakeAdapter()
        result = WatchCommissionCustodian(fake_verifier).ingest(blocked_record())
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(adapter.calls, [])

    def test_missing_verifier_is_visible_unverified_state(self) -> None:
        result = WatchCommissionCustodian(None).ingest(blocked_record())
        self.assertEqual(result.status, "UNVERIFIED_EXTERNAL_CONTRACT")
        self.assertTrue(result.errors)

    def test_preparation_remains_blocked_until_kill_switch_proof(self) -> None:
        adapter = FakeAdapter()
        custodian = WatchCommissionCustodian(fake_verifier)
        prepared = custodian.prepare_disabled(declared_record(), adapter)
        self.assertEqual(prepared.status, "BLOCKED")
        self.assertEqual(prepared.record["block_reason"], "KILL_SWITCH_UNPROVEN")
        inert = custodian.exercise_kill_switch(prepared.record, adapter)
        self.assertEqual(inert.status, "INERT")
        self.assertEqual(adapter.calls, ["prepare_disabled", "exercise_kill_switch"])

    def test_proven_is_accepted_only_after_upstream_verifier_accepts(self) -> None:
        custodian = WatchCommissionCustodian(fake_verifier)
        accepted = custodian.ingest(proven_record())
        self.assertEqual(accepted.status, "PROVEN")
        invalid = proven_record()
        invalid["proof"] = {"alert_received": False, "receipt_ref": None}
        rejected = custodian.ingest(invalid)
        self.assertEqual(rejected.status, "REJECTED_EXTERNAL_CONTRACT")
        self.assertIn("ALERT_RECEIPT_REQUIRED", rejected.errors)

    def test_adapter_success_without_candidate_record_cannot_synthesize_proven(self) -> None:
        class BadAdapter(FakeAdapter):
            def perform_safe_crossing(self, mechanism_ref: str, proof_spec: Mapping[str, Any]) -> Mapping[str, Any]:
                return {"status": "completed", "receipt_refs": ["fixture://receipt"]}

        adapter = BadAdapter()
        result = WatchCommissionCustodian(fake_verifier).perform_safe_crossing(
            declared_record(), adapter, proof_spec={"safe": True}
        )
        self.assertEqual(result.status, "REJECTED_EXTERNAL_CONTRACT")
        self.assertIn("EXTERNAL_MECHANISM_REQUIRED", result.errors)
        self.assertEqual(adapter.calls, [])

    def test_crossing_event_reopens_mission_and_binds_commission_id(self) -> None:
        payload = active_payload()
        payload["state"]["status"] = "paused"
        payload["state"]["blockers"] = [{"kind": "pause", "reason": "wait"}]
        payload["continuity"]["watch_commissions"] = [
            {"external_contract_status": "PROVEN", "record": proven_record()}
        ]
        manifest = MissionManifest.from_dict(payload)
        updated = WatchCommissionCustodian(fake_verifier).record_crossing(
            manifest,
            commission_record=proven_record(),
            event_ref="event://crossing/1",
            observed_at="2026-08-07T18:00:00Z",
        )
        self.assertEqual(updated.state["status"], "active")
        event = updated.continuity["watch_commissions"][-1]
        self.assertEqual(event["commission_id"], "wc-001")
        self.assertEqual(event["event_ref"], "event://crossing/1")

    def test_revocation_disables_external_mechanism_without_erasing_proof(self) -> None:
        adapter = FakeAdapter()
        result = WatchCommissionCustodian(fake_verifier).disable_for_revocation(proven_record(), adapter)
        self.assertEqual(result.status, "INERT")
        self.assertEqual(result.record["proof"]["receipt_ref"], "fixture://receipt/alert")
        self.assertEqual(adapter.calls, ["disable"])

    def test_prompt_time_skill_persistence_rejection_is_preserved(self) -> None:
        record = proven_record()
        record["external_observer"]["mechanism_ref"] = "skills/manifest/SKILL.md"

        def rejecting_verifier(candidate: Mapping[str, Any]) -> list[str]:
            if str(candidate["external_observer"]["mechanism_ref"]).endswith("SKILL.md"):
                return ["PROMPT_TIME_ARTIFACT_FORBIDDEN"]
            return fake_verifier(candidate)

        result = WatchCommissionCustodian(rejecting_verifier).ingest(record)
        self.assertEqual(result.status, "REJECTED_EXTERNAL_CONTRACT")
        self.assertIn("PROMPT_TIME_ARTIFACT_FORBIDDEN", result.errors)

    def test_upstream_verifier_cannot_admit_unknown_state(self) -> None:
        record = declared_record()
        record["state"] = "MAGIC"
        result = WatchCommissionCustodian(lambda _record: []).ingest(record)
        self.assertEqual(result.status, "REJECTED_EXTERNAL_CONTRACT")
        self.assertIn("STATE_INVALID", result.errors)

    def test_crossing_requires_a_current_proven_commission(self) -> None:
        manifest = MissionManifest.from_dict(active_payload())
        with self.assertRaisesRegex(ValueError, "WATCH_COMMISSION_NOT_PROVEN"):
            WatchCommissionCustodian(fake_verifier).record_crossing(
                manifest,
                commission_record=blocked_record(),
                event_ref="event://crossing/blocked",
                observed_at="2026-08-07T18:00:00Z",
            )

    def test_adapter_cannot_substitute_another_commission(self) -> None:
        class SubstitutingAdapter(FakeAdapter):
            def prepare_disabled(self, commission: Mapping[str, Any]) -> Mapping[str, Any]:
                output = dict(super().prepare_disabled(commission))
                candidate = copy.deepcopy(output["record"])
                candidate["commission_id"] = "wc-other"
                output["record"] = candidate
                return output

        result = WatchCommissionCustodian(fake_verifier).prepare_disabled(
            declared_record(), SubstitutingAdapter()
        )
        self.assertEqual(result.status, "REJECTED_EXTERNAL_CONTRACT")
        self.assertIn("COMMISSION_IDENTITY_MISMATCH", result.errors)

    def test_adapter_exception_is_visible_not_raised(self) -> None:
        class ExplodingAdapter(FakeAdapter):
            def prepare_disabled(self, commission: Mapping[str, Any]) -> Mapping[str, Any]:
                raise RuntimeError("fixture explosion")

        result = WatchCommissionCustodian(fake_verifier).prepare_disabled(
            declared_record(), ExplodingAdapter()
        )
        self.assertEqual(result.status, "ADAPTER_FAILED")
        self.assertTrue(result.errors[0].startswith("ADAPTER_EXCEPTION:RuntimeError"))

    def test_crossing_must_reference_a_commission_retained_by_the_mission(self) -> None:
        manifest = MissionManifest.from_dict(active_payload())
        with self.assertRaisesRegex(ValueError, "WATCH_COMMISSION_NOT_RETAINED"):
            WatchCommissionCustodian(fake_verifier).record_crossing(
                manifest,
                commission_record=proven_record(),
                event_ref="event://crossing/unbound",
                observed_at="2026-08-07T18:00:00Z",
            )

    def test_adapter_receipt_refs_must_be_nonempty_strings(self) -> None:
        class BadReceiptAdapter(FakeAdapter):
            def prepare_disabled(self, commission: Mapping[str, Any]) -> Mapping[str, Any]:
                output = dict(super().prepare_disabled(commission))
                output["receipt_refs"] = [None, ""]
                return output

        result = WatchCommissionCustodian(fake_verifier).prepare_disabled(
            declared_record(), BadReceiptAdapter()
        )
        self.assertEqual(result.status, "REJECTED_EXTERNAL_CONTRACT")
        self.assertIn("ADAPTER_RECEIPTS_INVALID", result.errors)

    def test_crossing_cannot_rebind_retained_commission_subject(self) -> None:
        retained = proven_record()
        retained["subject"] = {"ref": "service:original", "revision": "r1"}
        payload = active_payload()
        payload["continuity"]["watch_commissions"] = [
            {"external_contract_status": "PROVEN", "record": retained}
        ]
        manifest = MissionManifest.from_dict(payload)
        incoming = copy.deepcopy(retained)
        incoming["subject"] = {"ref": "service:other", "revision": "r1"}
        with self.assertRaisesRegex(ValueError, "WATCH_COMMISSION_IDENTITY_MISMATCH"):
            WatchCommissionCustodian(fake_verifier).record_crossing(
                manifest,
                commission_record=incoming,
                event_ref="event://crossing/rebound",
                observed_at="2026-08-07T18:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
