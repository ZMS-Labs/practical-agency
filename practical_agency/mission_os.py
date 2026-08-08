"""Pure Mission OS proposal helpers (never mutate the manifest)."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from practical_agency.deferred_interest import validate_deferred_interest
from practical_agency.manifest_model import MissionManifest

_SKILL_SHAPED_LABEL = re.compile(r"(?i)\b(skill|invoke|run)\s+[a-z0-9_-]+\b")
_DEFAULT_BASIS_REFS = ("authority:instruction", "outcome:desired_state")
_PROPOSAL_BINDING_FIELDS = {
    "proposal_id",
    "proposal_mission_id",
    "proposal_base_revision",
    "proposal_payload_sha256",
}


@dataclass(frozen=True, slots=True)
class MissionOsProposal:
    kind: str
    payload: dict[str, Any]


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
        raise ValueError("INVALID_FRONTIER_INDEX")
    return {
        "mission_id": manifest.mission_id,
        "revision": manifest.revision,
        "frontier_index": frontier_index,
        "label": label,
    }


def _validate_labels(
    labels: Sequence[str], *, forbidden_substrings: Sequence[str] = ()
) -> None:
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


def _mapping_refs(value: object) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, str) and value.strip():
        refs.add(value)
    elif isinstance(value, Mapping):
        for key in ("ref", "subject_ref", "artifact_ref", "event_ref", "receipt_ref"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                refs.add(item)
    return refs


def _known_basis_refs(manifest: MissionManifest) -> set[str]:
    refs = set(_DEFAULT_BASIS_REFS)
    for index, amendment in enumerate(manifest.authority.get("amendments", [])):
        if isinstance(amendment, str) and amendment.strip():
            refs.add(f"authority:amendment:{index}")
    for field in (
        "completion_proof",
        "integrity_guards",
        "scope_proof",
        "stop_conditions",
    ):
        for item in manifest.outcome.get(field, []):
            if isinstance(item, str) and item.strip():
                refs.add(item)
    for item in manifest.truth.get("subject_refs", []):
        if isinstance(item, str) and item.strip():
            refs.add(item)
    for field in ("verified_facts", "assumptions", "contradictions", "unknowns"):
        for item in manifest.truth.get(field, []):
            refs.update(_mapping_refs(item))
    for item in manifest.continuity.get("durable_artifacts", []):
        if isinstance(item, str) and item.strip():
            refs.add(item)
    for item in manifest.continuity.get("external_handoffs", []):
        refs.update(_mapping_refs(item))
    return refs


def _known_subject_refs(manifest: MissionManifest) -> set[str]:
    refs: set[str] = set()
    for item in manifest.truth.get("subject_refs", []):
        if isinstance(item, str) and item.strip():
            refs.add(item)
    for field in ("verified_facts", "assumptions", "contradictions", "unknowns"):
        for item in manifest.truth.get(field, []):
            refs.update(_mapping_refs(item))
    for field in ("completion_proof", "scope_proof"):
        for item in manifest.outcome.get(field, []):
            if isinstance(item, str) and item.strip():
                refs.add(item)
    for item in manifest.continuity.get("durable_artifacts", []):
        if isinstance(item, str) and item.strip():
            refs.add(item)
    for item in manifest.continuity.get("external_handoffs", []):
        refs.update(_mapping_refs(item))
    return refs


def _known_contradiction_refs(manifest: MissionManifest) -> set[str]:
    refs: set[str] = set()
    for item in manifest.truth.get("contradictions", []):
        refs.update(_mapping_refs(item))
    for item in manifest.continuity.get("external_handoffs", []):
        if isinstance(item, Mapping) and item.get("kind") == "watch-crossing":
            refs.update(_mapping_refs(item))
    return refs


def _validate_basis_refs(manifest: MissionManifest, basis_refs: object) -> list[str]:
    if (
        not isinstance(basis_refs, list)
        or not basis_refs
        or any(not isinstance(item, str) or not item.strip() for item in basis_refs)
    ):
        raise ValueError("FRONTIER_BASIS_REQUIRED")
    known = _known_basis_refs(manifest)
    for ref in basis_refs:
        if ref not in known:
            raise ValueError(f"FRONTIER_BASIS_UNKNOWN:{ref}")
    return list(basis_refs)


def _validate_contradiction_refs(
    manifest: MissionManifest, contradiction_refs: object
) -> list[str]:
    if (
        not isinstance(contradiction_refs, list)
        or not contradiction_refs
        or any(
            not isinstance(item, str) or not item.strip()
            for item in contradiction_refs
        )
    ):
        raise ValueError("REPLAN_CONTRADICTION_REQUIRED")
    known = _known_contradiction_refs(manifest)
    for ref in contradiction_refs:
        if ref not in known:
            raise ValueError(f"REPLAN_CONTRADICTION_UNKNOWN:{ref}")
    return list(contradiction_refs)


def _proposal_body(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(value)
        for key, value in payload.items()
        if key not in _PROPOSAL_BINDING_FIELDS
        and key not in {"proposal_kind", "checkpoint_ref"}
    }


def _proposal_digest(
    *, kind: str, mission_id: str, base_revision: int, body: Mapping[str, Any]
) -> str:
    canonical = {
        "kind": kind,
        "mission_id": mission_id,
        "base_revision": base_revision,
        "payload": deepcopy(dict(body)),
    }
    try:
        encoded = json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError("MISSION_OS_PROPOSAL_NOT_CANONICAL") from error
    return hashlib.sha256(encoded).hexdigest()


def _bind_proposal(
    manifest: MissionManifest, kind: str, body: Mapping[str, Any]
) -> MissionOsProposal:
    copied = deepcopy(dict(body))
    digest = _proposal_digest(
        kind=kind,
        mission_id=manifest.mission_id,
        base_revision=manifest.revision,
        body=copied,
    )
    return MissionOsProposal(
        kind,
        {
            **copied,
            "proposal_id": f"proposal:{digest[:24]}",
            "proposal_mission_id": manifest.mission_id,
            "proposal_base_revision": manifest.revision,
            "proposal_payload_sha256": digest,
        },
    )


def _validate_proposal_binding(
    manifest: MissionManifest, kind: str, payload: Mapping[str, Any]
) -> dict[str, Any]:
    proposal_id = payload.get("proposal_id")
    mission_id = payload.get("proposal_mission_id")
    base_revision = payload.get("proposal_base_revision")
    supplied_digest = payload.get("proposal_payload_sha256")
    if not isinstance(proposal_id, str) or not proposal_id.strip():
        raise ValueError("MISSION_OS_PROPOSAL_ID_REQUIRED")
    if mission_id != manifest.mission_id:
        raise ValueError("MISSION_OS_PROPOSAL_MISSION_MISMATCH")
    if (
        isinstance(base_revision, bool)
        or not isinstance(base_revision, int)
        or base_revision != manifest.revision
    ):
        raise ValueError("MISSION_OS_PROPOSAL_REVISION_MISMATCH")
    if not isinstance(supplied_digest, str) or not re.fullmatch(
        r"[0-9a-f]{64}", supplied_digest
    ):
        raise ValueError("MISSION_OS_PROPOSAL_HASH_REQUIRED")
    body = _proposal_body(payload)
    actual = _proposal_digest(
        kind=kind,
        mission_id=manifest.mission_id,
        base_revision=manifest.revision,
        body=body,
    )
    if actual != supplied_digest:
        raise ValueError("MISSION_OS_PROPOSAL_HASH_MISMATCH")
    if proposal_id != f"proposal:{actual[:24]}":
        raise ValueError("MISSION_OS_PROPOSAL_ID_MISMATCH")
    return body


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
    tokens: set[str] = set()
    for ref in completion + scope:
        if isinstance(ref, str) and ref.strip() and ref not in durable:
            tokens.add(ref)
    return tokens


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
    if not isinstance(refs, list) or not refs:
        raise ValueError("DEFER_CRITICAL_PATH_AMBIGUOUS")
    known = _known_subject_refs(manifest)
    for ref in refs:
        if not isinstance(ref, str) or not ref.strip() or ref not in known:
            raise ValueError("DEFER_CRITICAL_PATH_AMBIGUOUS")
        if ref in unmet:
            raise ValueError("DEFER_CRITICAL_PATH")

    frontier = manifest.state.get("current_frontier") or []
    if (
        isinstance(frontier, list)
        and len(frontier) == 1
        and isinstance(summary, str)
        and summary == frontier[0]
    ):
        raise ValueError("DEFER_CRITICAL_PATH")


def propose_frontier_patch(
    manifest: MissionManifest,
    labels: list[str],
    *,
    forbidden_substrings: Sequence[str] = (),
    basis_refs: Sequence[str] = _DEFAULT_BASIS_REFS,
) -> MissionOsProposal:
    if not labels:
        raise ValueError("FRONTIER_LABELS_REQUIRED")
    _validate_labels(labels, forbidden_substrings=forbidden_substrings)
    validated_basis = _validate_basis_refs(manifest, list(basis_refs))
    return _bind_proposal(
        manifest,
        "frontier_patch",
        {"labels": list(labels), "basis_refs": validated_basis},
    )


def propose_replan_slice(
    manifest: MissionManifest,
    *,
    new_frontier: list[str],
    contradiction_refs: list[str],
    forbidden_substrings: Sequence[str] = (),
    basis_refs: Sequence[str] = _DEFAULT_BASIS_REFS,
) -> MissionOsProposal:
    if not new_frontier:
        raise ValueError("FRONTIER_LABELS_REQUIRED")
    _validate_labels(new_frontier, forbidden_substrings=forbidden_substrings)
    validated_contradictions = _validate_contradiction_refs(
        manifest, contradiction_refs
    )
    validated_basis = _validate_basis_refs(manifest, list(basis_refs))
    return _bind_proposal(
        manifest,
        "replan_slice",
        {
            "labels": list(new_frontier),
            "contradiction_refs": validated_contradictions,
            "basis_refs": validated_basis,
        },
    )


def propose_defer(
    manifest: MissionManifest,
    interest: Mapping[str, Any],
    *,
    completion_proof_ids: Sequence[str] | None = None,
) -> MissionOsProposal:
    copied = deepcopy(interest)
    errors = validate_deferred_interest(copied, mission_id=manifest.mission_id)
    if errors:
        raise ValueError(errors[0])
    if copied.get("created_at_revision") != manifest.revision:
        raise ValueError("DEFERRED_INTEREST_REVISION_MISMATCH")
    _defer_critical_path(
        manifest, copied, completion_proof_ids=completion_proof_ids
    )
    return _bind_proposal(manifest, "defer", {"interest": copied})


def propose_return_rebind(
    manifest: MissionManifest,
    invalidate: list[Mapping[str, Any]],
) -> MissionOsProposal:
    invalidated = deepcopy(invalidate)
    if not invalidated:
        raise ValueError("RETURN_REBIND_INVALIDATE_REQUIRED")
    return _bind_proposal(
        manifest, "return_rebind", {"invalidate": invalidated}
    )


def propose_absorb(
    manifest: MissionManifest,
    interest_index: int,
    *,
    amendment: str | None = None,
) -> MissionOsProposal:
    body: dict[str, Any] = {"interest_index": interest_index}
    if amendment is not None:
        body["amendment"] = amendment
    return _bind_proposal(manifest, "absorb", body)


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
