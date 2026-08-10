"""Execution of exact, intrinsically non-mutating capability grants."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import hashlib

from practical_agency.capability_grants import CapabilityGrantError, consume_grant


class CapabilityOperationError(RuntimeError):
    """Named refusal for an operation outside a grant's read-only surface."""


_READ_ONLY = {"file.read", "resource.read", "web.search", "web.open"}


def execute_read(
    grant: dict[str, Any], *, mission_id: str, mission_revision: int,
    operation: str, target: str, workspace: Path, evidence_refs: list[str] | None = None,
    evidence_payload: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if operation not in _READ_ONLY:
        raise CapabilityOperationError("OPERATION_NOT_READ_ONLY")
    scope = grant.get("evidence_scope")
    if not isinstance(scope, list) or target not in scope:
        raise CapabilityOperationError("TARGET_NOT_IN_EVIDENCE_SCOPE")
    refs = list(evidence_refs or [])
    if operation.startswith("web.") and not refs:
        raise CapabilityOperationError("SOURCE_EVIDENCE_REQUIRED")
    if operation.startswith("web.") and (not evidence_payload or not all(ref in evidence_payload for ref in refs)):
        raise CapabilityOperationError("SOURCE_BYTES_REQUIRED")
    observed: list[dict[str, Any]] = []
    if operation in {"file.read", "resource.read"}:
        root = workspace.resolve()
        path = (root / target).resolve()
        try:
            path.relative_to(root)
        except ValueError as error:
            raise CapabilityOperationError("TARGET_OUTSIDE_WORKSPACE") from error
        if not path.is_file():
            raise CapabilityOperationError("READ_TARGET_NOT_FOUND")
        observed.append({"target": target, "content": path.read_text(encoding="utf-8"), "mutation": False})
    else:
        observed.append({"target": target, "source_evidence": refs, "evidence_records":[{"ref": ref, "sha256": hashlib.sha256(evidence_payload[ref].encode("utf-8")).hexdigest()} for ref in refs], "mutation": False})
    try:
        result = consume_grant(
            grant, mission_id=mission_id, mission_revision=mission_revision,
            operation=operation, evidence_refs=refs or [f"file:{target}"],
        )
    except CapabilityGrantError as error:
        raise CapabilityOperationError(str(error)) from error
    result["observed_effects"] = observed
    return result
