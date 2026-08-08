"""Immutable mission-manifest model and canonical serialization."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


class MissionStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    BLOCKED = "blocked"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class MissionManifest:
    schema: str
    mission_id: str
    revision: int
    authority: dict[str, Any]
    outcome: dict[str, Any]
    truth: dict[str, Any]
    state: dict[str, Any]
    capabilities: dict[str, Any]
    continuity: dict[str, Any]
    integrity: dict[str, Any]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissionManifest":
        from practical_agency.validation import validate_manifest_dict

        copied = deepcopy(dict(payload))
        continuity = copied.get("continuity")
        if isinstance(continuity, dict):
            continuity.setdefault("deferred_interests", [])
            continuity.setdefault("processed_event_ids", [])
            continuity.setdefault("execution_receipts", [])
        errors = validate_manifest_dict(copied)
        if errors:
            raise ValueError("INVALID_MISSION_MANIFEST: " + " | ".join(errors))
        return cls(
            schema=copied["schema"],
            mission_id=copied["mission_id"],
            revision=copied["revision"],
            authority=deepcopy(copied["authority"]),
            outcome=deepcopy(copied["outcome"]),
            truth=deepcopy(copied["truth"]),
            state=deepcopy(copied["state"]),
            capabilities=deepcopy(copied["capabilities"]),
            continuity=deepcopy(copied["continuity"]),
            integrity=deepcopy(copied["integrity"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "mission_id": self.mission_id,
            "revision": self.revision,
            "authority": deepcopy(self.authority),
            "outcome": deepcopy(self.outcome),
            "truth": deepcopy(self.truth),
            "state": deepcopy(self.state),
            "capabilities": deepcopy(self.capabilities),
            "continuity": deepcopy(self.continuity),
            "integrity": deepcopy(self.integrity),
        }

    def to_canonical_json(self) -> str:
        return json.dumps(
            self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ) + "\n"


def load_manifest(path: Path) -> MissionManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"INVALID_MISSION_FILE: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("INVALID_MISSION_FILE: root must be an object")
    return MissionManifest.from_dict(payload)
