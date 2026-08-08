"""Pure Mission OS proposal helpers (never mutate the manifest)."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from practical_agency.deferred_interest import validate_deferred_interest
from practical_agency.manifest_model import MissionManifest

_SKILL_SHAPED_LABEL = re.compile(r"(?i)\b(skill|invoke|run)\s+[a-z0-9_-]+\b")
_PROPOSAL_KEYS = {
    "schema",
    "proposal_id",
    "mission_id",
    "base_revision",
    "kind",
    "content",
    "payload_sha256",
}


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def frontier_sha256(frontier: object) -> str:
    if not isinstance(frontier, list):
        raise ValueError("FRONTIER_MUST_BE_ARRAY")
    return _canonical_sha256({"frontier": frontier})


@dataclass(frozen=True, slots=True)
class MissionOsProposal:
    proposal_id: str
    mission_id: str
    base_revision: int
    kind: str
    content: dict[str, Any]
    payload_sha256: str

    @property
    def payload(self) -> dict[str, Any]:
        """Compatibility view of the proposal-specific content."""
        return deepcopy(self.content)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "mission-os-proposal@1",
            "proposal_id": self.proposal_id,
            "mission_id": self.mission_id,
            "base_revision": self.base_revision,
            "kind": self.kind,
            "content": deepcopy(self.content),
            "payload_sha256": self.payload_sha256,
        }

    def to_event_data(self) -> dict[str, Any]:
        return {"proposal": self.to_dict()}


def _build_proposal(
    manifest: MissionManifest, kind: str, content: Mapping[str, Any]
) -> MissionOsProposal:
    proposal_id = f"proposal-{uuid4().hex}"
    copied = deepcopy(dict(content))
    signed = {
        "proposal_id": proposal_id,
        "mission_id": manifest.mission_id,
        "base_revision": manifest.revision,
        "kind": kind,
        "content": copied,
    }
    return MissionOsProposal(
        proposal_id=proposal_id,
        mission_id=manifest.mission_id,
        base_revision=manifest.revision,
        kind=kind,
        content=copied,
        payload_sha256=_canonical_sha256(signed),
    )


def bind_mission_os_proposal(
    manifest: MissionManifest, kind: str, content: Mapping[str, Any]
) -> MissionOsProposal:
    """Bind already-validated proposal content to one live mission revision."""
    if not isinstance(kind, str) or not kind.strip() or not isinstance(content, Mapping):
        raise ValueError("MISSION_OS_PROPOSAL_INVALID")
    return _build_proposal(manifest, kind, content)


def decode_mission_os_proposal(
    manifest: MissionManifest, raw: object
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Validate a bound proposal and return kind, content, and binding metadata."""
    if not isinstance(raw, Mapping) or set(raw) != _PROPOSAL_KEYS:
        raise ValueError("MISSION_OS_PROPOSAL_INVALID")
    if raw.get("schema") != "mission-os-proposal@1":
        raise ValueError("MISSION_OS_PROPOSAL_SCHEMA")
    proposal_id = raw.get("proposal_id")
    if not isinstance(proposal_id, str) or not proposal_id.strip():
        raise ValueError("MISSION_OS_PROPOSAL_ID_REQUIRED")
    if raw.get("mission_id") != manifest.mission_id:
        raise ValueError("MISSION_OS_PROPOSAL_MISSION_MISMATCH")
    base_revision = raw.get("base_revision")
    if (
        isinstance(base_revision, bool)
        or not isinstance(base_revision, int)
        or base_revision != manifest.revision
    ):
        raise ValueError("MISSION_OS_PROPOSAL_REVISION_MISMATCH")
    kind = raw.get("kind")
    if not isinstance(kind, str) or not kind.strip():
        raise ValueError("MISSION_OS_PROPOSAL_KIND_REQUIRED")
    content = raw.get("content")
    if not isinstance(content, Mapping):
        raise ValueError("MISSION_OS_PROPOSAL_CONTENT_REQUIRED")
    signed = {
        "proposal_id": proposal_id,
        "mission_id": manifest.mission_id,
        "base_revision": base_revision,
        "kind": kind,
        "content": dict(content),
    }
    if raw.get("payload_sha256") != _canonical_sha256(signed):
        raise ValueError("MISSION_OS_PROPOSAL_HASH_MISMATCH")
    decoded_content = dict(content)
    if kind == "replan_slice":
        validate_contradiction_refs(
            manifest, decoded_content.get("contradiction_refs")
        )
    metadata = {
        "proposal_id": proposal_id,
        "base_revision": base_revision,
        "payload_sha256": raw["payload_sha256"],
    }
    return kind, deepcopy(decoded_content), metadata


def _return_point_dict(manifest: MissionManifest, frontier_index: int) -> dict[str, Any]:
    frontier = manifest.state.get("current_frontier", [])
    if (
        isinstance(frontier_index, bool)
        or not isinstance(frontier_index, int)
        or not isinstance(frontier, list)
        or frontier_index < 0
        or frontier_index >= len(frontier)
    ):
        raise ValueError("INVALID_FRONTIER_INDEX")
    label = frontier[frontier_index]
    if not isinstance(label, str) or not label.strip():
        raise ValueError("INVALID_FRONTIER_LABEL")
    return {
        "mission_id": manifest.mission_id,
        "revision": manifest.revision,
        "frontier_index": frontier_index,
        "label": label,
    }


