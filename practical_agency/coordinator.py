"""Bounded mission coordination with explicit return points and one-step dispatch."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Mapping, Protocol, Sequence

from .authority import ActionRequest, evaluate_action
from .capability_discovery import CapabilityDescriptor
from .checkpoint_store import CheckpointStore
from .manifest_model import MissionManifest
from .state_machine import transition


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
    degradation: str | None = None


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    request_id: str
    status: str
    artifact_refs: tuple[str, ...]
    observed_effects: tuple[Mapping[str, Any], ...]
    returned_control_point: ReturnPoint
    coverage_limits: tuple[str, ...]


class ExecutionAdapter(Protocol):
    adapter_ref: str

    def dispatch(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...



def _validate_execution_receipt(
    receipt: Mapping[str, Any], *, request_id: str, adapter_ref: str
) -> dict[str, Any]:
    required = {
        "schema",
        "request_id",
        "adapter_ref",
        "status",
        "observed_effects",
        "artifact_refs",
        "recorded_at",
        "coverage_limits",
    }
    candidate = dict(receipt)
    if not request_id.strip() or not adapter_ref.strip():
        raise ValueError("INVALID_EXECUTION_RECEIPT: request and adapter identity must be non-empty")
    if set(candidate) != required or candidate.get("schema") != "execution-receipt@1":
        raise ValueError("INVALID_EXECUTION_RECEIPT: adapter returned the wrong shape")
    if candidate.get("request_id") != request_id or candidate.get("adapter_ref") != adapter_ref:
        raise ValueError("EXECUTION_RECEIPT_IDENTITY_MISMATCH: receipt does not bind the dispatch")
    if candidate.get("status") not in {"completed", "blocked", "failed", "cancelled"}:
        raise ValueError("INVALID_EXECUTION_RECEIPT: status is outside the closed set")
    if not isinstance(candidate.get("recorded_at"), str) or not candidate["recorded_at"].strip():
        raise ValueError("INVALID_EXECUTION_RECEIPT: recorded_at must be a non-empty string")
    observed = candidate.get("observed_effects")
    if not isinstance(observed, list) or not all(isinstance(item, Mapping) for item in observed):
        raise ValueError("INVALID_EXECUTION_RECEIPT: observed_effects must be a list of objects")
    for field in ("artifact_refs", "coverage_limits"):
        value = candidate.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"INVALID_EXECUTION_RECEIPT: {field} must be a list of strings")
    return candidate

def _validate_capability_result(result: CapabilityResult) -> None:
    if not isinstance(result.request_id, str) or not result.request_id.strip():
        raise ValueError("INVALID_CAPABILITY_RESULT: request_id must be non-empty")
    if result.status not in {"completed", "declined", "blocked", "failed"}:
        raise ValueError("INVALID_CAPABILITY_RESULT: status is outside the closed set")
    if not isinstance(result.returned_control_point, ReturnPoint):
        raise ValueError("INVALID_CAPABILITY_RESULT: returned_control_point is invalid")
    if not isinstance(result.artifact_refs, (tuple, list)) or not all(
        isinstance(item, str) for item in result.artifact_refs
    ):
        raise ValueError("INVALID_CAPABILITY_RESULT: artifact_refs must be strings")
    if not isinstance(result.coverage_limits, (tuple, list)) or not all(
        isinstance(item, str) for item in result.coverage_limits
    ):
        raise ValueError("INVALID_CAPABILITY_RESULT: coverage_limits must be strings")
    if not isinstance(result.observed_effects, (tuple, list)) or not all(
        isinstance(item, Mapping) for item in result.observed_effects
    ):
        raise ValueError("INVALID_CAPABILITY_RESULT: observed_effects must be objects")


def normalize_invocation(text: str) -> str | None:
    normalized = " ".join(text.casefold().split())
    if normalized in {"helix it", "manifest this", "carry this through"}:
        return "manifest"
    if normalized.startswith("manifest ") or normalized.startswith("helix "):
        return "manifest"
    return None


def _blocked_manifest(manifest: MissionManifest, *, code: str, detail: str) -> MissionManifest:
    payload = manifest.to_dict()
    payload["revision"] = manifest.revision + 1
    payload["state"]["status"] = "blocked"
    payload["state"]["blockers"] = [{"code": code, "detail": detail}]
    payload["state"]["next_action"] = "resolve authority or execution blocker"
    payload["continuity"]["decisions"].append(
        {"kind": "dispatch-blocked", "revision": payload["revision"], "code": code, "detail": detail}
    )
    return MissionManifest.from_dict(payload)


class MissionCoordinator:
    def __init__(
        self,
        *,
        checkpoint_store: CheckpointStore | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.checkpoint_store = checkpoint_store
        self.clock = clock or (lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z"))

    def _recorded_at(self) -> str:
        value = self.clock()
        if not isinstance(value, str) or not value.strip():
            raise ValueError("INVALID_CLOCK: clock must return a non-empty timestamp string")
        return value

    def _checkpoint_dispatch(
        self,
        manifest: MissionManifest,
        *,
        request_id: str,
        receipt: Mapping[str, Any],
    ) -> None:
        if self.checkpoint_store is None:
            return
        self.checkpoint_store.save(
            manifest,
            events=[{"kind": "execution", "request_id": request_id, "status": receipt["status"]}],
            receipts=[receipt],
        )

    def decide(
        self,
        manifest: MissionManifest,
        *,
        capabilities: Sequence[CapabilityDescriptor] = (),
        named_condition: str | None = None,
        requested_capability_id: str | None = None,
        capability_authority_ref: str | None = None,
        execution_request: ActionRequest | None = None,
        proof_bundle_ready: bool = False,
    ) -> CoordinationDecision:
        if manifest.authority["revoked"] or manifest.state["status"] in {"completed", "cancelled"}:
            return CoordinationDecision("BLOCK", "mission authority is unavailable or terminal", None, None)

        if requested_capability_id is not None:
            candidates = [item for item in capabilities if item.capability_id == requested_capability_id]
            if len(candidates) != 1:
                return CoordinationDecision(
                    "BLOCK", f"capability {requested_capability_id} is unavailable or ambiguous", None, None
                )
            descriptor = candidates[0]
            if descriptor.availability != "available":
                return CoordinationDecision(
                    "BLOCK",
                    f"capability {requested_capability_id} is unavailable: {descriptor.degradation_reason}",
                    None,
                    None,
                )
            if not named_condition or not named_condition.strip():
                return CoordinationDecision("BLOCK", "bounded condition is required", None, None)
            required_authority = set(descriptor.authority_required)
            granted_authority = set(manifest.authority["permissions"])
            missing_authority = sorted(required_authority - granted_authority)
            if missing_authority:
                return CoordinationDecision(
                    "BLOCK",
                    "CAPABILITY_AUTHORITY_NOT_GRANTED: " + ", ".join(missing_authority),
                    None,
                    None,
                )
            if required_authority and not capability_authority_ref:
                return CoordinationDecision(
                    "BLOCK",
                    "CAPABILITY_AUTHORITY_RECEIPT_REQUIRED: selected capability requires scoped authority",
                    None,
                    None,
                )
            frontier = manifest.state["current_frontier"]
            label = manifest.state["next_action"] or (frontier[0] if frontier else "return to mission")
            return_point = ReturnPoint(manifest.mission_id, manifest.revision, 0, label)
            request_id = f"cap:{manifest.mission_id}:r{manifest.revision}:{requested_capability_id}"
            request = {
                "schema": "capability-request@1",
                "request_id": request_id,
                "mission_id": manifest.mission_id,
                "mission_revision": manifest.revision,
                "capability_id": descriptor.capability_id,
                "source_sha256": descriptor.source_sha256,
                "bounded_request": named_condition,
                "authority_ref": capability_authority_ref,
                "expected_output_contract": descriptor.output_contract,
                "return_point": return_point.to_dict(),
                "stop_condition": "return after the bounded request is answered or blocked",
            }
            return CoordinationDecision(
                "REQUEST_CAPABILITY", "bounded condition belongs to the selected capability", request, return_point
            )

        if execution_request is not None:
            authority = evaluate_action(manifest, execution_request)
            if not authority.allowed:
                return CoordinationDecision("BLOCK", f"{authority.code}: {authority.detail}", None, None)
            degradation = None if self.checkpoint_store is not None else "SESSION_BOUNDED_NO_CHECKPOINT_STORE"
            return CoordinationDecision(
                "DISPATCH", "one authorized directly checkable execution step", None, None, degradation
            )

        if proof_bundle_ready:
            return CoordinationDecision("VERIFY", "proof bundle is ready for independent acceptance", None, None)

        return CoordinationDecision("NOOP", "no bounded next action was supplied", None, None)

    def apply_capability_result(
        self,
        manifest: MissionManifest,
        decision: CoordinationDecision,
        result: CapabilityResult,
    ) -> MissionManifest:
        if decision.kind != "REQUEST_CAPABILITY" or decision.request is None or decision.return_point is None:
            raise ValueError("NOT_A_CAPABILITY_DECISION: decision does not own a return point")
        _validate_capability_result(result)
        if (
            manifest.mission_id != decision.return_point.mission_id
            or manifest.revision != decision.return_point.revision
        ):
            raise ValueError(
                "STALE_CAPABILITY_RESULT: mission advanced after the bounded request was issued"
            )
        if result.request_id != decision.request["request_id"]:
            raise ValueError("REQUEST_ID_MISMATCH: result belongs to another invocation")
        if result.returned_control_point != decision.return_point:
            raise ValueError("RETURN_POINT_MISMATCH: bounded result returned elsewhere")

        payload = manifest.to_dict()
        payload["revision"] = manifest.revision + 1
        record = {
            "request_id": result.request_id,
            "capability_id": decision.request["capability_id"],
            "source_sha256": decision.request["source_sha256"],
            "status": result.status,
            "artifact_refs": list(result.artifact_refs),
            "observed_effects": [dict(item) for item in result.observed_effects],
            "returned_control_point": result.returned_control_point.to_dict(),
            "coverage_limits": list(result.coverage_limits),
        }
        payload["capabilities"]["invoked"].append(record)
        payload["continuity"]["durable_artifacts"].extend(result.artifact_refs)
        payload["continuity"]["decisions"].append(
            {"kind": "capability-result", "revision": payload["revision"], **record}
        )

        verdicts = {
            str(item.get("verdict", "")).upper()
            for item in result.observed_effects
            if isinstance(item, Mapping)
        }
        if result.status in {"blocked", "failed"} or verdicts.intersection({"NO-GO", "FAIL"}):
            payload["state"]["status"] = "blocked"
            payload["state"]["blockers"] = [
                {
                    "code": "CAPABILITY_RESULT_BLOCKED",
                    "request_id": result.request_id,
                    "status": result.status,
                    "verdicts": sorted(verdicts),
                }
            ]
            payload["state"]["next_action"] = "resolve capability finding"
        return MissionManifest.from_dict(payload)

    def dispatch_one(
        self,
        manifest: MissionManifest,
        request: ActionRequest,
        *,
        adapter: ExecutionAdapter,
        actor_ref: str,
    ) -> tuple[MissionManifest, dict[str, Any]]:
        if not isinstance(actor_ref, str) or not actor_ref.strip():
            raise ValueError("ACTOR_REF_REQUIRED: dispatch actor must be non-empty")
        adapter_ref = getattr(adapter, "adapter_ref", None)
        if not isinstance(adapter_ref, str) or not adapter_ref.strip():
            raise ValueError("ADAPTER_REF_REQUIRED: execution adapter must identify itself")

        authority = evaluate_action(manifest, request)
        request_id = f"exec:{manifest.mission_id}:r{manifest.revision}:{request.action_id}"
        if not authority.allowed:
            receipt = {
                "schema": "execution-receipt@1",
                "request_id": request_id,
                "adapter_ref": adapter_ref,
                "status": "blocked",
                "observed_effects": [],
                "artifact_refs": [],
                "recorded_at": self._recorded_at(),
                "coverage_limits": [authority.code],
            }
            if authority.code == "MISSION_NOT_ACTIVE":
                return manifest, receipt
            updated = _blocked_manifest(manifest, code=authority.code, detail=authority.detail)
            self._checkpoint_dispatch(updated, request_id=request_id, receipt=receipt)
            return updated, receipt

        adapter_request = {
            "schema": "execution-request@1",
            "request_id": request_id,
            "mission_id": manifest.mission_id,
            "mission_revision": manifest.revision,
            "action": {
                "action_id": request.action_id,
                "description": request.description,
                "required_permissions": list(request.required_permissions),
                "touches": list(request.touches),
                "costs": list(request.costs),
                "consequential": request.consequential,
                "irreversible": request.irreversible,
                "authority_ref": request.authority_ref,
                "stop_condition": request.stop_condition,
            },
        }
        try:
            adapter_output = adapter.dispatch(adapter_request)
        except Exception as error:  # noqa: BLE001 - adapter is an external boundary
            code = f"ADAPTER_EXCEPTION:{type(error).__name__}"
            receipt = {
                "schema": "execution-receipt@1",
                "request_id": request_id,
                "adapter_ref": adapter_ref,
                "status": "failed",
                "observed_effects": [
                    {"kind": "adapter-exception", "exception_type": type(error).__name__}
                ],
                "artifact_refs": [],
                "recorded_at": self._recorded_at(),
                "coverage_limits": [code],
            }
            updated = _blocked_manifest(
                manifest, code="EXECUTION_ADAPTER_FAILED", detail=code
            )
            self._checkpoint_dispatch(updated, request_id=request_id, receipt=receipt)
            return updated, receipt

        if not isinstance(adapter_output, Mapping):
            raise ValueError("INVALID_EXECUTION_RECEIPT: adapter output must be an object")
        raw_receipt = _validate_execution_receipt(
            adapter_output, request_id=request_id, adapter_ref=adapter_ref
        )
        if raw_receipt["status"] != "completed":
            updated = _blocked_manifest(
                manifest, code="EXECUTION_NOT_COMPLETED", detail=str(raw_receipt["status"])
            )
            self._checkpoint_dispatch(updated, request_id=request_id, receipt=raw_receipt)
            return updated, raw_receipt

        payload = manifest.to_dict()
        payload["revision"] = manifest.revision + 1
        action_record = {
            "action_id": request.action_id,
            "request_id": request_id,
            "actor_ref": actor_ref,
            "adapter_ref": adapter_ref,
            "receipt": raw_receipt,
        }
        payload["state"]["completed_actions"].append(action_record)
        payload["continuity"]["durable_artifacts"].extend(raw_receipt["artifact_refs"])
        payload["continuity"]["decisions"].append(
            {"kind": "execution", "revision": payload["revision"], **action_record}
        )
        if actor_ref not in payload["integrity"]["material_work_actors"]:
            payload["integrity"]["material_work_actors"].append(actor_ref)
        if self.checkpoint_store is None:
            code = "SESSION_BOUNDED_NO_CHECKPOINT_STORE"
            raw_receipt["coverage_limits"] = list(raw_receipt["coverage_limits"]) + [code]
            payload["capabilities"]["degraded"].append({"code": code})
        updated = MissionManifest.from_dict(payload)
        self._checkpoint_dispatch(updated, request_id=request_id, receipt=raw_receipt)
        return updated, raw_receipt

    def propose_verification(
        self, manifest: MissionManifest, *, actor_ref: str, proof_bundle_ref: str
    ) -> MissionManifest:
        return transition(
            manifest,
            "verifying",
            actor_ref=actor_ref,
            evidence_ref=proof_bundle_ref,
            reason="proof bundle ready",
        )
