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

    def _authorized(
        self, workspace: Path
    ) -> tuple[ManifestController, dict[str, object]]:
        controller = ManifestController(plugin_root=ROOT)
        definition = self._definition()
        defined = controller.manifest_define(
            definition=definition,
            **self._host_refs(
                workspace,
                "manifest_define",
                prompt="$manifest define this mission",
                turn="setup-define",
            ),
        )
        contract_hash = str(defined["authority_contract_sha256"])
        controller.manifest_authorize(
            authority_contract_sha256=contract_hash,
            **self._host_refs(
                workspace,
                "manifest_authorize",
                prompt=f"approve manifest {contract_hash}",
                turn="setup-authorize",
            ),
        )
        return controller, definition

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

    def test_dispatch_uses_durable_intended_bytes_and_current_host_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            controller, definition = self._authorized(workspace)

            result = controller.manifest_dispatch(
                **self._host_refs(
                    workspace,
                    "manifest_dispatch",
                    prompt="continue the manifest mission",
                    turn="turn-dispatch",
                )
            )

            artifact = definition["governed_artifacts"][0]
            target = workspace / str(artifact["path"])
            self.assertEqual(target.read_text(encoding="utf-8"), artifact["content"])
            self.assertEqual(result["effect"]["adapter_ref"], "filesystem-artifact@1")
            self.assertTrue(Path(result["effect"]["external_receipt_ref"]).is_file())
            self.assertEqual(
                result["authority_scope"]["permissions"],
                ["repository:write"],
            )
            self.assertEqual(
                result["frontier"],
                ["write approved governed artifact"],
            )
            latest = discover_active_mission(workspace).manifest
            self.assertEqual(latest.continuity["verifier_results"][-1]["status"], "verified")

    def test_dispatch_without_current_gate_fails_before_effect(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            controller, definition = self._authorized(workspace)
            refs = self._host_refs(
                workspace,
                "manifest_dispatch",
                prompt="continue the manifest mission",
                turn="turn-missing-gate",
            )

            with self.assertRaisesRegex(ControllerError, "HOST_GATE_UNAVAILABLE"):
                controller.manifest_dispatch(
                    _host_context_ref=refs["_host_context_ref"]
                )

            artifact = definition["governed_artifacts"][0]
            self.assertFalse((workspace / str(artifact["path"])).exists())

    def test_verify_detects_planted_drift_then_dispatch_repairs_durable_intent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            controller, definition = self._authorized(workspace)
            controller.manifest_dispatch(
                **self._host_refs(
                    workspace,
                    "manifest_dispatch",
                    prompt="continue the manifest mission",
                    turn="turn-dispatch",
                )
            )
            artifact = definition["governed_artifacts"][0]
            target = workspace / str(artifact["path"])
            target.write_bytes(b"planted drift\n")

            contradicted = controller.manifest_verify(
                **self._host_refs(
                    workspace,
                    "manifest_verify",
                    prompt="verify the manifest mission",
                    turn="turn-drift",
                )
            )

            self.assertIn(
                contradicted["reason_code"],
                {"UNRECEIPTED_WORKSPACE_DRIFT", "ARTIFACT_HASH_MISMATCH"},
            )
            self.assertEqual(contradicted["mission_status"], "active")
            self.assertIn("repair live state", contradicted["next_action"])

            repaired = controller.manifest_dispatch(
                **self._host_refs(
                    workspace,
                    "manifest_dispatch",
                    prompt="repair the manifest mission",
                    turn="turn-repair",
                )
            )
            self.assertEqual(target.read_text(encoding="utf-8"), artifact["content"])
            self.assertEqual(repaired["observation"]["status"], "verified")

            verified = controller.manifest_verify(
                **self._host_refs(
                    workspace,
                    "manifest_verify",
                    prompt="verify the repaired manifest mission",
                    turn="turn-verified",
                )
            )
            self.assertEqual(verified["mission_status"], "verifying")

    def test_replacement_engage_checkpoints_receipt_contradiction_for_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            controller, definition = self._authorized(workspace)
            controller.manifest_dispatch(
                **self._host_refs(
                    workspace,
                    "manifest_dispatch",
                    prompt="continue the manifest mission",
                    turn="turn-dispatch",
                )
            )
            before = discover_active_mission(workspace).manifest.revision
            artifact = definition["governed_artifacts"][0]
            (workspace / str(artifact["path"])).write_bytes(b"planted drift\n")

            replacement = ManifestController(plugin_root=ROOT)
            result = replacement.manifest_engage(
                **self._host_refs(
                    workspace,
                    "manifest_engage",
                    prompt="manifest this",
                    turn="turn-resume-drift",
                )
            )

            latest = discover_active_mission(workspace).manifest
            self.assertGreater(latest.revision, before)
            self.assertEqual(result["mission_status"], "active")
            self.assertEqual(result["reason_code"], "ARTIFACT_HASH_MISMATCH")
            self.assertIn("repair live state", result["next_action"])

    def test_generic_verifier_profile_is_refused_without_revision_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            controller, _ = self._authorized(workspace)
            before = discover_active_mission(workspace).manifest.revision

            with self.assertRaisesRegex(
                ControllerError, "SANDBOXED_VERIFIER_UNAVAILABLE"
            ):
                controller.manifest_verify(
                    profile="python-tests",
                    **self._host_refs(
                        workspace,
                        "manifest_verify",
                        prompt="run tests",
                        turn="turn-generic-verify",
                    ),
                )

            self.assertEqual(discover_active_mission(workspace).manifest.revision, before)

    def test_steward_acceptance_fails_and_declared_role_acceptance_is_honest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            controller, _ = self._authorized(workspace)
            controller.manifest_dispatch(
                **self._host_refs(
                    workspace,
                    "manifest_dispatch",
                    prompt="continue the manifest mission",
                    turn="turn-dispatch",
                )
            )
            controller.manifest_verify(
                **self._host_refs(
                    workspace,
                    "manifest_verify",
                    prompt="verify the manifest mission",
                    turn="turn-verify",
                )
            )

            with self.assertRaisesRegex(
                ControllerError, "INDEPENDENT_ACCEPTANCE_REQUIRED"
            ):
                controller.manifest_accept(
                    acceptor_ref="mission-steward",
                    verdict="PASS",
                    separation_assurance="declared-role-separation",
                    **self._host_refs(
                        workspace,
                        "manifest_accept",
                        prompt="accept the manifest mission",
                        turn="turn-self-accept",
                    ),
                )

            accepted = controller.manifest_accept(
                acceptor_ref="acceptor:operator-review",
                verdict="PASS",
                separation_assurance="declared-role-separation",
                **self._host_refs(
                    workspace,
                    "manifest_accept",
                    prompt="accept the manifest mission",
                    turn="turn-accept",
                ),
            )
            self.assertEqual(accepted["mission_status"], "completed")
            self.assertIn(
                "principal separation is not externally proven",
                accepted["coverage_limits"],
            )


if __name__ == "__main__":
    unittest.main()