def _validate_labels(
    labels: Sequence[str], *, forbidden_substrings: Sequence[str] = ()
) -> None:
    if not labels:
        raise ValueError("FRONTIER_LABELS_REQUIRED")
    forbidden_folded = {part.casefold() for part in forbidden_substrings if part}
    for label in labels:
        if not isinstance(label, str) or not label.strip() or "\n" in label:
            raise ValueError("FRONTIER_LABEL_FORBIDDEN")
        stripped = label.strip()
        lowered = stripped.casefold()
        if lowered.startswith("skill:") or lowered.startswith("capability:"):
            raise ValueError("FRONTIER_LABEL_FORBIDDEN")
        if "://skill" in lowered:
            raise ValueError("FRONTIER_LABEL_FORBIDDEN")
        if _SKILL_SHAPED_LABEL.search(stripped):
            raise ValueError("FRONTIER_LABEL_FORBIDDEN")
        for token in forbidden_folded:
            if lowered == token:
                raise ValueError("FRONTIER_LABEL_FORBIDDEN")
            parts = re.split(r"[^a-z0-9_-]+", lowered)
            if token in parts:
                raise ValueError("FRONTIER_LABEL_FORBIDDEN")


def available_basis_refs(manifest: MissionManifest) -> set[str]:
    refs = {"authority:instruction", "outcome:desired_state"}
    refs.update(
        f"authority:amendment:{index}"
        for index, _ in enumerate(manifest.authority.get("amendments") or [])
    )
    for ref in manifest.truth.get("subject_refs") or []:
        if isinstance(ref, str) and ref.strip():
            refs.add(ref)
    for field in ("verified_facts", "contradictions", "unknowns"):
        for item in manifest.truth.get(field) or []:
            if isinstance(item, str) and item.strip():
                refs.add(item)
            elif isinstance(item, Mapping):
                for key in ("ref", "subject_ref", "event_ref"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        refs.add(value)
    for ref in manifest.continuity.get("durable_artifacts") or []:
        if isinstance(ref, str) and ref.strip():
            refs.add(ref)
    for handoff in manifest.continuity.get("external_handoffs") or []:
        if isinstance(handoff, Mapping):
            for key in ("event_ref", "handoff_ref", "receipt_ref"):
                value = handoff.get(key)
                if isinstance(value, str) and value.strip():
                    refs.add(value)
    return refs


def validate_basis_refs(manifest: MissionManifest, basis_refs: object) -> list[str]:
    if not isinstance(basis_refs, list) or not basis_refs or any(
        not isinstance(ref, str) or not ref.strip() for ref in basis_refs
    ):
        raise ValueError("MISSION_OS_BASIS_REQUIRED")
    available = available_basis_refs(manifest)
    unresolved = [ref for ref in basis_refs if ref not in available]
    if unresolved:
        raise ValueError("MISSION_OS_BASIS_UNRESOLVED:" + ",".join(unresolved))
    return list(basis_refs)


def available_contradiction_refs(manifest: MissionManifest) -> set[str]:
    """Return references that can truthfully authorize a contradiction replan."""
    refs: set[str] = set()
    for item in manifest.truth.get("contradictions") or []:
        if isinstance(item, str) and item.strip():
            refs.add(item)
        elif isinstance(item, Mapping):
            for key in ("ref", "subject_ref", "event_ref"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    refs.add(value)
    for handoff in manifest.continuity.get("external_handoffs") or []:
        if not isinstance(handoff, Mapping) or handoff.get("kind") != "watch-crossing":
            continue
        event_ref = handoff.get("event_ref")
        if isinstance(event_ref, str) and event_ref.strip():
            refs.add(event_ref)
    return refs


def validate_contradiction_refs(
    manifest: MissionManifest, contradiction_refs: object
) -> list[str]:
    if not isinstance(contradiction_refs, list) or not contradiction_refs or any(
        not isinstance(ref, str) or not ref.strip() for ref in contradiction_refs
    ):
        raise ValueError("REPLAN_CONTRADICTION_REQUIRED")
    available = available_contradiction_refs(manifest)
    unresolved = [ref for ref in contradiction_refs if ref not in available]
    if unresolved:
        raise ValueError(
            "REPLAN_CONTRADICTION_UNRESOLVED:" + ",".join(unresolved)
        )
    return list(contradiction_refs)


def _unmet_proof_tokens(
    manifest: MissionManifest,
    *,
    completion_proof_ids: Sequence[str] | None,
) -> set[str]:
    durable = set(manifest.continuity.get("durable_artifacts") or [])
    outcome = manifest.outcome
    completion = (
        list(completion_proof_ids)
        if completion_proof_ids is not None
        else list(outcome.get("completion_proof") or [])
    )
    scope = list(outcome.get("scope_proof") or [])
    return {
        ref
        for ref in completion + scope
        if isinstance(ref, str) and ref.strip() and ref not in durable
    }


def _defer_critical_path(
    manifest: MissionManifest,
    interest: Mapping[str, Any],
    *,
    completion_proof_ids: Sequence[str] | None,
) -> None:
    unmet = _unmet_proof_tokens(
        manifest, completion_proof_ids=completion_proof_ids
    )
    summary = interest.get("summary")
    if isinstance(summary, str) and summary in unmet:
        raise ValueError("DEFER_CRITICAL_PATH")
    refs = interest.get("subject_refs")
    if isinstance(refs, list) and any(ref in unmet for ref in refs):
        raise ValueError("DEFER_CRITICAL_PATH")
    frontier = manifest.state.get("current_frontier") or []
    if isinstance(frontier, list) and isinstance(summary, str) and summary in frontier:
        raise ValueError("DEFER_CRITICAL_PATH")

    clearance = interest.get("critical_path_clearance")
    if not isinstance(clearance, Mapping) or set(clearance) != {"reason", "basis_refs"}:
        raise ValueError("DEFER_CRITICAL_PATH_AMBIGUOUS")
    reason = clearance.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("DEFER_CRITICAL_PATH_AMBIGUOUS")
    try:
        validate_basis_refs(manifest, clearance.get("basis_refs"))
    except ValueError as exc:
        raise ValueError("DEFER_CRITICAL_PATH_AMBIGUOUS") from exc


def propose_frontier_patch(
    manifest: MissionManifest,
    labels: list[str],
    *,
    basis_refs: list[str] | None = None,
    replace_range: tuple[int, int] | None = None,
    forbidden_substrings: Sequence[str] = (),
) -> MissionOsProposal:
    _validate_labels(labels, forbidden_substrings=forbidden_substrings)
    basis = validate_basis_refs(
        manifest,
        list(basis_refs or ["authority:instruction", "outcome:desired_state"]),
    )
    frontier = manifest.state.get("current_frontier")
    if not isinstance(frontier, list):
        raise ValueError("FRONTIER_MUST_BE_ARRAY")
    start, end = replace_range or (0, len(frontier))
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int)
        or not isinstance(end, int)
        or start < 0
        or end < start
        or end > len(frontier)
    ):
        raise ValueError("FRONTIER_REPLACE_RANGE_INVALID")
    return _build_proposal(
        manifest,
        "frontier_patch",
        {
            "labels": list(labels),
            "basis_refs": basis,
            "replace_range": [start, end],
        },
    )


