"""Closed mission lifecycle with independent completion."""
from __future__ import annotations

from typing import Any, Mapping

from .manifest_model import MissionManifest, MissionStatus


class TransitionError(ValueError):
    """Raised when a requested mission transition is not authorized by the lifecycle."""


_ALLOWED: dict[str, set[str]] = {
    "draft": {"active"},
    "active": {"paused", "blocked", "verifying"},
    "paused": {"active", "blocked"},
    "blocked": {"active"},
    "verifying": {"completed", "active", "blocked"},
    "completed": set(),
    "cancelled": set(),
}


def transition(
    manifest: MissionManifest,
    target: str | MissionStatus,
    *,
    actor_ref: str,
    evidence_ref: str | None,
    reason: str | None = None,
    independent: bool = False,
) -> MissionManifest:
    target_value = target.value if isinstance(target, MissionStatus) else target
    current = manifest.state["status"]
    if current in {"completed", "cancelled"}:
        raise TransitionError(f"TERMINAL_STATE: {current} cannot transition")
    if target_value == MissionStatus.CANCELLED.value:
        raise TransitionError(
            "REVOCATION_REQUIRED: cancelled is reachable only through operator revocation"
        )
    if target_value not in _ALLOWED.get(current, set()):
        raise TransitionError(f"ILLEGAL_TRANSITION: {current} -> {target_value}")
    if target_value in {"blocked", "paused"} and not reason:
        raise TransitionError(
            "BLOCK_REASON_REQUIRED: name why the mission stops"
            if target_value == "blocked"
            else "PAUSED_REASON_REQUIRED: name why the mission stops"
        )
    if target_value in {"active", "verifying", "completed"} and not evidence_ref:
        raise TransitionError("EVIDENCE_REQUIRED: transition needs a durable evidence reference")

    material_actors = set(manifest.integrity["material_work_actors"])
    if target_value == "completed":
        if not independent or actor_ref in material_actors:
            raise TransitionError(
                "INDEPENDENT_ACCEPTOR_REQUIRED: material work actor cannot accept completion"
            )
        if manifest.integrity["unresolved_verdicts"]:
            raise TransitionError("UNRESOLVED_VERDICTS: completion is not available")

    payload = manifest.to_dict()
    payload["revision"] = manifest.revision + 1
    state = payload["state"]
    state["status"] = target_value

    if target_value == "active":
        state["blockers"] = []
        state["current_frontier"] = ["advance mission"]
        state["next_action"] = "advance mission"
    elif target_value == "paused":
        state["blockers"] = [{"kind": "pause", "reason": reason, "evidence_ref": evidence_ref}]
        state["next_action"] = "obtain resume authority"
    elif target_value == "blocked":
        state["blockers"] = [{"kind": "block", "reason": reason, "evidence_ref": evidence_ref}]
        state["next_action"] = "resolve blocker"
    elif target_value == "verifying":
        state["blockers"] = []
        state["next_action"] = "obtain independent acceptance"
    elif target_value in {"completed", "cancelled"}:
        state["blockers"] = []
        state["current_frontier"] = []
        state["next_action"] = None

    if target_value == "verifying":
        actors = payload["integrity"]["material_work_actors"]
        if actor_ref not in actors:
            actors.append(actor_ref)

    if target_value == "completed":
        payload["integrity"]["completion_acceptor"] = actor_ref
        payload["integrity"]["acceptance_receipt_ref"] = evidence_ref
    elif current == "completed" or target_value != "verifying":
        if target_value not in {"completed"}:
            payload["integrity"]["completion_acceptor"] = None
            payload["integrity"]["acceptance_receipt_ref"] = None

    payload["continuity"]["decisions"].append(
        {
            "kind": "transition",
            "revision": payload["revision"],
            "from": current,
            "to": target_value,
            "actor_ref": actor_ref,
            "evidence_ref": evidence_ref,
            "reason": reason,
            "independent": independent,
        }
    )
    return MissionManifest.from_dict(payload)


def reopen_for_contradiction(
    manifest: MissionManifest,
    *,
    contradiction: Mapping[str, Any],
    observed_by: str,
    evidence_ref: str,
) -> MissionManifest:
    if not evidence_ref:
        raise TransitionError("EVIDENCE_REQUIRED: contradiction needs a durable observation")
    payload = manifest.to_dict()
    payload["revision"] = manifest.revision + 1
    payload["truth"]["contradictions"].append(
        {
            **dict(contradiction),
            "observed_by": observed_by,
            "evidence_ref": evidence_ref,
            "revision": payload["revision"],
        }
    )
    payload["state"]["status"] = "active"
    payload["state"]["blockers"] = []
    payload["state"]["current_frontier"] = ["reconcile live-state contradiction"]
    payload["state"]["next_action"] = "reconcile live-state contradiction"
    payload["integrity"]["completion_acceptor"] = None
    payload["integrity"]["acceptance_receipt_ref"] = None
    payload["continuity"]["decisions"].append(
        {
            "kind": "reopen-contradiction",
            "revision": payload["revision"],
            "actor_ref": observed_by,
            "evidence_ref": evidence_ref,
        }
    )
    return MissionManifest.from_dict(payload)
