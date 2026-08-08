from __future__ import annotations

from copy import deepcopy
from typing import Any


def minimal_payload() -> dict[str, Any]:
    return {
        "schema": "mission-manifest@1",
        "mission_id": "mission-001",
        "revision": 1,
        "authority": {
            "operator_ref": "operator:test",
            "instruction": "Create and verify the example artifact.",
            "amendments": [],
            "permissions": ["repository:write"],
            "protected_state": ["unrelated files"],
            "acceptable_costs": ["one feature branch"],
            "escalation_required_for": ["destructive action"],
            "revoked": False,
            "revocation_reason": None,
        },
        "outcome": {
            "desired_state": "The example artifact exists and validates.",
            "completion_proof": ["artifact:validator-pass"],
            "integrity_guards": ["runtime reads the canonical artifact"],
            "scope_proof": ["diff contains only intended files"],
            "stop_conditions": ["operator revokes authority"],
        },
        "truth": {
            "subject_refs": ["repo:example@rev-1"],
            "verified_facts": [],
            "assumptions": [],
            "contradictions": [],
            "unknowns": [],
        },
        "state": {
            "status": "draft",
            "completed_actions": [],
            "current_frontier": ["obtain approval"],
            "blockers": [],
            "next_action": "obtain approval",
        },
        "capabilities": {
            "discovered_at": None,
            "available": [],
            "invoked": [],
            "unavailable": [],
            "degraded": [],
        },
        "continuity": {
            "prior_checkpoint": None,
            "durable_artifacts": [],
            "decisions": [],
            "external_handoffs": [],
            "watch_commissions": [],
            "deferred_interests": [],
            "processed_event_ids": [],
            "execution_receipts": [],
        },
        "integrity": {
            "actor_may_self_accept": False,
            "required_gates": [],
            "unresolved_verdicts": [],
            "completion_acceptor": None,
        },
    }


def clone_payload() -> dict[str, Any]:
    return deepcopy(minimal_payload())


def mission_os_event(
    manifest: "MissionManifest", kind: str, content: dict[str, Any]
) -> dict[str, Any]:
    """Return a validated, revision-bound mission-OS event payload for tests."""
    from practical_agency.mission_os import (
        propose_absorb,
        propose_defer,
        propose_frontier_patch,
        propose_replan_slice,
        propose_return_rebind,
    )

    if kind == "frontier_patch":
        proposal = propose_frontier_patch(
            manifest,
            list(content["labels"]),
            basis_refs=content.get("basis_refs"),
            replace_range=tuple(content["replace_range"]) if "replace_range" in content else None,
        )
    elif kind == "replan_slice":
        proposal = propose_replan_slice(
            manifest,
            new_frontier=list(content["labels"]),
            contradiction_refs=list(content["contradiction_refs"]),
            basis_refs=content.get("basis_refs"),
            replace_range=tuple(content["replace_range"]) if "replace_range" in content else None,
        )
    elif kind == "defer":
        proposal = propose_defer(manifest, content["interest"])
    elif kind == "return_rebind":
        proposal = propose_return_rebind(manifest, list(content["invalidate"]))
    elif kind == "absorb":
        proposal = propose_absorb(
            manifest,
            content["interest_index"],
            amendment=content.get("amendment"),
        )
    else:
        raise ValueError(f"unknown mission OS test proposal: {kind}")
    return proposal.to_event_data()


def critical_path_clearance(
    *, reason: str = "Recorded as outside the current completion path.",
    basis_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "reason": reason,
        "basis_refs": list(basis_refs or ["authority:instruction"]),
    }
