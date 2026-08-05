from __future__ import annotations

import unittest

import pandas as pd

from core.fibonacci_contract import (
    FIBONACCI_MODEL,
    build_fibonacci_contract,
    classify_remaining,
)
from core.final_fidelity_management import (
    advance_target_lifecycle,
    build_target_hierarchy,
    profit_capture_metrics,
    simulate_profit_management,
    transition_m1_to_m5_management,
)
from core.synchronized_m1_replay import (
    M1_STOP_TERMINOLOGY,
    ParentEntryLifecycle,
    arbitrate_first_valid_entry,
    build_closed_candle_timeline,
    find_m1_child_entry,
    validate_m1_ownership,
)


def candle_frame(rows):
    return pd.DataFrame(
        rows,
        columns=("time", "open", "high", "low", "close"),
    )


def bullish_fibonacci():
    data = candle_frame(
        [
            (0, 100, 101, 99, 100),
            (300, 100, 101, 99, 100),
            (600, 101, 111, 100, 110),
            (900, 110, 110, 107, 108),
            (1200, 108, 109, 104, 105),
            (1500, 105, 107, 103, 106),
        ]
    )
    swings = [
        {
            "side": "LOW",
            "index": 1,
            "level": 100,
            "confirmed_at_index": 2,
        },
        {
            "side": "HIGH",
            "index": 2,
            "level": 110,
            "confirmed_at_index": 3,
        },
    ]
    return build_fibonacci_contract(
        data=data,
        direction="BULLISH",
        anchor=swings[1],
        swings=swings,
        as_of_index=5,
    )


def parent_contract():
    return {
        "parent_m5_setup_id": "EURUSD#|M5|SETUP|1",
        "parent_m5_retracement_id": "EURUSD#|M5|SETUP|1|RETRACE",
        "parent_impulse_cycle_id": "EURUSD#|M5|IMPULSE|1",
        "parent_direction": "BULLISH",
        "parent_protected_structure_id": "EURUSD#|M5|PROTECT|1",
        "parent_fib_anchor_version": "M5_PARENT_IMPULSE_ANCHORS_V2",
        "armed_time": 60.0,
        "active_time": 180.0,
        "m5_entry_time": 600.0,
        "m5_entry_index": 1,
        "m5_entry_price": 102.0,
        "m5_logical_stop": 98.0,
        "m5_emergency_stop": 97.0,
        "price_boundary_low": 95.0,
        "price_boundary_high": 105.0,
        "dominant_protection_intact": True,
        "fibonacci_zone": "STEVE_PRIMARY_DEEP_SWEET_SPOT",
        "fib_hundred_price": 105.0,
    }


def m1_sequence():
    return candle_frame(
        [
            (0, 100.0, 100.5, 99.5, 100.0),
            (60, 100.0, 102.0, 99.8, 101.5),
            (120, 100.5, 100.8, 99.0, 99.4),
            (180, 99.2, 99.6, 98.5, 98.8),
            (240, 98.8, 99.2, 98.0, 98.5),
            (300, 99.0, 100.4, 98.8, 100.0),
            (360, 100.0, 101.0, 99.7, 100.5),
            (420, 100.2, 100.8, 99.9, 100.5),
            (480, 100.5, 101.8, 100.3, 101.5),
            (540, 101.5, 101.9, 101.2, 101.7),
        ]
    )


