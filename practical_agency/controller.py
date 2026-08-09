"""Pathless manifest engagement over the deterministic mission kernel."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from practical_agency.checkpoint_store import (
    FileCheckpointStore,
    ReconciliationFinding,
    apply_reconciliation_findings,
)
from practical_agency.coordinator import CoordinationError, coordinate_once, dispatch_once
from practical_agency.filesystem_artifact import (
    FilesystemArtifactAdapter,
    FilesystemArtifactError,
    inspect_filesystem_receipt,
    verify_filesystem_receipt,
)
from practical_agency.governed_workspace import (
    GovernedWorkspaceError,
    capture_baseline,
    find_unreceipted_drift,
)
from practical_agency.host_evidence import (
    HostBinding,
    HostEvidenceError,
    validate_host_bindings,
)
from practical_agency.manifest_model import MissionManifest
from practical_agency.mission_os import propose_frontier_patch
from practical_agency.mission_repository import (
    DiscoveredMission,
    MissionDiscoveryError,
    discover_active_mission,
)
from practical_agency.state_machine import (
    MISSION_STEWARD_REF,
    TransitionError,
    apply_event_data,
)


class ControllerError(RuntimeError):
    """Named refusal from the operator-facing manifest controller."""


_DEFINITION_FIELDS = (
    "instruction",
    "desired_state",
    "governed_artifacts",
    "permissions",
    "protected_state",
    "acceptable_costs",
    "escalation_required_for",
    "stop_conditions",
    "completion_acceptor",
)
_LIST_FIELDS = (
    "permissions",
    "protected_state",
    "acceptable_costs",
    "escalation_required_for",
    "stop_conditions",
)


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _definition_record(manifest: MissionManifest) -> Mapping[str, Any]:
    records = [
        item
        for item in manifest.continuity.get("decisions", [])
        if isinstance(item, Mapping) and item.get("kind") == "manifest-definition"
    ]
    if len(records) != 1:
        raise ControllerError("AUTHORITY_CONTRACT_INVALID")
    record = records[0]
    if set(record) != {
        "kind",
        "authority_contract",
        "authority_contract_sha256",
    }:
        raise ControllerError("AUTHORITY_CONTRACT_INVALID")
    contract = record.get("authority_contract")
    digest = record.get("authority_contract_sha256")
    if (
        not isinstance(contract, Mapping)
        or not isinstance(digest, str)
        or _canonical_sha256(contract) != digest
    ):
        raise ControllerError("AUTHORITY_CONTRACT_INVALID")
    return record


def _active_milestone_record(manifest: MissionManifest) -> Mapping[str, Any] | None:
    decisions = manifest.continuity.get("decisions", [])
    accepted = {
        item.get("authority_contract_sha256")
        for item in decisions
        if isinstance(item, Mapping)
        and item.get("kind") == "manifest-milestone-acceptance"
    }
    active = [
        item
        for item in decisions
        if isinstance(item, Mapping)
        and item.get("kind") == "manifest-milestone-definition"
        and item.get("authority_contract_sha256") not in accepted
    ]
    if len(active) > 1:
        raise ControllerError("MANIFEST_MILESTONE_AMBIGUOUS")
    if not active:
        return None
    record = active[0]
    if set(record) != {
        "kind",
        "authority_contract",
        "authority_contract_sha256",
        "governed_workspace",
        "return_frontier",
        "return_next_action",
    }:
        raise ControllerError("AUTHORITY_CONTRACT_INVALID")
    contract = record.get("authority_contract")
    digest = record.get("authority_contract_sha256")
    if (
        not isinstance(contract, Mapping)
        or not isinstance(digest, str)
        or _canonical_sha256(contract) != digest
    ):
        raise ControllerError("AUTHORITY_CONTRACT_INVALID")
    return record


def _pending_milestone_proposal(
    manifest: MissionManifest,
) -> Mapping[str, Any] | None:
    decisions = manifest.continuity.get("decisions", [])
    authorized = {
        item.get("authority_contract_sha256")
        for item in decisions
        if isinstance(item, Mapping)
        and item.get("kind") == "manifest-milestone-definition"
    }
    pending = [
        item
        for item in decisions
        if isinstance(item, Mapping)
        and item.get("kind") == "manifest-milestone-proposal"
        and item.get("authority_contract_sha256") not in authorized
    ]
    if len(pending) > 1:
        raise ControllerError("MANIFEST_MILESTONE_AMBIGUOUS")
    if not pending:
        return None
    record = pending[0]
    contract = record.get("authority_contract")
    digest = record.get("authority_contract_sha256")
    if (
        not isinstance(contract, Mapping)
        or not isinstance(digest, str)
        or _canonical_sha256(contract) != digest
    ):
        raise ControllerError("AUTHORITY_CONTRACT_INVALID")
    return record


def _durable_definition(manifest: MissionManifest) -> Mapping[str, Any]:
    standard_records = [
        item
        for item in manifest.continuity.get("decisions", [])
        if isinstance(item, Mapping) and item.get("kind") == "manifest-definition"
    ]
    if standard_records:
        record = _definition_record(manifest)
    else:
        record = _active_milestone_record(manifest)
        if record is None:
            raise ControllerError("AUTHORITY_CONTRACT_INVALID")
    contract = record["authority_contract"]
    definition = contract.get("definition") if isinstance(contract, Mapping) else None
    if not isinstance(definition, Mapping):
        raise ControllerError("AUTHORITY_CONTRACT_INVALID")
    return definition


def _latest_receipt_for_path(
    manifest: MissionManifest, relpath: str
) -> Mapping[str, Any] | None:
    proof_ref = f"file:{relpath}"
    for receipt in reversed(manifest.continuity.get("execution_receipts", [])):
        if (
            isinstance(receipt, Mapping)
            and receipt.get("status") == "completed"
            and proof_ref in receipt.get("artifact_refs", [])
            and isinstance(receipt.get("request"), Mapping)
            and isinstance(receipt.get("external_receipt_ref"), str)
        ):
            return receipt
    return None


def _result_recorded(manifest: MissionManifest, result_ref: str) -> bool:
    return any(
        isinstance(item, Mapping) and item.get("result_ref") == result_ref
        for item in manifest.continuity.get("verifier_results", [])
    )


def _request_expected_before(state: Mapping[str, Any]) -> dict[str, Any]:
    if state.get("kind") == "absent":
        return {"kind": "absent"}
    digest = state.get("sha256")
    if state.get("kind") != "regular-file" or not isinstance(digest, str):
        raise ControllerError("GOVERNED_WORKSPACE_INVALID")
    return {"kind": "regular-file", "sha256": digest}


def _status_summary(manifest: MissionManifest) -> dict[str, Any]:
    governed = manifest.continuity.get("governed_workspace")
    governed_paths = (
        list(governed.get("paths", [])) if isinstance(governed, Mapping) else []
    )
    return {
        "mission_id": manifest.mission_id,
        "revision": manifest.revision,
        "mission_status": manifest.state["status"],
        "authority_scope": {
            "permissions": list(manifest.authority["permissions"]),
            "protected_state": list(manifest.authority["protected_state"]),
            "acceptable_costs": list(manifest.authority["acceptable_costs"]),
            "escalation_required_for": list(
                manifest.authority["escalation_required_for"]
            ),
            "governed_paths": governed_paths,
        },
        "frontier": list(manifest.state["current_frontier"]),
        "next_action": manifest.state["next_action"],
        "unresolved_verdicts": list(manifest.integrity["unresolved_verdicts"]),
    }


class ManifestController:
    """Compose pathless mission operations without exposing storage identity."""

    def __init__(self, *, plugin_root: Path | str) -> None:
        self.plugin_root = Path(plugin_root).resolve()
        self.process_instance_id = f"controller-{uuid4().hex}"

    def _binding(
        self,
        operation: str,
        context_ref: object,
        gate_ref: object,
    ) -> HostBinding:
        if not _nonempty(context_ref) or not _nonempty(gate_ref):
            raise ControllerError("HOST_GATE_UNAVAILABLE")
        try:
            return validate_host_bindings(
                context_ref=str(context_ref),
                gate_ref=str(gate_ref),
                expected_tool_name=f"mcp__practical_agency__{operation}",
                plugin_root=self.plugin_root,
            )
        except HostEvidenceError as error:
            raise ControllerError(str(error)) from error

    @staticmethod
    def _discover(workspace: Path) -> DiscoveredMission:
        try:
            return discover_active_mission(workspace)
        except MissionDiscoveryError as error:
            raise ControllerError(str(error)) from error

    @staticmethod
    def _store(workspace: Path, mission_id: str) -> FileCheckpointStore:
        return FileCheckpointStore(
            workspace / "missions" / mission_id / "checkpoints"
        )

    def manifest_engage(
        self,
        *,
        _host_context_ref: str | None = None,
        _host_gate_ref: str | None = None,
    ) -> dict[str, Any]:
        binding = self._binding(
            "manifest_engage", _host_context_ref, _host_gate_ref
        )
        try:
            discovered = discover_active_mission(binding.workspace_root)
        except MissionDiscoveryError as error:
            if str(error) == "ACTIVE_MISSION_NOT_FOUND":
                return {
                    "status": "MISSION_DEFINITION_REQUIRED",
                    "required_fields": list(_DEFINITION_FIELDS),
                    "process_instance_id": self.process_instance_id,
                }
            raise ControllerError(str(error)) from error

        manifest = discovered.manifest
        store = self._store(binding.workspace_root, manifest.mission_id)
        try:
            definition = _durable_definition(manifest)
        except ControllerError:
            definition = {}
        artifacts = definition.get("governed_artifacts")
        if isinstance(artifacts, list):
            for artifact in artifacts:
                relpath = artifact.get("path") if isinstance(artifact, Mapping) else None
                if not isinstance(relpath, str):
                    continue
                receipt = _latest_receipt_for_path(manifest, relpath)
                if receipt is None:
                    continue
                try:
                    observation = inspect_filesystem_receipt(
                        str(receipt["external_receipt_ref"]),
                        receipt["request"],
                        binding.workspace_root,
                        receipt_root=discovered.mission_dir / "receipts",
                    )
                except FilesystemArtifactError as error:
                    raise ControllerError(str(error)) from error
                if observation.status != "verified":
                    if not _result_recorded(manifest, observation.result_ref):
                        manifest = apply_event_data(
                            manifest,
                            "record_verifier_result",
                            "observer:artifact-verifier",
                            {"result": observation.to_dict()},
                        )
                    checkpoint = store.save(manifest)
                    return {
                        "status": "engaged",
                        **_status_summary(manifest),
                        "mission_id": manifest.mission_id,
                        "revision": manifest.revision,
                        "mission_status": manifest.state["status"],
                        "next_action": manifest.state["next_action"],
                        "reason_code": observation.reason_code,
                        "checkpoint_ref": checkpoint.path,
                        "checkpoint_sha256": checkpoint.sha256,
                        "drift_findings": [
                            {
                                "path": relpath,
                                "reason_code": observation.reason_code,
                            }
                        ],
                        "process_instance_id": self.process_instance_id,
                    }
        governed = manifest.continuity.get("governed_workspace")
        try:
            findings = (
                find_unreceipted_drift(
                    binding.workspace_root,
                    governed,
                    manifest.continuity.get("execution_receipts", []),
                )
                if isinstance(governed, Mapping)
                else []
            )
        except GovernedWorkspaceError as error:
            raise ControllerError(str(error)) from error
        if findings and manifest.state.get("status") != "draft":
            live = capture_baseline(
                binding.workspace_root, [item.path for item in findings]
            )
            baseline_by_path = {
                item["path"]: item
                for item in governed["baseline"]
                if isinstance(item, Mapping)
            }
            live_by_path = {
                item["path"]: item
                for item in live["baseline"]
                if isinstance(item, Mapping)
            }
            manifest = apply_reconciliation_findings(
                manifest,
                [
                    ReconciliationFinding(
                        subject_ref=f"file:{item.path}",
                        checkpoint_value=baseline_by_path[item.path],
                        live_value=live_by_path[item.path],
                        classification="CONTRADICTED",
                    )
                    for item in findings
                ],
            )
            checkpoint = store.save(manifest)
            return {
                "status": "engaged",
                **_status_summary(manifest),
                "mission_id": manifest.mission_id,
                "revision": manifest.revision,
                "mission_status": manifest.state["status"],
                "next_action": manifest.state["next_action"],
                "reason_code": "UNRECEIPTED_WORKSPACE_DRIFT",
                "checkpoint_ref": checkpoint.path,
                "checkpoint_sha256": checkpoint.sha256,
                "drift_findings": [
                    {"path": item.path, "reason_code": item.reason_code}
                    for item in findings
                ],
                "process_instance_id": self.process_instance_id,
            }
        return {
            "status": "engaged",
            **_status_summary(manifest),
            "mission_id": manifest.mission_id,
            "revision": manifest.revision,
            "mission_status": manifest.state["status"],
            "next_action": manifest.state["next_action"],
            "checkpoint_ref": discovered.receipt.path,
            "checkpoint_sha256": discovered.receipt.sha256,
            "drift_findings": [
                {"path": item.path, "reason_code": item.reason_code}
                for item in findings
            ],
            "process_instance_id": self.process_instance_id,
        }

    def _normalize_definition(
        self, workspace: Path, definition: object
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not isinstance(definition, Mapping) or set(definition) != set(
            _DEFINITION_FIELDS
        ):
            raise ControllerError("MISSION_DEFINITION_INVALID")
        if not _nonempty(definition.get("instruction")):
            raise ControllerError("MISSION_DEFINITION_INVALID")
        if not _nonempty(definition.get("desired_state")):
            raise ControllerError("MISSION_DEFINITION_INVALID")
        if not _nonempty(definition.get("completion_acceptor")):
            raise ControllerError("MISSION_DEFINITION_INVALID")
        for field in _LIST_FIELDS:
            value = definition.get(field)
            if (
                not isinstance(value, list)
                or not value
                or not all(_nonempty(item) for item in value)
            ):
                raise ControllerError("MISSION_DEFINITION_INVALID")

        raw_artifacts = definition.get("governed_artifacts")
        if not isinstance(raw_artifacts, list) or not raw_artifacts:
            raise ControllerError("MISSION_DEFINITION_INVALID")
        artifacts: list[dict[str, str]] = []
        for raw in raw_artifacts:
            if (
                not isinstance(raw, Mapping)
                or set(raw) != {"path", "content"}
                or not _nonempty(raw.get("path"))
                or not isinstance(raw.get("content"), str)
            ):
                raise ControllerError("MISSION_DEFINITION_INVALID")
            artifacts.append(
                {"path": str(raw["path"]), "content": str(raw["content"])}
            )
        try:
            baseline = capture_baseline(
                workspace, [artifact["path"] for artifact in artifacts]
            )
        except GovernedWorkspaceError as error:
            raise ControllerError(str(error)) from error
        normalized_paths = baseline["paths"]
        for artifact, normalized_path in zip(
            artifacts, normalized_paths, strict=True
        ):
            artifact["path"] = normalized_path

        normalized = {
            "instruction": definition["instruction"],
            "desired_state": definition["desired_state"],
            "governed_artifacts": artifacts,
            **{field: list(definition[field]) for field in _LIST_FIELDS},
            "completion_acceptor": definition["completion_acceptor"],
        }
        return normalized, baseline

    def manifest_define(
        self,
        *,
        definition: Mapping[str, Any],
        _host_context_ref: str | None = None,
        _host_gate_ref: str | None = None,
    ) -> dict[str, Any]:
        binding = self._binding(
            "manifest_define", _host_context_ref, _host_gate_ref
        )
        discovered: DiscoveredMission | None = None
        try:
            discovered = discover_active_mission(binding.workspace_root)
        except MissionDiscoveryError as error:
            if str(error) != "ACTIVE_MISSION_NOT_FOUND":
                raise ControllerError(str(error)) from error

        normalized, baseline = self._normalize_definition(
            binding.workspace_root, definition
        )
        if discovered is not None:
            manifest = discovered.manifest
            if manifest.state.get("status") != "active":
                raise ControllerError(
                    f"MISSION_DEFINITION_ALREADY_EXISTS:{manifest.mission_id}"
                )
            standard_records = [
                item
                for item in manifest.continuity.get("decisions", [])
                if isinstance(item, Mapping)
                and item.get("kind") == "manifest-definition"
            ]
            if (
                standard_records
                or _active_milestone_record(manifest) is not None
                or _pending_milestone_proposal(manifest) is not None
            ):
                raise ControllerError(
                    f"MISSION_DEFINITION_ALREADY_EXISTS:{manifest.mission_id}"
                )
            contract = {
                "schema": "manifest-authority-contract@1",
                "mission_id": manifest.mission_id,
                "definition": deepcopy(normalized),
            }
            contract_hash = _canonical_sha256(contract)
            try:
                proposed = apply_event_data(
                    manifest,
                    "propose_manifest_milestone",
                    MISSION_STEWARD_REF,
                    {
                        "authority_contract": contract,
                        "authority_contract_sha256": contract_hash,
                        "governed_workspace": baseline,
                    },
                )
            except TransitionError as error:
                raise ControllerError(str(error)) from error
            receipt = self._store(
                binding.workspace_root, proposed.mission_id
            ).save(proposed)
            return {
                "status": "definition-proposed",
                **_status_summary(proposed),
                "mission_id": proposed.mission_id,
                "revision": proposed.revision,
                "mission_status": proposed.state["status"],
                "authority_contract_sha256": contract_hash,
                "approval_phrase": f"approve manifest {contract_hash}",
                "checkpoint_ref": receipt.path,
                "checkpoint_sha256": receipt.sha256,
                "process_instance_id": self.process_instance_id,
            }

        nonce_sha256 = _sha256_text(binding.context.context_nonce)
        mission_id = f"manifest-{nonce_sha256[:24]}"
        mission_dir = binding.workspace_root / "missions" / mission_id
        if mission_dir.is_symlink() or mission_dir.exists():
            raise ControllerError("MISSION_ID_COLLISION")

        contract = {
            "schema": "manifest-authority-contract@1",
            "mission_id": mission_id,
            "definition": deepcopy(normalized),
        }
        contract_hash = _canonical_sha256(contract)
        proof_refs = [
            f"file:{artifact['path']}"
            for artifact in normalized["governed_artifacts"]
        ]
        manifest = MissionManifest.from_dict(
            {
                "schema": "mission-manifest@1",
                "mission_id": mission_id,
                "revision": 1,
                "authority": {
                    "operator_ref": f"operator:host-context:{nonce_sha256[:16]}",
                    "instruction": normalized["instruction"],
                    "amendments": [],
                    "permissions": normalized["permissions"],
                    "protected_state": normalized["protected_state"],
                    "acceptable_costs": normalized["acceptable_costs"],
                    "escalation_required_for": normalized[
                        "escalation_required_for"
                    ],
                    "revoked": False,
                    "revocation_reason": None,
                },
                "outcome": {
                    "desired_state": normalized["desired_state"],
                    "completion_proof": proof_refs,
                    "integrity_guards": [
                        "typed verifier result binds live bytes to the execution receipt"
                    ],
                    "scope_proof": [
                        "only normalized governed artifact paths may be mutated"
                    ],
                    "stop_conditions": normalized["stop_conditions"],
                },
                "truth": {
                    "subject_refs": proof_refs,
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
                    "decisions": [
                        {
                            "kind": "manifest-definition",
                            "authority_contract": contract,
                            "authority_contract_sha256": contract_hash,
                        }
                    ],
                    "external_handoffs": [],
                    "watch_commissions": [],
                    "deferred_interests": [],
                    "processed_event_ids": [],
                    "execution_receipts": [],
                    "verifier_results": [],
                    "governed_workspace": baseline,
                },
                "integrity": {
                    "actor_may_self_accept": False,
                    "required_gates": [],
                    "unresolved_verdicts": [],
                    "completion_acceptor": normalized["completion_acceptor"],
                },
            }
        )
        receipt = self._store(binding.workspace_root, mission_id).save(manifest)
        return {
            "status": "definition-created",
            **_status_summary(manifest),
            "mission_id": mission_id,
            "revision": manifest.revision,
            "mission_status": manifest.state["status"],
            "authority_contract_sha256": contract_hash,
            "approval_phrase": f"approve manifest {contract_hash}",
            "checkpoint_ref": receipt.path,
            "checkpoint_sha256": receipt.sha256,
            "process_instance_id": self.process_instance_id,
        }

    def manifest_authorize(
        self,
        *,
        authority_contract_sha256: str,
        _host_context_ref: str | None = None,
        _host_gate_ref: str | None = None,
    ) -> dict[str, Any]:
        binding = self._binding(
            "manifest_authorize", _host_context_ref, _host_gate_ref
        )
        discovered = self._discover(binding.workspace_root)
        manifest = discovered.manifest
        if manifest.state.get("status") == "active":
            proposal = _pending_milestone_proposal(manifest)
            if proposal is None:
                raise ControllerError("MISSION_NOT_DRAFT")
            durable_hash = str(proposal["authority_contract_sha256"])
            if authority_contract_sha256 != durable_hash:
                raise ControllerError("AUTHORITY_CONTRACT_MISMATCH")
            approval_phrase = f"approve manifest {durable_hash}"
            if approval_phrase not in binding.context.prompt:
                raise ControllerError("HOST_CONTEXT_INVALID")
            try:
                authorized = apply_event_data(
                    manifest,
                    "authorize_manifest_milestone",
                    str(manifest.authority["operator_ref"]),
                    {"authority_contract_sha256": durable_hash},
                )
            except TransitionError as error:
                raise ControllerError(str(error)) from error
            store = self._store(binding.workspace_root, authorized.mission_id)
            authorized_checkpoint = store.save(authorized)
            proposal = propose_frontier_patch(
                authorized, ["write approved governed artifact"]
            )
            try:
                active = apply_event_data(
                    authorized,
                    "apply_mission_os",
                    MISSION_STEWARD_REF,
                    proposal.to_event_data(),
                )
            except TransitionError as error:
                raise ControllerError(str(error)) from error
            latest = store.save(active)
            return {
                "status": "authorized-milestone",
                **_status_summary(active),
                "mission_id": active.mission_id,
                "revision": active.revision,
                "mission_status": active.state["status"],
                "next_action": active.state["next_action"],
                "authority_contract_sha256": durable_hash,
                "checkpoint_ref": authorized_checkpoint.path,
                "latest_checkpoint_ref": latest.path,
                "latest_checkpoint_sha256": latest.sha256,
                "process_instance_id": self.process_instance_id,
            }
        if manifest.state.get("status") != "draft":
            raise ControllerError("MISSION_NOT_DRAFT")
        record = _definition_record(manifest)
        durable_hash = str(record["authority_contract_sha256"])
        if authority_contract_sha256 != durable_hash:
            raise ControllerError("AUTHORITY_CONTRACT_MISMATCH")
        approval_phrase = f"approve manifest {durable_hash}"
        if approval_phrase not in binding.context.prompt:
            raise ControllerError("HOST_CONTEXT_INVALID")

        store = self._store(binding.workspace_root, manifest.mission_id)
        approved = apply_event_data(
            manifest,
            "approve",
            str(manifest.authority["operator_ref"]),
            {"checkpoint_ref": discovered.receipt.path},
        )
        store.save(approved)
        proposal = propose_frontier_patch(
            approved,
            ["write approved governed artifact"],
        )
        active = apply_event_data(
            approved,
            "apply_mission_os",
            MISSION_STEWARD_REF,
            proposal.to_event_data(),
        )
        latest = store.save(active)
        return {
            "status": "authorized",
            **_status_summary(active),
            "mission_id": active.mission_id,
            "revision": active.revision,
            "mission_status": active.state["status"],
            "next_action": active.state["next_action"],
            "authority_contract_sha256": durable_hash,
            "checkpoint_ref": active.continuity["prior_checkpoint"],
            "latest_checkpoint_ref": latest.path,
            "latest_checkpoint_sha256": latest.sha256,
            "process_instance_id": self.process_instance_id,
        }

    @staticmethod
    def _artifact_for_dispatch(
        manifest: MissionManifest,
    ) -> tuple[Mapping[str, Any], bool]:
        definition = _durable_definition(manifest)
        artifacts = definition.get("governed_artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ControllerError("GOVERNED_ARTIFACT_NOT_FOUND")
        next_action = manifest.state.get("next_action")
        repair_prefix = "repair live state for file:"
        if isinstance(next_action, str) and next_action.startswith(repair_prefix):
            repair_path = next_action[len(repair_prefix) :]
            matches = [
                item
                for item in artifacts
                if isinstance(item, Mapping) and item.get("path") == repair_path
            ]
            if len(matches) != 1:
                raise ControllerError("GOVERNED_ARTIFACT_NOT_FOUND")
            return matches[0], True

        pending = [
            item
            for item in artifacts
            if isinstance(item, Mapping)
            and isinstance(item.get("path"), str)
            and _latest_receipt_for_path(manifest, str(item["path"])) is None
        ]
        if len(pending) != 1:
            raise ControllerError(
                "GOVERNED_ARTIFACT_NOT_FOUND"
                if not pending
                else "GOVERNED_ARTIFACT_AMBIGUOUS"
            )
        return pending[0], False

    @staticmethod
    def _baseline_state(manifest: MissionManifest, relpath: str) -> Mapping[str, Any]:
        governed = manifest.continuity.get("governed_workspace")
        entries = governed.get("baseline") if isinstance(governed, Mapping) else None
        matches = [
            entry
            for entry in entries or []
            if isinstance(entry, Mapping) and entry.get("path") == relpath
        ]
        if len(matches) != 1 or not isinstance(matches[0].get("state"), Mapping):
            raise ControllerError("GOVERNED_WORKSPACE_INVALID")
        return matches[0]["state"]

    def manifest_dispatch(
        self,
        *,
        _host_context_ref: str | None = None,
        _host_gate_ref: str | None = None,
    ) -> dict[str, Any]:
        binding = self._binding(
            "manifest_dispatch", _host_context_ref, _host_gate_ref
        )
        if binding.gate.lock_reason not in {
            "explicit-manifest-intent",
            "unfinished-durable-mission",
            "unfinished-mission-integrity-error",
        }:
            raise ControllerError("HOST_GATE_UNAVAILABLE")
        discovered = self._discover(binding.workspace_root)
        manifest = discovered.manifest
        artifact, repairing = self._artifact_for_dispatch(manifest)
        relpath = artifact.get("path")
        content = artifact.get("content")
        if not isinstance(relpath, str) or not isinstance(content, str):
            raise ControllerError("GOVERNED_ARTIFACT_INVALID")
        if repairing:
            try:
                live = capture_baseline(binding.workspace_root, [relpath])
            except GovernedWorkspaceError as error:
                raise ControllerError(str(error)) from error
            expected_state = live["baseline"][0]["state"]
            action = str(manifest.state["next_action"])
        else:
            expected_state = self._baseline_state(manifest, relpath)
            action = "write-text"
        expected_before = _request_expected_before(expected_state)
        store = self._store(binding.workspace_root, manifest.mission_id)
        decision = coordinate_once(
            manifest,
            execution_request={
                "capability_id": "filesystem-artifact",
                "requested_permissions": ["repository:write"],
                "requested_effects": [f"relpath:{relpath}", f"utf8:{content}"],
                "estimated_costs": ["one local artifact write"],
                "action": action,
                "expected_before": expected_before,
            },
            checkpoint_store=store,
        )
        if decision.kind != "DISPATCH" or decision.request is None:
            raise ControllerError(decision.reason)
        adapter = FilesystemArtifactAdapter(
            binding.workspace_root,
            receipt_root=discovered.mission_dir / "receipts",
            allowed_paths=tuple(
                manifest.continuity["governed_workspace"]["paths"]
            ),
        )
        try:
            receipt = dispatch_once(manifest, decision, adapter)
        except (CoordinationError, FilesystemArtifactError) as error:
            raise ControllerError(str(error)) from error
        if receipt.get("status") != "completed":
            raise ControllerError(
                f"FILESYSTEM_EFFECT_NOT_COMPLETED:{receipt.get('status')}"
            )

        recorded = apply_event_data(
            manifest,
            "record_execution_receipt",
            MISSION_STEWARD_REF,
            {"receipt": receipt, "request": decision.request},
        )
        store.save(recorded)
        acted = apply_event_data(
            recorded,
            "record_action",
            MISSION_STEWARD_REF,
            {"action_ref": receipt["artifact_refs"][0]},
        )
        store.save(acted)
        try:
            verification = verify_filesystem_receipt(
                str(receipt["external_receipt_ref"]),
                decision.request,
                binding.workspace_root,
                receipt_root=discovered.mission_dir / "receipts",
            )
        except FilesystemArtifactError as error:
            raise ControllerError(str(error)) from error
        verified = apply_event_data(
            acted,
            "record_verifier_result",
            "observer:artifact-verifier",
            {"result": verification.to_dict()},
        )
        checkpoint = store.save(verified)
        return {
            "status": "dispatched",
            **_status_summary(verified),
            "mission_id": verified.mission_id,
            "revision": verified.revision,
            "mission_status": verified.state["status"],
            "effect": deepcopy(receipt),
            "observation": verification.to_dict(),
            "checkpoint_ref": checkpoint.path,
            "checkpoint_sha256": checkpoint.sha256,
            "process_instance_id": self.process_instance_id,
        }

    def manifest_verify(
        self,
        *,
        profile: str = "artifact-bindings",
        _host_context_ref: str | None = None,
        _host_gate_ref: str | None = None,
    ) -> dict[str, Any]:
        binding = self._binding("manifest_verify", _host_context_ref, _host_gate_ref)
        if profile != "artifact-bindings":
            raise ControllerError("SANDBOXED_VERIFIER_UNAVAILABLE")
        discovered = self._discover(binding.workspace_root)
        manifest = discovered.manifest
        definition = _durable_definition(manifest)
        artifacts = definition.get("governed_artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ControllerError("GOVERNED_ARTIFACT_NOT_FOUND")
        store = self._store(binding.workspace_root, manifest.mission_id)
        observations: list[dict[str, Any]] = []
        for artifact in artifacts:
            if not isinstance(artifact, Mapping) or not isinstance(
                artifact.get("path"), str
            ):
                raise ControllerError("GOVERNED_ARTIFACT_INVALID")
            relpath = str(artifact["path"])
            receipt = _latest_receipt_for_path(manifest, relpath)
            if receipt is None:
                raise ControllerError("PROOF_BUNDLE_NOT_READY")
            try:
                observation = inspect_filesystem_receipt(
                    str(receipt["external_receipt_ref"]),
                    receipt["request"],
                    binding.workspace_root,
                    receipt_root=discovered.mission_dir / "receipts",
                )
            except FilesystemArtifactError as error:
                raise ControllerError(str(error)) from error
            observations.append(observation.to_dict())
            if not _result_recorded(manifest, observation.result_ref):
                manifest = apply_event_data(
                    manifest,
                    "record_verifier_result",
                    "observer:artifact-verifier",
                    {"result": observation.to_dict()},
                )
                store.save(manifest)
            if observation.status != "verified":
                latest = store.save(manifest)
                return {
                    "status": "contradicted",
                    **_status_summary(manifest),
                    "reason_code": observation.reason_code,
                    "mission_id": manifest.mission_id,
                    "revision": manifest.revision,
                    "mission_status": manifest.state["status"],
                    "next_action": manifest.state["next_action"],
                    "observation": observation.to_dict(),
                    "checkpoint_ref": latest.path,
                    "checkpoint_sha256": latest.sha256,
                    "process_instance_id": self.process_instance_id,
                }

        governed = manifest.continuity.get("governed_workspace")
        try:
            drift = find_unreceipted_drift(
                binding.workspace_root,
                governed,
                manifest.continuity.get("execution_receipts", []),
            )
        except GovernedWorkspaceError as error:
            raise ControllerError(str(error)) from error
        if drift:
            live = capture_baseline(
                binding.workspace_root, [item.path for item in drift]
            )
            baseline_by_path = {
                item["path"]: item
                for item in governed["baseline"]
                if isinstance(item, Mapping)
            }
            live_by_path = {
                item["path"]: item
                for item in live["baseline"]
                if isinstance(item, Mapping)
            }
            manifest = apply_reconciliation_findings(
                manifest,
                [
                    ReconciliationFinding(
                        subject_ref=f"file:{item.path}",
                        checkpoint_value=baseline_by_path[item.path],
                        live_value=live_by_path[item.path],
                        classification="CONTRADICTED",
                    )
                    for item in drift
                ],
            )
            checkpoint = store.save(manifest)
            return {
                "status": "contradicted",
                **_status_summary(manifest),
                "reason_code": "UNRECEIPTED_WORKSPACE_DRIFT",
                "mission_id": manifest.mission_id,
                "revision": manifest.revision,
                "mission_status": manifest.state["status"],
                "next_action": manifest.state["next_action"],
                "drift_findings": [
                    {"path": item.path, "reason_code": item.reason_code}
                    for item in drift
                ],
                "checkpoint_ref": checkpoint.path,
                "checkpoint_sha256": checkpoint.sha256,
                "process_instance_id": self.process_instance_id,
            }

        if _active_milestone_record(manifest) is not None:
            milestone_frontier = ["independent acceptance of governed milestone"]
            if manifest.state.get("current_frontier") != milestone_frontier:
                try:
                    proposal = propose_frontier_patch(manifest, milestone_frontier)
                    manifest = apply_event_data(
                        manifest,
                        "apply_mission_os",
                        MISSION_STEWARD_REF,
                        proposal.to_event_data(),
                    )
                except (TransitionError, ValueError) as error:
                    raise ControllerError(str(error)) from error
            checkpoint = store.save(manifest)
            return {
                "status": "verified-milestone",
                **_status_summary(manifest),
                "mission_id": manifest.mission_id,
                "revision": manifest.revision,
                "mission_status": manifest.state["status"],
                "next_action": manifest.state["next_action"],
                "observations": observations,
                "checkpoint_ref": checkpoint.path,
                "checkpoint_sha256": checkpoint.sha256,
                "process_instance_id": self.process_instance_id,
            }

        if manifest.state.get("status") == "active":
            try:
                manifest = apply_event_data(
                    manifest,
                    "begin_verification",
                    MISSION_STEWARD_REF,
                    {},
                )
            except TransitionError as error:
                raise ControllerError(str(error)) from error
        checkpoint = store.save(manifest)
        return {
            "status": "verified",
            **_status_summary(manifest),
            "mission_id": manifest.mission_id,
            "revision": manifest.revision,
            "mission_status": manifest.state["status"],
            "next_action": manifest.state["next_action"],
            "observations": observations,
            "checkpoint_ref": checkpoint.path,
            "checkpoint_sha256": checkpoint.sha256,
            "process_instance_id": self.process_instance_id,
        }

    def manifest_accept(
        self,
        *,
        acceptor_ref: str,
        verdict: str,
        separation_assurance: str,
        principal_evidence_ref: str | None = None,
        _host_context_ref: str | None = None,
        _host_gate_ref: str | None = None,
    ) -> dict[str, Any]:
        binding = self._binding("manifest_accept", _host_context_ref, _host_gate_ref)
        discovered = self._discover(binding.workspace_root)
        manifest = discovered.manifest
        verified_results = [
            item
            for item in manifest.continuity.get("verifier_results", [])
            if isinstance(item, Mapping) and item.get("status") == "verified"
        ]
        evidence_refs = [
            str(item["result_ref"])
            for item in verified_results
            if isinstance(item.get("result_ref"), str)
        ]
        evidence_refs.extend(
            str(item["external_receipt_ref"])
            for item in verified_results
            if isinstance(item.get("external_receipt_ref"), str)
        )
        coverage_limits = [
            "principal separation is not externally proven",
            "declared roles and process separation are not distinct-principal evidence",
        ]
        acceptance_data = {
            "verdict": verdict,
            "evidence_refs": list(dict.fromkeys(evidence_refs)),
            "coverage_limits": coverage_limits,
            "separation_assurance": separation_assurance,
            "principal_evidence_ref": principal_evidence_ref,
        }
        if _active_milestone_record(manifest) is not None:
            try:
                continued = apply_event_data(
                    manifest,
                    "accept_manifest_milestone",
                    acceptor_ref,
                    acceptance_data,
                )
            except TransitionError as error:
                raise ControllerError(str(error)) from error
            checkpoint = self._store(
                binding.workspace_root, continued.mission_id
            ).save(continued)
            return {
                "status": "accepted-milestone",
                **_status_summary(continued),
                "mission_id": continued.mission_id,
                "revision": continued.revision,
                "mission_status": continued.state["status"],
                "separation_assurance": separation_assurance,
                "coverage_limits": coverage_limits,
                "checkpoint_ref": checkpoint.path,
                "checkpoint_sha256": checkpoint.sha256,
                "process_instance_id": self.process_instance_id,
            }
        try:
            completed = apply_event_data(
                manifest,
                "accept",
                acceptor_ref,
                acceptance_data,
            )
        except TransitionError as error:
            raise ControllerError(str(error)) from error
        checkpoint = self._store(
            binding.workspace_root, completed.mission_id
        ).save(completed)
        return {
            "status": "accepted",
            **_status_summary(completed),
            "mission_id": completed.mission_id,
            "revision": completed.revision,
            "mission_status": completed.state["status"],
            "separation_assurance": separation_assurance,
            "coverage_limits": coverage_limits,
            "checkpoint_ref": checkpoint.path,
            "checkpoint_sha256": checkpoint.sha256,
            "process_instance_id": self.process_instance_id,
        }
