"""Mission-bound, one-use grants for intrinsically non-mutating operations."""
from __future__ import annotations

from copy import deepcopy
from uuid import uuid4
from typing import Any, Mapping


class CapabilityGrantError(RuntimeError):
    """Named refusal for a stale, over-broad, or replayed grant."""


_REQUIRED = {
    "mission_id", "mission_revision", "capability_id",
    "capability_descriptor_sha256", "blocking_condition", "return_point",
    "admitted_operation", "evidence_scope", "mutation", "expires_after_use",
}


def issue_grant(payload: Mapping[str, Any]) -> dict[str, Any]:
    if set(payload) != _REQUIRED:
        raise CapabilityGrantError("GRANT_FIELDS_INVALID")
    if not isinstance(payload["mission_id"], str) or not payload["mission_id"].strip():
        raise CapabilityGrantError("GRANT_MISSION_INVALID")
    if not isinstance(payload["mission_revision"], int) or payload["mission_revision"] < 1:
        raise CapabilityGrantError("GRANT_REVISION_INVALID")
    digest = payload["capability_descriptor_sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise CapabilityGrantError("GRANT_DESCRIPTOR_INVALID")
    if payload["mutation"] is not False or payload["expires_after_use"] is not True:
        raise CapabilityGrantError("GRANT_MUTATION_POLICY_INVALID")
    scope = payload["evidence_scope"]
    if not isinstance(scope, list) or not scope or not all(isinstance(item, str) and item for item in scope):
        raise CapabilityGrantError("GRANT_EVIDENCE_SCOPE_INVALID")
    return {**deepcopy(dict(payload)), "schema": "capability-grant@1", "grant_id": f"grant-{uuid4().hex}", "used": False, "revoked": False}


def issue_grant_from_descriptor(
    descriptor: Any, *, mission_id: str, mission_revision: int,
    blocking_condition: str, return_point: Mapping[str, Any],
    admitted_operation: str, evidence_scope: list[str],
) -> dict[str, Any]:
    """Derive the grant identity from a discovered descriptor, never a copied inventory."""
    descriptor_id = getattr(descriptor, "capability_id", None)
    descriptor_digest = getattr(descriptor, "source_sha256", None)
    if not isinstance(descriptor_id, str) or not isinstance(descriptor_digest, str):
        raise CapabilityGrantError("GRANT_DESCRIPTOR_REQUIRED")
    return issue_grant({
        "mission_id": mission_id, "mission_revision": mission_revision,
        "capability_id": descriptor_id,
        "capability_descriptor_sha256": descriptor_digest,
        "blocking_condition": blocking_condition, "return_point": dict(return_point),
        "admitted_operation": admitted_operation, "evidence_scope": list(evidence_scope),
        "mutation": False, "expires_after_use": True,
    })


def consume_grant(
    grant: dict[str, Any], *, mission_id: str, mission_revision: int,
    operation: str, evidence_refs: list[str], mutation: bool = False,
    return_point: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if grant.get("revoked") is True:
        raise CapabilityGrantError("GRANT_REVOKED")
    if grant.get("used") is True:
        raise CapabilityGrantError("GRANT_REPLAYED")
    if mission_id != grant.get("mission_id"):
        raise CapabilityGrantError("GRANT_MISSION_MISMATCH")
    if mission_revision != grant.get("mission_revision"):
        raise CapabilityGrantError("GRANT_STALE")
    if operation != grant.get("admitted_operation"):
        raise CapabilityGrantError("GRANT_OPERATION_NOT_ADMITTED")
    if mutation or grant.get("mutation") is not False:
        raise CapabilityGrantError("GRANT_MUTATION_FORBIDDEN")
    expected_point = grant.get("return_point")
    if return_point is not None and dict(return_point) != expected_point:
        raise CapabilityGrantError("GRANT_RETURN_POINT_MISMATCH")
    scope = set(grant.get("evidence_scope", []))
    if not evidence_refs or not set(evidence_refs).issubset(scope):
        raise CapabilityGrantError("GRANT_EVIDENCE_REQUIRED")
    grant["used"] = True
    return {
        "schema": "capability-result@1", "grant_id": grant["grant_id"],
        "verdict": "PASS", "returned_control_point": deepcopy(expected_point),
        "coverage_limits": ["intrinsically non-mutating operation", "exact grant evidence scope"],
        "evidence_refs": list(evidence_refs), "observed_effects": [],
    }
