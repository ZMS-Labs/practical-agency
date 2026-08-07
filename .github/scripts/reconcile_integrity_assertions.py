#!/usr/bin/env python3
"""Reconcile exact regression assertions after the hardened APIs stabilized."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "tests" / "test_integrity_hardening.py"


def replace_once(old: str, new: str) -> None:
    text = TARGET.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one assertion marker, found {count}: {old[:100]!r}")
    TARGET.write_text(text.replace(old, new), encoding="utf-8")


replace_once(
    '''error.startswith(("INVALID_STRING_LIST:", "INVALID_OBJECT_LIST:"))''',
    '''error.startswith((
                        "INVALID_STRING_LIST:",
                        "INVALID_OBJECT_LIST:",
                        "INVALID_SUBJECT_REFS:",
                    ))''',
)
replace_once(
    '''        self.assertEqual(reopened.state["status"], "blocked")
''',
    '''        self.assertEqual(reopened.state["status"], "active")
''',
)
replace_once(
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
replace_once('''"COMMISSION_NOT_ACTIVE"''', '''"COMMISSION_NOT_OPERATING"''')
print("integrity assertions reconciled")
