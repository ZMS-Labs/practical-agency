"""Shared validation and contract types for mission-state transitions."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from practical_agency.manifest_model import MissionManifest

class TransitionError(RuntimeError):
    """Named refusal for an invalid mission transition."""


MISSION_STEWARD_REF = "mission-steward"
_EVENT_SCHEMA = "mission-event@1"
_EXECUTION_RECEIPT_FIELDS = {
    "schema",
    "request_id",
    "mission_id",
    "mission_revision",
    "adapter_ref",
    "status",
    "artifact_refs",
    "observed_effects",
    "external_receipt_ref",
    "coverage_limits",
}
_RESULT_STATUSES = {"completed", "declined", "blocked", "failed"}


@dataclass(frozen=True, slots=True)
class MissionEvent:
    schema: str
    event_id: str
    mission_id: str
    expected_revision: int
    kind: str
    actor_ref: str
    data: Mapping[str, Any]
    observed_at: str


def _required_string(data: Mapping[str, Any], key: str, code: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TransitionError(code)
    return value


def _string_list(
    data: Mapping[str, Any], key: str, code: str, *, non_empty: bool = False
) -> list[str]:
    value = data.get(key)
    if (
        not isinstance(value, list)
        or (non_empty and not value)
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise TransitionError(code)
    return list(value)


def _operator_only(manifest: MissionManifest, event: MissionEvent) -> None:
    if event.actor_ref != manifest.authority.get("operator_ref"):
        raise TransitionError("OPERATOR_AUTHORITY_REQUIRED")


def _require_mission_steward(event: MissionEvent) -> None:
    if event.actor_ref != MISSION_STEWARD_REF:
        raise TransitionError("MISSION_STEWARD_REQUIRED")


def _append_unique(target: list[Any], value: Any) -> None:
    if value not in target:
        target.append(deepcopy(value))


def _material_workers(data: Mapping[str, Any]) -> set[str]:
    workers: set[str] = set()
    decisions = data.get("continuity", {}).get("decisions", [])
    for item in decisions:
        if isinstance(item, Mapping) and item.get("kind") == "material-action":
            actor = item.get("actor_ref")
            if isinstance(actor, str):
                workers.add(actor)
    return workers


def _require_independent_acceptor(
    data: Mapping[str, Any], event: MissionEvent
) -> None:
    acceptor = data.get("integrity", {}).get("completion_acceptor")
    if event.actor_ref != acceptor or event.actor_ref in _material_workers(data):
        raise TransitionError("INDEPENDENT_ACCEPTANCE_REQUIRED")


def _required_proof_refs(data: Mapping[str, Any]) -> list[str]:
    return list(data["outcome"]["completion_proof"]) + list(
        data["integrity"]["required_gates"]
    )


def _missing_proof_refs(data: Mapping[str, Any]) -> list[str]:
    present = set(data["continuity"]["durable_artifacts"])
    return [ref for ref in _required_proof_refs(data) if ref not in present]


def _acceptance_evidence(payload: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    evidence_refs = _string_list(
        payload, "evidence_refs", "ACCEPTANCE_EVIDENCE_REQUIRED", non_empty=True
    )
    coverage_limits = _string_list(
        payload, "coverage_limits", "ACCEPTANCE_COVERAGE_LIMITS_REQUIRED"
    )
    return evidence_refs, coverage_limits


def _reconciliation_subject(marker: object) -> str | None:
    if not isinstance(marker, str) or not marker.startswith("RECONCILIATION:"):
        return None
    parts = marker.split(":", 2)
    return parts[2] if len(parts) == 3 and parts[2] else None


def _event_seen(manifest: MissionManifest, event_id: str) -> bool:
    return any(
        isinstance(item, Mapping)
        and item.get("kind") == "mission-event-apply"
        and item.get("event_id") == event_id
        for item in manifest.continuity.get("decisions", [])
    )


def _validate_event_envelope(
    manifest: MissionManifest, event: MissionEvent
) -> None:
    if event.schema != _EVENT_SCHEMA:
        raise TransitionError("INVALID_EVENT_SCHEMA")
    if not isinstance(event.event_id, str) or not event.event_id.strip():
        raise TransitionError("EVENT_ID_REQUIRED")
    if _event_seen(manifest, event.event_id):
        raise TransitionError("EVENT_ALREADY_APPLIED")
    if event.mission_id != manifest.mission_id:
        raise TransitionError("EVENT_MISSION_MISMATCH")
    if (
        isinstance(event.expected_revision, bool)
        or not isinstance(event.expected_revision, int)
        or event.expected_revision != manifest.revision
    ):
        raise TransitionError("EVENT_REVISION_MISMATCH")
    if not isinstance(event.kind, str) or not event.kind.strip():
        raise TransitionError("EVENT_KIND_REQUIRED")
    if not isinstance(event.actor_ref, str) or not event.actor_ref.strip():
        raise TransitionError("EVENT_ACTOR_REQUIRED")
    if not isinstance(event.data, Mapping):
        raise TransitionError("EVENT_DATA_MUST_BE_OBJECT")
    if not isinstance(event.observed_at, str) or not event.observed_at.strip():
        raise TransitionError("EVENT_OBSERVED_AT_REQUIRED")


def _execution_receipt(
    manifest: MissionManifest, payload: Mapping[str, Any]
) -> dict[str, Any]:
    raw = payload.get("receipt")
    if not isinstance(raw, Mapping):
        raise TransitionError("EXECUTION_RECEIPT_REQUIRED")
    receipt = deepcopy(dict(raw))
    if set(receipt) != _EXECUTION_RECEIPT_FIELDS:
        raise TransitionError("INVALID_EXECUTION_RECEIPT:fields")
    if receipt.get("schema") != "execution-receipt@1":
        raise TransitionError("INVALID_EXECUTION_RECEIPT:schema")
    request_id = receipt.get("request_id")
    if (
        not isinstance(request_id, str)
        or not request_id.startswith(
            f"{manifest.mission_id}:r{manifest.revision}:"
        )
    ):
        raise TransitionError("EXECUTION_RECEIPT_REQUEST_MISMATCH")
    if receipt.get("mission_id") != manifest.mission_id:
        raise TransitionError("EXECUTION_RECEIPT_MISSION_MISMATCH")
    if receipt.get("mission_revision") != manifest.revision:
        raise TransitionError("EXECUTION_RECEIPT_REVISION_MISMATCH")
    if not isinstance(receipt.get("adapter_ref"), str) or not receipt[
        "adapter_ref"
    ].strip():
        raise TransitionError("INVALID_EXECUTION_RECEIPT:adapter_ref")
    if receipt.get("status") not in _RESULT_STATUSES:
        raise TransitionError("INVALID_EXECUTION_RECEIPT:status")
    for field in ("artifact_refs", "coverage_limits"):
        value = receipt.get(field)
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            raise TransitionError(f"INVALID_EXECUTION_RECEIPT:{field}")
    if not isinstance(receipt.get("observed_effects"), list):
        raise TransitionError("INVALID_EXECUTION_RECEIPT:observed_effects")
    external_ref = receipt.get("external_receipt_ref")
    if external_ref is not None and (
        not isinstance(external_ref, str) or not external_ref.strip()
    ):
        raise TransitionError("INVALID_EXECUTION_RECEIPT:external_receipt_ref")
    if receipt.get("status") == "completed" and not isinstance(
        external_ref, str
    ):
        raise TransitionError("EXTERNAL_EXECUTION_RECEIPT_REQUIRED")
    return receipt
