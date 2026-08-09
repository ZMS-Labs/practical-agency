from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from practical_agency.install_provenance import (
    InstallProvenanceError,
    build_runtime_manifest,
    compare_runtime_trees,
)


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATHS = (
    ".codex-plugin",
    ".mcp.json",
    ".agents/plugins/marketplace.json",
    "hooks",
    "skills/manifest",
    "practical_agency",
    "contracts",
)


def copy_runtime_plugin(target: Path) -> Path:
    installed = target / "installed"
    installed.mkdir()
    for relative in RUNTIME_PATHS:
        source = ROOT / relative
        destination = installed / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(
                source,
                destination,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        else:
            shutil.copy2(source, destination)
    return installed


class InstallProvenanceTests(unittest.TestCase):
    def test_governed_artifact_bytes_are_checkout_stable_lf(self) -> None:
        relative = "docs/operations/codex-manifest-alpha.md"
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")

        self.assertIn(f"/{relative} text eol=lf", attributes)
        self.assertNotIn(b"\r\n", (ROOT / relative).read_bytes())

    def test_tracked_mission_evidence_bytes_are_checkout_stable_lf(self) -> None:
        completed = subprocess.run(
            ["git", "ls-files", "missions"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        tracked = [ROOT / line for line in completed.stdout.splitlines() if line]
        self.assertTrue(tracked)
        for path in tracked:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertNotIn(b"\r\n", path.read_bytes())

    def test_runtime_text_bytes_are_checkout_stable_lf(self) -> None:
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        for required in (
            "/.agents/plugins/marketplace.json text eol=lf",
            "/.codex-plugin/plugin.json text eol=lf",
            "/.mcp.json text eol=lf",
            "/hooks/** text eol=lf",
            "/skills/manifest/** text eol=lf",
            "/practical_agency/** text eol=lf",
            "/contracts/** text eol=lf",
        ):
            self.assertIn(required, attributes)
        manifest = build_runtime_manifest(ROOT)
        for entry in manifest["files"]:
            path = ROOT / entry["path"]
            if path.suffix in {".json", ".md", ".py"}:
                self.assertNotIn(b"\r\n", path.read_bytes(), entry["path"])

    def test_runtime_manifest_is_explicit_canonical_and_cache_free(self) -> None:
        manifest = build_runtime_manifest(ROOT)

        self.assertEqual(manifest["schema"], "plugin-runtime-manifest@1")
        paths = [entry["path"] for entry in manifest["files"]]
        self.assertEqual(paths, sorted(paths))
        self.assertIn("practical_agency/mcp_server.py", paths)
        self.assertIn("skills/manifest/SKILL.md", paths)
        self.assertNotIn("docs", {Path(path).parts[0] for path in paths})
        self.assertNotIn("tests", {Path(path).parts[0] for path in paths})
        self.assertFalse(any("__pycache__" in path or path.endswith(".pyc") for path in paths))
        for entry in manifest["files"]:
            self.assertEqual(set(entry), {"path", "size", "sha256"})
            self.assertEqual(len(entry["sha256"]), 64)

    def test_source_install_manifest_detects_one_changed_hook_byte(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pa-provenance-") as temp:
            installed = copy_runtime_plugin(Path(temp))
            self.assertEqual(compare_runtime_trees(ROOT, installed)["status"], "match")
            (installed / "hooks" / "manifest_hook.py").write_bytes(b"changed\n")

            with self.assertRaisesRegex(
                InstallProvenanceError, "INSTALL_PROVENANCE_MISMATCH"
            ):
                compare_runtime_trees(ROOT, installed)

    def test_verifier_writes_receipt_only_for_exact_match(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pa-provenance-") as temp:
            target = Path(temp)
            installed = copy_runtime_plugin(target)
            receipt = target / "install-provenance.json"
            command = [
                sys.executable,
                str(ROOT / "scripts" / "verify_codex_install.py"),
                "--source",
                str(ROOT),
                "--installed",
                str(installed),
                "--receipt",
                str(receipt),
            ]

            matched = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(matched.returncode, 0, matched.stderr + matched.stdout)
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "install-provenance@1")
            self.assertEqual(payload["status"], "match")
            self.assertEqual(payload["source_manifest_sha256"], payload["installed_manifest_sha256"])

            receipt.unlink()
            (installed / "skills" / "manifest" / "SKILL.md").write_bytes(b"changed\n")
            mismatched = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertNotEqual(mismatched.returncode, 0)
            self.assertIn("INSTALL_PROVENANCE_MISMATCH", mismatched.stderr)
            self.assertFalse(receipt.exists())


if __name__ == "__main__":
    unittest.main()
