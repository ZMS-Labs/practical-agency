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


def prepare_disabled(
    commission: Mapping[str, Any], adapter: WatchExecutionAdapter
) -> dict[str, Any]:
    candidate = deepcopy(dict(commission))
    receipt = deepcopy(dict(adapter.prepare_disabled(candidate)))
    mechanism_ref = receipt.get("mechanism_ref")
    if not isinstance(mechanism_ref, str) or not mechanism_ref:
        raise CommissionIntegrationError("ADAPTER_MECHANISM_REF_REQUIRED")
    persistence_ref = receipt.get("persistence_receipt_ref")
    if not isinstance(persistence_ref, str) or not persistence_ref:
        raise CommissionIntegrationError("PERSISTENCE_RECEIPT_REQUIRED")
    block_evidence = receipt.get("block_evidence")
    if not isinstance(block_evidence, Mapping) or not all(
        isinstance(block_evidence.get(key), str) and block_evidence.get(key)
        for key in ("detail", "observed_at", "receipt_ref")
    ):
        raise CommissionIntegrationError("BLOCK_EVIDENCE_REQUIRED")

    observer = candidate.setdefault("external_observer", {})
    if not isinstance(observer, dict):
        raise CommissionIntegrationError("EXTERNAL_OBSERVER_MUST_BE_OBJECT")
    observer.update(
        {
            "substrate_kind": receipt.get("substrate_kind"),
            "substrate": receipt.get("substrate"),
            "mechanism_ref": mechanism_ref,
            "persistence_receipt_ref": persistence_ref,
            "persistent_outside_session": True,
            "enabled": False,
        }
    )
    candidate["state"] = "BLOCKED"
    candidate["block_reason"] = "KILL_SWITCH_UNPROVEN"
    candidate["block_evidence"] = deepcopy(dict(block_evidence))
    candidate["coverage_limits"] = deepcopy(receipt.get("coverage_limits", []))
    return candidate


def exercise_kill_switch(
    prepared: Mapping[str, Any],
    adapter: WatchExecutionAdapter,
    verifier: Verifier | None,
) -> ExternalCommissionResult:
    candidate = deepcopy(dict(prepared))
    observer = candidate.get("external_observer")
    if not isinstance(observer, Mapping):
        raise CommissionIntegrationError("EXTERNAL_OBSERVER_REQUIRED")
    mechanism_ref = observer.get("mechanism_ref")
    if not isinstance(mechanism_ref, str) or not mechanism_ref:
        raise CommissionIntegrationError("MECHANISM_REF_REQUIRED")
    receipt = deepcopy(dict(adapter.exercise_kill_switch(mechanism_ref)))
    if receipt.get("observed_stopped") is not True:
        raise CommissionIntegrationError("KILL_SWITCH_NOT_OBSERVED_STOPPED")
    exercise_ref = receipt.get("exercise_receipt_ref")
    if not isinstance(exercise_ref, str) or not exercise_ref:
        raise CommissionIntegrationError("KILL_SWITCH_RECEIPT_REQUIRED")

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


def handle_crossing_event(
    manifest: MissionManifest, event: Mapping[str, Any]
) -> MissionManifest:
    commission_id = event.get("commission_id")
    event_ref = event.get("event_ref")
    if not isinstance(commission_id, str) or not commission_id:
        raise CommissionIntegrationError("COMMISSION_ID_REQUIRED")
    if not isinstance(event_ref, str) or not event_ref:
        raise CommissionIntegrationError("EVENT_RECEIPT_REQUIRED")
    retained = manifest.continuity.get("watch_commissions", [])
    if not any(
        isinstance(record, Mapping) and record.get("commission_id") == commission_id
        for record in retained
    ):
        raise CommissionIntegrationError("COMMISSION_NOT_RETAINED")

    data = manifest.to_dict()
    data["state"]["status"] = MissionStatus.ACTIVE.value
    frontier = f"triage crossing for commission {commission_id}"
    if frontier not in data["state"]["current_frontier"]:
        data["state"]["current_frontier"].insert(0, frontier)
    data["state"]["next_action"] = frontier
    data["continuity"]["external_handoffs"].append(
        {
            "kind": "watch-crossing",
            "commission_id": commission_id,
            "event_ref": event_ref,
            "observed_at": event.get("observed_at"),
            "hands_to": ["triage", "decision-ledger"],
        }
    )
    data["revision"] = manifest.revision + 1
    return MissionManifest.from_dict(data)


def disable_commissions_for_revocation(
    manifest: MissionManifest, adapter: WatchExecutionAdapter
) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for record in manifest.continuity.get("watch_commissions", []):
        if not isinstance(record, Mapping):
            continue
        observer = record.get("external_observer")
        if not isinstance(observer, Mapping):
            continue
        mechanism_ref = observer.get("mechanism_ref")
        if isinstance(mechanism_ref, str) and mechanism_ref:
            result = adapter.disable(mechanism_ref)
            if not isinstance(result, Mapping):
                raise CommissionIntegrationError("DISABLE_RECEIPT_MUST_BE_OBJECT")
            receipts.append(deepcopy(dict(result)))
    return receipts
