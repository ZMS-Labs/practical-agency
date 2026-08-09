"""Pathless manifest engagement over the deterministic mission kernel."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from practical_agency.checkpoint_store import FileCheckpointStore
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
from practical_agency.state_machine import MISSION_STEWARD_REF, apply_event_data


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
        return {
            "status": "engaged",
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
        try:
            discovered = discover_active_mission(binding.workspace_root)
        except MissionDiscoveryError as error:
            if str(error) != "ACTIVE_MISSION_NOT_FOUND":
                raise ControllerError(str(error)) from error
        else:
            raise ControllerError(
                f"MISSION_DEFINITION_ALREADY_EXISTS:{discovered.manifest.mission_id}"
            )

        normalized, baseline = self._normalize_definition(
            binding.workspace_root, definition
        )
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
