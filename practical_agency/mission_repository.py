"""Pathless discovery of one durable, unfinished mission in a workspace."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from practical_agency.checkpoint_store import (
    CheckpointError,
    CheckpointReceipt,
    FileCheckpointStore,
)
from practical_agency.manifest_model import MissionManifest, MissionStatus


class MissionDiscoveryError(RuntimeError):
    """Named refusal when active-mission discovery is absent or ambiguous."""


@dataclass(frozen=True, slots=True)
class DiscoveredMission:
    workspace_root: Path
    mission_dir: Path
    manifest: MissionManifest
    receipt: CheckpointReceipt


_TERMINAL_STATUSES = {
    MissionStatus.COMPLETED.value,
    MissionStatus.CANCELLED.value,
}


def discover_active_mission(workspace_root: Path) -> DiscoveredMission:
    """Discover exactly one unfinished mission under ``workspace_root/missions``.

    Mission identity and current revision come from validated checkpoint receipts,
    never from a caller-supplied mission path or mission id.
    """

    workspace = Path(workspace_root).resolve()
    missions_root = (workspace / "missions").resolve()
    if not missions_root.is_dir() or missions_root.is_symlink():
        raise MissionDiscoveryError("ACTIVE_MISSION_NOT_FOUND")

    candidates: list[DiscoveredMission] = []
    for mission_dir in sorted(missions_root.iterdir(), key=lambda item: item.name):
        if not mission_dir.is_dir() or mission_dir.is_symlink():
            continue
        checkpoints = mission_dir / "checkpoints"
        if not checkpoints.is_dir() or checkpoints.is_symlink():
            continue
        mission_ids: set[str] = set()
        try:
            receipt_paths = sorted(checkpoints.glob("*.r*.receipt.json"))
            for receipt_path in receipt_paths:
                if receipt_path.is_symlink():
                    raise CheckpointError("CHECKPOINT_RECEIPT_SYMLINK")
                payload = json.loads(receipt_path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise CheckpointError(
                        "INVALID_CHECKPOINT_RECEIPT: root must be object"
                    )
                receipt_identity = CheckpointReceipt.from_dict(payload)
                expected_name = (
                    f"{receipt_identity.mission_id}."
                    f"r{receipt_identity.revision:08d}.receipt.json"
                )
                if receipt_path.name != expected_name:
                    raise CheckpointError("CHECKPOINT_RECEIPT_FILENAME_MISMATCH")
                mission_ids.add(receipt_identity.mission_id)
        except (CheckpointError, OSError, json.JSONDecodeError) as error:
            raise MissionDiscoveryError(
                f"ACTIVE_MISSION_CHECKPOINT_INVALID:{mission_dir.name}:{error}"
            ) from error
        if not mission_ids:
            continue
        if len(mission_ids) != 1:
            identities = ",".join(sorted(mission_ids))
            raise MissionDiscoveryError(
                f"ACTIVE_MISSION_CHECKPOINT_AMBIGUOUS:{mission_dir.name}:"
                f"{identities}"
            )
        mission_id = next(iter(mission_ids))
        if mission_id != mission_dir.name:
            raise MissionDiscoveryError(
                f"ACTIVE_MISSION_DIRECTORY_MISMATCH:{mission_dir.name}:"
                f"{mission_id}"
            )
        try:
            latest = FileCheckpointStore(checkpoints).load_latest(mission_id)
        except CheckpointError as error:
            raise MissionDiscoveryError(
                f"ACTIVE_MISSION_CHECKPOINT_INVALID:{mission_dir.name}:{error}"
            ) from error
        if latest is None:
            continue
        manifest, receipt = latest
        if manifest.mission_id != mission_id:
            raise MissionDiscoveryError(
                f"ACTIVE_MISSION_DIRECTORY_MISMATCH:{mission_dir.name}:"
                f"{manifest.mission_id}"
            )
        if manifest.state.get("status") not in _TERMINAL_STATUSES:
            candidates.append(
                DiscoveredMission(
                    workspace_root=workspace,
                    mission_dir=mission_dir.resolve(),
                    manifest=manifest,
                    receipt=receipt,
                )
            )

    if not candidates:
        raise MissionDiscoveryError("ACTIVE_MISSION_NOT_FOUND")
    if len(candidates) != 1:
        mission_ids = ",".join(item.manifest.mission_id for item in candidates)
        raise MissionDiscoveryError(f"ACTIVE_MISSION_AMBIGUOUS:{mission_ids}")
    return candidates[0]
