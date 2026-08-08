"""Harness packaging surfaces must be checkable and materializable outside the tree."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTMATTER = re.compile(r"\A---\r?\n(?P<body>.*?)\r?\n---(?:\r?\n|\Z)", re.S)


def _description(skill_text: str) -> str:
    match = FRONTMATTER.match(skill_text)
    assert match is not None
    desc_match = re.search(r"(?m)^description:\s*(.*?)\s*$", match.group("body"))
    assert desc_match is not None
    return desc_match.group(1)


class HarnessSurfaceTests(unittest.TestCase):
    def test_harness_matrix_document_exists_with_required_rows(self) -> None:
        path = ROOT / "docs" / "release" / "HARNESS-VERIFICATION-MATRIX-0.1.0.md"
        self.assertTrue(path.is_file(), "missing harness verification matrix")
        text = path.read_text(encoding="utf-8")
        for required in (
            "Cursor",
            "Generic Agent Skills",
            "Claude",
            "LIVE",
            "DETERMINISTIC",
            "LIVE_BLOCKED_EXTERNAL",
            "STRUCTURAL",
        ):
            self.assertIn(required, text)

    def test_check_harness_surfaces_script_materializes_exact_skill(self) -> None:
        script = ROOT / ".github" / "scripts" / "check_harness_surfaces.py"
        self.assertTrue(script.is_file(), "missing check_harness_surfaces.py")
        with tempfile.TemporaryDirectory(prefix="pa-harness-") as temp:
            target = Path(temp)
            completed = subprocess.run(
                [sys.executable, str(script), "--materialize", str(target)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            installed = target / ".agents" / "skills" / "manifest" / "SKILL.md"
            self.assertTrue(installed.is_file(), installed)
            source = (ROOT / "skills" / "manifest" / "SKILL.md").read_text(encoding="utf-8")
            loaded = installed.read_text(encoding="utf-8")
            self.assertEqual(loaded, source)
            description = _description(loaded)
            self.assertIn("manifest this", description)
            self.assertIn("helix it", description)
            self.assertIn("Do NOT use", description)
            report = json.loads((target / "harness-materialize-receipt.json").read_text())
            self.assertEqual(report["loaded_skill_count"], 1)
            self.assertEqual(report["loaded_skill_name"], "manifest")
            self.assertEqual(report["description_exact"], True)

    def test_ci_runs_harness_surface_check(self) -> None:
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("check_harness_surfaces.py", ci)


if __name__ == "__main__":
    unittest.main()
