schema: outsource-relay@1
work_id: durable-capability-transaction
based_on_commit: 634d6a1334fe2cc21b8ac64f391abbd70623bd51
status: PARTIAL
summary: |
  Production-only Stage 2 patch derived from the committed RED evidence. It replaces caller-carried grant execution with canonical grant_id lookup, persists and consumes a one-use request-bound grant before observation, emits strict capability request/result records, removes request/result/grant injection from MCP, refuses web transport before retrieval, and routes reason-bearing FAIL and INCONCLUSIVE verdicts through the existing reject transition. Tests were not run.
work_product: |
  diff --git a/practical_agency/capability_operations.py b/practical_agency/capability_operations.py
  --- a/practical_agency/capability_operations.py
  +++ b/practical_agency/capability_operations.py
  @@ -108,6 +108,17 @@ def execute_read(
           if not isinstance(evidence_payload, Mapping) or not isinstance(evidence_payload.get(source_ref), str):
               raise CapabilityOperationError("SOURCE_EVIDENCE_REQUIRED")
   
  +    try:
  +        result = consume_grant(
  +            grant,
  +            mission_id=mission_id,
  +            mission_revision=mission_revision,
  +            operation=operation,
  +            evidence_refs=refs or [f"file:{target}"],
  +            return_point=return_point,
  +        )
  +    except CapabilityGrantError as error:
  +        raise CapabilityOperationError(str(error)) from error
  +
       observed: list[dict[str, Any]] = []
       if operation in {"file.read", "resource.read"}:
           raw_target = target.removeprefix("resource:") if operation == "resource.read" else target
  @@ -128,17 +139,6 @@ def execute_read(
       else:
           raise CapabilityOperationError("OPERATION_NOT_READ_ONLY")
   
  -    try:
  -        result = consume_grant(
  -            grant,
  -            mission_id=mission_id,
  -            mission_revision=mission_revision,
  -            operation=operation,
  -            evidence_refs=refs or [f"file:{target}"],
  -            return_point=return_point,
  -        )
  -    except CapabilityGrantError as error:
  -        raise CapabilityOperationError(str(error)) from error
  -
       result["observed_effects"] = observed
       return result
  diff --git a/practical_agency/controller.py b/practical_agency/controller.py
  --- a/practical_agency/controller.py
  +++ b/practical_agency/controller.py
  @@ -7,14 +7,20 @@ from copy import deepcopy
   from pathlib import Path
   from typing import Any, Mapping
   from uuid import uuid4
   
  +from practical_agency.authority import authorize_action
  +from practical_agency.capability_discovery import (
  +    CapabilityDescriptor,
  +    FileSystemSkillProvider,
  +    discover_capabilities,
  +)
  +from practical_agency.capability_grants import (
  +    CapabilityGrantError,
  +    issue_grant_from_descriptor,
  +)
  +from practical_agency.capability_operations import CapabilityOperationError, execute_read
   from practical_agency.checkpoint_store import (
       FileCheckpointStore,
       ReconciliationFinding,
       apply_reconciliation_findings,
   )
   from practical_agency.coordinator import CoordinationError, coordinate_once, dispatch_once
  -from practical_agency.capability_operations import CapabilityOperationError, execute_read
  -from practical_agency.capability_discovery import FileSystemSkillProvider, discover_capabilities
  -from practical_agency.capability_grants import CapabilityGrantError, issue_grant_from_descriptor
   from practical_agency.filesystem_artifact import (
       FilesystemArtifactAdapter,
       FilesystemArtifactError,
  @@ -65,6 +71,32 @@ _LIST_FIELDS = (
       "stop_conditions",
   )
   
  +_CAPABILITY_INTENT_FIELDS = {
  +    "bounded_question_or_action",
  +    "requested_permissions",
  +    "requested_effects",
  +    "estimated_costs",
  +    "timeout_or_stop_condition",
  +}
  +_CAPABILITY_REQUEST_FIELDS = {
  +    "schema",
  +    "request_id",
  +    "mission_id",
  +    "mission_revision",
  +    "capability_id",
  +    "capability_source_sha256",
  +    "bounded_question_or_action",
  +    "authority_receipt",
  +    "expected_output_contract",
  +    "return_point",
  +    "timeout_or_stop_condition",
  +}
  +_CAPABILITY_REQUEST_CONTRACT = "contracts/capability-request.schema.json"
  +_CAPABILITY_RESULT_CONTRACT = "contracts/capability-result.schema.json"
  +_READ_AUTHORITY = {
  +    "file.read": ("repository:read", "bounded reads"),
  +    "resource.read": ("repository:read", "bounded reads"),
  +}
  +
   
   def _canonical_sha256(value: Mapping[str, Any]) -> str:
       encoded = json.dumps(
  @@ -77,6 +109,15 @@ def _nonempty(value: object) -> bool:
       return isinstance(value, str) and bool(value.strip())
   
   
  +def _nonempty_string_list(value: object) -> bool:
  +    return (
  +        isinstance(value, list)
  +        and bool(value)
  +        and all(_nonempty(item) for item in value)
  +    )
  +
  +
   def _sha256_text(value: str) -> str:
       return hashlib.sha256(value.encode("utf-8")).hexdigest()
   
  @@ -326,14 +367,24 @@ class ManifestController:
               workspace / "missions" / mission_id / "checkpoints"
           )
   
  -    def _observed_descriptor(self, capability_id: object, descriptor_digest: object) -> None:
  +    def _descriptor(self, capability_id: object) -> CapabilityDescriptor:
           descriptors = discover_capabilities([FileSystemSkillProvider(self.plugin_root / "skills")])
           matches = [item for item in descriptors if item.capability_id == capability_id]
           if len(matches) != 1 or matches[0].availability != "available":
               raise ControllerError("CAPABILITY_DESCRIPTOR_UNAVAILABLE")
  -        if matches[0].source_sha256 != descriptor_digest:
  +        return matches[0]
  +
  +    def _observed_descriptor(
  +        self,
  +        capability_id: object,
  +        descriptor_digest: object,
  +    ) -> CapabilityDescriptor:
  +        descriptor = self._descriptor(capability_id)
  +        if descriptor.source_sha256 != descriptor_digest:
               raise ControllerError("CAPABILITY_DESCRIPTOR_MISMATCH")
  +        return descriptor
   
       def manifest_engage(
           self,
  @@ -500,20 +551,115 @@ class ManifestController:
           if binding.gate.lock_reason not in {"explicit-manifest-intent", "unfinished-durable-mission", "unfinished-mission-integrity-error", "bootstrap-recovery"}:
               raise ControllerError("MANIFEST_ENGAGEMENT_LOCKED")
  +        if not _nonempty(admitted_operation):
  +            raise ControllerError("OPERATION_NOT_READ_ONLY")
  +        if admitted_operation.startswith("web."):
  +            raise ControllerError("WEB_OPERATION_DISABLED")
  +        authority_rule = _READ_AUTHORITY.get(admitted_operation)
  +        if authority_rule is None:
  +            raise ControllerError("OPERATION_NOT_READ_ONLY")
  +        if (
  +            not _nonempty(capability_id)
  +            or not _nonempty(blocking_condition)
  +            or not _nonempty_string_list(evidence_scope)
  +            or len(evidence_scope) != 1
  +        ):
  +            raise ControllerError("CAPABILITY_REQUEST_INVALID")
  +
           discovered = self._discover(binding.workspace_root)
  -        descriptors = discover_capabilities([FileSystemSkillProvider(self.plugin_root / "skills")])
  -        matches = [item for item in descriptors if item.capability_id == capability_id]
  -        if len(matches) != 1 or matches[0].availability != "available":
  -            raise ControllerError("CAPABILITY_DESCRIPTOR_UNAVAILABLE")
  +        descriptor = self._descriptor(capability_id)
  +        if (
  +            descriptor.input_contract != _CAPABILITY_REQUEST_CONTRACT
  +            or descriptor.output_contract != _CAPABILITY_RESULT_CONTRACT
  +        ):
  +            raise ControllerError("CAPABILITY_CONTRACT_MISMATCH")
  +        if not isinstance(request, Mapping) or set(request) != _CAPABILITY_INTENT_FIELDS:
  +            raise ControllerError("CAPABILITY_REQUEST_INVALID")
  +
  +        permissions = request.get("requested_permissions")
  +        effects = request.get("requested_effects")
  +        costs = request.get("estimated_costs")
  +        if (
  +            not _nonempty(request.get("bounded_question_or_action"))
  +            or not _nonempty(request.get("timeout_or_stop_condition"))
  +            or not _nonempty_string_list(permissions)
  +            or not _nonempty_string_list(effects)
  +            or not _nonempty_string_list(costs)
  +        ):
  +            raise ControllerError("CAPABILITY_REQUEST_INVALID")
  +
  +        required_permissions = list(
  +            dict.fromkeys([*descriptor.authority_required, authority_rule[0]])
  +        )
  +        if (
  +            list(permissions) != required_permissions
  +            or list(effects) != evidence_scope
  +            or list(costs) != [authority_rule[1]]
  +            or request.get("bounded_question_or_action")
  +            != f"{admitted_operation}:{evidence_scope[0]}"
  +        ):
  +            raise ControllerError("CAPABILITY_REQUEST_INVALID")
  +
           manifest = discovered.manifest
  -        point = {"mission_id": manifest.mission_id, "revision": manifest.revision + 1, "frontier_index": 0, "label": manifest.state["current_frontier"][0]}
  +        authority_errors = authorize_action(
  +            manifest,
  +            descriptor.capability_id,
  +            required_permissions,
  +            evidence_scope,
  +            [authority_rule[1]],
  +        )
  +        if authority_errors:
  +            raise ControllerError(authority_errors[0])
  +
  +        frontier = manifest.state.get("current_frontier")
  +        if (
  +            not isinstance(frontier, list)
  +            or not frontier
  +            or not _nonempty(frontier[0])
  +        ):
  +            raise ControllerError("CAPABILITY_RETURN_POINT_UNAVAILABLE")
  +        point = {
  +            "mission_id": manifest.mission_id,
  +            "revision": manifest.revision + 1,
  +            "frontier_index": 0,
  +            "label": frontier[0],
  +        }
           try:
  -            grant = issue_grant_from_descriptor(matches[0], mission_id=manifest.mission_id, mission_revision=manifest.revision + 1, blocking_condition=blocking_condition, return_point=point, admitted_operation=admitted_operation, evidence_scope=evidence_scope)
  +            grant = issue_grant_from_descriptor(
  +                descriptor,
  +                mission_id=manifest.mission_id,
  +                mission_revision=manifest.revision + 1,
  +                blocking_condition=blocking_condition,
  +                return_point=point,
  +                admitted_operation=admitted_operation,
  +                evidence_scope=evidence_scope,
  +            )
           except (CapabilityGrantError, IndexError) as error:
               raise ControllerError(str(error)) from error
  -        updated = apply_event_data(manifest, "record_capability_request", "mission-steward:capability", {"grant": grant, "request": request})
  +
  +        request_id = f"capability-request:{grant['grant_id']}"
  +        grant["request_id"] = request_id
  +        canonical_request = {
  +            "schema": "capability-request@1",
  +            "request_id": request_id,
  +            "mission_id": manifest.mission_id,
  +            "mission_revision": manifest.revision + 1,
  +            "capability_id": descriptor.capability_id,
  +            "capability_source_sha256": descriptor.source_sha256,
  +            "bounded_question_or_action": request["bounded_question_or_action"],
  +            "authority_receipt": (
  +                f"checkpoint-sha256:{discovered.receipt.sha256}"
  +            ),
  +            "expected_output_contract": descriptor.output_contract,
  +            "return_point": deepcopy(point),
  +            "timeout_or_stop_condition": request["timeout_or_stop_condition"],
  +        }
  +        try:
  +            updated = apply_event_data(
  +                manifest,
  +                "record_capability_request",
  +                "mission-steward:capability",
  +                {"grant": grant, "request": canonical_request},
  +            )
  +        except TransitionError as error:
  +            raise ControllerError(str(error)) from error
           checkpoint = self._store(binding.workspace_root, manifest.mission_id).save(updated)
  -        return {"status": "capability-issued", "grant": grant, "checkpoint_ref": checkpoint.path, "checkpoint_sha256": checkpoint.sha256}
  +        return {
  +            "status": "capability-issued",
  +            "grant_id": str(grant["grant_id"]),
  +            "grant": deepcopy(grant),
  +            "checkpoint_ref": checkpoint.path,
  +            "checkpoint_sha256": checkpoint.sha256,
  +        }
   
       def manifest_capability_result(
           self,
  @@ -537,26 +683,173 @@ class ManifestController:
       def manifest_capability_execute(
           self,
           *,
  -        grant: dict[str, Any],
  +        grant_id: str,
           operation: str,
           target: str,
           evidence_refs: list[str] | None = None,
           evidence_payload: Mapping[str, str] | None = None,
           _host_context_ref: str | None = None,
           _host_gate_ref: str | None = None,
       ) -> dict[str, Any]:
           binding = self._binding("manifest_capability_execute", _host_context_ref, _host_gate_ref)
           if binding.gate.lock_reason not in {"explicit-manifest-intent", "unfinished-durable-mission", "unfinished-mission-integrity-error", "bootstrap-recovery"}:
               raise ControllerError("MANIFEST_ENGAGEMENT_LOCKED")
  +        if not _nonempty(grant_id):
  +            raise ControllerError("CAPABILITY_GRANT_ID_REQUIRED")
  +        if not _nonempty(operation):
  +            raise ControllerError("OPERATION_NOT_READ_ONLY")
  +        if operation.startswith("web."):
  +            raise ControllerError("WEB_OPERATION_DISABLED")
  +        authority_rule = _READ_AUTHORITY.get(operation)
  +        if authority_rule is None:
  +            raise ControllerError("OPERATION_NOT_READ_ONLY")
  +
           discovered = self._discover(binding.workspace_root)
           manifest = discovered.manifest
  +        records = [
  +            item
  +            for item in manifest.capabilities.get("invoked", [])
  +            if isinstance(item, Mapping) and item.get("grant_id") == grant_id
  +        ]
  +        if len(records) != 1:
  +            raise ControllerError("CAPABILITY_GRANT_NOT_FOUND")
  +        record = records[0]
  +        if record.get("result") is not None:
  +            raise ControllerError("CAPABILITY_RESULT_REPLAY")
  +        execution_state = record.get("execution_state")
  +        if execution_state == "in_progress":
  +            raise ControllerError("CAPABILITY_EXECUTION_IN_PROGRESS")
  +        if execution_state != "pending":
  +            raise ControllerError("CAPABILITY_GRANT_NOT_PENDING")
  +
  +        grant = record.get("grant")
  +        request = record.get("request")
  +        if not isinstance(grant, Mapping) or not isinstance(request, Mapping):
  +            raise ControllerError("CAPABILITY_REQUEST_INVALID")
  +        if grant.get("grant_id") != grant_id:
  +            raise ControllerError("CAPABILITY_GRANT_ID_MISMATCH")
  +        if grant.get("mission_id") != manifest.mission_id:
  +            raise ControllerError("CAPABILITY_GRANT_MISSION_MISMATCH")
  +        if grant.get("mission_revision") != manifest.revision:
  +            raise ControllerError("GRANT_STALE")
  +        if grant.get("admitted_operation") != operation:
  +            raise ControllerError("GRANT_OPERATION_NOT_ADMITTED")
  +
  +        scope = grant.get("evidence_scope")
  +        if (
  +            not isinstance(scope, list)
  +            or len(scope) != 1
  +            or not all(_nonempty(item) for item in scope)
  +        ):
  +            raise ControllerError("CAPABILITY_GRANT_INVALID")
  +        if target not in scope:
  +            raise ControllerError("TARGET_NOT_IN_EVIDENCE_SCOPE")
  +
  +        if evidence_refs is None:
  +            refs = [target]
  +        elif _nonempty_string_list(evidence_refs):
  +            refs = list(evidence_refs)
  +        else:
  +            raise ControllerError("GRANT_EVIDENCE_REQUIRED")
  +        if any(ref not in scope for ref in refs):
  +            raise ControllerError("GRANT_EVIDENCE_REQUIRED")
  +
  +        if (
  +            set(request) != _CAPABILITY_REQUEST_FIELDS
  +            or request.get("schema") != "capability-request@1"
  +            or not _nonempty(request.get("request_id"))
  +            or not _nonempty(request.get("authority_receipt"))
  +            or not _nonempty(request.get("timeout_or_stop_condition"))
  +            or request.get("request_id") != grant.get("request_id")
  +            or request.get("mission_id") != manifest.mission_id
  +            or request.get("mission_revision") != manifest.revision
  +            or request.get("capability_id") != grant.get("capability_id")
  +            or request.get("capability_source_sha256")
  +            != grant.get("capability_descriptor_sha256")
  +            or request.get("bounded_question_or_action")
  +            != f"{operation}:{target}"
  +            or request.get("expected_output_contract")
  +            != _CAPABILITY_RESULT_CONTRACT
  +            or request.get("return_point") != grant.get("return_point")
  +        ):
  +            raise ControllerError("CAPABILITY_REQUEST_INVALID")
  +
  +        descriptor = self._observed_descriptor(
  +            grant.get("capability_id"),
  +            grant.get("capability_descriptor_sha256"),
  +        )
  +        if (
  +            descriptor.input_contract != _CAPABILITY_REQUEST_CONTRACT
  +            or descriptor.output_contract != _CAPABILITY_RESULT_CONTRACT
  +        ):
  +            raise ControllerError("CAPABILITY_CONTRACT_MISMATCH")
  +        required_permissions = list(
  +            dict.fromkeys([*descriptor.authority_required, authority_rule[0]])
  +        )
  +        authority_errors = authorize_action(
  +            manifest,
  +            descriptor.capability_id,
  +            required_permissions,
  +            scope,
  +            [authority_rule[1]],
  +        )
  +        if authority_errors:
  +            raise ControllerError(authority_errors[0])
  +
  +        execution_grant = deepcopy(dict(grant))
  +        store = self._store(binding.workspace_root, manifest.mission_id)
           try:
  -            result = execute_read(grant, mission_id=manifest.mission_id, mission_revision=manifest.revision,
  -                                  operation=operation, target=target, workspace=binding.workspace_root,
  -                                  evidence_refs=evidence_refs, evidence_payload=evidence_payload)
  +            begun = apply_event_data(
  +                manifest,
  +                "begin_capability_execution",
  +                "mission-steward:capability",
  +                {
  +                    "grant_id": grant_id,
  +                    "operation": operation,
  +                    "target": target,
  +                    "evidence_refs": refs,
  +                },
  +            )
  +        except TransitionError as error:
  +            raise ControllerError(str(error)) from error
  +        store.save(begun)
  +
  +        try:
  +            observed = execute_read(
  +                execution_grant,
  +                mission_id=manifest.mission_id,
  +                mission_revision=manifest.revision,
  +                operation=operation,
  +                target=target,
  +                workspace=binding.workspace_root,
  +                evidence_refs=refs,
  +                evidence_payload=evidence_payload,
  +            )
           except CapabilityOperationError as error:
               raise ControllerError(str(error)) from error
  -        updated = apply_event_data(manifest, "record_capability_result", "capability:result", {"grant_id": grant.get("grant_id"), "result": result})
  -        checkpoint = self._store(binding.workspace_root, manifest.mission_id).save(updated)
  -        return {"status": "capability-executed", "result": result, "checkpoint_ref": checkpoint.path, "checkpoint_sha256": checkpoint.sha256}
  +
  +        result = {
  +            "schema": "capability-result@1",
  +            "request_id": request["request_id"],
  +            "status": "completed",
  +            "verdict": observed.get("verdict"),
  +            "artifact_refs": refs,
  +            "observed_effects": deepcopy(observed["observed_effects"]),
  +            "returned_control_point": deepcopy(request["return_point"]),
  +            "coverage_limits": list(observed["coverage_limits"]),
  +        }
  +        try:
  +            updated = apply_event_data(
  +                begun,
  +                "record_capability_result",
  +                "capability:result",
  +                {"grant_id": grant_id, "result": result},
  +            )
  +        except TransitionError as error:
  +            raise ControllerError(str(error)) from error
  +        checkpoint = store.save(updated)
  +        return {
  +            "status": "capability-executed",
  +            "grant_id": grant_id,
  +            "result": deepcopy(result),
  +            "checkpoint_ref": checkpoint.path,
  +            "checkpoint_sha256": checkpoint.sha256,
  +        }
   
       def manifest_clarify(
           self,
  @@ -1278,6 +1571,7 @@ class ManifestController:
           *,
           acceptor_ref: str,
           verdict: str,
  +        reason: str | None = None,
           separation_assurance: str,
           principal_evidence_ref: str | None = None,
           _host_context_ref: str | None = None,
  @@ -1320,6 +1614,39 @@ class ManifestController:
               "separation_assurance": separation_assurance,
               "principal_evidence_ref": principal_evidence_ref,
           }
  +        if verdict in {"FAIL", "INCONCLUSIVE"}:
  +            try:
  +                rejected = apply_event_data(
  +                    manifest,
  +                    "reject",
  +                    acceptor_ref,
  +                    {**acceptance_data, "reason": reason},
  +                )
  +            except TransitionError as error:
  +                raise ControllerError(str(error)) from error
  +            checkpoint = self._store(
  +                binding.workspace_root, rejected.mission_id
  +            ).save(rejected)
  +            return {
  +                "status": "rejected",
  +                **_status_summary(rejected),
  +                "mission_id": rejected.mission_id,
  +                "revision": rejected.revision,
  +                "mission_status": rejected.state["status"],
  +                "verdict": verdict,
  +                "reason": reason,
  +                "evidence_refs": list(acceptance_data["evidence_refs"]),
  +                "separation_assurance": separation_assurance,
  +                "coverage_limits": coverage_limits,
  +                "checkpoint_ref": checkpoint.path,
  +                "checkpoint_sha256": checkpoint.sha256,
  +                "process_instance_id": self.process_instance_id,
  +            }
  +
           if _active_milestone_record(manifest) is not None:
               try:
                   continued = apply_event_data(
  diff --git a/practical_agency/mcp_server.py b/practical_agency/mcp_server.py
  --- a/practical_agency/mcp_server.py
  +++ b/practical_agency/mcp_server.py
  @@ -49,15 +49,6 @@ TOOLS: list[dict[str, Any]] = [
           ),
       },
       {
  -        "name": "manifest_capability_request",
  -        "description": "Persist one externally issued bounded capability request.",
  -        "inputSchema": _closed_schema(
  -            {
  -                "grant": {"type": "object"},
  -                "request": {"type": "object"},
  -            },
  -            ("grant", "request"),
  -        ),
  -    },
  -    {
           "name": "manifest_capability_issue",
           "description": "Issue and persist one descriptor-derived bounded capability grant.",
           "inputSchema": _closed_schema(
  @@ -75,29 +66,20 @@ TOOLS: list[dict[str, Any]] = [
           ),
       },
       {
  -        "name": "manifest_capability_result",
  -        "description": "Persist one typed capability result against its return point.",
  -        "inputSchema": _closed_schema(
  -            {
  -                "grant_id": {"type": "string", "minLength": 1},
  -                "result": {"type": "object"},
  -            },
  -            ("grant_id", "result"),
  -        ),
  -    },
  -    {
           "name": "manifest_capability_execute",
  -        "description": "Execute one bounded read operation and record its typed result.",
  +        "description": "Execute one canonical durable grant exactly once and record its typed result.",
           "inputSchema": _closed_schema(
               {
  -                "grant": {"type": "object"},
  +                "grant_id": {"type": "string", "minLength": 1},
                   "operation": {"type": "string", "minLength": 1},
                   "target": {"type": "string", "minLength": 1},
                   "evidence_refs": {"type": "array", "items": {"type": "string"}},
                   "evidence_payload": {"type": ["object", "null"]},
               },
  -            ("grant", "operation", "target"),
  +            ("grant_id", "operation", "target"),
           ),
       },
       {
  @@ -161,6 +143,7 @@ TOOLS: list[dict[str, Any]] = [
                   "acceptor_ref": {"type": "string", "minLength": 1},
                   "verdict": {"type": "string", "enum": ["PASS", "FAIL", "INCONCLUSIVE"]},
  +                "reason": {"type": "string", "minLength": 1},
                   "separation_assurance": {
                       "type": "string",
                       "enum": ["declared-role-separation", "externally-proven"],
  diff --git a/practical_agency/state_machine.py b/practical_agency/state_machine.py
  --- a/practical_agency/state_machine.py
  +++ b/practical_agency/state_machine.py
  @@ -9,6 +9,7 @@ from uuid import uuid4
   from typing import Any, Mapping
   
  +from practical_agency.capability_grants import CapabilityGrantError, consume_grant
   from practical_agency.deferred_interest import validate_deferred_interest
   from practical_agency.governed_workspace import (
       GovernedWorkspaceError,
  @@ -133,6 +134,10 @@ _ALLOWED_FROM: dict[str, set[str]] = {
       },
       "record_action": {MissionStatus.ACTIVE.value},
       "record_capability_request": {MissionStatus.ACTIVE.value, MissionStatus.BLOCKED.value},
  +    "begin_capability_execution": {
  +        MissionStatus.ACTIVE.value,
  +        MissionStatus.BLOCKED.value,
  +    },
       "record_capability_result": {MissionStatus.ACTIVE.value, MissionStatus.BLOCKED.value},
       "record_observation": {
           MissionStatus.ACTIVE.value,
  @@ -181,6 +186,33 @@ _MANIFEST_DEFINITION_FIELDS = {
       "completion_acceptor",
   }
   
  +_CAPABILITY_REQUEST_FIELDS = {
  +    "schema",
  +    "request_id",
  +    "mission_id",
  +    "mission_revision",
  +    "capability_id",
  +    "capability_source_sha256",
  +    "bounded_question_or_action",
  +    "authority_receipt",
  +    "expected_output_contract",
  +    "return_point",
  +    "timeout_or_stop_condition",
  +}
  +_CAPABILITY_RESULT_REQUIRED_FIELDS = {
  +    "schema",
  +    "request_id",
  +    "status",
  +    "artifact_refs",
  +    "observed_effects",
  +    "returned_control_point",
  +    "coverage_limits",
  +}
  +_CAPABILITY_RESULT_ALLOWED_FIELDS = (
  +    _CAPABILITY_RESULT_REQUIRED_FIELDS | {"verdict"}
  +)
  +_CAPABILITY_RESULT_STATUSES = {"completed", "declined", "blocked", "failed"}
  +
   
   def _canonical_mapping_sha256(value: Mapping[str, Any]) -> str:
       encoded = json.dumps(
  @@ -617,10 +649,90 @@ def apply_event(
           invoked = data["capabilities"].setdefault("invoked", [])
           if any(isinstance(item, Mapping) and item.get("grant_id") == grant_id for item in invoked):
               raise TransitionError("CAPABILITY_GRANT_REPLAY")
  -        invoked.append({"grant_id": grant_id, "grant": deepcopy(dict(grant)), "request": deepcopy(dict(request)), "result": None})
  +        record = {
  +            "grant_id": grant_id,
  +            "grant": deepcopy(dict(grant)),
  +            "request": deepcopy(dict(request)),
  +            "result": None,
  +        }
  +        if request.get("schema") == "capability-request@1":
  +            request_id = request.get("request_id")
  +            if (
  +                set(request) != _CAPABILITY_REQUEST_FIELDS
  +                or not isinstance(request_id, str)
  +                or not request_id.strip()
  +                or request.get("mission_id") != manifest.mission_id
  +                or request.get("mission_revision") != grant.get("mission_revision")
  +                or request.get("capability_id") != grant.get("capability_id")
  +                or request.get("capability_source_sha256")
  +                != grant.get("capability_descriptor_sha256")
  +                or request.get("return_point") != grant.get("return_point")
  +                or grant.get("request_id") != request_id
  +                or not isinstance(
  +                    request.get("bounded_question_or_action"), str
  +                )
  +                or not request["bounded_question_or_action"].strip()
  +                or not isinstance(
  +                    request.get("timeout_or_stop_condition"), str
  +                )
  +                or not request["timeout_or_stop_condition"].strip()
  +            ):
  +                raise TransitionError("CAPABILITY_REQUEST_INVALID")
  +            record["execution_state"] = "pending"
  +        invoked.append(record)
           artifact = f"capability-grant:{grant_id}"
           _append_unique(continuity["durable_artifacts"], artifact)
           continuity["decisions"].append({"kind": "capability-request", "actor_ref": event.actor_ref, "grant_id": grant_id, "request": deepcopy(dict(request))})
   
  +    elif event.kind == "begin_capability_execution":
  +        if set(payload) != {
  +            "grant_id",
  +            "operation",
  +            "target",
  +            "evidence_refs",
  +        }:
  +            raise TransitionError("CAPABILITY_EXECUTION_EVENT_INVALID")
  +        grant_id = payload.get("grant_id")
  +        operation = payload.get("operation")
  +        target = payload.get("target")
  +        evidence_refs = payload.get("evidence_refs")
  +        if (
  +            not isinstance(grant_id, str)
  +            or not grant_id.strip()
  +            or not isinstance(operation, str)
  +            or not operation.strip()
  +            or not isinstance(target, str)
  +            or not target.strip()
  +            or not isinstance(evidence_refs, list)
  +            or not evidence_refs
  +            or any(
  +                not isinstance(item, str) or not item.strip()
  +                for item in evidence_refs
  +            )
  +        ):
  +            raise TransitionError("CAPABILITY_EXECUTION_EVENT_INVALID")
  +        invoked = [
  +            item
  +            for item in data["capabilities"].get("invoked", [])
  +            if isinstance(item, Mapping) and item.get("grant_id") == grant_id
  +        ]
  +        if len(invoked) != 1:
  +            raise TransitionError("CAPABILITY_GRANT_NOT_FOUND")
  +        record = invoked[0]
  +        if record.get("result") is not None:
  +            raise TransitionError("CAPABILITY_RESULT_REPLAY")
  +        if record.get("execution_state") != "pending":
  +            if record.get("execution_state") == "in_progress":
  +                raise TransitionError("CAPABILITY_EXECUTION_IN_PROGRESS")
  +            raise TransitionError("CAPABILITY_GRANT_NOT_PENDING")
  +        grant = record.get("grant")
  +        request = record.get("request")
  +        if (
  +            not isinstance(grant, dict)
  +            or not isinstance(request, Mapping)
  +            or request.get("schema") != "capability-request@1"
  +        ):
  +            raise TransitionError("CAPABILITY_REQUEST_INVALID")
  +        scope = grant.get("evidence_scope")
  +        if not isinstance(scope, list) or target not in scope:
  +            raise TransitionError("TARGET_NOT_IN_EVIDENCE_SCOPE")
  +        try:
  +            consume_grant(
  +                grant,
  +                mission_id=manifest.mission_id,
  +                mission_revision=manifest.revision,
  +                operation=operation,
  +                evidence_refs=evidence_refs,
  +                return_point=request.get("return_point"),
  +            )
  +        except CapabilityGrantError as error:
  +            raise TransitionError(str(error)) from error
  +        record["execution_state"] = "in_progress"
  +        continuity["decisions"].append(
  +            {
  +                "kind": "capability-execution-begun",
  +                "actor_ref": event.actor_ref,
  +                "grant_id": grant_id,
  +                "request_id": request.get("request_id"),
  +                "operation": operation,
  +                "target": target,
  +            }
  +        )
  +
       elif event.kind == "record_capability_result":
           if set(payload) != {"grant_id", "result"}:
               raise TransitionError("CAPABILITY_RESULT_EVENT_INVALID")
  @@ -637,12 +749,65 @@ def apply_event(
           grant = record.get("grant")
           if not isinstance(grant, Mapping) or result.get("returned_control_point") != grant.get("return_point"):
               raise TransitionError("CAPABILITY_RETURN_POINT_MISMATCH")
  -        if not isinstance(result.get("evidence_refs"), list) or not result.get("evidence_refs"):
  -            raise TransitionError("CAPABILITY_EVIDENCE_REQUIRED")
  +
  +        execution_state = record.get("execution_state")
  +        if execution_state is not None:
  +            if execution_state != "in_progress":
  +                raise TransitionError("CAPABILITY_GRANT_NOT_IN_PROGRESS")
  +            request = record.get("request")
  +            artifact_refs = result.get("artifact_refs")
  +            coverage_limits = result.get("coverage_limits")
  +            verdict = result.get("verdict")
  +            if (
  +                not isinstance(request, Mapping)
  +                or set(result) - _CAPABILITY_RESULT_ALLOWED_FIELDS
  +                or not _CAPABILITY_RESULT_REQUIRED_FIELDS.issubset(result)
  +                or result.get("schema") != "capability-result@1"
  +                or result.get("request_id") != request.get("request_id")
  +                or result.get("status") not in _CAPABILITY_RESULT_STATUSES
  +                or (
  +                    verdict is not None
  +                    and (
  +                        not isinstance(verdict, str)
  +                        or not verdict.strip()
  +                    )
  +                )
  +                or not isinstance(artifact_refs, list)
  +                or not artifact_refs
  +                or any(
  +                    not isinstance(item, str) or not item.strip()
  +                    for item in artifact_refs
  +                )
  +                or not isinstance(result.get("observed_effects"), list)
  +                or not isinstance(coverage_limits, list)
  +                or not coverage_limits
  +                or any(
  +                    not isinstance(item, str) or not item.strip()
  +                    for item in coverage_limits
  +                )
  +                or result.get("returned_control_point")
  +                != request.get("return_point")
  +            ):
  +                raise TransitionError("CAPABILITY_RESULT_INVALID")
  +            evidence_refs = list(artifact_refs)
  +            record["execution_state"] = "consumed"
  +        else:
  +            evidence_refs = result.get("evidence_refs")
  +            if not isinstance(evidence_refs, list) or not evidence_refs:
  +                raise TransitionError("CAPABILITY_EVIDENCE_REQUIRED")
  +
           record["result"] = deepcopy(dict(result))
           _append_unique(continuity["durable_artifacts"], f"capability-result:{grant_id}")
  -        continuity["decisions"].append({"kind": "capability-result", "actor_ref": event.actor_ref, "grant_id": grant_id, "verdict": result.get("verdict"), "coverage_limits": deepcopy(result.get("coverage_limits", [])), "evidence_refs": deepcopy(result.get("evidence_refs", []))})
  +        continuity["decisions"].append(
  +            {
  +                "kind": "capability-result",
  +                "actor_ref": event.actor_ref,
  +                "grant_id": grant_id,
  +                "verdict": result.get("verdict"),
  +                "coverage_limits": deepcopy(
  +                    result.get("coverage_limits", [])
  +                ),
  +                "evidence_refs": deepcopy(evidence_refs),
  +            }
  +        )
   
       elif event.kind == "record_observation":
           artifact_ref = _required_string(
evidence: |
  Execution status: NOT RUN.

  DCT-002:
  - practical_agency/controller.py::manifest_capability_issue validates descriptor contracts, exact one-target intent, descriptor/operation permissions, protected state, acceptable cost, and escalation boundaries through authorize_action before persisting a grant.
  - practical_agency/controller.py::manifest_capability_execute ignores caller grant copies, loads the unique canonical checkpoint record by grant_id, checks the exact persisted scope before descriptor discovery or target observation, re-observes the descriptor digest, and re-authorizes against current manifest authority.
  - The TARGET_NOT_IN_EVIDENCE_SCOPE, CAPABILITY_DESCRIPTOR_MISMATCH, PERMISSION_NOT_GRANTED, PROTECTED_STATE_VIOLATION, COST_NOT_AUTHORIZED, and ESCALATION_REQUIRED refusal strings are preserved by the implementing hunks.

  DCT-003:
  - practical_agency/state_machine.py adds the closed begin_capability_execution transition. It consumes the canonical grant and persists execution_state=in_progress before the controller enters execute_read.
  - practical_agency/controller.py saves that intermediate revision before observation. A completed transaction is detected from the latest checkpoint and returns CAPABILITY_RESULT_REPLAY without executing.
  - An interrupted in-progress transaction remains conservatively consumed/unknown and returns CAPABILITY_EXECUTION_IN_PROGRESS rather than risking a second effect.
  - practical_agency/capability_operations.py moves in-memory grant consumption before local content or web retrieval as defense in depth.

  DCT-004:
  - practical_agency/mcp_server.py removes manifest_capability_request and manifest_capability_result from TOOLS.
  - manifest_capability_execute now requires grant_id and exposes no grant property, so a caller-carried grant is rejected by MCP validation before controller, file, or checkpoint access.
  - The retained controller issue argument is untrusted intent; production generates the persisted request. The retained non-MCP request/result methods are not advertised or dispatchable through the reachable MCP surface.

  DCT-005:
  - practical_agency/controller.py generates capability-request@1 with only the committed schema fields and generates capability-result@1 with only its committed required/optional fields.
  - practical_agency/state_machine.py validates exact canonical request fields and strict result fields, request_id binding, mission/descriptor/return-point binding, statuses, artifact references, observations, and coverage before persistence.
  - Input-only requested_permissions, requested_effects, and estimated_costs are validated at issue time but are not copied into the canonical request or grant record.

  DCT-006:
  - Both issue and execute return WEB_OPERATION_DISABLED before execute_read, _retrieve_web, DNS resolution, or urlopen.
  - Low-level web behavior remains available only to the existing isolated operation API; the governed controller/MCP path is network-closed until a separate transport design is approved.

  DCT-007:
  - practical_agency/controller.py::manifest_accept accepts an optional reason and routes FAIL and INCONCLUSIVE to the existing reason-bearing reject transition.
  - The response returns the durable verdict, reason, evidence references, coverage limits, and resulting non-completed mission status. The existing independent-acceptor and declared-role-separation checks remain state-machine owned.

  DCT-008:
  - The valid local path is manifest_capability_issue -> persisted pending request/grant -> manifest_capability_execute(grant_id=...) -> persisted in_progress checkpoint -> one execute_read -> strict persisted result.
  - No shell, generic executable adapter, mutation path, daemon, scheduler, or new public skill is added.

  DCT-009:
  - The implementation uses the real ManifestController, FileCheckpointStore save boundary, apply_event_data transitions, capability operation, descriptor discovery, and McpServer declarations. No test-only seam or production special case is introduced.

  Preserved boundaries:
  - No skills, public-content files, schemas, tests, fixtures, watch-verifier ownership, acceptance-principal claims, DCO material, or unrelated repository behavior are modified.
  - Original operator instruction and append-only authority amendments remain protected by the unchanged state-machine invariant.
requirements: |
  DCT-001: PRESERVED. Stage 1 remains the committed tests-only module; this Stage 2 diff contains production hunks only and does not alter, skip, weaken, or special-case any test.
  DCT-002: IMPLEMENTED by controller authority/scope/descriptor validation before begin_capability_execution or observation.
  DCT-003: IMPLEMENTED by persisted pending -> in_progress -> consumed state and latest-checkpoint replay refusal.
  DCT-004: IMPLEMENTED on the reachable MCP surface by removing request/result tools and replacing grant JSON with grant_id.
  DCT-005: IMPLEMENTED by canonical producers and closed state-machine consumers for capability-request@1 and capability-result@1.
  DCT-006: IMPLEMENTED by controller-level WEB_OPERATION_DISABLED refusal before the operation transport is entered.
  DCT-007: IMPLEMENTED by reason-bearing controller routing to the existing reject transition.
  DCT-008: IMPLEMENTED by the canonical grant_id local-read transaction.
  DCT-009: IMPLEMENTED through production controller, checkpoint, state-machine, operation, descriptor, and MCP boundaries.
  Verification state: UNVERIFIED. No test, syntax, runtime, probe, packaging, public-content, or GitHub check was executed by this relay.
decisions_and_assumptions: |
  1. The durable invocation record carries execution_state values pending, in_progress, and consumed. A persisted in_progress record without a result is treated as consumed/unknown and cannot be retried automatically.
  2. Enabled controller operations are file.read and resource.read. Their canonical required permission is repository:read and canonical estimated cost is bounded reads, matching the committed Stage 1 decision. web.* is refused before transport.
  3. The issued grant persists only generated request_id in addition to the existing grant fields. Input-only authority-intent fields are validated but not persisted; execution-time authority is re-derived from the current descriptor, admitted operation, exact canonical scope, and cost rule.
  4. The controller saves the in-progress checkpoint before calling execute_read. The operation receives an internal copy of the already validated grant; the authoritative checkpoint grant has already been consumed by the state transition.
  5. manifest_capability_request and manifest_capability_result remain Python methods for compatibility but are removed from the MCP tool registry. Canonical records additionally reject direct result recording unless execution_state is in_progress.
  6. No claim is made that the patch applies cleanly or passes tests until the origin applies and runs it at the stated commit.
blockers_or_questions: |
  The focused Stage 2 module can be addressed production-only, but the pre-existing tests/test_mcp_server.py exact TOOL_NAMES assertion still requires manifest_capability_request and manifest_capability_result to be advertised. That assertion is incompatible with the superseding DCT-004 requirement and the committed adversarial test requiring their removal. Because this relay may not modify tests, full-suite GREEN is not claimed; the origin must reconcile that superseded assertion in a separately authorized test-alignment step without restoring the forbidden surfaces.
recommended_next_action: |
  Apply this production-only diff at 634d6a1334fe2cc21b8ac64f391abbd70623bd51, run python -m unittest -v tests.test_durable_capability_transaction, then inspect the full-suite result and update only the superseded MCP tool-list expectation if the focused module is GREEN.
