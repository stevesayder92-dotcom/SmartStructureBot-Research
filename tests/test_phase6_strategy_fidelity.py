from __future__ import annotations

import unittest
from pathlib import Path

from core.entry_freshness import EntryFreshnessEngine
from core.pipeline_runner import PipelineOptions, run_pipeline
from core.strategy_fidelity import (
    compare_manual_to_bot,
    summarise_comparisons,
    validate_manual_label,
)

import pandas as pd


class StrategyFidelityTest(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_incomplete_review_is_never_scored_as_rejection(self):
        manual = {
            "example_id": "example-1",
            "review_status": "UNREVIEWED",
            "human_decision": "UNCERTAIN",
        }
        comparison = compare_manual_to_bot(
            manual=manual,
            bot={"entry_ready": False, "direction": "BEARISH"},
        )
        self.assertFalse(comparison["scorable"])
        self.assertIsNone(comparison["agreement"])

    def test_complete_trade_requires_structural_labels(self):
        validation = validate_manual_label(
            {
                "review_status": "COMPLETE",
                "human_decision": "BUY",
                "manual_reason": "Valid continuation",
            }
        )
        self.assertFalse(validation["valid"])
        self.assertIn(
            "A traded COMPLETE example requires failure_trigger_index",
            validation["errors"],
        )

    def test_disagreements_are_field_specific(self):
        manual = {
            "example_id": "example-2",
            "review_status": "COMPLETE",
            "human_decision": "SELL",
            "direction": "BEARISH",
            "origin_bos_index": 10,
            "initial_pullback_start_index": 15,
            "failure_trigger_index": 21,
            "entry_index": 25,
            "manual_reason": "Counter-trend HL failed",
        }
        bot = {
            "entry_ready": True,
            "direction": "BEARISH",
            "origin_bos_index": 10,
            "first_candidate_index": 16,
            "active_failure_trigger_index": 22,
            "entry_index": 27,
        }
        comparison = compare_manual_to_bot(manual=manual, bot=bot)
        self.assertTrue(comparison["scorable"])
        self.assertEqual(
            {
                item["category"]
                for item in comparison["disagreements"]
            },
            {"PULLBACK_ORIGIN", "FAILURE_TRIGGER", "ENTRY_TIMING"},
        )
        self.assertFalse(comparison["thresholds_changed"])

    def test_summary_needs_thirty_labels_for_readiness_inference(self):
        summary = summarise_comparisons(
            [
                {
                    "scorable": True,
                    "agreement": True,
                    "disagreements": [],
                }
            ]
            * 29
        )
        self.assertFalse(summary["demo_readiness_can_be_inferred"])

    def test_freshness_exposes_trigger_confirmation_delay(self):
        data = pd.DataFrame(
            {
                "open": [100.0] * 30,
                "high": [101.0] * 30,
                "low": [99.0] * 30,
                "close": [100.0] * 30,
            }
        )
        retracement = {
            "first_qualification_index": 10,
            "qualified": True,
            "protected_swing_intact": True,
            "state": "ENTRY_CANDIDATE",
            "active_failure_trigger": {
                "index": 12,
                "fractal_confirmed_at_index": 14,
                "structural_confirmed_at_index": 24,
                "tradeable_at_index": 24,
                "belongs_to_same_qualified_retracement": True,
            },
        }
        result = EntryFreshnessEngine(
            data,
            timeframe="M5",
        ).assess(retracement=retracement, entry_index=24)
        self.assertEqual(result["trigger_confirmation_delay_candles"], 10)
        self.assertTrue(
            result["trigger_confirmation_coincident_with_entry"]
        )

    def test_real_entry_publishes_fractal_and_locked_trigger_times(self):
        data = pd.read_csv(
            self.ROOT
            / "research_data"
            / "GOLD_M5_phase5b_closed.csv"
        ).reset_index(drop=True)
        result = run_pipeline(
            data=data,
            symbol="GOLD#",
            timeframe="M5",
            as_of_index=4591,
            options=PipelineOptions(),
        )
        trigger = result.snapshot["retracement"][
            "active_failure_trigger"
        ]
        freshness = result.snapshot["entry_freshness"]
        self.assertEqual(trigger["fractal_confirmed_at_index"], 4545)
        self.assertEqual(trigger["structural_confirmed_at_index"], 4580)
        self.assertEqual(
            freshness["trigger_confirmation_delay_candles"],
            35,
        )
        self.assertFalse(
            freshness["trigger_confirmation_coincident_with_entry"]
        )


if __name__ == "__main__":
    unittest.main()
