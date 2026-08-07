from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
DESCRIPTION_CEILING = 420


class ManifestSkillTests(unittest.TestCase):
    def test_sole_public_skill_is_manifest(self) -> None:
        skill_files = sorted(SKILLS.glob("*/SKILL.md"))
        self.assertEqual([path.parent.name for path in skill_files], ["manifest"])

    def test_skill_body_has_required_semantics(self) -> None:
        text = (SKILLS / "manifest" / "SKILL.md").read_text(encoding="utf-8")
        for required in (
            "name: manifest",
            "operator",
            "mission manifest",
            "never self-certify",
            "capability",
            "checkpoint",
            "helix it",
            "resume",
            "reconcile",
        ):
            self.assertIn(required, text)
        self.assertNotIn(
            "when a mission manifest already governs the task and is current",
            text,
        )

    def test_description_byte_ceiling(self) -> None:
        text = (SKILLS / "manifest" / "SKILL.md").read_text(encoding="utf-8")
        match = re.search(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        self.assertIsNotNone(match)
        front = match.group(1)
        desc_match = re.search(r"^description:\s*(.*)$", front, re.MULTILINE)
        self.assertIsNotNone(desc_match)
        description = desc_match.group(1).strip()
        size = len(description.encode("utf-8"))
        self.assertLessEqual(size, DESCRIPTION_CEILING, msg=f"description is {size} bytes")


if __name__ == "__main__":
    unittest.main()
