"""Deeply immutable mission-manifest model and canonical serialization."""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class MissionStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    BLOCKED = "blocked"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    if isinstance(value, list):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class MissionManifest:
    schema: str
    mission_id: str
    revision: int
    authority: Mapping[str, Any]
    outcome: Mapping[str, Any]
    truth: Mapping[str, Any]
    state: Mapping[str, Any]
    capabilities: Mapping[str, Any]
    continuity: Mapping[str, Any]
    integrity: Mapping[str, Any]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissionManifest":
        from .validation import validate_manifest_dict

        raw = _thaw(payload)
        if not isinstance(raw, dict):
            raise ValueError("RECORD_MUST_BE_OBJECT: root must be an object")
        errors = validate_manifest_dict(raw)
        if errors:
            raise ValueError("; ".join(errors))
        return cls(
            schema=raw["schema"],
            mission_id=raw["mission_id"],
            revision=raw["revision"],
            authority=_freeze(raw["authority"]),
            outcome=_freeze(raw["outcome"]),
            truth=_freeze(raw["truth"]),
            state=_freeze(raw["state"]),
            capabilities=_freeze(raw["capabilities"]),
            continuity=_freeze(raw["continuity"]),
            integrity=_freeze(raw["integrity"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "mission_id": self.mission_id,
            "revision": self.revision,
            "authority": _thaw(self.authority),
            "outcome": _thaw(self.outcome),
            "truth": _thaw(self.truth),
            "state": _thaw(self.state),
            "capabilities": _thaw(self.capabilities),
            "continuity": _thaw(self.continuity),
            "integrity": _thaw(self.integrity),
        }

    def to_canonical_json(self) -> str:
        return json.dumps(
            self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ) + "\n"
