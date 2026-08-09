"""Executable multi-process proof for durable, brokered filesystem missions."""
from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import queue
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from practical_agency.checkpoint_store import FileCheckpointStore
from practical_agency.coordinator import coordinate_once, dispatch_once
from practical_agency.filesystem_artifact import (
    FilesystemArtifactAdapter,
    inspect_filesystem_receipt,
    verify_filesystem_receipt,
)
from practical_agency.manifest_model import MissionManifest
from practical_agency.mission_os import build_mission_os_event
from practical_agency.mission_repository import discover_active_mission
from practical_agency.state_machine import TransitionError, apply_event_data


MISSION_ID = "durable-filesystem-proof"
PROOF_RELPATH = "mission-artifacts/durable-proof.txt"
PROOF_REF = f"file:{PROOF_RELPATH}"
INITIAL_BODY = "initial brokered artifact\n"
DRIFT_BODY = "externally planted drift\n"
REPAIRED_BODY = "repaired brokered artifact\n"
PROCESS_A_CRASH_EXIT = 86


class DurableProofError(RuntimeError):
    """Named failure in the executable proof harness."""


def _manifest_payload() -> dict[str, Any]:
    return {
        "schema": "mission-manifest@1",
        "mission_id": MISSION_ID,
        "revision": 1,
        "authority": {
            "operator_ref": "operator:proof",
            "instruction": (
                "Execute one bounded filesystem artifact mission, survive process "
                "interruption, detect drift, repair it, and preserve verifiable receipts."
            ),
            "amendments": [],
            "permissions": ["repository:write"],
            "protected_state": ["unrelated files"],
            "acceptable_costs": ["one local artifact write"],
            "escalation_required_for": ["destructive action"],
            "revoked": False,
            "revocation_reason": None,
        },
        "outcome": {
            "desired_state": "The receipt-bound artifact contains the repaired body.",
            "completion_proof": [PROOF_REF],
            "integrity_guards": [
                "all artifact writes require a one-use broker grant",
                "completion uses the latest typed verifier result",
            ],
            "scope_proof": ["filesystem-artifact@1 external receipt"],
            "stop_conditions": ["operator revokes authority"],
        },
        "truth": {
            "subject_refs": [PROOF_REF],
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
            "verifier_results": [],
        },
        "integrity": {
            "actor_may_self_accept": False,
            "required_gates": [],
            "unresolved_verdicts": [],
            "completion_acceptor": "acceptor:process-c",
        },
    }


def _initialize(workspace_root: Path) -> None:
    workspace = Path(workspace_root).resolve()
    mission_dir = workspace / "missions" / MISSION_ID
    if mission_dir.exists() and any(mission_dir.iterdir()):
        raise DurableProofError("PROOF_MISSION_DIRECTORY_NOT_EMPTY")
    store = FileCheckpointStore(mission_dir / "checkpoints")
    draft = MissionManifest.from_dict(_manifest_payload())
    draft_receipt = store.save(draft)
    active = apply_event_data(
        draft,
        "approve",
        "operator:proof",
        {"checkpoint_ref": draft_receipt.path},
    )
    active = apply_event_data(
        active,
        "apply_mission_os",
        "mission-steward",
        build_mission_os_event(
            active,
            "frontier_patch",
            {
                "labels": [
                    "write bounded artifact",
                    "verify receipt after interruption",
                ]
            },
        ),
    )
    store.save(active)


def _latest_execution_receipt(
    manifest: MissionManifest,
) -> Mapping[str, Any]:
    for receipt in reversed(manifest.continuity.get("execution_receipts", [])):
        if (
            isinstance(receipt, Mapping)
            and receipt.get("status") == "completed"
            and PROOF_REF in receipt.get("artifact_refs", [])
            and isinstance(receipt.get("request"), Mapping)
        ):
            return receipt
    raise DurableProofError("COMPLETED_FILESYSTEM_RECEIPT_NOT_FOUND")


