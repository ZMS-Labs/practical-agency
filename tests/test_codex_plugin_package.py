from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL_NAMES = [
    "manifest_engage",
    "manifest_capability_request",
    "manifest_capability_result",
    "manifest_clarify",
    "manifest_define",
    "manifest_authorize",
    "manifest_dispatch",
    "manifest_verify",
    "manifest_accept",
]


def copy_runtime_plugin(target_root: Path) -> Path:
    installed = target_root / "practical-agency"
    shutil.copytree(
        ROOT,
        installed,
        ignore=shutil.ignore_patterns(
            ".git", "docs", "tests", "missions", "__pycache__", "*.pyc"
        ),
    )
    return installed


def run_mcp_exchange(installed: Path) -> list[dict[str, object]]:
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "package-test", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [sys.executable, "-m", "practical_agency.mcp_server"],
        cwd=installed,
        env=environment,
        input="".join(json.dumps(item) + "\n" for item in messages),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr + completed.stdout)
    return [json.loads(line) for line in completed.stdout.splitlines()]


class CodexPluginPackageTests(unittest.TestCase):
    def test_codex_plugin_metadata_has_relative_runtime_surfaces(self) -> None:
        plugin = json.loads(
            (ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(plugin["name"], "practical-agency")
        self.assertEqual(plugin["skills"], "./skills/")
        self.assertEqual(plugin["mcpServers"], "./.mcp.json")
        self.assertEqual(plugin["hooks"], "./hooks/hooks.json")

        mcp = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
        self.assertEqual(set(mcp["mcpServers"]), {"practical-agency"})
        server = mcp["mcpServers"]["practical-agency"]
        self.assertEqual(server["cwd"], ".")
        self.assertEqual(server["command"], "python")
        self.assertEqual(server["args"], ["-m", "practical_agency.mcp_server"])

        marketplace = json.loads(
            (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(marketplace["name"], "practical-agency-dev")
        self.assertEqual(len(marketplace["plugins"]), 1)
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], "practical-agency")
        self.assertEqual(entry["source"], {"source": "url", "url": "./"})
        self.assertEqual(
            entry["policy"],
            {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        )

        encoded = json.dumps([plugin, mcp, marketplace])
        self.assertNotIn(str(ROOT), encoded)
        self.assertNotIn("Y:\\\\", encoded)

        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(project["project"]["requires-python"], ">=3.11")

    def test_plugin_hooks_use_codex_plugin_root_contract(self) -> None:
        manifest = json.loads(
            (ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8")
        )
        handlers = [
            handler
            for groups in manifest["hooks"].values()
            for group in groups
            for handler in group["hooks"]
        ]
        self.assertTrue(handlers)
        for handler in handlers:
            self.assertIn("${PLUGIN_ROOT}", handler["command"])
            self.assertIn("$env:PLUGIN_ROOT", handler["commandWindows"])
            self.assertNotIn("CODEX_PLUGIN_ROOT", json.dumps(handler))

    def test_copied_plugin_starts_without_source_working_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pa-plugin-") as temp:
            installed = copy_runtime_plugin(Path(temp))

            responses = run_mcp_exchange(installed)

            self.assertEqual(
                responses[0]["result"]["serverInfo"]["name"], "practical-agency"
            )
            self.assertEqual(
                [tool["name"] for tool in responses[1]["result"]["tools"]],
                TOOL_NAMES,
            )

    def test_package_check_proves_real_codex_mcp_exchange(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / ".github" / "scripts" / "check_package.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        self.assertIn("codex_mcp_tools=9", completed.stdout)
        self.assertIn("runtime_manifest=verified", completed.stdout)


if __name__ == "__main__":
    unittest.main()
