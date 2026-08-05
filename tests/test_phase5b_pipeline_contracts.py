from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from core.pipeline_runner import PipelineOptions, run_pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Phase5BPipelineContractsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = pd.read_csv(
            PROJECT_ROOT / "research_data" / "GOLD_M1.csv"
        ).reset_index(drop=True)
        cls.result = run_pipeline(
            data=cls.data,
            symbol="GOLD#",
            timeframe="M1",
            as_of_index=3064,
            options=PipelineOptions(),
        )
        cls.snapshot = cls.result.snapshot

    def test_protection_belongs_to_current_cycle(self):
        protection = self.snapshot["protection"]
        cycle = self.snapshot["impulse_cycle"]
        self.assertTrue(protection["available"])
        self.assertEqual(protection["cycle_id"], cycle["cycle_id"])
        self.assertLess(
            protection["index"],
            self.snapshot["entry"]["index"],
        )

    def test_protection_roles_are_independent_roots(self):
        decision = self.snapshot["protection"]
        invalidation = self.snapshot["setup_invalidation"]
        trailing = self.snapshot["trailing_protection"]
        self.assertEqual(
            decision["protection_role"],
            "DECISION_PROTECTION",
        )
        self.assertEqual(
            invalidation["protection_role"],
            "SETUP_INVALIDATION",
        )
        self.assertEqual(
            trailing["role"],
            "TRAILING_PROTECTION",
        )
        self.assertNotEqual(
            decision.get("index"),
            invalidation.get("index"),
        )
        self.assertFalse(trailing["available"])

    def test_entry_freshness_is_causal_and_advisory(self):
        freshness = self.snapshot["entry_freshness"]
        self.assertTrue(freshness["causal_valid"])
        self.assertTrue(freshness["advisory_only"])
        self.assertFalse(freshness["strategy_outcome_changed"])
        self.assertEqual(
            freshness["entry_index"],
            self.snapshot["entry"]["index"],
        )

    def test_no_future_cycle_or_protection_data(self):
        current = self.snapshot["meta"]["as_of_index"]
        cycle = self.snapshot["impulse_cycle"]
        protection = self.snapshot["protection"]
        self.assertLessEqual(
            cycle["origin_bos_available_at_index"],
            current,
        )
        self.assertLessEqual(
            protection["protection_available_at_index"],
            current,
        )
        self.assertFalse(
            self.result.diagnostics["future_protection_used"]
        )

    def test_no_order_api_calls_exist_in_runtime(self):
        forbidden = (
            "order_send(",
            "order_check(",
            "positions_get(",
            "TRADE_ACTION_DEAL",
        )
        matches = []
        for path in (
            list((PROJECT_ROOT / "core").glob("*.py"))
            + [PROJECT_ROOT / "main.py"]
        ):
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in text:
                    matches.append(f"{path.name}:{token}")
        self.assertEqual(matches, [])

    def test_missing_qualified_trigger_cannot_use_raw_fallback(self):
        ger40 = pd.read_csv(
            PROJECT_ROOT
            / "research_data"
            / "GER40Cash_M5_phase5b_closed.csv"
        ).reset_index(drop=True)
        result = run_pipeline(
            data=ger40,
            symbol="GER40Cash#",
            timeframe="M5",
            as_of_index=2347,
            options=PipelineOptions(),
        )
        retracement = result.snapshot["retracement"]
        self.assertTrue(retracement["qualified"])
        self.assertIsNone(
            retracement["active_failure_trigger"]
        )
        self.assertFalse(result.snapshot["entry"]["ready"])
        self.assertEqual(
            result.snapshot["entry"]["state"],
            "WAITING_FOR_FAILURE_TRIGGER",
        )
