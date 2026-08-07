"""Bounded action authorization against a mission manifest."""

from __future__ import annotations

from typing import Iterable, Sequence

from practical_agency.manifest_model import MissionManifest


def authorize_action(
    manifest: MissionManifest,
    capability_id: str,
    requested_permissions: Sequence[str],
    requested_effects: Sequence[str],
    estimated_costs: Sequence[str],
) -> list[str]:
    """Return named refusal codes; an empty list means inside authority."""
    del capability_id  # capability selection is recorded elsewhere; authority is effect-bound
    refusals: list[str] = []
    authority = manifest.authority

    if authority.get("revoked") is True:
        refusals.append("AUTHORITY_REVOKED: operator authority has been revoked")
        return refusals

    permitted = set(authority.get("permissions") or [])
    for permission in requested_permissions:
        if permission not in permitted:
            refusals.append(f"PERMISSION_NOT_GRANTED: {permission}")

    protected = set(authority.get("protected_state") or [])
    for effect in requested_effects:
        if effect in protected:
            refusals.append(f"PROTECTED_STATE_VIOLATION: {effect}")

    acceptable = set(authority.get("acceptable_costs") or [])
    for cost in estimated_costs:
        if cost not in acceptable:
            refusals.append(f"COST_NOT_AUTHORIZED: {cost}")

    escalation = set(authority.get("escalation_required_for") or [])
    for effect in requested_effects:
        if effect in escalation:
            refusals.append(f"ESCALATION_REQUIRED: {effect}")

    return refusals


def effects_touch_protected(manifest: MissionManifest, effects: Iterable[str]) -> bool:
    protected = set(manifest.authority.get("protected_state") or [])
    return any(effect in protected for effect in effects)
