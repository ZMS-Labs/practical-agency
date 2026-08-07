#!/usr/bin/env python3
"""Apply the bounded independent-integrity findings to PR #2.

This is a branch-scoped, one-shot migration helper. It writes the reviewed
state-machine implementation, applies structure-aware edits to four adjacent
files, validates its expected markers, and removes itself before the resulting
source commit is created.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE_MACHINE = ROOT / "practical_agency/state_machine.py"
VALIDATION = ROOT / "practical_agency/validation.py"
CHECKPOINT = ROOT / "practical_agency/checkpoint_store.py"
END_TO_END = ROOT / "tests/test_end_to_end_mission.py"
STATE_TESTS = ROOT / "tests/test_state_machine.py"
SELF = Path(__file__)


STATE_MACHINE_SOURCE = '''"""Closed mission lifecycle with independent completion."""
from __future__ import annotations

from typing import Any, Mapping

from .manifest_model import MissionManifest, MissionStatus


class TransitionError(ValueError):
    """Raised when a requested mission transition is not authorized by the lifecycle."""


_ALLOWED: dict[str, set[str]] = {
    "draft": {"active"},
    "active": {"paused", "blocked", "verifying"},
    "paused": {"active", "blocked"},
    "blocked": {"active"},
    "verifying": {"completed", "active", "blocked"},
    "completed": set(),
    "cancelled": set(),
}


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _append_unique(values: list[str], additions: tuple[str, ...] | list[str]) -> None:
    for item in additions:
        if item not in values:
            values.append(item)


def transition(
    manifest: MissionManifest,
    target: str | MissionStatus,
    *,
    actor_ref: str,
    evidence_ref: str | None,
    reason: str | None = None,
    independent: bool = False,
) -> MissionManifest:
    target_value = target.value if isinstance(target, MissionStatus) else target
    current = manifest.state["status"]
    if current in {"completed", "cancelled"}:
        raise TransitionError(f"TERMINAL_STATE: {current} cannot transition")
    if target_value == MissionStatus.CANCELLED.value:
        raise TransitionError(
            "REVOCATION_REQUIRED: cancelled is reachable only through operator revocation"
        )
    if target_value not in _ALLOWED.get(current, set()):
        raise TransitionError(f"ILLEGAL_TRANSITION: {current} -> {target_value}")
    if target_value in {"verifying", "completed"} and manifest.state["blockers"]:
        raise TransitionError(
            "UNRESOLVED_BLOCKERS: exact recorded remediation must complete first"
        )
    if target_value in {"blocked", "paused"} and not reason:
        raise TransitionError(
            "BLOCK_REASON_REQUIRED: name why the mission stops"
            if target_value == "blocked"
            else "PAUSED_REASON_REQUIRED: name why the mission stops"
        )
    if target_value in {"active", "verifying", "completed"} and not evidence_ref:
        raise TransitionError("EVIDENCE_REQUIRED: transition needs a durable evidence reference")

    material_actors = set(manifest.integrity["material_work_actors"])
    if target_value == "verifying":
        artifacts = set(manifest.continuity["durable_artifacts"])
        missing_gates = [
            gate for gate in manifest.integrity["required_gates"] if gate not in artifacts
        ]
        if missing_gates:
            raise TransitionError(
                "REQUIRED_GATES_MISSING: " + ", ".join(sorted(missing_gates))
            )
    if target_value == "completed":
        if not independent or actor_ref in material_actors:
            raise TransitionError(
                "INDEPENDENT_ACCEPTOR_REQUIRED: material work actor cannot accept completion"
            )
        if manifest.integrity["unresolved_verdicts"]:
            raise TransitionError("UNRESOLVED_VERDICTS: completion is not available")

    payload = manifest.to_dict()
    payload["revision"] = manifest.revision + 1
    state = payload["state"]
    state["status"] = target_value

    if target_value == "active":
        state["blockers"] = []
        state["current_frontier"] = ["advance mission"]
        state["next_action"] = "advance mission"
    elif target_value == "paused":
        state["blockers"] = [
            {"kind": "pause", "reason": reason, "evidence_ref": evidence_ref}
        ]
        state["next_action"] = "obtain resume authority"
    elif target_value == "blocked":
        state["blockers"] = [
            {"kind": "block", "reason": reason, "evidence_ref": evidence_ref}
        ]
        state["next_action"] = "resolve blocker"
    elif target_value == "verifying":
        state["blockers"] = []
        state["next_action"] = "obtain independent acceptance"
        artifacts = payload["continuity"]["durable_artifacts"]
        assert isinstance(evidence_ref, str)
        if evidence_ref not in artifacts:
            artifacts.append(evidence_ref)
    elif target_value in {"completed", "cancelled"}:
        state["blockers"] = []
        state["current_frontier"] = []
        state["next_action"] = None

    if target_value == "verifying":
        actors = payload["integrity"]["material_work_actors"]
        if actor_ref not in actors:
            actors.append(actor_ref)

    if target_value == "completed":
        payload["integrity"]["completion_acceptor"] = actor_ref
        payload["integrity"]["acceptance_receipt_ref"] = evidence_ref
    elif current == "completed" or target_value != "verifying":
        if target_value != "completed":
            payload["integrity"]["completion_acceptor"] = None
            payload["integrity"]["acceptance_receipt_ref"] = None

    payload["continuity"]["decisions"].append(
        {
            "kind": "transition",
            "revision": payload["revision"],
            "from": current,
            "to": target_value,
            "actor_ref": actor_ref,
            "evidence_ref": evidence_ref,
            "reason": reason,
            "independent": independent,
        }
    )
    return MissionManifest.from_dict(payload)


def reopen_for_contradiction(
    manifest: MissionManifest,
    *,
    contradiction: Mapping[str, Any],
    observed_by: str,
    evidence_ref: str,
) -> MissionManifest:
    if not evidence_ref:
        raise TransitionError("EVIDENCE_REQUIRED: contradiction needs a durable observation")
    if not _nonempty_string(observed_by):
        raise TransitionError("OBSERVER_REQUIRED: contradiction needs an observing actor")
    subject_ref = contradiction.get("subject_ref")
    if not _nonempty_string(subject_ref):
        raise TransitionError(
            "CONTRADICTION_SUBJECT_REQUIRED: contradiction needs a stable subject_ref"
        )

    payload = manifest.to_dict()
    payload["revision"] = manifest.revision + 1
    contradiction_record = {
        **dict(contradiction),
        "subject_ref": subject_ref,
        "observed_by": observed_by,
        "evidence_ref": evidence_ref,
        "revision": payload["revision"],
    }
    payload["truth"]["contradictions"].append(contradiction_record)

    invalidated_refs = set(payload["integrity"]["required_gates"])
    acceptance_ref = payload["integrity"]["acceptance_receipt_ref"]
    if isinstance(acceptance_ref, str) and acceptance_ref:
        invalidated_refs.add(acceptance_ref)
    for decision in payload["continuity"]["decisions"]:
        if (
            isinstance(decision, Mapping)
            and decision.get("kind") == "transition"
            and decision.get("to") == "verifying"
        ):
            proof_ref = decision.get("evidence_ref")
            if isinstance(proof_ref, str) and proof_ref:
                invalidated_refs.add(proof_ref)
    payload["continuity"]["durable_artifacts"] = [
        ref
        for ref in payload["continuity"]["durable_artifacts"]
        if ref not in invalidated_refs
    ]
    if evidence_ref not in payload["continuity"]["durable_artifacts"]:
        payload["continuity"]["durable_artifacts"].append(evidence_ref)

    blocker = {
        "code": "RECONCILIATION_CONTRADICTED",
        "subject_ref": subject_ref,
        "evidence_ref": evidence_ref,
    }
    verdict = {
        "verdict": "CONTRADICTED",
        "subject_ref": subject_ref,
        "evidence_ref": evidence_ref,
    }
    payload["state"]["status"] = "active"
    payload["state"]["blockers"].append(blocker)
    payload["state"]["current_frontier"] = ["reconcile live-state contradiction"]
    payload["state"]["next_action"] = "reconcile live-state contradiction"
    payload["integrity"]["unresolved_verdicts"].append(verdict)
    payload["integrity"]["completion_acceptor"] = None
    payload["integrity"]["acceptance_receipt_ref"] = None
    payload["continuity"]["decisions"].append(
        {
            "kind": "reopen-contradiction",
            "revision": payload["revision"],
            "actor_ref": observed_by,
            "subject_ref": subject_ref,
            "evidence_ref": evidence_ref,
            "invalidated_refs": sorted(invalidated_refs),
        }
    )
    return MissionManifest.from_dict(payload)


def record_reconciliation_observation(
    manifest: MissionManifest,
    *,
    subject_ref: str,
    observed_by: str,
    evidence_ref: str,
    restored_gate_refs: tuple[str, ...] | list[str] = (),
) -> MissionManifest:
    if manifest.state["status"] not in {"active", "blocked"}:
        raise TransitionError(
            "RECONCILIATION_STATE_REQUIRED: mission must be active or blocked"
        )
    if not _nonempty_string(subject_ref):
        raise TransitionError("RECONCILIATION_SUBJECT_REQUIRED: subject_ref is required")
    if not _nonempty_string(observed_by):
        raise TransitionError("OBSERVER_REQUIRED: reconciliation needs an observing actor")
    if not _nonempty_string(evidence_ref):
        raise TransitionError("EVIDENCE_REQUIRED: reconciliation needs a durable observation")
    if not isinstance(restored_gate_refs, (tuple, list)) or any(
        not _nonempty_string(ref) for ref in restored_gate_refs
    ):
        raise TransitionError(
            "INVALID_RESTORED_GATES: restored_gate_refs must contain non-empty strings"
        )
    required_gates = set(manifest.integrity["required_gates"])
    unknown_gates = sorted(set(restored_gate_refs) - required_gates)
    if unknown_gates:
        raise TransitionError("UNKNOWN_GATE_REFERENCE: " + ", ".join(unknown_gates))

    matching_blocker = any(
        isinstance(item, Mapping)
        and item.get("code") == "RECONCILIATION_CONTRADICTED"
        and item.get("subject_ref") == subject_ref
        for item in manifest.state["blockers"]
    )
    matching_verdict = any(
        isinstance(item, Mapping)
        and item.get("verdict") == "CONTRADICTED"
        and item.get("subject_ref") == subject_ref
        for item in manifest.integrity["unresolved_verdicts"]
    )
    if not matching_blocker or not matching_verdict:
        raise TransitionError(
            "RECONCILIATION_TARGET_NOT_FOUND: subject has no matching blocker and verdict"
        )

    payload = manifest.to_dict()
    payload["revision"] = manifest.revision + 1
    payload["truth"]["contradictions"] = [
        item
        for item in payload["truth"]["contradictions"]
        if not (isinstance(item, Mapping) and item.get("subject_ref") == subject_ref)
    ]
    payload["truth"]["verified_facts"].append(
        {
            "kind": "reconciliation-observation",
            "subject_ref": subject_ref,
            "observed_by": observed_by,
            "evidence_ref": evidence_ref,
            "revision": payload["revision"],
        }
    )
    payload["state"]["blockers"] = [
        item
        for item in payload["state"]["blockers"]
        if not (
            isinstance(item, Mapping)
            and item.get("code") == "RECONCILIATION_CONTRADICTED"
            and item.get("subject_ref") == subject_ref
        )
    ]
    payload["integrity"]["unresolved_verdicts"] = [
        item
        for item in payload["integrity"]["unresolved_verdicts"]
        if not (
            isinstance(item, Mapping)
            and item.get("verdict") == "CONTRADICTED"
            and item.get("subject_ref") == subject_ref
        )
    ]
    artifacts = payload["continuity"]["durable_artifacts"]
    _append_unique(artifacts, [evidence_ref, *restored_gate_refs])

    if payload["state"]["blockers"]:
        payload["state"]["status"] = "blocked"
        payload["state"]["current_frontier"] = ["resolve remaining blockers"]
        payload["state"]["next_action"] = "resolve remaining blockers"
    else:
        payload["state"]["status"] = "active"
        payload["state"]["current_frontier"] = ["prepare verification evidence"]
        payload["state"]["next_action"] = "prepare verification evidence"

    payload["continuity"]["decisions"].append(
        {
            "kind": "reconciliation-observation",
            "revision": payload["revision"],
            "actor_ref": observed_by,
            "subject_ref": subject_ref,
            "evidence_ref": evidence_ref,
            "restored_gate_refs": list(restored_gate_refs),
        }
    )
    return MissionManifest.from_dict(payload)


def record_acceptance_verdict(
    manifest: MissionManifest,
    *,
    verdict: str,
    actor_ref: str,
    evidence_refs: tuple[str, ...] | list[str],
    coverage_limits: tuple[str, ...] | list[str] = (),
    reason: str | None = None,
) -> MissionManifest:
    if manifest.state["status"] != "verifying":
        raise TransitionError(
            "VERIFYING_STATE_REQUIRED: acceptance verdict requires a verifying mission"
        )
    normalized_verdict = verdict.upper() if isinstance(verdict, str) else ""
    if normalized_verdict not in {"PASS", "FAIL", "INCONCLUSIVE"}:
        raise TransitionError("INVALID_ACCEPTANCE_VERDICT: use PASS, FAIL, or INCONCLUSIVE")
    if not _nonempty_string(actor_ref):
        raise TransitionError("ACCEPTOR_REQUIRED: acceptance actor is required")
    if actor_ref in set(manifest.integrity["material_work_actors"]):
        raise TransitionError(
            "INDEPENDENT_ACCEPTOR_REQUIRED: material work actor cannot issue a verdict"
        )
    if not isinstance(evidence_refs, (tuple, list)) or not evidence_refs or any(
        not _nonempty_string(ref) for ref in evidence_refs
    ):
        raise TransitionError(
            "ACCEPTANCE_EVIDENCE_REQUIRED: verdict needs durable evidence references"
        )
    if not isinstance(coverage_limits, (tuple, list)) or any(
        not _nonempty_string(limit) for limit in coverage_limits
    ):
        raise TransitionError(
            "INVALID_COVERAGE_LIMITS: coverage_limits must contain non-empty strings"
        )
    if normalized_verdict in {"FAIL", "INCONCLUSIVE"} and not _nonempty_string(reason):
        raise TransitionError(
            "ACCEPTANCE_REASON_REQUIRED: non-pass verdict must explain the finding"
        )

    if normalized_verdict == "PASS":
        completed = transition(
            manifest,
            "completed",
            actor_ref=actor_ref,
            evidence_ref=evidence_refs[0],
            reason=reason or "independent pass",
            independent=True,
        )
        payload = completed.to_dict()
        _append_unique(payload["continuity"]["durable_artifacts"], list(evidence_refs))
        payload["continuity"]["decisions"].append(
            {
                "kind": "acceptance-verdict",
                "revision": payload["revision"],
                "verdict": normalized_verdict,
                "actor_ref": actor_ref,
                "evidence_refs": list(evidence_refs),
                "coverage_limits": list(coverage_limits),
                "reason": reason or "independent pass",
            }
        )
        return MissionManifest.from_dict(payload)

    payload = manifest.to_dict()
    payload["revision"] = manifest.revision + 1
    next_action = f"address acceptance verdict: {normalized_verdict}"
    subject_ref = f"mission:{manifest.mission_id}"
    blocker = {
        "code": f"ACCEPTANCE_{normalized_verdict}",
        "subject_ref": subject_ref,
        "evidence_ref": evidence_refs[0],
        "reason": reason,
    }
    unresolved = {
        "verdict": normalized_verdict,
        "subject_ref": subject_ref,
        "actor_ref": actor_ref,
        "evidence_refs": list(evidence_refs),
        "coverage_limits": list(coverage_limits),
        "reason": reason,
        "revision": payload["revision"],
    }
    payload["state"]["status"] = "active" if normalized_verdict == "FAIL" else "blocked"
    payload["state"]["blockers"].append(blocker)
    payload["state"]["current_frontier"] = [next_action]
    payload["state"]["next_action"] = next_action
    payload["integrity"]["unresolved_verdicts"].append(unresolved)
    payload["integrity"]["completion_acceptor"] = None
    payload["integrity"]["acceptance_receipt_ref"] = None
    _append_unique(payload["continuity"]["durable_artifacts"], list(evidence_refs))
    payload["continuity"]["decisions"].append(
        {
            "kind": "acceptance-verdict",
            "revision": payload["revision"],
            "verdict": normalized_verdict,
            "actor_ref": actor_ref,
            "evidence_refs": list(evidence_refs),
            "coverage_limits": list(coverage_limits),
            "reason": reason,
        }
    )
    return MissionManifest.from_dict(payload)
'''


def require_once(text: str, needle: str, *, path: Path) -> int:
    count = text.count(needle)
    if count != 1:
        raise SystemExit(f"{path}: expected one occurrence, found {count}: {needle!r}")
    return text.index(needle)


def patch_validation() -> None:
    text = VALIDATION.read_text(encoding="utf-8")
    marker = "\ndef _nullable_string(value: Any) -> bool:\n"
    position = require_once(text, marker, path=VALIDATION)
    object_helper = '''

def _object_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, Mapping) for item in value)
'''
    text = text[:position] + object_helper + text[position:]

    state_marker = '\n    state = payload.get("state")\n'
    position = require_once(text, state_marker, path=VALIDATION)
    object_checks = '''
    object_list_fields = {
        "truth": ("verified_facts", "assumptions", "contradictions", "unknowns"),
        "capabilities": ("available", "invoked", "unavailable", "degraded"),
        "continuity": ("decisions", "external_handoffs", "watch_commissions"),
    }
    for section, fields in object_list_fields.items():
        value = payload.get(section)
        if not isinstance(value, Mapping):
            continue
        for field in fields:
            if not _object_list(value.get(field)):
                errors.append(
                    f"INVALID_OBJECT_LIST: {section}.{field} must contain objects"
                )
'''
    text = text[:position] + object_checks + text[position:]

    old = '''        for field in ("completed_actions", "blockers"):
            if not _list(state.get(field)):
                errors.append(f"INVALID_STATE_LIST: state.{field} must be a list")'''
    new = '''        for field in ("completed_actions", "blockers"):
            if not _object_list(state.get(field)):
                errors.append(
                    f"INVALID_OBJECT_LIST: state.{field} must contain objects"
                )'''
    require_once(text, old, path=VALIDATION)
    text = text.replace(old, new, 1)

    old = '''        if not _list(integrity.get("unresolved_verdicts")):
            errors.append(
                "INVALID_INTEGRITY_LIST: integrity.unresolved_verdicts must be a list"
            )'''
    new = '''        if not _object_list(integrity.get("unresolved_verdicts")):
            errors.append(
                "INVALID_OBJECT_LIST: integrity.unresolved_verdicts must contain objects"
            )'''
    require_once(text, old, path=VALIDATION)
    VALIDATION.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_checkpoint_store() -> None:
    text = CHECKPOINT.read_text(encoding="utf-8")
    old = '''        pointer_path = mission_dir / "LATEST"
        if not pointer_path.exists():
            return None'''
    new = '''        pointer_path = mission_dir / "LATEST"
        if pointer_path.is_symlink():
            raise CheckpointError(
                "CHECKPOINT_SYMLINK_FORBIDDEN: LATEST pointer cannot be a symlink"
            )
        if not pointer_path.exists():
            return None'''
    require_once(text, old, path=CHECKPOINT)
    text = text.replace(old, new, 1)

    old = '''        path = mission_dir / pointer["filename"]
        try:
            data = path.read_bytes()'''
    new = '''        path = mission_dir / pointer["filename"]
        if path.is_symlink():
            raise CheckpointError(
                "CHECKPOINT_SYMLINK_FORBIDDEN: checkpoint content cannot be a symlink"
            )
        try:
            data = path.read_bytes()'''
    require_once(text, old, path=CHECKPOINT)
    CHECKPOINT.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_end_to_end() -> None:
    text = END_TO_END.read_text(encoding="utf-8")
    old = "from practical_agency.state_machine import TransitionError, reopen_for_contradiction, transition"
    new = '''from practical_agency.state_machine import (
    TransitionError,
    record_reconciliation_observation,
    reopen_for_contradiction,
    transition,
)'''
    require_once(text, old, path=END_TO_END)
    text = text.replace(old, new, 1)

    old = '''                contradiction={
                    "kind": "artifact-hash-mismatch",
                    "expected": expected_first_hash,
                    "observed": live_hash,
                },'''
    new = '''                contradiction={
                    "subject_ref": "artifact://output.txt",
                    "kind": "artifact-hash-mismatch",
                    "expected": expected_first_hash,
                    "observed": live_hash,
                },'''
    require_once(text, old, path=END_TO_END)
    text = text.replace(old, new, 1)

    old = '                action("repair", "repair example artifact"),'
    new = '                action("repair", "reconcile live-state contradiction"),'
    require_once(text, old, path=END_TO_END)
    text = text.replace(old, new, 1)

    old = '''            expected_final_hash = hashlib.sha256(b"corrected\\n").hexdigest()
            self.assertEqual(correction_receipt["observed_effects"][0]["sha256"], expected_final_hash)

            verifying = coordinator.propose_verification(
                corrected,'''
    new = '''            expected_final_hash = hashlib.sha256(b"corrected\\n").hexdigest()
            self.assertEqual(correction_receipt["observed_effects"][0]["sha256"], expected_final_hash)

            reconciled = record_reconciliation_observation(
                corrected,
                subject_ref="artifact://output.txt",
                observed_by="observer:test",
                evidence_ref=f"artifact://output.txt@sha256:{expected_final_hash}",
            )
            store.save(reconciled, events=[{"kind": "live-state-reconciled"}])

            verifying = coordinator.propose_verification(
                reconciled,'''
    require_once(text, old, path=END_TO_END)
    END_TO_END.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_state_tests() -> None:
    text = STATE_TESTS.read_text(encoding="utf-8")
    old = '            contradiction={"claim": "artifact hash", "observed": "changed"},'
    new = '''            contradiction={
                "subject_ref": "artifact://canonical",
                "claim": "artifact hash",
                "observed": "changed",
            },'''
    require_once(text, old, path=STATE_TESTS)
    text = text.replace(old, new, 1)

    old = '''        self.assertTrue(reopened.truth["contradictions"])
        self.assertIsNone(reopened.integrity["completion_acceptor"])'''
    new = '''        self.assertTrue(reopened.truth["contradictions"])
        self.assertTrue(reopened.state["blockers"])
        self.assertTrue(reopened.integrity["unresolved_verdicts"])
        self.assertIsNone(reopened.integrity["completion_acceptor"])'''
    require_once(text, old, path=STATE_TESTS)
    STATE_TESTS.write_text(text.replace(old, new, 1), encoding="utf-8")


def verify_markers() -> None:
    required = {
        STATE_MACHINE: (
            "def record_reconciliation_observation(",
            "def record_acceptance_verdict(",
            "REQUIRED_GATES_MISSING",
            "RECONCILIATION_CONTRADICTED",
        ),
        VALIDATION: (
            "def _object_list(",
            "truth.verified_facts",
            "state.{field}",
            "integrity.unresolved_verdicts",
        ),
        CHECKPOINT: (
            "LATEST pointer cannot be a symlink",
            "checkpoint content cannot be a symlink",
        ),
        END_TO_END: (
            "record_reconciliation_observation",
            '"subject_ref": "artifact://output.txt"',
            'action("repair", "reconcile live-state contradiction")',
        ),
        STATE_TESTS: (
            '"subject_ref": "artifact://canonical"',
            'reopened.integrity["unresolved_verdicts"]',
        ),
    }
    for path, markers in required.items():
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                raise SystemExit(f"{path}: required marker missing: {marker!r}")


def main() -> int:
    STATE_MACHINE.write_text(STATE_MACHINE_SOURCE, encoding="utf-8")
    patch_validation()
    patch_checkpoint_store()
    patch_end_to_end()
    patch_state_tests()
    verify_markers()
    SELF.unlink()
    print("independent integrity findings applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
