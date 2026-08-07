from __future__ import annotations

import unittest
from typing import Any

from practical_agency.watch_commission import (
    MissionWatchCustody,
    UnverifiedExternalContract,
    FakeWatchExecutionAdapter,
)


def _blocked_no_substrate() -> dict[str, Any]:
    return {
        "schema": "watch-commission@1",
        "commission_id": "wc-1",
        "state": "BLOCKED",
        "block_reason": "NO_EXECUTION_SUBSTRATE",
        "block_evidence": {
            "detail": "no scheduler available",
            "observed_at": "2026-08-07T00:00:00Z",
            "receipt_ref": "discovery:none",
        },
        "proof": {},
        "observed_failure": {},
    }


class WatchCommissionAdapterTests(unittest.TestCase):
    def test_blocked_without_dispatch(self) -> None:
        custody = MissionWatchCustody(adapter=FakeWatchExecutionAdapter(), verifier=None)
        record = custody.retain(_blocked_no_substrate())
        self.assertEqual(record["state"], "BLOCKED")
        self.assertEqual(custody.dispatch_count, 0)

    def test_prepare_stays_blocked_until_kill_switch(self) -> None:
        adapter = FakeWatchExecutionAdapter()
        custody = MissionWatchCustody(adapter=adapter, verifier=lambda r: r)
        prepared = custody.prepare(_blocked_no_substrate())
        self.assertEqual(prepared["state"], "BLOCKED")
        self.assertEqual(prepared["block_reason"], "KILL_SWITCH_UNPROVEN")
        inert = custody.exercise_kill_switch(prepared)
        self.assertEqual(inert["state"], "INERT")

    def test_cannot_synthesize_proven_from_adapter_success(self) -> None:
        adapter = FakeWatchExecutionAdapter(force_success=True)
        custody = MissionWatchCustody(adapter=adapter, verifier=None)
        with self.assertRaises(UnverifiedExternalContract):
            custody.claim_proven(
                {
                    "schema": "watch-commission@1",
                    "commission_id": "wc-2",
                    "state": "INERT",
                    "block_reason": None,
                    "block_evidence": {},
                    "proof": {"alert_receipt": "r1"},
                    "observed_failure": {},
                }
            )

    def test_verifier_required_for_proven(self) -> None:
        adapter = FakeWatchExecutionAdapter()
        custody = MissionWatchCustody(
            adapter=adapter,
            verifier=lambda record: {**record, "state": "PROVEN"},
        )
        proven = custody.claim_proven(
            {
                "schema": "watch-commission@1",
                "commission_id": "wc-3",
                "state": "INERT",
                "block_reason": None,
                "block_evidence": {},
                "proof": {"alert_receipt": "r1"},
                "observed_failure": {},
                "mechanism_ref": "cron:disk",
            }
        )
        self.assertEqual(proven["state"], "PROVEN")

    def test_crossing_reopens_frontier(self) -> None:
        custody = MissionWatchCustody(adapter=FakeWatchExecutionAdapter(), verifier=None)
        custody.retain({**_blocked_no_substrate(), "commission_id": "wc-cross"})
        event = custody.crossing_event("wc-cross", detail="threshold crossed")
        self.assertEqual(event["commission_id"], "wc-cross")
        self.assertEqual(event["kind"], "watch_crossing")


if __name__ == "__main__":
    unittest.main()
