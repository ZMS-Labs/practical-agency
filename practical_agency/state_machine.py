"""Closed, authority-preserving mission-state transitions."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any, Mapping

from practical_agency.deferred_interest import validate_deferred_interest
from practical_agency.manifest_model import MissionManifest, MissionStatus
from practical_agency.mission_os import (
    _defer_critical_path,
    _validate_labels,
    decode_mission_os_proposal,
    frontier_sha256,
    validate_basis_refs,
)


class TransitionError(RuntimeError):
    """Named refusal for an invalid mission transition."""


MISSION_STEWARD_REF = "mission-steward"


@dataclass(frozen=True, slots=True)
class MissionEvent:
    schema: str
    event_id: str
    mission_id: str
    expected_revision: int
    kind: str
    actor_ref: str
    data: Mapping[str, Any] = field(default_factory=dict)
    observed_at: str = ""

    @classmethod
    def for_manifest(
        cls,
        manifest: MissionManifest,
        kind: str,
        actor_ref: str,
        data: Mapping[str, Any] | None = None,
        *,
        event_id: str | None = None,
        observed_at: str | None = None,
    ) -> "MissionEvent":
        return cls(
            schema="mission-event@1",
            event_id=event_id or f"event-{uuid4().hex}",
            mission_id=manifest.mission_id,
            expected_revision=manifest.revision,
            kind=kind,
            actor_ref=actor_ref,
            data=deepcopy(dict(data or {})),
            observed_at=observed_at or datetime.now(timezone.utc).isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "event_id": self.event_id,
            "mission_id": self.mission_id,
            "expected_revision": self.expected_revision,
            "kind": self.kind,
            "actor_ref": self.actor_ref,
            "data": deepcopy(dict(self.data)),
            "observed_at": self.observed_at,
        }


def apply_event_data(
    manifest: MissionManifest,
    kind: str,
    actor_ref: str,
    data: Mapping[str, Any] | None = None,
    *,
    event_id: str | None = None,
    observed_at: str | None = None,
) -> MissionManifest:
    """Bind and synchronously apply one local event to the live revision."""
    return apply_event(
        manifest,
        MissionEvent.for_manifest(
            manifest,
            kind,
            actor_ref,
            data,
            event_id=event_id,
            observed_at=observed_at,
        ),
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
    "record_observation": {
        MissionStatus.ACTIVE.value,
        MissionStatus.BLOCKED.value,
    },
    "record_watch_crossing": {
        MissionStatus.DRAFT.value,
        MissionStatus.ACTIVE.value,
        MissionStatus.PAUSED.value,
        MissionStatus.BLOCKED.value,
        MissionStatus.VERIFYING.value,
        MissionStatus.COMPLETED.value,
    },
    "record_execution_receipt": {MissionStatus.ACTIVE.value},
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


def _validate_event_envelope(
    manifest: MissionManifest, event: MissionEvent
) -> None:
    if event.schema != "mission-event@1":
        raise TransitionError("EVENT_SCHEMA_MISMATCH")
    if not isinstance(event.event_id, str) or not event.event_id.strip():
        raise TransitionError("EVENT_ID_REQUIRED")
    if event.mission_id != manifest.mission_id:
        raise TransitionError("EVENT_MISSION_MISMATCH")
    if (
        isinstance(event.expected_revision, bool)
        or not isinstance(event.expected_revision, int)
        or event.expected_revision != manifest.revision
    ):
        raise TransitionError("EVENT_REVISION_MISMATCH")
    if not isinstance(event.actor_ref, str) or not event.actor_ref.strip():
        raise TransitionError("EVENT_ACTOR_REQUIRED")
    if not isinstance(event.observed_at, str) or not event.observed_at.strip():
        raise TransitionError("EVENT_OBSERVED_AT_REQUIRED")
    if not isinstance(event.data, Mapping):
        raise TransitionError("EVENT_DATA_MUST_BE_OBJECT")
    processed = manifest.continuity.get("processed_event_ids", [])
    if not isinstance(processed, list):
        raise TransitionError("PROCESSED_EVENT_IDS_INVALID")
    if event.event_id in processed:
        raise TransitionError("EVENT_REPLAY")


def apply_event(manifest: MissionManifest, event: MissionEvent) -> MissionManifest:
    _validate_event_envelope(manifest, event)
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
    continuity.setdefault("processed_event_ids", [])
    continuity.setdefault("execution_receipts", [])
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

    elif event.kind == "record_watch_crossing":
        _require_mission_steward(event)
        if set(payload) != {"handoff"}:
            raise TransitionError("WATCH_CROSSING_EVENT_INVALID")
        handoff = payload.get("handoff")
        required_handoff_fields = {
            "kind",
            "commission_id",
            "event_ref",
            "observed_at",
            "condition",
            "expected_output_contract",
            "return_point",
        }
        if not isinstance(handoff, Mapping) or set(handoff) != required_handoff_fields:
            raise TransitionError("WATCH_CROSSING_HANDOFF_INVALID")
        if handoff.get("kind") != "watch-crossing":
            raise TransitionError("WATCH_CROSSING_HANDOFF_INVALID")
        for key in (
            "commission_id",
            "event_ref",
            "observed_at",
            "condition",
            "expected_output_contract",
        ):
            if not isinstance(handoff.get(key), str) or not handoff.get(key).strip():
                raise TransitionError(f"WATCH_CROSSING_{key.upper()}_REQUIRED")
        if handoff.get("observed_at") != event.observed_at:
            raise TransitionError("WATCH_CROSSING_OBSERVED_AT_MISMATCH")
        return_point = handoff.get("return_point")
        if (
            not isinstance(return_point, Mapping)
            or set(return_point) != {"mission_id", "mission_revision", "status"}
            or return_point.get("mission_id") != manifest.mission_id
            or return_point.get("mission_revision") != manifest.revision
            or return_point.get("status") != current
        ):
            raise TransitionError("WATCH_CROSSING_RETURN_POINT_MISMATCH")
        if any(
            isinstance(item, Mapping)
            and item.get("kind") == "watch-crossing"
            and item.get("commission_id") == handoff.get("commission_id")
            and item.get("event_ref") == handoff.get("event_ref")
            for item in continuity.get("external_handoffs", [])
        ):
            raise TransitionError("WATCH_CROSSING_REPLAY")
        continuity["external_handoffs"].append(deepcopy(dict(handoff)))

    elif event.kind == "record_execution_receipt":
        _require_mission_steward(event)
        if set(payload) != {"receipt", "request"}:
            raise TransitionError("EXECUTION_RECEIPT_EVENT_INVALID")
        receipt = payload.get("receipt")
        request = payload.get("request")
        required_receipt_fields = {
            "schema",
            "request_id",
            "mission_id",
            "mission_revision",
            "adapter_ref",
            "status",
            "artifact_refs",
            "observed_effects",
            "external_receipt_ref",
            "coverage_limits",
        }
        if not isinstance(receipt, Mapping) or set(receipt) != required_receipt_fields:
            raise TransitionError("EXECUTION_RECEIPT_INVALID")
        if not isinstance(request, Mapping):
            raise TransitionError("EXECUTION_RECEIPT_REQUEST_REQUIRED")
        required_request_fields = {
            "schema",
            "request_id",
            "mission_id",
            "mission_revision",
            "capability_id",
            "requested_permissions",
            "requested_effects",
            "estimated_costs",
            "action",
        }
        if set(request) != required_request_fields or request.get("schema") != "execution-request@1":
            raise TransitionError("EXECUTION_RECEIPT_REQUEST_INVALID")
        if receipt.get("schema") != "execution-receipt@1":
            raise TransitionError("EXECUTION_RECEIPT_SCHEMA")
        if (
            receipt.get("request_id") != request.get("request_id")
            or receipt.get("mission_id") != request.get("mission_id")
            or receipt.get("mission_revision") != request.get("mission_revision")
        ):
            raise TransitionError("EXECUTION_RECEIPT_REQUEST_MISMATCH")
        if receipt.get("mission_id") != manifest.mission_id:
            raise TransitionError("EXECUTION_RECEIPT_MISSION_MISMATCH")
        if receipt.get("mission_revision") != manifest.revision:
            raise TransitionError("EXECUTION_RECEIPT_REVISION_MISMATCH")
        for key in ("request_id", "adapter_ref"):
            if not isinstance(receipt.get(key), str) or not receipt.get(key).strip():
                raise TransitionError(f"EXECUTION_RECEIPT_{key.upper()}_REQUIRED")
        if receipt.get("status") not in {"completed", "declined", "blocked", "failed"}:
            raise TransitionError("EXECUTION_RECEIPT_STATUS")
        artifact_refs = receipt.get("artifact_refs")
        coverage_limits = receipt.get("coverage_limits")
        if (
            not isinstance(artifact_refs, list)
            or any(not isinstance(item, str) or not item.strip() for item in artifact_refs)
            or not isinstance(coverage_limits, list)
            or any(not isinstance(item, str) or not item.strip() for item in coverage_limits)
            or not isinstance(receipt.get("observed_effects"), list)
        ):
            raise TransitionError("EXECUTION_RECEIPT_INVALID")
        external_ref = receipt.get("external_receipt_ref")
        if receipt.get("status") == "completed" and (
            not isinstance(external_ref, str) or not external_ref.strip()
        ):
            raise TransitionError("EXECUTION_RECEIPT_EXTERNAL_REF_REQUIRED")
        existing_ids = {
            item.get("request_id")
            for item in continuity.get("execution_receipts", [])
            if isinstance(item, Mapping)
        }
        if receipt.get("request_id") in existing_ids:
            raise TransitionError("EXECUTION_RECEIPT_REPLAY")
        stored_receipt = deepcopy(dict(receipt))
        stored_receipt["request"] = deepcopy(dict(request))
        stored_receipt["recorded_at_revision"] = manifest.revision + 1
        continuity["execution_receipts"].append(stored_receipt)
        for artifact_ref in artifact_refs:
            _append_unique(continuity["durable_artifacts"], artifact_ref)

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
        if set(payload) != {"proposal"}:
            raise TransitionError("MISSION_OS_BOUND_PROPOSAL_REQUIRED")
        try:
            proposal_kind, content, proposal_meta = decode_mission_os_proposal(
                manifest, payload.get("proposal")
            )
        except ValueError as exc:
            raise TransitionError(str(exc)) from exc
        new_revision = manifest.revision + 1
        continuity.setdefault("deferred_interests", [])
        decision_extra: dict[str, Any] = {}

        if proposal_kind in ("frontier_patch", "replan_slice"):
            _require_mission_steward(event)
            labels = _string_list(
                content, "labels", "FRONTIER_LABELS_REQUIRED", non_empty=True
            )
            try:
                _validate_labels(labels)
                basis_refs = validate_basis_refs(
                    manifest, content.get("basis_refs")
                )
            except ValueError as exc:
                raise TransitionError(str(exc)) from exc
            replace_range = content.get("replace_range")
            if (
                not isinstance(replace_range, list)
                or len(replace_range) != 2
                or any(isinstance(item, bool) or not isinstance(item, int) for item in replace_range)
            ):
                raise TransitionError("FRONTIER_REPLACE_RANGE_INVALID")
            start_index, end_index = replace_range
            current_frontier = state.get("current_frontier")
            if (
                not isinstance(current_frontier, list)
                or start_index < 0
                or end_index < start_index
                or end_index > len(current_frontier)
            ):
                raise TransitionError("FRONTIER_REPLACE_RANGE_INVALID")
            contradiction_refs: list[str] = []
            if proposal_kind == "replan_slice":
                contradiction_refs = _string_list(
                    content,
                    "contradiction_refs",
                    "REPLAN_CONTRADICTION_REQUIRED",
                    non_empty=True,
                )
                try:
                    validate_basis_refs(manifest, contradiction_refs)
                except ValueError as exc:
                    raise TransitionError(str(exc)) from exc
            if current == MissionStatus.COMPLETED.value:
                crossing_refs = {
                    item.get("event_ref")
                    for item in continuity.get("external_handoffs", [])
                    if isinstance(item, Mapping)
                    and item.get("kind") == "watch-crossing"
                }
                if (
                    proposal_kind != "replan_slice"
                    or not contradiction_refs
                    or not set(contradiction_refs).issubset(crossing_refs)
                ):
                    raise TransitionError("COMPLETED_REPLAN_REQUIRES_WATCH_CROSSING")
                state["status"] = MissionStatus.ACTIVE.value
            next_frontier = list(current_frontier)
            next_frontier[start_index:end_index] = labels
            state["current_frontier"] = next_frontier
            state["next_action"] = next_frontier[0] if next_frontier else None
            decision_extra.update(
                {
                    "basis_refs": basis_refs,
                    "replace_range": [start_index, end_index],
                    "frontier_sha256": frontier_sha256(next_frontier),
                }
            )
            if contradiction_refs:
                decision_extra["contradiction_refs"] = contradiction_refs

        elif proposal_kind == "defer":
            _require_mission_steward(event)
            interest = content.get("interest")
            if not isinstance(interest, Mapping):
                raise TransitionError("DEFERRED_INTEREST_REQUIRED")
            copied = deepcopy(dict(interest))
            copied["created_at_revision"] = new_revision
            try:
                _defer_critical_path(
                    manifest, copied, completion_proof_ids=None
                )
            except ValueError as exc:
                raise TransitionError(str(exc)) from exc
            errors = validate_deferred_interest(
                copied, mission_id=manifest.mission_id
            )
            if errors:
                raise TransitionError(errors[0])
            continuity["deferred_interests"].append(copied)
            decision_extra["critical_path_clearance"] = deepcopy(
                copied.get("critical_path_clearance")
            )

        elif proposal_kind == "return_rebind":
            _require_mission_steward(event)
            invalidate = content.get("invalidate")
            if not isinstance(invalidate, list) or not invalidate:
                raise TransitionError("RETURN_REBIND_INVALIDATE_REQUIRED")
            decision_extra["invalidate"] = deepcopy(invalidate)

        elif proposal_kind == "absorb":
            idx = content.get("interest_index")
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
                amendment = content.get("amendment")
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
                "proposal_id": proposal_meta["proposal_id"],
                "base_revision": proposal_meta["base_revision"],
                "payload_sha256": proposal_meta["payload_sha256"],
                "actor_ref": event.actor_ref,
                "at_revision": new_revision,
                **decision_extra,
            }
        )

    checkpoint_ref = payload.get("checkpoint_ref")
    if isinstance(checkpoint_ref, str) and checkpoint_ref.strip():
        continuity["prior_checkpoint"] = checkpoint_ref

    continuity["processed_event_ids"].append(event.event_id)
    data["revision"] = manifest.revision + 1
    if authority.get("instruction") != original_instruction:
        raise TransitionError("OPERATOR_INSTRUCTION_MUTATED")
    return MissionManifest.from_dict(data)
