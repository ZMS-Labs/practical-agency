schema: outsource-relay@1
work_id: durable-capability-transaction
based_on_commit: 993efd0fbc920a8345f79b25fd81413b4a96220b
status: PARTIAL
summary: |
  Stage 10 adds the repository consumer side of the reserved host catalog/invoke/lookup seam in two production files. Caller-free issue now fails closed when the registry is absent, or derives the current typed durable need and one uniquely eligible separately rooted external member when it is present. Grant-only execute re-observes that member, durably begins the one-use attempt before one host invocation, accepts only a canonically bound host receipt, and persists the exact member-owned result plus external durable receipt reference without entering execute_read. The legacy caller-selected local-read path remains available only when its existing arguments are supplied. No real host adapter, test change, execution, publication, or runtime claim is included.
work_product: |
  diff --git a/practical_agency/controller.py b/practical_agency/controller.py
  --- a/practical_agency/controller.py
  +++ b/practical_agency/controller.py
  @@ -7,3 +7,3 @@
   from pathlib import Path
  -from typing import Any, Mapping
  +from typing import Any, Mapping, Protocol
   from uuid import uuid4
  @@ -17,4 +17,5 @@
   from practical_agency.capability_grants import (
       CapabilityGrantError,
  +    issue_grant,
       issue_grant_from_descriptor,
   )
  @@ -59,5 +60,11 @@
   class ControllerError(RuntimeError):
       """Named refusal from the operator-facing manifest controller."""
   
   
  +class HostCapabilityRegistry(Protocol):
  +    def observe_member_capabilities(self, binding: HostBinding) -> Mapping[str, Any]: ...
  +    def invoke_member_capability(self, binding: HostBinding, invocation_ref: str, grant_id: str, execution_attempt_id: str, canonical_request_bytes: bytes) -> Mapping[str, Any]: ...
  +    def lookup_member_invocation(self, execution_attempt_id: str) -> Mapping[str, Any] | None: ...
  +
  +
   _DEFINITION_FIELDS = (
  @@ -103,14 +110,46 @@
   _READ_AUTHORITY = {
       "file.read": ("repository:read", "bounded reads"),
       "resource.read": ("repository:read", "bounded reads"),
   }
  +_CAPABILITY_NEED_FIELDS = {"schema", "need_id", "blocking_condition", "need_kind", "evidence_scope", "required_permissions", "expected_effects", "estimated_costs", "timeout_or_stop_condition", "return_point"}
  +_HOST_CATALOG_FIELDS = {"schema", "observation_id", "host_binding", "entries", "catalog_sha256"}
  +_HOST_ENTRY_FIELDS = {"member_root", "descriptor_path", "member_binding", "availability", "degradation_reason"}
  +_HOST_MEMBER_FIELDS = {"owner_package_id", "owner_runtime_sha256", "capability_id", "descriptor_sha256", "input_contract", "output_contract", "authority_required", "need_kinds", "non_mutating", "invocation_ref"}
  +_HOST_CONTRACT_FIELDS = {"id", "sha256"}
  +_HOST_RECEIPT_FIELDS = {"schema", "host_binding", "issue_catalog_sha256", "execute_catalog_sha256", "member_binding", "grant_id", "execution_attempt_id", "request_id", "request_sha256", "invocation_status", "result_json", "result_sha256", "returned_control_point", "external_durable_receipt_ref", "host_coverage_limits"}
  +_HOST_MEMBER_OPERATION = "host.member.invoke"
  +
  +
  +def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
  +    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
   
   
   def _canonical_sha256(value: Mapping[str, Any]) -> str:
  -    encoded = json.dumps(
  -        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
  -    ).encode("utf-8")
  -    return hashlib.sha256(encoded).hexdigest()
  +    return hashlib.sha256(_canonical_bytes(value)).hexdigest()
  +
  +
  +def _is_sha256(value: object) -> bool:
  +    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)
  +
  +
  +def _closed(value: object, fields: set[str]) -> bool:
  +    return isinstance(value, Mapping) and set(value) == fields
  +
  +
  +def _host_binding_payload(binding: HostBinding) -> dict[str, str]:
  +    return {"session_id": binding.context.session_id, "turn_id": binding.context.turn_id, "workspace_root": str(binding.workspace_root), "context_nonce_sha256": _sha256_text(binding.context.context_nonce)}
  +
  +
  +def _require(condition: bool, code: str) -> None:
  +    if not condition:
  +        raise ControllerError(code)
  +
  +
  +def _file_sha256(path: Path) -> str:
  +    try:
  +        return hashlib.sha256(path.read_bytes()).hexdigest()
  +    except OSError as error:
  +        raise ControllerError("HOST_CAPABILITY_REGISTRY_INVALID") from error
   
   
   def _nonempty(value: object) -> bool:
  @@ -341,3 +380,9 @@
  -    def __init__(self, *, plugin_root: Path | str) -> None:
  +    def __init__(
  +        self,
  +        *,
  +        plugin_root: Path | str,
  +        host_capability_registry: HostCapabilityRegistry | None = None,
  +    ) -> None:
           self.plugin_root = Path(plugin_root).resolve()
  +        self.host_capability_registry = host_capability_registry
           self.process_instance_id = f"controller-{uuid4().hex}"
  @@ -391,3 +436,399 @@
           return descriptor
   
  +    def _host_registry(self) -> HostCapabilityRegistry:
  +        registry = self.host_capability_registry
  +        if registry is None:
  +            raise ControllerError("HOST_CAPABILITY_REGISTRY_UNAVAILABLE")
  +        if any(not callable(getattr(registry, name, None)) for name in ("observe_member_capabilities", "invoke_member_capability", "lookup_member_invocation")):
  +            raise ControllerError("HOST_CAPABILITY_REGISTRY_INVALID")
  +        return registry
  +
  +    @staticmethod
  +    def _host_file(root: Path, ref: object) -> Path:
  +        _require(_nonempty(ref), "HOST_CAPABILITY_REGISTRY_INVALID")
  +        relative = Path(str(ref))
  +        _require(not relative.is_absolute() and bool(relative.parts) and ".." not in relative.parts, "HOST_CAPABILITY_REGISTRY_INVALID")
  +        candidate = root
  +        for part in relative.parts:
  +            candidate = candidate / part
  +            _require(not candidate.is_symlink(), "HOST_CAPABILITY_REGISTRY_INVALID")
  +        try:
  +            candidate.resolve().relative_to(root)
  +        except ValueError as error:
  +            raise ControllerError("HOST_CAPABILITY_REGISTRY_INVALID") from error
  +        _require(candidate.is_file(), "HOST_CAPABILITY_REGISTRY_INVALID")
  +        return candidate.resolve()
  +
  +    def _observe_host_members(self, binding: HostBinding) -> tuple[str, list[dict[str, Any]]]:
  +        registry = self._host_registry()
  +        try:
  +            catalog = registry.observe_member_capabilities(binding)
  +        except Exception as error:
  +            raise ControllerError("HOST_CAPABILITY_REGISTRY_INVALID") from error
  +        _require(
  +            _closed(catalog, _HOST_CATALOG_FIELDS)
  +            and catalog.get("schema") == "host-capability-catalog@1"
  +            and _nonempty(catalog.get("observation_id"))
  +            and _is_sha256(catalog.get("catalog_sha256"))
  +            and catalog.get("host_binding") == _host_binding_payload(binding)
  +            and isinstance(catalog.get("entries"), list),
  +            "HOST_CAPABILITY_REGISTRY_INVALID",
  +        )
  +        body = {"schema": catalog["schema"], "observation_id": catalog["observation_id"], "host_binding": deepcopy(catalog["host_binding"]), "entries": deepcopy(catalog["entries"])}
  +        try:
  +            catalog_sha256 = _canonical_sha256(body)
  +        except (TypeError, ValueError) as error:
  +            raise ControllerError("HOST_CAPABILITY_REGISTRY_INVALID") from error
  +        _require(catalog_sha256 == catalog["catalog_sha256"], "HOST_CAPABILITY_REGISTRY_INVALID")
  +        entries: list[dict[str, Any]] = []
  +        for entry in catalog["entries"]:
  +            _require(_closed(entry, _HOST_ENTRY_FIELDS) and _closed(entry.get("member_binding"), _HOST_MEMBER_FIELDS), "HOST_CAPABILITY_REGISTRY_INVALID")
  +            member = entry["member_binding"]
  +            _require(
  +                all(_nonempty(member.get(field)) for field in ("owner_package_id", "capability_id", "invocation_ref"))
  +                and _is_sha256(member.get("owner_runtime_sha256"))
  +                and _is_sha256(member.get("descriptor_sha256"))
  +                and _nonempty_string_list(member.get("authority_required"))
  +                and _nonempty_string_list(member.get("need_kinds"))
  +                and member.get("non_mutating") is True
  +                and entry.get("availability") in {"available", "unavailable", "degraded"}
  +                and (
  +                    (entry.get("availability") == "available" and entry.get("degradation_reason") is None)
  +                    or (entry.get("availability") != "available" and _nonempty(entry.get("degradation_reason")))
  +                ),
  +                "HOST_CAPABILITY_REGISTRY_INVALID",
  +            )
  +            input_contract = member.get("input_contract")
  +            output_contract = member.get("output_contract")
  +            _require(
  +                all(_closed(contract, _HOST_CONTRACT_FIELDS) and _nonempty(contract.get("id")) and _is_sha256(contract.get("sha256")) for contract in (input_contract, output_contract)),
  +                "HOST_CAPABILITY_REGISTRY_INVALID",
  +            )
  +            root_value = entry.get("member_root")
  +            _require(_nonempty(root_value), "HOST_CAPABILITY_REGISTRY_INVALID")
  +            root_path = Path(str(root_value))
  +            root = root_path.resolve()
  +            _require(root_path.is_absolute() and not root_path.is_symlink() and root_path == root and root.is_dir() and root != self.plugin_root and self.plugin_root not in root.parents and root not in self.plugin_root.parents, "HOST_CAPABILITY_REGISTRY_INVALID")
  +            descriptor_path = self._host_file(root, entry.get("descriptor_path"))
  +            _require(_file_sha256(descriptor_path) == member["descriptor_sha256"], "HOST_CAPABILITY_REGISTRY_INVALID")
  +            descriptors = [
  +                item
  +                for item in discover_capabilities([FileSystemSkillProvider(descriptor_path.parent.parent)])
  +                if Path(item.source_ref).resolve() == descriptor_path
  +            ]
  +            _require(len(descriptors) == 1, "HOST_CAPABILITY_REGISTRY_INVALID")
  +            descriptor = descriptors[0]
  +            need_kinds = descriptor.metadata.get("need_kinds")
  +            _require(
  +                descriptor.availability == "available"
  +                and descriptor.kind == "skill"
  +                and descriptor.persistence.value == "external"
  +                and descriptor.independence == "actor"
  +                and descriptor.capability_id == member["capability_id"]
  +                and descriptor.source_sha256 == member["descriptor_sha256"]
  +                and descriptor.input_contract == input_contract["id"]
  +                and descriptor.output_contract == output_contract["id"]
  +                and list(descriptor.authority_required) == list(member["authority_required"])
  +                and isinstance(need_kinds, (list, tuple))
  +                and list(need_kinds) == list(member["need_kinds"])
  +                and descriptor.metadata.get("non_mutating") in {True, "true"},
  +                "HOST_CAPABILITY_REGISTRY_INVALID",
  +            )
  +            for contract in (input_contract, output_contract):
  +                contract_path = self._host_file(root, contract["id"])
  +                repository_contract_path = self._host_file(self.plugin_root, contract["id"])
  +                contract_sha256 = _file_sha256(contract_path)
  +                _require(
  +                    contract_sha256 == contract["sha256"]
  +                    and _file_sha256(repository_contract_path) == contract_sha256,
  +                    "HOST_CAPABILITY_REGISTRY_INVALID",
  +                )
  +            entries.append(deepcopy(dict(entry)))
  +        return str(catalog["catalog_sha256"]), entries
  +
  +    @staticmethod
  +    def _durable_capability_need(manifest: MissionManifest, expected_revision: int) -> dict[str, Any]:
  +        blockers = manifest.state.get("blockers")
  +        frontier = manifest.state.get("current_frontier")
  +        _require(
  +            manifest.state.get("status") == "blocked"
  +            and isinstance(blockers, list)
  +            and bool(blockers)
  +            and isinstance(frontier, list)
  +            and bool(frontier)
  +            and _nonempty(frontier[0]),
  +            "CAPABILITY_REQUEST_INVALID",
  +        )
  +        records = [
  +            item
  +            for item in manifest.continuity.get("decisions", [])
  +            if isinstance(item, Mapping)
  +            and item.get("kind") == "capability-need"
  +            and isinstance(item.get("need"), Mapping)
  +            and item["need"].get("blocking_condition") == frontier[0]
  +            and item["need"].get("blocking_condition") in blockers
  +            and isinstance(item["need"].get("return_point"), Mapping)
  +            and item["need"]["return_point"].get("revision") == expected_revision
  +        ]
  +        _require(len(records) == 1 and set(records[0]) == {"kind", "need"}, "CAPABILITY_REQUEST_INVALID")
  +        need = records[0].get("need")
  +        _require(
  +            _closed(need, _CAPABILITY_NEED_FIELDS)
  +            and need.get("schema") == "capability-need@1"
  +            and all(_nonempty(need.get(field)) for field in ("need_id", "blocking_condition", "need_kind", "timeout_or_stop_condition"))
  +            and all(_nonempty_string_list(need.get(field)) for field in ("evidence_scope", "required_permissions", "expected_effects", "estimated_costs"))
  +            and len(need["evidence_scope"]) == 1
  +            and list(need["expected_effects"]) == list(need["evidence_scope"]),
  +            "CAPABILITY_REQUEST_INVALID",
  +        )
  +        point = need.get("return_point")
  +        _require(
  +            _closed(point, {"mission_id", "revision", "frontier_index", "label"})
  +            and point.get("mission_id") == manifest.mission_id
  +            and point.get("revision") == expected_revision
  +            and point.get("frontier_index") == 0
  +            and point.get("label") == need["blocking_condition"]
  +            and frontier[0] == need["blocking_condition"]
  +            and need["blocking_condition"] in blockers,
  +            "CAPABILITY_RETURN_POINT_MISMATCH",
  +        )
  +        return deepcopy(dict(need))
  +
  +    @staticmethod
  +    def _select_host_member(entries: list[dict[str, Any]], need: Mapping[str, Any]) -> dict[str, Any]:
  +        capability_ids = [str(entry["member_binding"]["capability_id"]) for entry in entries]
  +        if len(capability_ids) != len(set(capability_ids)):
  +            raise ControllerError("CAPABILITY_DESCRIPTOR_UNAVAILABLE")
  +        matches = [
  +            entry
  +            for entry in entries
  +            if entry["availability"] == "available"
  +            and entry["degradation_reason"] is None
  +            and need["need_kind"] in entry["member_binding"]["need_kinds"]
  +            and entry["member_binding"]["input_contract"]["id"] == _CAPABILITY_REQUEST_CONTRACT
  +            and entry["member_binding"]["output_contract"]["id"] == _CAPABILITY_RESULT_CONTRACT
  +            and entry["member_binding"]["authority_required"] == need["required_permissions"]
  +            and entry["member_binding"]["non_mutating"] is True
  +        ]
  +        if not matches:
  +            raise ControllerError("CAPABILITY_DESCRIPTOR_UNAVAILABLE")
  +        if len(matches) != 1:
  +            raise ControllerError("CAPABILITY_SELECTION_AMBIGUOUS")
  +        return deepcopy(matches[0])
  +
  +    @staticmethod
  +    def _capability_record(manifest: MissionManifest, grant_id: str) -> Mapping[str, Any]:
  +        records = [item for item in manifest.capabilities.get("invoked", []) if isinstance(item, Mapping) and item.get("grant_id") == grant_id]
  +        if len(records) != 1:
  +            raise ControllerError("CAPABILITY_GRANT_NOT_FOUND")
  +        return records[0]
  +
  +    def _issue_host_capability(self, binding: HostBinding) -> dict[str, Any]:
  +        self._host_registry()
  +        discovered = self._discover(binding.workspace_root)
  +        unknown_marker = _capability_effect_unknown_marker(discovered.manifest)
  +        if unknown_marker is not None:
  +            raise ControllerError(unknown_marker)
  +        manifest = discovered.manifest
  +        need = self._durable_capability_need(manifest, manifest.revision + 1)
  +        issue_catalog_sha256, entries = self._observe_host_members(binding)
  +        member = self._select_host_member(entries, need)["member_binding"]
  +        authority_errors = authorize_action(manifest, str(member["capability_id"]), need["required_permissions"], need["expected_effects"], need["estimated_costs"])
  +        if authority_errors:
  +            raise ControllerError(authority_errors[0])
  +        try:
  +            grant = issue_grant(
  +                {
  +                    "mission_id": manifest.mission_id,
  +                    "mission_revision": manifest.revision + 1,
  +                    "capability_id": member["capability_id"],
  +                    "capability_descriptor_sha256": member["descriptor_sha256"],
  +                    "blocking_condition": need["blocking_condition"],
  +                    "return_point": deepcopy(need["return_point"]),
  +                    "admitted_operation": _HOST_MEMBER_OPERATION,
  +                    "evidence_scope": list(need["evidence_scope"]),
  +                    "mutation": False,
  +                    "expires_after_use": True,
  +                }
  +            )
  +        except CapabilityGrantError as error:
  +            raise ControllerError(str(error)) from error
  +        request_id = f"capability-request:{grant['grant_id']}"
  +        request = {
  +            "schema": "capability-request@1",
  +            "request_id": request_id,
  +            "mission_id": manifest.mission_id,
  +            "mission_revision": manifest.revision + 1,
  +            "capability_id": member["capability_id"],
  +            "capability_source_sha256": member["descriptor_sha256"],
  +            "bounded_question_or_action": need["blocking_condition"],
  +            "authority_receipt": f"checkpoint-sha256:{discovered.receipt.sha256}",
  +            "expected_output_contract": member["output_contract"]["id"],
  +            "return_point": deepcopy(need["return_point"]),
  +            "timeout_or_stop_condition": need["timeout_or_stop_condition"],
  +        }
  +        grant.update(
  +            {
  +                "need_id": need["need_id"],
  +                "need_sha256": _canonical_sha256(need),
  +                "member_binding": deepcopy(dict(member)),
  +                "issue_catalog_sha256": issue_catalog_sha256,
  +                "request_id": request_id,
  +                "request_sha256": _canonical_sha256(request),
  +            }
  +        )
  +        try:
  +            updated = apply_event_data(manifest, "record_capability_request", "mission-steward:capability", {"grant": grant, "request": request})
  +        except TransitionError as error:
  +            raise ControllerError(str(error)) from error
  +        checkpoint = self._store(binding.workspace_root, manifest.mission_id).save(updated)
  +        return {"status": "capability-issued", "grant_id": str(grant["grant_id"]), "grant": deepcopy(grant), "checkpoint_ref": checkpoint.path, "checkpoint_sha256": checkpoint.sha256}
  +
  +    def _host_result_from_receipt(
  +        self,
  +        receipt: object,
  +        *,
  +        binding: HostBinding,
  +        issue_catalog_sha256: str,
  +        execute_catalog_sha256: str,
  +        member: Mapping[str, Any],
  +        grant_id: str,
  +        execution_attempt_id: str,
  +        request: Mapping[str, Any],
  +    ) -> tuple[dict[str, Any], dict[str, Any]]:
  +        _require(
  +            _closed(receipt, _HOST_RECEIPT_FIELDS)
  +            and receipt.get("schema") == "host-capability-invocation-receipt@1"
  +            and receipt.get("invocation_status") == "completed"
  +            and _nonempty(receipt.get("result_json"))
  +            and _is_sha256(receipt.get("result_sha256"))
  +            and _nonempty(receipt.get("external_durable_receipt_ref"))
  +            and _nonempty_string_list(receipt.get("host_coverage_limits")),
  +            "CAPABILITY_INVOCATION_RECEIPT_INVALID",
  +        )
  +        request_bytes = _canonical_bytes(request)
  +        _require(
  +            receipt.get("host_binding") == _host_binding_payload(binding)
  +            and receipt.get("issue_catalog_sha256") == issue_catalog_sha256
  +            and receipt.get("execute_catalog_sha256") == execute_catalog_sha256
  +            and receipt.get("member_binding") == member
  +            and receipt.get("grant_id") == grant_id
  +            and receipt.get("execution_attempt_id") == execution_attempt_id
  +            and receipt.get("request_id") == request.get("request_id")
  +            and receipt.get("request_sha256") == hashlib.sha256(request_bytes).hexdigest()
  +            and receipt.get("returned_control_point") == request.get("return_point"),
  +            "CAPABILITY_INVOCATION_BINDING_MISMATCH",
  +        )
  +        try:
  +            result = json.loads(str(receipt["result_json"]))
  +        except json.JSONDecodeError as error:
  +            raise ControllerError("CAPABILITY_INVOCATION_RECEIPT_INVALID") from error
  +        _require(isinstance(result, dict), "CAPABILITY_INVOCATION_RECEIPT_INVALID")
  +        result_bytes = _canonical_bytes(result)
  +        _require(
  +            str(receipt["result_json"]).encode("utf-8") == result_bytes
  +            and receipt["result_sha256"] == hashlib.sha256(result_bytes).hexdigest(),
  +            "CAPABILITY_INVOCATION_RECEIPT_INVALID",
  +        )
  +        return deepcopy(result), deepcopy(dict(receipt))
  +
  +    def _execute_host_capability(self, binding: HostBinding, grant_id: str) -> dict[str, Any]:
  +        registry = self._host_registry()
  +        discovered = self._discover(binding.workspace_root)
  +        manifest = discovered.manifest
  +        unknown_marker = _capability_effect_unknown_marker(manifest)
  +        if unknown_marker is not None:
  +            raise ControllerError(unknown_marker)
  +        record = self._capability_record(manifest, grant_id)
  +        if record.get("result") is not None:
  +            raise ControllerError("CAPABILITY_RESULT_REPLAY")
  +        if record.get("execution_state") == "in_progress":
  +            raise ControllerError("CAPABILITY_EXECUTION_IN_PROGRESS")
  +        if record.get("execution_state") != "pending":
  +            raise ControllerError("CAPABILITY_GRANT_NOT_PENDING")
  +        grant = record.get("grant")
  +        request = record.get("request")
  +        _require(isinstance(grant, Mapping) and isinstance(request, Mapping), "CAPABILITY_REQUEST_INVALID")
  +        need = self._durable_capability_need(manifest, manifest.revision)
  +        member = grant.get("member_binding")
  +        output_contract = member.get("output_contract") if isinstance(member, Mapping) else None
  +        scope = grant.get("evidence_scope")
  +        _require(
  +            _closed(member, _HOST_MEMBER_FIELDS)
  +            and isinstance(output_contract, Mapping)
  +            and isinstance(scope, list)
  +            and len(scope) == 1
  +            and grant.get("grant_id") == grant_id
  +            and grant.get("mission_id") == manifest.mission_id
  +            and grant.get("mission_revision") == manifest.revision
  +            and grant.get("admitted_operation") == _HOST_MEMBER_OPERATION
  +            and grant.get("mutation") is False
  +            and grant.get("need_id") == need["need_id"]
  +            and grant.get("need_sha256") == _canonical_sha256(need)
  +            and grant.get("blocking_condition") == need["blocking_condition"]
  +            and grant.get("return_point") == need["return_point"]
  +            and scope == need["evidence_scope"]
  +            and _is_sha256(grant.get("issue_catalog_sha256"))
  +            and set(request) == _CAPABILITY_REQUEST_FIELDS
  +            and request.get("schema") == "capability-request@1"
  +            and _nonempty(request.get("authority_receipt"))
  +            and request.get("request_id") == grant.get("request_id")
  +            and request.get("mission_id") == manifest.mission_id
  +            and request.get("mission_revision") == manifest.revision
  +            and request.get("capability_id") == member.get("capability_id")
  +            and request.get("capability_source_sha256") == member.get("descriptor_sha256")
  +            and request.get("bounded_question_or_action") == need["blocking_condition"]
  +            and request.get("expected_output_contract") == output_contract.get("id")
  +            and request.get("return_point") == need["return_point"]
  +            and request.get("timeout_or_stop_condition") == need["timeout_or_stop_condition"]
  +            and grant.get("request_sha256") == _canonical_sha256(request),
  +            "CAPABILITY_REQUEST_INVALID",
  +        )
  +        execute_catalog_sha256, entries = self._observe_host_members(binding)
  +        selected = self._select_host_member(entries, need)
  +        if selected["member_binding"] != member:
  +            raise ControllerError("CAPABILITY_DESCRIPTOR_MISMATCH")
  +        authority_errors = authorize_action(manifest, str(member["capability_id"]), need["required_permissions"], need["expected_effects"], need["estimated_costs"])
  +        if authority_errors:
  +            raise ControllerError(authority_errors[0])
  +        store = self._store(binding.workspace_root, manifest.mission_id)
  +        try:
  +            begun = apply_event_data(
  +                manifest,
  +                "begin_capability_execution",
  +                "mission-steward:capability",
  +                {"grant_id": grant_id, "operation": _HOST_MEMBER_OPERATION, "target": scope[0], "evidence_refs": list(scope), "execution_owner_id": self.process_instance_id},
  +            )
  +        except TransitionError as error:
  +            raise ControllerError(str(error)) from error
  +        store.save(begun)
  +        execution_attempt_id = self._capability_record(begun, grant_id).get("execution_attempt_id")
  +        _require(_nonempty(execution_attempt_id), "CAPABILITY_EXECUTION_STATE_INVALID")
  +        request_bytes = _canonical_bytes(request)
  +        try:
  +            raw_receipt = registry.invoke_member_capability(binding, str(member["invocation_ref"]), grant_id, str(execution_attempt_id), request_bytes)
  +        except Exception as error:
  +            raise ControllerError("CAPABILITY_INVOCATION_UNAVAILABLE") from error
  +        result, receipt = self._host_result_from_receipt(
  +            raw_receipt,
  +            binding=binding,
  +            issue_catalog_sha256=str(grant["issue_catalog_sha256"]),
  +            execute_catalog_sha256=execute_catalog_sha256,
  +            member=member,
  +            grant_id=grant_id,
  +            execution_attempt_id=str(execution_attempt_id),
  +            request=request,
  +        )
  +        try:
  +            updated = apply_event_data(
  +                begun,
  +                "record_capability_result",
  +                "capability:result",
  +                {"grant_id": grant_id, "result": result, "host_invocation_receipt": receipt},
  +            )
  +        except TransitionError as error:
  +            raise ControllerError(str(error)) from error
  +        checkpoint = store.save(updated)
  +        return {"status": "capability-executed", "grant_id": grant_id, "result": deepcopy(result), "checkpoint_ref": checkpoint.path, "checkpoint_sha256": checkpoint.sha256}
  +
       def manifest_engage(
  @@ -590,15 +1031,20 @@
       def manifest_capability_issue(
           self,
           *,
  -        capability_id: str,
  -        blocking_condition: str,
  -        admitted_operation: str,
  -        evidence_scope: list[str],
  -        request: Mapping[str, Any],
  +        capability_id: str | None = None,
  +        blocking_condition: str | None = None,
  +        admitted_operation: str | None = None,
  +        evidence_scope: list[str] | None = None,
  +        request: Mapping[str, Any] | None = None,
           _host_context_ref: str | None = None,
           _host_gate_ref: str | None = None,
       ) -> dict[str, Any]:
           binding = self._binding("manifest_capability_issue", _host_context_ref, _host_gate_ref)
           if binding.gate.lock_reason not in {"explicit-manifest-intent", "unfinished-durable-mission", "unfinished-mission-integrity-error", "bootstrap-recovery"}:
               raise ControllerError("MANIFEST_ENGAGEMENT_LOCKED")
  +        selection_fields = (capability_id, blocking_condition, admitted_operation, evidence_scope, request)
  +        if all(value is None for value in selection_fields):
  +            return self._issue_host_capability(binding)
  +        if any(value is None for value in selection_fields):
  +            raise ControllerError("CAPABILITY_REQUEST_INVALID")
           if not _nonempty(admitted_operation):
  @@ -743,17 +1189,19 @@
       def manifest_capability_execute(
           self,
           *,
           grant_id: str,
  -        operation: str,
  -        target: str,
  +        operation: str | None = None,
  +        target: str | None = None,
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
  +        if operation is None and target is None and evidence_refs is None and evidence_payload is None:
  +            return self._execute_host_capability(binding, grant_id)
           if not _nonempty(operation):
  diff --git a/practical_agency/state_machine.py b/practical_agency/state_machine.py
  --- a/practical_agency/state_machine.py
  +++ b/practical_agency/state_machine.py
  @@ -217,11 +217,16 @@
   _CAPABILITY_RESULT_STATUSES = {"completed", "declined", "blocked", "failed"}
  +_HOST_CAPABILITY_RECEIPT_FIELDS = {"schema", "host_binding", "issue_catalog_sha256", "execute_catalog_sha256", "member_binding", "grant_id", "execution_attempt_id", "request_id", "request_sha256", "invocation_status", "result_json", "result_sha256", "returned_control_point", "external_durable_receipt_ref", "host_coverage_limits"}
   
   
   def _canonical_mapping_sha256(value: Mapping[str, Any]) -> str:
       encoded = json.dumps(
           value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
       ).encode("utf-8")
       return hashlib.sha256(encoded).hexdigest()
   
   
  +def _is_sha256(value: object) -> bool:
  +    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)
  +
  +
   def _validate_manifest_milestone_contract(
  @@ -800,63 +805,109 @@
       elif event.kind == "record_capability_result":
  -        if set(payload) != {"grant_id", "result"}:
  +        allowed_payloads = (
  +            {"grant_id", "result"},
  +            {"grant_id", "result", "host_invocation_receipt"},
  +        )
  +        if set(payload) not in allowed_payloads:
               raise TransitionError("CAPABILITY_RESULT_EVENT_INVALID")
           grant_id = payload.get("grant_id")
           result = payload.get("result")
  +        host_receipt = payload.get("host_invocation_receipt")
           if not isinstance(grant_id, str) or not isinstance(result, Mapping):
               raise TransitionError("CAPABILITY_RESULT_REQUIRED")
           invoked = [item for item in data["capabilities"].get("invoked", []) if isinstance(item, Mapping) and item.get("grant_id") == grant_id]
           if len(invoked) != 1:
               raise TransitionError("CAPABILITY_GRANT_NOT_FOUND")
           record = invoked[0]
           if record.get("result") is not None:
               raise TransitionError("CAPABILITY_RESULT_REPLAY")
           grant = record.get("grant")
  +        request = record.get("request")
           if not isinstance(grant, Mapping) or result.get("returned_control_point") != grant.get("return_point"):
               raise TransitionError("CAPABILITY_RETURN_POINT_MISMATCH")
   
           execution_state = record.get("execution_state")
           if execution_state is not None:
               if execution_state != "in_progress":
                   raise TransitionError("CAPABILITY_GRANT_NOT_IN_PROGRESS")
  -            request = record.get("request")
               artifact_refs = result.get("artifact_refs")
               coverage_limits = result.get("coverage_limits")
               verdict = result.get("verdict")
               if (
                   not isinstance(request, Mapping)
                   or set(result) - _CAPABILITY_RESULT_ALLOWED_FIELDS
                   or not _CAPABILITY_RESULT_REQUIRED_FIELDS.issubset(result)
                   or result.get("schema") != "capability-result@1"
                   or result.get("request_id") != request.get("request_id")
                   or result.get("status") not in _CAPABILITY_RESULT_STATUSES
                   or (
                       verdict is not None
                       and (not isinstance(verdict, str) or not verdict.strip())
                   )
                   or not isinstance(artifact_refs, list)
                   or not artifact_refs
                   or any(
                       not isinstance(item, str) or not item.strip()
                       for item in artifact_refs
                   )
                   or not isinstance(result.get("observed_effects"), list)
                   or not isinstance(coverage_limits, list)
                   or not coverage_limits
                   or any(
                       not isinstance(item, str) or not item.strip()
                       for item in coverage_limits
                   )
                   or result.get("returned_control_point")
                   != request.get("return_point")
               ):
                   raise TransitionError("CAPABILITY_RESULT_INVALID")
               evidence_refs = list(artifact_refs)
               record["execution_state"] = "consumed"
           else:
               evidence_refs = result.get("evidence_refs")
               if not isinstance(evidence_refs, list) or not evidence_refs:
                   raise TransitionError("CAPABILITY_EVIDENCE_REQUIRED")
   
  +        external_receipt_ref: str | None = None
  +        member_binding = grant.get("member_binding")
  +        if member_binding is not None:
  +            canonical_result = json.dumps(dict(result), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
  +            host_binding = host_receipt.get("host_binding") if isinstance(host_receipt, Mapping) else None
  +            host_coverage = host_receipt.get("host_coverage_limits") if isinstance(host_receipt, Mapping) else None
  +            if (
  +                not isinstance(request, Mapping)
  +                or not isinstance(host_receipt, Mapping)
  +                or set(host_receipt) != _HOST_CAPABILITY_RECEIPT_FIELDS
  +                or host_receipt.get("schema") != "host-capability-invocation-receipt@1"
  +                or not isinstance(host_binding, Mapping)
  +                or set(host_binding) != {"session_id", "turn_id", "workspace_root", "context_nonce_sha256"}
  +                or any(not isinstance(host_binding.get(field), str) or not host_binding[field].strip() for field in ("session_id", "turn_id", "workspace_root"))
  +                or not _is_sha256(host_binding.get("context_nonce_sha256"))
  +                or not _is_sha256(host_receipt.get("issue_catalog_sha256"))
  +                or host_receipt.get("issue_catalog_sha256") != grant.get("issue_catalog_sha256")
  +                or not _is_sha256(host_receipt.get("execute_catalog_sha256"))
  +                or host_receipt.get("member_binding") != member_binding
  +                or host_receipt.get("grant_id") != grant_id
  +                or host_receipt.get("execution_attempt_id") != record.get("execution_attempt_id")
  +                or host_receipt.get("request_id") != request.get("request_id")
  +                or host_receipt.get("request_sha256") != _canonical_mapping_sha256(request)
  +                or host_receipt.get("invocation_status") != "completed"
  +                or host_receipt.get("result_json") != canonical_result
  +                or host_receipt.get("result_sha256") != _canonical_mapping_sha256(result)
  +                or host_receipt.get("returned_control_point") != request.get("return_point")
  +                or not isinstance(host_coverage, list)
  +                or not host_coverage
  +                or any(not isinstance(item, str) or not item.strip() for item in host_coverage)
  +                or not isinstance(host_receipt.get("external_durable_receipt_ref"), str)
  +                or not host_receipt["external_durable_receipt_ref"].strip()
  +            ):
  +                raise TransitionError("CAPABILITY_INVOCATION_RECEIPT_INVALID")
  +            external_receipt_ref = str(host_receipt["external_durable_receipt_ref"])
  +            record["host_invocation_receipt"] = deepcopy(dict(host_receipt))
  +        elif host_receipt is not None:
  +            raise TransitionError("CAPABILITY_INVOCATION_RECEIPT_INVALID")
  +
           record["result"] = deepcopy(dict(result))
  +        if external_receipt_ref is not None:
  +            _append_unique(continuity["durable_artifacts"], external_receipt_ref)
           _append_unique(continuity["durable_artifacts"], f"capability-result:{grant_id}")
           continuity["decisions"].append({"kind": "capability-result", "actor_ref": event.actor_ref, "grant_id": grant_id, "verdict": result.get("verdict"), "coverage_limits": deepcopy(result.get("coverage_limits", [])), "evidence_refs": deepcopy(evidence_refs)})
evidence: |
  REQUIREMENT-TO-HUNK MATRIX — source-derived; no tests or runtime probes were run.
  
  1. Fail-closed absent default and exact reserved seam
     Hunks: practical_agency/controller.py @@ -59,5 +60,11 @@ and @@ -341,3 +380,9 @@.
     Mapping: HostCapabilityRegistry exposes only observe_member_capabilities, invoke_member_capability, and lookup_member_invocation. ManifestController accepts the reserved dependency optionally; _host_registry returns exactly HOST_CAPABILITY_REGISTRY_UNAVAILABLE when absent and HOST_CAPABILITY_REGISTRY_INVALID when the injected object does not expose the closed protocol.
  
  2. Host-attested external catalog, installed-byte verification, and derived selection
     Hunk: practical_agency/controller.py @@ -391,3 +436,399 @@.
     Mapping: the issue/execute observations are bound to the exact HostBinding and canonical catalog digest; each catalog entry is closed, separately rooted from plugin_root, symlink-safe, descriptor-digest checked, parsed through FileSystemSkillProvider/discover_capabilities, constrained to external actor-owned skill metadata, and bound to request/result contract bytes that equal the repository's strict contracts. Duplicate capability IDs fail closed. The selected member is the sole available non-mutating member whose need kind, authority, and contracts exactly satisfy the current blocked frontier's capability-need@1.
  
  3. Durable need, member, catalog, request, and return-point grant binding
     Hunk: practical_agency/controller.py @@ -391,3 +436,399 @@.
     Mapping: _issue_host_capability authorizes the typed need, issues the existing one-use non-mutating grant, and adds need_id/need_sha256, the exact closed member_binding, issue_catalog_sha256, request_id, and request_sha256. The strict capability-request@1 uses the blocker as its bounded action and preserves the durable return point.
  
  4. Caller-free issue with legacy compatibility only on the old complete argument set
     Hunk: practical_agency/controller.py @@ -590,15 +1031,20 @@.
     Mapping: all five old selection fields default to None. Supplying none enters the host transaction; supplying only some fails CAPABILITY_REQUEST_INVALID; supplying all preserves the existing local-read path unchanged. No member root, invocation handle, catalog, request, or result is accepted from that caller-free branch.
  
  5. Grant-only, one-shot member invocation with no local fallback
     Hunks: practical_agency/controller.py @@ -391,3 +436,399 @@ and @@ -743,17 +1189,19 @@.
     Mapping: grant-only execute enters _execute_host_capability. It validates the durable need/grant/request chain, re-observes the catalog and exact member, checkpoints begin_capability_execution with the existing execution_attempt_id/owner/used-grant machinery, then calls invoke_member_capability exactly once with invocation_ref, grant_id, attempt ID, and canonical request bytes. The normal path never calls lookup_member_invocation or execute_read. Invocation or receipt failure occurs only after the durable in_progress checkpoint, preserving existing orphan-to-unknown recovery.
  
  6. Exact member-owned result and receipt persistence
     Hunks: practical_agency/controller.py @@ -391,3 +436,399 @@, practical_agency/state_machine.py @@ -217,11 +217,16 @@, and @@ -800,63 +805,109 @@.
     Mapping: the controller requires the closed host-capability-invocation-receipt@1, binds both catalog digests, host binding, member, grant, attempt, request digest, result digest, and return point, and requires result_json to already be canonical UTF-8 JSON. The state transition accepts the receipt only for a member-bound grant, rechecks its durable bindings, stores it unchanged as host_invocation_receipt, appends external_durable_receipt_ref, and stores the parsed strict result without synthesizing or rewriting verdict, coverage, artifacts, effects, request identity, or return point.
  
  7. Prior behavior and exclusions
     Hunks: all.
     Mapping: no test, MCP schema, validation model, capability operation, engage/orphan branch, web path, proof path, principal logic, shell path, mutation path, or adapter is modified. The existing two-field record_capability_result payload and old local issue/execute bodies remain valid for prior focused tests.
requirements: |
  - Stage 10 production-only scope: implemented by changes only to practical_agency/controller.py and practical_agency/state_machine.py.
  - Fail-closed absent registry: implemented with ControllerError("HOST_CAPABILITY_REGISTRY_UNAVAILABLE") before mission discovery, catalog observation, checkpoint mutation, or target observation.
  - Reserved fake protocol seam: implemented with the exact catalog/invoke/lookup method surface and no concrete Codex adapter.
  - Blocker-derived typed need: implemented from the current blocked frontier and its uniquely matching closed capability-need@1; no caller selection or tie-break is used on the host branch.
  - External member ownership: implemented with separate-root, descriptor, persistence, independence, authority, need-kind, non-mutation, invocation-ref, and strict contract-byte binding.
  - Durable grant and request: implemented with need, member, issue catalog, request digest, mutation-false, one-use, mission revision, and return-point binding.
  - Grant-only execution: implemented; the old operation/target/evidence fields are optional only to admit the host branch, while complete legacy calls preserve prior behavior.
  - One invocation and no fallback: implemented by checkpointing begin before one invoke_member_capability call and never entering lookup_member_invocation or execute_read on the normal host path.
  - Exact FAIL preservation: implemented by requiring canonical receipt result bytes and persisting the exact parsed capability-result@1 and coverage without synthesis.
  - Durable receipt: implemented as host_invocation_receipt with external_durable_receipt_ref retained in continuity.durable_artifacts.
  - Existing one-use/replay/orphan controls: preserved through the existing issue_grant, begin_capability_execution, consume_grant, result replay, and unchanged manifest_engage unknown-effect path.
  - Exclusions: no real host adapter, caller root/handle/result, web enablement, whole-mission proof integration, principal change, shell, mutation, test modification, execution, publication, merge, or message.
decisions_and_assumptions: |
  - Treat host_capability_registry as reserved constructor wiring, not a public MCP field. None is the only default and is intentionally unavailable.
  - Require all three reserved methods even though lookup_member_invocation remains unused on the normal Stage 10 path; replacement-process receipt reconciliation remains a later stage.
  - Bind owner_runtime_sha256 exactly as host attestation but do not invent a universal package-hash algorithm. Independently verify the descriptor and both strict contract byte digests that the repository consumer can observe.
  - Require the external member root to be canonical, non-symlinked, and disjoint from plugin_root; persist no root in the grant or receipt member_binding.
  - Reuse issue_grant and the existing begin transition with an internal host.member.invoke operation so one-use consumption, durable execution_attempt_id, owner binding, and orphan recovery remain unchanged.
  - Require a host receipt whenever a grant carries member_binding; reject a host receipt on a legacy grant. This closes direct member-result injection while retaining the existing legacy result event shape.
  - Preserve the legacy caller-selected local-read path only when all five prior issue arguments and the prior execute arguments are supplied. The host-member branch accepts none of them.
  - No tests or runtime probes were run, as required.
blockers_or_questions: NONE
recommended_next_action: |
  Apply this diff at 993efd0fbc920a8345f79b25fd81413b4a96220b and run python -m unittest tests.test_host_member_capability_transaction.HostMemberCapabilityTransactionRedTest.test_host_member_is_selected_from_durable_blocker_and_receipt_bound -v once.