def _dispatch_and_verify(
    manifest: MissionManifest,
    store: FileCheckpointStore,
    adapter: FilesystemArtifactAdapter,
    *,
    body: str,
    action: str,
) -> tuple[MissionManifest, dict[str, Any]]:
    decision = coordinate_once(
        manifest,
        execution_request={
            "capability_id": "filesystem-artifact",
            "requested_permissions": ["repository:write"],
            "requested_effects": [f"relpath:{PROOF_RELPATH}", f"utf8:{body}"],
            "estimated_costs": ["one local artifact write"],
            "action": action,
        },
        checkpoint_store=store,
    )
    if decision.kind != "DISPATCH" or decision.request is None:
        raise DurableProofError(
            f"BROKER_DID_NOT_AUTHORIZE:{decision.kind}:{decision.reason}"
        )
    receipt = dispatch_once(manifest, decision, adapter)
    if receipt.get("status") != "completed":
        raise DurableProofError(f"FILESYSTEM_EFFECT_NOT_COMPLETED:{receipt.get('status')}")
    recorded = apply_event_data(
        manifest,
        "record_execution_receipt",
        "mission-steward",
        {"receipt": receipt, "request": decision.request},
    )
    acted = apply_event_data(
        recorded,
        "record_action",
        "mission-steward",
        {"action_ref": receipt["artifact_refs"][0]},
    )
    verification = verify_filesystem_receipt(
        str(receipt["external_receipt_ref"]),
        decision.request,
        adapter.root,
    )
    verified = apply_event_data(
        acted,
        "record_verifier_result",
        "observer:artifact-verifier",
        {"result": verification.to_dict()},
    )
    return verified, receipt


def _process_a(workspace_root: str) -> None:
    discovered = discover_active_mission(Path(workspace_root))
    store = FileCheckpointStore(discovered.mission_dir / "checkpoints")
    adapter = FilesystemArtifactAdapter(discovered.mission_dir / "adapter_data")
    checkpointed, _ = _dispatch_and_verify(
        discovered.manifest,
        store,
        adapter,
        body=INITIAL_BODY,
        action="write-text",
    )
    store.save(checkpointed)
    os._exit(PROCESS_A_CRASH_EXIT)


def _process_b(workspace_root: str) -> dict[str, Any]:
    discovered = discover_active_mission(Path(workspace_root))
    store = FileCheckpointStore(discovered.mission_dir / "checkpoints")
    adapter = FilesystemArtifactAdapter(discovered.mission_dir / "adapter_data")
    persisted_receipt = _latest_execution_receipt(discovered.manifest)
    contradiction = inspect_filesystem_receipt(
        str(persisted_receipt["external_receipt_ref"]),
        persisted_receipt["request"],
        adapter.root,
    )
    if contradiction.status != "contradicted":
        raise DurableProofError(
            f"PLANTED_DRIFT_NOT_DETECTED:{contradiction.status}"
        )
    reopened = apply_event_data(
        discovered.manifest,
        "record_verifier_result",
        "observer:process-b",
        {"result": contradiction.to_dict()},
    )
    store.save(reopened)
    repaired, receipt = _dispatch_and_verify(
        reopened,
        store,
        adapter,
        body=REPAIRED_BODY,
        action=str(reopened.state["next_action"]),
    )
    verifying = apply_event_data(
        repaired,
        "begin_verification",
        "mission-steward",
        {},
    )
    checkpoint = store.save(verifying)
    return {
        "drift_detection": contradiction.reason_code,
        "external_receipt_ref": receipt["external_receipt_ref"],
        "checkpoint_sha256": checkpoint.sha256,
    }


