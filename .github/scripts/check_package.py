#!/usr/bin/env python3
"""Enforce the one-skill package surface and resident description budget."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTMATTER = re.compile(r"\A---\r?\n(?P<body>.*?)\r?\n---(?:\r?\n|\Z)", re.S)
DESCRIPTION_BUDGET_BYTES = 420


def scalar(frontmatter: str, key: str) -> str | None:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(.*?)\s*$", frontmatter)
    if not match:
        return None
    value = match.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'\"', "'"}:
        value = value[1:-1]
    return value


def main() -> int:
    errors: list[str] = []
    all_skills = sorted(ROOT.rglob("SKILL.md"))
    expected = ROOT / "skills" / "manifest" / "SKILL.md"
    if all_skills != [expected]:
        errors.append(
            "PUBLIC_SKILL_SET_MISMATCH: expected only skills/manifest/SKILL.md; "
            f"found={[str(path.relative_to(ROOT)) for path in all_skills]}"
        )
    if expected.is_file():
        text = expected.read_text(encoding="utf-8")
        match = FRONTMATTER.match(text)
        if not match:
            errors.append("MANIFEST_FRONTMATTER_INVALID")
        else:
            name = scalar(match.group("body"), "name")
            description = scalar(match.group("body"), "description")
            if name != "manifest":
                errors.append(f"MANIFEST_NAME_INVALID:{name!r}")
            if not description:
                errors.append("MANIFEST_DESCRIPTION_MISSING")
            elif len(description.encode("utf-8")) > DESCRIPTION_BUDGET_BYTES:
                errors.append(
                    f"DESCRIPTION_BUDGET_EXCEEDED:{len(description.encode('utf-8'))}>"
                    f"{DESCRIPTION_BUDGET_BYTES}"
                )
            elif "Do NOT use" not in description:
                errors.append("MANIFEST_DECLINE_BOUNDARY_MISSING")

    for relative in (
        "plugin.json",
        ".cursor-plugin/plugin.json",
        ".claude-plugin/plugin.json",
    ):
        path = ROOT / relative
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"PLUGIN_METADATA_INVALID:{relative}:{error}")
            continue
        if payload.get("skills") != "./skills/":
            errors.append(f"PLUGIN_SKILL_ROOT_INVALID:{relative}")

    if errors:
        print("package check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    description = scalar(
        FRONTMATTER.match(expected.read_text(encoding="utf-8")).group("body"),
        "description",
    )
    print(
        "package ok: one public skill (manifest), "
        f"description_bytes={len((description or '').encode('utf-8'))}/"
        f"{DESCRIPTION_BUDGET_BYTES}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
