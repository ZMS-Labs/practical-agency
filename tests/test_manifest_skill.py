from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SKILLS = ROOT / "skills"


class ManifestSkillTests(unittest.TestCase):
    def test_manifest_is_the_only_public_skill(self) -> None:
        skill_files = sorted(SKILLS.glob("*/SKILL.md"))
        self.assertEqual([path.parent.name for path in skill_files], ["manifest"])

    def test_manifest_contains_required_mission_driver_semantics(self) -> None:
        text = (SKILLS / "manifest" / "SKILL.md").read_text(encoding="utf-8")
        for required in (
            "name: manifest",
            "operator",
            "mission manifest",
            "never self-certify",
            "capability",
            "checkpoint",
            "helix it",
            "commission-watch",
            "independent",
        ):
            self.assertIn(required, text)

    def test_description_stays_within_recorded_v01_budget(self) -> None:
        text = (SKILLS / "manifest" / "SKILL.md").read_text(encoding="utf-8")
        match = re.search(r"\A---\n(.*?)\n---\n", text, re.S)
        self.assertIsNotNone(match)
        description_line = next(
            line for line in (match.group(1).splitlines() if match else []) if line.startswith("description:")
        )
        description = description_line.split(":", 1)[1].strip().strip('"')
        self.assertLessEqual(len(description.encode("utf-8")), 420)
        self.assertIn("Do NOT use", description)

    def test_plugin_metadata_points_to_canonical_skill_root(self) -> None:
        cursor = json.loads((ROOT / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(cursor["skills"], "./skills/")
        generic = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(generic["skills"], "./skills/")


if __name__ == "__main__":
    unittest.main()
