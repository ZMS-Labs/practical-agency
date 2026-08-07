"""Semantic validation for mission-manifest@1."""

from __future__ import annotations

from typing import Any, Mapping

from practical_agency.manifest_model import MissionStatus

SCHEMA = "mission-manifest@1"

TOP_LEVEL_KEYS = {
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

AUTHORITY_KEYS = {
    "operator_ref",
    "instruction",
    "amendments",
    "permissions",
    "protected_state",
    "acceptable_costs",
    "escalation_required_for",
    "revoked",
    "revocation_reason",
}

OUTCOME_KEYS = {
    "desired_state",
    "completion_proof",
    "integrity_guards",
    "scope_proof",
    "stop_conditions",
}

TRUTH_KEYS = {
    "subject_refs",
    "verified_facts",
    "assumptions",
    "contradictions",
    "unknowns",
}

STATE_KEYS = {
    "status",
    "completed_actions",
    "current_frontier",
    "blockers",
    "next_action",
}

CAPABILITIES_KEYS = {
    "discovered_at",
    "available",
    "invoked",
    "unavailable",
    "degraded",
}

CONTINUITY_KEYS = {
    "prior_checkpoint",
    "durable_artifacts",
    "decisions",
    "external_handoffs",
    "watch_commissions",
}

INTEGRITY_KEYS = {
    "actor_may_self_accept",
    "required_gates",
    "unresolved_verdicts",
    "completion_acceptor",
}

STATUS_VALUES = {status.value for status in MissionStatus}


def _reject_unknown(errors: list[str], path: str, payload: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    for key in unknown:
        errors.append(f"UNKNOWN_KEY: {path}.{key}")


def _require_object(errors: list[str], path: str, value: Any) -> Mapping[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(f"INVALID_OBJECT: {path} must be an object")
        return None
    return value


def _require_nonempty_str(errors: list[str], path: str, value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"EMPTY_STRING: {path} must be a non-empty string")


def _require_list(errors: list[str], path: str, value: Any) -> None:
    if not isinstance(value, list):
        errors.append(f"INVALID_LIST: {path} must be a list")


def validate_manifest_dict(payload: Mapping[str, Any] | Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["INVALID_OBJECT: top-level payload must be an object"]

    _reject_unknown(errors, "manifest", payload, TOP_LEVEL_KEYS)
    for key in TOP_LEVEL_KEYS:
        if key not in payload:
            errors.append(f"MISSING_KEY: manifest.{key}")

    if payload.get("schema") != SCHEMA:
        errors.append(f"INVALID_SCHEMA: expected {SCHEMA}")

    mission_id = payload.get("mission_id")
    _require_nonempty_str(errors, "manifest.mission_id", mission_id)

    revision = payload.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        errors.append("INVALID_REVISION: revision must be a positive integer")

    authority = _require_object(errors, "manifest.authority", payload.get("authority"))
    if authority is not None:
        _reject_unknown(errors, "authority", authority, AUTHORITY_KEYS)
        _require_nonempty_str(errors, "authority.operator_ref", authority.get("operator_ref"))
        _require_nonempty_str(errors, "authority.instruction", authority.get("instruction"))
        for key in (
            "amendments",
            "permissions",
            "protected_state",
            "acceptable_costs",
            "escalation_required_for",
        ):
            _require_list(errors, f"authority.{key}", authority.get(key))
        if not isinstance(authority.get("revoked"), bool):
            errors.append("INVALID_BOOL: authority.revoked must be a boolean")

    outcome = _require_object(errors, "manifest.outcome", payload.get("outcome"))
    if outcome is not None:
        _reject_unknown(errors, "outcome", outcome, OUTCOME_KEYS)
        _require_nonempty_str(errors, "outcome.desired_state", outcome.get("desired_state"))
        for key in (
            "completion_proof",
            "integrity_guards",
            "scope_proof",
            "stop_conditions",
        ):
            value = outcome.get(key)
            _require_list(errors, f"outcome.{key}", value)
            if isinstance(value, list) and len(value) < 1:
                errors.append(f"EMPTY_PROOF: outcome.{key} must be non-empty")

    truth = _require_object(errors, "manifest.truth", payload.get("truth"))
    if truth is not None:
        _reject_unknown(errors, "truth", truth, TRUTH_KEYS)
        for key in TRUTH_KEYS:
            _require_list(errors, f"truth.{key}", truth.get(key))

    state = _require_object(errors, "manifest.state", payload.get("state"))
    status: str | None = None
    if state is not None:
        _reject_unknown(errors, "state", state, STATE_KEYS)
        status_value = state.get("status")
        if status_value not in STATUS_VALUES:
            errors.append("INVALID_STATUS: state.status is outside the closed enum")
        else:
            status = str(status_value)
        for key in ("completed_actions", "current_frontier", "blockers"):
            _require_list(errors, f"state.{key}", state.get(key))
        next_action = state.get("next_action")
        if next_action is not None and not isinstance(next_action, str):
            errors.append("INVALID_STRING: state.next_action must be a string or null")

    capabilities = _require_object(errors, "manifest.capabilities", payload.get("capabilities"))
    if capabilities is not None:
        _reject_unknown(errors, "capabilities", capabilities, CAPABILITIES_KEYS)
        for key in ("available", "invoked", "unavailable", "degraded"):
            _require_list(errors, f"capabilities.{key}", capabilities.get(key))

    continuity = _require_object(errors, "manifest.continuity", payload.get("continuity"))
    if continuity is not None:
        _reject_unknown(errors, "continuity", continuity, CONTINUITY_KEYS)
        for key in (
            "durable_artifacts",
            "decisions",
            "external_handoffs",
            "watch_commissions",
        ):
            _require_list(errors, f"continuity.{key}", continuity.get(key))

    integrity = _require_object(errors, "manifest.integrity", payload.get("integrity"))
    if integrity is not None:
        _reject_unknown(errors, "integrity", integrity, INTEGRITY_KEYS)
        if integrity.get("actor_may_self_accept") is not False:
            errors.append(
                "SELF_ACCEPTANCE_FORBIDDEN: integrity.actor_may_self_accept must be exactly false"
            )
        _require_list(errors, "integrity.required_gates", integrity.get("required_gates"))
        unresolved = integrity.get("unresolved_verdicts")
        _require_list(errors, "integrity.unresolved_verdicts", unresolved)
        acceptor = integrity.get("completion_acceptor")
        if status == MissionStatus.COMPLETED.value:
            if not isinstance(acceptor, str) or not acceptor.strip():
                errors.append(
                    "COMPLETION_ACCEPTOR_REQUIRED: completed missions need a completion_acceptor"
                )
            if isinstance(unresolved, list) and unresolved:
                errors.append(
                    "UNRESOLVED_VERDICTS: completed missions cannot retain unresolved verdicts"
                )

    if authority is not None and authority.get("revoked") is True:
        if status not in {MissionStatus.CANCELLED.value, MissionStatus.BLOCKED.value}:
            errors.append(
                "REVOKED_STATE: revoked authority permits only cancelled or blocked state"
            )

    if (
        continuity is not None
        and isinstance(revision, int)
        and not isinstance(revision, bool)
        and revision > 1
        and status
        in {
            MissionStatus.ACTIVE.value,
            MissionStatus.VERIFYING.value,
            MissionStatus.COMPLETED.value,
        }
        and continuity.get("prior_checkpoint") is None
    ):
        errors.append(
            "CHECKPOINT_REQUIRED: active/verifying/completed after revision 1 need prior_checkpoint"
        )

    return errors
