from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from practical_agency.capability_discovery import (
    CapabilityDescriptor,
    FileSystemSkillProvider,
    Persistence,
    discover_capabilities,
)


class CapabilityDiscoveryTests(unittest.TestCase):
    def write_skill(self, root: Path, dirname: str, *, name: str = "sample", description: str = "Use for sample work.", extra: str = "") -> Path:
        path = root / dirname / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(
            f"---\nname: {name}\ndescription: {description}\nmetadata:\n  persistence: prompt\n  independence: either\n---\n\n# {name}\n\n{extra}\n",
            encoding="utf-8",
        )
        return path

    def test_discovers_immediate_skill_child(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.write_skill(root, "sample")
            result = FileSystemSkillProvider(root, source_root_ref="skills://fixture").discover()
            self.assertEqual(len(result), 1)
            descriptor = result[0]
            self.assertEqual(descriptor.capability_id, "sample")
            self.assertEqual(descriptor.source_ref, "skills://fixture/sample/SKILL.md")
            self.assertNotIn(str(root), descriptor.source_ref)
            self.assertEqual(descriptor.persistence, Persistence.PROMPT)
            self.assertEqual(descriptor.availability, "available")

    def test_add_and_remove_require_no_inventory_edit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = self.write_skill(root, "one", name="one")
            provider = FileSystemSkillProvider(root)
            self.assertEqual([d.capability_id for d in provider.discover()], ["one"])
            self.write_skill(root, "two", name="two")
            self.assertEqual([d.capability_id for d in provider.discover()], ["one", "two"])
            first.unlink()
            self.assertEqual([d.capability_id for d in provider.discover()], ["two"])

    def test_malformed_frontmatter_is_degraded_not_silent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "bad" / "SKILL.md"
            path.parent.mkdir()
            path.write_text("---\nname: bad\ndescription: [unsupported\n---\n", encoding="utf-8")
            descriptor = FileSystemSkillProvider(root).discover()[0]
            self.assertEqual(descriptor.availability, "degraded")
            self.assertIn("MALFORMED_FRONTMATTER", descriptor.degradation_reason or "")

    def test_blank_description_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_skill(root, "blank", name="blank", description="")
            descriptor = FileSystemSkillProvider(root).discover()[0]
            self.assertEqual(descriptor.availability, "unavailable")
            self.assertEqual(descriptor.degradation_reason, "EMPTY_DESCRIPTION")

    def test_duplicate_ids_become_named_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            self.write_skill(Path(left), "a", name="same")
            self.write_skill(Path(right), "b", name="same")
            descriptors = discover_capabilities(
                [FileSystemSkillProvider(Path(left)), FileSystemSkillProvider(Path(right))]
            )
            self.assertEqual(len(descriptors), 2)
            self.assertTrue(all(d.availability == "unavailable" for d in descriptors))
            self.assertTrue(all(d.degradation_reason == "DUPLICATE_CAPABILITY_ID:same" for d in descriptors))

    def test_source_hash_changes_with_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.write_skill(root, "sample")
            first = FileSystemSkillProvider(root).discover()[0].source_sha256
            path.write_text(path.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
            second = FileSystemSkillProvider(root).discover()[0].source_sha256
            self.assertNotEqual(first, second)

    def test_nested_skill_is_not_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_skill(root / "nested", "deep", name="deep")
            self.assertEqual(FileSystemSkillProvider(root).discover(), [])

    def test_harness_descriptor_can_join_filesystem_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_skill(root, "sample")

            class HarnessProvider:
                def discover(self) -> list[CapabilityDescriptor]:
                    return [
                        CapabilityDescriptor(
                            capability_id="tool:test",
                            kind="tool",
                            source_ref="harness://tool/test",
                            source_sha256="0" * 64,
                            description="A test tool.",
                            input_contract=None,
                            output_contract=None,
                            authority_required=(),
                            persistence=Persistence.SESSION,
                            independence="either",
                            availability="available",
                            degradation_reason=None,
                        )
                    ]

            result = discover_capabilities([FileSystemSkillProvider(root), HarnessProvider()])
            self.assertEqual([d.capability_id for d in result], ["sample", "tool:test"])

    def test_kernel_contains_no_known_skill_inventory(self) -> None:
        root = Path(__file__).parents[1] / "practical_agency"
        forbidden = ("metacognate", "gauntlet", "write-goal", "evidence-locked-uat")
        for path in root.glob("*.py"):
            text = path.read_text(encoding="utf-8").casefold()
            for name in forbidden:
                self.assertNotIn(name, text, f"{path} hard-codes {name}")

    def test_missing_explicit_name_is_degraded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "unnamed" / "SKILL.md"
            path.parent.mkdir()
            path.write_text(
                "---\ndescription: Use for unnamed work.\nmetadata:\n  persistence: prompt\n---\n",
                encoding="utf-8",
            )
            descriptor = FileSystemSkillProvider(root).discover()[0]
            self.assertEqual(descriptor.availability, "degraded")
            self.assertIn("NAME_REQUIRED", descriptor.degradation_reason or "")


if __name__ == "__main__":
    unittest.main()
