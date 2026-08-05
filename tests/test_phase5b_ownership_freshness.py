from __future__ import annotations

import unittest

import pandas as pd

from core.entry_freshness import EntryFreshnessEngine
from core.htf_context import compare_htf_advisory_policies
from core.impulse_cycle import (
    DecisionProtectionPolicy,
    DecisionProtectionSelector,
    ImpulseCycleEngine,
)
from core.protection_audit import reproduce_protection_invalidation


def protection_fixture():
    cycle = {
        "cycle_id": "CYCLE-X-M5-BEARISH-8",
        "owner": "ImpulseCycleEngine",
        "direction": "BEARISH",
        "origin_bos_index": 8,
        "origin_bos_available_at_index": 8,
        "impulse_start_index": 5,
        "causal_valid": True,
    }
    points = [
        {
            "index": 2,
            "side": "HIGH",
            "type": "LH",
            "body_price": 120.0,
            "confirmed_at_index": 3,
            "decision_weight": 8,
        },
        {
            "index": 6,
            "side": "HIGH",
            "type": "LH",
            "body_price": 110.0,
            "confirmed_at_index": 7,
            "decision_weight": 6,
        },
        {
            "index": 10,
            "side": "HIGH",
            "type": "LH",
            "body_price": 106.0,
            "confirmed_at_index": 11,
            "decision_weight": 5,
        },
        {
            "index": 15,
            "side": "HIGH",
            "type": "LH",
            "body_price": 104.0,
            "confirmed_at_index": 15,
            "decision_weight": 7,
        },
    ]
    events = [
        {
            "index": 8,
            "type": "BEARISH_BOS",
            "decision_available_at_index": 8,
            "causal_valid": True,
        },
        {
            "index": 14,
            "type": "BEARISH_BOS",
            "decision_available_at_index": 14,
            "causal_valid": True,
        },
    ]
    return cycle, points, events


