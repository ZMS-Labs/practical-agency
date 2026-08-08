from __future__ import annotations

import re
import unittest
from pathlib import Path

from practical_agency.mission_os import (
    emit_unanswered_condition,
    propose_defer,
    propose_frontier_patch,
    propose_replan_slice,
    propose_return_rebind,
)
from practical_agency.manifest_model import MissionManifest
from tests.helpers import clone_payload


class MissionOsProposeTests(unittest.TestCase):
    def active(self) -> MissionManifest:
        payload = clone_payload()
        payload["revision"] = 2
        payload["state"]["status"] = "active"
        payload["state"]["current_frontier"] = [
            "write authorized artifact",
            "verify artifact hash",
        ]
        payload["continuity"]["prior_checkpoint"] = "checkpoint:1"
        return MissionManifest.from_dict(payload)

    def test_propose_does_not_mutate_manifest(self) -> None:
        manifest = self.active()
        before = manifest.to_dict()
        proposal = propose_frontier_patch(
            manifest, ["write authorized artifact", "verify artifact hash"]
        )
        self.assertEqual(proposal.kind, "frontier_patch")
        self.assertEqual(manifest.to_dict(), before)
        self.assertEqual(
            manifest.state["current_frontier"],
            ["write authorized artifact", "verify artifact hash"],
        )

    def test_frontier_labels_reject_skill_name_shaped_tokens(self) -> None:
        with self.assertRaisesRegex(ValueError, "FRONTIER_LABEL_FORBIDDEN"):
            propose_frontier_patch(
                self.active(),
                ["run metacognate next"],
                forbidden_substrings=("metacognate",),
            )

    def test_propose_defer_deep_copies_interest_subject_refs(self) -> None:
        manifest = self.active()
        interest = {
            "schema": "deferred-interest@1",
            "mission_id": "mission-001",
            "summary": "side note",
            "criticality": "low",
            "why_not_now": "distraction",
            "suggested_next": None,
            "subject_refs": ["ref:a"],
            "created_at_revision": 2,
            "status": "open",
        }
        proposal = propose_defer(manifest, interest)
        interest["subject_refs"].append("ref:mutated")
        self.assertEqual(
            proposal.payload["interest"]["subject_refs"],
            ["ref:a"],
        )

    def test_propose_return_rebind_kind(self) -> None:
        proposal = propose_return_rebind(
            self.active(),
            [{"kind": "subject", "ref": "x"}],
        )
        self.assertEqual(proposal.kind, "return_rebind")

    def test_defer_refuses_completion_proof_necessary_summary(self) -> None:
        manifest = self.active()
        interest = {
            "schema": "deferred-interest@1",
            "mission_id": "mission-001",
            "summary": "artifact:validator-pass",
            "criticality": "low",
            "why_not_now": "distraction",
            "suggested_next": None,
            "subject_refs": [],
            "created_at_revision": 2,
            "status": "open",
        }
        with self.assertRaisesRegex(ValueError, "DEFER_CRITICAL_PATH"):
            propose_defer(manifest, interest)

    def test_emit_condition_has_no_capability_id(self) -> None:
        out = emit_unanswered_condition(
            self.active(), "approach uncertain for this claim", frontier_index=0
        )
        self.assertEqual(
            set(out),
            {"condition", "return_point"},
        )
        self.assertNotIn("capability_id", out)
        self.assertEqual(out["return_point"]["frontier_index"], 0)

    def test_replan_requires_contradiction_refs(self) -> None:
        with self.assertRaisesRegex(ValueError, "REPLAN_CONTRADICTION_REQUIRED"):
            propose_replan_slice(
                self.active(),
                new_frontier=["repair live drift"],
                contradiction_refs=[],
            )

    def test_mission_os_source_has_no_inventory_patterns(self) -> None:
        source = (
            Path(__file__).parents[1] / "practical_agency" / "mission_os.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("skills/", source)
        self.assertIsNone(re.search(r"stage[_\s-]*map\s*[:=]", source, re.I))


if __name__ == "__main__":
    unittest.main()
