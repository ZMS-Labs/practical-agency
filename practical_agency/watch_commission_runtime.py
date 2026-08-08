"""Runtime crossing and revocation handling for retained watch commissions."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from practical_agency.manifest_model import MissionManifest, MissionStatus
from practical_agency.watch_commission_core import (
    CommissionIntegrationError,
    WatchExecutionAdapter,
    _required_receipt_string,
)


def _crossing_return_point(manifest: MissionManifest) -> dict[str, Any]:
    frontier = manifest.state.get("current_frontier")
    next_action = manifest.state.get("next_action")
    index: int | None = None
    label: str | None = None
    if isinstance(frontier, list) and isinstance(next_action, str):
        try:
            index = frontier.index(next_action)
            label = next_action
        except ValueError:
            pass
    return {
        "mission_id": manifest.mission_id,
        "revision": manifest.revision,
        "frontier_index": index,
        "label": label,
        "status": manifest.state.get("status"),
    }


def handle_crossing_event(
    manifest: MissionManifest, event: Mapping[str, Any]
) -> MissionManifest:
    """Retain a crossing as a bounded condition without writing mission state.

    The observer owns evidence emission only. Mission OS may later propose a
    replan citing this receipt, and the mission steward remains the sole writer
    that can apply the new frontier.
    """

    if manifest.authority.get("revoked") is True:
        raise CommissionIntegrationError("AUTHORITY_REVOKED")
    if manifest.state.get("status") == MissionStatus.CANCELLED.value:
        raise CommissionIntegrationError("MISSION_CANCELLED")
    if set(event) != {"commission_id", "event_ref", "observed_at"}:
        raise CommissionIntegrationError("INVALID_CROSSING_EVENT")
    commission_id = _required_receipt_string(
        event, "commission_id", "COMMISSION_ID_REQUIRED"
    )
    event_ref = _required_receipt_string(
        event, "event_ref", "EVENT_RECEIPT_REQUIRED"
    )
    observed_at = _required_receipt_string(
        event, "observed_at", "EVENT_OBSERVED_AT_REQUIRED"
    )
    retained = manifest.continuity.get("watch_commissions", [])
    matching = next(
        (
            record
            for record in retained
            if isinstance(record, Mapping)
            and record.get("commission_id") == commission_id
        ),
        None,
    )
    if matching is None:
        raise CommissionIntegrationError("COMMISSION_NOT_RETAINED")
    observer = matching.get("external_observer")
    if (
        matching.get("state") != "PROVEN"
        or not isinstance(observer, Mapping)
        or observer.get("enabled") is not True
    ):
        raise CommissionIntegrationError("COMMISSION_NOT_OPERATING")
    if any(
        isinstance(item, Mapping)
        and item.get("kind") == "watch-crossing"
        and item.get("event_ref") == event_ref
        for item in manifest.continuity.get("external_handoffs", [])
    ):
        raise CommissionIntegrationError("CROSSING_EVENT_ALREADY_RETAINED")

    data = manifest.to_dict()
    data["continuity"]["external_handoffs"].append(
        {
            "kind": "watch-crossing",
            "commission_id": commission_id,
            "event_ref": event_ref,
            "observed_at": observed_at,
            "unanswered_condition": (
                "What mission action, if any, is authorized by crossing "
                f"{event_ref} for retained commission {commission_id}?"
            ),
            "expected_output_contract": (
                "A revision-bound mission OS replan proposal citing event_ref, "
                "or an explicit no-op."
            ),
            "return_point": _crossing_return_point(manifest),
        }
    )
    data["revision"] = manifest.revision + 1
    return MissionManifest.from_dict(data)


def disable_commissions_for_revocation(
    manifest: MissionManifest, adapter: WatchExecutionAdapter
) -> tuple[MissionManifest, list[dict[str, Any]]]:
    if manifest.authority.get("revoked") is not True:
        raise CommissionIntegrationError("AUTHORITY_NOT_REVOKED")

    data = manifest.to_dict()
    receipts: list[dict[str, Any]] = []
    retained = data["continuity"]["watch_commissions"]
    for index, record in enumerate(retained):
        if not isinstance(record, Mapping):
            continue
        updated = deepcopy(dict(record))
        observer = updated.get("external_observer")
        if not isinstance(observer, dict):
            continue
        mechanism_ref = observer.get("mechanism_ref")
        if not isinstance(mechanism_ref, str) or not mechanism_ref:
            continue
        raw_result = adapter.disable(mechanism_ref)
        if not isinstance(raw_result, Mapping):
            raise CommissionIntegrationError("DISABLE_RECEIPT_MUST_BE_OBJECT")
        result = deepcopy(dict(raw_result))
        if set(result) != {
            "mechanism_ref",
            "disabled",
            "observed_at",
            "disable_receipt_ref",
        }:
            raise CommissionIntegrationError("INVALID_DISABLE_RECEIPT")
        if result.get("mechanism_ref") != mechanism_ref:
            raise CommissionIntegrationError("DISABLE_MECHANISM_MISMATCH")
        if result.get("disabled") is not True:
            raise CommissionIntegrationError("DISABLE_NOT_OBSERVED")
        _required_receipt_string(
            result, "observed_at", "DISABLE_OBSERVED_AT_REQUIRED"
        )
        _required_receipt_string(
            result, "disable_receipt_ref", "DISABLE_RECEIPT_REF_REQUIRED"
        )
        observer["enabled"] = False
        if updated.get("state") in {"PROVEN", "SUSPECT"}:
            updated["state"] = "INERT"
            updated["failure"] = {
                "kind": None,
                "detail": None,
                "observed_at": None,
                "receipt_ref": None,
            }
        retained[index] = updated
        receipts.append(result)
        data["continuity"]["external_handoffs"].append(
            {
                "kind": "watch-disable-on-revocation",
                "commission_id": updated.get("commission_id"),
                **deepcopy(result),
            }
        )

    if receipts:
        data["revision"] = manifest.revision + 1
        return MissionManifest.from_dict(data), receipts
    return manifest, receipts
