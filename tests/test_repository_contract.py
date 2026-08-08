from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class RepositoryContractTests(unittest.TestCase):
    def test_required_contracts_are_strict_json_schemas(self) -> None:
        required = {
            "mission-manifest.schema.json",
            "mission-event.schema.json",
            "checkpoint.schema.json",
            "execution-request.schema.json",
            "execution-receipt.schema.json",
            "capability-request.schema.json",
            "capability-result.schema.json",
        }
        self.assertEqual({path.name for path in (ROOT / "contracts").glob("*.json")}, required)
        for path in sorted((ROOT / "contracts").glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertFalse(payload.get("additionalProperties", True), path.name)

    def test_project_metadata_and_docs_exist(self) -> None:
        for relative in (
            "pyproject.toml",
            "AGENTS.md",
            "README.md",
            "LICENSE",
            "roles/mission-steward.md",
            "roles/independent-acceptor.md",
            "adapters/README.md",
            "docs/mission-manifest.md",
            "docs/release/RELEASE-0.1.0.md",
            "examples/watch-commission-mission.json",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_readme_has_exact_first_screen_and_honest_limits(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        expected = (
            "# Practical Agency\n\n"
            "Practical Agency is human-authorized mission control for carrying intent through\n"
            "durable, coordinated, resumable action.\n\n"
            "Its sole public entry skill is `manifest`.\n\n"
            "Practical Agency does not give an artificial agent independent ends. It extends\n"
            "the operator's agency through bounded delegation: the operator owns the purpose,\n"
            "authority, protected state, acceptable costs, and right to interrupt; the system\n"
            "preserves those constraints while coordinating workflow, epistemic discipline,\n"
            "execution substrates, continuity, and independent proof.\n"
        )
        self.assertTrue(text.startswith(expected))
        for phrase in (
            "not a daemon",
            "no production external execution adapter",
            "Cursor/Generic Agent Skills install inventory is LIVE",
            "Customize→Skills panel and Claude live load remain unverified",
            "comparative benefit",
        ):
            self.assertIn(phrase, text)

    def test_ci_declares_full_stdlib_gate_and_dco(self) -> None:
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        for required in (
            'python-version: "3.12"',
            "unittest discover",
            "compileall",
            "check_contracts.py",
            "check_package.py",
            "check_public_content.py",
        ):
            self.assertIn(required, ci)
        dco = (ROOT / ".github/workflows/dco.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request_target", dco)
        self.assertIn("check_dco.py", dco)

    def test_repository_checkers_pass(self) -> None:
        for script in ("check_contracts.py", "check_package.py", "check_public_content.py"):
            completed = subprocess.run(
                [sys.executable, str(ROOT / ".github/scripts" / script)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
