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
    from practical_agency.mission_os import build_mission_os_event

    return build_mission_os_event(manifest, kind, content)


def critical_path_clearance(
    *, reason: str = "Recorded as outside the current completion path.",
    basis_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "reason": reason,
        "basis_refs": list(basis_refs or ["authority:instruction"]),
    }


def record_fixture_verifier_result(
    manifest: "MissionManifest",
    *,
    proof_ref: str = "artifact:validator-pass",
    subject_ref: str = "repo:example@rev-1",
    value: object = "validated",
) -> "MissionManifest":
    """Record a real typed fixture verifier result through production events."""
    from practical_agency.proof import VerifierResult
    from practical_agency.state_machine import apply_event_data

    request = {
        "schema": "execution-request@1",
        "request_id": (
            f"{manifest.mission_id}:r{manifest.revision}:"
            "fixture-proof:execution:f0"
        ),
        "mission_id": manifest.mission_id,
        "mission_revision": manifest.revision,
        "capability_id": "fixture-proof",
        "requested_permissions": [],
        "requested_effects": [proof_ref],
        "estimated_costs": [],
        "action": "observe fixture artifact",
    }
    receipt = {
        "schema": "execution-receipt@1",
        "request_id": request["request_id"],
        "mission_id": request["mission_id"],
        "mission_revision": request["mission_revision"],
        "adapter_ref": "fixture-proof@1",
        "status": "completed",
        "artifact_refs": [proof_ref],
        "observed_effects": [
            {"kind": "fixture-observation", "artifact_ref": proof_ref, "value": value}
        ],
        "external_receipt_ref": f"fixture://receipt/{request['request_id']}",
        "coverage_limits": ["fixture verifier only"],
    }
    recorded = apply_event_data(
        manifest,
        "record_execution_receipt",
        "mission-steward",
        {"receipt": receipt, "request": request},
    )
    result = VerifierResult.bind(
        verifier_ref="fixture-verifier@1",
        status="verified",
        proof_ref=proof_ref,
        subject_ref=subject_ref,
        request=request,
        receipt=receipt,
        observation={
            "kind": "fixture-observation",
            "artifact_ref": proof_ref,
            "value": value,
        },
        reason_code=None,
        coverage_limits=("fixture verifier only",),
    )
    return apply_event_data(
        recorded,
        "record_verifier_result",
        "observer:test",
        {"result": result.to_dict()},
    )
