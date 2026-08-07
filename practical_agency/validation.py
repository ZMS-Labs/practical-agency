"""Fail-closed semantic validation for mission-manifest@1."""
from __future__ import annotations

from typing import Any, Mapping

from practical_agency.manifest_model import MissionStatus

TOP_LEVEL = {
    "schema",
    "mission_id",
    "revision",
    "authority",
    "outcome",
    "truth",
    "state",
    "capabilities",
    "continuity",
    "integrity",
}

OBJECT_KEYS: dict[str, set[str]] = {
    "authority": {
        "operator_ref",
        "instruction",
        "amendments",
        "permissions",
        "protected_state",
        "acceptable_costs",
        "escalation_required_for",
        "revoked",
        "revocation_reason",
    },
    "outcome": {
        "desired_state",
        "completion_proof",
        "integrity_guards",
        "scope_proof",
        "stop_conditions",
    },
    "truth": {
        "subject_refs",
        "verified_facts",
        "assumptions",
        "contradictions",
        "unknowns",
    },
    "state": {
        "status",
        "completed_actions",
        "current_frontier",
        "blockers",
        "next_action",
    },
    "capabilities": {
        "discovered_at",
        "available",
        "invoked",
        "unavailable",
        "degraded",
    },
    "continuity": {
        "prior_checkpoint",
        "durable_artifacts",
        "decisions",
        "external_handoffs",
        "watch_commissions",
    },
    "integrity": {
        "actor_may_self_accept",
        "required_gates",
        "unresolved_verdicts",
        "completion_acceptor",
    },
}

LIST_FIELDS: dict[str, set[str]] = {
    "authority": {
        "amendments",
        "permissions",
        "protected_state",
        "acceptable_costs",
        "escalation_required_for",
    },
    "outcome": {
        "completion_proof",
        "integrity_guards",
        "scope_proof",
        "stop_conditions",
    },
    "truth": {
        "subject_refs",
        "verified_facts",
        "assumptions",
        "contradictions",
        "unknowns",
    },
    "state": {"completed_actions", "current_frontier", "blockers"},
    "capabilities": {"available", "invoked", "unavailable", "degraded"},
    "continuity": {
        "durable_artifacts",
        "decisions",
        "external_handoffs",
        "watch_commissions",
    },
    "integrity": {"required_gates", "unresolved_verdicts"},
}


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _unknown_keys(
    errors: list[str], prefix: str, payload: Mapping[str, Any], allowed: set[str]
) -> None:
    for key in sorted(set(payload) - allowed):
        path = f"{prefix}.{key}" if prefix else key
        errors.append(f"UNKNOWN_FIELD: {path} is not allowed")


def _all_nonempty_strings(value: object) -> bool:
    return isinstance(value, list) and all(_nonempty_string(item) for item in value)


