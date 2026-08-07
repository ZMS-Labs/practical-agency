from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class RepositoryContractTests(unittest.TestCase):
    def test_required_repository_surfaces_exist(self) -> None:
        required = (
            "README.md",
            "AGENTS.md",
            "pyproject.toml",
            "roles/mission-steward.md",
            "roles/independent-acceptor.md",
            "contracts/mission-event.schema.json",
            "contracts/execution-request.schema.json",
            ".github/scripts/check_repo.py",
            ".github/scripts/check_dco.py",
            ".github/workflows/ci.yml",
            "docs/release/RELEASE-0.1.0.md",
        )
        for relative in required:
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_every_json_file_parses(self) -> None:
        for path in sorted(ROOT.rglob("*.json")):
            with self.subTest(path=path.relative_to(ROOT)):
                json.loads(path.read_text(encoding="utf-8"))

    def test_readme_is_honest_about_runtime_boundary(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8").casefold()
        for phrase in (
            "sole public entry skill",
            "no background service",
            "no production execution adapter",
            "independent acceptance",
            "commission-watch",
            "unverified_external_contract",
            "comparative benefit",
        ):
            self.assertIn(phrase, text)

    def test_roles_keep_actor_and_acceptor_separate(self) -> None:
        steward = (ROOT / "roles/mission-steward.md").read_text(encoding="utf-8").casefold()
        acceptor = (ROOT / "roles/independent-acceptor.md").read_text(encoding="utf-8").casefold()
        for phrase in ("preserve authority", "re-anchor", "one bounded next action", "never self-accept"):
            self.assertIn(phrase, steward)
        for phrase in ("did not perform", "pass", "fail", "inconclusive", "cannot dispatch fixes"):
            self.assertIn(phrase, acceptor)

    def test_watch_example_labels_unverified_external_contract(self) -> None:
        payload = json.loads((ROOT / "examples/watch-commission-mission.json").read_text(encoding="utf-8"))
        entry = payload["continuity"]["watch_commissions"][0]
        self.assertEqual(entry["external_contract_status"], "UNVERIFIED_EXTERNAL_CONTRACT")
        self.assertEqual(entry["record"]["state"], "BLOCKED")

    def test_repository_check_and_its_self_test_pass(self) -> None:
        for args in (("--self-test",), ()):
            completed = subprocess.run(
                [sys.executable, str(ROOT / ".github/scripts/check_repo.py"), *args],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_dco_checker_self_test_passes(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / ".github/scripts/check_dco.py"), "--self-test"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_ci_checks_committed_diff_not_only_worktree(self) -> None:
        text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn('git diff --check "$BASE_SHA...$HEAD_SHA"', text)
        self.assertIn('git show --check --format= "$HEAD_SHA"', text)


if __name__ == "__main__":
    unittest.main()
