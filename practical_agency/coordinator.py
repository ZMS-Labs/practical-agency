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
    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]: ...


_EXECUTION_INPUT_FIELDS = {
    "capability_id",
    "requested_permissions",
    "requested_effects",
    "estimated_costs",
    "action",
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
    if isinstance(frontier, list) and 0 <= frontier_index < len(frontier):
        label = str(frontier[frontier_index])
    else:
        label = str(manifest.state.get("next_action") or "resume mission")
    return ReturnPoint(
        manifest.mission_id, manifest.revision, frontier_index, label
    )


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


def coordinate_once(
    manifest: MissionManifest,
    *,
    execution_request: Mapping[str, Any] | None = None,
    unresolved_condition: str | None = None,
    selected_capability: CapabilityDescriptor | None = None,
    frontier_index: int = 0,
    checkpoint_store: object | None = None,
    completion_proposed: bool = False,
) -> CoordinationDecision:
    if manifest.state.get("status") != MissionStatus.ACTIVE.value:
        return CoordinationDecision(
            "BLOCK",
            f"MISSION_NOT_ACTIVE:{manifest.state.get('status')}",
            None,
            None,
        )

    if completion_proposed:
        return CoordinationDecision(
            "VERIFY",
            "MATERIAL_COMPLETION_REQUIRES_INDEPENDENT_ACCEPTANCE",
            {"mission_id": manifest.mission_id, "revision": manifest.revision},
            _return_point(manifest, frontier_index),
        )

    if unresolved_condition is not None:
        if not unresolved_condition.strip():
            return CoordinationDecision("BLOCK", "EMPTY_BOUNDED_CONDITION", None, None)
        if selected_capability is None:
            return CoordinationDecision(
                "BLOCK", "NO_CAPABILITY_SELECTED_FOR_CONDITION", None, None
            )
        if selected_capability.availability != "available":
            return CoordinationDecision(
                "BLOCK",
                f"CAPABILITY_UNAVAILABLE:{selected_capability.capability_id}:"
                f"{selected_capability.degradation_reason or selected_capability.availability}",
                None,
                _return_point(manifest, frontier_index),
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
                "BLOCK", " | ".join(authority_errors), None, _return_point(manifest, frontier_index)
            )
        point = _return_point(manifest, frontier_index)
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
        capability_id = raw_request["capability_id"]
        errors = authorize_action(
            manifest,
            capability_id,
            raw_request["requested_permissions"],
            raw_request["requested_effects"],
            raw_request["estimated_costs"],
        )
        if errors:
            return CoordinationDecision("BLOCK", " | ".join(errors), None, None)
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
        return CoordinationDecision(
            "DISPATCH", reason, request, _return_point(manifest, frontier_index)
        )

    return CoordinationDecision("NOOP", "NO_BOUNDED_NEXT_ACTION", None, None)


def _validate_execution_receipt(
    result: Mapping[str, Any],
    manifest: MissionManifest,
    request: Mapping[str, Any],
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
    if not _nonempty_string(result.get("adapter_ref")):
        raise CoordinationError("INVALID_EXECUTION_RECEIPT:adapter_ref")
    if result.get("status") not in _RESULT_STATUSES:
        raise CoordinationError("INVALID_EXECUTION_RECEIPT:status")
    if not _string_list(result.get("artifact_refs")):
        raise CoordinationError("INVALID_EXECUTION_RECEIPT:artifact_refs")
    if not isinstance(result.get("observed_effects"), list):
        raise CoordinationError("INVALID_EXECUTION_RECEIPT:observed_effects")
    external_ref = result.get("external_receipt_ref")
    if external_ref is not None and not _nonempty_string(external_ref):
        raise CoordinationError("INVALID_EXECUTION_RECEIPT:external_receipt_ref")
    if not _string_list(result.get("coverage_limits")):
        raise CoordinationError("INVALID_EXECUTION_RECEIPT:coverage_limits")


def dispatch_once(
    manifest: MissionManifest,
    decision: CoordinationDecision,
    adapter: ExecutionAdapter,
) -> dict[str, Any]:
    if decision.kind != "DISPATCH" or decision.request is None:
        raise CoordinationError("DECISION_NOT_DISPATCHABLE")
    if decision.request.get("mission_id") != manifest.mission_id:
        raise CoordinationError("MISSION_ID_MISMATCH")
    if decision.request.get("mission_revision") != manifest.revision:
        raise CoordinationError("MISSION_REVISION_MISMATCH")
    result = adapter.dispatch(deepcopy(decision.request))
    if not isinstance(result, dict):
        raise CoordinationError("INVALID_EXECUTION_RECEIPT:root")
    _validate_execution_receipt(result, manifest, decision.request)
    return deepcopy(result)


def _validate_capability_result(
    result: Mapping[str, Any], decision: CoordinationDecision
) -> None:
    if set(result) - _CAPABILITY_RESULT_ALLOWED or not _CAPABILITY_RESULT_REQUIRED.issubset(result):
        raise CoordinationError("INVALID_CAPABILITY_RESULT:fields")
    if result.get("schema") != "capability-result@1":
        raise CoordinationError("INVALID_CAPABILITY_RESULT:schema")
    if result.get("request_id") != decision.request.get("request_id"):
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
    if result.get("returned_control_point") != decision.return_point.to_dict():
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
