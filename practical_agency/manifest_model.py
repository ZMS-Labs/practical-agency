"""mission-manifest@1 dataclass carrier."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class MissionStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    BLOCKED = "blocked"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


def _deep_copy(value: Any) -> Any:
    return copy.deepcopy(value)


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
        return cls(
            schema=str(payload["schema"]),
            mission_id=str(payload["mission_id"]),
            revision=int(payload["revision"]),
            authority=_deep_copy(payload["authority"]),
            outcome=_deep_copy(payload["outcome"]),
            truth=_deep_copy(payload["truth"]),
            state=_deep_copy(payload["state"]),
            capabilities=_deep_copy(payload["capabilities"]),
            continuity=_deep_copy(payload["continuity"]),
            integrity=_deep_copy(payload["integrity"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "mission_id": self.mission_id,
            "revision": self.revision,
            "authority": _deep_copy(self.authority),
            "outcome": _deep_copy(self.outcome),
            "truth": _deep_copy(self.truth),
            "state": _deep_copy(self.state),
            "capabilities": _deep_copy(self.capabilities),
            "continuity": _deep_copy(self.continuity),
            "integrity": _deep_copy(self.integrity),
        }

    def to_canonical_json(self) -> str:
        return (
            json.dumps(
                self.to_dict(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )


def load_manifest(path: str | bytes) -> MissionManifest:
    """Load a mission manifest JSON file into a MissionManifest."""
    from pathlib import Path

    text = Path(path).read_text(encoding="utf-8")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("MANIFEST_NOT_OBJECT: top-level JSON must be an object")
    return MissionManifest.from_dict(payload)
