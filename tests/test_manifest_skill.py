from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SKILLS = ROOT / "skills"


class ManifestSkillTests(unittest.TestCase):
    def test_exactly_one_public_skill_exists(self) -> None:
        skill_files = sorted(SKILLS.glob("*/SKILL.md"))
        self.assertEqual([path.parent.name for path in skill_files], ["manifest"])

    def test_skill_contains_driver_contract(self) -> None:
        text = (SKILLS / "manifest" / "SKILL.md").read_text(encoding="utf-8")
        required = (
            "name: manifest",
            "operator",
            "mission manifest",
            "never self-certify",
            "capability",
            "checkpoint",
            "helix it",
            "resume",
            "reconcile",
            "independent acceptor",
            "commission-watch",
            "external observer",
        )
        for phrase in required:
            self.assertIn(phrase, text.casefold())
        self.assertNotIn("when a mission manifest already governs the task and is current", text)

    def test_description_is_explicit_and_within_budget(self) -> None:
        text = (SKILLS / "manifest" / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
        self.assertIsNotNone(match)
        frontmatter = match.group(1)
        description = next(
            line.split(":", 1)[1].strip()
            for line in frontmatter.splitlines()
            if line.startswith("description:")
        )
        self.assertLessEqual(len(description.encode("utf-8")), 420)
        for phrase in ("operator", "resumable", "checkpoint", "never self-certify", "routine one-step"):
            self.assertIn(phrase, description.casefold())

    def test_plugin_metadata_points_to_canonical_root_skills(self) -> None:
        root_plugin = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        cursor_plugin = json.loads((ROOT / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8"))
        claude_plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(root_plugin["skills"], "./skills/")
        self.assertEqual(cursor_plugin["skills"], "./skills/")
        self.assertNotIn("skills", claude_plugin)

    def test_no_duplicate_plugin_skill_tree_exists(self) -> None:
        self.assertFalse((ROOT / "plugins").exists())


if __name__ == "__main__":
    unittest.main()
