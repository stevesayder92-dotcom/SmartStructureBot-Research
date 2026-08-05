from __future__ import annotations

import unittest

import pandas as pd

from core.steve_trade_management import atr_at
from core.expert_strategy import (
    build_expert_htf_context,
    confirmed_swings,
    infer_htf_direction,
)
from core.pipeline_runner import PipelineOptions, run_pipeline
from core.replay_runner import ReplayOptions, run_replay


def candles(
    highs: list[float],
    lows: list[float],
    closes: list[float] | None = None,
    *,
    spacing: int = 300,
) -> pd.DataFrame:
    if closes is None:
        closes = [
            (float(high) + float(low)) / 2
            for high, low in zip(highs, lows)
        ]
    return pd.DataFrame(
        {
            "time": [index * spacing for index in range(len(highs))],
            "open": list(closes),
            "high": highs,
            "low": lows,
            "close": closes,
            "tick_volume": [100] * len(highs),
        }
    )


def context(direction: str) -> dict:
    return {
        "available": direction in {"BULLISH", "BEARISH"},
        "availability": (
            "AVAILABLE"
            if direction in {"BULLISH", "BEARISH"}
            else "UNAVAILABLE"
        ),
        "state": f"STRICT_2_OF_3_{direction}",
        "owner": "HTFContextEngine",
        "policy": "STRICT_2_OF_3_H1_M30_M15",
        "approved_direction": direction,
        "frames": {},
        "votes": {
            "BULLISH": 2 if direction == "BULLISH" else 0,
            "BEARISH": 2 if direction == "BEARISH" else 0,
            "NEUTRAL": 3 if direction == "NEUTRAL" else 1,
        },
        "causal": True,
        "causal_valid": True,
        "incomplete_htf_candles_used": False,
        "hard_block": direction == "NEUTRAL",
        "advisory_only": False,
        "reasons": ["Synthetic strict-vote test context"],
    }


class ExpertSwingCausalityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.data = candles(
            highs=[1, 2, 3, 6, 3, 2, 1, 7, 8],
            lows=[0, 1, 2, 3, 2, 1, 0, 4, 5],
        )

    def test_swing_is_invisible_until_third_right_candle_closes(self):
        before = confirmed_swings(
            self.data, as_of_index=5, sensitivity=3
        )
        at_confirmation = confirmed_swings(
            self.data, as_of_index=6, sensitivity=3
        )
        self.assertFalse(
            any(point["index"] == 3 for point in before)
        )
        swing = next(
            point
            for point in at_confirmation
            if point["index"] == 3 and point["side"] == "HIGH"
        )
        self.assertEqual(swing["confirmed_at_index"], 6)
        self.assertEqual(swing["available_at_index"], 6)

    def test_confirmed_history_is_suffix_invariant_and_never_repaints(self):
        confirmed = confirmed_swings(
            self.data, as_of_index=6, sensitivity=3
        )
        extended = self.data.copy()
        extended.loc[len(extended)] = {
            "time": 9999,
            "open": 50,
            "high": 100,
            "low": -100,
            "close": 50,
            "tick_volume": 100,
        }
        later = confirmed_swings(
            extended, as_of_index=len(extended) - 1, sensitivity=3
        )
        original = [
            point for point in confirmed if point["confirmed_at_index"] <= 6
        ]
        preserved = [
            point for point in later if point["confirmed_at_index"] <= 6
        ]
        self.assertEqual(original, preserved)


