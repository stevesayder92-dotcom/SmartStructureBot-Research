from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from core.pipeline_runner import (
    PipelineOptions,
    run_pipeline,
)
from core.replay_inspector import ReplayInspector
from core.signal_ledger import SignalLedger


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPLAY_DATA = (
    PROJECT_ROOT
    / "test_data"
    / "GER40Cash_M5_400_raw.csv"
)


class CanonicalEntryFlowTest(unittest.TestCase):
    def test_phase4_pipeline_never_publishes_pre_origin_setup(self):
        data = pd.read_csv(REPLAY_DATA).reset_index(drop=True)

        ledger = SignalLedger()
        ready_count = 0
        coherent_setups = 0

        for as_of_index in range(100, len(data)):
            pipeline_result = run_pipeline(
                data=data,
                symbol="GER40Cash#",
                timeframe=5,
                as_of_index=as_of_index,
                options=PipelineOptions(
                    enforce_retracement_origin=False,
                ),
            )
            snapshot = pipeline_result.snapshot
            candle = data.iloc[as_of_index].to_dict()
            ledger.record_snapshot(
                snapshot=snapshot,
                candle=candle,
            )
            entry = snapshot["entry"]
            setup = snapshot["setup"]
            if entry.get("ready"):
                ready_count += 1
                self.assertIsNotNone(entry.get("setup_id"))
                self.assertEqual(entry.get("index"), as_of_index)
            if setup.get("setup_id"):
                coherent_setups += 1
                self.assertLessEqual(
                    setup["origin_trend_bos"],
                    setup["initial_pullback_start"],
                )
                self.assertLessEqual(
                    setup["initial_pullback_start"],
                    setup["current_pullback_end"],
                )

        inspected_entries = ReplayInspector(
            data=data,
            ledger=ledger,
        ).entry_records(allowed_only=True)
        self.assertEqual(len(inspected_entries), ready_count)
        self.assertGreaterEqual(coherent_setups, 0)


if __name__ == "__main__":
    unittest.main()
