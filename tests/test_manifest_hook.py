from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "manifest_hook.py"


class ManifestHookTests(unittest.TestCase):
    def _workspace(self, temp: str) -> Path:
        workspace = Path(temp) / "workspace"
        workspace.mkdir()
        (workspace / ".git").mkdir()
        return workspace

    def _run_hook(self, event: dict[str, object]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(event),
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )

    def _submit(self, workspace: Path, prompt: str = "$manifest do this") -> None:
        completed = self._run_hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(workspace),
                "session_id": "session-1",
                "turn_id": "turn-1",
                "prompt": prompt,
            }
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_user_prompt_hook_writes_context_without_exposing_nonce(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            prompt = "$manifest create the approved runbook"
            completed = self._run_hook(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "cwd": str(workspace),
                    "session_id": "session-1",
                    "turn_id": "turn-1",
                    "prompt": prompt,
                }
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(completed.stdout)
            context = list(
                (workspace / "missions" / ".host-context").rglob("*.json")
            )
            self.assertEqual(len(context), 1)
            payload = json.loads(context[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["prompt"], prompt)
            self.assertNotIn(payload["context_nonce"], completed.stdout)
            self.assertEqual(
                output["hookSpecificOutput"]["hookEventName"],
                "UserPromptSubmit",
            )
            self.assertIn(
                "host context is available",
                output["hookSpecificOutput"]["additionalContext"],
            )

    def test_pre_tool_hook_overwrites_reserved_refs_for_controller(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            self._submit(workspace)
            completed = self._run_hook(
                {
                    "hook_event_name": "PreToolUse",
                    "cwd": str(workspace),
                    "session_id": "session-1",
                    "turn_id": "turn-1",
                    "tool_name": "mcp__practical_agency__manifest_engage",
                    "tool_use_id": "tool-use-1",
                    "tool_input": {
                        "_host_context_ref": "forged-context",
                        "_host_gate_ref": "forged-gate",
                    },
                }
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(completed.stdout)["hookSpecificOutput"]
            self.assertEqual(output["permissionDecision"], "allow")
            updated = output["updatedInput"]
            self.assertNotEqual(updated["_host_context_ref"], "forged-context")
            self.assertNotEqual(updated["_host_gate_ref"], "forged-gate")
            self.assertTrue(Path(updated["_host_context_ref"]).is_file())
            self.assertTrue(Path(updated["_host_gate_ref"]).is_file())

    def test_locked_engagement_denies_competing_local_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            self._submit(workspace)
            for tool_name in (
                "shell_command",
                "apply_patch",
                "mcp__github__create_or_update_file",
                "some_other_local_function",
            ):
                with self.subTest(tool_name=tool_name):
                    completed = self._run_hook(
                        {
                            "hook_event_name": "PreToolUse",
                            "cwd": str(workspace),
                            "session_id": "session-1",
                            "turn_id": "turn-1",
                            "tool_name": tool_name,
                            "tool_use_id": f"tool-use-{tool_name}",
                            "tool_input": {"secret": "must-not-be-recorded"},
                        }
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    output = json.loads(completed.stdout)["hookSpecificOutput"]
                    self.assertEqual(output["permissionDecision"], "deny")
                    self.assertNotIn("must-not-be-recorded", completed.stdout)

    def test_unlocked_turn_does_not_deny_ordinary_tool(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            self._submit(workspace, prompt="Explain this one-line function")
            completed = self._run_hook(
                {
                    "hook_event_name": "PreToolUse",
                    "cwd": str(workspace),
                    "session_id": "session-1",
                    "turn_id": "turn-1",
                    "tool_name": "shell_command",
                    "tool_use_id": "tool-use-ordinary",
                    "tool_input": {"command": "git status"},
                }
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(completed.stdout)["hookSpecificOutput"]
            self.assertEqual(output["permissionDecision"], "allow")


if __name__ == "__main__":
    unittest.main()
