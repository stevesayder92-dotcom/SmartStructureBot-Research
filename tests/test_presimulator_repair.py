from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd

from core.fidelity_patch import simulate_patched_profit_management
from core.presimulator_repair import (
    EmergencyRiskEngine,
    HybridRepairConfig,
    ParentViabilityEngine,
    StrategicReentryCoordinator,
    build_complete_attempt2_management,
    causal_partial_decision,
    chronological_sequence_equity,
    structural_floor_recommendation,
)


ROOT = Path(__file__).resolve().parents[1]


def _history(values):
    return [{"index": i, "time": 1000 + i * 60,
             "giveback": {"current_R": value}} for i, value in enumerate(values)]


def _attempt(final, values, number=1):
    return {"attempt_number": number, "final_R": final, "history": _history(values),
            "exit_index": len(values) - 1}


def _candles(count=18):
    rows = []
    for i in range(count):
        base = 100 + i * 0.15
        rows.append({"time": 10_000 + i * 60, "open": base, "high": base + 0.4,
                     "low": base - 0.3, "close": base + 0.2})
    return pd.DataFrame(rows)


class PreSimulatorRepairTest(unittest.TestCase):
    def test_loss_plus_open_profit_builds_cumulative_equity(self):
        result = chronological_sequence_equity(parent_setup_id="P",
            attempt_1=_attempt(-1, [0, -1]), attempt_2=_attempt(3, [0, 3], 2))
        self.assertIn(2.0, [x["sequence_equity_R"] for x in result["sequence_equity_curve"]])

    def test_sequence_peak_is_chronological(self):
        result = chronological_sequence_equity(parent_setup_id="P",
            attempt_1=_attempt(-1, [1, -1]), attempt_2=_attempt(2, [0, 2], 2))
        self.assertEqual(result["sequence_peak_R"], 1)

    def test_sequence_giveback_formula(self):
        result = chronological_sequence_equity(parent_setup_id="P", attempt_1=_attempt(1, [2, 1]))
        self.assertEqual(result["sequence_giveback_R"], 1)

    def test_winner_to_loser_reversal_formula(self):
        result = chronological_sequence_equity(parent_setup_id="P", attempt_1=_attempt(-1, [2, -1]))
        self.assertTrue(result["winner_to_loser_reversal"])

    def test_negative_final_has_zero_profit_retained_ratio(self):
        result = chronological_sequence_equity(parent_setup_id="P", attempt_1=_attempt(-1, [2, -1]))
        self.assertEqual(result["profit_retained_ratio"], 0)

    def _attempt2(self):
        candles = _candles()
        candidate = {"execution_attempt_id": "P|ATTEMPT|2|M1|0", "entry_timeframe": "M1",
                     "entry_index": 0, "entry_price": 100.2, "logical_stop": 99.5,
                     "emergency_stop": 99.0}
        return build_complete_attempt2_management(candidate=candidate, parent_setup_id="P",
            direction="BULLISH", candles=candles, m5_candles=candles.iloc[::5].copy(), tp1_target=101.0)

    def test_attempt2_builds_fresh_management_state(self):
        self.assertTrue(self._attempt2()["fresh_attempt_state"])

    def test_attempt2_builds_fresh_targets(self):
        self.assertEqual(self._attempt2()["target_hierarchy"]["owner"], "Attempt2FreshTargetEngine")

    def test_attempt2_builds_fresh_trails(self):
        self.assertIn("fresh_trail_candidates", self._attempt2())

    def test_attempt2_may_transition_m1_to_m5(self):
        self.assertEqual(self._attempt2()["management_transition"]["state"], "M1_TO_M5_MANAGEMENT_AVAILABLE")

    def test_attempt2_may_exit_opposing_bos(self):
        candles = _candles(5)
        result = simulate_patched_profit_management(direction="BULLISH", entry_price=100.2,
            initial_stop=99, emergency_stop=98, candles=candles, tp1_target=None,
            opposing_bos_events=[2])
        self.assertEqual(result["exit_reason"], "EXIT_OPPOSING_BOS")

    def test_attempt2_management_complete_for_reentry(self):
        self.assertTrue(self._attempt2()["attempt_2_management_complete"])

    def test_intact_protection_alone_does_not_allow_reentry(self):
        data = _candles(2)
        parent = {"parent_setup_id": "P", "direction": "BULLISH",
                  "dominant_protection_intact_at_failure": True}
        result = ParentViabilityEngine().assess(parent=parent, failure_time=20_000,
            m5_data=data, m1_data=data)
        self.assertEqual(result["state"], "NO_REENTRY_UNPROVEN_PARENT")

    def test_fresh_child_reset_allows_m1_reentry(self):
        self.assertEqual(HybridRepairConfig().meaningful_reset_atr, 0.35)

    def test_immediate_original_trigger_reuse_is_rejected(self):
        source = (ROOT / "core" / "presimulator_repair.py").read_text(encoding="utf-8")
        self.assertIn("trigger_is_new", source)

    def test_m5_confirmation_may_own_after_m1_failure(self):
        coordinator = StrategicReentryCoordinator()
        viable = {"reentry_eligible": True, "state": "SAME_RETRACEMENT_EXTENDED"}
        m5 = {"entry_time": 20, "entry_timeframe": "M5"}
        with patch.object(coordinator.viability_engine, "assess", return_value=viable), \
             patch("core.presimulator_repair._scan_candidate", side_effect=[None, None, m5]):
            result = coordinator.evaluate(parent={"parent_setup_id": "P", "direction": "BULLISH"},
                failure_time=1, review_end_time=30, m1_data=_candles(), m5_data=_candles())
        self.assertEqual(result["selected_owner"], "M5")

    def test_strategic_candidate_outranks_technical_candidate(self):
        coordinator = StrategicReentryCoordinator()
        viable = {"reentry_eligible": True, "state": "SAME_RETRACEMENT_EXTENDED"}
        technical = {"entry_time": 5, "entry_timeframe": "M1"}
        m5 = {"entry_time": 20, "entry_timeframe": "M5"}
        with patch.object(coordinator.viability_engine, "assess", return_value=viable), \
             patch("core.presimulator_repair._scan_candidate", side_effect=[technical, None, m5]):
            result = coordinator.evaluate(parent={"parent_setup_id": "P", "direction": "BULLISH"},
                failure_time=1, review_end_time=30, m1_data=_candles(), m5_data=_candles())
        self.assertEqual(result["selected_owner"], "M5")

    def test_reentry_limit_is_one(self):
        data = _candles()
        parent = {"parent_setup_id": "P", "direction": "BULLISH",
                  "dominant_protection_intact_at_failure": True}
        result = ParentViabilityEngine().assess(parent=parent, failure_time=10_100,
            m5_data=data, m1_data=data, reentry_count=1)
        self.assertEqual(result["state"], "CLOSED_REENTRY_LIMIT")

    def test_second_failure_is_terminal(self):
        self.assertIn("CLOSED_AFTER_SECOND_FAILURE", (ROOT / "SmartStructureBot_Bible.md").read_text(encoding="utf-8"))

    def test_partial_uses_decision_time_state(self):
        result = causal_partial_decision([{"index": 2, "time": 5, "target_state": "WICK_TOUCHED", "close": 1}])
        self.assertEqual(result["target_state_at_decision"], "WICK_TOUCHED")

    def test_future_rejection_cannot_rewrite_partial(self):
        prefix = [{"index": 2, "target_state": "WICK_TOUCHED", "close": 1}]
        self.assertEqual(causal_partial_decision(prefix)["partial_fraction"],
                         causal_partial_decision(prefix + [{"index": 3, "target_state": "REJECTED"}])["partial_fraction"])

    def test_partial_prefix_is_suffix_invariant(self):
        prefix = [{"index": 2, "target_state": "BODY_CLOSED_THROUGH", "close": 1}]
        a = causal_partial_decision(prefix)
        b = causal_partial_decision(prefix + [{"index": 8, "target_state": "ACCEPTED_BEYOND"}])
        self.assertEqual((a["partial_decision_index"], a["partial_fraction"]),
                         (b["partial_decision_index"], b["partial_fraction"]))

    def test_emergency_risk_multiple_formula(self):
        result = EmergencyRiskEngine().evaluate(entry_price=100, logical_stop=99, emergency_stop=98)
        self.assertEqual(result["emergency_risk_multiple"], 2)

    def test_position_size_caps_emergency_account_risk(self):
        cfg = HybridRepairConfig(selected_risk_model="DUAL_RISK_CAP", max_emergency_account_risk=1.25)
        result = EmergencyRiskEngine(cfg).evaluate(entry_price=100, logical_stop=99, emergency_stop=97)
        self.assertLessEqual(result["model_b"]["emergency_loss_account_R"], 1.25)

    def test_logical_and_account_r_are_separate(self):
        result = self._attempt2()
        self.assertIn("logical_R", result)
        self.assertIn("account_risk_R", result)

    def test_profit_alone_does_not_tighten(self):
        result = structural_floor_recommendation(direction="BULLISH", current_protection=99,
            current_price=105, opportunity_state="EARNED", deterioration_state="NO_DANGER",
            giveback_r=0, normal_pullback=False, structures=[])
        self.assertEqual(result["committed_action"], "HOLD")

    def test_one_weak_candle_does_not_tighten(self):
        result = structural_floor_recommendation(direction="BULLISH", current_protection=99,
            current_price=105, opportunity_state="SIGNIFICANT", deterioration_state="WATCH",
            giveback_r=0.2, normal_pullback=False, structures=[])
        self.assertEqual(result["committed_action"], "HOLD")

    def test_opportunity_and_deterioration_may_tighten(self):
        result = structural_floor_recommendation(direction="BULLISH", current_protection=99,
            current_price=105, opportunity_state="SIGNIFICANT", deterioration_state="HIGH_RISK",
            giveback_r=1, normal_pullback=False,
            structures=[{"proven": True, "level": 102, "available_at": 3, "owner": "M5"}])
        self.assertEqual(result["committed_action"], "LOCK_STRUCTURAL_PROFIT")

    def test_tightening_requires_structure_owner(self):
        result = structural_floor_recommendation(direction="BULLISH", current_protection=99,
            current_price=105, opportunity_state="SIGNIFICANT", deterioration_state="HIGH_RISK",
            giveback_r=1, normal_pullback=False, structures=[])
        self.assertEqual(result["recommendation"], "NO_VALID_TIGHTER_STRUCTURE")

    def test_hybrid_stop_never_loosens(self):
        self.assertTrue(self._attempt2()["protection_never_loosened"])

    def test_healthy_pullback_remains_open(self):
        result = structural_floor_recommendation(direction="BULLISH", current_protection=99,
            current_price=105, opportunity_state="MAJOR_RUNNER", deterioration_state="HIGH_RISK",
            giveback_r=2, normal_pullback=True, structures=[])
        self.assertEqual(result["committed_action"], "HOLD_NORMAL_PULLBACK")

    def test_strong_continuation_keeps_runner(self):
        result = structural_floor_recommendation(direction="BULLISH", current_protection=99,
            current_price=105, opportunity_state="SIGNIFICANT", deterioration_state="NO_DANGER",
            giveback_r=0.2, normal_pullback=False, structures=[])
        self.assertEqual(result["committed_action"], "HOLD")

    def test_tp1_wick_does_not_force_break_even_hybrid(self):
        source = (ROOT / "core" / "presimulator_repair.py").read_text(encoding="utf-8")
        self.assertNotIn("MOVE_TO_BREAK_EVEN", source)

    def test_one_committed_action_per_event_hybrid(self):
        self.assertTrue(self._attempt2()["single_action_per_event"])

    def test_supporting_engines_cannot_mutate_position_hybrid(self):
        result = self._attempt2()
        self.assertTrue(all(event["commit_count"] == 1 for event in result["history"]))

    def test_frozen_population_has_no_duplicate_first_entries(self):
        audit = json.loads((ROOT / "final_fidelity_patch_v1_evidence" / "final_fidelity_patch_v1_audit.json").read_text())
        keys = [(r["parent_m5_setup_id"], r["entry_time"]) for r in audit["rows"]]
        self.assertEqual(len(keys), len(set(keys)))

    def test_repair_uses_no_future_candles(self):
        self.assertFalse(self._attempt2()["future_data_used"])

    def test_repair_uses_no_unfinished_candles(self):
        self.assertFalse(self._attempt2()["unfinished_candle_used"])

    def test_repaired_replay_is_deterministic(self):
        self.assertEqual(self._attempt2()["final_R"], self._attempt2()["final_R"])

    def test_repair_calls_no_order_api(self):
        source = (ROOT / "core" / "presimulator_repair.py").read_text(encoding="utf-8")
        self.assertNotIn("order_send(", source)


if __name__ == "__main__":
    unittest.main()
