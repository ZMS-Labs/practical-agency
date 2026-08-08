"""Pure Mission OS proposal helpers (never mutate the manifest)."""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from practical_agency.deferred_interest import validate_deferred_interest
from practical_agency.manifest_model import MissionManifest

_SKILL_SHAPED_LABEL = re.compile(r"(?i)\b(skill|invoke|run)\s+[a-z0-9_-]+\b")


@dataclass(frozen=True, slots=True)
class MissionOsProposal:
    kind: str
    payload: dict[str, Any]


def _return_point_dict(manifest: MissionManifest, frontier_index: int) -> dict[str, Any]:
    frontier = manifest.state.get("current_frontier", [])
    if isinstance(frontier, list) and 0 <= frontier_index < len(frontier):
        label = str(frontier[frontier_index])
    else:
        label = str(manifest.state.get("next_action") or "resume mission")
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
    if isinstance(refs, list):
        for ref in refs:
            if isinstance(ref, str) and ref in unmet:
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
) -> MissionOsProposal:
    _validate_labels(labels, forbidden_substrings=forbidden_substrings)
    return MissionOsProposal("frontier_patch", {"labels": list(labels)})


def propose_replan_slice(
    manifest: MissionManifest,
    *,
    new_frontier: list[str],
    contradiction_refs: list[str],
    forbidden_substrings: Sequence[str] = (),
) -> MissionOsProposal:
    if not contradiction_refs:
        raise ValueError("REPLAN_CONTRADICTION_REQUIRED")
    _validate_labels(new_frontier, forbidden_substrings=forbidden_substrings)
    return MissionOsProposal(
        "replan_slice",
        {
            "labels": list(new_frontier),
            "contradiction_refs": list(contradiction_refs),
        },
    )


def propose_defer(
    manifest: MissionManifest,
    interest: Mapping[str, Any],
    *,
    completion_proof_ids: Sequence[str] | None = None,
) -> MissionOsProposal:
    copied = dict(interest)
    errors = validate_deferred_interest(copied, mission_id=manifest.mission_id)
    if errors:
        raise ValueError(errors[0])
    _defer_critical_path(
        manifest, copied, completion_proof_ids=completion_proof_ids
    )
    return MissionOsProposal("defer", {"interest": copied})


def propose_return_rebind(
    manifest: MissionManifest,
    invalidate: list[Mapping[str, Any]],
) -> MissionOsProposal:
    invalidated = [dict(item) for item in invalidate]
    return MissionOsProposal("return_rebind", {"invalidate": invalidated})


def emit_unanswered_condition(
    manifest: MissionManifest,
    condition: str,
    frontier_index: int = 0,
) -> dict[str, Any]:
    return {
        "condition": condition,
        "return_point": _return_point_dict(manifest, frontier_index),
    }
