"""Bounded filesystem artifact adapter with crash-visible external receipts.

Stdlib-only. No shell. Writes only under an allowlisted root prefix.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

_ADAPTER_REF = "filesystem-artifact@1"
_RELPATH = re.compile(r"^relpath:(?P<path>.+)$")
_UTF8 = re.compile(r"^utf8:(?P<body>.*)$", re.S)
_SAFE_RELPATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


class FilesystemArtifactError(RuntimeError):
    """Named refusal or visible interrupted filesystem operation."""


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        with temp.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temp.unlink(missing_ok=True)


def _atomic_write_json(path: Path, body: Mapping[str, Any]) -> None:
    encoded = (
        json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _atomic_write_bytes(path, encoded)


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _receipt_path(root: Path, request_id: str) -> Path:
    name = hashlib.sha256(request_id.encode("utf-8")).hexdigest() + ".json"
    return (root / ".receipts" / name).resolve()


def _completed_receipt_from_journal(
    journal: Mapping[str, Any], receipt_path: Path
) -> dict[str, Any]:
    relpath = journal["relpath"]
    return {
        "schema": "execution-receipt@1",
        "request_id": journal["request_id"],
        "mission_id": journal["mission_id"],
        "mission_revision": journal["mission_revision"],
        "adapter_ref": journal["adapter_ref"],
        "status": "completed",
        "artifact_refs": [f"file:{relpath}"],
        "observed_effects": [
            {
                "kind": "text-artifact-written",
                "relpath": relpath,
                "sha256": journal["artifact_sha256"],
                "bytes": journal["bytes"],
            }
        ],
        "external_receipt_ref": str(receipt_path),
        "coverage_limits": [
            "filesystem-artifact@1 writes text under allowlisted prefixes only",
            "no arbitrary shell",
            "receipt journal is a local durable file under the adapter root",
            "existing committed request replayed idempotently without a new effect",
        ],
    }


class FilesystemArtifactAdapter:
    """Write text artifacts under a rooted allowlist and journal every effect."""

    adapter_ref = _ADAPTER_REF
    capability_ids = ("filesystem-artifact",)

    def __init__(
        self,
        root: Path,
        *,
        allowed_prefixes: tuple[str, ...] = ("mission-artifacts/",),
        fail_at: str | None = None,
    ) -> None:
        if fail_at not in {None, "before_effect", "after_effect", "before_receipt_commit"}:
            raise ValueError("INVALID_FAILURE_INJECTION_POINT")
        self.root = Path(root).resolve()
        self.allowed_prefixes = tuple(allowed_prefixes)
        self.fail_at = fail_at
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / ".receipts").mkdir(parents=True, exist_ok=True)

    def dispatch(self, request: Mapping[str, Any]) -> dict[str, Any]:
        request_id = str(request.get("request_id") or "")
        mission_id = str(request.get("mission_id") or "")
        mission_revision = request.get("mission_revision")
        action = request.get("action")
        effects = request.get("requested_effects")

        base = {
            "schema": "execution-receipt@1",
            "request_id": request_id,
            "mission_id": mission_id,
            "mission_revision": mission_revision,
            "adapter_ref": self.adapter_ref,
            "artifact_refs": [],
            "observed_effects": [],
            "external_receipt_ref": None,
            "coverage_limits": [
                "filesystem-artifact@1 writes text under allowlisted prefixes only",
                "no arbitrary shell",
                "receipt journal is a local durable file under the adapter root",
            ],
        }

        if action != "write-text":
            return {
                **base,
                "status": "declined",
                "coverage_limits": base["coverage_limits"]
                + [f"unsupported action:{action!r}; no arbitrary shell"],
            }
        if not isinstance(effects, list):
            return {
                **base,
                "status": "blocked",
                "coverage_limits": base["coverage_limits"] + ["effects required"],
            }

        relpath: str | None = None
        body: str | None = None
        for item in effects:
            if not isinstance(item, str):
                continue
            path_match = _RELPATH.match(item)
            if path_match:
                relpath = path_match.group("path")
                continue
            body_match = _UTF8.match(item)
            if body_match:
                body = body_match.group("body")

        if not relpath or body is None:
            return {
                **base,
                "status": "blocked",
                "coverage_limits": base["coverage_limits"]
                + ["require relpath: and utf8: effects"],
            }
        if (
            not _SAFE_RELPATH.fullmatch(relpath)
            or ".." in relpath.split("/")
            or relpath.startswith("/")
            or not any(relpath.startswith(prefix) for prefix in self.allowed_prefixes)
        ):
            return {
                **base,
                "status": "blocked",
                "coverage_limits": base["coverage_limits"]
                + ["relpath outside allowlisted prefixes or unsafe"],
            }

        target = (self.root / relpath).resolve()
        try:
            target.relative_to(self.root)
        except ValueError:
            return {
                **base,
                "status": "blocked",
                "coverage_limits": base["coverage_limits"] + ["path escape blocked"],
            }

        data = body.encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()
        receipt_path = _receipt_path(self.root, request_id)
        request_hash = _canonical_sha256(dict(request))
        if receipt_path.exists():
            try:
                existing = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise FilesystemArtifactError("EXISTING_RECEIPT_INVALID") from error
            if not isinstance(existing, dict):
                raise FilesystemArtifactError("EXISTING_RECEIPT_INVALID")
            if existing.get("request_sha256") != request_hash:
                raise FilesystemArtifactError("REQUEST_ID_COLLISION")
            state = existing.get("state")
            if state != "committed":
                raise FilesystemArtifactError(
                    f"EXISTING_RECEIPT_NOT_RETRYABLE:{state}"
                )
            verify_filesystem_receipt(str(receipt_path), request, self.root)
            return _completed_receipt_from_journal(existing, receipt_path)

        journal: dict[str, Any] = {
            "schema": "filesystem-artifact-receipt@1",
            "state": "prepared",
            "adapter_ref": self.adapter_ref,
            "request_id": request_id,
            "mission_id": mission_id,
            "mission_revision": mission_revision,
            "capability_id": request.get("capability_id"),
            "request_sha256": request_hash,
            "relpath": relpath,
            "artifact_path": str(target),
            "artifact_sha256": digest,
            "bytes": len(data),
            "failure": None,
        }
        _atomic_write_json(receipt_path, journal)

        if self.fail_at == "before_effect":
            journal["state"] = "failed"
            journal["failure"] = "INJECTED_BEFORE_EFFECT"
            _atomic_write_json(receipt_path, journal)
            raise FilesystemArtifactError("INJECTED_BEFORE_EFFECT")

        _atomic_write_bytes(target, data)
        if self.fail_at == "after_effect":
            journal["state"] = "uncertain"
            journal["failure"] = "INJECTED_AFTER_EFFECT"
            _atomic_write_json(receipt_path, journal)
            raise FilesystemArtifactError("INJECTED_AFTER_EFFECT")

        try:
            if self.fail_at == "before_receipt_commit":
                raise FilesystemArtifactError("INJECTED_BEFORE_RECEIPT_COMMIT")
            journal["state"] = "committed"
            _atomic_write_json(receipt_path, journal)
        except Exception as error:
            journal["state"] = "uncertain"
            journal["failure"] = f"RECEIPT_FINALIZATION_FAILED:{type(error).__name__}"
            try:
                _atomic_write_json(receipt_path, journal)
            except Exception:
                pass
            if isinstance(error, FilesystemArtifactError):
                raise
            raise FilesystemArtifactError("RECEIPT_FINALIZATION_FAILED") from error

        return {
            **base,
            "status": "completed",
            "artifact_refs": [f"file:{relpath}"],
            "observed_effects": [
                {
                    "kind": "text-artifact-written",
                    "relpath": relpath,
                    "sha256": digest,
                    "bytes": len(data),
                }
            ],
            "external_receipt_ref": str(receipt_path),
        }


def verify_filesystem_receipt(
    external_receipt_ref: str,
    expected_request: Mapping[str, Any],
    root: Path,
) -> dict[str, Any]:
    """Verify receipt identity and recompute the observed artifact digest."""
    root = Path(root).resolve()
    receipt = Path(external_receipt_ref).resolve()
    receipts_root = (root / ".receipts").resolve()
    try:
        receipt.relative_to(receipts_root)
    except ValueError as error:
        raise FilesystemArtifactError("RECEIPT_PATH_OUTSIDE_ROOT") from error
    expected_receipt_path = _receipt_path(
        root, str(expected_request.get("request_id") or "")
    )
    if receipt != expected_receipt_path:
        raise FilesystemArtifactError("RECEIPT_PATH_IDENTITY_MISMATCH")
    if receipt.parent != receipts_root or not receipt.is_file():
        raise FilesystemArtifactError("RECEIPT_NOT_FOUND")
    try:
        body = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FilesystemArtifactError("RECEIPT_INVALID") from error
    if not isinstance(body, dict) or body.get("schema") != "filesystem-artifact-receipt@1":
        raise FilesystemArtifactError("RECEIPT_INVALID")
    if body.get("state") != "committed":
        raise FilesystemArtifactError(f"RECEIPT_NOT_COMMITTED:{body.get('state')}")
    for field in ("request_id", "mission_id", "mission_revision", "capability_id"):
        if body.get(field) != expected_request.get(field):
            raise FilesystemArtifactError(f"RECEIPT_{field.upper()}_MISMATCH")
    if body.get("adapter_ref") != _ADAPTER_REF:
        raise FilesystemArtifactError("RECEIPT_ADAPTER_MISMATCH")
    if body.get("request_sha256") != _canonical_sha256(dict(expected_request)):
        raise FilesystemArtifactError("RECEIPT_REQUEST_HASH_MISMATCH")
    relpath = body.get("relpath")
    artifact_path = body.get("artifact_path")
    if not isinstance(relpath, str) or not isinstance(artifact_path, str):
        raise FilesystemArtifactError("RECEIPT_ARTIFACT_IDENTITY_INVALID")
    expected_path = (root / relpath).resolve()
    try:
        expected_path.relative_to(root)
    except ValueError as error:
        raise FilesystemArtifactError("ARTIFACT_PATH_OUTSIDE_ROOT") from error
    if Path(artifact_path).resolve() != expected_path or not expected_path.is_file():
        raise FilesystemArtifactError("ARTIFACT_NOT_FOUND_OR_MISMATCH")
    data = expected_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != body.get("artifact_sha256") or len(data) != body.get("bytes"):
        raise FilesystemArtifactError("ARTIFACT_HASH_MISMATCH")
    return deepcopy(body)
