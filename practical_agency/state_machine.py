"""Closed, authority-preserving mission-state transitions."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping

from practical_agency.manifest_model import MissionManifest, MissionStatus


class TransitionError(RuntimeError):
    """Named refusal for an invalid mission transition."""


@dataclass(frozen=True, slots=True)
class MissionEvent:
    kind: str
    actor_ref: str
    data: Mapping[str, Any] = field(default_factory=dict)


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
    "record_observation": {MissionStatus.ACTIVE.value},
    "amend_authority": {
        MissionStatus.DRAFT.value,
        MissionStatus.ACTIVE.value,
        MissionStatus.PAUSED.value,
        MissionStatus.BLOCKED.value,
    },
}


def _required_string(data: Mapping[str, Any], key: str, code: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TransitionError(code)
    return value


def _operator_only(manifest: MissionManifest, event: MissionEvent) -> None:
    if event.actor_ref != manifest.authority.get("operator_ref"):
        raise TransitionError("OPERATOR_AUTHORITY_REQUIRED")


def _append_unique(target: list[Any], value: Any) -> None:
    if value not in target:
        target.append(deepcopy(value))


def _material_workers(data: Mapping[str, Any]) -> set[str]:
    workers: set[str] = set()
    decisions = data.get("continuity", {}).get("decisions", [])
    for item in decisions:
        if isinstance(item, Mapping) and item.get("kind") == "material-action":
            actor = item.get("actor_ref")
            if isinstance(actor, str):
                workers.add(actor)
    return workers


def apply_event(manifest: MissionManifest, event: MissionEvent) -> MissionManifest:
    if event.kind not in _ALLOWED_FROM:
        raise TransitionError(f"UNKNOWN_EVENT:{event.kind}")

    current = manifest.state.get("status")
    if manifest.authority.get("revoked") is True and event.kind not in {"cancel"}:
        raise TransitionError("AUTHORITY_REVOKED")
    if current not in _ALLOWED_FROM[event.kind]:
        raise TransitionError(f"INVALID_TRANSITION:{current}->{event.kind}")

    original_instruction = manifest.authority.get("instruction")
    data = manifest.to_dict()
    payload = deepcopy(dict(event.data))
    state = data["state"]
    authority = data["authority"]
    continuity = data["continuity"]
    integrity = data["integrity"]

    if event.kind == "approve":
        _operator_only(manifest, event)
        checkpoint_ref = _required_string(
            payload, "checkpoint_ref", "CHECKPOINT_REQUIRED_FOR_APPROVAL"
        )
        continuity["prior_checkpoint"] = checkpoint_ref
        state["status"] = MissionStatus.ACTIVE.value
        if state["next_action"] == "obtain approval":
            state["next_action"] = (
                state["current_frontier"][0] if state["current_frontier"] else None
            )

    elif event.kind == "pause":
        state["status"] = MissionStatus.PAUSED.value
        reason = payload.get("reason")
        if isinstance(reason, str) and reason.strip():
            _append_unique(state["blockers"], f"PAUSED:{reason}")

    elif event.kind == "resume":
        state["status"] = MissionStatus.ACTIVE.value
        state["blockers"] = [
            item for item in state["blockers"] if not str(item).startswith("PAUSED:")
        ]

    elif event.kind == "block":
        reason = _required_string(payload, "reason", "BLOCK_REASON_REQUIRED")
        state["status"] = MissionStatus.BLOCKED.value
        _append_unique(state["blockers"], reason)
        state["next_action"] = f"resolve blocker: {reason}"

    elif event.kind == "unblock":
        state["status"] = MissionStatus.ACTIVE.value
        reason = payload.get("reason")
        if isinstance(reason, str) and reason:
            state["blockers"] = [item for item in state["blockers"] if item != reason]
        else:
            state["blockers"] = []
        state["next_action"] = (
            state["current_frontier"][0] if state["current_frontier"] else None
        )

    elif event.kind == "begin_verification":
        if not isinstance(integrity.get("completion_acceptor"), str) or not integrity[
            "completion_acceptor"
        ].strip():
            raise TransitionError("COMPLETION_ACCEPTOR_REQUIRED")
        if state["blockers"]:
            raise TransitionError("UNRESOLVED_BLOCKERS")
        state["status"] = MissionStatus.VERIFYING.value
        state["next_action"] = "independent acceptance"

    elif event.kind == "accept":
        acceptor = integrity.get("completion_acceptor")
        if event.actor_ref != acceptor or event.actor_ref in _material_workers(data):
            raise TransitionError("INDEPENDENT_ACCEPTANCE_REQUIRED")
        if payload.get("verdict") != "PASS":
            raise TransitionError("PASS_VERDICT_REQUIRED")
        if integrity["unresolved_verdicts"]:
            raise TransitionError("UNRESOLVED_VERDICTS")
        present = set(continuity["durable_artifacts"])
        missing = [
            ref for ref in data["outcome"]["completion_proof"] if ref not in present
        ]
        if missing:
            raise TransitionError("COMPLETION_PROOF_MISSING:" + ",".join(missing))
        state["status"] = MissionStatus.COMPLETED.value
        state["current_frontier"] = []
        state["next_action"] = None
        continuity["decisions"].append(
            {
                "kind": "independent-acceptance",
                "actor_ref": event.actor_ref,
                "verdict": "PASS",
            }
        )

    elif event.kind == "reject":
        if event.actor_ref != integrity.get("completion_acceptor"):
            raise TransitionError("INDEPENDENT_ACCEPTANCE_REQUIRED")
        verdict = payload.get("verdict")
        if verdict not in {"FAIL", "INCONCLUSIVE"}:
            raise TransitionError("REJECTION_VERDICT_REQUIRED")
        reason = str(payload.get("reason") or "unspecified")
        unresolved = f"{verdict}:{reason}"
        _append_unique(integrity["unresolved_verdicts"], unresolved)
        _append_unique(state["blockers"], unresolved)
        state["status"] = (
            MissionStatus.BLOCKED.value
            if verdict == "INCONCLUSIVE"
            else MissionStatus.ACTIVE.value
        )
        state["next_action"] = f"address verdict: {unresolved}"

    elif event.kind == "revoke":
        _operator_only(manifest, event)
        reason = _required_string(payload, "reason", "REVOCATION_REASON_REQUIRED")
        authority["revoked"] = True
        authority["revocation_reason"] = reason
        state["status"] = MissionStatus.CANCELLED.value
        state["next_action"] = None
        _append_unique(state["blockers"], f"AUTHORITY_REVOKED:{reason}")

    elif event.kind == "cancel":
        _operator_only(manifest, event)
        state["status"] = MissionStatus.CANCELLED.value
        state["next_action"] = None

    elif event.kind == "record_action":
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

    elif event.kind == "record_observation":
        artifact_ref = _required_string(
            payload, "artifact_ref", "OBSERVATION_ARTIFACT_REQUIRED"
        )
        _append_unique(continuity["durable_artifacts"], artifact_ref)
        fact = payload.get("fact")
        if isinstance(fact, Mapping):
            subject_ref = fact.get("subject_ref")
            if isinstance(subject_ref, str) and subject_ref:
                data["truth"]["verified_facts"] = [
                    item
                    for item in data["truth"]["verified_facts"]
                    if not (
                        isinstance(item, Mapping)
                        and item.get("subject_ref") == subject_ref
                    )
                ]
                data["truth"]["verified_facts"].append(deepcopy(dict(fact)))

    elif event.kind == "amend_authority":
        _operator_only(manifest, event)
        amendment = _required_string(payload, "amendment", "AMENDMENT_REQUIRED")
        authority["amendments"].append(amendment)
        for field, key in (
            ("permissions", "permissions_add"),
            ("protected_state", "protected_state_add"),
            ("acceptable_costs", "acceptable_costs_add"),
            ("escalation_required_for", "escalation_required_for_add"),
        ):
            additions = payload.get(key, [])
            if not isinstance(additions, list):
                raise TransitionError(f"INVALID_AMENDMENT_FIELD:{key}")
            for item in additions:
                if not isinstance(item, str) or not item.strip():
                    raise TransitionError(f"INVALID_AMENDMENT_ITEM:{key}")
                _append_unique(authority[field], item)

    checkpoint_ref = payload.get("checkpoint_ref")
    if isinstance(checkpoint_ref, str) and checkpoint_ref.strip():
        continuity["prior_checkpoint"] = checkpoint_ref

    data["revision"] = manifest.revision + 1
    if authority.get("instruction") != original_instruction:
        raise TransitionError("OPERATOR_INSTRUCTION_MUTATED")
    return MissionManifest.from_dict(data)