def propose_replan_slice(
    manifest: MissionManifest,
    *,
    new_frontier: list[str],
    contradiction_refs: list[str],
    basis_refs: list[str] | None = None,
    replace_range: tuple[int, int] | None = None,
    forbidden_substrings: Sequence[str] = (),
) -> MissionOsProposal:
    contradictions = validate_contradiction_refs(manifest, contradiction_refs)
    merged_basis = list(dict.fromkeys((basis_refs or []) + contradictions))
    proposal = propose_frontier_patch(
        manifest,
        new_frontier,
        basis_refs=merged_basis,
        replace_range=replace_range,
        forbidden_substrings=forbidden_substrings,
    )
    return _build_proposal(
        manifest,
        "replan_slice",
        {
            **proposal.content,
            "contradiction_refs": contradictions,
        },
    )


def propose_defer(
    manifest: MissionManifest,
    interest: Mapping[str, Any],
    *,
    completion_proof_ids: Sequence[str] | None = None,
) -> MissionOsProposal:
    copied = deepcopy(dict(interest))
    copied["created_at_revision"] = manifest.revision
    _defer_critical_path(
        manifest, copied, completion_proof_ids=completion_proof_ids
    )
    errors = validate_deferred_interest(copied, mission_id=manifest.mission_id)
    if errors:
        raise ValueError(errors[0])
    return _build_proposal(manifest, "defer", {"interest": copied})


def propose_return_rebind(
    manifest: MissionManifest,
    invalidate: list[Mapping[str, Any]],
) -> MissionOsProposal:
    if not invalidate or any(not isinstance(item, Mapping) for item in invalidate):
        raise ValueError("RETURN_REBIND_INVALIDATE_REQUIRED")
    return _build_proposal(
        manifest, "return_rebind", {"invalidate": deepcopy(invalidate)}
    )


def propose_absorb(
    manifest: MissionManifest,
    interest_index: int,
    *,
    amendment: str | None = None,
) -> MissionOsProposal:
    content: dict[str, Any] = {"interest_index": interest_index}
    if amendment is not None:
        content["amendment"] = amendment
    return _build_proposal(manifest, "absorb", content)


def emit_unanswered_condition(
    manifest: MissionManifest,
    condition: str,
    frontier_index: int = 0,
) -> dict[str, Any]:
    if not isinstance(condition, str) or not condition.strip():
        raise ValueError("EMPTY_BOUNDED_CONDITION")
    return {
        "condition": condition,
        "return_point": _return_point_dict(manifest, frontier_index),
    }
