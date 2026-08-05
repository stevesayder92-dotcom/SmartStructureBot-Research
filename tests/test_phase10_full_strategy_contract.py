from __future__ import annotations

from pathlib import Path
import unittest

import pandas as pd

from core.adaptive_decision import grade_setup
from core.expert_strategy import confirmed_swings
from core.fibonacci_contract import (
    FibonacciConfig,
    build_fibonacci_contract,
)
from core.m1_fallback import evaluate_m1_fallback
from core.semantic_swing_hierarchy import build_semantic_swing_hierarchy
from core.steve_trade_management import (
    SteveManagementConfig,
    SteveTradeManagementEngine,
    logical_invalidation_decision,
    select_setup_logical_invalidation,
    transition_protection_without_loosening,
)
from tests.test_phase9_steve_management_contract import (
    bullish_entry,
    context,
    frame,
    initial_data,
    trail_data,
    trail_swings,
)


def fib_data() -> pd.DataFrame:
    return frame(
        opens=[101, 102, 107, 113, 118, 119, 116, 114],
        highs=[103, 105, 110, 116, 120, 120, 118, 116],
        lows=[100, 101, 105, 111, 116, 115, 112, 113],
        closes=[102, 104, 109, 115, 119, 116, 114, 115],
    )


def fib_swings() -> list[dict]:
    return [
        {
            "side": "LOW",
            "index": 1,
            "level": 100.0,
            "confirmed_at_index": 2,
        },
        {
            "side": "HIGH",
            "index": 4,
            "level": 120.0,
            "confirmed_at_index": 5,
        },
    ]


def fib_contract(
    *,
    as_of: int = 7,
    config: FibonacciConfig | None = None,
) -> dict:
    return build_fibonacci_contract(
        data=fib_data(),
        direction="BULLISH",
        anchor=fib_swings()[1],
        swings=fib_swings(),
        as_of_index=as_of,
        config=config,
    )


def reentry_fixture():
    closes = [92, 98, 101, 88, 89, 91, 96, 97, 101, 80]
    opens = [92, 97, 100, 94, 88, 90, 95, 96, 99, 95]
    data = frame(
        opens=opens,
        highs=[max(o, c) + 1 for o, c in zip(opens, closes)],
        lows=[min(o, c) - 1 for o, c in zip(opens, closes)],
        closes=closes,
    )
    swings = [
        {
            "side": "LOW",
            "classification": "LL",
            "index": 4,
            "level": 87.0,
            "confirmed_at_index": 5,
        },
        {
            "side": "HIGH",
            "classification": "HH",
            "index": 6,
            "level": 97.0,
            "confirmed_at_index": 7,
        },
    ]
    return data, swings