def _process_c(workspace_root: str) -> dict[str, Any]:
    discovered = discover_active_mission(Path(workspace_root))
    store = FileCheckpointStore(discovered.mission_dir / "checkpoints")
    adapter = FilesystemArtifactAdapter(discovered.mission_dir / "adapter_data")
    persisted_receipt = _latest_execution_receipt(discovered.manifest)
    verification = verify_filesystem_receipt(
        str(persisted_receipt["external_receipt_ref"]),
        persisted_receipt["request"],
        adapter.root,
    )
    independently_observed = apply_event_data(
        discovered.manifest,
        "record_verifier_result",
        "observer:process-c",
        {"result": verification.to_dict()},
    )
    store.save(independently_observed)
    verdict = {
        "verdict": "PASS",
        "evidence_refs": [
            verification.result_ref,
            verification.external_receipt_ref,
        ],
        "coverage_limits": [
            "process separation is proven; OS account separation is not",
        ],
        "separation_assurance": "declared-role-separation",
        "principal_evidence_ref": None,
    }
    try:
        apply_event_data(
            independently_observed,
            "accept",
            "mission-steward",
            verdict,
        )
    except TransitionError as error:
        if str(error) != "INDEPENDENT_ACCEPTANCE_REQUIRED":
            raise
    else:
        raise DurableProofError("MISSION_STEWARD_SELF_ACCEPTANCE_WAS_NOT_REJECTED")
    completed = apply_event_data(
        independently_observed,
        "accept",
        "acceptor:process-c",
        verdict,
    )
    checkpoint = store.save(completed)
    acceptance = completed.continuity["decisions"][-1]
    return {
        "final_status": completed.state["status"],
        "final_checkpoint_sha256": checkpoint.sha256,
        "third_verifier_result_ref": verification.result_ref,
        "acceptance_assurance": acceptance["separation_assurance"],
    }


def _queue_phase(
    target: Callable[[str], dict[str, Any]],
    workspace_root: str,
    result_queue: Any,
) -> None:
    try:
        result_queue.put({"ok": True, "result": target(workspace_root)})
    except Exception as error:
        result_queue.put(
            {
                "ok": False,
                "error": f"{type(error).__name__}:{error}",
            }
        )
        raise


def _run_queued_phase(
    context: multiprocessing.context.BaseContext,
    target: Callable[[str], dict[str, Any]],
    workspace_root: Path,
) -> dict[str, Any]:
    result_queue = context.Queue()
    process = context.Process(
        target=_queue_phase,
        args=(target, str(workspace_root), result_queue),
    )
    process.start()
    process.join(20)
    if process.is_alive():
        process.terminate()
        process.join(5)
        raise DurableProofError("PROOF_PHASE_TIMEOUT")
    try:
        envelope = result_queue.get(timeout=2)
    except queue.Empty as error:
        raise DurableProofError(
            f"PROOF_PHASE_NO_RESULT:exit={process.exitcode}"
        ) from error
    if process.exitcode != 0 or envelope.get("ok") is not True:
        raise DurableProofError(
            f"PROOF_PHASE_FAILED:exit={process.exitcode}:"
            f"{envelope.get('error')}"
        )
    return dict(envelope["result"])


def run_proof(workspace_root: Path) -> dict[str, Any]:
    workspace = Path(workspace_root).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    _initialize(workspace)
    context = multiprocessing.get_context("spawn")

    process_a = context.Process(target=_process_a, args=(str(workspace),))
    process_a.start()
    process_a.join(20)
    if process_a.is_alive():
        process_a.terminate()
        process_a.join(5)
        raise DurableProofError("PROCESS_A_TIMEOUT")
    if process_a.exitcode != PROCESS_A_CRASH_EXIT:
        raise DurableProofError(f"PROCESS_A_DID_NOT_CRASH:{process_a.exitcode}")

    mission_dir = workspace / "missions" / MISSION_ID
    artifact = mission_dir / "adapter_data" / PROOF_RELPATH
    if not artifact.is_file():
        raise DurableProofError("PROCESS_A_ARTIFACT_MISSING")
    artifact.write_text(DRIFT_BODY, encoding="utf-8")

    process_b = _run_queued_phase(context, _process_b, workspace)
    process_c = _run_queued_phase(context, _process_c, workspace)
    return {
        "schema": "durable-mission-proof@1",
        "mission_id": MISSION_ID,
        "process_a_exit_code": process_a.exitcode,
        "drift_detection": process_b["drift_detection"],
        "external_receipt_ref": process_b["external_receipt_ref"],
        "final_status": process_c["final_status"],
        "final_checkpoint_sha256": process_c["final_checkpoint_sha256"],
        "third_verifier_result_ref": process_c["third_verifier_result_ref"],
        "acceptance_assurance": process_c["acceptance_assurance"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Run the fixed multi-process proof")
    run_parser.add_argument("--workspace-root", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command != "run":
        raise DurableProofError("UNKNOWN_PROOF_COMMAND")
    report = run_proof(args.workspace_root)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
