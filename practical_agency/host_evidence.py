"""Fixed-schema host evidence for Codex manifest engagements.

The hook is the only writer of these control records. They are provenance and
covered-tool posture evidence, not cryptographic principal identity.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class HostEvidenceError(RuntimeError):
    """Named refusal for absent, malformed, stale, or mismatched host evidence."""


_CONTEXT_FIELDS = {
    "schema",
    "prompt",
    "prompt_sha256",
    "workspace_root",
    "session_id",
    "turn_id",
    "context_nonce",
    "hook_definition_sha256",
    "created_at",
}
_GATE_FIELDS = {
    "schema",
    "tool_name",
    "tool_use_id",
    "session_id",
    "turn_id",
    "workspace_root",
    "hook_definition_sha256",
    "lock_reason",
    "context_nonce_sha256",
    "decision",
}
_GATE_DECISIONS = {"allow-controller", "deny-covered-tool"}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
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
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _workspace_root(path: Path | str, code: str) -> Path:
    raw = Path(path)
    if raw.is_symlink():
        raise HostEvidenceError(code)
    workspace = raw.resolve()
    marker = workspace / ".git"
    if not workspace.is_dir() or marker.is_symlink() or not marker.exists():
        raise HostEvidenceError(code)
    return workspace


def _safe_directory(path: Path, workspace: Path, code: str) -> Path:
    if path.is_symlink():
        raise HostEvidenceError(code)
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise HostEvidenceError(code)
    resolved = path.resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError as error:
        raise HostEvidenceError(code) from error
    return resolved


def _control_root(workspace: Path, name: str, code: str) -> Path:
    missions = _safe_directory(workspace / "missions", workspace, code)
    return _safe_directory(missions / name, workspace, code)


def _context_path(workspace: Path, session_id: str, turn_id: str) -> Path:
    root = _control_root(workspace, ".host-context", "HOST_CONTEXT_INVALID")
    session = _safe_directory(
        root / _sha256_text(session_id), workspace, "HOST_CONTEXT_INVALID"
    )
    path = session / f"{_sha256_text(turn_id)}.json"
    if path.is_symlink():
        raise HostEvidenceError("HOST_CONTEXT_INVALID")
    return path


def _gate_path(workspace: Path, tool_use_id: str) -> Path:
    root = _control_root(workspace, ".host-gates", "HOST_GATE_UNAVAILABLE")
    path = root / f"{_sha256_text(tool_use_id)}.json"
    if path.is_symlink():
        raise HostEvidenceError("HOST_GATE_UNAVAILABLE")
    return path


def hook_definition_sha256(plugin_root: Path | str) -> str:
    root = Path(plugin_root).resolve()
    digest = hashlib.sha256()
    required = [root / "hooks" / "hooks.json", root / "hooks" / "manifest_hook.py"]
    package_root = root / "practical_agency"
    if package_root.is_symlink() or not package_root.is_dir():
        raise HostEvidenceError("HOST_CONTEXT_INVALID")
    runtime_paths = required + sorted(package_root.rglob("*.py"))
    for path in runtime_paths:
        if path.is_symlink() or not path.is_file():
            raise HostEvidenceError("HOST_CONTEXT_INVALID")
        try:
            relative = path.resolve().relative_to(root).as_posix()
        except ValueError as error:
            raise HostEvidenceError("HOST_CONTEXT_INVALID") from error
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class HostContextReceipt:
    path: str
    prompt: str
    prompt_sha256: str
    workspace_root: str
    session_id: str
    turn_id: str
    context_nonce: str
    hook_definition_sha256: str
    created_at: str


@dataclass(frozen=True, slots=True)
class HostGateReceipt:
    path: str
    tool_name: str
    tool_use_id: str
    session_id: str
    turn_id: str
    workspace_root: str
    hook_definition_sha256: str
    lock_reason: str
    context_nonce_sha256: str
    decision: str


@dataclass(frozen=True, slots=True)
class HostBinding:
    context: HostContextReceipt
    gate: HostGateReceipt
    workspace_root: Path


def _read_json(path: Path, *, code: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise HostEvidenceError(code)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HostEvidenceError(code) from error
    if not isinstance(payload, dict):
        raise HostEvidenceError(code)
    return payload


def load_host_context(
    context_ref: str | Path,
    *,
    plugin_root: Path | str,
) -> HostContextReceipt:
    path = Path(context_ref)
    payload = _read_json(path, code="HOST_CONTEXT_INVALID")
    if set(payload) != _CONTEXT_FIELDS or payload.get("schema") != "host-context@1":
        raise HostEvidenceError("HOST_CONTEXT_INVALID")
    for field in (
        "prompt",
        "workspace_root",
        "session_id",
        "turn_id",
        "created_at",
    ):
        if not _nonempty(payload.get(field)):
            raise HostEvidenceError("HOST_CONTEXT_INVALID")
    if (
        not _is_sha256(payload.get("prompt_sha256"))
        or not _is_sha256(payload.get("context_nonce"))
        or not _is_sha256(payload.get("hook_definition_sha256"))
        or payload["prompt_sha256"] != _sha256_text(payload["prompt"])
    ):
        raise HostEvidenceError("HOST_CONTEXT_INVALID")
    workspace = _workspace_root(payload["workspace_root"], "HOST_CONTEXT_INVALID")
    expected_path = _context_path(workspace, payload["session_id"], payload["turn_id"])
    if path.resolve() != expected_path.resolve():
        raise HostEvidenceError("HOST_CONTEXT_INVALID")
    if payload["hook_definition_sha256"] != hook_definition_sha256(plugin_root):
        raise HostEvidenceError("HOST_CONTEXT_INVALID")
    return HostContextReceipt(
        path=str(path.resolve()),
        prompt=payload["prompt"],
        prompt_sha256=payload["prompt_sha256"],
        workspace_root=str(workspace),
        session_id=payload["session_id"],
        turn_id=payload["turn_id"],
        context_nonce=payload["context_nonce"],
        hook_definition_sha256=payload["hook_definition_sha256"],
        created_at=payload["created_at"],
    )


def write_host_context(
    *,
    workspace_root: Path | str,
    prompt: str,
    session_id: str,
    turn_id: str,
    plugin_root: Path | str,
) -> HostContextReceipt:
    workspace = _workspace_root(workspace_root, "HOST_CONTEXT_INVALID")
    if not all(_nonempty(item) for item in (prompt, session_id, turn_id)):
        raise HostEvidenceError("HOST_CONTEXT_INVALID")
    path = _context_path(workspace, session_id, turn_id)
    payload = {
        "schema": "host-context@1",
        "prompt": prompt,
        "prompt_sha256": _sha256_text(prompt),
        "workspace_root": str(workspace),
        "session_id": session_id,
        "turn_id": turn_id,
        "context_nonce": secrets.token_hex(32),
        "hook_definition_sha256": hook_definition_sha256(plugin_root),
        "created_at": _utc_now(),
    }
    _atomic_write_json(path, payload)
    return load_host_context(path, plugin_root=plugin_root)


def load_host_gate(gate_ref: str | Path, *, plugin_root: Path | str) -> HostGateReceipt:
    path = Path(gate_ref)
    payload = _read_json(path, code="HOST_GATE_UNAVAILABLE")
    if set(payload) != _GATE_FIELDS or payload.get("schema") != "host-gate-posture@1":
        raise HostEvidenceError("HOST_GATE_UNAVAILABLE")
    for field in (
        "tool_name",
        "tool_use_id",
        "session_id",
        "turn_id",
        "workspace_root",
        "lock_reason",
    ):
        if not _nonempty(payload.get(field)):
            raise HostEvidenceError("HOST_GATE_UNAVAILABLE")
    if (
        payload.get("decision") not in _GATE_DECISIONS
        or not _is_sha256(payload.get("hook_definition_sha256"))
        or not _is_sha256(payload.get("context_nonce_sha256"))
    ):
        raise HostEvidenceError("HOST_GATE_UNAVAILABLE")
    workspace = _workspace_root(payload["workspace_root"], "HOST_GATE_UNAVAILABLE")
    expected_path = _gate_path(workspace, payload["tool_use_id"])
    if path.resolve() != expected_path.resolve():
        raise HostEvidenceError("HOST_GATE_UNAVAILABLE")
    if payload["hook_definition_sha256"] != hook_definition_sha256(plugin_root):
        raise HostEvidenceError("HOST_GATE_UNAVAILABLE")
    return HostGateReceipt(
        path=str(path.resolve()),
        tool_name=payload["tool_name"],
        tool_use_id=payload["tool_use_id"],
        session_id=payload["session_id"],
        turn_id=payload["turn_id"],
        workspace_root=str(workspace),
        hook_definition_sha256=payload["hook_definition_sha256"],
        lock_reason=payload["lock_reason"],
        context_nonce_sha256=payload["context_nonce_sha256"],
        decision=payload["decision"],
    )


def write_host_gate(
    *,
    context_ref: str | Path,
    tool_name: str,
    tool_use_id: str,
    session_id: str,
    turn_id: str,
    workspace_root: Path | str,
    lock_reason: str,
    decision: str,
    plugin_root: Path | str,
) -> HostGateReceipt:
    if decision not in _GATE_DECISIONS or not all(
        _nonempty(item)
        for item in (tool_name, tool_use_id, session_id, turn_id, lock_reason)
    ):
        raise HostEvidenceError("HOST_GATE_UNAVAILABLE")
    context = load_host_context(context_ref, plugin_root=plugin_root)
    workspace = _workspace_root(workspace_root, "HOST_GATE_UNAVAILABLE")
    if (
        context.workspace_root != str(workspace)
        or context.session_id != session_id
        or context.turn_id != turn_id
    ):
        raise HostEvidenceError("HOST_GATE_UNAVAILABLE")
    path = _gate_path(workspace, tool_use_id)
    payload = {
        "schema": "host-gate-posture@1",
        "tool_name": tool_name,
        "tool_use_id": tool_use_id,
        "session_id": session_id,
        "turn_id": turn_id,
        "workspace_root": str(workspace),
        "hook_definition_sha256": context.hook_definition_sha256,
        "lock_reason": lock_reason,
        "context_nonce_sha256": _sha256_text(context.context_nonce),
        "decision": decision,
    }
    _atomic_write_json(path, payload)
    return load_host_gate(path, plugin_root=plugin_root)


def validate_host_bindings(
    *,
    context_ref: str | Path,
    gate_ref: str | Path,
    expected_tool_name: str,
    plugin_root: Path | str,
) -> HostBinding:
    try:
        context = load_host_context(context_ref, plugin_root=plugin_root)
        gate = load_host_gate(gate_ref, plugin_root=plugin_root)
    except HostEvidenceError as error:
        if str(error) == "HOST_CONTEXT_INVALID":
            raise
        raise HostEvidenceError("HOST_GATE_UNAVAILABLE") from error
    if (
        gate.decision != "allow-controller"
        or gate.tool_name != expected_tool_name
        or gate.session_id != context.session_id
        or gate.turn_id != context.turn_id
        or gate.workspace_root != context.workspace_root
        or gate.hook_definition_sha256 != context.hook_definition_sha256
        or gate.context_nonce_sha256 != _sha256_text(context.context_nonce)
    ):
        raise HostEvidenceError("HOST_GATE_UNAVAILABLE")
    return HostBinding(
        context=context,
        gate=gate,
        workspace_root=Path(context.workspace_root),
    )


def current_context_ref(
    *, workspace_root: Path | str, session_id: str, turn_id: str
) -> str:
    workspace = _workspace_root(workspace_root, "HOST_CONTEXT_INVALID")
    path = _context_path(workspace, session_id, turn_id)
    if not path.is_file() or path.is_symlink():
        raise HostEvidenceError("HOST_CONTEXT_INVALID")
    return str(path.resolve())
