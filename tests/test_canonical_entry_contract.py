from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from core.pipeline_runner import (
    PipelineOptions,
    _build_canonical_entry,
    run_pipeline,
)
from core.signal_ledger import SignalLedger


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPLAY_DATA = (
    PROJECT_ROOT
    / "test_data"
    / "GER40Cash_M5_400_raw.csv"
)


class CanonicalEntryContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = pd.read_csv(REPLAY_DATA).reset_index(
            drop=True
        )

    def _pipeline(self, index: int, data=None):
        source = self.data if data is None else data
        return run_pipeline(
            data=source,
            symbol="GER40Cash#",
            timeframe=5,
            as_of_index=index,
            options=PipelineOptions(
                enforce_retracement_origin=False,
            ),
        )

    def test_legacy_entry_is_not_restored_by_phase4(self):
        result = self._pipeline(102)
        entry = result.snapshot["entry"]

        self.assertIs(entry["available"], False)
        self.assertIs(entry["ready"], False)
        self.assertIsNone(entry["index"])
        self.assertIsNone(entry["price"])
        self.assertEqual(
            result.snapshot["retracement"]["state"],
            "MICRO_COUNTER_NOISE",
        )
        self.assertIs(entry["causal"], True)
        self.assertIs(entry["current_candle_only"], True)
        self.assertIs(
            result.diagnostics[
                "canonical_entry_as_of_matches"
            ],
            True,
        )
        self.assertIs(
            result.diagnostics[
                "canonical_entry_price_matches_close"
            ],
            True,
        )

    def test_noise_candle_creates_no_ledger_entry(self):
        result = self._pipeline(102)
        ledger = SignalLedger()
        candle = self.data.iloc[102].to_dict()

        first = ledger.record_snapshot(
            snapshot=result.snapshot,
            candle=candle,
        )
        second = ledger.record_snapshot(
            snapshot=result.snapshot,
            candle=candle,
        )

        self.assertIsNone(first)
        self.assertIsNone(second)
        self.assertEqual(len(ledger.entry_events()), 0)

    def test_blocked_candidate_is_published_non_ready(self):
        result = self._pipeline(100)
        entry = result.snapshot["entry"]
        ledger = SignalLedger()
        event = ledger.record_snapshot(
            snapshot=result.snapshot,
            candle=self.data.iloc[100].to_dict(),
        )

        self.assertFalse(
            result.snapshot["market"][
                "continuation_state"
            ]["entry_ready"]
        )
        self.assertEqual(entry["state"], "NO_TRADE")
        self.assertIs(entry["available"], False)
        self.assertIs(entry["ready"], False)
        self.assertIsNone(entry["index"])
        self.assertIsNone(entry["price"])
        self.assertIsNone(event)
        self.assertEqual(ledger.entry_events(True), [])

    def test_stale_candidate_cannot_be_published(self):
        continuation = {
            "state": "ENTRY_READY",
            "entry_ready": True,
            "causal_valid": True,
            "current_candle_only": True,
            "failure_trigger": {
                "index": 8,
                "level": 100.0,
            },
            "continuation_bos": {
                "type": "BULLISH_ENTRY_BOS",
                "index": 9,
                "entry_price": 101.0,
                "broken_structure_index": 8,
                "broken_structure_price": 100.0,
                "causal_valid": True,
                "current_candle_only": True,
            },
        }
        validation = {
            "allowed": True,
            "state": "ENTRY_VALIDATED",
            "causal_valid": True,
            "current_candle_only": True,
            "reason": [],
        }

        entry = _build_canonical_entry(
            trend="BULLISH",
            as_of_index=10,
            current_close=102.0,
            continuation_state=continuation,
            entry_validation=validation,
        )

        self.assertIs(entry["available"], False)
        self.assertIs(entry["ready"], False)
        self.assertEqual(entry["state"], "BLOCKED_STALE_ENTRY")
        self.assertIsNone(entry["index"])
        self.assertIsNone(entry["price"])
        self.assertIs(entry["causal"], False)

    def test_future_suffix_does_not_change_entry(self):
        full_result = self._pipeline(102)
        prefix = self.data.iloc[:103].copy()
        prefix_result = self._pipeline(
            102,
            data=prefix,
        )

        self.assertEqual(
            full_result.snapshot["entry"],
            prefix_result.snapshot["entry"],
        )
        self.assertEqual(
            full_result.diagnostics[
                "future_structures_used"
            ],
            0,
        )
        self.assertEqual(
            full_result.diagnostics[
                "future_strength_used"
            ],
            0,
        )
        self.assertIs(
            full_result.diagnostics[
                "future_access_test_passed"
            ],
            True,
        )


if __name__ == "__main__":
    unittest.main()
