#!/usr/bin/env python3
"""Fail-closed repository and packaging invariants for Practical Agency."""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from practical_agency.capability_discovery import FileSystemSkillProvider, parse_frontmatter  # noqa: E402
from practical_agency import __version__  # noqa: E402
from practical_agency.manifest_model import MissionManifest  # noqa: E402

VERSION = "0.1.0"
DESCRIPTION_BUDGET = 420
REQUIRED_FILES = (
    "README.md",
    "AGENTS.md",
    "LICENSE",
    "pyproject.toml",
    "plugin.json",
    ".cursor-plugin/plugin.json",
    ".claude-plugin/plugin.json",
    "skills/manifest/SKILL.md",
    "roles/mission-steward.md",
    "roles/independent-acceptor.md",
    "contracts/mission-manifest.schema.json",
    "contracts/mission-event.schema.json",
    "contracts/capability-request.schema.json",
    "contracts/capability-result.schema.json",
    "contracts/execution-request.schema.json",
    "contracts/execution-receipt.schema.json",
    "contracts/checkpoint.schema.json",
    "examples/minimal-mission.json",
    "examples/watch-commission-mission.json",
    "docs/mission-manifest.md",
    "docs/release/RELEASE-0.1.0.md",
    ".github/scripts/check_dco.py",
    ".github/workflows/ci.yml",
)
FORBIDDEN_PATTERNS = (
    ("PRIVATE_KEY", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    ("GITHUB_TOKEN", re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b")),
    ("API_KEY", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("POSIX_HOME_PATH", re.compile(r"(?<![A-Za-z0-9])/(?:home|Users)/[A-Za-z0-9._-]+/")),
    ("WINDOWS_USER_PATH", re.compile(r"[A-Za-z]:\\\\Users\\\\[^\\\s]+\\\\")),
)
TEXT_SUFFIXES = {".md", ".py", ".json", ".toml", ".yml", ".yaml", ".txt"}


def _load_json(path: Path, errors: list[str]) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        errors.append(f"INVALID_JSON:{path.relative_to(ROOT)}:{error}")
        return None


def _forbidden_text_errors(label: str, text: str) -> list[str]:
    errors: list[str] = []
    for code, pattern in FORBIDDEN_PATTERNS:
        if pattern.search(text):
            errors.append(f"{code}:{label}")
    return errors


def _is_generated_path(path: Path) -> bool:
    return any(
        part in {".git", "__pycache__", ".pytest_cache", "build", "dist"}
        or part.endswith(".egg-info")
        for part in path.parts
    )


def _iter_public_text_files() -> Iterable[Path]:
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        if _is_generated_path(path):
            continue
        if path == Path(__file__).resolve():
            continue
        yield path


def _description_errors(description: str) -> list[str]:
    errors: list[str] = []
    size = len(description.encode("utf-8"))
    if size > DESCRIPTION_BUDGET:
        errors.append(f"DESCRIPTION_BUDGET_EXCEEDED:{size}>{DESCRIPTION_BUDGET}")
    lowered = description.casefold()
    for phrase in ("operator", "resumable", "checkpoint", "never self-certify", "routine one-step"):
        if phrase not in lowered:
            errors.append(f"DESCRIPTION_TRIGGER_MISSING:{phrase}")
    return errors


def check_repository() -> list[str]:
    errors: list[str] = []

    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            errors.append(f"REQUIRED_FILE_MISSING:{relative}")

    if (ROOT / "plugins").exists():
        errors.append("DUPLICATE_SKILL_TREE_FORBIDDEN:plugins")

    skill_files = sorted((ROOT / "skills").glob("*/SKILL.md"))
    expected_skill = ROOT / "skills/manifest/SKILL.md"
    if skill_files != [expected_skill]:
        rendered = ",".join(str(path.relative_to(ROOT)) for path in skill_files)
        errors.append(f"PUBLIC_SKILL_INVENTORY_MISMATCH:{rendered}")
    elif expected_skill.is_file():
        try:
            top, _metadata = parse_frontmatter(expected_skill.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as error:
            errors.append(f"INVALID_MANIFEST_SKILL_FRONTMATTER:{error}")
        else:
            if top.get("name") != "manifest":
                errors.append("MANIFEST_SKILL_NAME_MISMATCH")
            errors.extend(_description_errors(top.get("description", "")))
            skill_text = expected_skill.read_text(encoding="utf-8").casefold()
            if "operator revocation" not in skill_text:
                errors.append("MANIFEST_REVOCATION_BOUNDARY_MISSING")
        descriptors = FileSystemSkillProvider(ROOT / "skills").discover()
        if len(descriptors) != 1 or descriptors[0].availability != "available":
            errors.append("MANIFEST_SKILL_NOT_DISCOVERABLE")

    json_payloads: dict[str, object] = {}
    for path in sorted(ROOT.rglob("*.json")):
        if _is_generated_path(path):
            continue
        payload = _load_json(path, errors)
        if payload is not None:
            json_payloads[str(path.relative_to(ROOT))] = payload

    root_plugin = json_payloads.get("plugin.json")
    cursor_plugin = json_payloads.get(".cursor-plugin/plugin.json")
    claude_plugin = json_payloads.get(".claude-plugin/plugin.json")
    if not isinstance(root_plugin, dict) or root_plugin.get("skills") != "./skills/":
        errors.append("ROOT_PLUGIN_SKILL_PATH_MISMATCH")
    if not isinstance(cursor_plugin, dict) or cursor_plugin.get("skills") != "./skills/":
        errors.append("CURSOR_PLUGIN_SKILL_PATH_MISMATCH")
    if isinstance(claude_plugin, dict) and "skills" in claude_plugin:
        errors.append("CLAUDE_PLUGIN_CUSTOM_SKILL_PATH_FORBIDDEN")
    for label, payload in (
        ("root", root_plugin),
        ("cursor", cursor_plugin),
        ("claude", claude_plugin),
    ):
        if not isinstance(payload, dict) or payload.get("name") != "practical-agency":
            errors.append(f"PLUGIN_IDENTITY_MISMATCH:{label}")
        if isinstance(payload, dict) and payload.get("version") != VERSION:
            errors.append(f"PLUGIN_VERSION_MISMATCH:{label}")

    try:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        errors.append(f"INVALID_PYPROJECT:{error}")
    else:
        project = pyproject.get("project", {})
        if project.get("name") != "zms-practical-agency":
            errors.append("DISTRIBUTION_NAME_MISMATCH")
        if project.get("version") != VERSION:
            errors.append("PYPROJECT_VERSION_MISMATCH")
        if project.get("requires-python") != ">=3.12":
            errors.append("PYTHON_FLOOR_MISMATCH")
        if project.get("dependencies") != []:
            errors.append("RUNTIME_DEPENDENCIES_FORBIDDEN")
        if project.get("license") != "GPL-3.0-or-later":
            errors.append("LICENSE_EXPRESSION_MISMATCH")
    if __version__ != VERSION:
        errors.append("PACKAGE_VERSION_MISMATCH")

    for example in ("examples/minimal-mission.json", "examples/watch-commission-mission.json"):
        payload = json_payloads.get(example)
        if isinstance(payload, dict):
            try:
                MissionManifest.from_dict(payload)
            except ValueError as error:
                errors.append(f"INVALID_MISSION_EXAMPLE:{example}:{error}")

    watch_example = json_payloads.get("examples/watch-commission-mission.json")
    if isinstance(watch_example, dict):
        try:
            entry = watch_example["continuity"]["watch_commissions"][0]
            if entry["external_contract_status"] != "UNVERIFIED_EXTERNAL_CONTRACT":
                raise KeyError("wrong status")
            if entry["record"]["state"] != "BLOCKED":
                raise KeyError("wrong upstream state")
        except (KeyError, IndexError, TypeError):
            errors.append("WATCH_EXAMPLE_EXTERNAL_STATUS_MISSING")

    readme = (ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").is_file() else ""
    for phrase in (
        "sole public entry skill",
        "no background service",
        "no production execution adapter",
        "independent acceptance",
        "commission-watch",
        "UNVERIFIED_EXTERNAL_CONTRACT",
        "comparative benefit",
    ):
        if phrase.casefold() not in readme.casefold():
            errors.append(f"README_BOUNDARY_MISSING:{phrase}")

    for path in _iter_public_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            errors.append(f"UNREADABLE_PUBLIC_TEXT:{path.relative_to(ROOT)}:{error}")
            continue
        errors.extend(_forbidden_text_errors(str(path.relative_to(ROOT)), text))

    return errors


def self_test() -> list[str]:
    failures: list[str] = []
    planted = "credential=ghp_" + "A" * 32 + "\npath=/home/example/private/file\n"
    detected = _forbidden_text_errors("planted", planted)
    if not any(item.startswith("GITHUB_TOKEN:") for item in detected):
        failures.append("SELF_TEST_TOKEN_NOT_DETECTED")
    if not any(item.startswith("POSIX_HOME_PATH:") for item in detected):
        failures.append("SELF_TEST_HOME_PATH_NOT_DETECTED")
    if _forbidden_text_errors("clean", "generic public documentation"):
        failures.append("SELF_TEST_CLEAN_TEXT_REJECTED")
    if not any(item.startswith("DESCRIPTION_BUDGET_EXCEEDED") for item in _description_errors("x" * 421)):
        failures.append("SELF_TEST_DESCRIPTION_BUDGET_NOT_DETECTED")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    errors = self_test() if args.self_test else check_repository()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("repository self-test ok" if args.self_test else "repository contract ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
