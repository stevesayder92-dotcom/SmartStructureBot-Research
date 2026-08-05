from __future__ import annotations

import unittest

import pandas as pd

from core.steve_trade_management import (
    SteveTradeManagementEngine,
    select_last_important_pre_bos_swing,
)


def candles(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "time": index * 300,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "tick_volume": 100,
            }
            for index, (open_price, high, low, close) in enumerate(rows)
        ]
    )


class Phase101FeedbackContractTests(unittest.TestCase):
    def test_sell_stop_uses_last_reaction_high_proved_by_entry_bos(self):
        data = candles(
            [
                (110, 112, 108, 109),
                (109, 110, 105, 106),
                (106, 107, 100, 101),
                (101, 106, 100, 105),
                (105, 109, 103, 108),
                (108, 108.5, 101, 102),
                (102, 103, 97, 98),
                (98, 120, 96, 119),
            ]
        )
        selected = select_last_important_pre_bos_swing(
            swings=[
                {
                    "side": "HIGH",
                    "index": 0,
                    "level": 112,
                    "confirmed_at_index": 2,
                }
            ],
            direction="BEARISH",
            trigger_index=2,
            entry_index=6,
            data=data,
            setup_start_index=0,
        )
        self.assertEqual(selected["index"], 4)
        self.assertEqual(selected["level"], 109)
        self.assertEqual(selected["confirmed_at_index"], 6)
        self.assertEqual(
            selected["confirmation_method"],
            "CAUSAL_ENTRY_BOS_PROOF_NO_FUTURE_CANDLES",
        )

    def test_buy_stop_uses_last_reaction_low_proved_by_entry_bos(self):
        data = candles(
            [
                (90, 92, 88, 91),
                (91, 95, 90, 94),
                (94, 100, 93, 99),
                (99, 100, 94, 95),
                (95, 97, 91, 92),
                (92, 99, 92, 98),
                (98, 104, 97, 103),
            ]
        )
        selected = select_last_important_pre_bos_swing(
            swings=[],
            direction="BULLISH",
            trigger_index=2,
            entry_index=6,
            data=data,
            setup_start_index=0,
        )
        self.assertEqual(selected["index"], 4)
        self.assertEqual(selected["level"], 91)
        self.assertEqual(selected["confirmed_at_index"], 6)

    def test_no_opposing_reaction_uses_causal_confirmed_fallback(self):
        data = candles(
            [
                (110, 112, 108, 109),
                (109, 110, 105, 106),
                (106, 107, 100, 101),
                (101, 102, 98, 99),
                (99, 100, 96, 97),
            ]
        )
        fallback = {
            "side": "HIGH",
            "index": 0,
            "level": 112,
            "confirmed_at_index": 2,
        }
        selected = select_last_important_pre_bos_swing(
            swings=[fallback],
            direction="BEARISH",
            trigger_index=2,
            entry_index=4,
            data=data,
            setup_start_index=0,
            fallback=fallback,
        )
        self.assertEqual(selected["index"], 0)
        self.assertEqual(
            selected["selection_scope"],
            "LATEST_CONFIRMED_INSIDE_QUALIFIED_RETRACEMENT",
        )

    def test_previous_impulse_tp1_is_triggered_by_wick_touch(self):
        data = candles(
            [
                (98, 100, 95, 99),
                (99, 101, 99, 100),
                (100, 110, 99, 101),
            ]
        )
        structure = {
            "side": "LOW",
            "index": 0,
            "level": 95,
            "confirmed_at_index": 0,
        }
        entry = {
            "ready": True,
            "setup_id": "TEST|BULLISH|PB_0",
            "direction": "BULLISH",
            "entry_index": 1,
            "entry_price": 100,
            "counter": structure,
            "logical_stop_structure": structure,
            "trigger": {
                "side": "HIGH",
                "index": 0,
                "level": 100,
                "confirmed_at_index": 0,
            },
            "anchor": {"side": "HIGH", "index": 0, "level": 110},
            "stop_level": 95,
        }
        context = {
            "frames": {
                "H1": {
                    "last_confirmed_low": {
                        "index": 0,
                        "level": 90,
                        "confirmed_at_index": 0,
                    }
                },
                "M30": {},
                "M15": {},
            }
        }
        result = SteveTradeManagementEngine().evaluate(
            data=data,
            symbol="TEST#",
            timeframe="M5",
            as_of_index=2,
            direction="BULLISH",
            context=context,
            confirmed_swings=[],
            canonical_entry=entry,
        )
        attempt = result["active_attempt"]
        self.assertEqual(attempt["position_1_target"], 110)
        self.assertEqual(
            attempt["position_1_target_source"],
            "ENTRY_IMPULSE",
        )
        self.assertTrue(attempt["tp1_triggered"])
        self.assertEqual(
            attempt["history"][-1]["event"],
            "TP1_TRIGGERED_RESEARCH",
        )


if __name__ == "__main__":
    unittest.main()
