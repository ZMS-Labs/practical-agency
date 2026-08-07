#!/usr/bin/env python3
"""Apply the final bounded schema/semantic and watch-state alignment."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def ensure_replacement(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    old_count = text.count(old)
    new_count = text.count(new)
    if old_count == 1 and new_count == 0:
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        return
    if old_count == 0 and new_count == 1:
        return
    raise SystemExit(
        f"{path}: expected exactly old or exactly new state; "
        f"old={old_count} new={new_count}: {old[:90]!r}"
    )


def ensure_insertion(path: Path, marker: str, addition: str) -> None:
    text = path.read_text(encoding="utf-8")
    marker_count = text.count(marker)
    addition_count = text.count(addition)
    if marker_count != 1:
        raise SystemExit(f"{path}: expected one insertion marker, found {marker_count}")
    if addition_count == 0:
        path.write_text(text.replace(marker, marker + addition, 1), encoding="utf-8")
        return
    if addition_count == 1:
        return
    raise SystemExit(f"{path}: expected zero or one approved insertion, found {addition_count}")


def main() -> int:
    validation = ROOT / "practical_agency/validation.py"
    ensure_replacement(
        validation,
        '            "INVALID_SUBJECT_REFS: truth.subject_refs must contain only non-empty strings"\n',
        '            "INVALID_STRING_LIST: truth.subject_refs must contain only non-empty strings"\n',
    )
    ensure_insertion(
        validation,
        '''    for field in ("decisions", "external_handoffs", "watch_commissions"):\n        if not _all_mappings(continuity.get(field)):\n            errors.append(\n                f"INVALID_OBJECT_LIST: continuity.{field} must contain only objects"\n            )\n\n''',
        '''    if not _all_nonempty_strings(continuity.get("durable_artifacts")):\n        errors.append(\n            "INVALID_STRING_LIST: continuity.durable_artifacts must contain only non-empty strings"\n        )\n\n''',
    )
    ensure_insertion(
        validation,
        '''    if not _optional_string(integrity.get("completion_acceptor")):\n        errors.append(\n            "INVALID_OPTIONAL_STRING: integrity.completion_acceptor must be null or a string"\n        )\n\n''',
        '''    for field in ("required_gates", "unresolved_verdicts"):\n        if not _all_nonempty_strings(integrity.get(field)):\n            errors.append(\n                f"INVALID_STRING_LIST: integrity.{field} must contain only non-empty strings"\n            )\n\n''',
    )

    schema = ROOT / "contracts/mission-manifest.schema.json"
    ensure_replacement(
        schema,
        '''        "durable_artifacts": {\n          "type": "array",\n          "items": {}\n        },''',
        '''        "durable_artifacts": {\n          "type": "array",\n          "items": {\n            "type": "string",\n            "minLength": 1\n          }\n        },''',
    )
    ensure_replacement(
        schema,
        '''        "required_gates": {\n          "type": "array",\n          "items": {}\n        },''',
        '''        "required_gates": {\n          "type": "array",\n          "items": {\n            "type": "string",\n            "minLength": 1\n          }\n        },''',
    )
    ensure_replacement(
        schema,
        '''        "unresolved_verdicts": {\n          "type": "array",\n          "items": {}\n        },''',
        '''        "unresolved_verdicts": {\n          "type": "array",\n          "items": {\n            "type": "string",\n            "minLength": 1\n          }\n        },''',
    )

    ensure_replacement(
        ROOT / "practical_agency/watch_commission.py",
        '        raise CommissionIntegrationError("COMMISSION_NOT_OPERATING")\n',
        '        raise CommissionIntegrationError("COMMISSION_NOT_ACTIVE")\n',
    )
    ensure_replacement(
        ROOT / "tests/test_manifest_model.py",
        '            (("truth", "subject_refs"), [1], "INVALID_SUBJECT_REFS:"),\n',
        '            (("truth", "subject_refs"), [1], "INVALID_STRING_LIST:"),\n',
    )

    for relative in (
        ".github/scripts/finalize_integrity_hardening.py",
        ".github/workflows/finalize-integrity-hardening.yml",
        ".github/scripts/reconcile_integrity_assertions.py",
        ".github/workflows/reconcile-integrity-assertions.yml",
    ):
        path = ROOT / relative
        if path.exists():
            path.unlink()

    print("final integrity alignment applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