class ExpertHTFContextTest(unittest.TestCase):
    @staticmethod
    def bullish(spacing: int) -> pd.DataFrame:
        return candles(
            highs=[10, 11, 12, 15, 12, 11, 10, 16, 17],
            lows=[8, 9, 10, 13, 10, 9, 8, 14, 15],
            closes=[9, 10, 11, 14, 11, 10, 9, 16, 16.5],
            spacing=spacing,
        )

    @staticmethod
    def bearish(spacing: int) -> pd.DataFrame:
        return candles(
            highs=[12, 11, 10, 7, 10, 11, 12, 6, 5],
            lows=[10, 9, 8, 5, 8, 9, 10, 4, 3],
            closes=[11, 10, 9, 6, 9, 10, 11, 4, 3.5],
            spacing=spacing,
        )

    def test_htf_direction_uses_close_not_wick(self):
        frame = self.bullish(900)
        frame.loc[7, "high"] = 16
        frame.loc[7, "close"] = 14.5
        frame.loc[8, "close"] = 14.5
        neutral = infer_htf_direction(frame, sensitivity=3)
        self.assertEqual(neutral["direction"], "NEUTRAL")
        frame.loc[8, "close"] = 15.5
        bullish = infer_htf_direction(frame, sensitivity=3)
        self.assertEqual(bullish["direction"], "BULLISH")
        self.assertTrue(bullish["last_break"]["close_only"])

    def test_strict_two_of_three_and_no_single_strong_override(self):
        frames = {
            "H1": self.bullish(3600),
            "M30": self.bullish(1800),
            "M15": self.bearish(900),
        }
        decision_open = 9 * 3600
        approved = build_expert_htf_context(
            decision_candle_open_time=decision_open,
            decision_timeframe_seconds=300,
            frame_data=frames,
            sensitivity=3,
        )
        self.assertEqual(approved["approved_direction"], "BULLISH")
        self.assertEqual(approved["votes"]["BULLISH"], 2)

        frames["M30"] = candles(
            highs=[10] * 9,
            lows=[9] * 9,
            closes=[9.5] * 9,
            spacing=1800,
        )
        blocked = build_expert_htf_context(
            decision_candle_open_time=decision_open,
            decision_timeframe_seconds=300,
            frame_data=frames,
            sensitivity=3,
        )
        self.assertEqual(blocked["approved_direction"], "NEUTRAL")
        self.assertTrue(blocked["hard_block"])

    def test_incomplete_htf_candle_is_excluded(self):
        frame = self.bullish(3600)
        decision_open = 7 * 3600
        result = build_expert_htf_context(
            decision_candle_open_time=decision_open,
            decision_timeframe_seconds=300,
            frame_data={"H1": frame, "M30": frame, "M15": frame},
            sensitivity=3,
        )
        self.assertEqual(
            result["frames"]["H1"]["closed_rows_used"], 7
        )


