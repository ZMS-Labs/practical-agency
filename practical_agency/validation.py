"""Fail-closed semantic validation for mission-manifest@1."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .manifest_model import MissionManifest, MissionStatus

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

SECTION_FIELDS: dict[str, set[str]] = {
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
        "material_work_actors",
        "required_gates",
        "unresolved_verdicts",
        "completion_acceptor",
        "acceptance_receipt_ref",
    },
}


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _list(value: Any) -> bool:
    return isinstance(value, list)


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _nullable_string(value: Any) -> bool:
    return value is None or isinstance(value, str)


def validate_manifest_dict(payload: Mapping[str, Any] | Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, Mapping):
        return ["RECORD_MUST_BE_OBJECT: root must be an object"]

    keys = set(payload)
    for missing in sorted(TOP_LEVEL - keys):
        errors.append(f"MISSING_TOP_LEVEL_FIELD: {missing}")
    for unexpected in sorted(keys - TOP_LEVEL):
        errors.append(f"UNEXPECTED_TOP_LEVEL_FIELD: {unexpected}")

    if payload.get("schema") != "mission-manifest@1":
        errors.append("INVALID_SCHEMA: schema must equal mission-manifest@1")
    if not _nonempty_string(payload.get("mission_id")):
        errors.append("INVALID_MISSION_ID: mission_id must be a non-empty string")
    revision = payload.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        errors.append("INVALID_REVISION: revision must be a positive integer")

    for section, fields in SECTION_FIELDS.items():
        value = payload.get(section)
        if not isinstance(value, Mapping):
            errors.append(f"INVALID_SECTION: {section} must be an object")
            continue
        section_keys = set(value)
        for missing in sorted(fields - section_keys):
            errors.append(f"MISSING_{section.upper()}_FIELD: {missing}")
        for unexpected in sorted(section_keys - fields):
            errors.append(f"UNEXPECTED_{section.upper()}_FIELD: {unexpected}")

    authority = payload.get("authority")
    if isinstance(authority, Mapping):
        if not _nonempty_string(authority.get("operator_ref")):
            errors.append("OPERATOR_REQUIRED: authority.operator_ref must be non-empty")
        if not _nonempty_string(authority.get("instruction")):
            errors.append("INSTRUCTION_REQUIRED: authority.instruction must be non-empty")
        amendments = authority.get("amendments")
        if not _list(amendments):
            errors.append("INVALID_AUTHORITY_LIST: authority.amendments must be a list")
        else:
            amendment_fields = {
                "revision",
                "instruction",
                "authorized_by",
                "authorization_ref",
                "recorded_at",
            }
            previous_revision = 0
            manifest_revision = payload.get("revision")
            for index, amendment in enumerate(amendments):
                if not isinstance(amendment, Mapping) or set(amendment) != amendment_fields:
                    errors.append(
                        f"INVALID_AMENDMENT: authority.amendments[{index}] has the wrong shape"
                    )
                    continue
                amendment_revision = amendment.get("revision")
                revision_valid = (
                    isinstance(amendment_revision, int)
                    and not isinstance(amendment_revision, bool)
                    and amendment_revision > 1
                    and isinstance(manifest_revision, int)
                    and amendment_revision <= manifest_revision
                )
                if not revision_valid:
                    errors.append(
                        f"INVALID_AMENDMENT: authority.amendments[{index}].revision is invalid"
                    )
                elif amendment_revision <= previous_revision:
                    errors.append(
                        "INVALID_AMENDMENT_ORDER: amendment revisions must be strictly increasing"
                    )
                else:
                    previous_revision = amendment_revision
                for field in ("instruction", "authorization_ref", "recorded_at"):
                    if not _nonempty_string(amendment.get(field)):
                        errors.append(
                            f"INVALID_AMENDMENT: authority.amendments[{index}].{field} must be non-empty"
                        )
                if amendment.get("authorized_by") != authority.get("operator_ref"):
                    errors.append(
                        f"INVALID_AMENDMENT: authority.amendments[{index}].authorized_by must match operator"
                    )
        for field in (
            "permissions",
            "protected_state",
            "acceptable_costs",
            "escalation_required_for",
        ):
            if not _string_list(authority.get(field)):
                errors.append(
                    f"INVALID_STRING_LIST: authority.{field} must be a list of strings"
                )
        if not isinstance(authority.get("revoked"), bool):
            errors.append("INVALID_REVOCATION_FLAG: authority.revoked must be boolean")
        if not _nullable_string(authority.get("revocation_reason")):
            errors.append("INVALID_REVOCATION_REASON: revocation_reason must be string or null")
        if authority.get("revoked") and not _nonempty_string(authority.get("revocation_reason")):
            errors.append("REVOCATION_REASON_REQUIRED: revoked authority must name a reason")

    outcome = payload.get("outcome")
    if isinstance(outcome, Mapping):
        if not _nonempty_string(outcome.get("desired_state")):
            errors.append("DESIRED_STATE_REQUIRED: outcome.desired_state must be non-empty")
        for field in ("completion_proof", "integrity_guards", "scope_proof", "stop_conditions"):
            if not _string_list(outcome.get(field)):
                errors.append(
                    f"INVALID_STRING_LIST: outcome.{field} must be a list of strings"
                )
        if isinstance(outcome.get("completion_proof"), list) and not outcome["completion_proof"]:
            errors.append("COMPLETION_PROOF_REQUIRED: at least one completion proof is required")

    for section in ("truth", "capabilities", "continuity"):
        value = payload.get(section)
        if isinstance(value, Mapping):
            for field, item in value.items():
                if field in {"discovered_at", "prior_checkpoint"}:
                    if not _nullable_string(item):
                        errors.append(f"INVALID_NULLABLE_REF: {section}.{field}")
                elif not _list(item):
                    errors.append(f"INVALID_LIST: {section}.{field} must be a list")
            if section == "truth" and not _string_list(value.get("subject_refs")):
                errors.append(
                    "INVALID_STRING_LIST: truth.subject_refs must be a list of strings"
                )
            if section == "continuity" and not _string_list(
                value.get("durable_artifacts")
            ):
                errors.append(
                    "INVALID_STRING_LIST: continuity.durable_artifacts must be a list of strings"
                )

    state = payload.get("state")
    status: str | None = None
    if isinstance(state, Mapping):
        status = state.get("status") if isinstance(state.get("status"), str) else None
        if status not in {candidate.value for candidate in MissionStatus}:
            errors.append("INVALID_STATUS: state.status is outside the closed lifecycle")
        for field in ("completed_actions", "blockers"):
            if not _list(state.get(field)):
                errors.append(f"INVALID_STATE_LIST: state.{field} must be a list")
        if not _string_list(state.get("current_frontier")):
            errors.append(
                "INVALID_STRING_LIST: state.current_frontier must be a list of strings"
            )
        if not _nullable_string(state.get("next_action")):
            errors.append("INVALID_NEXT_ACTION: state.next_action must be string or null")
        if status == MissionStatus.BLOCKED.value and isinstance(state.get("blockers"), list) and not state["blockers"]:
            errors.append("BLOCKER_REQUIRED: blocked missions must name a blocker")
        if status in {MissionStatus.COMPLETED.value, MissionStatus.CANCELLED.value} and state.get("next_action") is not None:
            errors.append("TERMINAL_NEXT_ACTION_FORBIDDEN: terminal missions cannot name a next action")

    integrity = payload.get("integrity")
    if isinstance(integrity, Mapping):
        if integrity.get("actor_may_self_accept") is not False:
            errors.append("SELF_ACCEPTANCE_FORBIDDEN: actor_may_self_accept must be false")
        if not _string_list(integrity.get("material_work_actors")):
            errors.append(
                "INVALID_STRING_LIST: integrity.material_work_actors must be a list of strings"
            )
        if not _string_list(integrity.get("required_gates")):
            errors.append(
                "INVALID_STRING_LIST: integrity.required_gates must be a list of strings"
            )
        if not _list(integrity.get("unresolved_verdicts")):
            errors.append(
                "INVALID_INTEGRITY_LIST: integrity.unresolved_verdicts must be a list"
            )
        for field in ("completion_acceptor", "acceptance_receipt_ref"):
            if not _nullable_string(integrity.get(field)):
                errors.append(f"INVALID_INTEGRITY_REF: integrity.{field} must be string or null")
        if status == MissionStatus.COMPLETED.value:
            if not _nonempty_string(integrity.get("completion_acceptor")):
                errors.append("COMPLETION_ACCEPTOR_REQUIRED: completed mission needs independent acceptor")
            if not _nonempty_string(integrity.get("acceptance_receipt_ref")):
                errors.append("ACCEPTANCE_RECEIPT_REQUIRED: completed mission needs acceptance receipt")
            actors = integrity.get("material_work_actors")
            if isinstance(actors, list) and integrity.get("completion_acceptor") in actors:
                errors.append("INDEPENDENCE_REQUIRED: completion acceptor performed material work")
            unresolved = integrity.get("unresolved_verdicts")
            if isinstance(unresolved, list) and unresolved:
                errors.append("UNRESOLVED_VERDICTS_FORBID_COMPLETION: clear or resolve all verdicts")

    if isinstance(authority, Mapping):
        if authority.get("revoked") and status != MissionStatus.CANCELLED.value:
            errors.append("REVOKED_MISSION_MUST_CANCEL: revoked authority requires cancelled status")
        if status == MissionStatus.CANCELLED.value and authority.get("revoked") is not True:
            errors.append(
                "CANCELLED_REQUIRES_REVOCATION: cancelled is reachable only through recorded operator revocation"
            )
        if authority.get("revoked") is True:
            continuity = payload.get("continuity")
            decisions = continuity.get("decisions") if isinstance(continuity, Mapping) else None
            operator_ref = authority.get("operator_ref")
            manifest_revision = payload.get("revision")
            valid_revocation = False
            if isinstance(decisions, list):
                for decision in decisions:
                    if not isinstance(decision, Mapping) or decision.get("kind") != "revocation":
                        continue
                    decision_revision = decision.get("revision")
                    valid_revision = (
                        isinstance(decision_revision, int)
                        and not isinstance(decision_revision, bool)
                        and isinstance(manifest_revision, int)
                        and decision_revision <= manifest_revision
                    )
                    if (
                        decision.get("actor_ref") == operator_ref
                        and _nonempty_string(decision.get("evidence_ref"))
                        and _nonempty_string(decision.get("recorded_at"))
                        and valid_revision
                    ):
                        valid_revocation = True
                        break
            if not valid_revocation:
                errors.append(
                    "REVOCATION_DECISION_REQUIRED: revoked authority needs a receipted operator decision"
                )

    return errors


def load_manifest(path: Path) -> MissionManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"UNREADABLE_MANIFEST: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("RECORD_MUST_BE_OBJECT: root must be an object")
    return MissionManifest.from_dict(payload)
