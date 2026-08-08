#!/usr/bin/env python3
"""Validate committed JSON, strict contract shape, and mission examples."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from practical_agency.validation import validate_manifest_dict  # noqa: E402

REQUIRED_SCHEMAS = {
    "mission-manifest.schema.json",
    "mission-event.schema.json",
    "checkpoint.schema.json",
    "execution-request.schema.json",
    "execution-receipt.schema.json",
    "capability-request.schema.json",
    "capability-result.schema.json",
}


def check_object_strictness(node: Any, path: str, errors: list[str]) -> None:
    if isinstance(node, dict):
        if (
            node.get("type") == "object"
            and "properties" in node
            and node.get("x-practical-agency-open") is not True
            and node.get("additionalProperties") is not False
        ):
            errors.append(f"OPEN_SCHEMA_OBJECT: {path}")
        for key, value in node.items():
            check_object_strictness(value, f"{path}.{key}", errors)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            check_object_strictness(value, f"{path}[{index}]", errors)


def main() -> int:
    errors: list[str] = []
    for path in sorted(ROOT.rglob("*.json")):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"INVALID_JSON: {path.relative_to(ROOT)}: {error}")

    schema_dir = ROOT / "contracts"
    actual = {path.name for path in schema_dir.glob("*.json")}
    if actual != REQUIRED_SCHEMAS:
        errors.append(
            f"SCHEMA_SET_MISMATCH: expected={sorted(REQUIRED_SCHEMAS)} actual={sorted(actual)}"
        )
    for path in sorted(schema_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            errors.append(f"SCHEMA_DRAFT_MISMATCH: {path.name}")
        if payload.get("additionalProperties") is not False:
            errors.append(f"OPEN_ROOT_SCHEMA: {path.name}")
        check_object_strictness(payload, path.name, errors)

    for path in sorted((ROOT / "examples").glob("*-mission.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for error in validate_manifest_dict(payload):
            errors.append(f"INVALID_MISSION_EXAMPLE: {path.name}: {error}")

    if errors:
        print("contract check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(
        f"contracts ok: {len(REQUIRED_SCHEMAS)} schemas, "
        f"{len(list((ROOT / 'examples').glob('*-mission.json')))} mission examples"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
