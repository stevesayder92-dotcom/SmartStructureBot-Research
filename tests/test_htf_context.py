from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from core.htf_context import (
    HTFContextPolicy,
    HigherTimeframeContextEngine,
    attach_local_alignment,
)
from core.pipeline_runner import (
    PipelineOptions,
    run_pipeline,
)
from core.setup_lifecycle import PipelineRuntimeState


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = (
    PROJECT_ROOT
    / "test_data"
    / "GER40Cash_M5_400_raw.csv"
)


def snapshot(
    trend: str,
    phase: str = "BULLISH_EXPANSION",
    *,
    hard_block: bool = False,
):
    return {
        "meta": {"as_of_index": 20},
        "market": {"trend": trend},
        "structure": {"phase": phase},
        "validation": {
            "verdict": (
                "STRUCTURE_INVALID"
                if hard_block
                else "STRUCTURE_VALID"
            ),
            "hard_block": hard_block,
        },
        "contract_health": {"valid": True},
    }


def record(
    timeframe: str,
    trend: str,
    open_time: float,
    *,
    phase: str | None = None,
):
    seconds = {
        "H1": 3600,
        "M30": 1800,
        "M15": 900,
    }[timeframe]
    return {
        "bar_open_time": open_time,
        "bar_close_time": open_time + seconds,
        "snapshot": snapshot(
            trend,
            phase
            or f"{trend}_EXPANSION",
        ),
        "causal": True,
    }


class HigherTimeframeContextTest(unittest.TestCase):
    def test_m30_m15_preferred_agreement(self):
        engine = HigherTimeframeContextEngine(
            HTFContextPolicy(
                name="PREFER_M30_M15"
            )
        )
        context = engine.build(
            decision_candle_open_time=10_000,
            decision_timeframe_seconds=300,
            frame_histories={
                "H1": [
                    record(
                        "H1",
                        "BEARISH",
                        6_000,
                    )
                ],
                "M30": [
                    record(
                        "M30",
                        "BULLISH",
                        8_400,
                    )
                ],
                "M15": [
                    record(
                        "M15",
                        "BULLISH",
                        9_000,
                    )
                ],
            },
        )

        self.assertEqual(
            context["approved_direction"],
            "BULLISH",
        )
        self.assertEqual(
            context["state"],
            "M30_M15_AGREEMENT",
        )
        self.assertFalse(
            context["incomplete_htf_candles_used"]
        )

    def test_consensus_policy_requires_two_clean_frames(self):
        engine = HigherTimeframeContextEngine(
            HTFContextPolicy(
                name="CONSENSUS_2_OF_3",
                allow_single_strong=False,
            )
        )
        context = engine.build(
            decision_candle_open_time=10_000,
            decision_timeframe_seconds=300,
            frame_histories={
                "H1": [
                    record("H1", "BEARISH", 6_000)
                ],
                "M30": [
                    record("M30", "BEARISH", 8_400)
                ],
                "M15": [
                    record("M15", "BULLISH", 9_000)
                ],
            },
        )

        self.assertEqual(
            context["approved_direction"],
            "BEARISH",
        )
        self.assertEqual(
            context["votes"]["BEARISH"],
            2,
        )

    def test_one_clean_strong_htf_can_be_accepted(self):
        engine = HigherTimeframeContextEngine(
            HTFContextPolicy(
                name="PREFER_M30_M15",
                allow_single_strong=True,
            )
        )
        context = engine.build(
            decision_candle_open_time=10_000,
            decision_timeframe_seconds=300,
            frame_histories={
                "H1": [
                    record("H1", "BULLISH", 6_000)
                ],
                "M30": [],
                "M15": [],
            },
        )

        self.assertEqual(
            context["approved_direction"],
            "BULLISH",
        )
        self.assertTrue(
            context["strong_single_accepted"]
        )

    def test_future_htf_snapshot_cannot_retroactively_change_context(self):
        engine = HigherTimeframeContextEngine()
        context = engine.build(
            decision_candle_open_time=10_000,
            decision_timeframe_seconds=300,
            frame_histories={
                "M15": [
                    record(
                        "M15",
                        "BEARISH",
                        9_000,
                    ),
                    record(
                        "M15",
                        "BULLISH",
                        9_600,
                    ),
                ]
            },
        )

        self.assertEqual(
            context["frames"]["M15"]["trend"],
            "BEARISH",
        )
        self.assertEqual(
            context[
                "future_or_incomplete_records_rejected"
            ],
            1,
        )
        self.assertFalse(
            context["incomplete_htf_candles_used"]
        )

    def test_local_countertrend_does_not_overwrite_htf(self):
        context = {
            "approved_direction": "BULLISH",
            "available": True,
            "state": "HTF_CONSENSUS",
            "reason": [],
        }
        aligned = attach_local_alignment(
            context,
            "BEARISH",
        )

        self.assertEqual(
            aligned["approved_direction"],
            "BULLISH",
        )
        self.assertEqual(
            aligned["entry_alignment"],
            "CONFLICT",
        )

    def test_pipeline_publishes_context_without_hardcoding_gate(self):
        data = pd.read_csv(DATA_PATH)
        runtime_state = PipelineRuntimeState()
        result = None
        htf_context = {
            "available": True,
            "state": "H1_ANCHOR_SELECTED",
            "approved_direction": "BEARISH",
            "policy": "H1_ANCHOR",
            "frames": {},
            "votes": {
                "BULLISH": 0,
                "BEARISH": 1,
            },
            "causal": True,
            "incomplete_htf_candles_used": False,
            "reason": [],
        }

        for index in range(100, 103):
            result = run_pipeline(
                data=data,
                symbol="GER40Cash#",
                timeframe=5,
                as_of_index=index,
                options=PipelineOptions(
                    enforce_retracement_origin=False,
                ),
                runtime_state=runtime_state,
                higher_timeframe_context=(
                    htf_context
                ),
            )

        assert result is not None
        self.assertFalse(
            result.snapshot["entry"]["ready"]
        )
        self.assertEqual(
            result.snapshot["entry"][
                "direction"
            ],
            "BULLISH",
        )
        self.assertEqual(
            result.snapshot["context"][
                "approved_direction"
            ],
            "BEARISH",
        )
        self.assertIn(
            result.snapshot["context"][
                "entry_alignment"
            ],
            {"CONFLICT", "NO_ENTRY_DIRECTION"},
        )
        self.assertIn(
            result.snapshot["entry"][
                "htf_alignment"
            ],
            {"CONFLICT", "NO_ENTRY_DIRECTION"},
        )


if __name__ == "__main__":
    unittest.main()