class FinalFidelityContractTest(unittest.TestCase):
    def test_fibonacci_zero_is_origin_and_hundred_is_extreme(self):
        fib = bullish_fibonacci()
        self.assertEqual(FIBONACCI_MODEL, "STEVE_REMAINING_IMPULSE_PERCENT_V2")
        self.assertEqual(fib["fib_zero_price"], 100)
        self.assertEqual(fib["fib_hundred_price"], 110)
        self.assertEqual(fib["fib_zero_role"], "FULL_STRUCTURE_RETEST_ORIGIN")
        self.assertEqual(
            fib["fib_hundred_role"],
            "RETRACEMENT_START_IMPULSE_EXTREME",
        )

    def test_fibonacci_remaining_and_depth_are_complements(self):
        fib = bullish_fibonacci()
        self.assertAlmostEqual(
            fib["remaining_impulse_ratio"]
            + fib["retracement_depth_ratio"],
            1.0,
        )
        self.assertAlmostEqual(fib["remaining_impulse_ratio"], 0.3)
        self.assertAlmostEqual(fib["retracement_depth_ratio"], 0.7)
        self.assertEqual(
            fib["zone"],
            "STEVE_PRIMARY_DEEP_SWEET_SPOT",
        )
        self.assertEqual(
            classify_remaining(0.236),
            "STEVE_PRIMARY_DEEP_SWEET_SPOT",
        )
        self.assertEqual(
            classify_remaining(0.382),
            "STEVE_PRIMARY_DEEP_SWEET_SPOT",
        )

    def test_raw_fibonacci_breach_is_not_hidden_by_display_clamp(self):
        fib = bullish_fibonacci()
        self.assertLessEqual(
            fib["display_remaining_impulse_percent"],
            100,
        )
        self.assertIn("dominant_origin_breached", fib)

    def test_unrelated_m1_parent_is_hard_rejected(self):
        parent = parent_contract()
        child = {
            field: parent[field]
            for field in (
                "parent_m5_setup_id",
                "parent_m5_retracement_id",
                "parent_impulse_cycle_id",
                "parent_direction",
                "parent_protected_structure_id",
                "parent_fib_anchor_version",
            )
        }
        child["parent_m5_retracement_id"] = "OTHER"
        result = validate_m1_ownership(parent=parent, child=child)
        self.assertFalse(result["matched"])
        self.assertTrue(result["hard_block"])

    def test_synchronized_timeline_never_exposes_unfinished_candles(self):
        m1 = m1_sequence()
        m5 = candle_frame(
            [
                (0, 100, 102, 99, 101),
                (300, 101, 103, 100, 102),
            ]
        )
        timeline = build_closed_candle_timeline(
            m5_data=m5,
            m1_data=m1,
        )
        self.assertTrue(all(row["causal_valid"] for row in timeline))
        self.assertFalse(any(row["unfinished_m5_visible"] for row in timeline))
        self.assertFalse(any(row["future_m1_visible_to_m5"] for row in timeline))
        at_300 = next(row for row in timeline if row["event_time"] == 300)
        self.assertEqual(
            at_300["processing_order"],
            ["M5_PARENT_UPDATE", "M1_CHILD_UPDATE", "M5_FALLBACK"],
        )

    def test_valid_m1_entry_uses_relevant_swing_body_edge(self):
        result = find_m1_child_entry(
            parent=parent_contract(),
            m1_data=m1_sequence(),
            sensitivity=1,
        )
        self.assertTrue(result["entry_ready"])
        entry = result["entry"]
        self.assertEqual(
            entry["logical_stop_terminology"],
            M1_STOP_TERMINOLOGY,
        )
        self.assertEqual(entry["logical_stop"], 98.5)
        self.assertTrue(entry["logical_stop"] < entry["entry_price"])
        self.assertFalse(entry["wick_only_bos"])

    def test_first_valid_m1_consumes_and_blocks_later_m5(self):
        m1 = find_m1_child_entry(
            parent=parent_contract(),
            m1_data=m1_sequence(),
            sensitivity=1,
        )
        decision = arbitrate_first_valid_entry(
            parent=parent_contract(),
            m1_result=m1,
        )
        self.assertEqual(decision["entry_owner"], "M1")
        self.assertTrue(decision["duplicate_m5_entry_blocked"])
        self.assertTrue(decision["m5_entry_avoided_due_to_prior_m1"])

    def test_m5_fallback_closes_m1_gate_when_no_child_entry(self):
        result = arbitrate_first_valid_entry(
            parent=parent_contract(),
            m1_result={
                "entry_ready": False,
                "entry": None,
                "m1_was_monitored": True,
                "rejections": [],
            },
        )
        self.assertEqual(result["entry_owner"], "M5")
        self.assertTrue(result["m1_gate_closed"])
        self.assertLess(
            result["entry"]["emergency_stop"],
            result["entry"]["logical_stop"],
        )

    def test_m1_to_m5_transition_never_widens(self):
        rejected = transition_m1_to_m5_management(
            direction="BULLISH",
            current_m1_protection=100,
            proposed_m5_protection=99,
            proof_index=10,
            proof_reason="M5_BOS",
        )
        self.assertEqual(
            rejected["management_state"],
            "TRANSITION_REJECTED_WOULD_LOOSEN",
        )
        self.assertEqual(rejected["selected_level"], 100)
        accepted = transition_m1_to_m5_management(
            direction="BULLISH",
            current_m1_protection=100,
            proposed_m5_protection=101,
            proof_index=11,
            proof_reason="M5_BOS",
        )
        self.assertEqual(accepted["selected_level"], 101)

    def test_one_reentry_per_parent_and_protection_failure_blocks(self):
        lifecycle = ParentEntryLifecycle("SETUP")
        self.assertTrue(lifecycle.claim(timeframe="M1", event_time=1))
        self.assertTrue(
            lifecycle.fail_first_attempt(
                dominant_protection_intact=True,
                parent_retracement_valid=True,
            )
        )
        self.assertTrue(lifecycle.claim_reentry(timeframe="M5", event_time=2))
        self.assertFalse(lifecycle.claim_reentry(timeframe="M1", event_time=3))
        failed = ParentEntryLifecycle("FAILED")
        failed.claim(timeframe="M5", event_time=1)
        self.assertFalse(
            failed.fail_first_attempt(
                dominant_protection_intact=False,
                parent_retracement_valid=True,
            )
        )

    def test_target_wick_close_acceptance_and_rejection_are_distinct(self):
        target = {
            "price": 110.0,
            "state": "CREATED",
            "target_id": "TP1",
        }
        wick = advance_target_lifecycle(
            target=target,
            direction="BULLISH",
            candle={"open": 109, "high": 111, "low": 108, "close": 109.5},
        )
        close = advance_target_lifecycle(
            target=target,
            direction="BULLISH",
            candle={"open": 109, "high": 111, "low": 108, "close": 110.5},
        )
        accepted = advance_target_lifecycle(
            target=target,
            direction="BULLISH",
            candle={"open": 110, "high": 112, "low": 109, "close": 111},
            prior_closes_beyond=1,
        )
        self.assertEqual(wick["state"], "WICK_TOUCHED")
        self.assertEqual(close["state"], "BODY_CLOSED_THROUGH")
        self.assertEqual(accepted["state"], "ACCEPTED_BEYOND")
        self.assertNotEqual(wick["state"], close["state"])

    def test_target_hierarchy_rejects_wrong_side_objective(self):
        hierarchy = build_target_hierarchy(
            direction="BULLISH",
            entry_price=100,
            logical_stop=98,
            previous_impulse_extreme=105,
            external_objectives=[
                {"price": 95, "source": "HTF_SWING"},
                {"price": 110, "source": "EXTERNAL_LIQUIDITY"},
            ],
        )
        self.assertEqual(hierarchy["tp1"]["price"], 105)
        self.assertNotIn(95, [row["price"] for row in hierarchy["candidates"]])

    def test_target_rejection_after_acceptance_exits_runner(self):
        candles = candle_frame(
            [
                (0, 100, 103, 99, 102),
                (60, 102, 104, 101, 103),
                (120, 103, 103.5, 100, 100.5),
                (180, 100.5, 101, 99, 100),
            ]
        )
        managed = simulate_profit_management(
            direction="BULLISH",
            entry_price=100,
            initial_stop=98,
            candles=candles,
            tp1_target=102,
            target_events=[
                {"state": "BODY_CLOSED_THROUGH", "index": 0},
                {"state": "ACCEPTED_BEYOND", "index": 1},
                {"state": "REJECTED", "index": 2},
            ],
        )
        self.assertEqual(
            managed["exit_reason"],
            "TP1_ACCEPTANCE_REJECTED_RUNNER_EXIT",
        )
        self.assertEqual(managed["exit_index"], 2)
        self.assertTrue(managed["tp1_partial_filled"])

    def test_tp1_touch_does_not_force_break_even(self):
        candles = candle_frame(
            [
                (0, 100, 102.5, 99, 101),
                (60, 101, 101.5, 98.5, 99),
            ]
        )
        managed = simulate_profit_management(
            direction="BULLISH",
            entry_price=100,
            initial_stop=98,
            candles=candles,
            tp1_target=102,
        )
        partial = next(
            event
            for event in managed["history"]
            if event["state"] == "TP1_PARTIAL_FILLED"
        )
        self.assertFalse(partial["break_even_forced"])
        self.assertEqual(managed["final_protection"], 98)

    def test_emergency_broker_stop_caps_catastrophic_wick(self):
        candles = candle_frame(
            [
                (0, 100, 101, 95, 99),
                (60, 99, 100, 98, 99.5),
            ]
        )
        managed = simulate_profit_management(
            direction="BULLISH",
            entry_price=100,
            initial_stop=98,
            emergency_stop=96,
            candles=candles,
            tp1_target=104,
        )
        self.assertEqual(
            managed["exit_reason"],
            "EMERGENCY_BROKER_STOP_HIT",
        )
        self.assertEqual(managed["exit_price"], 96)
        self.assertEqual(managed["exit_index"], 0)

    def test_profit_capture_metrics_are_exact(self):
        candles = candle_frame(
            [
                (0, 100, 104, 99, 103),
                (60, 103, 106, 102, 105),
                (120, 105, 105, 102, 103),
            ]
        )
        metrics = profit_capture_metrics(
            direction="BULLISH",
            entry_price=100,
            initial_stop=98,
            candles=candles,
            exit_price=103,
        )
        self.assertEqual(metrics["initial_risk"], 2)
        self.assertEqual(metrics["MFE"], 6)
        self.assertEqual(metrics["MAE"], 1)
        self.assertEqual(metrics["peak_R"], 3)
        self.assertEqual(metrics["final_R"], 1.5)
        self.assertEqual(metrics["giveback_R"], 1.5)
        self.assertEqual(metrics["capture_ratio"], 0.5)

    def test_replay_contract_is_reproducible_and_research_only(self):
        first = find_m1_child_entry(
            parent=parent_contract(),
            m1_data=m1_sequence(),
            sensitivity=1,
        )
        second = find_m1_child_entry(
            parent=parent_contract(),
            m1_data=m1_sequence(),
            sensitivity=1,
        )
        self.assertEqual(first, second)
        self.assertFalse(first["future_data_used"])
        self.assertFalse(first["order_api_called"])


if __name__ == "__main__":
    unittest.main()
