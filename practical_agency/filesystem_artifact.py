"""Bounded filesystem artifact adapter with journaled external receipts.

Stdlib-only. No shell. Writes only under an allowlisted root prefix.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping

_ADAPTER_REF = "filesystem-artifact@1"
_CAPABILITY_ID = "filesystem-artifact"
_RELPATH = re.compile(r"^relpath:(?P<path>.+)$")
_UTF8 = re.compile(r"^utf8:(?P<body>.*)$", re.S)
_SAFE_RELPATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_RECEIPT_FIELDS = {
    "schema",
    "status",
    "adapter_ref",
    "request_id",
    "mission_id",
    "mission_revision",
    "relpath",
    "artifact_path",
    "artifact_sha256",
    "bytes",
}


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        try:
            directory_fd = os.open(
                path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            )
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            # The file itself was flushed and atomically replaced. Some
            # filesystems do not permit directory fsync.
            pass
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _receipt_bytes(body: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(dict(body), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def verify_filesystem_receipt(receipt_ref: str | Path) -> dict[str, Any]:
    """Verify a finalized adapter receipt against the observed artifact bytes."""

    path = Path(receipt_ref)
    if path.is_symlink():
        raise ValueError("FILESYSTEM_RECEIPT_SYMLINK")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"FILESYSTEM_RECEIPT_UNREADABLE:{error}") from error
    if not isinstance(payload, dict) or set(payload) != _RECEIPT_FIELDS:
        raise ValueError("INVALID_FILESYSTEM_RECEIPT:fields")
    if payload.get("schema") != "filesystem-artifact-receipt@1":
        raise ValueError("INVALID_FILESYSTEM_RECEIPT:schema")
    if payload.get("status") != "completed":
        raise ValueError("FILESYSTEM_RECEIPT_NOT_FINAL")
    if payload.get("adapter_ref") != _ADAPTER_REF:
        raise ValueError("INVALID_FILESYSTEM_RECEIPT:adapter_ref")

    artifact_raw = payload.get("artifact_path")
    expected_digest = payload.get("artifact_sha256")
    expected_bytes = payload.get("bytes")
    if not isinstance(artifact_raw, str) or not artifact_raw:
        raise ValueError("INVALID_FILESYSTEM_RECEIPT:artifact_path")
    if (
        not isinstance(expected_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None
    ):
        raise ValueError("INVALID_FILESYSTEM_RECEIPT:artifact_sha256")
    if (
        isinstance(expected_bytes, bool)
        or not isinstance(expected_bytes, int)
        or expected_bytes < 0
    ):
        raise ValueError("INVALID_FILESYSTEM_RECEIPT:bytes")

    root = path.resolve().parent.parent
    artifact = Path(artifact_raw)
    if artifact.is_symlink():
        raise ValueError("FILESYSTEM_ARTIFACT_SYMLINK")
    try:
        resolved = artifact.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise ValueError("FILESYSTEM_RECEIPT_ARTIFACT_OUTSIDE_ROOT") from error
    try:
        data = resolved.read_bytes()
    except OSError as error:
        raise ValueError(f"FILESYSTEM_RECEIPT_ARTIFACT_UNREADABLE:{error}") from error
    if len(data) != expected_bytes:
        raise ValueError("FILESYSTEM_RECEIPT_BYTE_COUNT_MISMATCH")
    if hashlib.sha256(data).hexdigest() != expected_digest:
        raise ValueError("FILESYSTEM_RECEIPT_HASH_MISMATCH")
    return dict(payload)


class FilesystemArtifactAdapter:
    """Write text artifacts under a rooted allowlist and emit durable receipts."""

    capability_id = _CAPABILITY_ID
    adapter_ref = _ADAPTER_REF

    def __init__(
        self,
        root: Path,
        *,
        allowed_prefixes: tuple[str, ...] = ("mission-artifacts/",),
    ) -> None:
        self.root = Path(root).resolve()
        self.allowed_prefixes = tuple(allowed_prefixes)
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
            "adapter_ref": _ADAPTER_REF,
            "artifact_refs": [],
            "observed_effects": [],
            "external_receipt_ref": None,
            "coverage_limits": [
                "filesystem-artifact@1 writes text under allowlisted prefixes only",
                "no arbitrary shell",
                "a prepared durable journal precedes the world effect",
                "a completed receipt is hash-verified against artifact bytes",
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
        receipt_name = hashlib.sha256(request_id.encode("utf-8")).hexdigest() + ".json"
        receipt_path = self.root / ".receipts" / receipt_name
        if receipt_path.is_symlink():
            raise OSError("FILESYSTEM_RECEIPT_PATH_SYMLINK")

        receipt_body = {
            "schema": "filesystem-artifact-receipt@1",
            "status": "prepared",
            "adapter_ref": _ADAPTER_REF,
            "request_id": request_id,
            "mission_id": mission_id,
            "mission_revision": mission_revision,
            "relpath": relpath,
            "artifact_path": str(target),
            "artifact_sha256": digest,
            "bytes": len(data),
        }

        # The prepared record is durable before any world effect. If the process
        # stops after replacement but before finalization, recovery observes an
        # explicit uncertain/prepared record instead of an unreceipted effect.
        _atomic_write(receipt_path, _receipt_bytes(receipt_body))
        _atomic_write(target, data)

        completed_body = {**receipt_body, "status": "completed"}
        _atomic_write(receipt_path, _receipt_bytes(completed_body))

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
            "external_receipt_ref": str(receipt_path.resolve()),
        }
