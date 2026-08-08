from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from dataclasses import fields
from pathlib import Path
from typing import Any
from unittest.mock import patch

import practical_agency.filesystem_artifact as filesystem_artifact
from practical_agency.capability_discovery import (
    CapabilityDescriptor,
    FileSystemSkillProvider,
    Persistence,
)
from practical_agency.checkpoint_store import FileCheckpointStore
from practical_agency.coordinator import (
    CoordinationDecision,
    CoordinationError,
    ReturnPoint,
    coordinate_once,
    dispatch_once,
)
from practical_agency.manifest_model import MissionManifest
from practical_agency.mission_os import (
    emit_unanswered_condition,
    propose_defer,
    propose_frontier_patch,
    propose_replan_slice,
)
from practical_agency.state_machine import MissionEvent, TransitionError, apply_event
from practical_agency.watch_commission import handle_crossing_event
from tests.helpers import clone_payload


_EVENT_FIELDS = {
    "schema",
    "event_id",
    "mission_id",
    "expected_revision",
    "kind",
    "actor_ref",
    "data",
    "observed_at",
}


def active_manifest(*, applied_frontier: bool) -> MissionManifest:
    payload = clone_payload()
    payload["revision"] = 2
    payload["state"]["status"] = "active"
    payload["state"]["current_frontier"] = ["write authorized artifact"]
    payload["state"]["next_action"] = "write authorized artifact"
    payload["continuity"]["prior_checkpoint"] = "checkpoint:1"
    if applied_frontier:
        payload["continuity"]["decisions"].append(
            {
                "kind": "mission-os-apply",
                "proposal_kind": "frontier_patch",
                "actor_ref": "mission-steward",
                "at_revision": 2,
            }
        )
    return MissionManifest.from_dict(payload)


def completed_watched_manifest() -> MissionManifest:
    payload = clone_payload()
    payload["revision"] = 5
    payload["state"]["status"] = "completed"
    payload["state"]["current_frontier"] = []
    payload["state"]["next_action"] = None
    payload["continuity"]["prior_checkpoint"] = "checkpoint:4"
    payload["integrity"]["completion_acceptor"] = "reviewer:test"
    payload["continuity"]["watch_commissions"] = [
        {
            "commission_id": "wc-1",
            "state": "PROVEN",
            "external_observer": {"enabled": True},
        }
    ]
    return MissionManifest.from_dict(payload)


def mission_event(
    manifest: MissionManifest,
    *,
    event_id: str,
    kind: str,
    actor_ref: str,
    data: dict[str, Any],
) -> MissionEvent:
    return MissionEvent(
        schema="mission-event@1",
        event_id=event_id,
        mission_id=manifest.mission_id,
        expected_revision=manifest.revision,
        kind=kind,
        actor_ref=actor_ref,
        data=data,
        observed_at="2026-08-08T06:00:00Z",
    )


def fixture_capability() -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability_id="fixture",
        kind="skill",
        source_ref="fixture://skill",
        source_sha256="a" * 64,
        description="Use for one bounded question.",
        input_contract=None,
        output_contract=None,
        authority_required=("repository:write",),
        persistence=Persistence.SESSION,
        independence="actor",
        availability="available",
        degradation_reason=None,
    )


class RecordingAdapter:
    capability_id = "fixture"
    adapter_ref = "fixture://recording-adapter"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(request)
        return {
            "schema": "execution-receipt@1",
            "request_id": request["request_id"],
            "mission_id": request["mission_id"],
            "mission_revision": request["mission_revision"],
            "adapter_ref": self.adapter_ref,
            "status": "completed",
            "artifact_refs": ["artifact:fixture"],
            "observed_effects": [],
            "external_receipt_ref": "fixture://receipt/1",
            "coverage_limits": ["fixture only"],
        }


