"""Execution of exact, intrinsically non-mutating capability grants."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import hashlib
import ipaddress
import socket
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

from practical_agency.capability_grants import CapabilityGrantError, consume_grant


class CapabilityOperationError(RuntimeError):
    """Named refusal for an operation outside a grant's read-only surface."""


_READ_ONLY = {"file.read", "resource.read", "web.search", "web.open"}


def _canonical_relative(root: Path, target: str) -> Path:
    if not target or target != target.replace("\\", "/") or "//" in target:
        raise CapabilityOperationError("ALTERNATE_PATH_IDENTITY")
    parts = target.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise CapabilityOperationError("ALTERNATE_PATH_IDENTITY")
    candidate = root.joinpath(*parts)
    if candidate.is_symlink():
        raise CapabilityOperationError("PATH_REPARSE_POINT")
    resolved = candidate.resolve()
    if resolved != candidate.absolute():
        raise CapabilityOperationError("PATH_REPARSE_POINT")
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise CapabilityOperationError("TARGET_OUTSIDE_WORKSPACE") from error
    return resolved


def _safe_web_target(target: str) -> None:
    parsed = urlparse(target)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise CapabilityOperationError("WEB_TARGET_INVALID")
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise CapabilityOperationError("WEB_PRIVATE_TARGET")
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, None)}
        except OSError as error:
            raise CapabilityOperationError("WEB_TARGET_UNRESOLVED") from error
    if any(address.is_private or address.is_loopback or address.is_link_local or address.is_reserved for address in addresses):
        raise CapabilityOperationError("WEB_PRIVATE_TARGET")


def _retrieve_web(target: str) -> dict[str, Any]:
    _safe_web_target(target)
    request = urllib.request.Request(target, headers={"User-Agent": "practical-agency-capability/1"})
    with urllib.request.urlopen(request, timeout=10) as response:
        observed_url = str(response.geturl())
        if observed_url != target:
            _safe_web_target(observed_url)
            raise CapabilityOperationError("WEB_REDIRECT_OUT_OF_SCOPE")
        content = response.read()
        return {
            "url": observed_url,
            "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "status": int(response.status),
            "content": content.decode("utf-8", errors="replace"),
            "content_sha256": hashlib.sha256(content).hexdigest(),
        }


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
        relative_target = target
        if operation == "resource.read":
            if not target.startswith("resource:") or target.startswith("resource://"):
                raise CapabilityOperationError("RESOURCE_IDENTITY_REQUIRED")
            relative_target = target.removeprefix("resource:")
        path = _canonical_relative(root, relative_target)
        if not path.is_file():
            raise CapabilityOperationError("READ_TARGET_NOT_FOUND")
        observed.append({"target": target, "content": path.read_text(encoding="utf-8"), "mutation": False})
    else:
        response = _retrieve_web(target)
        if "content_sha256" not in response:
            response = {**response, "content_sha256": hashlib.sha256(str(response.get("content", "")).encode("utf-8")).hexdigest()}
        if target not in scope:
            raise CapabilityOperationError("TARGET_NOT_IN_EVIDENCE_SCOPE")
        observed.append({"target": target, "response": response, "source_evidence": refs, "evidence_records":[{"ref": ref, "sha256": hashlib.sha256(evidence_payload[ref].encode("utf-8")).hexdigest()} for ref in refs], "mutation": False})
    try:
        result = consume_grant(
            grant, mission_id=mission_id, mission_revision=mission_revision,
            operation=operation, evidence_refs=refs or [f"file:{target}"],
        )
    except CapabilityGrantError as error:
        raise CapabilityOperationError(str(error)) from error
    result["observed_effects"] = observed
    return result
