"""Evidence and durable-receipt transition handlers."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

from practical_agency.manifest_model import MissionManifest, MissionStatus
from practical_agency.state_machine_support import (
    MissionEvent,
    TransitionError,
    _append_unique,
    _execution_receipt,
    _reconciliation_subject,
    _require_mission_steward,
    _required_string,
)


def apply_evidence_event(
    data: dict[str, Any],
    manifest: MissionManifest,
    event: MissionEvent,
    payload: Mapping[str, Any],
    *,
    new_revision: int,
) -> bool:
    """Apply an evidence/receipt event, returning whether it was handled."""

    state = data["state"]
    continuity = data["continuity"]
    integrity = data["integrity"]
    current = manifest.state.get("status")

    if event.kind == "record_action":
        action_ref = _required_string(payload, "action_ref", "ACTION_REF_REQUIRED")
        _append_unique(state["completed_actions"], action_ref)
        _append_unique(continuity["durable_artifacts"], action_ref)
        continuity["decisions"].append(
            {
                "kind": "material-action",
                "actor_ref": event.actor_ref,
                "action_ref": action_ref,
            }
        )

    elif event.kind == "record_execution_receipt":
        _require_mission_steward(event)
        receipt = _execution_receipt(manifest, payload)
        canonical = json.dumps(
            receipt,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        continuity["decisions"].append(
            {
                "kind": "execution-receipt",
                **receipt,
                "receipt_sha256": hashlib.sha256(canonical).hexdigest(),
                "recorded_by": event.actor_ref,
                "recorded_at": event.observed_at,
                "recorded_revision": new_revision,
            }
        )
        for artifact_ref in receipt["artifact_refs"]:
            _append_unique(continuity["durable_artifacts"], artifact_ref)

    elif event.kind == "record_observation":
        artifact_ref = _required_string(
            payload, "artifact_ref", "OBSERVATION_ARTIFACT_REQUIRED"
        )
        fact = payload.get("fact")
        if not isinstance(fact, Mapping) or set(fact) != {"subject_ref", "value"}:
            raise TransitionError("OBSERVATION_FACT_REQUIRED")
        subject_ref = fact.get("subject_ref")
        if not isinstance(subject_ref, str) or not subject_ref.strip():
            raise TransitionError("OBSERVATION_SUBJECT_REQUIRED")
        _append_unique(continuity["durable_artifacts"], artifact_ref)
        data["truth"]["verified_facts"] = [
            item
            for item in data["truth"]["verified_facts"]
            if not (
                isinstance(item, Mapping)
                and item.get("subject_ref") == subject_ref
            )
        ]
        data["truth"]["verified_facts"].append(deepcopy(dict(fact)))
        for field_name in ("contradictions", "unknowns"):
            data["truth"][field_name] = [
                item
                for item in data["truth"][field_name]
                if not (
                    isinstance(item, Mapping)
                    and item.get("subject_ref") == subject_ref
                )
            ]
        state["blockers"] = [
            marker
            for marker in state["blockers"]
            if _reconciliation_subject(marker) != subject_ref
        ]
        integrity["unresolved_verdicts"] = [
            marker
            for marker in integrity["unresolved_verdicts"]
            if _reconciliation_subject(marker) != subject_ref
        ]
        if current == MissionStatus.BLOCKED.value:
            if state["blockers"] or integrity["unresolved_verdicts"]:
                state["status"] = MissionStatus.BLOCKED.value
                state["next_action"] = (
                    f"resolve blocker: {state['blockers'][0]}"
                    if state["blockers"]
                    else "resolve unresolved verdict"
                )
            else:
                state["status"] = MissionStatus.ACTIVE.value
                state["next_action"] = (
                    state["current_frontier"][0]
                    if state["current_frontier"]
                    else "resume mission"
                )

    else:
        return False

    return True
