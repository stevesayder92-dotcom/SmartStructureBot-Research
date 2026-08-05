from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from core.pipeline_runner import (
    PipelineOptions,
    run_pipeline,
)
from core.replay_inspector import ReplayInspector
from core.setup_lifecycle import PipelineRuntimeState
from core.signal_ledger import SignalLedger


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPLAY_DATA = (
    PROJECT_ROOT
    / "test_data"
    / "GER40Cash_M5_400_raw.csv"
)


class SetupConsumptionIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = pd.read_csv(REPLAY_DATA).reset_index(
            drop=True
        )

    def test_micro_noise_does_not_create_consumable_setup(self):
        runtime_state = PipelineRuntimeState()
        ledger = SignalLedger()
        results = []

        for index in range(100, 106):
            result = run_pipeline(
                data=self.data,
                symbol="GER40Cash#",
                timeframe=5,
                as_of_index=index,
                options=PipelineOptions(
                    enforce_retracement_origin=False,
                ),
                runtime_state=runtime_state,
            )
            ledger.record_snapshot(
                snapshot=result.snapshot,
                candle=self.data.iloc[index].to_dict(),
            )
            results.append(result)

        ready_results = [
            result
            for result in results
            if result.snapshot["entry"]["ready"]
        ]
        candidate_setup_ids = {
            result.snapshot["entry"]["setup_id"]
            for result in results
            if result.snapshot["market"][
                "continuation_state"
            ]["entry_ready"]
        }

        self.assertEqual(len(ready_results), 0)
        self.assertEqual(len(candidate_setup_ids), 0)
        self.assertEqual(
            len(ledger.entry_events(allowed_only=True)),
            0,
        )
        self.assertEqual(
            len(
                ReplayInspector(
                    data=self.data,
                    ledger=ledger,
                ).entry_records(allowed_only=True)
            ),
            0,
        )

    def test_canonical_candidate_setup_id_is_never_none(self):
        runtime_state = PipelineRuntimeState()

        for index in range(100, 106):
            result = run_pipeline(
                data=self.data,
                symbol="GER40Cash#",
                timeframe=5,
                as_of_index=index,
                options=PipelineOptions(
                    enforce_retracement_origin=False,
                ),
                runtime_state=runtime_state,
            )
            continuation = result.snapshot["market"][
                "continuation_state"
            ]

            if continuation["entry_ready"]:
                self.assertIsNotNone(
                    result.snapshot["entry"][
                        "setup_id"
                    ]
                )


if __name__ == "__main__":
    unittest.main()