class Pr7MergeReadinessTests(unittest.TestCase):
    def test_unknown_additive_metadata_does_not_degrade_real_skill_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            skill = Path(temp) / "metacognate" / "SKILL.md"
            skill.parent.mkdir()
            skill.write_text(
                "---\n"
                "name: metacognate\n"
                "description: Decide which unanswerable condition names the work.\n"
                "metadata:\n"
                "  hands-to: []\n"
                "---\n",
                encoding="utf-8",
            )
            descriptor = FileSystemSkillProvider(Path(temp)).discover()[0]
        self.assertEqual(descriptor.capability_id, "metacognate")
        self.assertEqual(descriptor.availability, "available")
        self.assertIsNone(descriptor.degradation_reason)

    def test_pinned_upstream_metacognate_descriptor_is_discoverable(self) -> None:
        root = os.environ.get("PRACTICAL_AGENCY_UPSTREAM_EPISTEMIC_SKILLS_ROOT")
        if root is None:
            self.skipTest("pinned upstream skill tree is supplied by CI")
        descriptors = FileSystemSkillProvider(Path(root)).discover()
        metacognate = next(item for item in descriptors if item.capability_id == "metacognate")
        self.assertEqual(metacognate.availability, "available")
        self.assertIsNone(metacognate.degradation_reason)

    def test_watch_crossing_records_condition_without_writing_frontier(self) -> None:
        manifest = completed_watched_manifest()
        updated = handle_crossing_event(
            manifest,
            {
                "commission_id": "wc-1",
                "event_ref": "external-event://1",
                "observed_at": "2026-08-08T06:00:00Z",
            },
        )
        self.assertEqual(updated.state, manifest.state)
        handoff = updated.continuity["external_handoffs"][-1]
        self.assertEqual(handoff["kind"], "watch-crossing")
        self.assertIn("unanswered_condition", handoff)
        self.assertIn("return_point", handoff)
        self.assertNotIn("hands_to", handoff)

    def test_capability_interrupt_requires_applied_frontier_unconditionally(self) -> None:
        decision = coordinate_once(
            active_manifest(applied_frontier=False),
            unresolved_condition="Which evidence actually bears load?",
            selected_capability=fixture_capability(),
            checkpoint_store=object(),
            require_applied_frontier=False,
        )
        self.assertEqual(decision.kind, "BLOCK")
        self.assertEqual(decision.reason, "MISSION_OS_APPLY_REQUIRED")

    def test_execution_requires_applied_frontier_unconditionally(self) -> None:
        decision = coordinate_once(
            active_manifest(applied_frontier=False),
            execution_request={
                "capability_id": "fixture",
                "requested_permissions": ["repository:write"],
                "requested_effects": ["intended files"],
                "estimated_costs": ["one feature branch"],
                "action": "write authorized artifact",
            },
            checkpoint_store=object(),
            require_applied_frontier=False,
        )
        self.assertEqual(decision.kind, "BLOCK")
        self.assertEqual(decision.reason, "MISSION_OS_APPLY_REQUIRED")

    def test_forged_dispatch_is_reauthorized_before_adapter_call(self) -> None:
        manifest = active_manifest(applied_frontier=True)
        request = {
            "schema": "execution-request@1",
            "request_id": f"{manifest.mission_id}:r{manifest.revision}:fixture:execution:f0",
            "mission_id": manifest.mission_id,
            "mission_revision": manifest.revision,
            "capability_id": "fixture",
            "requested_permissions": ["network:write"],
            "requested_effects": [],
            "estimated_costs": [],
            "action": "write authorized artifact",
        }
        decision = CoordinationDecision(
            "DISPATCH",
            "forged",
            request,
            ReturnPoint(manifest.mission_id, manifest.revision, 0, "write authorized artifact"),
        )
        adapter = RecordingAdapter()
        with self.assertRaisesRegex(CoordinationError, "PERMISSION_NOT_GRANTED:network:write"):
            dispatch_once(manifest, decision, adapter)
        self.assertEqual(adapter.calls, [])

    def test_dispatch_refuses_adapter_capability_mismatch_before_effect(self) -> None:
        manifest = active_manifest(applied_frontier=True)
        decision = coordinate_once(
            manifest,
            execution_request={
                "capability_id": "fixture",
                "requested_permissions": ["repository:write"],
                "requested_effects": ["intended files"],
                "estimated_costs": ["one feature branch"],
                "action": "write authorized artifact",
            },
            checkpoint_store=object(),
        )
        adapter = RecordingAdapter()
        adapter.capability_id = "other"
        with self.assertRaisesRegex(CoordinationError, "ADAPTER_CAPABILITY_MISMATCH"):
            dispatch_once(manifest, decision, adapter)
        self.assertEqual(adapter.calls, [])

    def test_runtime_mission_event_matches_published_contract(self) -> None:
        self.assertTrue(_EVENT_FIELDS.issubset({item.name for item in fields(MissionEvent)}))

    def test_cross_mission_event_is_refused(self) -> None:
        manifest = MissionManifest.from_dict(clone_payload())
        event = MissionEvent(
            schema="mission-event@1",
            event_id="event:cross-mission",
            mission_id="other-mission",
            expected_revision=manifest.revision,
            kind="approve",
            actor_ref="operator:test",
            data={"checkpoint_ref": "checkpoint:1"},
            observed_at="2026-08-08T06:00:00Z",
        )
        with self.assertRaisesRegex(TransitionError, "EVENT_MISSION_MISMATCH"):
            apply_event(manifest, event)

    def test_replayed_event_id_is_refused_before_stale_revision(self) -> None:
        manifest = MissionManifest.from_dict(clone_payload())
        event = mission_event(
            manifest,
            event_id="event:approve:1",
            kind="approve",
            actor_ref="operator:test",
            data={"checkpoint_ref": "checkpoint:1"},
        )
        updated = apply_event(manifest, event)
        with self.assertRaisesRegex(TransitionError, "EVENT_ALREADY_APPLIED"):
            apply_event(updated, event)

    def test_mission_os_proposal_is_revision_and_hash_bound(self) -> None:
        manifest = active_manifest(applied_frontier=True)
        proposal = propose_frontier_patch(
            manifest,
            ["write authorized artifact"],
            basis_refs=["authority:instruction"],
        )
        for key in (
            "proposal_id",
            "proposal_mission_id",
            "proposal_base_revision",
            "proposal_payload_sha256",
            "basis_refs",
        ):
            self.assertIn(key, proposal.payload)
        tampered = dict(proposal.payload)
        tampered["labels"] = ["invent an unrelated objective"]
        event = mission_event(
            manifest,
            event_id="event:tampered-proposal",
            kind="apply_mission_os",
            actor_ref="mission-steward",
            data={"proposal_kind": proposal.kind, **tampered},
        )
        with self.assertRaisesRegex(TransitionError, "MISSION_OS_PROPOSAL_HASH_MISMATCH"):
            apply_event(manifest, event)

    def test_replan_cannot_manufacture_a_contradiction_reference(self) -> None:
        manifest = active_manifest(applied_frontier=True)
        with self.assertRaisesRegex(ValueError, "REPLAN_CONTRADICTION_UNKNOWN"):
            propose_replan_slice(
                manifest,
                new_frontier=["repair contradicted evidence"],
                contradiction_refs=["truth:invented"],
                basis_refs=["authority:instruction"],
            )

    def test_ambiguous_deferral_fails_closed(self) -> None:
        manifest = active_manifest(applied_frontier=True)
        interest = {
            "schema": "deferred-interest@1",
            "mission_id": manifest.mission_id,
            "summary": "polish the proof later",
            "criticality": "low",
            "why_not_now": "appears optional",
            "suggested_next": None,
            "subject_refs": [],
            "created_at_revision": manifest.revision,
            "status": "open",
        }
        with self.assertRaisesRegex(ValueError, "DEFER_CRITICAL_PATH_AMBIGUOUS"):
            propose_defer(manifest, interest)

    def test_invalid_frontier_index_is_refused(self) -> None:
        manifest = active_manifest(applied_frontier=True)
        with self.assertRaisesRegex(ValueError, "INVALID_FRONTIER_INDEX"):
            emit_unanswered_condition(manifest, "Need one bounded answer", frontier_index=3)

    def test_receipt_filename_is_a_safe_digest_even_for_slash_in_request_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            adapter = filesystem_artifact.FilesystemArtifactAdapter(Path(temp))
            request = {
                "request_id": "mission/r2:filesystem-artifact:execution:f0",
                "mission_id": "mission-001",
                "mission_revision": 2,
                "action": "write-text",
                "requested_effects": [
                    "relpath:mission-artifacts/result.txt",
                    "utf8:hello",
                ],
            }
            receipt = adapter.dispatch(request)
            receipt_path = Path(receipt["external_receipt_ref"])
            self.assertEqual(receipt["status"], "completed")
            self.assertRegex(receipt_path.name, r"^[0-9a-f]{64}\.json$")
            self.assertEqual(receipt_path.parent.name, ".receipts")

    def test_prepared_journal_survives_failure_after_world_effect(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            adapter = filesystem_artifact.FilesystemArtifactAdapter(root)
            request_id = "mission-001:r2:filesystem-artifact:execution:f0"
            request = {
                "request_id": request_id,
                "mission_id": "mission-001",
                "mission_revision": 2,
                "action": "write-text",
                "requested_effects": [
                    "relpath:mission-artifacts/result.txt",
                    "utf8:hello",
                ],
            }
            real_replace = os.replace
            calls = 0

            def fail_final_receipt(source: str | bytes | Path, target: str | bytes | Path) -> None:
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise OSError("injected final receipt failure")
                real_replace(source, target)

            with patch.object(filesystem_artifact.os, "replace", side_effect=fail_final_receipt):
                with self.assertRaisesRegex(OSError, "injected final receipt failure"):
                    adapter.dispatch(request)

            journal = root / ".receipts" / f"{hashlib.sha256(request_id.encode()).hexdigest()}.json"
            self.assertTrue(journal.is_file())
            self.assertEqual(json.loads(journal.read_text(encoding="utf-8"))["status"], "prepared")
            self.assertEqual((root / "mission-artifacts" / "result.txt").read_text(), "hello")

    def test_checkpoint_resume_recovers_and_verifies_external_execution_receipt(self) -> None:
        verify_receipt = getattr(filesystem_artifact, "verify_filesystem_receipt", None)
        self.assertIsNotNone(verify_receipt)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = active_manifest(applied_frontier=True)
            adapter = filesystem_artifact.FilesystemArtifactAdapter(root / "effects")
            request = {
                "request_id": f"{manifest.mission_id}:r{manifest.revision}:filesystem-artifact:execution:f0",
                "mission_id": manifest.mission_id,
                "mission_revision": manifest.revision,
                "action": "write-text",
                "requested_effects": [
                    "relpath:mission-artifacts/result.txt",
                    "utf8:durable result",
                ],
            }
            execution_receipt = adapter.dispatch(request)
            recorded = apply_event(
                manifest,
                mission_event(
                    manifest,
                    event_id="event:execution-receipt:1",
                    kind="record_execution_receipt",
                    actor_ref="mission-steward",
                    data={"receipt": execution_receipt},
                ),
            )
            store = FileCheckpointStore(root / "checkpoints")
            checkpoint = store.save(recorded)
            resumed = store.load(checkpoint)
            retained = next(
                item
                for item in resumed.continuity["decisions"]
                if item.get("kind") == "execution-receipt"
            )
            verified = verify_receipt(retained["external_receipt_ref"])
            self.assertEqual(verified["request_id"], execution_receipt["request_id"])
            self.assertEqual(verified["status"], "completed")


if __name__ == "__main__":
    unittest.main()
