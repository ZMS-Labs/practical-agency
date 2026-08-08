"""deferred-interest@1 validation helpers."""
from __future__ import annotations

from typing import Any, Mapping

_CRITICALITY = {"low", "medium", "high"}
_STATUS = {"open", "absorbed", "discarded"}
_REQUIRED = {
    "schema",
    "mission_id",
    "summary",
    "criticality",
    "why_not_now",
    "suggested_next",
    "subject_refs",
    "created_at_revision",
    "status",
}
_ALLOWED = _REQUIRED | {"critical_path_clearance"}


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def normalize_deferred_interests(value: object) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError("deferred_interests must be an array")
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise TypeError("deferred_interests items must be objects")
        normalized.append(dict(item))
    return normalized


def validate_deferred_interest(
    obj: Mapping[str, Any] | object, *, mission_id: str
) -> list[str]:
    if not isinstance(obj, Mapping):
        return ["DEFERRED_INTEREST_MUST_BE_OBJECT"]
    errors: list[str] = []
    if set(obj) - _ALLOWED:
        errors.append("DEFERRED_INTEREST_UNKNOWN_FIELD")
    if _REQUIRED - set(obj):
        errors.append("DEFERRED_INTEREST_MISSING_FIELD")
    if obj.get("schema") != "deferred-interest@1":
        errors.append("DEFERRED_INTEREST_SCHEMA")
    if obj.get("mission_id") != mission_id:
        errors.append("DEFERRED_INTEREST_MISSION_MISMATCH")
    if obj.get("criticality") not in _CRITICALITY:
        errors.append("DEFERRED_INTEREST_CRITICALITY")
    if obj.get("status") not in _STATUS:
        errors.append("DEFERRED_INTEREST_STATUS")
    if not _nonempty_string(obj.get("summary")):
        errors.append("DEFERRED_INTEREST_SUMMARY")
    if not _nonempty_string(obj.get("why_not_now")):
        errors.append("DEFERRED_INTEREST_WHY_NOT_NOW")
    suggested_next = obj.get("suggested_next")
    if suggested_next is not None and not _nonempty_string(suggested_next):
        errors.append("DEFERRED_INTEREST_SUGGESTED_NEXT")
    revision = obj.get("created_at_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        errors.append("DEFERRED_INTEREST_CREATED_AT_REVISION")
    refs = obj.get("subject_refs")
    if not isinstance(refs, list) or any(
        not isinstance(x, str) or not x.strip() for x in refs
    ):
        errors.append("DEFERRED_INTEREST_SUBJECT_REFS")
    elif obj.get("criticality") == "high" and not refs:
        errors.append("SUBJECT_REFS_REQUIRED")
    clearance = obj.get("critical_path_clearance")
    if clearance is not None:
        if not isinstance(clearance, Mapping) or set(clearance) != {"reason", "basis_refs"}:
            errors.append("CRITICAL_PATH_CLEARANCE_INVALID")
        else:
            if not _nonempty_string(clearance.get("reason")):
                errors.append("CRITICAL_PATH_CLEARANCE_REASON")
            basis_refs = clearance.get("basis_refs")
            if not isinstance(basis_refs, list) or not basis_refs or any(
                not _nonempty_string(ref) for ref in basis_refs
            ):
                errors.append("CRITICAL_PATH_CLEARANCE_BASIS_REFS")
    return errors
