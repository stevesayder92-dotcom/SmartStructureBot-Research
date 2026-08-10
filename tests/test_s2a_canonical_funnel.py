from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import ast
import unittest

import pandas as pd

from core.expert_strategy import confirmed_swings
from core.pipeline_runner import PipelineOptions, run_pipeline
from core.synchronized_m1_replay import validate_closed_series
from simulator.audit.canonical_entry_funnel import (
    CanonicalEntryFunnelObserver,
    UNAVAILABLE,
    classify_m1_event,
)
from simulator.models.schema import stable_hash


ROOT = Path(__file__).resolve().parents[1]


def candles(rows: int = 50) -> pd.DataFrame:
    values = []
    for index in range(rows):
        base = 100.0 + index * 0.08
        wave = (index % 7 - 3) * 0.12
        open_price = base + wave
        close = open_price + (0.06 if index % 2 == 0 else -0.03)
        values.append(
            {
                "time": 1_800_000_000.0 + index * 300.0,
                "open": open_price,
                "high": max(open_price, close) + 0.25,
                "low": min(open_price, close) - 0.25,
                "close": close,
                "tick_volume": 100,
            }
        )
    return pd.DataFrame(values)


def m1_candles(rows: int = 250) -> pd.DataFrame:
    frame = candles(rows)
    frame["time"] = 1_800_000_000.0 + frame.index * 60.0
    return frame


def candidate(setup_id: str, entry_index: int = 20) -> dict:
    return {
        "setup_id": setup_id,
        "direction": "BULLISH",
        "anchor": {
            "index": 8,
            "level": 100.2,
            "side": "HIGH",
            "classification": "HH",
            "confirmed_at_index": 11,
        },
        "counter": {
            "index": 12,
            "level": 99.8,
            "side": "LOW",
            "classification": "HL",
            "confirmed_at_index": 15,
        },
        "trigger": {
            "index": 16,
            "level": 100.1,
            "side": "HIGH",
            "confirmed_at_index": 19,
        },
        "origin_bos": {
            "index": 6,
            "price": 100.0,
            "direction": "BULLISH",
            "type": "BULLISH_BODY_CLOSE_BOS",
            "causal_valid": True,
        },
        "logical_stop_structure": {
            "index": 12,
            "level": 99.8,
            "confirmed_at_index": 15,
        },
        "qualified_at": 19,
        "entry_index": entry_index,
        "entry_price": 101.5,
        "stop_level": 99.7,
        "fibonacci": {
            "available": True,
            "causal_valid": True,
            "fib_zero_index": 6,
            "fib_zero_price": 99.0,
            "fib_hundred_index": 8,
            "fib_hundred_price": 101.0,
            "retracement_depth_ratio": 0.5,
            "zone": "PRIMARY_SWEET_SPOT",
        },
    }


def context() -> dict:
    return {
        "available": True,
        "availability": "AVAILABLE",
        "state": "ALIGNED_BULLISH",
        "approved_direction": "BULLISH",
        "owner": "HTFContextEngine",
        "causal_valid": True,
        "hard_block": False,
        "reasons": ["Synthetic causal context"],
    }


def parent(setup_id: str) -> dict:
    return {
        "owner": "SystemStateDirector",
        "state": "M5_PARENT_ACTIVE",
        "parent_m5_setup_id": setup_id,
        "active_time": 1_800_000_000.0 + 15 * 300 + 300,
        "armed_time": 1_800_000_000.0 + 11 * 300 + 300,
        "dominant_protection_level": 99.0,
        "dominant_protection_intact": True,
        "causal_valid": True,
        "closed_candles_only": True,
    }


def snapshot(setup_id: str, entry_index: int = 20) -> dict:
    return {
        "entry": {
            "ready": True,
            "available": True,
            "state": "ENTRY_VALIDATED",
            "setup_id": setup_id,
            "direction": "BULLISH",
            "index": entry_index,
            "price": 101.5,
            "causal": True,
        },
        "validation": {
            "state": "ENTRY_ALLOWED",
            "allowed": True,
            "owner": "StructureValidator",
        },
        "decision": {"action": "ENTER_TRADE"},
        "execution": {"action": "PAPER_SIGNAL"},
        "management": {"sequence_id": setup_id},
    }


