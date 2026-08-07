#!/usr/bin/env python3
"""Apply the final bounded schema/semantic and watch-state alignment."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, found {count}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    validation = ROOT / "practical_agency/validation.py"
    replace_once(
        validation,
        '            "INVALID_SUBJECT_REFS: truth.subject_refs must contain only non-empty strings"\n',
        '            "INVALID_STRING_LIST: truth.subject_refs must contain only non-empty strings"\n',
    )
    marker = '''    for field in ("decisions", "external_handoffs", "watch_commissions"):\n        if not _all_mappings(continuity.get(field)):\n            errors.append(\n                f"INVALID_OBJECT_LIST: continuity.{field} must contain only objects"\n            )\n\n'''
    replace_once(
        validation,
        marker,
        marker
        + '''    if not _all_nonempty_strings(continuity.get("durable_artifacts")):\n        errors.append(\n            "INVALID_STRING_LIST: continuity.durable_artifacts must contain only non-empty strings"\n        )\n\n''',
    )
    marker = '''    if not _optional_string(integrity.get("completion_acceptor")):\n        errors.append(\n            "INVALID_OPTIONAL_STRING: integrity.completion_acceptor must be null or a string"\n        )\n\n'''
    replace_once(
        validation,
        marker,
        marker
        + '''    for field in ("required_gates", "unresolved_verdicts"):\n        if not _all_nonempty_strings(integrity.get(field)):\n            errors.append(\n                f"INVALID_STRING_LIST: integrity.{field} must contain only non-empty strings"\n            )\n\n''',
    )

    schema = ROOT / "contracts/mission-manifest.schema.json"
    replace_once(
        schema,
        '''        "durable_artifacts": {\n          "type": "array",\n          "items": {}\n        },''',
        '''        "durable_artifacts": {\n          "type": "array",\n          "items": {\n            "type": "string",\n            "minLength": 1\n          }\n        },''',
    )
    replace_once(
        schema,
        '''        "required_gates": {\n          "type": "array",\n          "items": {}\n        },''',
        '''        "required_gates": {\n          "type": "array",\n          "items": {\n            "type": "string",\n            "minLength": 1\n          }\n        },''',
    )
    replace_once(
        schema,
        '''        "unresolved_verdicts": {\n          "type": "array",\n          "items": {}\n        },''',
        '''        "unresolved_verdicts": {\n          "type": "array",\n          "items": {\n            "type": "string",\n            "minLength": 1\n          }\n        },''',
    )

    replace_once(
        ROOT / "practical_agency/watch_commission.py",
        '        raise CommissionIntegrationError("COMMISSION_NOT_OPERATING")\n',
        '        raise CommissionIntegrationError("COMMISSION_NOT_ACTIVE")\n',
    )
    replace_once(
        ROOT / "tests/test_manifest_model.py",
        '            (("truth", "subject_refs"), [1], "INVALID_SUBJECT_REFS:"),\n',
        '            (("truth", "subject_refs"), [1], "INVALID_STRING_LIST:"),\n',
    )

    for relative in (
        ".github/scripts/finalize_integrity_hardening.py",
        ".github/workflows/finalize-integrity-hardening.yml",
    ):
        path = ROOT / relative
        if path.exists():
            path.unlink()

    print("final integrity alignment applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
