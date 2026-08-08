"""Closed, authority-preserving mission-state transitions."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping

from practical_agency.deferred_interest import validate_deferred_interest
from practical_agency.manifest_model import MissionManifest, MissionStatus
from practical_agency.mission_os import _defer_critical_path, _validate_labels


class TransitionError(RuntimeError):
    """Named refusal for an invalid mission transition."""


MISSION_STEWARD_REF = "mission-steward"


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
    "apply_mission_os": {MissionStatus.ACTIVE.value},
}


def _required_string(data: Mapping[str, Any], key: str, code: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TransitionError(code)
    return value


def _string_list(
    data: Mapping[str, Any], key: str, code: str, *, non_empty: bool = False
) -> list[str]:
    value = data.get(key)
    if (
        not isinstance(value, list)
        or (non_empty and not value)
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise TransitionError(code)
    return list(value)


def _operator_only(manifest: MissionManifest, event: MissionEvent) -> None:
    if event.actor_ref != manifest.authority.get("operator_ref"):
        raise TransitionError("OPERATOR_AUTHORITY_REQUIRED")


def _require_mission_steward(event: MissionEvent) -> None:
    if event.actor_ref != MISSION_STEWARD_REF:
        raise TransitionError("MISSION_STEWARD_REQUIRED")


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


def _require_independent_acceptor(
    data: Mapping[str, Any], event: MissionEvent
) -> None:
    acceptor = data.get("integrity", {}).get("completion_acceptor")
    if event.actor_ref != acceptor or event.actor_ref in _material_workers(data):
        raise TransitionError("INDEPENDENT_ACCEPTANCE_REQUIRED")


def _required_proof_refs(data: Mapping[str, Any]) -> list[str]:
    return list(data["outcome"]["completion_proof"]) + list(
        data["integrity"]["required_gates"]
    )


def _missing_proof_refs(data: Mapping[str, Any]) -> list[str]:
    present = set(data["continuity"]["durable_artifacts"])
    return [ref for ref in _required_proof_refs(data) if ref not in present]


def _acceptance_evidence(payload: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    evidence_refs = _string_list(
        payload, "evidence_refs", "ACCEPTANCE_EVIDENCE_REQUIRED", non_empty=True
    )
    coverage_limits = _string_list(
        payload, "coverage_limits", "ACCEPTANCE_COVERAGE_LIMITS_REQUIRED"
    )
    return evidence_refs, coverage_limits


def _reconciliation_subject(marker: object) -> str | None:
    if not isinstance(marker, str) or not marker.startswith("RECONCILIATION:"):
        return None
    parts = marker.split(":", 2)
    return parts[2] if len(parts) == 3 and parts[2] else None


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
        reason = payload.get("reason")
        reconciliation_blockers = [
            item
            for item in state["blockers"]
            if _reconciliation_subject(item) is not None
        ]
        if reconciliation_blockers and (
            not isinstance(reason, str) or reason in reconciliation_blockers
        ):
            raise TransitionError("RECONCILIATION_OBSERVATION_REQUIRED")
        if isinstance(reason, str) and reason:
            state["blockers"] = [item for item in state["blockers"] if item != reason]
        else:
            state["blockers"] = []
        if state["blockers"]:
            state["status"] = MissionStatus.BLOCKED.value
            state["next_action"] = f"resolve blocker: {state['blockers'][0]}"
        else:
            state["status"] = MissionStatus.ACTIVE.value
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
        if integrity["unresolved_verdicts"]:
            raise TransitionError("UNRESOLVED_VERDICTS")
        missing = _missing_proof_refs(data)
        if missing:
            raise TransitionError("PROOF_BUNDLE_NOT_READY:" + ",".join(missing))
        state["status"] = MissionStatus.VERIFYING.value
        state["next_action"] = "independent acceptance"

    elif event.kind == "accept":
        _require_independent_acceptor(data, event)
        if payload.get("verdict") != "PASS":
            raise TransitionError("PASS_VERDICT_REQUIRED")
        evidence_refs, coverage_limits = _acceptance_evidence(payload)
        if integrity["unresolved_verdicts"]:
            raise TransitionError("UNRESOLVED_VERDICTS")
        missing = _missing_proof_refs(data)
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
                "evidence_refs": evidence_refs,
                "coverage_limits": coverage_limits,
            }
        )

    elif event.kind == "reject":
        _require_independent_acceptor(data, event)
        verdict = payload.get("verdict")
        if verdict not in {"FAIL", "INCONCLUSIVE"}:
            raise TransitionError("REJECTION_VERDICT_REQUIRED")
        reason = _required_string(payload, "reason", "REJECTION_REASON_REQUIRED")
        evidence_refs, coverage_limits = _acceptance_evidence(payload)
        unresolved = f"{verdict}:{reason}"
        _append_unique(integrity["unresolved_verdicts"], unresolved)
        _append_unique(state["blockers"], unresolved)
        state["status"] = (
            MissionStatus.BLOCKED.value
            if verdict == "INCONCLUSIVE"
            else MissionStatus.ACTIVE.value
        )
        state["next_action"] = f"address verdict: {unresolved}"
        continuity["decisions"].append(
            {
                "kind": "independent-rejection",
                "actor_ref": event.actor_ref,
                "verdict": verdict,
                "reason": reason,
                "evidence_refs": evidence_refs,
                "coverage_limits": coverage_limits,
            }
        )

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

    elif event.kind == "apply_mission_os":
        proposal_kind = payload.get("proposal_kind")
        if not isinstance(proposal_kind, str) or not proposal_kind.strip():
            raise TransitionError("MISSION_OS_PROPOSAL_KIND_REQUIRED")
        new_revision = manifest.revision + 1
        continuity.setdefault("deferred_interests", [])
        decision_extra: dict[str, Any] = {}

        if proposal_kind in ("frontier_patch", "replan_slice"):
            _require_mission_steward(event)
            labels = _string_list(
                payload, "labels", "FRONTIER_LABELS_REQUIRED", non_empty=True
            )
            try:
                _validate_labels(labels)
            except ValueError as exc:
                raise TransitionError(str(exc)) from exc
            state["current_frontier"] = labels
            state["next_action"] = labels[0] if labels else None
            if proposal_kind == "replan_slice":
                contradiction_refs = _string_list(
                    payload,
                    "contradiction_refs",
                    "REPLAN_CONTRADICTION_REQUIRED",
                    non_empty=True,
                )
                for ref in contradiction_refs:
                    _append_unique(data["truth"]["contradictions"], ref)
                decision_extra["contradiction_refs"] = contradiction_refs

        elif proposal_kind == "defer":
            _require_mission_steward(event)
            interest = payload.get("interest")
            if not isinstance(interest, Mapping):
                raise TransitionError("DEFERRED_INTEREST_REQUIRED")
            copied = deepcopy(dict(interest))
            errors = validate_deferred_interest(
                copied, mission_id=manifest.mission_id
            )
            if errors:
                raise TransitionError(errors[0])
            try:
                _defer_critical_path(
                    manifest, copied, completion_proof_ids=None
                )
            except ValueError as exc:
                raise TransitionError(str(exc)) from exc
            continuity["deferred_interests"].append(copied)

        elif proposal_kind == "return_rebind":
            _require_mission_steward(event)
            invalidate = payload.get("invalidate")
            if not isinstance(invalidate, list) or not invalidate:
                raise TransitionError("RETURN_REBIND_INVALIDATE_REQUIRED")
            invalidated = deepcopy(invalidate)
            decision_extra["invalidate"] = invalidated

        elif proposal_kind == "absorb":
            idx = payload.get("interest_index")
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
            criticality = interest.get("criticality")
            if criticality == "high":
                _operator_only(manifest, event)
                amendment = payload.get("amendment")
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

    checkpoint_ref = payload.get("checkpoint_ref")
    if isinstance(checkpoint_ref, str) and checkpoint_ref.strip():
        continuity["prior_checkpoint"] = checkpoint_ref

    data["revision"] = manifest.revision + 1
    if authority.get("instruction") != original_instruction:
        raise TransitionError("OPERATOR_INSTRUCTION_MUTATED")
    return MissionManifest.from_dict(data)
