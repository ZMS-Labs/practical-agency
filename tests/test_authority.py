from __future__ import annotations

import copy
import unittest

from practical_agency.authority import authorize_action
from practical_agency.manifest_model import MissionManifest
from practical_agency.validation import validate_manifest_dict


def _minimal_payload() -> dict:
    return {
        "schema": "mission-manifest@1",
        "mission_id": "mission-001",
        "revision": 1,
        "authority": {
            "operator_ref": "operator:test",
            "instruction": "Create and verify the example artifact.",
            "amendments": [],
            "permissions": ["repository:write"],
            "protected_state": ["unrelated files"],
            "acceptable_costs": ["one feature branch"],
            "escalation_required_for": ["destructive action"],
            "revoked": False,
            "revocation_reason": None,
        },
        "outcome": {
            "desired_state": "The example artifact exists and validates.",
            "completion_proof": ["validator passes"],
            "integrity_guards": ["runtime reads the canonical artifact"],
            "scope_proof": ["diff contains only intended files"],
            "stop_conditions": ["operator revokes authority"],
        },
        "truth": {
            "subject_refs": ["repo:example@rev-1"],
            "verified_facts": [],
            "assumptions": [],
            "contradictions": [],
            "unknowns": [],
        },
        "state": {
            "status": "active",
            "completed_actions": [],
            "current_frontier": ["write example"],
            "blockers": [],
            "next_action": "write example",
        },
        "capabilities": {
            "discovered_at": None,
            "available": [],
            "invoked": [],
            "unavailable": [],
            "degraded": [],
        },
        "continuity": {
            "prior_checkpoint": "checkpoint://mission-001/0001",
            "durable_artifacts": [],
            "decisions": [],
            "external_handoffs": [],
            "watch_commissions": [],
        },
        "integrity": {
            "actor_may_self_accept": False,
            "required_gates": [],
            "unresolved_verdicts": [],
            "completion_acceptor": "acceptor:independent",
        },
    }


class AuthorityTests(unittest.TestCase):
    def test_authorized_action_returns_empty(self) -> None:
        manifest = MissionManifest.from_dict(_minimal_payload())
        refusals = authorize_action(
            manifest,
            capability_id="filesystem.write",
            requested_permissions=["repository:write"],
            requested_effects=["examples/minimal-mission.json"],
            estimated_costs=["one feature branch"],
        )
        self.assertEqual(refusals, [])

    def test_revoked_authority_refuses(self) -> None:
        payload = _minimal_payload()
        payload["authority"]["revoked"] = True
        payload["state"]["status"] = "blocked"
        manifest = MissionManifest.from_dict(payload)
        refusals = authorize_action(
            manifest,
            capability_id="filesystem.write",
            requested_permissions=["repository:write"],
            requested_effects=["examples/out.txt"],
            estimated_costs=["one feature branch"],
        )
        self.assertTrue(any(code.startswith("AUTHORITY_REVOKED") for code in refusals))

    def test_protected_state_violation(self) -> None:
        manifest = MissionManifest.from_dict(_minimal_payload())
        refusals = authorize_action(
            manifest,
            capability_id="filesystem.write",
            requested_permissions=["repository:write"],
            requested_effects=["unrelated files"],
            estimated_costs=["one feature branch"],
        )
        self.assertTrue(any(code.startswith("PROTECTED_STATE_VIOLATION") for code in refusals))

    def test_permission_not_granted(self) -> None:
        manifest = MissionManifest.from_dict(_minimal_payload())
        refusals = authorize_action(
            manifest,
            capability_id="shell.exec",
            requested_permissions=["shell:exec"],
            requested_effects=["tmp/out"],
            estimated_costs=["one feature branch"],
        )
        self.assertTrue(any(code.startswith("PERMISSION_NOT_GRANTED") for code in refusals))

    def test_cost_not_authorized(self) -> None:
        manifest = MissionManifest.from_dict(_minimal_payload())
        refusals = authorize_action(
            manifest,
            capability_id="filesystem.write",
            requested_permissions=["repository:write"],
            requested_effects=["examples/out.txt"],
            estimated_costs=["paid cloud GPU"],
        )
        self.assertTrue(any(code.startswith("COST_NOT_AUTHORIZED") for code in refusals))

    def test_escalation_required(self) -> None:
        manifest = MissionManifest.from_dict(_minimal_payload())
        refusals = authorize_action(
            manifest,
            capability_id="filesystem.write",
            requested_permissions=["repository:write"],
            requested_effects=["destructive action"],
            estimated_costs=["one feature branch"],
        )
        self.assertTrue(any(code.startswith("ESCALATION_REQUIRED") for code in refusals))

    def test_active_payload_validates(self) -> None:
        payload = _minimal_payload()
        # revision 1 active may have prior_checkpoint null per validator
        # but our fixture sets one; ensure valid when status active at rev 1
        payload["continuity"]["prior_checkpoint"] = None
        self.assertEqual(validate_manifest_dict(payload), [])


if __name__ == "__main__":
    unittest.main()
