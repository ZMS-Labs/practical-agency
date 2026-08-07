from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from typing import Any

from practical_agency.capability_discovery import FileSystemSkillProvider
from practical_agency.checkpoint_store import (
    FileCheckpointStore,
    apply_reconciliation_findings,
    reconcile_observations,
)
from practical_agency.coordinator import coordinate_once, dispatch_once
from practical_agency.manifest_model import MissionManifest
from practical_agency.state_machine import MissionEvent, TransitionError, apply_event
from tests.helpers import clone_payload


class MemoryAdapter:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(request)
        call = len(self.calls)
        return {
            "schema": "execution-receipt@1",
            "request_id": request["request_id"],
            "mission_id": request["mission_id"],
            "mission_revision": request["mission_revision"],
            "adapter_ref": "memory:test",
            "status": "completed",
            "artifact_refs": [f"artifact:call-{call}"],
            "observed_effects": request.get("requested_effects", []),
            "external_receipt_ref": f"memory://receipt/{call}",
            "coverage_limits": ["in-memory fixture only"],
        }


class EndToEndMissionTests(unittest.TestCase):
    def test_resumable_independently_accepted_mission(self) -> None:
        original_instruction = "Keep  the operator's exact words\nacross every restart."
        payload = clone_payload()
        payload["authority"]["instruction"] = original_instruction
        payload["integrity"]["completion_acceptor"] = "reviewer:test"
        draft = MissionManifest.from_dict(payload)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = FileCheckpointStore(root / "checkpoints")
            first_receipt = store.save(draft)
            active = apply_event(
                draft,
                MissionEvent(
                    "approve",
                    "operator:test",
                    {"checkpoint_ref": first_receipt.path},
                ),
            )

            skills = root / "skills"
            fixture = skills / "fixture-writer"
            fixture.mkdir(parents=True)
            fixture.joinpath("SKILL.md").write_text(
                "---\nname: fixture-writer\ndescription: Use to write the fixture.\n"
                "metadata:\n  persistence: session\n  independence: actor\n"
                "  authority_required: [repository:write]\n---\n# fixture\n",
                encoding="utf-8",
            )
            discovered = FileSystemSkillProvider(skills).discover()
            self.assertEqual(
                [item.capability_id for item in discovered], ["fixture-writer"]
            )

            adapter = MemoryAdapter()
            decision = coordinate_once(
                active,
                execution_request={
                    "capability_id": "fixture-writer",
                    "requested_permissions": ["repository:write"],
                    "requested_effects": ["intended files"],
                    "estimated_costs": ["one feature branch"],
                    "action": "write canonical artifact",
                },
                checkpoint_store=store,
            )
            result = dispatch_once(active, decision, adapter)
            acted = apply_event(
                active,
                MissionEvent(
                    "record_action",
                    "mission-steward",
                    {"action_ref": result["artifact_refs"][0]},
                ),
            )
            artifact_hash = hashlib.sha256(b"canonical artifact").hexdigest()
            observed = apply_event(
                acted,
                MissionEvent(
                    "record_observation",
                    "observer:test",
                    {
                        "artifact_ref": "artifact:validator-pass",
                        "fact": {
                            "subject_ref": "artifact:canonical",
                            "value": artifact_hash,
                        },
                    },
                ),
            )
            checkpoint = store.save(observed)

            del draft, active, acted, observed, decision, result
            resumed = store.load(checkpoint)
            self.assertEqual(resumed.authority["instruction"], original_instruction)

            live_hash = hashlib.sha256(b"unexpected live artifact").hexdigest()
            findings = reconcile_observations(
                resumed, {"artifact:canonical": live_hash}
            )
            self.assertEqual(findings[0].classification, "CONTRADICTED")
            reopened = apply_reconciliation_findings(resumed, findings)
            self.assertEqual(reopened.state["status"], "active")
            self.assertTrue(reopened.state["blockers"])
            self.assertNotIn(
                "artifact:validator-pass",
                reopened.continuity["durable_artifacts"],
            )
            with self.assertRaisesRegex(TransitionError, "UNRESOLVED_BLOCKERS"):
                apply_event(
                    reopened,
                    MissionEvent("begin_verification", "mission-steward", {}),
                )

            correction = coordinate_once(
                reopened,
                execution_request={
                    "capability_id": "fixture-writer",
                    "requested_permissions": ["repository:write"],
                    "requested_effects": ["intended files"],
                    "estimated_costs": ["one feature branch"],
                    "action": reopened.state["next_action"],
                },
                checkpoint_store=store,
            )
            correction_result = dispatch_once(reopened, correction, adapter)
            corrected = apply_event(
                reopened,
                MissionEvent(
                    "record_action",
                    "mission-steward",
                    {"action_ref": correction_result["artifact_refs"][0]},
                ),
            )
            self.assertNotIn(
                "artifact:validator-pass",
                corrected.continuity["durable_artifacts"],
            )

            repaired_hash = hashlib.sha256(b"repaired canonical artifact").hexdigest()
            reobserved = apply_event(
                corrected,
                MissionEvent(
                    "record_observation",
                    "observer:test",
                    {
                        "artifact_ref": "artifact:validator-pass",
                        "fact": {
                            "subject_ref": "artifact:canonical",
                            "value": repaired_hash,
                        },
                    },
                ),
            )
            self.assertEqual(reobserved.state["blockers"], [])
            self.assertEqual(reobserved.integrity["unresolved_verdicts"], [])
            verifying = apply_event(
                reobserved,
                MissionEvent("begin_verification", "mission-steward", {}),
            )

            verdict = {
                "verdict": "PASS",
                "evidence_refs": ["artifact:independent-review"],
                "coverage_limits": ["isolated fixture"],
            }
            with self.assertRaisesRegex(
                TransitionError, "INDEPENDENT_ACCEPTANCE_REQUIRED"
            ):
                apply_event(
                    verifying,
                    MissionEvent("accept", "mission-steward", verdict),
                )

            completed = apply_event(
                verifying,
                MissionEvent("accept", "reviewer:test", verdict),
            )
            final_receipt = store.save(completed)
            final = store.load(final_receipt)
            self.assertEqual(final.state["status"], "completed")
            self.assertEqual(final.authority["instruction"], original_instruction)
            self.assertEqual(len(adapter.calls), 2)
            self.assertEqual(
                final.continuity["decisions"][-1]["evidence_refs"],
                ["artifact:independent-review"],
            )


if __name__ == "__main__":
    unittest.main()
