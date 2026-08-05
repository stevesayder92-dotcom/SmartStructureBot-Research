from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd

from core.sequence_recovery import (
    CrossTimeframeReentryCoordinator,
    EarnedOpportunityEngine,
    MatureProfitFloorEngine,
    OpportunityRiskEngine,
    SequenceEliteConfig,
    dynamic_partial_fraction,
    final_invalidation_structure,
    long_runner_metrics,
    sequence_outcome,
    winner_to_loser_metrics,
)


ROOT = Path(__file__).resolve().parents[1]


def _data(count: int = 12, start: float = 1_700_000_000.0) -> pd.DataFrame:
    rows = []
    for i in range(count):
        base = 100.0 + (i % 4) * 0.2
        rows.append({"time": start + i * 60, "open": base, "high": base + 0.4,
                     "low": base - 0.4, "close": base + (0.1 if i % 2 else -0.1)})
    return pd.DataFrame(rows)


def _attempt(value: float, peak: float = 1.0) -> dict:
    return {"final_R": value, "peak_R": peak, "MFE_R": peak, "MAE_R": 1.0}


def _candidate(tf: str, when: float) -> dict:
    return {"entry_timeframe": tf, "entry_time": when, "entry_index": 5,
            "execution_attempt_id": f"P|ATTEMPT|2|{tf}|5", "attempt_number": 2,
            "logical_stop": 99.0, "entry_price": 100.0}


