from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from practical_agency.host_evidence import (
    HostEvidenceError,
    hook_definition_sha256,
    validate_host_bindings,
    write_host_context,
    write_host_gate,
)


ROOT = Path(__file__).resolve().parents[1]


class HostEvidenceTests(unittest.TestCase):
    def _workspace(self, temp: str) -> Path:
        workspace = Path(temp) / "workspace"
        workspace.mkdir()
        (workspace / ".git").mkdir()
        return workspace

    def test_context_and_gate_bind_exact_host_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            context = write_host_context(
                workspace_root=workspace,
                prompt="$manifest create the approved runbook",
                session_id="session-1",
                turn_id="turn-1",
                plugin_root=ROOT,
            )
            context_path = Path(context.path)
            payload = json.loads(context_path.read_text(encoding="utf-8"))

            self.assertEqual(
                set(payload),
                {
                    "schema",
                    "prompt",
                    "prompt_sha256",
                    "workspace_root",
                    "session_id",
                    "turn_id",
                    "context_nonce",
                    "hook_definition_sha256",
                    "created_at",
                },
            )
            self.assertEqual(payload["schema"], "host-context@1")
            self.assertEqual(payload["prompt"], "$manifest create the approved runbook")
            self.assertEqual(
                payload["prompt_sha256"],
                hashlib.sha256(payload["prompt"].encode("utf-8")).hexdigest(),
            )
            self.assertEqual(len(payload["context_nonce"]), 64)

            gate = write_host_gate(
                context_ref=context.path,
                tool_name="mcp__practical_agency__manifest_engage",
                tool_use_id="tool-use-1",
                session_id="session-1",
                turn_id="turn-1",
                workspace_root=workspace,
                lock_reason="explicit-manifest-intent",
                decision="allow-controller",
                plugin_root=ROOT,
            )
            binding = validate_host_bindings(
                context_ref=context.path,
                gate_ref=gate.path,
                expected_tool_name="mcp__practical_agency__manifest_engage",
                plugin_root=ROOT,
            )

            self.assertEqual(binding.context.prompt, payload["prompt"])
            self.assertEqual(binding.gate.tool_use_id, "tool-use-1")
            self.assertEqual(binding.gate.decision, "allow-controller")
            self.assertEqual(binding.workspace_root, workspace.resolve())

    def test_model_supplied_or_stale_binding_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            context = write_host_context(
                workspace_root=workspace,
                prompt="$manifest do this",
                session_id="session-1",
                turn_id="turn-1",
                plugin_root=ROOT,
            )
            gate = write_host_gate(
                context_ref=context.path,
                tool_name="mcp__practical_agency__manifest_engage",
                tool_use_id="tool-use-1",
                session_id="session-1",
                turn_id="turn-1",
                workspace_root=workspace,
                lock_reason="explicit-manifest-intent",
                decision="allow-controller",
                plugin_root=ROOT,
            )
            gate_payload = json.loads(Path(gate.path).read_text(encoding="utf-8"))
            gate_payload["turn_id"] = "turn-forged"
            Path(gate.path).write_text(
                json.dumps(gate_payload, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(HostEvidenceError, "HOST_GATE_UNAVAILABLE"):
                validate_host_bindings(
                    context_ref=context.path,
                    gate_ref=gate.path,
                    expected_tool_name="mcp__practical_agency__manifest_engage",
                    plugin_root=ROOT,
                )

    def test_hook_definition_hash_covers_imported_runtime_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            plugin = Path(temp) / "plugin"
            shutil.copytree(ROOT / "hooks", plugin / "hooks")
            shutil.copytree(
                ROOT / "practical_agency",
                plugin / "practical_agency",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            before = hook_definition_sha256(plugin)
            dependency = plugin / "practical_agency" / "host_evidence.py"
            dependency.write_bytes(dependency.read_bytes() + b"\n# changed dependency\n")

            self.assertNotEqual(hook_definition_sha256(plugin), before)

    def test_symlinked_control_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._workspace(temp)
            missions = workspace / "missions"
            external = Path(temp) / "external"
            external.mkdir()
            try:
                os.symlink(external, missions, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symlink creation unavailable: {error}")

            with self.assertRaisesRegex(HostEvidenceError, "HOST_CONTEXT_INVALID"):
                write_host_context(
                    workspace_root=workspace,
                    prompt="$manifest do this",
                    session_id="session-1",
                    turn_id="turn-1",
                    plugin_root=ROOT,
                )


if __name__ == "__main__":
    unittest.main()
