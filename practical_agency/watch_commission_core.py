"""Adapter boundary for externally verified watch-commission@1 records."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from practical_agency.manifest_model import MissionManifest, MissionStatus


class CommissionIntegrationError(RuntimeError):
    """A named refusal to retain or operate an unverified external contract."""


class WatchExecutionAdapter(Protocol):
    def prepare_disabled(self, commission: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def exercise_kill_switch(self, mechanism_ref: str) -> Mapping[str, Any]: ...
    def enable_for_proof(self, mechanism_ref: str, authority_ref: str) -> Mapping[str, Any]: ...
    def perform_safe_crossing(
        self, mechanism_ref: str, proof_spec: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...
    def disable(self, mechanism_ref: str) -> Mapping[str, Any]: ...


Verifier = Callable[[Mapping[str, Any]], list[str]]


@dataclass(frozen=True, slots=True)
class ExternalCommissionResult:
    status: str
    record: dict[str, Any]
    errors: tuple[str, ...]


def accept_external_commission(
    record: Mapping[str, Any], verifier: Verifier | None
) -> ExternalCommissionResult:
    copied = deepcopy(dict(record))
    if verifier is None:
        return ExternalCommissionResult(
            "UNVERIFIED_EXTERNAL_CONTRACT",
            copied,
            ("UPSTREAM_VERIFIER_UNAVAILABLE",),
        )
    try:
        errors = tuple(verifier(copied))
    except Exception as error:  # Fail closed at a package boundary.
        return ExternalCommissionResult(
            "UNVERIFIED_EXTERNAL_CONTRACT",
            copied,
            (f"UPSTREAM_VERIFIER_ERROR:{type(error).__name__}",),
        )
    if errors:
        return ExternalCommissionResult("REJECTED_EXTERNAL_CONTRACT", copied, errors)
    return ExternalCommissionResult("VERIFIED_EXTERNAL_CONTRACT", copied, ())


def _verified_record(
    commission: Mapping[str, Any] | ExternalCommissionResult,
    verifier: Verifier | None,
) -> ExternalCommissionResult:
    if isinstance(commission, ExternalCommissionResult):
        if commission.status != "VERIFIED_EXTERNAL_CONTRACT":
            return commission
        return accept_external_commission(commission.record, verifier)
    return accept_external_commission(commission, verifier)


def _required_receipt_string(
    receipt: Mapping[str, Any], key: str, code: str
) -> str:
    value = receipt.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CommissionIntegrationError(code)
    return value


def prepare_disabled(
    commission: Mapping[str, Any],
    adapter: WatchExecutionAdapter,
    verifier: Verifier | None,
) -> ExternalCommissionResult:
    verified = accept_external_commission(commission, verifier)
    if verified.status != "VERIFIED_EXTERNAL_CONTRACT":
        return verified
    if verified.record.get("state") != "DECLARED":
        return ExternalCommissionResult(
            "REJECTED_EXTERNAL_CONTRACT",
            verified.record,
            ("COMMISSION_MUST_BE_DECLARED_BEFORE_PREPARATION",),
        )

    candidate = deepcopy(verified.record)
    raw_receipt = adapter.prepare_disabled(deepcopy(candidate))
    if not isinstance(raw_receipt, Mapping):
        raise CommissionIntegrationError("PREPARATION_RECEIPT_MUST_BE_OBJECT")
    receipt = deepcopy(dict(raw_receipt))
    mechanism_ref = _required_receipt_string(
        receipt, "mechanism_ref", "ADAPTER_MECHANISM_REF_REQUIRED"
    )
    persistence_ref = _required_receipt_string(
        receipt, "persistence_receipt_ref", "PERSISTENCE_RECEIPT_REQUIRED"
    )
    substrate_kind = _required_receipt_string(
        receipt, "substrate_kind", "SUBSTRATE_KIND_REQUIRED"
    )
    substrate = _required_receipt_string(
        receipt, "substrate", "SUBSTRATE_REQUIRED"
    )
    block_evidence = receipt.get("block_evidence")
    if not isinstance(block_evidence, Mapping) or not all(
        isinstance(block_evidence.get(key), str) and block_evidence.get(key)
        for key in ("detail", "observed_at", "receipt_ref")
    ):
        raise CommissionIntegrationError("BLOCK_EVIDENCE_REQUIRED")
    coverage_limits = receipt.get("coverage_limits")
    if not isinstance(coverage_limits, list) or any(
        not isinstance(item, str) or not item.strip() for item in coverage_limits
    ):
        raise CommissionIntegrationError("COVERAGE_LIMITS_REQUIRED")

    observer = candidate.setdefault("external_observer", {})
    if not isinstance(observer, dict):
        raise CommissionIntegrationError("EXTERNAL_OBSERVER_MUST_BE_OBJECT")
    observer.update(
        {
            "substrate_kind": substrate_kind,
            "substrate": substrate,
            "mechanism_ref": mechanism_ref,
            "persistence_receipt_ref": persistence_ref,
            "persistent_outside_session": True,
            "enabled": False,
        }
    )
    candidate["state"] = "BLOCKED"
    candidate["block_reason"] = "KILL_SWITCH_UNPROVEN"
    candidate["block_evidence"] = deepcopy(dict(block_evidence))
    candidate["coverage_limits"] = deepcopy(coverage_limits)
    return accept_external_commission(candidate, verifier)


def exercise_kill_switch(
    prepared: Mapping[str, Any] | ExternalCommissionResult,
    adapter: WatchExecutionAdapter,
    verifier: Verifier | None,
) -> ExternalCommissionResult:
    verified = _verified_record(prepared, verifier)
    if verified.status != "VERIFIED_EXTERNAL_CONTRACT":
        return verified
    candidate = deepcopy(verified.record)
    if (
        candidate.get("state") != "BLOCKED"
        or candidate.get("block_reason") != "KILL_SWITCH_UNPROVEN"
    ):
        return ExternalCommissionResult(
            "REJECTED_EXTERNAL_CONTRACT",
            candidate,
            ("KILL_SWITCH_EXERCISE_REQUIRES_PREPARED_BLOCKED_COMMISSION",),
        )
    observer = candidate.get("external_observer")
    if not isinstance(observer, Mapping):
        raise CommissionIntegrationError("EXTERNAL_OBSERVER_REQUIRED")
    mechanism_ref = observer.get("mechanism_ref")
    if not isinstance(mechanism_ref, str) or not mechanism_ref:
        raise CommissionIntegrationError("MECHANISM_REF_REQUIRED")
    raw_receipt = adapter.exercise_kill_switch(mechanism_ref)
    if not isinstance(raw_receipt, Mapping):
        raise CommissionIntegrationError("KILL_SWITCH_RECEIPT_MUST_BE_OBJECT")
    receipt = deepcopy(dict(raw_receipt))
    if receipt.get("mechanism_ref") not in {None, mechanism_ref}:
        raise CommissionIntegrationError("KILL_SWITCH_MECHANISM_MISMATCH")
    if receipt.get("observed_stopped") is not True:
        raise CommissionIntegrationError("KILL_SWITCH_NOT_OBSERVED_STOPPED")
    exercise_ref = _required_receipt_string(
        receipt, "exercise_receipt_ref", "KILL_SWITCH_RECEIPT_REQUIRED"
    )

    kill_switch = candidate.setdefault("kill_switch", {})
    if not isinstance(kill_switch, dict):
        raise CommissionIntegrationError("KILL_SWITCH_MUST_BE_OBJECT")
    kill_switch["exercised"] = True
    kill_switch["exercise_receipt_ref"] = exercise_ref
    candidate["state"] = "INERT"
    candidate["block_reason"] = None
    candidate["block_evidence"] = {
        "detail": None,
        "observed_at": None,
        "receipt_ref": None,
    }
    return accept_external_commission(candidate, verifier)


def retain_commission(
    manifest: MissionManifest, result: ExternalCommissionResult
) -> MissionManifest:
    if result.status != "VERIFIED_EXTERNAL_CONTRACT":
        raise CommissionIntegrationError(result.status)
    data = manifest.to_dict()
    commission_id = result.record.get("commission_id")
    if not isinstance(commission_id, str) or not commission_id:
        raise CommissionIntegrationError("COMMISSION_ID_REQUIRED")
    retained = data["continuity"]["watch_commissions"]
    retained[:] = [
        item
        for item in retained
        if not (
            isinstance(item, Mapping) and item.get("commission_id") == commission_id
        )
    ]
    retained.append(deepcopy(result.record))
    data["revision"] = manifest.revision + 1
    return MissionManifest.from_dict(data)
