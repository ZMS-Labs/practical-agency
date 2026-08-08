#!/usr/bin/env python3
"""Check packaged harness surfaces and materialize a generic Agent Skills layout.

Materialization always writes outside claims about Cursor/Claude live skill-panel
inventory. It proves the installable skill bytes are exact and discoverable as a
one-skill Agent Skills tree.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTMATTER = re.compile(r"\A---\r?\n(?P<body>.*?)\r?\n---(?:\r?\n|\Z)", re.S)
PLUGIN_RELATIVE = (
    "plugin.json",
    ".cursor-plugin/plugin.json",
    ".claude-plugin/plugin.json",
)


def scalar(frontmatter: str, key: str) -> str | None:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(.*?)\s*$", frontmatter)
    if not match:
        return None
    value = match.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return value


def source_skill() -> Path:
    return ROOT / "skills" / "manifest" / "SKILL.md"


def check_plugin_surfaces() -> list[str]:
    errors: list[str] = []
    skill = source_skill()
    if not skill.is_file():
        return ["SOURCE_SKILL_MISSING"]
    text = skill.read_text(encoding="utf-8")
    match = FRONTMATTER.match(text)
    if not match:
        errors.append("SOURCE_FRONTMATTER_INVALID")
    else:
        if scalar(match.group("body"), "name") != "manifest":
            errors.append("SOURCE_NAME_NOT_MANIFEST")
        description = scalar(match.group("body"), "description") or ""
        if "manifest this" not in description or "helix it" not in description:
            errors.append("SOURCE_DESCRIPTION_MISSING_INVOCATION_INTENTS")
    for relative in PLUGIN_RELATIVE:
        path = ROOT / relative
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"PLUGIN_INVALID:{relative}:{error}")
            continue
        if payload.get("skills") != "./skills/":
            errors.append(f"PLUGIN_SKILLS_ROOT:{relative}")
        if payload.get("version") != "0.1.0":
            errors.append(f"PLUGIN_VERSION:{relative}:{payload.get('version')!r}")
    return errors


def materialize(target_root: Path) -> dict[str, object]:
    source = source_skill()
    destination = target_root / ".agents" / "skills" / "manifest" / "SKILL.md"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    loaded = destination.read_text(encoding="utf-8")
    source_text = source.read_text(encoding="utf-8")
    if loaded != source_text:
        raise RuntimeError("MATERIALIZE_BYTE_MISMATCH")
    match = FRONTMATTER.match(loaded)
    if not match:
        raise RuntimeError("MATERIALIZE_FRONTMATTER_INVALID")
    name = scalar(match.group("body"), "name")
    description = scalar(match.group("body"), "description") or ""
    skill_dirs = sorted(
        path.name
        for path in (target_root / ".agents" / "skills").iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    )
    report = {
        "schema": "practical-agency-harness-materialize@1",
        "source_skill": "skills/manifest/SKILL.md",
        "installed_path": str(destination),
        "loaded_skill_count": len(skill_dirs),
        "loaded_skill_name": name,
        "loaded_skill_names": skill_dirs,
        "description_exact": loaded == source_text,
        "description_bytes": len(description.encode("utf-8")),
        "invocation_intents": {
            "manifest this": "manifest this" in description,
            "helix it": "helix it" in description,
        },
    }
    receipt = target_root / "harness-materialize-receipt.json"
    receipt.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--materialize",
        type=Path,
        help="Materialize the generic Agent Skills layout under this directory",
    )
    args = parser.parse_args(argv)

    errors = check_plugin_surfaces()
    if errors:
        print("harness surface check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    if args.materialize is not None:
        target = args.materialize.resolve()
        target.mkdir(parents=True, exist_ok=True)
        # Refuse writing into the product tree (second SKILL.md breaks package check).
        try:
            target.relative_to(ROOT)
        except ValueError:
            pass
        else:
            print(
                "harness surface check failed: refuse materialize inside product tree",
                file=sys.stderr,
            )
            return 1
        report = materialize(target)
        print(
            "harness materialize ok: "
            f"count={report['loaded_skill_count']} name={report['loaded_skill_name']} "
            f"description_exact={report['description_exact']}"
        )
    else:
        print("harness surfaces ok: plugin roots -> ./skills/; source intents present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
