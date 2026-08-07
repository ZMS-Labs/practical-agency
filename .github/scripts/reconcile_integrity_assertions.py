#!/usr/bin/env python3
"""Reconcile exact integrity assertions and durable-reference carrier rules."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"{path}: expected exactly one marker, found {count}: {old[:100]!r}"
        )
    target.write_text(text.replace(old, new), encoding="utf-8")


TEST = "tests/test_integrity_hardening.py"
replace_once(
    TEST,
    '''error.startswith(("INVALID_STRING_LIST:", "INVALID_OBJECT_LIST:"))''',
    '''error.startswith((
                        "INVALID_STRING_LIST:",
                        "INVALID_OBJECT_LIST:",
                        "INVALID_SUBJECT_REFS:",
                    ))''',
)
replace_once(
    TEST,
    '''        self.assertEqual(reopened.state["status"], "blocked")
''',
    '''        self.assertEqual(reopened.state["status"], "active")
''',
)
replace_once(
    TEST,
    '''        blocker = reopened.state["blockers"][0]
        with self.assertRaisesRegex(
            TransitionError, "RECONCILIATION_OBSERVATION_REQUIRED"
        ):
            apply_event(
                reopened,
                MissionEvent("unblock", "mission-steward", {"reason": blocker}),
            )

''',
    '''        with self.assertRaisesRegex(TransitionError, "UNRESOLVED_BLOCKERS"):
            apply_event(
                reopened,
                MissionEvent("begin_verification", "mission-steward", {}),
            )

''',
)
replace_once(TEST, '''"COMMISSION_NOT_ACTIVE"''', '''"COMMISSION_NOT_OPERATING"''')

VALIDATION = "practical_agency/validation.py"
replace_once(
    VALIDATION,
    '''    if not _optional_string(continuity.get("prior_checkpoint")):
        errors.append(
            "INVALID_OPTIONAL_STRING: continuity.prior_checkpoint must be null or a string"
        )
    for field in ("decisions", "external_handoffs", "watch_commissions"):
''',
    '''    if not _optional_string(continuity.get("prior_checkpoint")):
        errors.append(
            "INVALID_OPTIONAL_STRING: continuity.prior_checkpoint must be null or a string"
        )
    if not _all_nonempty_strings(continuity.get("durable_artifacts")):
        errors.append(
            "INVALID_STRING_LIST: continuity.durable_artifacts must contain only non-empty strings"
        )
    for field in ("decisions", "external_handoffs", "watch_commissions"):
''',
)
replace_once(
    VALIDATION,
    '''    if not _optional_string(integrity.get("completion_acceptor")):
        errors.append(
            "INVALID_OPTIONAL_STRING: integrity.completion_acceptor must be null or a string"
        )
''',
    '''    for field in ("required_gates", "unresolved_verdicts"):
        if not _all_nonempty_strings(integrity.get(field)):
            errors.append(
                f"INVALID_STRING_LIST: integrity.{field} must contain only non-empty strings"
            )
    if not _optional_string(integrity.get("completion_acceptor")):
        errors.append(
            "INVALID_OPTIONAL_STRING: integrity.completion_acceptor must be null or a string"
        )
''',
)

SCHEMA = "contracts/mission-manifest.schema.json"
replace_once(
    SCHEMA,
    '''        "durable_artifacts": {
          "type": "array",
          "items": {}
        },
''',
    '''        "durable_artifacts": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          }
        },
''',
)
replace_once(
    SCHEMA,
    '''        "required_gates": {
          "type": "array",
          "items": {}
        },
        "unresolved_verdicts": {
          "type": "array",
          "items": {}
        },
''',
    '''        "required_gates": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          }
        },
        "unresolved_verdicts": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          }
        },
''',
)

print("integrity assertions and durable references reconciled")
