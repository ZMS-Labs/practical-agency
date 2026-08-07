"""Watch-commission custody — never a second semantic verifier."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Protocol


class UnverifiedExternalContract(RuntimeError):
    """Raised when PROVEN is claimed without an upstream verifier."""


class WatchExecutionAdapter(Protocol):
    def prepare_disabled(self, commission: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def exercise_kill_switch(self, mechanism_ref: str) -> Mapping[str, Any]: ...
    def enable_for_proof(self, mechanism_ref: str, authority_ref: str) -> Mapping[str, Any]: ...
    def perform_safe_crossing(
        self, mechanism_ref: str, proof_spec: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...
    def disable(self, mechanism_ref: str) -> Mapping[str, Any]: ...


Verifier = Callable[[dict[str, Any]], dict[str, Any]]


class FakeWatchExecutionAdapter:
    def __init__(self, force_success: bool = False) -> None:
        self.force_success = force_success
        self.calls: list[str] = []

    def prepare_disabled(self, commission: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append("prepare_disabled")
        return {
            "mechanism_ref": "fixture:observer",
            "receipt_ref": "receipt:prepare",
            "fixture_scope": "isolated-test",
            "unestablished_production_coverage": True,
        }

    def exercise_kill_switch(self, mechanism_ref: str) -> Mapping[str, Any]:
        self.calls.append("exercise_kill_switch")
        return {
            "mechanism_ref": mechanism_ref,
            "receipt_ref": "receipt:kill-switch",
            "stopped": True,
        }

    def enable_for_proof(self, mechanism_ref: str, authority_ref: str) -> Mapping[str, Any]:
        self.calls.append("enable_for_proof")
        return {
            "mechanism_ref": mechanism_ref,
            "authority_ref": authority_ref,
            "receipt_ref": "receipt:enable",
            "success": self.force_success,
        }

    def perform_safe_crossing(
        self, mechanism_ref: str, proof_spec: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        self.calls.append("perform_safe_crossing")
        return {
            "mechanism_ref": mechanism_ref,
            "proof_spec": dict(proof_spec),
            "receipt_ref": "receipt:crossing",
            "success": self.force_success,
        }

    def disable(self, mechanism_ref: str) -> Mapping[str, Any]:
        self.calls.append("disable")
        return {"mechanism_ref": mechanism_ref, "receipt_ref": "receipt:disable"}


class MissionWatchCustody:
    def __init__(
        self,
        adapter: WatchExecutionAdapter | None,
        verifier: Verifier | None,
    ) -> None:
        self.adapter = adapter
        self.verifier = verifier
        self._records: dict[str, dict[str, Any]] = {}
        self.dispatch_count = 0

    def retain(self, commission: Mapping[str, Any]) -> dict[str, Any]:
        record = dict(commission)
        # Refuse self-asserted skill persistence masquerading as external evidence.
        mechanism = str(record.get("mechanism_ref") or "")
        if "SKILL.md" in mechanism or mechanism.startswith("skill:"):
            raise ValueError("SELF_ASSERTED_SKILL_PERSISTENCE: refused")
        self._records[str(record["commission_id"])] = record
        return record

    def prepare(self, commission: Mapping[str, Any]) -> dict[str, Any]:
        if self.adapter is None:
            raise UnverifiedExternalContract("NO_ADAPTER")
        self.dispatch_count += 1
        result = self.adapter.prepare_disabled(commission)
        record = dict(commission)
        record["mechanism_ref"] = result["mechanism_ref"]
        record["state"] = "BLOCKED"
        record["block_reason"] = "KILL_SWITCH_UNPROVEN"
        record["block_evidence"] = {
            "detail": "mechanism prepared disabled; kill switch not yet exercised",
            "observed_at": "2026-08-07T00:00:00Z",
            "receipt_ref": result["receipt_ref"],
        }
        if result.get("fixture_scope"):
            record["fixture_scope"] = result["fixture_scope"]
        self._records[str(record["commission_id"])] = record
        return record

    def exercise_kill_switch(self, commission: Mapping[str, Any]) -> dict[str, Any]:
        if self.adapter is None:
            raise UnverifiedExternalContract("NO_ADAPTER")
        mechanism_ref = str(commission.get("mechanism_ref") or "")
        self.dispatch_count += 1
        result = self.adapter.exercise_kill_switch(mechanism_ref)
        record = dict(commission)
        record["state"] = "INERT"
        record["block_reason"] = None
        record["block_evidence"] = {}
        proof = dict(record.get("proof") or {})
        proof["kill_switch_receipt"] = result["receipt_ref"]
        record["proof"] = proof
        self._records[str(record["commission_id"])] = record
        return record

    def claim_proven(self, commission: Mapping[str, Any]) -> dict[str, Any]:
        if self.verifier is None:
            raise UnverifiedExternalContract(
                "UNVERIFIED_EXTERNAL_CONTRACT: upstream verifier required for PROVEN"
            )
        record = dict(commission)
        if self.adapter is not None:
            self.dispatch_count += 1
            self.adapter.enable_for_proof(
                str(record.get("mechanism_ref") or ""),
                "authority:operator",
            )
            self.dispatch_count += 1
            self.adapter.perform_safe_crossing(
                str(record.get("mechanism_ref") or ""),
                {"path": "production"},
            )
        verified = self.verifier(record)
        if verified.get("state") != "PROVEN":
            raise UnverifiedExternalContract("verifier did not accept PROVEN")
        self._records[str(verified["commission_id"])] = dict(verified)
        return dict(verified)

    def crossing_event(self, commission_id: str, detail: str) -> dict[str, Any]:
        if commission_id not in self._records:
            raise KeyError(f"UNKNOWN_COMMISSION: {commission_id}")
        return {
            "kind": "watch_crossing",
            "commission_id": commission_id,
            "detail": detail,
            "reopen_frontier": True,
        }
