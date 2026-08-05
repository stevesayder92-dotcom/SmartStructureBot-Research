from __future__ import annotations

import unittest

import pandas as pd

from core.fidelity_patch import (
    ContinuationQualityEngine,
    DEFAULT_PATCH_CONFIG,
    ExhaustionEngine,
    GivebackControlEngine,
    M1EntryQualityEngine,
    TradeManagementCoordinator,
    classify_m1_outcome,
    count_trade_identity,
    simulate_patched_profit_management,
)


def frame(rows):
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close"])


class FinalFidelityPatchV1Test(unittest.TestCase):
    def setUp(self):
        self.parent = {
            "parent_direction": "BULLISH",
            "fibonacci_zone": "STEVE_PRIMARY_DEEP_SWEET_SPOT",
            "m5_entry_time": 1800.0,
            "m5_entry_price": 106.0,
            "m5_logical_stop": 98.0,
            "fib_hundred_price": 110.0,
        }
        self.clean = frame([
            (0, 103.0, 103.3, 102.7, 102.8),
            (60, 102.8, 102.9, 102.0, 102.2),
            (120, 102.2, 102.4, 101.4, 101.6),
            (180, 101.6, 102.0, 101.3, 101.9),
            (240, 101.9, 102.4, 101.8, 102.3),
            (300, 102.3, 104.3, 102.2, 104.1),
        ])

    def quality(self, data=None, entry_index=5):
        data = data if data is not None else self.clean
        return M1EntryQualityEngine().evaluate(
            data=data, parent=self.parent, initial_index=0,
            counter_index=2, trigger_index=4, trigger_available_index=4,
            entry_index=entry_index, trigger_level=102.4,
            entry_price=float(data.iloc[entry_index]["close"]),
            logical_stop=101.6, local_atr=1.0, internal_swings=5,
            overlap_ratio=0.20,
        )

    def test_quality_breakdown_is_deterministic_and_sums_to_score(self):
        first = self.quality()
        second = self.quality()
        self.assertEqual(first, second)
        self.assertAlmostEqual(sum(first["component_scores"].values()), first["m1_quality_score"])
        self.assertTrue(first["structurally_valid"])

    def test_clean_bos_scores_above_wick_heavy_noise(self):
        clean = self.quality()
        noisy = self.clean.copy()
        noisy.loc[5, ["open", "high", "low", "close"]] = [102.39, 104.3, 102.2, 102.41]
        weak = self.quality(noisy)
        self.assertGreater(clean["m1_quality_score"], weak["m1_quality_score"])
        self.assertGreater(clean["component_scores"]["bos_quality"], weak["component_scores"]["bos_quality"])

    def test_stale_trigger_is_penalized_without_rewriting_structure(self):
        data = pd.concat([self.clean.iloc[:5], pd.concat([self.clean.iloc[[4]]]*31, ignore_index=True), self.clean.iloc[[5]]], ignore_index=True)
        data["time"] = range(0, len(data)*60, 60)
        stale = M1EntryQualityEngine().evaluate(
            data=data, parent={**self.parent, "m5_entry_time": 5000},
            initial_index=0, counter_index=2, trigger_index=4,
            trigger_available_index=4, entry_index=len(data)-1,
            trigger_level=102.4, entry_price=float(data.iloc[-1]["close"]),
            logical_stop=101.6, local_atr=1.0, internal_swings=5,
            overlap_ratio=0.20,
        )
        fresh = self.quality()
        self.assertLess(stale["component_scores"]["trigger_significance"], fresh["component_scores"]["trigger_significance"])
        self.assertTrue(stale["structurally_valid"])

    def test_m1_outcome_does_not_call_every_loss_false(self):
        result = classify_m1_outcome(structurally_valid=True, m5_later_confirmed=True, failed_quickly=True, trigger_significant=True, counter_move_active=False, meaningful_advantage=False, saved_move=False)
        self.assertEqual(result, "M1_VALID_NORMAL_LOSS")

    def test_continuation_hysteresis_rejects_one_candle_oscillation(self):
        engine = ContinuationQualityEngine()
        strong = frame([(0,100,101,99.8,100.8),(60,100.8,102,100.7,101.8),(120,101.8,103,101.7,102.8)])
        a = engine.evaluate(direction="BULLISH", entry_price=100, initial_risk=2, candles=strong, current_protection=98)
        weak_one = pd.concat([strong, frame([(180,102.8,102.9,102.3,102.5)])], ignore_index=True)
        b = engine.evaluate(direction="BULLISH", entry_price=100, initial_risk=2, candles=weak_one, current_protection=98, previous_state=a["state"], pending_state_count=0)
        if b["raw_state"] != a["state"]:
            self.assertEqual(b["state"], a["state"])

    def test_meaningful_protection_break_fails_continuation(self):
        data = frame([(0,100,101,99.8,100.7),(60,100.7,101,97.5,97.8)])
        report = ContinuationQualityEngine().evaluate(direction="BULLISH", entry_price=100, initial_risk=2, candles=data, current_protection=98.5)
        self.assertEqual(report["state"], "CONTINUATION_FAILED")

    def test_normal_pullback_is_not_exhaustion(self):
        continuation = {"state":"HEALTHY_CONTINUATION", "continuation_score":72}
        giveback = {"unrealized_giveback_R":0.8}
        result = ExhaustionEngine().evaluate(continuation=continuation, giveback=giveback, target_state="WICK_TOUCHED", failed_extensions=1, opposing_displacement=False, protection_intact=True)
        self.assertEqual(result["state"], "NO_EXHAUSTION")
        self.assertIn("CONTINUATION_STILL_HEALTHY", result["exhaustion_rejected_reasons"])

    def test_contextual_giveback_severity(self):
        engine = GivebackControlEngine()
        healthy = engine.evaluate(current_r=1.0, peak_r=2.0, maturity="RUNNER_PHASE", continuation_state="HEALTHY_CONTINUATION", protection_intact=True)
        weak = engine.evaluate(current_r=0.2, peak_r=2.0, maturity="RUNNER_PHASE", continuation_state="EXHAUSTION_WARNING", protection_intact=True)
        self.assertIn(healthy["state"], {"NORMAL_FLUCTUATION", "ACCEPTABLE_GIVEBACK"})
        self.assertEqual(weak["state"], "UNACCEPTABLE_GIVEBACK")

    def test_supporting_reports_do_not_mutate_and_one_action_commits(self):
        continuation = {"state":"HEALTHY_CONTINUATION", "continuation_score":70}
        giveback = {"state":"NORMAL_FLUCTUATION"}
        exhaustion = {"state":"NO_EXHAUSTION"}
        before = (dict(continuation), dict(giveback), dict(exhaustion))
        decision = TradeManagementCoordinator().decide(direction="BULLISH", current_price=104, current_protection=98, initial_stop=98, entry_price=100, maturity="EARLY_PROGRESS", continuation=continuation, giveback=giveback, exhaustion=exhaustion, target_state="CREATED", proven_trail=None, emergency_hit=False, logical_invalidated=False, opposing_bos_exit=False)
        self.assertEqual(decision["commit_count"], 1)
        self.assertEqual(before, (continuation, giveback, exhaustion))

    def test_patched_management_never_widens_and_wick_tp1_does_not_force_be(self):
        data = frame([(0,100,101,99.5,100.6),(60,100.6,102.1,100.1,101.0),(120,101,101.3,100.4,100.8)])
        result = simulate_patched_profit_management(direction="BULLISH", entry_price=100, initial_stop=98, candles=data, tp1_target=102)
        self.assertTrue(result["protection_never_loosened"])
        self.assertNotEqual(result["history"][1]["decision"]["reason"], "TP1_WICK_TOUCH_BREAK_EVEN")
        self.assertTrue(result["closed_candle_evidence_only"])
        self.assertFalse(result["order_api_called"])

    def test_identity_count_one_setup_one_sequence_two_attempts(self):
        audit = count_trade_identity([
            {"parent_setup_id":"S1", "trade_sequence_id":"Q1", "attempt_number":1, "entry_timeframe":"M1"},
            {"parent_setup_id":"S1", "trade_sequence_id":"Q1", "attempt_number":2, "entry_timeframe":"M5"},
        ])
        self.assertEqual((audit["setup_count"], audit["trade_sequence_count"], audit["execution_attempt_count"], audit["reentry_count"]), (1,1,2,1))

    def test_defaults_are_research_only(self):
        contract = DEFAULT_PATCH_CONFIG.contract()
        self.assertTrue(contract["research_only"])
        self.assertFalse(contract["order_execution"])


if __name__ == "__main__":
    unittest.main()
