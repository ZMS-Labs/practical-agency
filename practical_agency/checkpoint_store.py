"""Atomic, content-addressed mission checkpoints."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .manifest_model import MissionManifest

_SAFE_ID = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z")
_CHECKPOINT_FIELDS = {
    "schema",
    "mission_id",
    "revision",
    "prior_checkpoint",
    "manifest",
    "events",
    "receipts",
}


class CheckpointError(RuntimeError):
    """Raised when durable checkpoint invariants fail."""


@dataclass(frozen=True, slots=True)
class CheckpointReceipt:
    mission_id: str
    revision: int
    sha256: str
    path: Path
    prior_checkpoint: str | None


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _fsync_dir(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class CheckpointStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _mission_dir(self, mission_id: str) -> Path:
        if not _SAFE_ID.fullmatch(mission_id):
            raise CheckpointError("UNSAFE_MISSION_ID: mission_id is not filesystem-safe")
        path = self.root / mission_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _read_pointer(self, mission_dir: Path) -> dict[str, Any] | None:
        pointer_path = mission_dir / "LATEST"
        if pointer_path.is_symlink():
            raise CheckpointError(
                "CHECKPOINT_SYMLINK_FORBIDDEN: LATEST pointer cannot be a symlink"
            )
        if not pointer_path.exists():
            return None
        try:
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CheckpointError(f"INVALID_POINTER: {error}") from error
        required = {"schema", "mission_id", "revision", "sha256", "filename"}
        if not isinstance(pointer, dict) or set(pointer) != required or pointer.get("schema") != "checkpoint-pointer@1":
            raise CheckpointError("INVALID_POINTER: pointer shape is not checkpoint-pointer@1")
        mission_id = pointer.get("mission_id")
        revision = pointer.get("revision")
        digest = pointer.get("sha256")
        filename = pointer.get("filename")
        if mission_id != mission_dir.name:
            raise CheckpointError("INVALID_POINTER: mission identity differs from directory")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise CheckpointError("INVALID_POINTER: revision must be a positive integer")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise CheckpointError("INVALID_POINTER: sha256 must be lowercase hexadecimal")
        expected_filename = f"r{revision:08d}-{digest[:12]}.json"
        if filename != expected_filename:
            raise CheckpointError("INVALID_POINTER: filename does not match revision and digest")
        return pointer

    def save(
        self,
        manifest: MissionManifest,
        *,
        events: Iterable[Mapping[str, Any]] = (),
        receipts: Iterable[Mapping[str, Any]] = (),
    ) -> CheckpointReceipt:
        mission_dir = self._mission_dir(manifest.mission_id)
        pointer = self._read_pointer(mission_dir)
        prior_sha: str | None = None
        if pointer is not None:
            prior_revision = pointer["revision"]
            if manifest.revision < prior_revision:
                raise CheckpointError(
                    f"NON_MONOTONIC_REVISION: {manifest.revision} < {prior_revision}"
                )
            prior_sha = pointer["sha256"] if manifest.revision > prior_revision else None

        bundle: dict[str, Any] = {
            "schema": "checkpoint@1",
            "mission_id": manifest.mission_id,
            "revision": manifest.revision,
            "prior_checkpoint": prior_sha,
            "manifest": manifest.to_dict(),
            "events": [dict(item) for item in events],
            "receipts": [dict(item) for item in receipts],
        }
        try:
            data = _canonical_bytes(bundle)
        except (TypeError, ValueError) as error:
            raise CheckpointError(f"CHECKPOINT_SERIALIZATION_FAILED: {error}") from error
        digest = hashlib.sha256(data).hexdigest()
        filename = f"r{manifest.revision:08d}-{digest[:12]}.json"
        final_path = mission_dir / filename

        if pointer is not None and manifest.revision == pointer["revision"]:
            if pointer["sha256"] != digest:
                raise CheckpointError("REVISION_CONFLICT: same revision has different content")
            if not final_path.exists():
                raise CheckpointError("MISSING_CHECKPOINT: pointer references absent content")
            return CheckpointReceipt(
                manifest.mission_id, manifest.revision, digest, final_path, None
            )

        bundle_tmp: Path | None = None
        pointer_tmp: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=mission_dir, prefix=".checkpoint-", suffix=".tmp", delete=False
            ) as handle:
                bundle_tmp = Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(bundle_tmp, final_path)
            bundle_tmp = None
            _fsync_dir(mission_dir)

            pointer_payload = {
                "schema": "checkpoint-pointer@1",
                "mission_id": manifest.mission_id,
                "revision": manifest.revision,
                "sha256": digest,
                "filename": filename,
            }
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=mission_dir, prefix=".pointer-", suffix=".tmp", delete=False
            ) as handle:
                pointer_tmp = Path(handle.name)
                handle.write(_canonical_bytes(pointer_payload))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(pointer_tmp, mission_dir / "LATEST")
            pointer_tmp = None
            _fsync_dir(mission_dir)
        except OSError as error:
            for temporary in (bundle_tmp, pointer_tmp):
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            raise CheckpointError(f"CHECKPOINT_WRITE_FAILED: {error}") from error

        return CheckpointReceipt(
            manifest.mission_id,
            manifest.revision,
            digest,
            final_path,
            prior_sha,
        )

    def load_latest(self, mission_id: str) -> tuple[MissionManifest, CheckpointReceipt]:
        mission_dir = self._mission_dir(mission_id)
        pointer = self._read_pointer(mission_dir)
        if pointer is None:
            raise CheckpointError("NO_CHECKPOINT: mission has no LATEST pointer")
        path = mission_dir / pointer["filename"]
        if path.is_symlink():
            raise CheckpointError(
                "CHECKPOINT_SYMLINK_FORBIDDEN: checkpoint content cannot be a symlink"
            )
        try:
            data = path.read_bytes()
        except OSError as error:
            raise CheckpointError(f"MISSING_CHECKPOINT: {error}") from error
        digest = hashlib.sha256(data).hexdigest()
        if digest != pointer["sha256"]:
            raise CheckpointError("CHECKSUM_MISMATCH: checkpoint bytes do not match pointer")
        try:
            bundle = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CheckpointError(f"INVALID_CHECKPOINT_JSON: {error}") from error
        if (
            not isinstance(bundle, dict)
            or set(bundle) != _CHECKPOINT_FIELDS
            or bundle.get("schema") != "checkpoint@1"
        ):
            raise CheckpointError("INVALID_CHECKPOINT: root shape is not checkpoint@1")
        if bundle.get("mission_id") != mission_id or bundle.get("revision") != pointer["revision"]:
            raise CheckpointError("POINTER_BUNDLE_MISMATCH: identity or revision differs")
        prior = bundle.get("prior_checkpoint")
        if prior is not None and (not isinstance(prior, str) or not _SHA256.fullmatch(prior)):
            raise CheckpointError("INVALID_CHECKPOINT: prior_checkpoint is not a sha256 or null")
        for field in ("events", "receipts"):
            value = bundle.get(field)
            if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
                raise CheckpointError(f"INVALID_CHECKPOINT: {field} must be a list of objects")
        manifest_payload = bundle.get("manifest")
        if not isinstance(manifest_payload, dict):
            raise CheckpointError("INVALID_CHECKPOINT: manifest is not an object")
        try:
            manifest = MissionManifest.from_dict(manifest_payload)
        except ValueError as error:
            raise CheckpointError(f"INVALID_CHECKPOINT_MANIFEST: {error}") from error
        if manifest.mission_id != mission_id or manifest.revision != pointer["revision"]:
            raise CheckpointError(
                "MANIFEST_BUNDLE_MISMATCH: nested manifest identity or revision differs"
            )
        receipt = CheckpointReceipt(
            mission_id=mission_id,
            revision=pointer["revision"],
            sha256=digest,
            path=path,
            prior_checkpoint=bundle.get("prior_checkpoint"),
        )
        return manifest, receipt
