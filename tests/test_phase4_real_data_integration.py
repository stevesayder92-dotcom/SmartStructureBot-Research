from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from core.pipeline_runner import PipelineOptions, run_pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Phase4RealDataIntegrationTest(unittest.TestCase):
    def test_gold_qualified_entry_reaches_canonical_director(self):
        data = pd.read_csv(
            PROJECT_ROOT / "research_data" / "GOLD_M1.csv"
        ).reset_index(drop=True)
        index = 3064
        result = run_pipeline(
            data=data,
            symbol="GOLD#",
            timeframe="M1",
            as_of_index=index,
            options=PipelineOptions(),
        )
        retracement = result.snapshot["retracement"]
        entry = result.snapshot["entry"]
        setup = result.snapshot["setup"]

        self.assertEqual(retracement["state"], "CONSUMED")
        self.assertTrue(entry["ready"])
        self.assertEqual(entry["index"], index)
        self.assertEqual(
            entry["price"],
            float(data.at[index, "close"]),
        )
        self.assertIsNotNone(setup["setup_id"])
        self.assertLessEqual(
            retracement["origin_bos_index"],
            retracement[
                "qualified_retracement_start_index"
            ],
        )
        self.assertLessEqual(
            retracement[
                "qualified_retracement_start_index"
            ],
            retracement["current_pullback_end"],
        )
        self.assertGreaterEqual(
            retracement["failure_trigger"]["index"],
            retracement["qualification_index"],
        )
        self.assertEqual(
            result.snapshot["meta"]["setup_id"],
            setup["setup_id"],
        )


if __name__ == "__main__":
    unittest.main()