class Phase10FullStrategyContractTest(unittest.TestCase):
    # 1
    def test_01_fibonacci_anchors_are_directionally_correct(self):
        bullish = fib_contract()
        bearish_data = fib_data().copy()
        bearish_data[["open", "high", "low", "close"]] = (
            250 - fib_data()[["open", "low", "high", "close"]]
        ).to_numpy()
        bearish_swings = [
            {
                "side": "HIGH",
                "index": 1,
                "level": 150.0,
                "confirmed_at_index": 2,
            },
            {
                "side": "LOW",
                "index": 4,
                "level": 130.0,
                "confirmed_at_index": 5,
            },
        ]
        bearish = build_fibonacci_contract(
            data=bearish_data,
            direction="BEARISH",
            anchor=bearish_swings[1],
            swings=bearish_swings,
            as_of_index=7,
        )
        self.assertLess(
            bullish["zero_anchor_price"], bullish["hundred_anchor_price"]
        )
        self.assertGreater(
            bearish["zero_anchor_price"], bearish["hundred_anchor_price"]
        )
        self.assertEqual(
            bullish["zero_anchor_role"],
            "FULL_STRUCTURE_RETEST_ORIGIN",
        )
        self.assertEqual(
            bullish["hundred_anchor_role"],
            "RETRACEMENT_START_IMPULSE_EXTREME",
        )

    # 2
    def test_02_fibonacci_depth_is_causal(self):
        original = fib_contract(as_of=6)
        changed = fib_data()
        changed.loc[7, "low"] = 50.0
        replayed = build_fibonacci_contract(
            data=changed,
            direction="BULLISH",
            anchor=fib_swings()[1],
            swings=fib_swings(),
            as_of_index=6,
        )
        self.assertEqual(original["depth"], replayed["depth"])
        self.assertTrue(original["causal_valid"])

    # 3
    def test_03_fibonacci_minimum_is_configurable(self):
        contract = fib_contract(
            config=FibonacciConfig(
                minimum_relevant_depth=0.45,
                primary_minimum=0.50,
                primary_maximum=0.70,
                deep_maximum=0.85,
            )
        )
        self.assertFalse(contract["minimum_relevant_reached"])

    # 4
    def test_04_sweet_spot_bos_receives_high_relevance(self):
        decision = grade_setup(
            hard_blockers=[],
            htf_context={"available": True, "state": "STRONG_ALIGNED_BULLISH"},
            fibonacci=fib_contract(),
            structure_clear=True,
            bos_body_atr=1.0,
        )
        self.assertIn(decision["grade"], {"A_PLUS", "A"})
        self.assertIn(
            "38_2_TO_61_8_REMAINING",
            decision["positive_factors"],
        )

    # 5
    def test_05_shallow_strong_bos_remains_tradable(self):
        shallow = {**fib_contract(), "zone": "SHALLOW", "depth": 0.18}
        decision = grade_setup(
            hard_blockers=[],
            htf_context={"available": True, "state": "ALIGNED_BULLISH"},
            fibonacci=shallow,
            structure_clear=True,
            bos_body_atr=1.1,
        )
        self.assertTrue(decision["allowed"])
        self.assertFalse(decision["soft_factors_eliminated_setup"])

    # 6
    def test_06_deep_retracement_valid_while_protection_holds(self):
        deep = {**fib_contract(), "zone": "DEEP_BUT_VALID", "depth": 0.72}
        decision = grade_setup(
            hard_blockers=[],
            htf_context={"available": True, "state": "ALIGNED_BULLISH"},
            fibonacci=deep,
            structure_clear=True,
            bos_body_atr=0.5,
        )
        self.assertTrue(decision["allowed"])
        self.assertIn("DEEP_BUT_VALID", decision["positive_factors"])

    # 7
    def test_07_first_failure_leaves_parent_retracement_active(self):
        data, swings = reentry_fixture()
        result = SteveTradeManagementEngine().evaluate(
            data=data,
            symbol="GER40Cash#",
            timeframe="M5",
            as_of_index=3,
            direction="BULLISH",
            context=context(),
            confirmed_swings=swings,
            canonical_entry=bullish_entry(),
        )
        self.assertTrue(result["parent_retracement_active"])
        self.assertTrue(result["reentry_monitoring"])

    # 8
    def test_08_early_failure_does_not_automatically_invalidate_parent(self):
        data, swings = reentry_fixture()
        result = SteveTradeManagementEngine().evaluate(
            data=data,
            symbol="GER40Cash#",
            timeframe="M5",
            as_of_index=3,
            direction="BULLISH",
            context=context(),
            confirmed_swings=swings,
            canonical_entry=bullish_entry(),
        )
        self.assertFalse(result["parent_setup_closed"])
        self.assertEqual(
            result["reentry_state"], "FIRST_ENTRY_FAILED_RETRACEMENT_ACTIVE"
        )

    # 9
    def test_09_fresh_relevant_bos_allows_one_reentry(self):
        data, swings = reentry_fixture()
        result = SteveTradeManagementEngine().evaluate(
            data=data,
            symbol="GER40Cash#",
            timeframe="M5",
            as_of_index=8,
            direction="BULLISH",
            context=context(),
            confirmed_swings=swings,
            canonical_entry=bullish_entry(),
        )
        self.assertEqual(result["reentry_count"], 1)
        self.assertEqual(result["attempt_count"], 2)
        self.assertEqual(result["reentry_capability_remaining"], 0)

    # 10
    def test_10_reentry_requires_no_new_major_setup(self):
        data, swings = reentry_fixture()
        result = SteveTradeManagementEngine().evaluate(
            data=data,
            symbol="GER40Cash#",
            timeframe="M5",
            as_of_index=8,
            direction="BULLISH",
            context=context(),
            confirmed_swings=swings,
            canonical_entry=bullish_entry(),
        )
        self.assertEqual(
            {attempt["setup_id"] for attempt in result["attempts"]},
            {"PARENT-BULL-1"},
        )

    # 11
    def test_11_reentry_same_parent_separate_event_id(self):
        data, swings = reentry_fixture()
        result = SteveTradeManagementEngine().evaluate(
            data=data,
            symbol="GER40Cash#",
            timeframe="M5",
            as_of_index=8,
            direction="BULLISH",
            context=context(),
            confirmed_swings=swings,
            canonical_entry=bullish_entry(),
        )
        first, second = result["attempts"]
        self.assertEqual(first["setup_id"], second["setup_id"])
        self.assertNotEqual(first["event_id"], second["event_id"])

    # 12
    def test_12_dominant_protection_failure_blocks_reentry(self):
        data, swings = reentry_fixture()
        result = SteveTradeManagementEngine().evaluate(
            data=data,
            symbol="GER40Cash#",
            timeframe="M5",
            as_of_index=4,
            direction="BULLISH",
            context=context(level=95.0),
            confirmed_swings=swings,
            canonical_entry=bullish_entry(),
        )
        self.assertEqual(
            result["reentry_state"],
            "REENTRY_REJECTED_DOMINANT_PROTECTION_FAILED",
        )
        self.assertEqual(result["reentry_count"], 0)

    # 13
    def test_13_second_failure_closes_parent(self):
        data, swings = reentry_fixture()
        result = SteveTradeManagementEngine().evaluate(
            data=data,
            symbol="GER40Cash#",
            timeframe="M5",
            as_of_index=9,
            direction="BULLISH",
            context=context(),
            confirmed_swings=swings,
            canonical_entry=bullish_entry(),
        )
        self.assertTrue(result["parent_setup_closed"])
        self.assertEqual(result["reentry_state"], "CLOSED_AFTER_SECOND_FAILURE")

    # 14
    def test_14_soft_filters_reduce_risk_instead_of_blocking(self):
        decision = grade_setup(
            hard_blockers=[],
            htf_context={
                "available": True,
                "state": "MIXED_BUT_USABLE_BULLISH",
                "risk_modifier": 0.5,
            },
            fibonacci={"available": True, "zone": "SHALLOW"},
            structure_clear=False,
            bos_body_atr=0.2,
        )
        self.assertTrue(decision["allowed"])
        self.assertGreater(decision["risk_modifier"], 0)
        self.assertLess(decision["risk_modifier"], 1)

    # 15
    def test_15_m1_fallback_requires_valid_m5_context(self):
        m1 = fib_data()
        result = evaluate_m1_fallback(
            m5_snapshot={
                "context": {"approved_direction": "NEUTRAL"},
                "market": {"trend": "NEUTRAL"},
                "retracement": {"qualified": True},
                "entry": {"ready": False},
                "setup": {"setup_id": "PARENT"},
            },
            m1_data=m1,
            symbol="GOLD#",
            m1_as_of_index=len(m1) - 1,
            higher_timeframe_context={"approved_direction": "NEUTRAL"},
        )
        self.assertFalse(result["entry_ready"])

    # 16
    def test_16_m1_to_m5_transition_never_loosens(self):
        result = transition_protection_without_loosening(
            direction="BULLISH",
            current_level=100.0,
            candidate_m5_level=98.0,
        )
        self.assertEqual(result["selected_level"], 100.0)
        self.assertFalse(result["loosened"])

    # 17
    def test_17_raw_fractal_is_not_automatically_meaningful(self):
        data = fib_data()
        hierarchy = build_semantic_swing_hierarchy(
            data=data,
            swings=[
                {
                    "side": "HIGH",
                    "index": 3,
                    "level": 110.0,
                    "confirmed_at_index": 6,
                },
                {
                    "side": "LOW",
                    "index": 4,
                    "level": 109.99,
                    "confirmed_at_index": 7,
                },
            ],
            direction="BULLISH",
            as_of_index=7,
        )
        self.assertEqual(
            hierarchy["points"][1]["semantic_role"], "MICRO_NOISE"
        )

    # 18
    def test_18_trail_requires_meaningful_continuation_proof(self):
        result = SteveTradeManagementEngine().evaluate(
            data=trail_data(),
            symbol="GER40Cash#",
            timeframe="M5",
            as_of_index=9,
            direction="BULLISH",
            context=context(),
            confirmed_swings=trail_swings(),
            canonical_entry=bullish_entry(),
        )
        self.assertEqual(result["state"], "TRAIL_CANDIDATE_UNPROVEN")
        self.assertEqual(result["active_attempt"]["trail_movements"], [])

    # 19
    def test_19_tp1_touch_does_not_automatically_force_break_even(self):
        config = SteveManagementConfig(
            tp1_model="CONFIGURABLE_R",
            configurable_r_target=0.05,
        )
        result = SteveTradeManagementEngine(config=config).evaluate(
            data=initial_data(),
            symbol="GER40Cash#",
            timeframe="M5",
            as_of_index=3,
            direction="BULLISH",
            context=context(),
            confirmed_swings=[],
            canonical_entry=bullish_entry(),
        )
        attempt = result["active_attempt"]
        self.assertTrue(attempt["tp1_triggered"])
        self.assertNotEqual(
            attempt["current_protection"], attempt["entry_price"]
        )

    # 20
    def test_20_opposing_meaningful_bos_exits(self):
        result = SteveTradeManagementEngine().evaluate(
            data=trail_data(),
            symbol="GER40Cash#",
            timeframe="M5",
            as_of_index=11,
            direction="BULLISH",
            context=context(),
            confirmed_swings=trail_swings(),
            canonical_entry=bullish_entry(),
        )
        self.assertEqual(
            result["latest_attempt"]["exit_reason"],
            "OPPOSING_MEANINGFUL_BOS",
        )

    # 21
    def test_21_wick_only_logical_stop_survives(self):
        contract = select_setup_logical_invalidation(
            data=initial_data(),
            entry_model=bullish_entry(),
            timeframe="M5",
            config=SteveManagementConfig(),
        )
        boundary = contract["logical_boundary"]
        row = pd.Series(
            {
                "open": boundary + 1.0,
                "high": boundary + 2.0,
                "low": boundary - 1.0,
                "close": boundary + 0.5,
            }
        )
        decision = logical_invalidation_decision(
            row=row,
            direction="BULLISH",
            timeframe="M5",
            contract=contract,
            config=SteveManagementConfig(),
        )
        self.assertFalse(decision["invalidated"])
        self.assertTrue(decision["wick_only_survived"])

    # 22
    def test_22_body_close_invalidation_exits(self):
        contract = select_setup_logical_invalidation(
            data=initial_data(),
            entry_model=bullish_entry(),
            timeframe="M1",
            config=SteveManagementConfig(),
        )
        boundary = contract["logical_boundary"]
        decision = logical_invalidation_decision(
            row=pd.Series(
                {
                    "open": boundary + 1.0,
                    "high": boundary + 1.2,
                    "low": boundary - 1.2,
                    "close": boundary - 0.5,
                }
            ),
            direction="BULLISH",
            timeframe="M1",
            contract=contract,
            config=SteveManagementConfig(),
        )
        self.assertTrue(decision["invalidated"])

    # 23
    def test_23_no_future_data_changes_confirmed_history(self):
        data = fib_data()
        at_seven = confirmed_swings(data, as_of_index=7, sensitivity=2)
        future = pd.concat(
            [
                data,
                frame(
                    opens=[200],
                    highs=[220],
                    lows=[10],
                    closes=[210],
                ),
            ],
            ignore_index=True,
        )
        later = confirmed_swings(future, as_of_index=7, sensitivity=2)
        self.assertEqual(at_seven, later)

    # 24
    def test_24_no_stale_trigger_entry(self):
        data, swings = reentry_fixture()
        result = SteveTradeManagementEngine().evaluate(
            data=data,
            symbol="GER40Cash#",
            timeframe="M5",
            as_of_index=7,
            direction="BULLISH",
            context=context(),
            confirmed_swings=swings,
            canonical_entry=bullish_entry(),
        )
        self.assertIsNone(result["reentry_signal"])
        self.assertEqual(result["reentry_count"], 0)

    # 25
    def test_25_no_order_apis(self):
        project = Path(__file__).resolve().parents[1]
        runtime_text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in [project / "main.py", *sorted((project / "core").glob("*.py"))]
        )
        self.assertNotIn("order_send(", runtime_text)
        self.assertNotIn("TRADE_ACTION_DEAL", runtime_text)


if __name__ == "__main__":
    unittest.main()