def validate_manifest_dict(payload: Mapping[str, Any] | object) -> list[str]:
    if not isinstance(payload, Mapping):
        return ["RECORD_MUST_BE_OBJECT: root must be an object"]

    errors: list[str] = []
    _unknown_keys(errors, "", payload, TOP_LEVEL)
    for required in sorted(TOP_LEVEL - set(payload)):
        errors.append(f"MISSING_FIELD: {required} is required")

    if payload.get("schema") != "mission-manifest@1":
        errors.append("INVALID_SCHEMA: schema must equal mission-manifest@1")
    if not _nonempty_string(payload.get("mission_id")):
        errors.append("MISSION_ID_REQUIRED: mission_id must be non-empty")

    revision = payload.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        errors.append("INVALID_REVISION: revision must be a positive integer")

    governed: dict[str, Mapping[str, Any]] = {}
    for name, allowed in OBJECT_KEYS.items():
        value = payload.get(name)
        if not isinstance(value, Mapping):
            errors.append(f"INVALID_OBJECT: {name} must be an object")
            continue
        governed[name] = value
        _unknown_keys(errors, name, value, allowed)
        for required in sorted(allowed - set(value)):
            errors.append(f"MISSING_FIELD: {name}.{required} is required")
        for field in LIST_FIELDS.get(name, set()):
            if field in value and not isinstance(value[field], list):
                errors.append(f"INVALID_LIST: {name}.{field} must be an array")

    authority = governed.get("authority", {})
    outcome = governed.get("outcome", {})
    truth = governed.get("truth", {})
    state = governed.get("state", {})
    continuity = governed.get("continuity", {})
    integrity = governed.get("integrity", {})

    if not _nonempty_string(authority.get("operator_ref")):
        errors.append("OPERATOR_REQUIRED: authority.operator_ref must be non-empty")
    if not _nonempty_string(authority.get("instruction")):
        errors.append("INSTRUCTION_REQUIRED: authority.instruction must be non-empty")
    if authority.get("revoked") not in (True, False):
        errors.append("INVALID_REVOCATION_FLAG: authority.revoked must be boolean")
    if authority.get("revoked") is True and not _nonempty_string(
        authority.get("revocation_reason")
    ):
        errors.append("REVOCATION_REASON_REQUIRED: revoked authority requires a reason")

    if not _nonempty_string(outcome.get("desired_state")):
        errors.append("DESIRED_STATE_REQUIRED: outcome.desired_state must be non-empty")
    for field in (
        "completion_proof",
        "integrity_guards",
        "scope_proof",
        "stop_conditions",
    ):
        value = outcome.get(field)
        if not isinstance(value, list) or not value:
            errors.append(f"EMPTY_PROOF_FIELD: outcome.{field} must be a non-empty array")
        elif not _all_nonempty_strings(value):
            errors.append(f"INVALID_PROOF_ITEM: outcome.{field} items must be non-empty strings")

    subject_refs = truth.get("subject_refs")
    if not isinstance(subject_refs, list) or not subject_refs:
        errors.append("SUBJECT_REF_REQUIRED: truth.subject_refs must be non-empty")

    status = state.get("status")
    allowed_status = {item.value for item in MissionStatus}
    if status not in allowed_status:
        errors.append(f"INVALID_STATUS: {status!r} is not a mission status")

    next_action = state.get("next_action")
    if next_action is not None and not _nonempty_string(next_action):
        errors.append("INVALID_NEXT_ACTION: state.next_action must be null or non-empty")

    if integrity.get("actor_may_self_accept") is not False:
        errors.append(
            "SELF_ACCEPTANCE_FORBIDDEN: integrity.actor_may_self_accept must be false"
        )

    if status in {MissionStatus.VERIFYING.value, MissionStatus.COMPLETED.value}:
        if not _nonempty_string(integrity.get("completion_acceptor")):
            errors.append(
                "COMPLETION_ACCEPTOR_REQUIRED: verification/completion requires an acceptor"
            )

    if status == MissionStatus.COMPLETED.value:
        unresolved = integrity.get("unresolved_verdicts")
        if isinstance(unresolved, list) and unresolved:
            errors.append(
                "UNRESOLVED_VERDICTS: completed missions cannot retain unresolved verdicts"
            )

    if authority.get("revoked") is True and status not in {
        MissionStatus.BLOCKED.value,
        MissionStatus.CANCELLED.value,
    }:
        errors.append(
            "REVOKED_STATE_INVALID: revoked authority permits only blocked or cancelled"
        )

    if (
        isinstance(revision, int)
        and not isinstance(revision, bool)
        and revision > 1
        and status
        in {
            MissionStatus.ACTIVE.value,
            MissionStatus.VERIFYING.value,
            MissionStatus.COMPLETED.value,
        }
        and not _nonempty_string(continuity.get("prior_checkpoint"))
    ):
        errors.append(
            "PRIOR_CHECKPOINT_REQUIRED: resumable active state requires a checkpoint reference"
        )

    return errors
