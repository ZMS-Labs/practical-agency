"""Atomic mission checkpoint store with SHA-256 receipts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from practical_agency.manifest_model import MissionManifest

CHECKPOINT_NAME = re.compile(r"^(?P<mission_id>.+)-(?P<revision>\d{4})\.json$")


@dataclass(frozen=True, slots=True)
class CheckpointReceipt:
    mission_id: str
    revision: int
    path: str
    sha256: str
    created_at: str


@dataclass(frozen=True, slots=True)
class ReconciliationFinding:
    subject_ref: str
    checkpoint_value: object
    live_value: object
    classification: str  # CONTRADICTED | MOVED | UNVERIFIED


class FileCheckpointStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, mission_id: str, revision: int) -> Path:
        return self.root / f"{mission_id}-{revision:04d}.json"

    def save(self, manifest: MissionManifest) -> CheckpointReceipt:
        target = self._path_for(manifest.mission_id, manifest.revision)
        payload = manifest.to_canonical_json().encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()

        if target.exists():
            existing = target.read_bytes()
            if existing != payload:
                raise ValueError(
                    "CHECKPOINT_IMMUTABLE: refusing to overwrite an existing revision "
                    "with different bytes"
                )
            return CheckpointReceipt(
                mission_id=manifest.mission_id,
                revision=manifest.revision,
                path=str(target),
                sha256=hashlib.sha256(existing).hexdigest(),
                created_at=datetime.now(timezone.utc).isoformat(),
            )

        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{manifest.mission_id}-{manifest.revision:04d}.",
            suffix=".json.tmp",
            dir=str(self.root),
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, target)
        finally:
            if os.path.exists(tmp_name):
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass

        return CheckpointReceipt(
            mission_id=manifest.mission_id,
            revision=manifest.revision,
            path=str(target),
            sha256=digest,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def load(self, receipt: CheckpointReceipt) -> MissionManifest:
        path = Path(receipt.path)
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != receipt.sha256:
            raise ValueError("CHECKPOINT_HASH_MISMATCH: on-disk bytes do not match receipt")
        payload = json.loads(raw.decode("utf-8"))
        return MissionManifest.from_dict(payload)

    def load_latest(
        self, mission_id: str
    ) -> tuple[MissionManifest, CheckpointReceipt] | None:
        candidates: list[tuple[int, Path]] = []
        for path in self.root.iterdir():
            if not path.is_file() or path.name.endswith(".tmp"):
                continue
            match = CHECKPOINT_NAME.match(path.name)
            if not match or match.group("mission_id") != mission_id:
                continue
            candidates.append((int(match.group("revision")), path))
        if not candidates:
            return None
        revision, path = max(candidates, key=lambda item: item[0])
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        receipt = CheckpointReceipt(
            mission_id=mission_id,
            revision=revision,
            path=str(path),
            sha256=digest,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        return MissionManifest.from_dict(json.loads(raw.decode("utf-8"))), receipt


def reconcile_observations(
    manifest: MissionManifest,
    observations: Mapping[str, Any],
) -> list[ReconciliationFinding]:
    """Compare adapter-supplied live observations to stored verified facts."""
    findings: list[ReconciliationFinding] = []
    stored: dict[str, Any] = {}
    for item in manifest.truth.get("verified_facts") or []:
        if isinstance(item, dict) and "subject_ref" in item:
            stored[str(item["subject_ref"])] = item.get("value")

    for subject_ref, live_value in observations.items():
        if subject_ref not in stored:
            findings.append(
                ReconciliationFinding(
                    subject_ref=subject_ref,
                    checkpoint_value=None,
                    live_value=live_value,
                    classification="UNVERIFIED",
                )
            )
            continue
        checkpoint_value = stored[subject_ref]
        if checkpoint_value != live_value:
            findings.append(
                ReconciliationFinding(
                    subject_ref=subject_ref,
                    checkpoint_value=checkpoint_value,
                    live_value=live_value,
                    classification="CONTRADICTED",
                )
            )
    for subject_ref, checkpoint_value in stored.items():
        if subject_ref not in observations:
            findings.append(
                ReconciliationFinding(
                    subject_ref=subject_ref,
                    checkpoint_value=checkpoint_value,
                    live_value=None,
                    classification="MOVED",
                )
            )
    return findings
