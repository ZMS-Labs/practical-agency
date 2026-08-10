"""Pathless manifest engagement over the deterministic mission kernel."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Protocol
from uuid import uuid4

from practical_agency.authority import authorize_action
from practical_agency.capability_discovery import (
    CapabilityDescriptor,
    FileSystemSkillProvider,
    discover_capabilities,
)
from practical_agency.capability_grants import (
    CapabilityGrantError,
    issue_grant,
    issue_grant_from_descriptor,
)
from practical_agency.capability_operations import CapabilityOperationError, execute_read
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


class HostCapabilityRegistry(Protocol):
    def observe_member_capabilities(self, binding: HostBinding) -> Mapping[str, Any]: ...
    def invoke_member_capability(self, binding: HostBinding, invocation_ref: str, grant_id: str, execution_attempt_id: str, canonical_request_bytes: bytes) -> Mapping[str, Any]: ...
    def lookup_member_invocation(self, execution_attempt_id: str) -> Mapping[str, Any] | None: ...


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
_CAPABILITY_INTENT_FIELDS = {
    "bounded_question_or_action",
    "requested_permissions",
    "requested_effects",
    "estimated_costs",
    "timeout_or_stop_condition",
}
_CAPABILITY_REQUEST_FIELDS = {
    "schema",
    "request_id",
    "mission_id",
    "mission_revision",
    "capability_id",
    "capability_source_sha256",
    "bounded_question_or_action",
    "authority_receipt",
    "expected_output_contract",
    "return_point",
    "timeout_or_stop_condition",
}
_CAPABILITY_REQUEST_CONTRACT = "contracts/capability-request.schema.json"
_CAPABILITY_RESULT_CONTRACT = "contracts/capability-result.schema.json"
_READ_AUTHORITY = {
    "file.read": ("repository:read", "bounded reads"),
    "resource.read": ("repository:read", "bounded reads"),
}
_CAPABILITY_NEED_FIELDS = {"schema", "need_id", "blocking_condition", "need_kind", "evidence_scope", "required_permissions", "expected_effects", "estimated_costs", "timeout_or_stop_condition", "return_point"}
_HOST_CATALOG_FIELDS = {"schema", "observation_id", "host_binding", "entries", "catalog_sha256"}
_HOST_ENTRY_FIELDS = {"member_root", "descriptor_path", "member_binding", "availability", "degradation_reason"}
_HOST_MEMBER_FIELDS = {"owner_package_id", "owner_runtime_sha256", "capability_id", "descriptor_sha256", "input_contract", "output_contract", "authority_required", "need_kinds", "non_mutating", "invocation_ref"}
_HOST_CONTRACT_FIELDS = {"id", "sha256"}
_HOST_RECEIPT_FIELDS = {"schema", "host_binding", "issue_catalog_sha256", "execute_catalog_sha256", "member_binding", "grant_id", "execution_attempt_id", "request_id", "request_sha256", "invocation_status", "result_json", "result_sha256", "returned_control_point", "external_durable_receipt_ref", "host_coverage_limits"}
_HOST_MEMBER_OPERATION = "host.member.invoke"


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _closed(value: object, fields: set[str]) -> bool:
    return isinstance(value, Mapping) and set(value) == fields


def _host_binding_payload(binding: HostBinding) -> dict[str, str]:
    return {"session_id": binding.context.session_id, "turn_id": binding.context.turn_id, "workspace_root": str(binding.workspace_root), "context_nonce_sha256": _sha256_text(binding.context.context_nonce)}


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ControllerError(code)


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ControllerError("HOST_CAPABILITY_REGISTRY_INVALID") from error


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _nonempty_string_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_nonempty(item) for item in value)
    )


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
    closed = {
        item.get("authority_contract_sha256")
        for item in decisions
        if isinstance(item, Mapping)
        and item.get("kind") == "manifest-milestone-acceptance"
    }
    closed.update(
        item.get("superseded_authority_contract_sha256")
        for item in decisions
        if isinstance(item, Mapping)
        and item.get("kind") == "manifest-milestone-superseded"
    )
    active = [
        item
        for item in decisions
        if isinstance(item, Mapping)
        and item.get("kind") == "manifest-milestone-definition"
        and item.get("authority_contract_sha256") not in closed
    ]
    if len(active) > 1:
        raise ControllerError("MANIFEST_MILESTONE_AMBIGUOUS")
    if not active:
        return None
    record = active[0]
    required = {
        "kind",
        "authority_contract",
        "authority_contract_sha256",
        "governed_workspace",
        "return_frontier",
        "return_next_action",
    }
    if not required.issubset(record) or set(record) - (
        required | {"authorized_at_revision"}
    ):
        raise ControllerError("AUTHORITY_CONTRACT_INVALID")
    contract = record.get("authority_contract")
    digest = record.get("authority_contract_sha256")
    if (
        not isinstance(contract, Mapping)
        or not isinstance(digest, str)
        or _canonical_sha256(contract) != digest
    ):
        raise ControllerError("AUTHORITY_CONTRACT_INVALID")
    authorized_at = record.get("authorized_at_revision")
    if authorized_at is not None and (
        isinstance(authorized_at, bool)
        or not isinstance(authorized_at, int)
        or authorized_at < 1
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
    manifest: MissionManifest, relpath: str, *, min_revision: int = 0
) -> Mapping[str, Any] | None:
    proof_ref = f"file:{relpath}"
    for receipt in reversed(manifest.continuity.get("execution_receipts", [])):
        if (
            isinstance(receipt, Mapping)
            and receipt.get("status") == "completed"
            and proof_ref in receipt.get("artifact_refs", [])
            and isinstance(receipt.get("request"), Mapping)
            and isinstance(receipt.get("external_receipt_ref"), str)
            and isinstance(receipt.get("mission_revision"), int)
            and receipt.get("mission_revision") >= min_revision
        ):
            return receipt
    return None


def _active_definition_receipt_floor(manifest: MissionManifest) -> int:
    record = _active_milestone_record(manifest)
    if record is None:
        return 0
    value = record.get("authorized_at_revision")
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


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


def _capability_effect_unknown_marker(manifest: MissionManifest) -> str | None:
    for marker in manifest.integrity["unresolved_verdicts"]:
        if marker.startswith("CAPABILITY_EFFECT_UNKNOWN:"):
            return marker
    return None


class ManifestController:
    """Compose pathless mission operations without exposing storage identity."""

    def __init__(
        self,
        *,
        plugin_root: Path | str,
        host_capability_registry: HostCapabilityRegistry | None = None,
    ) -> None:
        self.plugin_root = Path(plugin_root).resolve()
        self.host_capability_registry = host_capability_registry
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

    def _descriptor(self, capability_id: object) -> CapabilityDescriptor:
        descriptors = discover_capabilities([FileSystemSkillProvider(self.plugin_root / "skills")])
        matches = [item for item in descriptors if item.capability_id == capability_id]
        if len(matches) != 1 or matches[0].availability != "available":
            raise ControllerError("CAPABILITY_DESCRIPTOR_UNAVAILABLE")
        return matches[0]

    def _observed_descriptor(
        self,
        capability_id: object,
        descriptor_digest: object,
    ) -> CapabilityDescriptor:
        descriptor = self._descriptor(capability_id)
        if descriptor.source_sha256 != descriptor_digest:
            raise ControllerError("CAPABILITY_DESCRIPTOR_MISMATCH")
        return descriptor

    def _host_registry(self) -> HostCapabilityRegistry:
        registry = self.host_capability_registry
        if registry is None:
            raise ControllerError("HOST_CAPABILITY_REGISTRY_UNAVAILABLE")
        if any(not callable(getattr(registry, name, None)) for name in ("observe_member_capabilities", "invoke_member_capability", "lookup_member_invocation")):
            raise ControllerError("HOST_CAPABILITY_REGISTRY_INVALID")
        return registry

    @staticmethod
    def _host_file(root: Path, ref: object) -> Path:
        _require(_nonempty(ref), "HOST_CAPABILITY_REGISTRY_INVALID")
        relative = Path(str(ref))
        _require(not relative.is_absolute() and bool(relative.parts) and ".." not in relative.parts, "HOST_CAPABILITY_REGISTRY_INVALID")
        candidate = root
        for part in relative.parts:
            candidate = candidate / part
            _require(not candidate.is_symlink(), "HOST_CAPABILITY_REGISTRY_INVALID")
        try:
            candidate.resolve().relative_to(root)
        except ValueError as error:
            raise ControllerError("HOST_CAPABILITY_REGISTRY_INVALID") from error
        _require(candidate.is_file(), "HOST_CAPABILITY_REGISTRY_INVALID")
        return candidate.resolve()

    def _observe_host_members(self, binding: HostBinding) -> tuple[str, list[dict[str, Any]]]:
        registry = self._host_registry()
        try:
            catalog = registry.observe_member_capabilities(binding)
        except Exception as error:
            raise ControllerError("HOST_CAPABILITY_REGISTRY_INVALID") from error
        _require(
            _closed(catalog, _HOST_CATALOG_FIELDS)
            and catalog.get("schema") == "host-capability-catalog@1"
            and _nonempty(catalog.get("observation_id"))
            and _is_sha256(catalog.get("catalog_sha256"))
            and catalog.get("host_binding") == _host_binding_payload(binding)
            and isinstance(catalog.get("entries"), list),
            "HOST_CAPABILITY_REGISTRY_INVALID",
        )
        body = {"schema": catalog["schema"], "observation_id": catalog["observation_id"], "host_binding": deepcopy(catalog["host_binding"]), "entries": deepcopy(catalog["entries"])}
        try:
            catalog_sha256 = _canonical_sha256(body)
        except (TypeError, ValueError) as error:
            raise ControllerError("HOST_CAPABILITY_REGISTRY_INVALID") from error
        _require(catalog_sha256 == catalog["catalog_sha256"], "HOST_CAPABILITY_REGISTRY_INVALID")
        entries: list[dict[str, Any]] = []
        for entry in catalog["entries"]:
            _require(_closed(entry, _HOST_ENTRY_FIELDS) and _closed(entry.get("member_binding"), _HOST_MEMBER_FIELDS), "HOST_CAPABILITY_REGISTRY_INVALID")
            member = entry["member_binding"]
            _require(
                all(_nonempty(member.get(field)) for field in ("owner_package_id", "capability_id", "invocation_ref"))
                and _is_sha256(member.get("owner_runtime_sha256"))
                and _is_sha256(member.get("descriptor_sha256"))
                and _nonempty_string_list(member.get("authority_required"))
                and _nonempty_string_list(member.get("need_kinds"))
                and member.get("non_mutating") is True
                and entry.get("availability") in {"available", "unavailable", "degraded"}
                and (
                    (entry.get("availability") == "available" and entry.get("degradation_reason") is None)
                    or (entry.get("availability") != "available" and _nonempty(entry.get("degradation_reason")))
                ),
                "HOST_CAPABILITY_REGISTRY_INVALID",
            )
            input_contract = member.get("input_contract")
            output_contract = member.get("output_contract")
            _require(
                all(_closed(contract, _HOST_CONTRACT_FIELDS) and _nonempty(contract.get("id")) and _is_sha256(contract.get("sha256")) for contract in (input_contract, output_contract)),
                "HOST_CAPABILITY_REGISTRY_INVALID",
            )
            root_value = entry.get("member_root")
            _require(_nonempty(root_value), "HOST_CAPABILITY_REGISTRY_INVALID")
            root_path = Path(str(root_value))
            root = root_path.resolve()
            _require(root_path.is_absolute() and not root_path.is_symlink() and root_path == root and root.is_dir() and root != self.plugin_root and self.plugin_root not in root.parents and root not in self.plugin_root.parents, "HOST_CAPABILITY_REGISTRY_INVALID")
            descriptor_path = self._host_file(root, entry.get("descriptor_path"))
            _require(_file_sha256(descriptor_path) == member["descriptor_sha256"], "HOST_CAPABILITY_REGISTRY_INVALID")
            descriptors = [
                item
                for item in discover_capabilities([FileSystemSkillProvider(descriptor_path.parent.parent)])
                if Path(item.source_ref).resolve() == descriptor_path
            ]
            _require(len(descriptors) == 1, "HOST_CAPABILITY_REGISTRY_INVALID")
            descriptor = descriptors[0]
            need_kinds = descriptor.metadata.get("need_kinds")
            _require(
                descriptor.availability == "available"
                and descriptor.kind == "skill"
                and descriptor.persistence.value == "external"
                and descriptor.independence == "actor"
                and descriptor.capability_id == member["capability_id"]
                and descriptor.source_sha256 == member["descriptor_sha256"]
                and descriptor.input_contract == input_contract["id"]
                and descriptor.output_contract == output_contract["id"]
                and list(descriptor.authority_required) == list(member["authority_required"])
                and isinstance(need_kinds, (list, tuple))
                and list(need_kinds) == list(member["need_kinds"])
                and descriptor.metadata.get("non_mutating") in {True, "true"},
                "HOST_CAPABILITY_REGISTRY_INVALID",
            )
            for contract in (input_contract, output_contract):
                contract_path = self._host_file(root, contract["id"])
                repository_contract_path = self._host_file(self.plugin_root, contract["id"])
                contract_sha256 = _file_sha256(contract_path)
                _require(
                    contract_sha256 == contract["sha256"]
                    and _file_sha256(repository_contract_path) == contract_sha256,
                    "HOST_CAPABILITY_REGISTRY_INVALID",
                )
            entries.append(deepcopy(dict(entry)))
        return str(catalog["catalog_sha256"]), entries

    @staticmethod
    def _durable_capability_need(manifest: MissionManifest, expected_revision: int) -> dict[str, Any]:
        blockers = manifest.state.get("blockers")
        frontier = manifest.state.get("current_frontier")
        _require(
            manifest.state.get("status") == "blocked"
            and isinstance(blockers, list)
            and bool(blockers)
            and isinstance(frontier, list)
            and bool(frontier)
            and _nonempty(frontier[0]),
            "CAPABILITY_REQUEST_INVALID",
        )
        records = [
            item
            for item in manifest.continuity.get("decisions", [])
            if isinstance(item, Mapping)
            and item.get("kind") == "capability-need"
            and isinstance(item.get("need"), Mapping)
            and item["need"].get("blocking_condition") == frontier[0]
            and item["need"].get("blocking_condition") in blockers
            and isinstance(item["need"].get("return_point"), Mapping)
            and item["need"]["return_point"].get("revision") == expected_revision
        ]
        _require(len(records) == 1 and set(records[0]) == {"kind", "need"}, "CAPABILITY_REQUEST_INVALID")
        need = records[0].get("need")
        _require(
            _closed(need, _CAPABILITY_NEED_FIELDS)
            and need.get("schema") == "capability-need@1"
            and all(_nonempty(need.get(field)) for field in ("need_id", "blocking_condition", "need_kind", "timeout_or_stop_condition"))
            and all(_nonempty_string_list(need.get(field)) for field in ("evidence_scope", "required_permissions", "expected_effects", "estimated_costs"))
            and len(need["evidence_scope"]) == 1
            and list(need["expected_effects"]) == list(need["evidence_scope"]),
            "CAPABILITY_REQUEST_INVALID",
        )
        point = need.get("return_point")
        _require(
            _closed(point, {"mission_id", "revision", "frontier_index", "label"})
            and point.get("mission_id") == manifest.mission_id
            and point.get("revision") == expected_revision
            and point.get("frontier_index") == 0
            and point.get("label") == need["blocking_condition"]
            and frontier[0] == need["blocking_condition"]
            and need["blocking_condition"] in blockers,
            "CAPABILITY_RETURN_POINT_MISMATCH",
        )
        return deepcopy(dict(need))

    @staticmethod
    def _select_host_member(entries: list[dict[str, Any]], need: Mapping[str, Any]) -> dict[str, Any]:
        capability_ids = [str(entry["member_binding"]["capability_id"]) for entry in entries]
        if len(capability_ids) != len(set(capability_ids)):
            raise ControllerError("CAPABILITY_DESCRIPTOR_UNAVAILABLE")
        matches = [
            entry
            for entry in entries
            if entry["availability"] == "available"
            and entry["degradation_reason"] is None
            and need["need_kind"] in entry["member_binding"]["need_kinds"]
            and entry["member_binding"]["input_contract"]["id"] == _CAPABILITY_REQUEST_CONTRACT
            and entry["member_binding"]["output_contract"]["id"] == _CAPABILITY_RESULT_CONTRACT
            and entry["member_binding"]["authority_required"] == need["required_permissions"]
            and entry["member_binding"]["non_mutating"] is True
        ]
        if not matches:
            raise ControllerError("CAPABILITY_DESCRIPTOR_UNAVAILABLE")
        if len(matches) != 1:
            raise ControllerError("CAPABILITY_SELECTION_AMBIGUOUS")
        return deepcopy(matches[0])

    @staticmethod
    def _capability_record(manifest: MissionManifest, grant_id: str) -> Mapping[str, Any]:
        records = [item for item in manifest.capabilities.get("invoked", []) if isinstance(item, Mapping) and item.get("grant_id") == grant_id]
        if len(records) != 1:
            raise ControllerError("CAPABILITY_GRANT_NOT_FOUND")
        return records[0]

    def _issue_host_capability(self, binding: HostBinding) -> dict[str, Any]:
        self._host_registry()
        discovered = self._discover(binding.workspace_root)
        unknown_marker = _capability_effect_unknown_marker(discovered.manifest)
        if unknown_marker is not None:
            raise ControllerError(unknown_marker)
        manifest = discovered.manifest
        need = self._durable_capability_need(manifest, manifest.revision + 1)
        issue_catalog_sha256, entries = self._observe_host_members(binding)
        member = self._select_host_member(entries, need)["member_binding"]
        authority_errors = authorize_action(manifest, str(member["capability_id"]), need["required_permissions"], need["expected_effects"], need["estimated_costs"])
        if authority_errors:
            raise ControllerError(authority_errors[0])
        try:
            grant = issue_grant(
                {
                    "mission_id": manifest.mission_id,
                    "mission_revision": manifest.revision + 1,
                    "capability_id": member["capability_id"],
                    "capability_descriptor_sha256": member["descriptor_sha256"],
                    "blocking_condition": need["blocking_condition"],
                    "return_point": deepcopy(need["return_point"]),
                    "admitted_operation": _HOST_MEMBER_OPERATION,
                    "evidence_scope": list(need["evidence_scope"]),
                    "mutation": False,
                    "expires_after_use": True,
                }
            )
        except CapabilityGrantError as error:
            raise ControllerError(str(error)) from error
        request_id = f"capability-request:{grant['grant_id']}"
        request = {
            "schema": "capability-request@1",
            "request_id": request_id,
            "mission_id": manifest.mission_id,
            "mission_revision": manifest.revision + 1,
            "capability_id": member["capability_id"],
            "capability_source_sha256": member["descriptor_sha256"],
            "bounded_question_or_action": need["blocking_condition"],
            "authority_receipt": f"checkpoint-sha256:{discovered.receipt.sha256}",
            "expected_output_contract": member["output_contract"]["id"],
            "return_point": deepcopy(need["return_point"]),
            "timeout_or_stop_condition": need["timeout_or_stop_condition"],
        }
        grant.update(
            {
                "need_id": need["need_id"],
                "need_sha256": _canonical_sha256(need),
                "member_binding": deepcopy(dict(member)),
                "issue_catalog_sha256": issue_catalog_sha256,
                "request_id": request_id,
                "request_sha256": _canonical_sha256(request),
            }
        )
        try:
            updated = apply_event_data(manifest, "record_capability_request", "mission-steward:capability", {"grant": grant, "request": request})
        except TransitionError as error:
            raise ControllerError(str(error)) from error
        checkpoint = self._store(binding.workspace_root, manifest.mission_id).save(updated)
        return {"status": "capability-issued", "grant_id": str(grant["grant_id"]), "grant": deepcopy(grant), "checkpoint_ref": checkpoint.path, "checkpoint_sha256": checkpoint.sha256}

    def _host_result_from_receipt(
        self,
        receipt: object,
        *,
        binding: HostBinding,
        issue_catalog_sha256: str,
        execute_catalog_sha256: str,
        member: Mapping[str, Any],
        grant_id: str,
        execution_attempt_id: str,
        request: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        _require(
            _closed(receipt, _HOST_RECEIPT_FIELDS)
            and receipt.get("schema") == "host-capability-invocation-receipt@1"
            and receipt.get("invocation_status") == "completed"
            and _nonempty(receipt.get("result_json"))
            and _is_sha256(receipt.get("result_sha256"))
            and _nonempty(receipt.get("external_durable_receipt_ref"))
            and _nonempty_string_list(receipt.get("host_coverage_limits")),
            "CAPABILITY_INVOCATION_RECEIPT_INVALID",
        )
        request_bytes = _canonical_bytes(request)
        _require(
            receipt.get("host_binding") == _host_binding_payload(binding)
            and receipt.get("issue_catalog_sha256") == issue_catalog_sha256
            and receipt.get("execute_catalog_sha256") == execute_catalog_sha256
            and receipt.get("member_binding") == member
            and receipt.get("grant_id") == grant_id
            and receipt.get("execution_attempt_id") == execution_attempt_id
            and receipt.get("request_id") == request.get("request_id")
            and receipt.get("request_sha256") == hashlib.sha256(request_bytes).hexdigest()
            and receipt.get("returned_control_point") == request.get("return_point"),
            "CAPABILITY_INVOCATION_BINDING_MISMATCH",
        )
        try:
            result = json.loads(str(receipt["result_json"]))
        except json.JSONDecodeError as error:
            raise ControllerError("CAPABILITY_INVOCATION_RECEIPT_INVALID") from error
        _require(isinstance(result, dict), "CAPABILITY_INVOCATION_RECEIPT_INVALID")
        result_bytes = _canonical_bytes(result)
        _require(
            str(receipt["result_json"]).encode("utf-8") == result_bytes
            and receipt["result_sha256"] == hashlib.sha256(result_bytes).hexdigest(),
            "CAPABILITY_INVOCATION_RECEIPT_INVALID",
        )
        return deepcopy(result), deepcopy(dict(receipt))

    def _execute_host_capability(self, binding: HostBinding, grant_id: str) -> dict[str, Any]:
        registry = self._host_registry()
        discovered = self._discover(binding.workspace_root)
        manifest = discovered.manifest
        unknown_marker = _capability_effect_unknown_marker(manifest)
        if unknown_marker is not None:
            raise ControllerError(unknown_marker)
        record = self._capability_record(manifest, grant_id)
        if record.get("result") is not None:
            raise ControllerError("CAPABILITY_RESULT_REPLAY")
        if record.get("execution_state") == "in_progress":
            raise ControllerError("CAPABILITY_EXECUTION_IN_PROGRESS")
        if record.get("execution_state") != "pending":
            raise ControllerError("CAPABILITY_GRANT_NOT_PENDING")
        grant = record.get("grant")
        request = record.get("request")
        _require(isinstance(grant, Mapping) and isinstance(request, Mapping), "CAPABILITY_REQUEST_INVALID")
        need = self._durable_capability_need(manifest, manifest.revision)
        member = grant.get("member_binding")
        output_contract = member.get("output_contract") if isinstance(member, Mapping) else None
        scope = grant.get("evidence_scope")
        _require(
            _closed(member, _HOST_MEMBER_FIELDS)
            and isinstance(output_contract, Mapping)
            and isinstance(scope, list)
            and len(scope) == 1
            and grant.get("grant_id") == grant_id
            and grant.get("mission_id") == manifest.mission_id
            and grant.get("mission_revision") == manifest.revision
            and grant.get("admitted_operation") == _HOST_MEMBER_OPERATION
            and grant.get("mutation") is False
            and grant.get("need_id") == need["need_id"]
            and grant.get("need_sha256") == _canonical_sha256(need)
            and grant.get("blocking_condition") == need["blocking_condition"]
            and grant.get("return_point") == need["return_point"]
            and scope == need["evidence_scope"]
            and _is_sha256(grant.get("issue_catalog_sha256"))
            and set(request) == _CAPABILITY_REQUEST_FIELDS
            and request.get("schema") == "capability-request@1"
            and _nonempty(request.get("authority_receipt"))
            and request.get("request_id") == grant.get("request_id")
            and request.get("mission_id") == manifest.mission_id
            and request.get("mission_revision") == manifest.revision
            and request.get("capability_id") == member.get("capability_id")
            and request.get("capability_source_sha256") == member.get("descriptor_sha256")
            and request.get("bounded_question_or_action") == need["blocking_condition"]
            and request.get("expected_output_contract") == output_contract.get("id")
            and request.get("return_point") == need["return_point"]
            and request.get("timeout_or_stop_condition") == need["timeout_or_stop_condition"]
            and grant.get("request_sha256") == _canonical_sha256(request),
            "CAPABILITY_REQUEST_INVALID",
        )
        execute_catalog_sha256, entries = self._observe_host_members(binding)
        selected = self._select_host_member(entries, need)
        if selected["member_binding"] != member:
            raise ControllerError("CAPABILITY_DESCRIPTOR_MISMATCH")
        authority_errors = authorize_action(manifest, str(member["capability_id"]), need["required_permissions"], need["expected_effects"], need["estimated_costs"])
        if authority_errors:
            raise ControllerError(authority_errors[0])
        store = self._store(binding.workspace_root, manifest.mission_id)
        try:
            begun = apply_event_data(
                manifest,
                "begin_capability_execution",
                "mission-steward:capability",
                {"grant_id": grant_id, "operation": _HOST_MEMBER_OPERATION, "target": scope[0], "evidence_refs": list(scope), "execution_owner_id": self.process_instance_id},
            )
        except TransitionError as error:
            raise ControllerError(str(error)) from error
        store.save(begun)
        execution_attempt_id = self._capability_record(begun, grant_id).get("execution_attempt_id")
        _require(_nonempty(execution_attempt_id), "CAPABILITY_EXECUTION_STATE_INVALID")
        request_bytes = _canonical_bytes(request)
        try:
            raw_receipt = registry.invoke_member_capability(binding, str(member["invocation_ref"]), grant_id, str(execution_attempt_id), request_bytes)
        except Exception as error:
            raise ControllerError("CAPABILITY_INVOCATION_UNAVAILABLE") from error
        result, receipt = self._host_result_from_receipt(
            raw_receipt,
            binding=binding,
            issue_catalog_sha256=str(grant["issue_catalog_sha256"]),
            execute_catalog_sha256=execute_catalog_sha256,
            member=member,
            grant_id=grant_id,
            execution_attempt_id=str(execution_attempt_id),
            request=request,
        )
        try:
            updated = apply_event_data(
                begun,
                "record_capability_result",
                "capability:result",
                {"grant_id": grant_id, "result": result, "host_invocation_receipt": receipt},
            )
        except TransitionError as error:
            raise ControllerError(str(error)) from error
        checkpoint = store.save(updated)
        return {"status": "capability-executed", "grant_id": grant_id, "result": deepcopy(result), "checkpoint_ref": checkpoint.path, "checkpoint_sha256": checkpoint.sha256}

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
        recovery_checkpoint = None
        for record in manifest.capabilities.get("invoked", []):
            if (
                not isinstance(record, Mapping)
                or record.get("execution_state") != "in_progress"
                or record.get("execution_owner_id") == self.process_instance_id
            ):
                continue
            try:
                manifest = apply_event_data(
                    manifest,
                    "mark_capability_execution_unknown",
                    "mission-steward:capability",
                    {"grant_id": record.get("grant_id")},
                )
            except TransitionError as error:
                raise ControllerError(str(error)) from error
            recovery_checkpoint = store.save(manifest)
        unknown_marker = _capability_effect_unknown_marker(manifest)
        if unknown_marker is not None:
            checkpoint = recovery_checkpoint or discovered.receipt
            return {
                "status": "engaged",
                **_status_summary(manifest),
                "checkpoint_ref": checkpoint.path,
                "checkpoint_sha256": checkpoint.sha256,
                "drift_findings": [],
                "process_instance_id": self.process_instance_id,
            }
        try:
            definition = _durable_definition(manifest)
        except ControllerError:
            definition = {}
        receipt_floor = _active_definition_receipt_floor(manifest)
        artifacts = definition.get("governed_artifacts")
        if isinstance(artifacts, list):
            for artifact in artifacts:
                relpath = artifact.get("path") if isinstance(artifact, Mapping) else None
                if not isinstance(relpath, str):
                    continue
                receipt = _latest_receipt_for_path(
                    manifest, relpath, min_revision=receipt_floor
                )
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

    def manifest_capability_request(
        self,
        *,
        grant: Mapping[str, Any],
        request: Mapping[str, Any],
        _host_context_ref: str | None = None,
        _host_gate_ref: str | None = None,
    ) -> dict[str, Any]:
        binding = self._binding("manifest_capability_request", _host_context_ref, _host_gate_ref)
        if binding.gate.lock_reason not in {"explicit-manifest-intent", "unfinished-durable-mission", "unfinished-mission-integrity-error", "bootstrap-recovery"}:
            raise ControllerError("MANIFEST_ENGAGEMENT_LOCKED")
        discovered = self._discover(binding.workspace_root)
        self._observed_descriptor(
            grant.get("capability_id"), grant.get("capability_descriptor_sha256")
        )
        manifest = discovered.manifest
        if grant.get("mission_id") != manifest.mission_id or grant.get("mission_revision") != manifest.revision:
            raise ControllerError("CAPABILITY_GRANT_MISSION_MISMATCH")
        updated = apply_event_data(manifest, "record_capability_request", "mission-steward:capability", {"grant": grant, "request": request})
        checkpoint = self._store(binding.workspace_root, manifest.mission_id).save(updated)
        return {"status": "capability-requested", "grant": deepcopy(dict(grant)), "request": deepcopy(dict(request)), "checkpoint_ref": checkpoint.path, "checkpoint_sha256": checkpoint.sha256, "return_point": deepcopy(dict(grant["return_point"]))}

    def manifest_capability_issue(
        self,
        *,
        capability_id: str | None = None,
        blocking_condition: str | None = None,
        admitted_operation: str | None = None,
        evidence_scope: list[str] | None = None,
        request: Mapping[str, Any] | None = None,
        _host_context_ref: str | None = None,
        _host_gate_ref: str | None = None,
    ) -> dict[str, Any]:
        binding = self._binding("manifest_capability_issue", _host_context_ref, _host_gate_ref)
        if binding.gate.lock_reason not in {"explicit-manifest-intent", "unfinished-durable-mission", "unfinished-mission-integrity-error", "bootstrap-recovery"}:
            raise ControllerError("MANIFEST_ENGAGEMENT_LOCKED")
        selection_fields = (capability_id, blocking_condition, admitted_operation, evidence_scope, request)
        if all(value is None for value in selection_fields):
            return self._issue_host_capability(binding)
        if any(value is None for value in selection_fields):
            raise ControllerError("CAPABILITY_REQUEST_INVALID")
        if not _nonempty(admitted_operation):
            raise ControllerError("OPERATION_NOT_READ_ONLY")
        if admitted_operation.startswith("web."):
            raise ControllerError("WEB_OPERATION_DISABLED")
        authority_rule = _READ_AUTHORITY.get(admitted_operation)
        if authority_rule is None:
            raise ControllerError("OPERATION_NOT_READ_ONLY")
        if (
            not _nonempty(capability_id)
            or not _nonempty(blocking_condition)
            or not _nonempty_string_list(evidence_scope)
            or len(evidence_scope) != 1
        ):
            raise ControllerError("CAPABILITY_REQUEST_INVALID")

        discovered = self._discover(binding.workspace_root)
        unknown_marker = _capability_effect_unknown_marker(discovered.manifest)
        if unknown_marker is not None:
            raise ControllerError(unknown_marker)
        descriptor = self._descriptor(capability_id)
        if (
            descriptor.input_contract != _CAPABILITY_REQUEST_CONTRACT
            or descriptor.output_contract != _CAPABILITY_RESULT_CONTRACT
        ):
            raise ControllerError("CAPABILITY_CONTRACT_MISMATCH")
        if not isinstance(request, Mapping) or set(request) != _CAPABILITY_INTENT_FIELDS:
            raise ControllerError("CAPABILITY_REQUEST_INVALID")

        permissions = request.get("requested_permissions")
        effects = request.get("requested_effects")
        costs = request.get("estimated_costs")
        if (
            not _nonempty(request.get("bounded_question_or_action"))
            or not _nonempty(request.get("timeout_or_stop_condition"))
            or not _nonempty_string_list(permissions)
            or not _nonempty_string_list(effects)
            or not _nonempty_string_list(costs)
        ):
            raise ControllerError("CAPABILITY_REQUEST_INVALID")

        required_permissions = list(
            dict.fromkeys([*descriptor.authority_required, authority_rule[0]])
        )
        if (
            list(permissions) != required_permissions
            or list(effects) != evidence_scope
            or list(costs) != [authority_rule[1]]
            or request.get("bounded_question_or_action")
            != f"{admitted_operation}:{evidence_scope[0]}"
        ):
            raise ControllerError("CAPABILITY_REQUEST_INVALID")

        manifest = discovered.manifest
        authority_errors = authorize_action(
            manifest,
            descriptor.capability_id,
            required_permissions,
            evidence_scope,
            [authority_rule[1]],
        )
        if authority_errors:
            raise ControllerError(authority_errors[0])

        frontier = manifest.state.get("current_frontier")
        if (
            not isinstance(frontier, list)
            or not frontier
            or not _nonempty(frontier[0])
        ):
            raise ControllerError("CAPABILITY_RETURN_POINT_UNAVAILABLE")
        point = {
            "mission_id": manifest.mission_id,
            "revision": manifest.revision + 1,
            "frontier_index": 0,
            "label": frontier[0],
        }
        try:
            grant = issue_grant_from_descriptor(
                descriptor,
                mission_id=manifest.mission_id,
                mission_revision=manifest.revision + 1,
                blocking_condition=blocking_condition,
                return_point=point,
                admitted_operation=admitted_operation,
                evidence_scope=evidence_scope,
            )
        except (CapabilityGrantError, IndexError) as error:
            raise ControllerError(str(error)) from error

        request_id = f"capability-request:{grant['grant_id']}"
        grant["request_id"] = request_id
        canonical_request = {
            "schema": "capability-request@1",
            "request_id": request_id,
            "mission_id": manifest.mission_id,
            "mission_revision": manifest.revision + 1,
            "capability_id": descriptor.capability_id,
            "capability_source_sha256": descriptor.source_sha256,
            "bounded_question_or_action": request["bounded_question_or_action"],
            "authority_receipt": f"checkpoint-sha256:{discovered.receipt.sha256}",
            "expected_output_contract": descriptor.output_contract,
            "return_point": deepcopy(point),
            "timeout_or_stop_condition": request["timeout_or_stop_condition"],
        }
        try:
            updated = apply_event_data(
                manifest,
                "record_capability_request",
                "mission-steward:capability",
                {"grant": grant, "request": canonical_request},
            )
        except TransitionError as error:
            raise ControllerError(str(error)) from error
        checkpoint = self._store(binding.workspace_root, manifest.mission_id).save(updated)
        return {
            "status": "capability-issued",
            "grant_id": str(grant["grant_id"]),
            "grant": deepcopy(grant),
            "checkpoint_ref": checkpoint.path,
            "checkpoint_sha256": checkpoint.sha256,
        }

    def manifest_capability_result(
        self,
        *,
        grant_id: str,
        result: Mapping[str, Any],
        _host_context_ref: str | None = None,
        _host_gate_ref: str | None = None,
    ) -> dict[str, Any]:
        binding = self._binding("manifest_capability_result", _host_context_ref, _host_gate_ref)
        if binding.gate.lock_reason not in {"explicit-manifest-intent", "unfinished-durable-mission", "unfinished-mission-integrity-error", "bootstrap-recovery"}:
            raise ControllerError("MANIFEST_ENGAGEMENT_LOCKED")
        discovered = self._discover(binding.workspace_root)
        manifest = discovered.manifest
        updated = apply_event_data(manifest, "record_capability_result", "capability:result", {"grant_id": grant_id, "result": result})
        checkpoint = self._store(binding.workspace_root, manifest.mission_id).save(updated)
        return {"status": "capability-result-recorded", "grant_id": grant_id, "result": deepcopy(dict(result)), "checkpoint_ref": checkpoint.path, "checkpoint_sha256": checkpoint.sha256}

    def manifest_capability_execute(
        self,
        *,
        grant_id: str,
        operation: str | None = None,
        target: str | None = None,
        evidence_refs: list[str] | None = None,
        evidence_payload: Mapping[str, str] | None = None,
        _host_context_ref: str | None = None,
        _host_gate_ref: str | None = None,
    ) -> dict[str, Any]:
        binding = self._binding("manifest_capability_execute", _host_context_ref, _host_gate_ref)
        if binding.gate.lock_reason not in {"explicit-manifest-intent", "unfinished-durable-mission", "unfinished-mission-integrity-error", "bootstrap-recovery"}:
            raise ControllerError("MANIFEST_ENGAGEMENT_LOCKED")
        if not _nonempty(grant_id):
            raise ControllerError("CAPABILITY_GRANT_ID_REQUIRED")
        if operation is None and target is None and evidence_refs is None and evidence_payload is None:
            return self._execute_host_capability(binding, grant_id)
        if not _nonempty(operation):
            raise ControllerError("OPERATION_NOT_READ_ONLY")
        if operation.startswith("web."):
            raise ControllerError("WEB_OPERATION_DISABLED")
        authority_rule = _READ_AUTHORITY.get(operation)
        if authority_rule is None:
            raise ControllerError("OPERATION_NOT_READ_ONLY")

        discovered = self._discover(binding.workspace_root)
        manifest = discovered.manifest
        unknown_marker = _capability_effect_unknown_marker(manifest)
        if unknown_marker is not None:
            raise ControllerError(unknown_marker)
        records = [
            item
            for item in manifest.capabilities.get("invoked", [])
            if isinstance(item, Mapping) and item.get("grant_id") == grant_id
        ]
        if len(records) != 1:
            raise ControllerError("CAPABILITY_GRANT_NOT_FOUND")
        record = records[0]
        if record.get("result") is not None:
            raise ControllerError("CAPABILITY_RESULT_REPLAY")
        execution_state = record.get("execution_state")
        if execution_state == "in_progress":
            raise ControllerError("CAPABILITY_EXECUTION_IN_PROGRESS")
        if execution_state != "pending":
            raise ControllerError("CAPABILITY_GRANT_NOT_PENDING")

        grant = record.get("grant")
        request = record.get("request")
        if not isinstance(grant, Mapping) or not isinstance(request, Mapping):
            raise ControllerError("CAPABILITY_REQUEST_INVALID")
        if grant.get("grant_id") != grant_id:
            raise ControllerError("CAPABILITY_GRANT_ID_MISMATCH")
        if grant.get("mission_id") != manifest.mission_id:
            raise ControllerError("CAPABILITY_GRANT_MISSION_MISMATCH")
        if grant.get("mission_revision") != manifest.revision:
            raise ControllerError("GRANT_STALE")
        if grant.get("admitted_operation") != operation:
            raise ControllerError("GRANT_OPERATION_NOT_ADMITTED")

        scope = grant.get("evidence_scope")
        if (
            not isinstance(scope, list)
            or len(scope) != 1
            or not all(_nonempty(item) for item in scope)
        ):
            raise ControllerError("CAPABILITY_GRANT_INVALID")
        if target not in scope:
            raise ControllerError("TARGET_NOT_IN_EVIDENCE_SCOPE")

        if evidence_refs is None:
            refs = [target]
        elif _nonempty_string_list(evidence_refs):
            refs = list(evidence_refs)
        else:
            raise ControllerError("GRANT_EVIDENCE_REQUIRED")
        if any(ref not in scope for ref in refs):
            raise ControllerError("GRANT_EVIDENCE_REQUIRED")

        if (
            set(request) != _CAPABILITY_REQUEST_FIELDS
            or request.get("schema") != "capability-request@1"
            or not _nonempty(request.get("request_id"))
            or not _nonempty(request.get("authority_receipt"))
            or not _nonempty(request.get("timeout_or_stop_condition"))
            or request.get("request_id") != grant.get("request_id")
            or request.get("mission_id") != manifest.mission_id
            or request.get("mission_revision") != manifest.revision
            or request.get("capability_id") != grant.get("capability_id")
            or request.get("capability_source_sha256")
            != grant.get("capability_descriptor_sha256")
            or request.get("bounded_question_or_action")
            != f"{operation}:{target}"
            or request.get("expected_output_contract")
            != _CAPABILITY_RESULT_CONTRACT
            or request.get("return_point") != grant.get("return_point")
        ):
            raise ControllerError("CAPABILITY_REQUEST_INVALID")

        descriptor = self._observed_descriptor(
            grant.get("capability_id"),
            grant.get("capability_descriptor_sha256"),
        )
        if (
            descriptor.input_contract != _CAPABILITY_REQUEST_CONTRACT
            or descriptor.output_contract != _CAPABILITY_RESULT_CONTRACT
        ):
            raise ControllerError("CAPABILITY_CONTRACT_MISMATCH")
        required_permissions = list(
            dict.fromkeys([*descriptor.authority_required, authority_rule[0]])
        )
        authority_errors = authorize_action(
            manifest,
            descriptor.capability_id,
            required_permissions,
            scope,
            [authority_rule[1]],
        )
        if authority_errors:
            raise ControllerError(authority_errors[0])

        execution_grant = deepcopy(dict(grant))
        store = self._store(binding.workspace_root, manifest.mission_id)
        try:
            begun = apply_event_data(
                manifest,
                "begin_capability_execution",
                "mission-steward:capability",
                {
                    "grant_id": grant_id,
                    "operation": operation,
                    "target": target,
                    "evidence_refs": refs,
                    "execution_owner_id": self.process_instance_id,
                },
            )
        except TransitionError as error:
            raise ControllerError(str(error)) from error
        store.save(begun)

        try:
            observed = execute_read(
                execution_grant,
                mission_id=manifest.mission_id,
                mission_revision=manifest.revision,
                operation=operation,
                target=target,
                workspace=binding.workspace_root,
                evidence_refs=refs,
                evidence_payload=evidence_payload,
            )
        except CapabilityOperationError as error:
            raise ControllerError(str(error)) from error

        result = {
            "schema": "capability-result@1",
            "request_id": request["request_id"],
            "status": "completed",
            "verdict": observed.get("verdict"),
            "artifact_refs": refs,
            "observed_effects": deepcopy(observed["observed_effects"]),
            "returned_control_point": deepcopy(request["return_point"]),
            "coverage_limits": list(observed["coverage_limits"]),
        }
        try:
            updated = apply_event_data(
                begun,
                "record_capability_result",
                "capability:result",
                {"grant_id": grant_id, "result": result},
            )
        except TransitionError as error:
            raise ControllerError(str(error)) from error
        checkpoint = store.save(updated)
        return {
            "status": "capability-executed",
            "grant_id": grant_id,
            "result": deepcopy(result),
            "checkpoint_ref": checkpoint.path,
            "checkpoint_sha256": checkpoint.sha256,
        }

    def manifest_clarify(
        self,
        *,
        clarification: str,
        _host_context_ref: str | None = None,
        _host_gate_ref: str | None = None,
    ) -> dict[str, Any]:
        binding = self._binding("manifest_clarify", _host_context_ref, _host_gate_ref)
        if not _nonempty(clarification):
            raise ControllerError("CLARIFICATION_REQUIRED")
        discovered = self._discover(binding.workspace_root)
        manifest = discovered.manifest
        updated = apply_event_data(manifest, "amend_authority", str(manifest.authority["operator_ref"]), {"amendment": clarification})
        checkpoint = self._store(binding.workspace_root, manifest.mission_id).save(updated)
        return {"status": "clarification-appended", "mission_id": updated.mission_id, "revision": updated.revision, "instruction": updated.authority["instruction"], "amendments": list(updated.authority["amendments"]), "checkpoint_ref": checkpoint.path, "checkpoint_sha256": checkpoint.sha256}

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
            active_milestone = _active_milestone_record(manifest)
            if standard_records or _pending_milestone_proposal(manifest) is not None:
                raise ControllerError(
                    f"MISSION_DEFINITION_ALREADY_EXISTS:{manifest.mission_id}"
                )
            contract = {
                "schema": "manifest-authority-contract@1",
                "mission_id": manifest.mission_id,
                "definition": deepcopy(normalized),
            }
            contract_hash = _canonical_sha256(contract)
            supersedes = (
                str(active_milestone["authority_contract_sha256"])
                if active_milestone is not None
                else None
            )
            if supersedes == contract_hash:
                raise ControllerError(
                    f"MISSION_DEFINITION_ALREADY_EXISTS:{manifest.mission_id}"
                )
            event_data = {
                "authority_contract": contract,
                "authority_contract_sha256": contract_hash,
                "governed_workspace": baseline,
            }
            if supersedes is not None:
                event_data["supersedes_authority_contract_sha256"] = supersedes
            try:
                proposed = apply_event_data(
                    manifest,
                    "propose_manifest_milestone",
                    MISSION_STEWARD_REF,
                    event_data,
                )
            except TransitionError as error:
                raise ControllerError(str(error)) from error
            receipt = self._store(
                binding.workspace_root, proposed.mission_id
            ).save(proposed)
            return {
                "status": (
                    "definition-revision-proposed"
                    if supersedes is not None
                    else "definition-proposed"
                ),
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
        receipt_floor = _active_definition_receipt_floor(manifest)
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
            and _latest_receipt_for_path(
                manifest,
                str(item["path"]),
                min_revision=receipt_floor,
            )
            is None
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
        receipt_floor = _active_definition_receipt_floor(manifest)
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
            receipt = _latest_receipt_for_path(
                manifest, relpath, min_revision=receipt_floor
            )
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
        reason: str | None = None,
        separation_assurance: str,
        principal_evidence_ref: str | None = None,
        _host_context_ref: str | None = None,
        _host_gate_ref: str | None = None,
    ) -> dict[str, Any]:
        binding = self._binding("manifest_accept", _host_context_ref, _host_gate_ref)
        discovered = self._discover(binding.workspace_root)
        manifest = discovered.manifest
        receipt_floor = _active_definition_receipt_floor(manifest)
        qualifying_request_ids = {
            item.get("request_id")
            for item in manifest.continuity.get("execution_receipts", [])
            if isinstance(item, Mapping)
            and isinstance(item.get("mission_revision"), int)
            and item.get("mission_revision") >= receipt_floor
        }
        verified_results = [
            item
            for item in manifest.continuity.get("verifier_results", [])
            if isinstance(item, Mapping)
            and item.get("status") == "verified"
            and item.get("request_id") in qualifying_request_ids
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
        if verdict in {"FAIL", "INCONCLUSIVE"}:
            try:
                rejected = apply_event_data(
                    manifest,
                    "reject",
                    acceptor_ref,
                    {**acceptance_data, "reason": reason},
                )
            except TransitionError as error:
                raise ControllerError(str(error)) from error
            checkpoint = self._store(
                binding.workspace_root, rejected.mission_id
            ).save(rejected)
            return {
                "status": "rejected",
                **_status_summary(rejected),
                "mission_id": rejected.mission_id,
                "revision": rejected.revision,
                "mission_status": rejected.state["status"],
                "verdict": verdict,
                "reason": reason,
                "evidence_refs": list(acceptance_data["evidence_refs"]),
                "separation_assurance": separation_assurance,
                "coverage_limits": coverage_limits,
                "checkpoint_ref": checkpoint.path,
                "checkpoint_sha256": checkpoint.sha256,
                "process_instance_id": self.process_instance_id,
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
