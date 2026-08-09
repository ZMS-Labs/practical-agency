"""Practical Agency CLI Bridge for harness-agnostic mission control."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from practical_agency.checkpoint_store import FileCheckpointStore
from practical_agency.coordinator import coordinate_once, dispatch_once
from practical_agency.filesystem_artifact import (
    FilesystemArtifactAdapter,
    verify_filesystem_receipt,
)
from practical_agency.manifest_model import MissionManifest
from practical_agency.state_machine import TransitionError, apply_event_data
from practical_agency.mission_os import build_mission_os_event


def _minimal_payload(
    mission_id: str,
    intent: str,
    acceptor: str,
    proof_relpath: str,
    operator_ref: str = "operator:cli",
) -> dict:
    return {
        "schema": "mission-manifest@1",
        "mission_id": mission_id,
        "revision": 1,
        "authority": {
            "operator_ref": operator_ref,
            "instruction": intent,
            "amendments": [],
            "permissions": ["repository:write"],
            "protected_state": ["unrelated files"],
            "acceptable_costs": ["one file"],
            "escalation_required_for": ["destructive action"],
            "revoked": False,
            "revocation_reason": None,
        },
        "outcome": {
            "desired_state": "Mission intent achieved and verified with external receipts.",
            "completion_proof": [f"file:{proof_relpath}"],
            "integrity_guards": ["runtime verification with external receipts"],
            "scope_proof": ["diff contains only intended changes"],
            "stop_conditions": ["operator revokes authority"],
        },
        "truth": {
            "subject_refs": ["repo:main"],
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
            "completion_acceptor": acceptor,
        },
    }


def cmd_init(args: argparse.Namespace) -> int:
    mission_dir = Path(args.out).resolve()
    mission_dir.mkdir(parents=True, exist_ok=True)
    store = FileCheckpointStore(mission_dir / "checkpoints")

    payload = _minimal_payload(
        args.mission_id,
        args.intent,
        args.acceptor,
        args.proof_relpath,
        args.operator,
    )
    draft = MissionManifest.from_dict(payload)
    chk = store.save(draft)
    print(f"Initialized draft mission {draft.mission_id} (r{draft.revision}) at {chk.path}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    mission_dir = Path(args.mission_dir).resolve()
    store = FileCheckpointStore(mission_dir / "checkpoints")
    latest = store.load_latest(mission_dir.name if args.mission_id is None else args.mission_id)
    if not latest:
        files = list((mission_dir / "checkpoints").glob("*.r*.receipt.json"))
        if not files:
            print(f"No active mission found in {mission_dir}")
            return 1
        m_id = files[0].name.split(".r")[0]
        latest = store.load_latest(m_id)
        if not latest:
            print("Failed to load mission checkpoint.")
            return 1

    manifest, chk = latest
    print(f"Mission ID:        {manifest.mission_id}")
    print(f"Revision:          {manifest.revision}")
    print(f"Status:            {manifest.state['status']}")
    print(f"Next Action:       {manifest.state.get('next_action')}")
    print(f"Current Frontier:  {manifest.state.get('current_frontier')}")
    print(f"Blockers:          {manifest.state.get('blockers')}")
    print(f"Durable Artifacts: {manifest.continuity.get('durable_artifacts')}")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    mission_dir = Path(args.mission_dir).resolve()
    store = FileCheckpointStore(mission_dir / "checkpoints")

    files = list((mission_dir / "checkpoints").glob("*.r*.receipt.json"))
    if not files:
        print(f"No checkpoint found in {mission_dir}")
        return 1
    m_id = files[0].name.split(".r")[0]
    loaded = store.load_latest(m_id)
    if not loaded:
        print("Failed to load mission checkpoint.")
        return 1

    manifest, chk = loaded
    operator_ref = args.operator or manifest.authority["operator_ref"]
    active = apply_event_data(
        manifest,
        "approve",
        operator_ref,
        {"checkpoint_ref": chk.path},
    )
    active = apply_event_data(
        active,
        "apply_mission_os",
        "mission-steward",
        build_mission_os_event(
            active,
            "frontier_patch",
            {"labels": ["write-text"]},
        ),
    )
    new_chk = store.save(active)
    print(f"Mission {active.mission_id} approved & active (r{active.revision}). Saved: {new_chk.path}")
    return 0


def cmd_dispatch_file(args: argparse.Namespace) -> int:
    mission_dir = Path(args.mission_dir).resolve()
    store = FileCheckpointStore(mission_dir / "checkpoints")

    files = list((mission_dir / "checkpoints").glob("*.r*.receipt.json"))
    m_id = files[0].name.split(".r")[0]
    loaded = store.load_latest(m_id)
    if not loaded:
        print("Failed to load mission checkpoint.")
        return 1

    manifest, _ = loaded
    adapter_root = mission_dir / "adapter_data"
    adapter = FilesystemArtifactAdapter(adapter_root, allowed_prefixes=("mission-artifacts/", "src/", "docs/"))

    relpath = args.relpath
    content = args.content

    decision = coordinate_once(
        manifest,
        execution_request={
            "capability_id": "filesystem-artifact",
            "requested_permissions": ["repository:write"],
            "requested_effects": [f"relpath:{relpath}", f"utf8:{content}"],
            "estimated_costs": ["one file"],
            "action": "write-text",
        },
        checkpoint_store=store,
    )
    if decision.request is None:
        print(f"Coordination failed: kind={decision.kind} reason={decision.reason}")
        return 1

    receipt = dispatch_once(manifest, decision, adapter)
    if receipt["status"] != "completed":
        print(f"File dispatch failed: {receipt}")
        return 1

    verification = verify_filesystem_receipt(
        receipt["external_receipt_ref"],
        decision.request,
        adapter_root,
    )

    acted = apply_event_data(
        manifest,
        "record_execution_receipt",
        "mission-steward",
        {"receipt": receipt, "request": decision.request},
    )
    acted = apply_event_data(
        acted,
        "record_action",
        "mission-steward",
        {"action_ref": receipt["artifact_refs"][0]},
    )

    observed = apply_event_data(
        acted,
        "record_verifier_result",
        "observer:cli",
        {"result": verification.to_dict()},
    )

    new_chk = store.save(observed)
    print(f"Dispatched file write {relpath}. Mission r{observed.revision} saved to {new_chk.path}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    mission_dir = Path(args.mission_dir).resolve()
    store = FileCheckpointStore(mission_dir / "checkpoints")

    files = list((mission_dir / "checkpoints").glob("*.r*.receipt.json"))
    m_id = files[0].name.split(".r")[0]
    loaded = store.load_latest(m_id)
    if not loaded:
        print("Failed to load mission checkpoint.")
        return 1

    manifest, _ = loaded
    verifying = apply_event_data(manifest, "begin_verification", "mission-steward", {})
    new_chk = store.save(verifying)
    print(f"Mission {verifying.mission_id} transitioned to VERIFYING (r{verifying.revision}). Saved: {new_chk.path}")
    return 0


def cmd_accept(args: argparse.Namespace) -> int:
    mission_dir = Path(args.mission_dir).resolve()
    store = FileCheckpointStore(mission_dir / "checkpoints")

    files = list((mission_dir / "checkpoints").glob("*.r*.receipt.json"))
    m_id = files[0].name.split(".r")[0]
    loaded = store.load_latest(m_id)
    if not loaded:
        print("Failed to load mission checkpoint.")
        return 1

    manifest, _ = loaded
    verdict = {
        "verdict": args.verdict,
        "evidence_refs": manifest.continuity.get("durable_artifacts", []),
        "coverage_limits": ["CLI bridge verification"],
        "separation_assurance": "declared-role-separation",
        "principal_evidence_ref": None,
    }

    try:
        completed = apply_event_data(manifest, "accept", args.acceptor, verdict)
    except TransitionError as err:
        print(f"Acceptance rejected: {err}")
        return 1

    new_chk = store.save(completed)
    print(f"SUCCESS: Mission {completed.mission_id} accepted as COMPLETED (r{completed.revision}) by {args.acceptor}. Saved: {new_chk.path}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="practical-agency",
        description="Practical Agency CLI Bridge for durable mission control.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # init
    p_init = subparsers.add_parser("init", help="Initialize a draft mission")
    p_init.add_argument("--mission-id", required=True, help="Unique mission identifier")
    p_init.add_argument("--intent", required=True, help="Verbatim operator instruction")
    p_init.add_argument("--acceptor", required=True, help="Independent acceptor ref")
    p_init.add_argument("--operator", default="operator:cli", help="Operator ref (default: operator:cli)")
    p_init.add_argument(
        "--proof-relpath",
        default="mission-artifacts/cli-proof.txt",
        help="Artifact relpath whose typed verification is required for completion",
    )
    p_init.add_argument("--out", required=True, help="Output mission directory")

    # status
    p_status = subparsers.add_parser("status", help="Show current mission status")
    p_status.add_argument("--mission-dir", required=True, help="Mission directory")
    p_status.add_argument("--mission-id", help="Mission identifier (optional)")

    # approve
    p_approve = subparsers.add_parser("approve", help="Approve draft mission")
    p_approve.add_argument("--mission-dir", required=True, help="Mission directory")
    p_approve.add_argument("--operator", help="Operator ref (optional; defaults to mission operator)")

    # dispatch-file
    p_file = subparsers.add_parser("dispatch-file", help="Dispatch a file write via filesystem-artifact@1")
    p_file.add_argument("--mission-dir", required=True, help="Mission directory")
    p_file.add_argument("--relpath", required=True, help="Relative path under allowed prefixes")
    p_file.add_argument("--content", required=True, help="UTF-8 text content to write")

    # verify
    p_verify = subparsers.add_parser("verify", help="Begin mission verification")
    p_verify.add_argument("--mission-dir", required=True, help="Mission directory")

    # accept
    p_accept = subparsers.add_parser("accept", help="Accept mission completion via independent acceptor")
    p_accept.add_argument("--mission-dir", required=True, help="Mission directory")
    p_accept.add_argument("--acceptor", required=True, help="Independent acceptor ref")
    p_accept.add_argument("--verdict", default="PASS", help="Acceptance verdict (default: PASS)")

    parsed = parser.parse_args(argv)

    handlers = {
        "init": cmd_init,
        "status": cmd_status,
        "approve": cmd_approve,
        "dispatch-file": cmd_dispatch_file,
        "verify": cmd_verify,
        "accept": cmd_accept,
    }
    return handlers[parsed.subcommand](parsed)


if __name__ == "__main__":
    sys.exit(main())