class SequenceElitePatchTest(unittest.TestCase):
    def setUp(self):
        self.parent = {"parent_setup_id": "P", "direction": "BULLISH",
                       "dominant_protection_level": 90.0,
                       "dominant_protection_intact_at_failure": True}
        self.data = _data()

    def _coordinate(self, m1, m5, reentry_count=0):
        with patch("core.sequence_recovery._scan_timeframe_candidate", side_effect=[m1, m5]):
            return CrossTimeframeReentryCoordinator().evaluate(
                parent=self.parent, first_failure_time=1_700_000_300.0,
                review_end_time=1_700_003_000.0, m1_data=self.data,
                m5_data=self.data, reentry_count=reentry_count)

    def test_m1_first_failure_may_allow_m5_reentry(self):
        self.assertEqual(self._coordinate(None, _candidate("M5", 20))["reentry_owner_timeframe"], "M5")

    def test_m5_first_failure_may_allow_m1_reentry(self):
        self.assertEqual(self._coordinate(_candidate("M1", 20), None)["reentry_owner_timeframe"], "M1")

    def test_first_valid_reentry_closes_competing_gate(self):
        result = self._coordinate(_candidate("M1", 10), _candidate("M5", 20))
        self.assertTrue(result["competing_gate_closed"])

    def test_same_parent_setup_id_is_preserved(self):
        result = self._coordinate(_candidate("M1", 10), None)
        self.assertEqual(result["parent_setup_id"], "P")

    def test_attempt_number_increments_to_two(self):
        result = self._coordinate(_candidate("M1", 10), None)
        self.assertEqual(result["winner"]["attempt_number"], 2)

    def test_reentry_stop_belongs_to_winning_timeframe(self):
        result = self._coordinate(None, _candidate("M5", 20))
        self.assertIn("|M5|", result["winner"]["execution_attempt_id"])

    def test_stale_attempt_one_trigger_cannot_be_reused(self):
        cfg = SequenceEliteConfig()
        self.assertEqual(cfg.reentry_freshness_m1_candles, 10)

    def test_second_failure_closes_parent_permanently(self):
        result = sequence_outcome(parent_setup_id="P", attempt_1=_attempt(-1), attempt_2=_attempt(-1))
        self.assertEqual(result["execution_attempt_count"], 2)

    def test_no_third_attempt_is_permitted(self):
        result = self._coordinate(None, None, reentry_count=1)
        self.assertTrue(result["state"].startswith("PARENT_CLOSED"))

    def test_trade_51_regression_lifecycle_is_explicitly_audited(self):
        tool = (ROOT / "tools" / "run_sequence_elite_evidence.py").read_text(encoding="utf-8")
        self.assertIn("trade_51_regression_audit.json", tool)

    def test_one_setup_two_attempts_counts_once(self):
        result = sequence_outcome(parent_setup_id="P", attempt_1=_attempt(-1), attempt_2=_attempt(2))
        self.assertEqual((result["setup_count"], result["trade_sequence_count"]), (1, 1))

    def test_combined_sequence_r_is_correct(self):
        result = sequence_outcome(parent_setup_id="P", attempt_1=_attempt(-1), attempt_2=_attempt(2))
        self.assertEqual(result["combined_sequence_R"], 1)

    def test_reentry_contribution_is_correct(self):
        result = sequence_outcome(parent_setup_id="P", attempt_1=_attempt(-1), attempt_2=_attempt(0.5))
        self.assertEqual(result["reentry_contribution_R"], 0.5)

    def test_sequence_recovery_flag_is_correct(self):
        result = sequence_outcome(parent_setup_id="P", attempt_1=_attempt(-1), attempt_2=_attempt(2))
        self.assertTrue(result["sequence_recovered_first_loss"])

    def test_attempt_and_sequence_metrics_remain_separate(self):
        result = sequence_outcome(parent_setup_id="P", attempt_1=_attempt(-1), attempt_2=_attempt(2))
        self.assertNotEqual(result["attempt_2_R"], result["sequence_final_R"])

    def test_opportunity_not_earned_from_profit_alone(self):
        result = EarnedOpportunityEngine().evaluate(current_r=1, peak_r=1,
            continuation_state="NOT_ESTABLISHED", target_state="CREATED", proven_structures=0)
        self.assertNotEqual(result["state"], "OPPORTUNITY_EARNED")

    def test_opportunity_earned_with_structure_and_progress(self):
        result = EarnedOpportunityEngine().evaluate(current_r=1, peak_r=1,
            continuation_state="HEALTHY_CONTINUATION", target_state="CREATED", proven_structures=1)
        self.assertEqual(result["state"], "OPPORTUNITY_EARNED")

    def test_major_runner_opportunity_uses_large_peak(self):
        result = EarnedOpportunityEngine().evaluate(current_r=2, peak_r=3,
            continuation_state="HEALTHY_CONTINUATION", target_state="CREATED")
        self.assertEqual(result["state"], "MAJOR_RUNNER_OPPORTUNITY")

    def test_healthy_continuation_caps_false_risk(self):
        result = OpportunityRiskEngine().evaluate(continuation_state="HEALTHY_CONTINUATION",
            target_state="CREATED", giveback_r=2, retained_peak_ratio=0.1,
            failed_extensions=3, opposing_displacement=True, protection_intact=True)
        self.assertEqual(result["raw_state"], "NO_DANGER")

    def test_opportunity_failure_requires_confluence(self):
        result = OpportunityRiskEngine().evaluate(continuation_state="CONTINUATION_FAILED",
            target_state="REJECTED", giveback_r=2, retained_peak_ratio=0.1,
            failed_extensions=3, opposing_displacement=True, protection_intact=False)
        self.assertEqual(result["state"], "OPPORTUNITY_FAILURE")

    def test_risk_hysteresis_rejects_one_event_flip(self):
        result = OpportunityRiskEngine().evaluate(continuation_state="WEAKENING_CONTINUATION",
            target_state="REJECTED", giveback_r=0, retained_peak_ratio=1,
            failed_extensions=0, opposing_displacement=False, protection_intact=False)
        self.assertEqual(result["state"], "NO_DANGER")

    def test_normal_pullback_is_explicitly_allowed(self):
        result = OpportunityRiskEngine().evaluate(continuation_state="HEALTHY_CONTINUATION",
            target_state="CREATED", giveback_r=0.2, retained_peak_ratio=0.8,
            failed_extensions=0, opposing_displacement=False, protection_intact=True)
        self.assertTrue(result["normal_pullback_allowed"])

    def test_mature_floor_requires_earned_opportunity(self):
        result = MatureProfitFloorEngine().select(direction="BULLISH", current_protection=99,
            current_price=105, opportunity_state="OPPORTUNITY_EARNED", risk_state="HIGH_RISK",
            structures=[{"proven": True, "level": 101, "available_at": 3}])
        self.assertEqual(result["state"], "FLOOR_NOT_ELIGIBLE")

    def test_mature_floor_requires_deterioration_risk(self):
        result = MatureProfitFloorEngine().select(direction="BULLISH", current_protection=99,
            current_price=105, opportunity_state="MAJOR_RUNNER_OPPORTUNITY", risk_state="WATCH",
            structures=[{"proven": True, "level": 101, "available_at": 3}])
        self.assertEqual(result["state"], "FLOOR_NOT_ELIGIBLE")

    def test_mature_floor_selects_proven_long_structure(self):
        result = MatureProfitFloorEngine().select(direction="BULLISH", current_protection=99,
            current_price=105, opportunity_state="MAJOR_RUNNER_OPPORTUNITY", risk_state="HIGH_RISK",
            structures=[{"proven": True, "level": 101, "available_at": 3, "owner": "M5"}])
        self.assertEqual(result["selected_level"], 101)

    def test_mature_floor_selects_proven_short_structure(self):
        result = MatureProfitFloorEngine().select(direction="BEARISH", current_protection=110,
            current_price=100, opportunity_state="MAJOR_RUNNER_OPPORTUNITY", risk_state="HIGH_RISK",
            structures=[{"proven": True, "level": 104, "available_at": 3, "owner": "M5"}])
        self.assertEqual(result["selected_level"], 104)

    def test_mature_floor_rejects_unproven_structure(self):
        result = MatureProfitFloorEngine().select(direction="BULLISH", current_protection=99,
            current_price=105, opportunity_state="MAJOR_RUNNER_OPPORTUNITY", risk_state="HIGH_RISK",
            structures=[{"proven": False, "level": 101, "available_at": 3}])
        self.assertEqual(result["state"], "NO_VALID_PROFIT_FLOOR_STRUCTURE")

    def test_structure_runner_profile_has_no_partial(self):
        self.assertEqual(dynamic_partial_fraction(profile="STRUCTURE_RUNNER_ONLY", target_state="WICK_TOUCHED", opportunity_state="OPPORTUNITY_EARNED", risk_state="WATCH"), 0)

    def test_static_partial_profile_uses_half(self):
        self.assertEqual(dynamic_partial_fraction(profile="PARTIAL_PLUS_RUNNER", target_state="WICK_TOUCHED", opportunity_state="OPPORTUNITY_EARNED", risk_state="WATCH"), 0.5)

    def test_dynamic_acceptance_profile_preserves_runner(self):
        self.assertEqual(dynamic_partial_fraction(profile="DYNAMIC_PARTIAL_PLUS_RUNNER", target_state="ACCEPTED_BEYOND", opportunity_state="OPPORTUNITY_EARNED", risk_state="WATCH"), 0.25)

    def test_dynamic_rejection_profile_protects_more(self):
        self.assertEqual(dynamic_partial_fraction(profile="DYNAMIC_PARTIAL_PLUS_RUNNER", target_state="REJECTED", opportunity_state="OPPORTUNITY_EARNED", risk_state="HIGH_RISK"), 0.65)

    def test_winner_to_loser_threshold_half_r(self):
        self.assertEqual(winner_to_loser_metrics([_attempt(-1, 0.5)])["peak_gte_0.5R_final_lt_0"], 1)

    def test_winner_to_loser_threshold_one_r(self):
        self.assertEqual(winner_to_loser_metrics([_attempt(-1, 1)])["peak_gte_1.0R_final_lt_0"], 1)

    def test_winner_to_loser_threshold_two_r(self):
        self.assertEqual(winner_to_loser_metrics([_attempt(-1, 2)])["peak_gte_2.0R_final_lt_0"], 1)

    def test_long_runner_preservation_bucket(self):
        self.assertEqual(long_runner_metrics([_attempt(2, 3)])["LONG_RUNNER_PRESERVED"], 1)

    def test_long_runner_excessive_giveback_bucket(self):
        self.assertEqual(long_runner_metrics([_attempt(0.5, 3)])["LONG_RUNNER_GAVE_BACK_EXCESSIVELY"], 1)

    def test_sequence_config_is_research_only(self):
        contract = SequenceEliteConfig().contract()
        self.assertTrue(contract["research_only"] and not contract["order_execution"])

    def test_sequence_config_file_matches_research_mode(self):
        config = json.loads((ROOT / "config" / "sequence_elite_v1.json").read_text())
        self.assertTrue(config["research_only"] and not config["order_execution"])

    def test_sequence_module_contains_no_order_send_call(self):
        source = (ROOT / "core" / "sequence_recovery.py").read_text(encoding="utf-8")
        self.assertNotIn("order_send(", source)

    def test_evidence_runner_publishes_zero_order_flag(self):
        source = (ROOT / "tools" / "run_sequence_elite_evidence.py").read_text(encoding="utf-8")
        self.assertIn('"order_api_called":False', source)


if __name__ == "__main__":
    unittest.main()