class ExpertRetracementEntryTest(unittest.TestCase):
    @staticmethod
    def bearish_setup(*, close_entry: bool) -> pd.DataFrame:
        highs = [
            13, 12, 11, 10, 11, 12, 13, 16,
            13, 12, 11, 10, 11, 12, 11, 10,
        ]
        lows = [
            10, 9, 8, 5, 8, 9, 10, 12,
            10, 9, 8.5, 8, 9, 9.5, 9.2, 7,
        ]
        closes = [
            11, 10, 9, 6, 9, 10, 12, 14,
            11, 10, 9, 9, 10, 10, 10,
            7 if close_entry else 9,
        ]
        result = candles(highs, lows, closes)
        # The expert contract requires the BOS candle body to point in the
        # entry direction; a doji close beyond structure is not an entry.
        result.loc[15, "open"] = 10.0
        return result

    def pipeline(self, data: pd.DataFrame):
        return run_pipeline(
            data=data,
            symbol="GER40Cash#",
            timeframe="M5",
            as_of_index=len(data) - 1,
            options=PipelineOptions(
                strategy_model="EXPERT_SPEC_V1",
                engine_sensitivity=3,
            ),
            higher_timeframe_context=context("BEARISH"),
        )

    def bullish_pipeline(self, data: pd.DataFrame):
        return run_pipeline(
            data=data,
            symbol="GER40Cash#",
            timeframe="M5",
            as_of_index=len(data) - 1,
            options=PipelineOptions(
                strategy_model="EXPERT_SPEC_V1",
                engine_sensitivity=3,
            ),
            higher_timeframe_context=context("BULLISH"),
        )

    def test_bearish_close_bos_enters_at_close_with_retracement_stop(self):
        result = self.pipeline(self.bearish_setup(close_entry=True))
        entry = result.snapshot["entry"]
        retracement = result.snapshot["retracement"]
        self.assertTrue(entry["ready"])
        self.assertEqual(entry["index"], 15)
        self.assertEqual(entry["price"], 7.0)
        self.assertEqual(entry["trigger_index"], 11)
        self.assertEqual(entry["trigger_level"], 8.0)
        self.assertEqual(entry["pullback_extreme_stop"], 16.0)
        self.assertEqual(entry["setup_invalidation_index"], 7)
        self.assertAlmostEqual(
            entry["stop_loss"],
            14.0
            + 0.15
            * atr_at(
                self.bearish_setup(close_entry=True),
                as_of_index=15,
            ),
        )
        self.assertGreater(
            entry["emergency_broker_stop"],
            entry["logical_stop"],
        )
        self.assertEqual(
            retracement["qualification_available_at_index"], 14
        )
        self.assertEqual(
            retracement["active_failure_trigger_index"], 11
        )

    def test_wick_only_cross_does_not_enter_and_trigger_remains(self):
        result = self.pipeline(self.bearish_setup(close_entry=False))
        entry = result.snapshot["entry"]
        retracement = result.snapshot["retracement"]
        self.assertFalse(entry["ready"])
        self.assertTrue(entry["wick_only_cross"])
        self.assertEqual(entry["trigger_index"], 11)
        self.assertEqual(
            retracement["state"], "WAITING_FOR_CLOSE_BOS"
        )

    def test_bullish_rules_are_an_exact_mirror(self):
        bearish = self.bearish_setup(close_entry=True)
        bullish = bearish.copy()
        bullish["high"] = 30 - bearish["low"]
        bullish["low"] = 30 - bearish["high"]
        bullish["open"] = 30 - bearish["open"]
        bullish["close"] = 30 - bearish["close"]
        result = self.bullish_pipeline(bullish)
        entry = result.snapshot["entry"]
        self.assertTrue(entry["ready"])
        self.assertEqual(entry["type"], "BUY_CLOSE_BOS")
        self.assertEqual(entry["index"], 15)
        self.assertEqual(entry["price"], 23.0)
        self.assertEqual(entry["trigger_level"], 22.0)
        self.assertEqual(entry["pullback_extreme_stop"], 14.0)
        self.assertEqual(entry["setup_invalidation_index"], 7)
        self.assertAlmostEqual(
            entry["stop_loss"],
            16.0 - 0.15 * atr_at(
                bullish,
                as_of_index=15,
            ),
        )
        self.assertLess(
            entry["emergency_broker_stop"],
            entry["logical_stop"],
        )

    def test_raw_confirmed_swing_is_not_a_proven_trail(self):
        data = self.bearish_setup(close_entry=True)
        extension = candles(
            highs=[9, 10, 12, 10, 9, 8, 13],
            lows=[6, 7, 9, 7, 6, 5, 10],
            closes=[7, 8, 10, 8, 7, 6, 13],
        )
        extension["time"] += (len(data) * 300)
        combined = pd.concat([data, extension], ignore_index=True)
        result = self.pipeline(combined)
        management = result.snapshot["trailing_protection"]
        self.assertEqual(
            management["state"], "TRAIL_CANDIDATE_UNPROVEN"
        )
        attempt = management["active_attempt"]
        self.assertEqual(attempt["trail_movements"], [])
        self.assertEqual(
            attempt["current_protection_source"],
            "SETUP_LOGICAL_INVALIDATION",
        )
        self.assertFalse(management["order_api_called"])

    def test_neutral_htf_hard_blocks_every_entry(self):
        data = self.bearish_setup(close_entry=True)
        result = run_pipeline(
            data=data,
            symbol="GER40Cash#",
            timeframe="M5",
            as_of_index=len(data) - 1,
            options=PipelineOptions(
                strategy_model="EXPERT_SPEC_V1",
                engine_sensitivity=3,
            ),
            higher_timeframe_context=context("NEUTRAL"),
        )
        self.assertFalse(result.snapshot["entry"]["ready"])
        self.assertEqual(
            result.snapshot["entry"]["state"], "BLOCKED_HTF_NEUTRAL"
        )

    def test_replay_emits_one_canonical_entry_without_lookahead(self):
        data = self.bearish_setup(close_entry=True)
        result = run_replay(
            data=data,
            symbol="GER40Cash#",
            timeframe="M5",
            options=ReplayOptions(start_index=0, end_index=15),
            pipeline_options=PipelineOptions(
                strategy_model="EXPERT_SPEC_V1",
                engine_sensitivity=3,
            ),
            higher_timeframe_context_provider=(
                lambda index: context("BEARISH")
            ),
        )
        entries = result.ledger.entry_events()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["entry_index"], 15)
        self.assertEqual(result.diagnostics["integrity_failure_count"], 0)
        self.assertFalse(
            any(
                item.diagnostics["order_api_called"]
                for item in result.pipeline_results
            )
        )


if __name__ == "__main__":
    unittest.main()
