"""Bounded delegated authority for mission actions and amendments."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from .manifest_model import MissionManifest


@dataclass(frozen=True, slots=True)
class ActionRequest:
    action_id: str
    description: str
    required_permissions: tuple[str, ...]
    touches: tuple[str, ...]
    costs: tuple[str, ...]
    consequential: bool
    irreversible: bool
    authority_ref: str | None
    stop_condition: str


@dataclass(frozen=True, slots=True)
class AuthorityDecision:
    allowed: bool
    code: str
    detail: str


def _deny(code: str, detail: str) -> AuthorityDecision:
    return AuthorityDecision(False, code, detail)


def evaluate_action(manifest: MissionManifest, request: ActionRequest) -> AuthorityDecision:
    authority = manifest.authority
    if authority["revoked"]:
        return _deny("AUTHORITY_REVOKED", authority.get("revocation_reason") or "authority revoked")
    status = manifest.state["status"]
    if status in {"completed", "cancelled"}:
        return _deny("MISSION_TERMINAL", f"mission is {status}")
    if status != "active":
        return _deny("MISSION_NOT_ACTIVE", f"mission is {status}")

    granted = set(authority["permissions"])
    missing = sorted(set(request.required_permissions) - granted)
    if missing:
        return _deny("PERMISSION_NOT_GRANTED", ", ".join(missing))

    protected = set(authority["protected_state"])
    touched_protected = sorted(protected.intersection(request.touches))
    if touched_protected:
        return _deny("PROTECTED_STATE", ", ".join(touched_protected))

    accepted_costs = set(authority["acceptable_costs"])
    rejected_costs = sorted(set(request.costs) - accepted_costs)
    if rejected_costs:
        return _deny("COST_NOT_ACCEPTED", ", ".join(rejected_costs))

    if not request.authority_ref:
        return _deny("AUTHORITY_RECEIPT_REQUIRED", "dispatch needs a scoped authority receipt")

    escalation_terms = {term.casefold() for term in authority["escalation_required_for"]}
    description = request.description.casefold()
    if request.irreversible or any(term and term in description for term in escalation_terms):
        return _deny("ESCALATION_REQUIRED", "irreversible or explicitly escalated action")

    if not request.stop_condition.strip():
        return _deny("STOP_CONDITION_REQUIRED", "every dispatch needs a bounded stop condition")

    return AuthorityDecision(True, "AUTHORIZED", "request is within recorded delegated authority")


def apply_amendment(
    manifest: MissionManifest,
    *,
    instruction: str,
    authorized_by: str,
    authorization_ref: str,
    recorded_at: str,
) -> MissionManifest:
    if authorized_by != manifest.authority["operator_ref"]:
        raise ValueError("OPERATOR_AUTHORITY_REQUIRED: only the recorded operator may amend the mission")
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("AMENDMENT_REQUIRED: instruction must be non-empty")
    if not isinstance(authorization_ref, str) or not authorization_ref.strip():
        raise ValueError("AUTHORIZATION_RECEIPT_REQUIRED: amendment needs a durable authority reference")
    if not isinstance(recorded_at, str) or not recorded_at.strip():
        raise ValueError("AMENDMENT_TIME_REQUIRED: amendment needs a durable timestamp")

    payload = manifest.to_dict()
    payload["revision"] = manifest.revision + 1
    payload["authority"]["amendments"].append(
        {
            "revision": payload["revision"],
            "instruction": instruction,
            "authorized_by": authorized_by,
            "authorization_ref": authorization_ref,
            "recorded_at": recorded_at,
        }
    )
    payload["continuity"]["decisions"].append(
        {
            "kind": "authority-amendment",
            "revision": payload["revision"],
            "actor_ref": authorized_by,
            "evidence_ref": authorization_ref,
        }
    )
    return MissionManifest.from_dict(payload)


def revoke_authority(
    manifest: MissionManifest,
    *,
    operator_ref: str,
    reason: str,
    authorization_ref: str,
    recorded_at: str,
) -> MissionManifest:
    if operator_ref != manifest.authority["operator_ref"]:
        raise ValueError("OPERATOR_AUTHORITY_REQUIRED: revocation actor does not match operator")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("REVOCATION_REASON_REQUIRED: reason must be non-empty")
    if not isinstance(authorization_ref, str) or not authorization_ref.strip():
        raise ValueError("REVOCATION_RECEIPT_REQUIRED: revocation needs a durable authority reference")
    if not isinstance(recorded_at, str) or not recorded_at.strip():
        raise ValueError("REVOCATION_TIME_REQUIRED: revocation needs a durable timestamp")
    payload = copy.deepcopy(manifest.to_dict())
    payload["revision"] = manifest.revision + 1
    payload["authority"]["revoked"] = True
    payload["authority"]["revocation_reason"] = reason
    payload["state"]["status"] = "cancelled"
    payload["state"]["blockers"] = []
    payload["state"]["current_frontier"] = []
    payload["state"]["next_action"] = None
    payload["continuity"]["decisions"].append(
        {
            "kind": "revocation",
            "revision": payload["revision"],
            "actor_ref": operator_ref,
            "reason": reason,
            "evidence_ref": authorization_ref,
            "recorded_at": recorded_at,
        }
    )
    return MissionManifest.from_dict(payload)
