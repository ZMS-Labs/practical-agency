"""Closed governed-path baselines and receipt-subtracted drift detection."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


_SAFE_RELPATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class GovernedWorkspaceError(RuntimeError):
    """A governed path or durable baseline is unsafe or malformed."""


@dataclass(frozen=True, slots=True)
class WorkspaceDriftFinding:
    path: str
    reason_code: str


def _normalized_relpath(raw: object) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise GovernedWorkspaceError("GOVERNED_PATH_INVALID")
    normalized = raw.replace("\\", "/")
    candidate = PurePosixPath(normalized)
    if (
        candidate.is_absolute()
        or not _SAFE_RELPATH.fullmatch(normalized)
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or candidate.parts[0].casefold() == "missions"
    ):
        raise GovernedWorkspaceError("GOVERNED_PATH_INVALID")
    return candidate.as_posix()


def _assert_safe_components(workspace_root: Path, relpath: str) -> Path:
    root = workspace_root.resolve()
    parts = PurePosixPath(relpath).parts
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise GovernedWorkspaceError("GOVERNED_PATH_SYMLINK")
    resolved = current.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise GovernedWorkspaceError("GOVERNED_PATH_ESCAPE") from error
    if resolved.exists() and not resolved.is_file():
        raise GovernedWorkspaceError("GOVERNED_PATH_NOT_REGULAR_FILE")
    return resolved


def normalize_governed_paths(
    workspace_root: Path | str, paths: Sequence[object]
) -> tuple[str, ...]:
    """Return unique normalized repository-relative regular-file paths."""

    root = Path(workspace_root)
    if not root.is_dir():
        raise GovernedWorkspaceError("WORKSPACE_ROOT_INVALID")
    if not isinstance(paths, Sequence) or isinstance(paths, (str, bytes)) or not paths:
        raise GovernedWorkspaceError("GOVERNED_PATHS_REQUIRED")
    normalized: list[str] = []
    for raw in paths:
        relpath = _normalized_relpath(raw)
        _assert_safe_components(root, relpath)
        if relpath in normalized:
            raise GovernedWorkspaceError("GOVERNED_PATH_DUPLICATE")
        normalized.append(relpath)
    return tuple(normalized)


def _file_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"kind": "absent"}
    if path.is_symlink() or not path.is_file():
        raise GovernedWorkspaceError("GOVERNED_PATH_NOT_REGULAR_FILE")
    data = path.read_bytes()
    return {
        "kind": "regular-file",
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _parent_components(root: Path, relpath: str) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    current = root.resolve()
    for part in PurePosixPath(relpath).parts[:-1]:
        current = current / part
        relative = current.relative_to(root.resolve()).as_posix()
        if current.is_symlink():
            raise GovernedWorkspaceError("GOVERNED_PATH_SYMLINK")
        if not current.exists():
            components.append({"path": relative, "kind": "absent"})
            continue
        if not current.is_dir():
            raise GovernedWorkspaceError("GOVERNED_PARENT_NOT_DIRECTORY")
        stat = current.stat()
        components.append(
            {
                "path": relative,
                "kind": "directory",
                "device": int(stat.st_dev),
                "inode": int(stat.st_ino),
            }
        )
    return components


def capture_baseline(
    workspace_root: Path | str, paths: Sequence[object]
) -> dict[str, Any]:
    """Capture literal byte state and parent identities for governed paths."""

    root = Path(workspace_root).resolve()
    normalized = normalize_governed_paths(root, paths)
    entries = []
    for relpath in normalized:
        target = _assert_safe_components(root, relpath)
        entries.append(
            {
                "path": relpath,
                "state": _file_state(target),
                "parent_components": _parent_components(root, relpath),
            }
        )
    return {
        "schema": "governed-workspace@1",
        "paths": list(normalized),
        "baseline": entries,
    }


def _state_is_valid(state: object) -> bool:
    if not isinstance(state, Mapping):
        return False
    if state.get("kind") == "absent":
        return set(state) == {"kind"}
    return (
        set(state) == {"kind", "bytes", "sha256"}
        and state.get("kind") == "regular-file"
        and isinstance(state.get("bytes"), int)
        and not isinstance(state.get("bytes"), bool)
        and int(state["bytes"]) >= 0
        and isinstance(state.get("sha256"), str)
        and _SHA256.fullmatch(str(state["sha256"])) is not None
    )


def validate_governed_workspace_record(value: object) -> None:
    """Validate the closed durable ``governed-workspace@1`` shape."""

    if not isinstance(value, Mapping) or set(value) != {"schema", "paths", "baseline"}:
        raise GovernedWorkspaceError("GOVERNED_WORKSPACE_INVALID")
    if value.get("schema") != "governed-workspace@1":
        raise GovernedWorkspaceError("GOVERNED_WORKSPACE_INVALID")
    paths = value.get("paths")
    baseline = value.get("baseline")
    if (
        not isinstance(paths, list)
        or not paths
        or len(set(paths)) != len(paths)
        or not all(isinstance(path, str) and _normalized_relpath(path) == path for path in paths)
        or not isinstance(baseline, list)
        or len(baseline) != len(paths)
    ):
        raise GovernedWorkspaceError("GOVERNED_WORKSPACE_INVALID")
    for path, entry in zip(paths, baseline, strict=True):
        if (
            not isinstance(entry, Mapping)
            or set(entry) != {"path", "state", "parent_components"}
            or entry.get("path") != path
            or not _state_is_valid(entry.get("state"))
            or not isinstance(entry.get("parent_components"), list)
        ):
            raise GovernedWorkspaceError("GOVERNED_WORKSPACE_INVALID")
        for component in entry["parent_components"]:
            if not isinstance(component, Mapping) or component.get("kind") not in {
                "absent",
                "directory",
            }:
                raise GovernedWorkspaceError("GOVERNED_WORKSPACE_INVALID")
            expected = {"path", "kind"}
            if component.get("kind") == "directory":
                expected |= {"device", "inode"}
            if set(component) != expected:
                raise GovernedWorkspaceError("GOVERNED_WORKSPACE_INVALID")


def _receipt_state(path: str, receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    expected: dict[str, Any] | None = None
    for receipt in receipts:
        if receipt.get("status") != "completed":
            continue
        effects = receipt.get("observed_effects")
        if not isinstance(effects, list):
            continue
        for effect in effects:
            if (
                isinstance(effect, Mapping)
                and effect.get("kind") == "text-artifact-written"
                and effect.get("relpath") == path
                and isinstance(effect.get("bytes"), int)
                and isinstance(effect.get("sha256"), str)
            ):
                expected = {
                    "kind": "regular-file",
                    "bytes": effect["bytes"],
                    "sha256": effect["sha256"],
                }
    return expected


def _existing_parent_identities_match(
    root: Path, entry: Mapping[str, Any]
) -> bool:
    expected = {
        component["path"]: component
        for component in entry["parent_components"]
        if component.get("kind") == "directory"
    }
    if not expected:
        return True
    observed = {
        component["path"]: component
        for component in _parent_components(root, str(entry["path"]))
    }
    return all(observed.get(path) == identity for path, identity in expected.items())


def find_unreceipted_drift(
    workspace_root: Path | str,
    governed_workspace: Mapping[str, Any],
    execution_receipts: Sequence[Mapping[str, Any]],
) -> list[WorkspaceDriftFinding]:
    """Report live governed state not explained by baseline plus receipts."""

    validate_governed_workspace_record(governed_workspace)
    root = Path(workspace_root).resolve()
    findings: list[WorkspaceDriftFinding] = []
    for entry in governed_workspace["baseline"]:
        relpath = str(entry["path"])
        expected = _receipt_state(relpath, execution_receipts) or dict(entry["state"])
        try:
            target = _assert_safe_components(root, relpath)
            observed = _file_state(target)
            parents_match = _existing_parent_identities_match(root, entry)
        except GovernedWorkspaceError:
            observed = {"kind": "unsafe-path-state"}
            parents_match = False
        if observed != expected or not parents_match:
            findings.append(
                WorkspaceDriftFinding(
                    path=relpath,
                    reason_code="UNRECEIPTED_WORKSPACE_DRIFT",
                )
            )
    return findings
