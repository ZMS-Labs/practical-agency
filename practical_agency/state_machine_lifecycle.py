"""Lifecycle and authority transition handlers for the mission state machine."""
from __future__ import annotations

from typing import Any, Mapping

from practical_agency.manifest_model import MissionManifest, MissionStatus
from practical_agency.state_machine_support import (
    MissionEvent,
    TransitionError,
    _acceptance_evidence,
    _append_unique,
    _missing_proof_refs,
    _operator_only,
    _reconciliation_subject,
    _require_independent_acceptor,
    _required_string,
)


def apply_lifecycle_event(
    data: dict[str, Any],
    manifest: MissionManifest,
    event: MissionEvent,
    payload: Mapping[str, Any],
) -> bool:
    """Apply a lifecycle/authority event, returning whether it was handled."""

    state = data["state"]
    authority = data["authority"]
    continuity = data["continuity"]
    integrity = data["integrity"]
    current = manifest.state.get("status")

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
        acceptor = integrity.get("completion_acceptor")
        if not isinstance(acceptor, str) or not acceptor.strip():
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

    else:
        return False

    return True
