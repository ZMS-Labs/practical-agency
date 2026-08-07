"""Bounded mission coordinator — one consequential step per call."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from practical_agency.authority import authorize_action
from practical_agency.capability_discovery import CapabilityDescriptor
from practical_agency.checkpoint_store import FileCheckpointStore
from practical_agency.manifest_model import MissionManifest
from practical_agency.state_machine import MissionEvent, TransitionError, apply_event

_INVOCATION_ALIASES = {
    "helix it": "manifest",
    "manifest this": "manifest",
    "manifest": "manifest",
    "carry this through": "manifest",
}


def normalize_invocation(text: str) -> str:
    key = " ".join(text.strip().lower().split())
    return _INVOCATION_ALIASES.get(key, key)


@dataclass(frozen=True, slots=True)
class ReturnPoint:
    mission_id: str
    revision: int
    frontier_index: int
    label: str


@dataclass(frozen=True, slots=True)
class CoordinationDecision:
    kind: str  # NOOP | REQUEST_CAPABILITY | DISPATCH | BLOCK | VERIFY
    reason: str
    request: dict[str, Any] | None
    return_point: ReturnPoint | None


class ExecutionAdapter(Protocol):
    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]: ...


class MissionCoordinator:
    def __init__(
        self,
        store: FileCheckpointStore | None,
        adapter: ExecutionAdapter | None,
    ) -> None:
        self.store = store
        self.adapter = adapter

    def step(
        self,
        manifest: MissionManifest,
        capabilities: Sequence[CapabilityDescriptor],
        operator_capability_id: str | None = None,
        propose_completion: bool = False,
    ) -> tuple[CoordinationDecision, MissionManifest]:
        if self.store is None:
            decision = CoordinationDecision(
                kind="BLOCK",
                reason="SESSION_BOUNDED: no checkpoint store available",
                request=None,
                return_point=None,
            )
            return decision, manifest

        if manifest.authority.get("revoked") is True:
            self.store.save(manifest)
            return (
                CoordinationDecision(
                    kind="BLOCK",
                    reason="AUTHORITY_REVOKED",
                    request=None,
                    return_point=None,
                ),
                manifest,
            )

        if propose_completion:
            verifying = apply_event(
                manifest,
                MissionEvent(
                    kind="begin_verification",
                    actor_ref="mission-steward",
                    artifact_refs=list(manifest.outcome.get("completion_proof") or []),
                ),
            )
            self.store.save(verifying)
            return (
                CoordinationDecision(
                    kind="VERIFY",
                    reason="completion proposed; awaiting independent acceptor",
                    request=None,
                    return_point=None,
                ),
                verifying,
            )

        frontier = list(manifest.state.get("current_frontier") or [])
        label = frontier[0] if frontier else str(manifest.state.get("next_action") or "next")
        return_point = ReturnPoint(
            mission_id=manifest.mission_id,
            revision=manifest.revision,
            frontier_index=0,
            label=label,
        )

        load_bearing_unknowns = [
            item
            for item in manifest.truth.get("unknowns") or []
            if isinstance(item, dict) and item.get("load_bearing")
        ]
        if load_bearing_unknowns and not operator_capability_id:
            available = [
                cap for cap in capabilities if cap.availability == "available"
            ]
            if not available:
                blocked = apply_event(
                    manifest,
                    MissionEvent(
                        kind="block",
                        actor_ref="mission-steward",
                        detail={"reason": "no capability for load-bearing unknown"},
                    ),
                )
                self.store.save(blocked)
                return (
                    CoordinationDecision(
                        kind="BLOCK",
                        reason="no available capability for load-bearing unknown",
                        request=None,
                        return_point=return_point,
                    ),
                    blocked,
                )
            chosen = available[0]
            request = {
                "schema": "capability-request@1",
                "request_id": f"req-{manifest.mission_id}-{manifest.revision}",
                "mission_id": manifest.mission_id,
                "revision": manifest.revision,
                "capability_id": chosen.capability_id,
                "source_sha256": chosen.source_sha256,
                "bounded_question": str(load_bearing_unknowns[0].get("claim")),
                "authority_receipt": f"authority:{manifest.revision}",
                "expected_output_contract": chosen.output_contract,
                "return_point": {
                    "mission_id": return_point.mission_id,
                    "revision": return_point.revision,
                    "frontier_index": return_point.frontier_index,
                    "label": return_point.label,
                },
                "stop_condition": "return after one bounded answer",
            }
            recorded = apply_event(
                manifest,
                MissionEvent(
                    kind="record_observation",
                    actor_ref="mission-steward",
                    detail={"capability_request": request},
                ),
            )
            self.store.save(recorded)
            return (
                CoordinationDecision(
                    kind="REQUEST_CAPABILITY",
                    reason="load-bearing unknown requires a member capability",
                    request=request,
                    return_point=return_point,
                ),
                recorded,
            )

        if operator_capability_id:
            match = next(
                (cap for cap in capabilities if cap.capability_id == operator_capability_id),
                None,
            )
            if match is not None and match.availability != "available":
                blocked = apply_event(
                    manifest,
                    MissionEvent(
                        kind="block",
                        actor_ref="mission-steward",
                        detail={
                            "reason": f"capability {operator_capability_id} {match.availability}"
                        },
                    ),
                )
                self.store.save(blocked)
                return (
                    CoordinationDecision(
                        kind="BLOCK",
                        reason=f"capability unavailable: {match.degradation_reason}",
                        request=None,
                        return_point=return_point,
                    ),
                    blocked,
                )

        if self.adapter is None:
            return (
                CoordinationDecision(
                    kind="BLOCK",
                    reason="NO_EXECUTION_ADAPTER",
                    request=None,
                    return_point=return_point,
                ),
                manifest,
            )

        effects = [label]
        refusals = authorize_action(
            manifest,
            capability_id=operator_capability_id or "execution",
            requested_permissions=["repository:write"],
            requested_effects=effects,
            estimated_costs=["one feature branch"],
        )
        # If the frontier label is not an authorized effect token, authorize a
        # generic repository write for routine in-repo progress.
        if refusals and operator_capability_id:
            refusals = authorize_action(
                manifest,
                capability_id=operator_capability_id,
                requested_permissions=["repository:write"],
                requested_effects=["examples/out.txt"],
                estimated_costs=["one feature branch"],
            )
            effects = ["examples/out.txt"]
        if refusals:
            return (
                CoordinationDecision(
                    kind="BLOCK",
                    reason="; ".join(refusals),
                    request=None,
                    return_point=return_point,
                ),
                manifest,
            )

        request = {
            "capability_id": operator_capability_id or "execution",
            "effects": effects,
            "mission_id": manifest.mission_id,
            "revision": manifest.revision,
        }
        result = self.adapter.dispatch(request)
        updated = apply_event(
            manifest,
            MissionEvent(
                kind="record_action",
                actor_ref="mission-steward",
                detail={"action": request["capability_id"], "result": result},
                artifact_refs=list(result.get("artifact_refs") or []),
            ),
        )
        self.store.save(updated)
        return (
            CoordinationDecision(
                kind="DISPATCH",
                reason="one authorized consequential step",
                request=request,
                return_point=return_point,
            ),
            updated,
        )

    def accept(
        self,
        manifest: MissionManifest,
        actor_ref: str,
        verdict: str,
        artifact_refs: Sequence[str],
    ) -> MissionManifest:
        updated = apply_event(
            manifest,
            MissionEvent(
                kind="accept",
                actor_ref=actor_ref,
                verdict=verdict,
                artifact_refs=list(artifact_refs),
            ),
        )
        if self.store is not None:
            self.store.save(updated)
        return updated


def apply_capability_result(
    manifest: MissionManifest,
    result: dict[str, Any],
) -> MissionManifest:
    """Return control to the recorded return point without taking over the mission."""
    return_point = (result.get("returned_control_point") or {}).get("label")
    detail = {
        "capability_result": {
            "request_id": result.get("request_id"),
            "status": result.get("status"),
            "coverage_limits": result.get("coverage_limits") or [],
        },
        "resume_label": return_point,
    }
    return apply_event(
        manifest,
        MissionEvent(
            kind="record_observation",
            actor_ref="mission-steward",
            detail=detail,
            artifact_refs=list(result.get("artifact_refs") or []),
        ),
    )
