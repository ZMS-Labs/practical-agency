from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from practical_agency.controller import ControllerError, ManifestController
from practical_agency.host_evidence import write_host_context, write_host_gate
from practical_agency.mission_repository import discover_active_mission


ROOT = Path(__file__).resolve().parents[1]


class ManifestControllerEngagementTests(unittest.TestCase):
    def _workspace(self, temp: str) -> Path:
        workspace = Path(temp) / "workspace"
        workspace.mkdir()
        (workspace / ".git").mkdir()
        return workspace

    def _host_refs(
        self,
        workspace: Path,
        operation: str,
        *,
        prompt: str,
        turn: str,
    ) -> dict[str, str]:
        context = write_host_context(
            workspace_root=workspace,
            prompt=prompt,
            session_id="session-1",
            turn_id=turn,
            plugin_root=ROOT,
        )
        gate = write_host_gate(
            context_ref=context.path,
            tool_name=f"mcp__practical_agency__{operation}",
            tool_use_id=f"tool-{turn}-{operation}",
            session_id="session-1",
            turn_id=turn,
            workspace_root=workspace,
            lock_reason="explicit-manifest-intent",
            decision="allow-controller",
            plugin_root=ROOT,
        )
        return {
            "_host_context_ref": context.path,
            "_host_gate_ref": gate.path,
        }

    def _definition(self) -> dict[str, object]:
        return {
            "instruction": "Create the approved runbook exactly.\nKeep this line.",
            "desired_state": "The approved runbook exists with exact bytes.",
            "governed_artifacts": [
                {
                    "path": "docs/operations/codex-manifest-alpha.md",
                    "content": "# Codex manifest alpha\n\nApproved bytes.\n",
                }
            ],
            "permissions": ["repository:write"],
            "protected_state": ["all paths outside the governed artifact"],
            "acceptable_costs": ["one local artifact write"],
            "escalation_required_for": ["any additional path or effect"],
            "stop_conditions": ["operator revokes authority"],
            "completion_acceptor": "acceptor:operator-review",
        }

    def test_engage_without_active_mission_returns_definition_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            controller = ManifestController(plugin_root=ROOT)

            result = controller.manifest_engage(
                **self._host_refs(
                    workspace,
                    "manifest_engage",
                    prompt="$manifest create the approved runbook",
                    turn="turn-1",
                )
            )

            self.assertEqual(result["status"], "MISSION_DEFINITION_REQUIRED")
            self.assertEqual(
                result["required_fields"],
                [
                    "instruction",
                    "desired_state",
                    "governed_artifacts",
                    "permissions",
                    "protected_state",
                    "acceptable_costs",
                    "escalation_required_for",
                    "stop_conditions",
                    "completion_acceptor",
                ],
            )
            self.assertNotIn("mission_path", result)
            self.assertNotIn("workspace_root", result)

    def test_define_preserves_verbatim_instruction_and_returns_approval_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            controller = ManifestController(plugin_root=ROOT)
            definition = self._definition()

            result = controller.manifest_define(
                definition=definition,
                **self._host_refs(
                    workspace,
                    "manifest_define",
                    prompt="$manifest define this mission",
                    turn="turn-define",
                ),
            )

            loaded = discover_active_mission(workspace).manifest
            self.assertEqual(loaded.authority["instruction"], definition["instruction"])
            self.assertEqual(loaded.state["status"], "draft")
            self.assertEqual(loaded.revision, 1)
            self.assertEqual(
                loaded.continuity["governed_workspace"]["paths"],
                ["docs/operations/codex-manifest-alpha.md"],
            )
            self.assertEqual(
                result["approval_phrase"],
                f"approve manifest {result['authority_contract_sha256']}",
            )
            self.assertNotIn("mission_path", result)

    def test_authorize_requires_current_prompt_to_contain_exact_contract_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            controller = ManifestController(plugin_root=ROOT)
            defined = controller.manifest_define(
                definition=self._definition(),
                **self._host_refs(
                    workspace,
                    "manifest_define",
                    prompt="$manifest define this mission",
                    turn="turn-define",
                ),
            )
            contract_hash = str(defined["authority_contract_sha256"])

            with self.assertRaisesRegex(ControllerError, "HOST_CONTEXT_INVALID"):
                controller.manifest_authorize(
                    authority_contract_sha256=contract_hash,
                    **self._host_refs(
                        workspace,
                        "manifest_authorize",
                        prompt="yes",
                        turn="turn-no",
                    ),
                )

            result = controller.manifest_authorize(
                authority_contract_sha256=contract_hash,
                **self._host_refs(
                    workspace,
                    "manifest_authorize",
                    prompt=f"approve manifest {contract_hash}",
                    turn="turn-approve",
                ),
            )

            loaded = discover_active_mission(workspace).manifest
            self.assertEqual(result["mission_status"], "active")
            self.assertEqual(loaded.state["status"], "active")
            self.assertEqual(loaded.revision, 3)
            self.assertEqual(
                loaded.state["current_frontier"],
                ["write approved governed artifact"],
            )
            self.assertEqual(loaded.continuity["prior_checkpoint"], result["checkpoint_ref"])

    def test_new_controller_resumes_active_mission_from_host_evidence_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            first = ManifestController(plugin_root=ROOT)
            defined = first.manifest_define(
                definition=self._definition(),
                **self._host_refs(
                    workspace,
                    "manifest_define",
                    prompt="$manifest define this mission",
                    turn="turn-define",
                ),
            )
            contract_hash = str(defined["authority_contract_sha256"])
            first.manifest_authorize(
                authority_contract_sha256=contract_hash,
                **self._host_refs(
                    workspace,
                    "manifest_authorize",
                    prompt=f"approve manifest {contract_hash}",
                    turn="turn-approve",
                ),
            )

            replacement = ManifestController(plugin_root=ROOT)
            result = replacement.manifest_engage(
                **self._host_refs(
                    workspace,
                    "manifest_engage",
                    prompt="manifest this",
                    turn="turn-resume",
                )
            )

            self.assertEqual(result["mission_status"], "active")
            self.assertEqual(result["revision"], 3)
            self.assertEqual(result["drift_findings"], [])
            self.assertNotEqual(result["process_instance_id"], first.process_instance_id)
            self.assertNotIn("mission_path", result)


if __name__ == "__main__":
    unittest.main()
