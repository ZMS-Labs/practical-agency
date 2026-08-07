from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from practical_agency.capability_discovery import FileSystemSkillProvider, Persistence, discover_capabilities


def write_skill(root: Path, name: str, description: str, body: str = "Body") -> Path:
    path = root / name
    path.mkdir(parents=True, exist_ok=True)
    skill = path / "SKILL.md"
    skill.write_text(
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        "metadata:\n"
        "  persistence: session\n"
        "  independence: actor\n"
        "  authority_required: [repository:read]\n"
        "---\n\n"
        f"# {name}\n\n{body}\n",
        encoding="utf-8",
    )
    return skill


class CapabilityDiscoveryTests(unittest.TestCase):
    def test_skill_is_discovered_from_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_skill(root, "alpha", "Use for alpha.")
            found = FileSystemSkillProvider(root).discover()
            self.assertEqual([item.capability_id for item in found], ["alpha"])
            self.assertEqual(found[0].persistence, Persistence.SESSION)
            self.assertEqual(found[0].authority_required, ("repository:read",))

    def test_add_and_remove_require_no_inventory_edit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = write_skill(root, "alpha", "Use for alpha.")
            provider = FileSystemSkillProvider(root)
            self.assertEqual(len(provider.discover()), 1)
            write_skill(root, "beta", "Use for beta.")
            self.assertEqual([x.capability_id for x in provider.discover()], ["alpha", "beta"])
            first.unlink()
            self.assertEqual([x.capability_id for x in provider.discover()], ["beta"])

    def test_malformed_frontmatter_is_degraded_not_silent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "broken"
            path.mkdir()
            path.joinpath("SKILL.md").write_text("---\nname: broken\n", encoding="utf-8")
            item = FileSystemSkillProvider(root).discover()[0]
            self.assertEqual(item.availability, "degraded")
            self.assertIn("MALFORMED_FRONTMATTER", item.degradation_reason or "")

    def test_blank_description_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_skill(root, "blank", '""')
            item = FileSystemSkillProvider(root).discover()[0]
            self.assertEqual(item.availability, "unavailable")
            self.assertEqual(item.degradation_reason, "EMPTY_DESCRIPTION")

    def test_duplicate_ids_become_named_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            write_skill(Path(one), "same", "Use one.")
            write_skill(Path(two), "same", "Use two.")
            found = discover_capabilities([FileSystemSkillProvider(Path(one)), FileSystemSkillProvider(Path(two))])
            self.assertEqual(len(found), 2)
            self.assertTrue(all(x.availability == "unavailable" for x in found))
            self.assertTrue(all(x.degradation_reason == "DUPLICATE_CAPABILITY_ID" for x in found))

    def test_source_hash_changes_with_body(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            skill = write_skill(root, "alpha", "Use for alpha.", "one")
            first = FileSystemSkillProvider(root).discover()[0].source_sha256
            skill.write_text(skill.read_text(encoding="utf-8") + "two\n", encoding="utf-8")
            second = FileSystemSkillProvider(root).discover()[0].source_sha256
            self.assertNotEqual(first, second)

    def test_production_code_contains_no_known_member_inventory(self) -> None:
        production = Path(__file__).parents[1] / "practical_agency"
        joined = "\n".join(path.read_text(encoding="utf-8") for path in production.glob("*.py"))
        for forbidden in ("gauntlet", "metacognate", "write-goal"):
            self.assertNotIn(forbidden, joined.lower())


if __name__ == "__main__":
    unittest.main()
