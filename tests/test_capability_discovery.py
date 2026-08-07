from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from practical_agency import capability_discovery as discovery
from practical_agency.capability_discovery import (
    FileSystemSkillProvider,
    discover_capabilities,
)


class CapabilityDiscoveryTests(unittest.TestCase):
    def _write_skill(self, root: Path, name: str, body: str) -> Path:
        skill_dir = root / name
        skill_dir.mkdir(parents=True)
        path = skill_dir / "SKILL.md"
        path.write_text(body, encoding="utf-8")
        return path

    def test_discovers_skill_from_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_skill(
                root,
                "demo",
                "---\nname: demo\ndescription: Demo skill for discovery.\n---\n\n# demo\n",
            )
            caps = discover_capabilities([root])
            self.assertEqual(len(caps), 1)
            self.assertEqual(caps[0].capability_id, "demo")
            self.assertEqual(caps[0].availability, "available")
            self.assertTrue(caps[0].source_sha256)

    def test_adding_skill_needs_no_source_edit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_skill(
                root,
                "alpha",
                "---\nname: alpha\ndescription: Alpha capability.\n---\n\n# alpha\n",
            )
            first = {cap.capability_id for cap in discover_capabilities([root])}
            self._write_skill(
                root,
                "beta",
                "---\nname: beta\ndescription: Beta capability.\n---\n\n# beta\n",
            )
            second = {cap.capability_id for cap in discover_capabilities([root])}
            self.assertEqual(first, {"alpha"})
            self.assertEqual(second, {"alpha", "beta"})

    def test_removing_skill_removes_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self._write_skill(
                root,
                "ephemeral",
                "---\nname: ephemeral\ndescription: Temporary skill.\n---\n\n# ephemeral\n",
            )
            self.assertEqual(len(discover_capabilities([root])), 1)
            path.unlink()
            path.parent.rmdir()
            self.assertEqual(discover_capabilities([root]), [])

    def test_malformed_frontmatter_is_degraded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_skill(root, "broken", "---\nname: [unterminated\n---\n\n# broken\n")
            caps = discover_capabilities([root])
            self.assertEqual(len(caps), 1)
            self.assertEqual(caps[0].availability, "degraded")
            self.assertIsNotNone(caps[0].degradation_reason)

    def test_blank_description_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_skill(root, "blank", "---\nname: blank\ndescription:   \n---\n\n# blank\n")
            caps = discover_capabilities([root])
            self.assertEqual(caps[0].availability, "unavailable")

    def test_duplicate_ids_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a"
            b = Path(tmp) / "b"
            a.mkdir()
            b.mkdir()
            self._write_skill(
                a,
                "shared",
                "---\nname: shared\ndescription: First copy.\n---\n\n# shared\n",
            )
            self._write_skill(
                b,
                "shared",
                "---\nname: shared\ndescription: Second copy.\n---\n\n# shared\n",
            )
            with self.assertRaisesRegex(ValueError, "CAPABILITY_ID_CONFLICT"):
                discover_capabilities([a, b])

    def test_source_hash_changes_with_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self._write_skill(
                root,
                "hashy",
                "---\nname: hashy\ndescription: Hash probe.\n---\n\n# hashy\nv1\n",
            )
            first = discover_capabilities([root])[0].source_sha256
            path.write_text(
                "---\nname: hashy\ndescription: Hash probe.\n---\n\n# hashy\nv2\n",
                encoding="utf-8",
            )
            second = discover_capabilities([root])[0].source_sha256
            self.assertNotEqual(first, second)

    def test_no_hardcoded_skill_inventory_in_package(self) -> None:
        package_root = Path(discovery.__file__).resolve().parent
        banned = ("metacognate", "gauntlet", "decision-ledger", "evidence-locked-uat")
        for path in package_root.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            for name in banned:
                self.assertNotIn(name, text, msg=f"{path} contains hardcoded skill {name}")


if __name__ == "__main__":
    unittest.main()
