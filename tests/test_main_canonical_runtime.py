from __future__ import annotations

import ast
from copy import deepcopy
import unittest
from pathlib import Path

import pandas as pd

from core.application_runtime import (
    CANONICAL_OUTPUT_SECTIONS,
    analyze_closed_data,
)
from core.pipeline_runner import PipelineOptions, run_pipeline
from core.replay_runner import (
    ReplayOptions,
    run_replay,
)
from core.runtime_config import RuntimeConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = (
    PROJECT_ROOT
    / "test_data"
    / "GER40Cash_M5_400_raw.csv"
)


class MainCanonicalRuntimeTest(unittest.TestCase):
    def test_main_is_a_thin_launcher(self):
        source = (
            PROJECT_ROOT / "main.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }

        self.assertEqual(
            imported_modules,
            {
                "__future__",
                "pathlib",
                "core.application_runtime",
            },
        )

        forbidden = {
            "ContinuationEngine",
            "EntryValidator",
            "RetracementManager",
            "MarketStructureDetector",
            "SystemStateDirector",
        }
        self.assertFalse(
            forbidden.intersection(source.split())
        )

    def test_application_and_replay_share_pipeline_contract(self):
        data = pd.read_csv(DATA_PATH).iloc[:104].copy()
        config = RuntimeConfig(
            symbol="GER40Cash#",
            timeframe="M5",
            candles=len(data),
            minimum_history=100,
            replay_start_index=100,
        )

        application = analyze_closed_data(
            data=data,
            config=config,
            pipeline_callable=run_pipeline,
        )
        replay = run_replay(
            data=data,
            symbol=config.symbol,
            timeframe=config.timeframe,
            options=ReplayOptions(
                start_index=100,
                end_index=103,
            ),
            pipeline_options=PipelineOptions(
                strategy_model=config.strategy_model,
                engine_sensitivity=config.engine_sensitivity,
            ),
            pipeline_callable=run_pipeline,
        )

        expected_snapshot = deepcopy(
            replay.pipeline_results[-1].snapshot
        )
        actual_snapshot = deepcopy(
            application.snapshot
        )
        expected_snapshot["meta"].pop(
            "created_at",
            None,
        )
        actual_snapshot["meta"].pop(
            "created_at",
            None,
        )
        self.assertEqual(
            actual_snapshot,
            expected_snapshot,
        )
        self.assertEqual(
            set(application.canonical_outputs),
            set(CANONICAL_OUTPUT_SECTIONS),
        )
        self.assertIs(
            application.replay.pipeline_results[
                -1
            ].snapshot,
            application.snapshot,
        )

    def test_live_mode_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "Unsafe or unsupported",
        ):
            RuntimeConfig(mode="LIVE")


if __name__ == "__main__":
    unittest.main()
