"""Bounded mission coordination over discovered capabilities and adapters."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from practical_agency.authority import authorize_action
from practical_agency.capability_discovery import CapabilityDescriptor
from practical_agency.manifest_model import MissionManifest, MissionStatus


class CoordinationError(RuntimeError):
    """Named coordinator refusal."""


@dataclass(frozen=True, slots=True)
class ReturnPoint:
    mission_id: str
    revision: int
    frontier_index: int
    label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "revision": self.revision,
            "frontier_index": self.frontier_index,
            "label": self.label,
        }


@dataclass(frozen=True, slots=True)
class CoordinationDecision:
    kind: str
    reason: str
    request: dict[str, Any] | None
    return_point: ReturnPoint | None


class ExecutionAdapter(Protocol):
    capability_id: str
    adapter_ref: str

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]: ...


_EXECUTION_INPUT_FIELDS = {
    "capability_id",
    "requested_permissions",
    "requested_effects",
    "estimated_costs",
    "action",
}
_EXECUTION_REQUEST_FIELDS = _EXECUTION_INPUT_FIELDS | {
    "schema",
    "request_id",
    "mission_id",
    "mission_revision",
}
_EXECUTION_RECEIPT_FIELDS = {
    "schema",
    "request_id",
    "mission_id",
    "mission_revision",
    "adapter_ref",
    "status",
    "artifact_refs",
    "observed_effects",
    "external_receipt_ref",
    "coverage_limits",
}
_CAPABILITY_RESULT_REQUIRED = {
    "schema",
    "request_id",
    "status",
    "artifact_refs",
    "observed_effects",
    "returned_control_point",
    "coverage_limits",
}
_CAPABILITY_RESULT_ALLOWED = _CAPABILITY_RESULT_REQUIRED | {"verdict"}
_RESULT_STATUSES = {"completed", "declined", "blocked", "failed"}


def normalize_invocation_intent(text: str) -> str:
    normalized = " ".join(text.casefold().split())
    if any(
        phrase in normalized
        for phrase in ("manifest this", "helix it", "carry this through")
    ):
        return "manifest"
    return normalized


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: object) -> bool:
    return isinstance(value, list) and all(_nonempty_string(item) for item in value)


def _return_point(
    manifest: MissionManifest, frontier_index: int
) -> ReturnPoint:
    frontier = manifest.state.get("current_frontier", [])
    if (
        isinstance(frontier_index, bool)
        or not isinstance(frontier_index, int)
        or not isinstance(frontier, list)
        or frontier_index < 0
        or frontier_index >= len(frontier)
    ):
        raise CoordinationError("INVALID_FRONTIER_INDEX")
    label = frontier[frontier_index]
    if not _nonempty_string(label):
        raise CoordinationError("INVALID_FRONTIER_INDEX")
    return ReturnPoint(
        manifest.mission_id, manifest.revision, frontier_index, str(label)
    )


def _decision_block(
    reason: str, manifest: MissionManifest, frontier_index: int
) -> CoordinationDecision:
    try:
        point = _return_point(manifest, frontier_index)
    except CoordinationError:
        point = None
    return CoordinationDecision("BLOCK", reason, None, point)


def _request_id(
    manifest: MissionManifest,
    capability_id: str,
    frontier_index: int,
    kind: str,
) -> str:
    return (
        f"{manifest.mission_id}:r{manifest.revision}:"
        f"{capability_id}:{kind}:f{frontier_index}"
    )


def _valid_execution_input(request: Mapping[str, Any]) -> str | None:
    if set(request) != _EXECUTION_INPUT_FIELDS:
        return "fields"
    if not _nonempty_string(request.get("capability_id")):
        return "capability_id"
    if not _nonempty_string(request.get("action")):
        return "action"
    for field in ("requested_permissions", "requested_effects", "estimated_costs"):
        if not _string_list(request.get(field)):
            return field
    return None


def _frontier_apply_present(manifest: MissionManifest) -> bool:
    rev = manifest.revision
    latest: int | None = None
    for item in manifest.continuity.get("decisions", []):
        if not isinstance(item, Mapping) or item.get("kind") != "mission-os-apply":
            continue
        if item.get("proposal_kind") not in {"frontier_patch", "replan_slice"}:
            continue
        at_revision = item.get("at_revision")
        if isinstance(at_revision, int) and (latest is None or at_revision > latest):
            latest = at_revision
    return latest is not None and latest <= rev


def _pending_remediation_reason(manifest: MissionManifest) -> str | None:
    blockers = manifest.state.get("blockers")
    unresolved = manifest.integrity.get("unresolved_verdicts")
    has_blockers = isinstance(blockers, list) and bool(blockers)
    has_unresolved = isinstance(unresolved, list) and bool(unresolved)
    if not (has_blockers or has_unresolved):
        return None
    expected = manifest.state.get("next_action")
    if not _nonempty_string(expected):
        return "REMEDIATION_ACTION_MISSING"
    return f"EXACT_REMEDIATION_ACTION_REQUIRED:{expected}"


def coordinate_once(
    manifest: MissionManifest,
    *,
    execution_request: Mapping[str, Any] | None = None,
    unresolved_condition: str | None = None,
    selected_capability: CapabilityDescriptor | None = None,
    frontier_index: int = 0,
    checkpoint_store: object | None = None,
    completion_proposed: bool = False,
    require_applied_frontier: bool = False,
) -> CoordinationDecision:
    # Kept for source compatibility; the hard gate is no longer caller-optional.
    del require_applied_frontier

    if manifest.state.get("status") != MissionStatus.ACTIVE.value:
        return CoordinationDecision(
            "BLOCK",
            f"MISSION_NOT_ACTIVE:{manifest.state.get('status')}",
            None,
            None,
        )

    consumes_frontier = unresolved_condition is not None or execution_request is not None
    if consumes_frontier and not _frontier_apply_present(manifest):
        return _decision_block(
            "MISSION_OS_APPLY_REQUIRED", manifest, frontier_index
        )

    remediation_reason = _pending_remediation_reason(manifest)
    if remediation_reason is not None:
        expected_action = manifest.state.get("next_action")
        supplied_action = (
            execution_request.get("action")
            if isinstance(execution_request, Mapping)
            else None
        )
        if supplied_action != expected_action or not _nonempty_string(expected_action):
            return _decision_block(
                remediation_reason, manifest, frontier_index
            )

    if completion_proposed:
        try:
            point = _return_point(manifest, frontier_index)
        except CoordinationError as error:
            return CoordinationDecision("BLOCK", str(error), None, None)
        return CoordinationDecision(
            "VERIFY",
            "MATERIAL_COMPLETION_REQUIRES_INDEPENDENT_ACCEPTANCE",
            {"mission_id": manifest.mission_id, "revision": manifest.revision},
            point,
        )

    if unresolved_condition is not None:
        if not unresolved_condition.strip():
            return CoordinationDecision("BLOCK", "EMPTY_BOUNDED_CONDITION", None, None)
        if selected_capability is None:
            return CoordinationDecision(
                "BLOCK", "NO_CAPABILITY_SELECTED_FOR_CONDITION", None, None
            )
        try:
            point = _return_point(manifest, frontier_index)
        except CoordinationError as error:
            return CoordinationDecision("BLOCK", str(error), None, None)
        if selected_capability.availability != "available":
            return CoordinationDecision(
                "BLOCK",
                f"CAPABILITY_UNAVAILABLE:{selected_capability.capability_id}:"
                f"{selected_capability.degradation_reason or selected_capability.availability}",
                None,
                point,
            )
        authority_errors = authorize_action(
            manifest,
            selected_capability.capability_id,
            list(selected_capability.authority_required),
            [],
            [],
        )
        if authority_errors:
            return CoordinationDecision(
                "BLOCK", " | ".join(authority_errors), None, point
            )
        request_id = _request_id(
            manifest, selected_capability.capability_id, frontier_index, "capability"
        )
        request = {
            "schema": "capability-request@1",
            "request_id": request_id,
            "mission_id": manifest.mission_id,
            "mission_revision": manifest.revision,
            "capability_id": selected_capability.capability_id,
            "capability_source_sha256": selected_capability.source_sha256,
            "bounded_question_or_action": unresolved_condition,
            "authority_receipt": manifest.continuity.get("prior_checkpoint"),
            "expected_output_contract": selected_capability.output_contract,
            "return_point": point.to_dict(),
            "timeout_or_stop_condition": "return after the bounded capability result",
        }
        reason = "BOUNDED_CAPABILITY_REQUEST"
        if checkpoint_store is None:
            reason += ":SESSION_BOUNDED_NO_CHECKPOINT_STORE"
        return CoordinationDecision("REQUEST_CAPABILITY", reason, request, point)

    if execution_request is not None:
        raw_request = deepcopy(dict(execution_request))
        invalid_field = _valid_execution_input(raw_request)
        if invalid_field is not None:
            return CoordinationDecision(
                "BLOCK", f"INVALID_EXECUTION_REQUEST:{invalid_field}", None, None
            )
        try:
            point = _return_point(manifest, frontier_index)
        except CoordinationError as error:
            return CoordinationDecision("BLOCK", str(error), None, None)
        capability_id = raw_request["capability_id"]
        errors = authorize_action(
            manifest,
            capability_id,
            raw_request["requested_permissions"],
            raw_request["requested_effects"],
            raw_request["estimated_costs"],
        )
        if errors:
            return CoordinationDecision("BLOCK", " | ".join(errors), None, point)
        request = {
            "schema": "execution-request@1",
            "request_id": _request_id(
                manifest, capability_id, frontier_index, "execution"
            ),
            "mission_id": manifest.mission_id,
            "mission_revision": manifest.revision,
            **raw_request,
        }
        reason = "AUTHORIZED_DISPATCH"
        if checkpoint_store is None:
            reason += ":SESSION_BOUNDED_NO_CHECKPOINT_STORE"
        return CoordinationDecision("DISPATCH", reason, request, point)

    return CoordinationDecision("NOOP", "NO_BOUNDED_NEXT_ACTION", None, None)


def _validate_execution_envelope(
    manifest: MissionManifest,
    decision: CoordinationDecision,
) -> dict[str, Any]:
    if decision.request is None:
        raise CoordinationError("DECISION_NOT_DISPATCHABLE")
    request = decision.request
    if set(request) != _EXECUTION_REQUEST_FIELDS:
        raise CoordinationError("INVALID_EXECUTION_REQUEST:fields")
    if request.get("schema") != "execution-request@1":
        raise CoordinationError("INVALID_EXECUTION_REQUEST:schema")
    if request.get("mission_id") != manifest.mission_id:
        raise CoordinationError("MISSION_ID_MISMATCH")
    if request.get("mission_revision") != manifest.revision:
        raise CoordinationError("MISSION_REVISION_MISMATCH")
    if decision.return_point is None:
        raise CoordinationError("RETURN_POINT_REQUIRED")
    live_point = _return_point(manifest, decision.return_point.frontier_index)
    if live_point != decision.return_point:
        raise CoordinationError("RETURN_POINT_MISMATCH")
    input_request = {field: request[field] for field in _EXECUTION_INPUT_FIELDS}
    invalid_field = _valid_execution_input(input_request)
    if invalid_field is not None:
        raise CoordinationError(f"INVALID_EXECUTION_REQUEST:{invalid_field}")
    expected_id = _request_id(
        manifest,
        str(request["capability_id"]),
        decision.return_point.frontier_index,
        "execution",
    )
    if request.get("request_id") != expected_id:
        raise CoordinationError("EXECUTION_REQUEST_ID_MISMATCH")
    if not _frontier_apply_present(manifest):
        raise CoordinationError("MISSION_OS_APPLY_REQUIRED")
    errors = authorize_action(
        manifest,
        str(request["capability_id"]),
        request["requested_permissions"],
        request["requested_effects"],
        request["estimated_costs"],
    )
    if errors:
        raise CoordinationError(" | ".join(errors))
    return deepcopy(request)


def _validate_execution_receipt(
    result: Mapping[str, Any],
    manifest: MissionManifest,
    request: Mapping[str, Any],
    *,
    adapter_ref: str,
) -> None:
    if set(result) != _EXECUTION_RECEIPT_FIELDS:
        raise CoordinationError("INVALID_EXECUTION_RECEIPT:fields")
    if result.get("schema") != "execution-receipt@1":
        raise CoordinationError("INVALID_EXECUTION_RECEIPT:schema")
    if result.get("request_id") != request.get("request_id"):
        raise CoordinationError("EXECUTION_RECEIPT_REQUEST_MISMATCH")
    if result.get("mission_id") != manifest.mission_id:
        raise CoordinationError("EXECUTION_RECEIPT_MISSION_MISMATCH")
    if result.get("mission_revision") != manifest.revision:
        raise CoordinationError("EXECUTION_RECEIPT_REVISION_MISMATCH")
    if result.get("adapter_ref") != adapter_ref:
        raise CoordinationError("EXECUTION_RECEIPT_ADAPTER_MISMATCH")
    if result.get("status") not in _RESULT_STATUSES:
        raise CoordinationError("INVALID_EXECUTION_RECEIPT:status")
    if not _string_list(result.get("artifact_refs")):
        raise CoordinationError("INVALID_EXECUTION_RECEIPT:artifact_refs")
    if not isinstance(result.get("observed_effects"), list):
        raise CoordinationError("INVALID_EXECUTION_RECEIPT:observed_effects")
    external_ref = result.get("external_receipt_ref")
    if external_ref is not None and not _nonempty_string(external_ref):
        raise CoordinationError("INVALID_EXECUTION_RECEIPT:external_receipt_ref")
    if result.get("status") == "completed" and not _nonempty_string(external_ref):
        raise CoordinationError("EXTERNAL_EXECUTION_RECEIPT_REQUIRED")
    if not _string_list(result.get("coverage_limits")):
        raise CoordinationError("INVALID_EXECUTION_RECEIPT:coverage_limits")


def dispatch_once(
    manifest: MissionManifest,
    decision: CoordinationDecision,
    adapter: ExecutionAdapter,
) -> dict[str, Any]:
    if decision.kind != "DISPATCH":
        raise CoordinationError("DECISION_NOT_DISPATCHABLE")
    request = _validate_execution_envelope(manifest, decision)

    remediation_reason = _pending_remediation_reason(manifest)
    if remediation_reason is not None:
        expected_action = manifest.state.get("next_action")
        supplied_action = request.get("action")
        if supplied_action != expected_action or not _nonempty_string(expected_action):
            raise CoordinationError(remediation_reason)

    adapter_capability = getattr(adapter, "capability_id", None)
    adapter_ref = getattr(adapter, "adapter_ref", None)
    if not _nonempty_string(adapter_capability) or not _nonempty_string(adapter_ref):
        raise CoordinationError("ADAPTER_IDENTITY_REQUIRED")
    if adapter_capability != request.get("capability_id"):
        raise CoordinationError(
            f"ADAPTER_CAPABILITY_MISMATCH:{adapter_capability}!={request.get('capability_id')}"
        )

    result = adapter.dispatch(deepcopy(request))
    if not isinstance(result, dict):
        raise CoordinationError("INVALID_EXECUTION_RECEIPT:root")
    _validate_execution_receipt(
        result, manifest, request, adapter_ref=str(adapter_ref)
    )
    return deepcopy(result)


def _validate_capability_result(
    result: Mapping[str, Any], decision: CoordinationDecision
) -> None:
    if (
        set(result) - _CAPABILITY_RESULT_ALLOWED
        or not _CAPABILITY_RESULT_REQUIRED.issubset(result)
    ):
        raise CoordinationError("INVALID_CAPABILITY_RESULT:fields")
    if result.get("schema") != "capability-result@1":
        raise CoordinationError("INVALID_CAPABILITY_RESULT:schema")
    if decision.request is None or result.get("request_id") != decision.request.get(
        "request_id"
    ):
        raise CoordinationError("CAPABILITY_RESULT_REQUEST_MISMATCH")
    if result.get("status") not in _RESULT_STATUSES:
        raise CoordinationError("INVALID_CAPABILITY_RESULT:status")
    verdict = result.get("verdict")
    if verdict is not None and not _nonempty_string(verdict):
        raise CoordinationError("INVALID_CAPABILITY_RESULT:verdict")
    if not _string_list(result.get("artifact_refs")):
        raise CoordinationError("INVALID_CAPABILITY_RESULT:artifact_refs")
    if not isinstance(result.get("observed_effects"), list):
        raise CoordinationError("INVALID_CAPABILITY_RESULT:observed_effects")
    if not _string_list(result.get("coverage_limits")):
        raise CoordinationError("INVALID_CAPABILITY_RESULT:coverage_limits")
    if decision.return_point is None or result.get(
        "returned_control_point"
    ) != decision.return_point.to_dict():
        raise CoordinationError("RETURN_POINT_MISMATCH")


def apply_capability_result(
    manifest: MissionManifest,
    decision: CoordinationDecision,
    result: Mapping[str, Any],
) -> MissionManifest:
    if decision.kind != "REQUEST_CAPABILITY" or decision.request is None:
        raise CoordinationError("DECISION_NOT_CAPABILITY_REQUEST")
    if decision.return_point is None:
        raise CoordinationError("RETURN_POINT_REQUIRED")
    expected_now = _return_point(
        manifest, decision.return_point.frontier_index
    )
    if decision.return_point != expected_now:
        raise CoordinationError("RETURN_POINT_MISMATCH")
    _validate_capability_result(result, decision)

    data = manifest.to_dict()
    status = result["status"]
    verdict = result.get("verdict")
    artifact_refs = result["artifact_refs"]
    for artifact in artifact_refs:
        if artifact not in data["continuity"]["durable_artifacts"]:
            data["continuity"]["durable_artifacts"].append(artifact)

    data["capabilities"]["invoked"].append(
        {
            "request_id": decision.request["request_id"],
            "capability_id": decision.request["capability_id"],
            "status": status,
            "verdict": verdict,
            "artifact_refs": deepcopy(artifact_refs),
            "observed_effects": deepcopy(result["observed_effects"]),
            "coverage_limits": deepcopy(result["coverage_limits"]),
        }
    )
    data["state"]["next_action"] = decision.return_point.label

    if status in {"blocked", "failed", "declined"}:
        blocker = f"CAPABILITY_{status.upper()}:{decision.request['capability_id']}"
        data["state"]["status"] = MissionStatus.BLOCKED.value
        if blocker not in data["state"]["blockers"]:
            data["state"]["blockers"].append(blocker)
    if verdict in {"NO-GO", "FAIL"}:
        data["state"]["status"] = MissionStatus.BLOCKED.value
        if verdict not in data["integrity"]["unresolved_verdicts"]:
            data["integrity"]["unresolved_verdicts"].append(verdict)
        if verdict not in data["state"]["blockers"]:
            data["state"]["blockers"].append(verdict)

    data["revision"] = manifest.revision + 1
    return MissionManifest.from_dict(data)