class Phase5BOwnershipFreshnessTest(unittest.TestCase):
    def test_impulse_cycle_contract_is_causal(self):
        cycle = ImpulseCycleEngine(
            symbol="TEST#",
            timeframe="M5",
        ).build(
            trend="BEARISH",
            origin_bos={
                "index": 8,
                "type": "BEARISH_BOS",
                "decision_available_at_index": 8,
            },
            structure_points=[
                {
                    "index": 6,
                    "side": "HIGH",
                    "type": "LH",
                    "confirmed_at_index": 7,
                }
            ],
            bos_events=[],
            as_of_index=12,
            qualified_retracement_start_index=10,
        )
        self.assertEqual(cycle["status"], "RETRACEMENT_ACTIVE")
        self.assertTrue(cycle["causal_valid"])
        self.assertLessEqual(
            cycle["impulse_start_index"],
            cycle["origin_bos_index"],
        )

    def test_unrelated_old_cycle_protection_is_rejected(self):
        cycle, points, events = protection_fixture()
        result = DecisionProtectionSelector().select(
            cycle=cycle,
            trend="BEARISH",
            structure_points=points,
            bos_events=events,
            as_of_index=16,
            current_price=90.0,
        )
        old = next(
            item for item in result["all_candidates"]
            if item["structure_index"] == 2
        )
        self.assertIn(
            "UNRELATED_OLD_IMPULSE_CYCLE",
            old["rejection_reasons"],
        )
        self.assertNotEqual(result["index"], 2)

    def test_origin_defending_protection_remains_stable(self):
        cycle, points, events = protection_fixture()
        result = DecisionProtectionSelector(
            policy=DecisionProtectionPolicy(
                "ORIGIN_DEFENDING_SWING"
            )
        ).select(
            cycle=cycle,
            trend="BEARISH",
            structure_points=points,
            bos_events=events,
            as_of_index=16,
            current_price=90.0,
        )
        self.assertEqual(result["index"], 6)

    def test_newer_protection_requires_continuation_bos(self):
        cycle, points, events = protection_fixture()
        no_continuation = events[:1]
        result = DecisionProtectionSelector(
            policy=DecisionProtectionPolicy(
                "LATEST_PROVEN_CONTINUATION_SWING"
            )
        ).select(
            cycle=cycle,
            trend="BEARISH",
            structure_points=points,
            bos_events=no_continuation,
            as_of_index=16,
            current_price=90.0,
        )
        self.assertEqual(result["index"], 6)

    def test_raw_latest_swing_cannot_replace_protection(self):
        cycle, points, events = protection_fixture()
        result = DecisionProtectionSelector(
            policy=DecisionProtectionPolicy(
                "HYBRID_PROVEN_REPLACEMENT"
            )
        ).select(
            cycle=cycle,
            trend="BEARISH",
            structure_points=points,
            bos_events=events,
            as_of_index=16,
            current_price=90.0,
        )
        self.assertEqual(result["index"], 10)
        self.assertNotEqual(result["index"], 15)

    def test_replacement_is_causal_and_current(self):
        cycle, points, events = protection_fixture()
        result = DecisionProtectionSelector(
            policy=DecisionProtectionPolicy(
                "LATEST_PROVEN_CONTINUATION_SWING"
            )
        ).select(
            cycle=cycle,
            trend="BEARISH",
            structure_points=points,
            bos_events=events,
            as_of_index=16,
            current_price=90.0,
        )
        self.assertLessEqual(
            result["decision_available_at_index"],
            result["as_of_index"],
        )
        self.assertEqual(result["confirming_bos_index"], 14)

    def test_waiting_is_published_without_fallback(self):
        cycle, points, events = protection_fixture()
        result = DecisionProtectionSelector().select(
            cycle=cycle,
            trend="BEARISH",
            structure_points=[points[0]],
            bos_events=events,
            as_of_index=16,
            current_price=90.0,
        )
        self.assertFalse(result["available"])
        self.assertEqual(
            result["state"],
            "WAITING_FOR_VALID_DECISION_PROTECTION",
        )

    def test_freshness_is_deterministic(self):
        data = pd.DataFrame(
            [
                {
                    "open": 100 + i,
                    "high": 102 + i,
                    "low": 99 + i,
                    "close": 101 + i,
                }
                for i in range(30)
            ]
        )
        retracement = {
            "as_of_index": 20,
            "qualified": True,
            "state": "ENTRY_CANDIDATE",
            "protected_swing_intact": True,
            "first_qualification_index": 10,
            "active_failure_trigger_index": 15,
            "active_failure_trigger": {
                "index": 15,
                "belongs_to_same_qualified_retracement": True,
            },
            "trigger_update_count": 1,
        }
        engine = EntryFreshnessEngine(data, timeframe="M5")
        self.assertEqual(
            engine.assess(
                retracement=retracement,
                entry_index=20,
            ),
            engine.assess(
                retracement=retracement,
                entry_index=20,
            ),
        )

    def test_trigger_refresh_must_belong_to_same_setup(self):
        data = pd.DataFrame(
            [
                {
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                }
                for _ in range(50)
            ]
        )
        result = EntryFreshnessEngine(
            data,
            timeframe="M5",
        ).assess(
            retracement={
                "as_of_index": 40,
                "qualified": True,
                "state": "ENTRY_CANDIDATE",
                "protected_swing_intact": True,
                "first_qualification_index": 5,
                "active_failure_trigger_index": 35,
                "active_failure_trigger": {
                    "index": 35,
                    "belongs_to_same_qualified_retracement": False,
                },
                "trigger_update_count": 2,
            },
            entry_index=40,
        )
        self.assertEqual(
            result["classification"],
            "STALE_RETRACEMENT_ENTRY",
        )
        self.assertFalse(
            result["policy_comparison"]["TRIGGER_REFRESH"]["allowed"]
        )

    def test_stale_classification_does_not_change_outcome(self):
        data = pd.DataFrame(
            [
                {
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                }
                for _ in range(80)
            ]
        )
        result = EntryFreshnessEngine(
            data,
            timeframe="M5",
        ).assess(
            retracement={
                "as_of_index": 70,
                "qualified": True,
                "state": "ENTRY_CANDIDATE",
                "protected_swing_intact": True,
                "first_qualification_index": 5,
                "active_failure_trigger_index": 6,
                "active_failure_trigger": {
                    "index": 6,
                    "belongs_to_same_qualified_retracement": True,
                },
                "trigger_update_count": 0,
            },
            entry_index=70,
        )
        self.assertEqual(
            result["classification"],
            "STALE_RETRACEMENT_ENTRY",
        )
        self.assertFalse(result["strategy_outcome_changed"])

    def test_htf_comparisons_are_advisory(self):
        context = {
            "frames": {
                "M30": {
                    "clean": True,
                    "strong": True,
                    "trend": "BEARISH",
                },
                "M15": {
                    "clean": True,
                    "strong": True,
                    "trend": "BEARISH",
                },
                "H1": {
                    "clean": True,
                    "strong": False,
                    "trend": "BULLISH",
                },
            }
        }
        results = compare_htf_advisory_policies(
            context,
            "BEARISH",
        )
        self.assertEqual(set(results), {
            "PREFER_M30_M15",
            "CONSENSUS_2_OF_3",
            "STRONGEST_SINGLE",
            "H1_ANCHOR",
        })
        self.assertTrue(
            all(item["advisory_only"] for item in results.values())
        )
        self.assertTrue(
            all(
                item["hard_block_applied"] is False
                for item in results.values()
            )
        )

    def test_canonical_invalidation_reproduces(self):
        snapshot = {
            "meta": {"as_of_index": 20},
            "impulse_cycle": {
                "owner": "ImpulseCycleEngine",
                "cycle_id": "CYCLE-1",
                "origin_bos_index": 8,
                "direction": "BEARISH",
            },
            "protection": {
                "owner": "DecisionProtectionSelector",
                "cycle_id": "CYCLE-1",
                "index": 6,
                "level": 110.0,
                "selection_policy": "ORIGIN_DEFENDING_SWING",
            },
            "retracement": {
                "as_of_index": 20,
                "trend": "BEARISH",
                "protected_swing_invalidation": {
                    "index": 20,
                    "body_close_crossed": True,
                    "wick_only": False,
                },
            },
        }
        result = reproduce_protection_invalidation(
            snapshot=snapshot,
            candle={
                "source_index": 20,
                "open": 109.0,
                "high": 112.0,
                "low": 108.0,
                "close": 111.0,
            },
        )
        self.assertTrue(result["canonical_reproduction_result"])

    def test_full_history_contamination_is_rejected(self):
        snapshot = {
            "meta": {"as_of_index": 20},
            "impulse_cycle": {
                "owner": "FullHistoryExporter",
                "cycle_id": "CYCLE-1",
                "direction": "BEARISH",
            },
            "protection": {
                "owner": "DecisionProtectionSelector",
                "cycle_id": "CYCLE-1",
                "level": 110.0,
            },
            "retracement": {
                "as_of_index": 20,
                "protected_swing_invalidation": {
                    "index": 20,
                    "body_close_crossed": True,
                    "wick_only": False,
                },
            },
        }
        result = reproduce_protection_invalidation(
            snapshot=snapshot,
            candle={
                "source_index": 20,
                "open": 109.0,
                "high": 112.0,
                "low": 108.0,
                "close": 111.0,
            },
        )
        self.assertFalse(result["canonical_source"])
        self.assertFalse(result["canonical_reproduction_result"])
