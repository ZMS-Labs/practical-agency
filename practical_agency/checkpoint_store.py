"""Atomic, hash-bound mission checkpoints and honest resumption."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from practical_agency.manifest_model import MissionManifest, MissionStatus


class CheckpointError(RuntimeError):
    """Named checkpoint integrity or storage failure."""


_RECEIPT_FIELDS = {
    "schema",
    "mission_id",
    "revision",
    "path",
    "sha256",
    "created_at",
}
_MISSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RECONCILIATION_CLASSES = {"CONTRADICTED", "MOVED", "UNVERIFIED"}


@dataclass(frozen=True, slots=True)
class CheckpointReceipt:
    mission_id: str
    revision: int
    path: str
    sha256: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {"schema": "checkpoint-receipt@1", **asdict(self)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CheckpointReceipt":
        if set(payload) != _RECEIPT_FIELDS:
            raise CheckpointError("INVALID_CHECKPOINT_RECEIPT: unexpected or missing fields")
        if payload.get("schema") != "checkpoint-receipt@1":
            raise CheckpointError("INVALID_CHECKPOINT_RECEIPT: invalid schema")

        mission_id = payload.get("mission_id")
        revision = payload.get("revision")
        path = payload.get("path")
        sha256 = payload.get("sha256")
        created_at = payload.get("created_at")
        if (
            not isinstance(mission_id, str)
            or not _MISSION_ID.fullmatch(mission_id)
            or isinstance(revision, bool)
            or not isinstance(revision, int)
            or revision < 1
            or not isinstance(path, str)
            or not path.strip()
            or not isinstance(sha256, str)
            or not _SHA256.fullmatch(sha256)
            or not isinstance(created_at, str)
            or not created_at.strip()
        ):
            raise CheckpointError("INVALID_CHECKPOINT_RECEIPT: invalid field type or value")
        return cls(
            mission_id=mission_id,
            revision=revision,
            path=path,
            sha256=sha256,
            created_at=created_at,
        )


@dataclass(frozen=True, slots=True)
class ReconciliationFinding:
    subject_ref: str
    checkpoint_value: object
    live_value: object
    classification: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", delete=False, dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        temp_path = None
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            # Some filesystems do not permit directory fsync; the file was still
            # flushed and atomically replaced.
            pass
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


class FileCheckpointStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _data_path(self, mission_id: str, revision: int) -> Path:
        return self.root / f"{mission_id}.r{revision:08d}.json"

    def _receipt_path(self, mission_id: str, revision: int) -> Path:
        return self.root / f"{mission_id}.r{revision:08d}.receipt.json"

    def save(self, manifest: MissionManifest) -> CheckpointReceipt:
        data = manifest.to_canonical_json().encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()
        data_path = self._data_path(manifest.mission_id, manifest.revision)
        receipt_path = self._receipt_path(manifest.mission_id, manifest.revision)

        if data_path.is_symlink() or receipt_path.is_symlink():
            raise CheckpointError("CHECKPOINT_PATH_SYMLINK")
        if data_path.exists():
            if data_path.read_bytes() != data:
                raise CheckpointError("CHECKPOINT_REVISION_COLLISION")
        else:
            _atomic_write(data_path, data)

        receipt = CheckpointReceipt(
            mission_id=manifest.mission_id,
            revision=manifest.revision,
            path=str(data_path.resolve()),
            sha256=digest,
            created_at=_utc_now(),
        )
        receipt_bytes = (
            json.dumps(receipt.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        if receipt_path.exists():
            existing = CheckpointReceipt.from_dict(
                json.loads(receipt_path.read_text(encoding="utf-8"))
            )
            if existing.sha256 != digest or Path(existing.path) != data_path.resolve():
                raise CheckpointError("CHECKPOINT_RECEIPT_COLLISION")
            return existing
        _atomic_write(receipt_path, receipt_bytes)
        return receipt

    def load(self, receipt: CheckpointReceipt) -> MissionManifest:
        supplied_path = Path(receipt.path)
        expected_raw = self._data_path(receipt.mission_id, receipt.revision)
        if supplied_path.is_symlink() or expected_raw.is_symlink():
            raise CheckpointError("CHECKPOINT_PATH_SYMLINK")

        root_path = self.root.resolve()
        expected_path = expected_raw.resolve()
        try:
            expected_path.relative_to(root_path)
        except ValueError as error:
            raise CheckpointError("CHECKPOINT_PATH_MISMATCH") from error
        path = supplied_path.resolve()
        if path != expected_path:
            raise CheckpointError("CHECKPOINT_PATH_MISMATCH")
        try:
            data = path.read_bytes()
        except OSError as error:
            raise CheckpointError(f"CHECKPOINT_UNREADABLE:{error}") from error
        actual = hashlib.sha256(data).hexdigest()
        if actual != receipt.sha256:
            raise CheckpointError("CHECKPOINT_HASH_MISMATCH")
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CheckpointError(f"CHECKPOINT_INVALID_JSON:{error}") from error
        if not isinstance(payload, dict):
            raise CheckpointError("CHECKPOINT_ROOT_MUST_BE_OBJECT")
        try:
            manifest = MissionManifest.from_dict(payload)
        except ValueError as error:
            raise CheckpointError(str(error)) from error
        if manifest.mission_id != receipt.mission_id or manifest.revision != receipt.revision:
            raise CheckpointError("CHECKPOINT_RECEIPT_IDENTITY_MISMATCH")
        return manifest

    def load_latest(
        self, mission_id: str
    ) -> tuple[MissionManifest, CheckpointReceipt] | None:
        if not _MISSION_ID.fullmatch(mission_id):
            raise CheckpointError("INVALID_MISSION_ID")
        pattern = re.compile(
            rf"^{re.escape(mission_id)}\.r(?P<revision>\d{{8}})\.receipt\.json$"
        )
        candidates: list[tuple[int, Path]] = []
        for path in self.root.iterdir():
            match = pattern.match(path.name)
            if match:
                if path.is_symlink():
                    raise CheckpointError("CHECKPOINT_RECEIPT_SYMLINK")
                candidates.append((int(match.group("revision")), path))
        if not candidates:
            return None
        candidate_revision, receipt_path = max(candidates, key=lambda item: item[0])
        try:
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CheckpointError(f"INVALID_CHECKPOINT_RECEIPT:{error}") from error
        if not isinstance(payload, dict):
            raise CheckpointError("INVALID_CHECKPOINT_RECEIPT: root must be object")
        receipt = CheckpointReceipt.from_dict(payload)
        if receipt.mission_id != mission_id or receipt.revision != candidate_revision:
            raise CheckpointError("CHECKPOINT_LATEST_IDENTITY_MISMATCH")
        return self.load(receipt), receipt


def reconcile_observations(
    manifest: MissionManifest, live_observations: Mapping[str, object]
) -> list[ReconciliationFinding]:
    findings: list[ReconciliationFinding] = []
    for fact in manifest.truth.get("verified_facts", []):
        if not isinstance(fact, Mapping):
            continue
        subject_ref = fact.get("subject_ref")
        if not isinstance(subject_ref, str) or not subject_ref:
            continue
        checkpoint_value = fact.get("value")
        if subject_ref not in live_observations:
            findings.append(
                ReconciliationFinding(
                    subject_ref, checkpoint_value, None, "UNVERIFIED"
                )
            )
            continue
        live_value = live_observations[subject_ref]
        if live_value != checkpoint_value:
            findings.append(
                ReconciliationFinding(
                    subject_ref, checkpoint_value, live_value, "CONTRADICTED"
                )
            )
    return findings


def apply_reconciliation_findings(
    manifest: MissionManifest,
    findings: Sequence[ReconciliationFinding],
) -> MissionManifest:
    """Reopen a mission and invalidate load-bearing proof for live-state drift.

    The checkpoint store does not decide whether the live observation is correct;
    it records the contradiction as unresolved and removes prior completion/gate
    artifacts from the set permitted to bear load. A fresh observation must clear
    the reconciliation blocker through the state machine.
    """

    if not findings:
        return manifest
    data = manifest.to_dict()
    truth = data["truth"]
    state = data["state"]
    integrity = data["integrity"]
    continuity = data["continuity"]
    subjects: list[str] = []

    for finding in findings:
        if (
            not isinstance(finding.subject_ref, str)
            or not finding.subject_ref.strip()
            or finding.classification not in _RECONCILIATION_CLASSES
        ):
            raise CheckpointError("INVALID_RECONCILIATION_FINDING")
        subject_ref = finding.subject_ref
        subjects.append(subject_ref)
        truth["verified_facts"] = [
            fact
            for fact in truth["verified_facts"]
            if not (
                isinstance(fact, Mapping)
                and fact.get("subject_ref") == subject_ref
            )
        ]
        evidence = {
            "subject_ref": subject_ref,
            "checkpoint_value": deepcopy(finding.checkpoint_value),
            "live_value": deepcopy(finding.live_value),
            "classification": finding.classification,
        }
        target = (
            truth["unknowns"]
            if finding.classification == "UNVERIFIED"
            else truth["contradictions"]
        )
        if evidence not in target:
            target.append(evidence)
        marker = f"RECONCILIATION:{finding.classification}:{subject_ref}"
        if marker not in state["blockers"]:
            state["blockers"].append(marker)
        if marker not in integrity["unresolved_verdicts"]:
            integrity["unresolved_verdicts"].append(marker)

    invalidated = set(data["outcome"]["completion_proof"]) | set(
        integrity["required_gates"]
    )
    continuity["durable_artifacts"] = [
        ref for ref in continuity["durable_artifacts"] if ref not in invalidated
    ]
    continuity["decisions"].append(
        {
            "kind": "live-state-reconciliation",
            "findings": [
                {
                    "subject_ref": item.subject_ref,
                    "checkpoint_value": deepcopy(item.checkpoint_value),
                    "live_value": deepcopy(item.live_value),
                    "classification": item.classification,
                }
                for item in findings
            ],
            "invalidated_artifact_refs": sorted(invalidated),
        }
    )
    if state["status"] != MissionStatus.CANCELLED.value:
        state["status"] = MissionStatus.BLOCKED.value
        state["next_action"] = "re-establish live proof for " + ", ".join(subjects)
    data["revision"] = manifest.revision + 1
    return MissionManifest.from_dict(data)
