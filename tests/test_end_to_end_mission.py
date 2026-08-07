from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from typing import Any

from practical_agency.capability_discovery import FileSystemSkillProvider
from practical_agency.checkpoint_store import FileCheckpointStore, reconcile_observations
from practical_agency.coordinator import coordinate_once, dispatch_once
from practical_agency.manifest_model import MissionManifest
from practical_agency.state_machine import MissionEvent, TransitionError, apply_event
from tests.helpers import clone_payload


class MemoryAdapter:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(request)
        return {
            "status": "completed",
            "artifact_ref": f"artifact:call-{len(self.calls)}",
            "observed_effects": request.get("requested_effects", []),
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
                MissionEvent("approve", "operator:test", {"checkpoint_ref": first_receipt.path}),
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
            self.assertEqual([item.capability_id for item in discovered], ["fixture-writer"])

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
                MissionEvent("record_action", "mission-steward", {"action_ref": result["artifact_ref"]}),
            )
            artifact_hash = hashlib.sha256(b"canonical artifact").hexdigest()
            observed = apply_event(
                acted,
                MissionEvent(
                    "record_observation",
                    "observer:test",
                    {
                        "artifact_ref": "artifact:validator-pass",
                        "fact": {"subject_ref": "artifact:canonical", "value": artifact_hash},
                    },
                ),
            )
            checkpoint = store.save(observed)

            del draft, active, acted, observed, decision, result
            resumed = store.load(checkpoint)
            self.assertEqual(resumed.authority["instruction"], original_instruction)

            findings = reconcile_observations(resumed, {"artifact:canonical": "different-live-hash"})
            self.assertEqual(findings[0].classification, "CONTRADICTED")
            blocked = apply_event(
                resumed,
                MissionEvent("block", "mission-steward", {"reason": "live state contradicted checkpoint"}),
            )
            reopened = apply_event(blocked, MissionEvent("unblock", "mission-steward", {}))

            correction = coordinate_once(
                reopened,
                execution_request={
                    "capability_id": "fixture-writer",
                    "requested_permissions": ["repository:write"],
                    "requested_effects": ["intended files"],
                    "estimated_costs": ["one feature branch"],
                    "action": "repair canonical artifact",
                },
                checkpoint_store=store,
            )
            correction_result = dispatch_once(reopened, correction, adapter)
            corrected = apply_event(
                reopened,
                MissionEvent("record_action", "mission-steward", {"action_ref": correction_result["artifact_ref"]}),
            )
            verifying = apply_event(corrected, MissionEvent("begin_verification", "mission-steward", {}))

            with self.assertRaisesRegex(TransitionError, "INDEPENDENT_ACCEPTANCE_REQUIRED"):
                apply_event(verifying, MissionEvent("accept", "mission-steward", {"verdict": "PASS"}))

            completed = apply_event(verifying, MissionEvent("accept", "reviewer:test", {"verdict": "PASS"}))
            final_receipt = store.save(completed)
            final = store.load(final_receipt)
            self.assertEqual(final.state["status"], "completed")
            self.assertEqual(final.authority["instruction"], original_instruction)
            self.assertEqual(len(adapter.calls), 2)


if __name__ == "__main__":
    unittest.main()
