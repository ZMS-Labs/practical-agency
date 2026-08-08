"""Mission-OS proposal application under sole-writer custody."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from practical_agency.deferred_interest import validate_deferred_interest
from practical_agency.manifest_model import MissionManifest, MissionStatus
from practical_agency.mission_os import (
    _defer_critical_path,
    _validate_basis_refs,
    _validate_contradiction_refs,
    _validate_labels,
    _validate_proposal_binding,
)
from practical_agency.state_machine_support import (
    MissionEvent,
    TransitionError,
    _operator_only,
    _require_mission_steward,
    _string_list,
)


def apply_mission_os_event(
    data: dict[str, Any],
    manifest: MissionManifest,
    event: MissionEvent,
    payload: Mapping[str, Any],
    *,
    new_revision: int,
) -> bool:
    """Apply a bound Mission-OS proposal, returning whether it was handled."""

    if event.kind != "apply_mission_os":
        return False

    current = manifest.state.get("status")
    state = data["state"]
    authority = data["authority"]
    continuity = data["continuity"]

    proposal_kind = payload.get("proposal_kind")
    if not isinstance(proposal_kind, str) or not proposal_kind.strip():
        raise TransitionError("MISSION_OS_PROPOSAL_KIND_REQUIRED")
    try:
        body = _validate_proposal_binding(manifest, proposal_kind, payload)
    except ValueError as exc:
        raise TransitionError(str(exc)) from exc

    if current == MissionStatus.COMPLETED.value and proposal_kind != "replan_slice":
        raise TransitionError("COMPLETED_REOPEN_REQUIRES_REPLAN")

    continuity.setdefault("deferred_interests", [])
    decision_extra: dict[str, Any] = {
        "proposal_id": payload["proposal_id"],
        "proposal_base_revision": payload["proposal_base_revision"],
        "proposal_payload_sha256": payload["proposal_payload_sha256"],
    }

    if proposal_kind in ("frontier_patch", "replan_slice"):
        _require_mission_steward(event)
        labels = _string_list(body, "labels", "FRONTIER_LABELS_REQUIRED", non_empty=True)
        try:
            _validate_labels(labels)
            basis_refs = _validate_basis_refs(manifest, body.get("basis_refs"))
        except ValueError as exc:
            raise TransitionError(str(exc)) from exc
        state["current_frontier"] = labels
        state["next_action"] = labels[0]
        decision_extra["basis_refs"] = basis_refs
        if proposal_kind == "replan_slice":
            try:
                contradiction_refs = _validate_contradiction_refs(
                    manifest, body.get("contradiction_refs")
                )
            except ValueError as exc:
                raise TransitionError(str(exc)) from exc
            decision_extra["contradiction_refs"] = contradiction_refs
            if current == MissionStatus.COMPLETED.value:
                state["status"] = MissionStatus.ACTIVE.value

    elif proposal_kind == "defer":
        _require_mission_steward(event)
        interest = body.get("interest")
        if not isinstance(interest, Mapping):
            raise TransitionError("DEFERRED_INTEREST_REQUIRED")
        copied = deepcopy(dict(interest))
        errors = validate_deferred_interest(copied, mission_id=manifest.mission_id)
        if errors:
            raise TransitionError(errors[0])
        if copied.get("created_at_revision") != manifest.revision:
            raise TransitionError("DEFERRED_INTEREST_REVISION_MISMATCH")
        try:
            _defer_critical_path(manifest, copied, completion_proof_ids=None)
        except ValueError as exc:
            raise TransitionError(str(exc)) from exc
        continuity["deferred_interests"].append(copied)

    elif proposal_kind == "return_rebind":
        _require_mission_steward(event)
        invalidate = body.get("invalidate")
        if not isinstance(invalidate, list) or not invalidate:
            raise TransitionError("RETURN_REBIND_INVALIDATE_REQUIRED")
        decision_extra["invalidate"] = deepcopy(invalidate)

    elif proposal_kind == "absorb":
        idx = body.get("interest_index")
        if isinstance(idx, bool) or not isinstance(idx, int):
            raise TransitionError("ABSORB_INTEREST_INDEX_REQUIRED")
        interests = continuity["deferred_interests"]
        if idx < 0 or idx >= len(interests):
            raise TransitionError("ABSORB_INTEREST_NOT_FOUND")
        interest = interests[idx]
        if not isinstance(interest, Mapping):
            raise TransitionError("ABSORB_INTEREST_NOT_FOUND")
        if interest.get("status") != "open":
            raise TransitionError("ABSORB_INTEREST_NOT_OPEN")
        if interest.get("criticality") == "high":
            _operator_only(manifest, event)
            amendment = body.get("amendment")
            if not isinstance(amendment, str) or not amendment.strip():
                raise TransitionError("HIGH_ABSORB_AMENDMENT_REQUIRED")
            authority["amendments"].append(amendment.strip())
        else:
            _require_mission_steward(event)
        interests[idx] = dict(interest)
        interests[idx]["status"] = "absorbed"
        decision_extra["interest_index"] = idx

    else:
        raise TransitionError(f"UNKNOWN_MISSION_OS_PROPOSAL:{proposal_kind}")

    continuity["decisions"].append(
        {
            "kind": "mission-os-apply",
            "proposal_kind": proposal_kind,
            "actor_ref": event.actor_ref,
            "at_revision": new_revision,
            **decision_extra,
        }
    )
    return True
