"""Closed, authority-preserving mission-state transitions."""
from __future__ import annotations

from copy import deepcopy

from practical_agency.manifest_model import MissionManifest, MissionStatus
from practical_agency.state_machine_evidence import apply_evidence_event
from practical_agency.state_machine_lifecycle import apply_lifecycle_event
from practical_agency.state_machine_mission_os import apply_mission_os_event
from practical_agency.state_machine_support import (
    MissionEvent,
    TransitionError,
    _validate_event_envelope,
)

_ALLOWED_FROM: dict[str, set[str]] = {
    "approve": {MissionStatus.DRAFT.value},
    "pause": {MissionStatus.ACTIVE.value},
    "resume": {MissionStatus.PAUSED.value},
    "block": {
        MissionStatus.ACTIVE.value,
        MissionStatus.PAUSED.value,
        MissionStatus.VERIFYING.value,
    },
    "unblock": {MissionStatus.BLOCKED.value},
    "begin_verification": {MissionStatus.ACTIVE.value},
    "accept": {MissionStatus.VERIFYING.value},
    "reject": {MissionStatus.VERIFYING.value},
    "revoke": {
        MissionStatus.DRAFT.value,
        MissionStatus.ACTIVE.value,
        MissionStatus.PAUSED.value,
        MissionStatus.BLOCKED.value,
        MissionStatus.VERIFYING.value,
    },
    "cancel": {
        MissionStatus.DRAFT.value,
        MissionStatus.ACTIVE.value,
        MissionStatus.PAUSED.value,
        MissionStatus.BLOCKED.value,
        MissionStatus.VERIFYING.value,
    },
    "record_action": {MissionStatus.ACTIVE.value},
    "record_execution_receipt": {
        MissionStatus.ACTIVE.value,
        MissionStatus.BLOCKED.value,
    },
    "record_observation": {
        MissionStatus.ACTIVE.value,
        MissionStatus.BLOCKED.value,
    },
    "amend_authority": {
        MissionStatus.DRAFT.value,
        MissionStatus.ACTIVE.value,
        MissionStatus.PAUSED.value,
        MissionStatus.BLOCKED.value,
    },
    "apply_mission_os": {
        MissionStatus.ACTIVE.value,
        MissionStatus.COMPLETED.value,
    },
}


def apply_event(manifest: MissionManifest, event: MissionEvent) -> MissionManifest:
    _validate_event_envelope(manifest, event)
    if event.kind not in _ALLOWED_FROM:
        raise TransitionError(f"UNKNOWN_EVENT:{event.kind}")

    current = manifest.state.get("status")
    if manifest.authority.get("revoked") is True and event.kind != "cancel":
        raise TransitionError("AUTHORITY_REVOKED")
    if current not in _ALLOWED_FROM[event.kind]:
        raise TransitionError(f"INVALID_TRANSITION:{current}->{event.kind}")

    original_instruction = manifest.authority.get("instruction")
    data = manifest.to_dict()
    payload = deepcopy(dict(event.data))
    continuity = data["continuity"]
    new_revision = manifest.revision + 1

    handled = apply_lifecycle_event(data, manifest, event, payload)
    if not handled:
        handled = apply_evidence_event(
            data,
            manifest,
            event,
            payload,
            new_revision=new_revision,
        )
    if not handled:
        handled = apply_mission_os_event(
            data,
            manifest,
            event,
            payload,
            new_revision=new_revision,
        )
    if not handled:
        raise TransitionError(f"UNKNOWN_EVENT:{event.kind}")

    checkpoint_ref = payload.get("checkpoint_ref")
    if isinstance(checkpoint_ref, str) and checkpoint_ref.strip():
        continuity["prior_checkpoint"] = checkpoint_ref

    continuity["decisions"].append(
        {
            "kind": "mission-event-apply",
            "event_id": event.event_id,
            "event_kind": event.kind,
            "mission_id": event.mission_id,
            "expected_revision": event.expected_revision,
            "actor_ref": event.actor_ref,
            "observed_at": event.observed_at,
            "applied_revision": new_revision,
        }
    )
    data["revision"] = new_revision
    if data["authority"].get("instruction") != original_instruction:
        raise TransitionError("OPERATOR_INSTRUCTION_MUTATED")
    return MissionManifest.from_dict(data)
