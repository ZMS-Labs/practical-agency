"""Closed mission-event transition table for mission-manifest@1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from practical_agency.manifest_model import MissionManifest, MissionStatus
from practical_agency.validation import validate_manifest_dict

STEWARD_REF = "mission-steward"

LEGAL_TRANSITIONS: dict[str, set[str]] = {
    "approve": {MissionStatus.DRAFT.value},
    "pause": {MissionStatus.ACTIVE.value, MissionStatus.VERIFYING.value},
    "resume": {MissionStatus.PAUSED.value},
    "block": {
        MissionStatus.DRAFT.value,
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
    "record_action": {
        MissionStatus.ACTIVE.value,
        MissionStatus.VERIFYING.value,
    },
    "record_observation": {
        MissionStatus.ACTIVE.value,
        MissionStatus.PAUSED.value,
        MissionStatus.BLOCKED.value,
        MissionStatus.VERIFYING.value,
    },
    "amend_authority": {
        MissionStatus.DRAFT.value,
        MissionStatus.ACTIVE.value,
        MissionStatus.PAUSED.value,
        MissionStatus.BLOCKED.value,
        MissionStatus.VERIFYING.value,
    },
}


class TransitionError(ValueError):
    """Named refusal for an illegal or unauthorized mission transition."""


@dataclass(frozen=True, slots=True)
class MissionEvent:
    kind: str
    actor_ref: str
    detail: Mapping[str, Any] | None = None
    artifact_refs: tuple[str, ...] | list[str] = ()
    verdict: str | None = None


def _clone(manifest: MissionManifest) -> dict[str, Any]:
    return manifest.to_dict()


def apply_event(manifest: MissionManifest, event: MissionEvent) -> MissionManifest:
    status = str(manifest.state.get("status"))
    kind = event.kind
    if kind not in LEGAL_TRANSITIONS:
        raise TransitionError(f"UNKNOWN_EVENT: {kind}")

    progress_kinds = {
        "record_action",
        "begin_verification",
        "accept",
        "approve",
        "resume",
        "unblock",
        "amend_authority",
        "pause",
        "block",
    }
    if manifest.authority.get("revoked") is True and kind in progress_kinds:
        raise TransitionError("AUTHORITY_REVOKED: no further mission progress is permitted")

    if status not in LEGAL_TRANSITIONS[kind]:
        raise TransitionError(f"ILLEGAL_TRANSITION: {kind} from {status}")

    payload = _clone(manifest)
    payload["revision"] = int(manifest.revision) + 1
    authority = payload["authority"]
    state = payload["state"]
    continuity = payload["continuity"]
    integrity = payload["integrity"]
    detail = dict(event.detail or {})
    artifacts = list(event.artifact_refs or [])
    # After the first revision, trusted progress must cite a prior checkpoint ref.
    if payload["revision"] > 1 and continuity.get("prior_checkpoint") is None:
        continuity["prior_checkpoint"] = (
            f"checkpoint://{manifest.mission_id}/{manifest.revision:04d}"
        )

    if kind == "approve":
        state["status"] = MissionStatus.ACTIVE.value
        state["next_action"] = "advance mission"
        state["current_frontier"] = ["advance mission"]
    elif kind == "pause":
        state["status"] = MissionStatus.PAUSED.value
    elif kind == "resume":
        state["status"] = MissionStatus.ACTIVE.value
    elif kind == "block":
        state["status"] = MissionStatus.BLOCKED.value
        blockers = list(state.get("blockers") or [])
        blockers.append(detail.get("reason") or "blocked")
        state["blockers"] = blockers
    elif kind == "unblock":
        if authority.get("revoked") is True:
            raise TransitionError("AUTHORITY_REVOKED: revoked missions cannot unblock")
        state["status"] = MissionStatus.ACTIVE.value
        state["blockers"] = []
    elif kind == "begin_verification":
        state["status"] = MissionStatus.VERIFYING.value
        state["next_action"] = "independent acceptance"
    elif kind == "accept":
        acceptor = integrity.get("completion_acceptor")
        if event.actor_ref != acceptor:
            raise TransitionError(
                "INDEPENDENT_ACCEPTANCE_REQUIRED: actor is not the completion_acceptor"
            )
        if event.actor_ref == STEWARD_REF:
            raise TransitionError(
                "INDEPENDENT_ACCEPTANCE_REQUIRED: mission steward cannot self-accept"
            )
        if event.verdict != "PASS":
            raise TransitionError("ACCEPT_REQUIRES_PASS: accept requires verdict PASS")
        if integrity.get("unresolved_verdicts"):
            raise TransitionError("UNRESOLVED_VERDICTS: cannot accept with unresolved verdicts")
        durable = set(continuity.get("durable_artifacts") or [])
        required = list(manifest.outcome.get("completion_proof") or [])
        missing = [item for item in required if item not in durable and item not in artifacts]
        if missing:
            raise TransitionError(
                f"COMPLETION_PROOF_MISSING: {', '.join(missing)}"
            )
        # Ensure proof refs are retained.
        for item in artifacts:
            if item not in durable:
                durable.add(item)
        continuity["durable_artifacts"] = sorted(durable)
        state["status"] = MissionStatus.COMPLETED.value
        state["next_action"] = None
        state["current_frontier"] = []
    elif kind == "reject":
        state["status"] = MissionStatus.ACTIVE.value
        unresolved = list(integrity.get("unresolved_verdicts") or [])
        unresolved.append(
            {
                "actor_ref": event.actor_ref,
                "verdict": event.verdict or "FAIL",
                "detail": detail,
            }
        )
        integrity["unresolved_verdicts"] = unresolved
        state["next_action"] = "address rejection"
    elif kind == "revoke":
        authority["revoked"] = True
        authority["revocation_reason"] = detail.get("reason") or "revoked"
        state["status"] = MissionStatus.BLOCKED.value
        blockers = list(state.get("blockers") or [])
        blockers.append("authority revoked")
        state["blockers"] = blockers
    elif kind == "cancel":
        state["status"] = MissionStatus.CANCELLED.value
        state["next_action"] = None
        state["current_frontier"] = []
    elif kind == "record_action":
        completed = list(state.get("completed_actions") or [])
        completed.append(detail.get("action") or "action")
        state["completed_actions"] = completed
        for item in artifacts:
            durable = list(continuity.get("durable_artifacts") or [])
            if item not in durable:
                durable.append(item)
            continuity["durable_artifacts"] = durable
    elif kind == "record_observation":
        for item in artifacts:
            durable = list(continuity.get("durable_artifacts") or [])
            if item not in durable:
                durable.append(item)
            continuity["durable_artifacts"] = durable
        decisions = list(continuity.get("decisions") or [])
        if detail:
            decisions.append(detail)
            continuity["decisions"] = decisions
    elif kind == "amend_authority":
        amendment = detail.get("amendment")
        if not isinstance(amendment, str) or not amendment.strip():
            raise TransitionError("AMENDMENT_REQUIRED: amend_authority needs amendment text")
        amendments = list(authority.get("amendments") or [])
        amendments.append(amendment)
        authority["amendments"] = amendments
        # Instruction remains byte-identical.
        authority["instruction"] = manifest.authority["instruction"]

    # Preserve operator instruction verbatim on every path.
    authority["instruction"] = manifest.authority["instruction"]

    errors = validate_manifest_dict(payload)
    if errors:
        raise TransitionError("INVALID_RESULT: " + "; ".join(errors))
    return MissionManifest.from_dict(payload)
