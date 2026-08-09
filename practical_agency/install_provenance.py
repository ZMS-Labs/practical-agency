"""Canonical byte manifest for source and installed plugin runtimes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class InstallProvenanceError(RuntimeError):
    """Named refusal for incomplete, unsafe, or unequal runtime trees."""


RUNTIME_PATHS = (
    ".codex-plugin",
    ".mcp.json",
    ".agents/plugins/marketplace.json",
    "hooks",
    "skills/manifest",
    "practical_agency",
    "contracts",
)


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _runtime_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for relative in RUNTIME_PATHS:
        subject = root / relative
        if subject.is_symlink() or not subject.exists():
            raise InstallProvenanceError(
                f"INSTALL_PROVENANCE_INPUT_INVALID:{relative}"
            )
        candidates = [subject] if subject.is_file() else list(subject.rglob("*"))
        for candidate in candidates:
            if candidate.is_symlink():
                raise InstallProvenanceError(
                    f"INSTALL_PROVENANCE_INPUT_INVALID:{candidate.relative_to(root).as_posix()}"
                )
            if not candidate.is_file():
                continue
            relative_path = candidate.relative_to(root).as_posix()
            if "__pycache__" in candidate.parts or relative_path.endswith((".pyc", ".pyo")):
                continue
            files.append(candidate)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def build_runtime_manifest(root: Path | str) -> dict[str, Any]:
    runtime_root = Path(root).resolve()
    if runtime_root.is_symlink() or not runtime_root.is_dir():
        raise InstallProvenanceError("INSTALL_PROVENANCE_INPUT_INVALID")
    entries = []
    for path in _runtime_files(runtime_root):
        content = path.read_bytes()
        entries.append(
            {
                "path": path.relative_to(runtime_root).as_posix(),
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    return {"schema": "plugin-runtime-manifest@1", "files": entries}


def compare_runtime_trees(
    source_root: Path | str, installed_root: Path | str
) -> dict[str, Any]:
    source = build_runtime_manifest(source_root)
    installed = build_runtime_manifest(installed_root)
    source_sha256 = _digest(source)
    installed_sha256 = _digest(installed)
    if source != installed:
        raise InstallProvenanceError(
            "INSTALL_PROVENANCE_MISMATCH:"
            f"source={source_sha256}:installed={installed_sha256}"
        )
    return {
        "status": "match",
        "source_manifest_sha256": source_sha256,
        "installed_manifest_sha256": installed_sha256,
        "file_count": len(source["files"]),
    }