class PhaseS2ACanonicalFunnelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.m5 = candles()
        self.m1 = m1_candles()

    def observe(
        self,
        observer: CanonicalEntryFunnelObserver,
        setup_id: str,
        rejections: list[dict] | None = None,
    ) -> None:
        observer.observe(
            symbol="TEST#",
            candidate=candidate(setup_id),
            context=context(),
            m5_data=self.m5,
            m1_data=self.m1,
            parent=parent(setup_id),
            m1_report={
                "state": "ACTIVE",
                "owner": "M1ChildStructureEngine",
                "entry_ready": False,
                "m1_was_monitored": True,
                "rejections": rejections or [],
                "causal_valid": True,
                "closed_candles_only": True,
                "future_data_used": False,
            },
            director_snapshot=snapshot(setup_id),
            director_action={"committed_action": "ENTER_M5"},
            paper_result={"canonical": {"primary_execution_action": "PAPER_ORDER_FILLED"}},
        )

    def test_observer_does_not_mutate_canonical_inputs(self):
        source = candidate("SETUP-1")
        original = deepcopy(source)
        observer = CanonicalEntryFunnelObserver()
        observer.observe(
            symbol="TEST#",
            candidate=source,
            context=context(),
            m5_data=self.m5,
            m1_data=self.m1,
        )
        self.assertEqual(source, original)
        self.assertTrue(observer.summary()["integrity"]["observer_non_mutation"])

    def test_exact_funnel_count_reconciliation(self):
        observer = CanonicalEntryFunnelObserver()
        self.observe(observer, "SETUP-1")
        self.observe(observer, "SETUP-2")
        summary = observer.summary()
        self.assertEqual(len(observer.funnel_rows), 2 * len(observer.STAGES))
        self.assertTrue(summary["integrity"]["funnel_count_reconciles"])
        self.assertTrue(summary["integrity"]["unique_setup_count_reconciles"])

    def test_every_setup_has_explainable_lifecycle(self):
        observer = CanonicalEntryFunnelObserver()
        self.observe(observer, "SETUP-1")
        self.assertTrue(observer.setup_rows[0]["lifecycle_explainable"])
        stages = {row["current_pipeline_stage"] for row in observer.funnel_rows}
        self.assertEqual(stages, set(observer.STAGES))

    def test_multiple_m1_events_are_not_multiple_setups(self):
        observer = CanonicalEntryFunnelObserver()
        duplicate = {
            "state": "M1_TRIGGER_BEFORE_PARENT_ACTIVE_REJECTED",
            "m1_index": 20,
            "hard_blockers": ["M5_PARENT_NOT_ACTIVE"],
        }
        self.observe(observer, "SETUP-1", [duplicate, deepcopy(duplicate)])
        summary = observer.summary()
        self.assertEqual(summary["counts"]["candidate_setups"], 1)
        self.assertEqual(summary["counts"]["m1_events"], 1)
        self.assertEqual(
            summary["answers"]["unique_setups_affected_by_early_triggers"], 1
        )

    def test_parent_active_timing_classification(self):
        self.assertEqual(
            classify_m1_event("M1_TRIGGER_BEFORE_PARENT_ACTIVE_REJECTED"),
            "M1_TRIGGER_SIDE_SWING_BEFORE_PARENT_ACTIVE",
        )
        self.assertEqual(
            classify_m1_event("M1_ENTRY_FOUND"),
            "M1_TRIGGER_WHILE_PARENT_ACTIVE",
        )
        self.assertEqual(
            classify_m1_event("M1_WICK_ONLY_BOS_REJECTED"),
            "M1_TRIGGER_WICK_ONLY",
        )

    def test_missing_canonical_metric_is_unavailable_not_substituted(self):
        observer = CanonicalEntryFunnelObserver()
        self.observe(observer, "SETUP-1")
        timing = observer.parent_rows[0]
        self.assertEqual(timing["significance_score"], UNAVAILABLE)
        self.assertEqual(timing["protected_structure_index"], UNAVAILABLE)
        self.assertNotEqual(timing["fib_zero_index"], UNAVAILABLE)

    def test_deterministic_observer_replay(self):
        first = CanonicalEntryFunnelObserver()
        second = CanonicalEntryFunnelObserver()
        self.observe(first, "SETUP-1")
        self.observe(second, "SETUP-1")
        self.assertEqual(stable_hash(first.summary()), stable_hash(second.summary()))
        self.assertEqual(stable_hash(first.funnel_rows), stable_hash(second.funnel_rows))

    def test_suffix_invariance_of_earlier_pipeline_decision(self):
        data = candles(70)
        approved = {
            **context(),
            "frames": {},
            "votes": {"BULLISH": 2, "BEARISH": 0, "NEUTRAL": 1},
            "risk_modifier": 1.0,
            "as_of_index": 39,
        }
        options = PipelineOptions(strategy_model="EXPERT_SPEC_V1", engine_sensitivity=3)
        prefix = run_pipeline(
            data=data.iloc[:40].copy(),
            symbol="TEST#",
            timeframe="M5",
            as_of_index=39,
            options=options,
            higher_timeframe_context=approved,
        )
        suffix_hidden = run_pipeline(
            data=data,
            symbol="TEST#",
            timeframe="M5",
            as_of_index=39,
            options=options,
            higher_timeframe_context=approved,
        )
        # Source-row provenance is allowed to report that a hidden suffix
        # exists; every strategy/Director root must remain identical.
        prefix_decision = {
            key: value for key, value in prefix.snapshot.items() if key != "meta"
        }
        suffix_decision = {
            key: value
            for key, value in suffix_hidden.snapshot.items()
            if key != "meta"
        }
        self.assertEqual(stable_hash(prefix_decision), stable_hash(suffix_decision))

    def test_swing_availability_timestamp_is_respected(self):
        data = pd.DataFrame(
            [
                {"time": i * 300, "open": 1, "high": high, "low": 0, "close": 1}
                for i, high in enumerate([1, 2, 3, 8, 3, 2, 1, 2])
            ]
        )
        before = confirmed_swings(data, as_of_index=5, sensitivity=3)
        after = confirmed_swings(data, as_of_index=6, sensitivity=3)
        self.assertFalse(any(point["index"] == 3 for point in before))
        swing = next(point for point in after if point["index"] == 3)
        self.assertEqual(swing["available_at_index"], 6)

    def test_unfinished_candle_is_rejected_by_audit_data_contract(self):
        data = candles(4)
        decision_time = float(data.iloc[-1]["time"]) + 299.0
        report = validate_closed_series(
            data, timeframe_seconds=300, decision_time=decision_time
        )
        self.assertFalse(report["valid"])
        self.assertEqual(report["unfinished_candles"], 1)

    def test_audit_modules_contain_no_order_send_call(self):
        targets = [
            ROOT / "simulator" / "audit" / "canonical_entry_funnel.py",
            ROOT / "tools" / "run_s2a_canonical_audit.py",
        ]
        calls = []
        for path in targets:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else node.func.id
                    if isinstance(node.func, ast.Name)
                    else ""
                )
                if name in {"order_send", "OrderSend"}:
                    calls.append((path.name, node.lineno))
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
