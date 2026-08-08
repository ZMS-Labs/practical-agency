"""Bounded delegated authority checks; this module authorizes but never executes."""
from __future__ import annotations

from collections.abc import Iterable

from practical_agency.manifest_model import MissionManifest


def _ordered_unique(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(items))


def authorize_action(
    manifest: MissionManifest,
    capability_id: str,
    requested_permissions: Iterable[str],
    requested_effects: Iterable[str],
    estimated_costs: Iterable[str],
) -> list[str]:
    del capability_id  # Capability identity is recorded elsewhere; authority is data-driven.
    authority = manifest.authority
    errors: list[str] = []

    if authority.get("revoked") is True:
        errors.append("AUTHORITY_REVOKED")

    granted = set(authority.get("permissions", []))
    for permission in requested_permissions:
        if permission not in granted:
            errors.append(f"PERMISSION_NOT_GRANTED:{permission}")

    protected = set(authority.get("protected_state", []))
    escalation = set(authority.get("escalation_required_for", []))
    for effect in requested_effects:
        if effect in protected:
            errors.append(f"PROTECTED_STATE_VIOLATION:{effect}")
        if effect in escalation:
            errors.append(f"ESCALATION_REQUIRED:{effect}")

    authorized_costs = set(authority.get("acceptable_costs", []))
    for cost in estimated_costs:
        if cost not in authorized_costs:
            errors.append(f"COST_NOT_AUTHORIZED:{cost}")
        if cost in escalation:
            errors.append(f"ESCALATION_REQUIRED:{cost}")

    return _ordered_unique(errors)
