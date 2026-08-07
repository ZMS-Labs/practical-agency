"""Custody bridge for upstream watch-commission@1 records.

Practical Agency never reimplements the upstream promotion oracle. It preserves a
candidate only after the supplied verifier accepts it, and otherwise records a
visible degraded or rejected state. Adapter operations may change runtime and
evidence fields, but they may not substitute another commission or mutate the
commission's epistemic identity.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from .manifest_model import MissionManifest

Verifier = Callable[[Mapping[str, Any]], list[str]]
UPSTREAM_STATES = {"DECLARED", "BLOCKED", "INERT", "PROVEN", "SUSPECT"}
_REJECTED_STATES = {"REJECTED_EXTERNAL_CONTRACT", "UNVERIFIED_EXTERNAL_CONTRACT"}
_IDENTITY_FIELDS = ("schema", "commission_id", "subject", "bound", "probe", "handoff")


class WatchExecutionAdapter(Protocol):
    def prepare_disabled(self, commission: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def exercise_kill_switch(self, mechanism_ref: str) -> Mapping[str, Any]: ...

    def enable_for_proof(self, mechanism_ref: str, authority_ref: str) -> Mapping[str, Any]: ...

    def perform_safe_crossing(
        self, mechanism_ref: str, proof_spec: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    def disable(self, mechanism_ref: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class WatchIntakeResult:
    status: str
    record: dict[str, Any]
    errors: tuple[str, ...]
    adapter_receipts: tuple[str, ...] = ()


class WatchCommissionCustodian:
    def __init__(self, verifier: Verifier | None) -> None:
        self.verifier = verifier

    def ingest(self, record: Mapping[str, Any]) -> WatchIntakeResult:
        if not isinstance(record, Mapping):
            return WatchIntakeResult(
                "REJECTED_EXTERNAL_CONTRACT", {}, ("RECORD_MUST_BE_OBJECT",)
            )
        candidate = copy.deepcopy(dict(record))
        if self.verifier is None:
            return WatchIntakeResult(
                "UNVERIFIED_EXTERNAL_CONTRACT",
                candidate,
                ("UPSTREAM_VERIFIER_UNAVAILABLE",),
            )
        try:
            verifier_output = self.verifier(candidate)
            if not isinstance(verifier_output, list) or not all(
                isinstance(item, str) for item in verifier_output
            ):
                raise TypeError("verifier must return list[str]")
            errors = tuple(verifier_output)
        except Exception as error:  # noqa: BLE001 - external verifier is an adapter boundary
            return WatchIntakeResult(
                "UNVERIFIED_EXTERNAL_CONTRACT",
                candidate,
                (f"UPSTREAM_VERIFIER_FAILED:{type(error).__name__}",),
            )
        if errors:
            return WatchIntakeResult("REJECTED_EXTERNAL_CONTRACT", candidate, errors)
        state = candidate.get("state")
        if not isinstance(state, str):
            return WatchIntakeResult(
                "REJECTED_EXTERNAL_CONTRACT", candidate, ("STATE_REQUIRED",)
            )
        if state not in UPSTREAM_STATES:
            return WatchIntakeResult(
                "REJECTED_EXTERNAL_CONTRACT", candidate, ("STATE_INVALID",)
            )
        return WatchIntakeResult(state, candidate, ())

    @staticmethod
    def _identity_errors(
        prior_record: Mapping[str, Any], candidate: Mapping[str, Any]
    ) -> tuple[str, ...]:
        for field in _IDENTITY_FIELDS:
            if prior_record.get(field) != candidate.get(field):
                return ("COMMISSION_IDENTITY_MISMATCH",)
        prior_destination = prior_record.get("destination")
        candidate_destination = candidate.get("destination")
        prior_ref = prior_destination.get("ref") if isinstance(prior_destination, Mapping) else None
        candidate_ref = (
            candidate_destination.get("ref")
            if isinstance(candidate_destination, Mapping)
            else None
        )
        if prior_ref != candidate_ref:
            return ("COMMISSION_IDENTITY_MISMATCH",)
        return ()

    def _apply_adapter_output(
        self, prior_record: Mapping[str, Any], output: Mapping[str, Any]
    ) -> WatchIntakeResult:
        if not isinstance(output, Mapping):
            return WatchIntakeResult(
                "REJECTED_EXTERNAL_CONTRACT",
                copy.deepcopy(dict(prior_record)),
                ("ADAPTER_OUTPUT_MUST_BE_OBJECT",),
            )
        record = output.get("record")
        receipt_refs = output.get("receipt_refs", ())
        if not isinstance(receipt_refs, (list, tuple)) or not all(
            isinstance(item, str) and bool(item.strip()) for item in receipt_refs
        ):
            return WatchIntakeResult(
                "REJECTED_EXTERNAL_CONTRACT",
                copy.deepcopy(dict(prior_record)),
                ("ADAPTER_RECEIPTS_INVALID",),
            )
        receipts = tuple(receipt_refs)
        if not isinstance(record, Mapping):
            return WatchIntakeResult(
                "REJECTED_EXTERNAL_CONTRACT",
                copy.deepcopy(dict(prior_record)),
                ("ADAPTER_CANDIDATE_RECORD_REQUIRED",),
                receipts,
            )
        candidate = copy.deepcopy(dict(record))
        identity_errors = self._identity_errors(prior_record, candidate)
        if identity_errors:
            return WatchIntakeResult(
                "REJECTED_EXTERNAL_CONTRACT", candidate, identity_errors, receipts
            )
        result = self.ingest(candidate)
        return WatchIntakeResult(result.status, result.record, result.errors, receipts)

    def _invoke_adapter(
        self,
        prior_record: Mapping[str, Any],
        operation: Callable[[], Mapping[str, Any]],
    ) -> WatchIntakeResult:
        try:
            output = operation()
        except Exception as error:  # noqa: BLE001 - adapter is an external boundary
            return WatchIntakeResult(
                "ADAPTER_FAILED",
                copy.deepcopy(dict(prior_record)),
                (f"ADAPTER_EXCEPTION:{type(error).__name__}",),
            )
        return self._apply_adapter_output(prior_record, output)

    @staticmethod
    def _mechanism_ref(record: Mapping[str, Any]) -> str | None:
        observer = record.get("external_observer")
        if not isinstance(observer, Mapping):
            return None
        value = observer.get("mechanism_ref")
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _retained_commission_records(
        manifest: MissionManifest,
    ) -> dict[str, Mapping[str, Any]]:
        retained: dict[str, Mapping[str, Any]] = {}
        for entry in manifest.continuity["watch_commissions"]:
            if not isinstance(entry, Mapping):
                continue
            nested = entry.get("record")
            if not isinstance(nested, Mapping):
                continue
            nested_id = nested.get("commission_id")
            if isinstance(nested_id, str) and nested_id:
                retained[nested_id] = nested
        return retained

    def prepare_disabled(
        self, record: Mapping[str, Any], adapter: WatchExecutionAdapter
    ) -> WatchIntakeResult:
        initial = self.ingest(record)
        if initial.status in _REJECTED_STATES:
            return initial
        return self._invoke_adapter(
            initial.record, lambda: adapter.prepare_disabled(initial.record)
        )

    def exercise_kill_switch(
        self, record: Mapping[str, Any], adapter: WatchExecutionAdapter
    ) -> WatchIntakeResult:
        initial = self.ingest(record)
        if initial.status in _REJECTED_STATES:
            return initial
        mechanism_ref = self._mechanism_ref(initial.record)
        if mechanism_ref is None:
            return WatchIntakeResult(
                "REJECTED_EXTERNAL_CONTRACT",
                initial.record,
                ("EXTERNAL_MECHANISM_REQUIRED",),
            )
        return self._invoke_adapter(
            initial.record, lambda: adapter.exercise_kill_switch(mechanism_ref)
        )

    def enable_for_proof(
        self,
        record: Mapping[str, Any],
        adapter: WatchExecutionAdapter,
        *,
        authority_ref: str,
    ) -> WatchIntakeResult:
        initial = self.ingest(record)
        if initial.status in _REJECTED_STATES:
            return initial
        mechanism_ref = self._mechanism_ref(initial.record)
        if mechanism_ref is None:
            return WatchIntakeResult(
                "REJECTED_EXTERNAL_CONTRACT", initial.record, ("EXTERNAL_MECHANISM_REQUIRED",)
            )
        if not isinstance(authority_ref, str) or not authority_ref.strip():
            return WatchIntakeResult(
                "REJECTED_EXTERNAL_CONTRACT", initial.record, ("AUTHORITY_RECEIPT_REQUIRED",)
            )
        return self._invoke_adapter(
            initial.record,
            lambda: adapter.enable_for_proof(mechanism_ref, authority_ref),
        )

    def perform_safe_crossing(
        self,
        record: Mapping[str, Any],
        adapter: WatchExecutionAdapter,
        *,
        proof_spec: Mapping[str, Any],
    ) -> WatchIntakeResult:
        initial = self.ingest(record)
        if initial.status in _REJECTED_STATES:
            return initial
        mechanism_ref = self._mechanism_ref(initial.record)
        if mechanism_ref is None:
            return WatchIntakeResult(
                "REJECTED_EXTERNAL_CONTRACT",
                initial.record,
                ("EXTERNAL_MECHANISM_REQUIRED",),
            )
        if not isinstance(proof_spec, Mapping):
            return WatchIntakeResult(
                "REJECTED_EXTERNAL_CONTRACT", initial.record, ("PROOF_SPEC_REQUIRED",)
            )
        proof_copy = copy.deepcopy(dict(proof_spec))
        return self._invoke_adapter(
            initial.record,
            lambda: adapter.perform_safe_crossing(mechanism_ref, proof_copy),
        )

    def disable_for_revocation(
        self, record: Mapping[str, Any], adapter: WatchExecutionAdapter
    ) -> WatchIntakeResult:
        initial = self.ingest(record)
        if initial.status in _REJECTED_STATES:
            return initial
        mechanism_ref = self._mechanism_ref(initial.record)
        if mechanism_ref is None:
            return WatchIntakeResult(
                "REJECTED_EXTERNAL_CONTRACT", initial.record, ("EXTERNAL_MECHANISM_REQUIRED",)
            )
        return self._invoke_adapter(
            initial.record, lambda: adapter.disable(mechanism_ref)
        )

    def record_crossing(
        self,
        manifest: MissionManifest,
        *,
        commission_record: Mapping[str, Any],
        event_ref: str,
        observed_at: str,
    ) -> MissionManifest:
        if manifest.authority["revoked"] or manifest.state["status"] == "cancelled":
            raise ValueError("MISSION_AUTHORITY_REVOKED: crossing cannot resume a cancelled mission")
        accepted = self.ingest(commission_record)
        if accepted.status in _REJECTED_STATES:
            raise ValueError(
                "WATCH_COMMISSION_NOT_ACCEPTED: " + "; ".join(accepted.errors)
            )
        if accepted.status != "PROVEN":
            raise ValueError(
                f"WATCH_COMMISSION_NOT_PROVEN: current state is {accepted.status}"
            )
        commission_id = accepted.record.get("commission_id")
        if not isinstance(commission_id, str) or not commission_id:
            raise ValueError("COMMISSION_ID_REQUIRED: crossing cannot be correlated")
        retained_record = self._retained_commission_records(manifest).get(commission_id)
        if retained_record is None:
            raise ValueError(
                "WATCH_COMMISSION_NOT_RETAINED: mission has no custody record for commission"
            )
        if self._identity_errors(retained_record, accepted.record):
            raise ValueError(
                "WATCH_COMMISSION_IDENTITY_MISMATCH: crossing changed retained commission identity"
            )
        if (
            not isinstance(event_ref, str)
            or not event_ref.strip()
            or not isinstance(observed_at, str)
            or not observed_at.strip()
        ):
            raise ValueError("CROSSING_RECEIPT_REQUIRED: event ref and observation time are required")

        payload = manifest.to_dict()
        payload["revision"] = manifest.revision + 1
        event = {
            "kind": "watch-crossing",
            "commission_id": commission_id,
            "commission_state": accepted.status,
            "event_ref": event_ref,
            "observed_at": observed_at,
        }
        payload["continuity"]["watch_commissions"].append(event)
        payload["continuity"]["decisions"].append(
            {"kind": "mission-reopened-by-watch", "revision": payload["revision"], **event}
        )
        payload["state"]["status"] = "active"
        payload["state"]["blockers"] = []
        payload["state"]["current_frontier"] = [
            f"respond to watch crossing {commission_id}"
        ]
        payload["state"]["next_action"] = f"respond to watch crossing {commission_id}"
        payload["integrity"]["completion_acceptor"] = None
        payload["integrity"]["acceptance_receipt_ref"] = None
        return MissionManifest.from_dict(payload)
