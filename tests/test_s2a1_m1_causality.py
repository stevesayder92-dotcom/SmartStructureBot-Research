from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import ast
import unittest

import pandas as pd

from core.fidelity_patch import M1EntryQualityEngine
from core.synchronized_m1_replay import (
    _first_body_close,
    arbitrate_first_valid_entry,
    build_parent_contract,
    causal_parent_snapshot,
    evaluate_armed_to_active_shadow,
    find_m1_child_entry,
)
from simulator.audit.canonical_entry_funnel import classify_m1_event
from simulator.models.schema import stable_hash
from tests.test_final_fidelity_contract import m1_sequence
from tests.test_s2a_canonical_funnel import candidate, candles


def _m1_prefix() -> pd.DataFrame:
    return pd.DataFrame(
        [
            (0, 103.0, 103.3, 102.7, 102.8),
            (60, 102.8, 102.9, 102.0, 102.2),
            (120, 102.2, 102.4, 101.4, 101.6),
            (180, 101.6, 102.0, 101.3, 101.9),
            (240, 101.9, 102.4, 101.8, 102.3),
            (300, 102.3, 102.7, 102.2, 102.5),
        ],
        columns=["time", "open", "high", "low", "close"],
    )


def _parent(**future_m5: float) -> dict:
    return {
        "parent_m5_setup_id": "TEST#|M5|SETUP|1",
        "parent_m5_retracement_id": "TEST#|M5|SETUP|1|RETRACEMENT|1",
        "parent_impulse_cycle_id": "TEST#|M5|IMPULSE|1|2|BULLISH",
        "parent_direction": "BULLISH",
        "parent_protected_structure_id": "TEST#|M5|PROTECTION|1",
        "parent_fib_anchor_version": "TEST",
        "fibonacci_zone": "38_2_TO_61_8_REMAINING",
        "fib_hundred_price": 110.0,
        "m5_entry_index": 6,
        "m5_emergency_stop": 97.0,
        **future_m5,
    }


def _decision_snapshot(parent: dict) -> dict:
    data = _m1_prefix()
    quality = M1EntryQualityEngine().evaluate(
        data=data,
        parent=parent,
        initial_index=0,
        counter_index=2,
        trigger_index=4,
        trigger_available_index=4,
        entry_index=5,
        trigger_level=102.4,
        entry_price=102.5,
        logical_stop=101.6,
        local_atr=1.0,
        internal_swings=3,
        overlap_ratio=0.5,
    )
    child = {
        "state": "M1_ENTRY_FOUND",
        "entry_ready": True,
        "entry_timeframe": "M1",
        "entry_index": 5,
        "entry_time": 360.0,
        "entry_price": 102.5,
        "logical_stop": 101.6,
        "stop_distance_m1": 0.9,
        "causal_valid": True,
    }
    m1_result = {
        "entry_ready": not quality["observe_only"],
        "entry": child if not quality["observe_only"] else None,
        "m1_was_monitored": True,
        "rejections": [],
    }
    arbitration = arbitrate_first_valid_entry(
        parent=parent,
        m1_result=m1_result,
        decision_time=360.0,
    )
    return {
        "m1_quality_score": quality["m1_quality_score"],
        "grade": quality["grade"],
        "research_policy": quality["research_policy"],
        "observe_only": quality["observe_only"],
        "entry_ready": m1_result["entry_ready"],
        "selected_entry": deepcopy(arbitration["entry"]),
        "logical_stop": arbitration["entry"].get("logical_stop"),
        "arbitration_result": {
            "state": arbitration["state"],
            "entry_owner": arbitration["entry_owner"],
            "m5_entry_avoided_due_to_prior_m1": arbitration[
                "m5_entry_avoided_due_to_prior_m1"
            ],
        },
    }


class PhaseS2A1PreRepairRegression(unittest.TestCase):
    def test_future_m5_outcome_cannot_change_earlier_m1_decision(self):
        prefix = _m1_prefix()
        before = _decision_snapshot(
            _parent(m5_entry_time=1800.0, m5_entry_price=106.0, m5_logical_stop=98.0)
        )
        mutated_future = prefix.copy()
        # The complete M1 prefix through its legal close at T=360 is unchanged.
        # Only hypothetical M5 outcome facts after T differ.
        self.assertTrue(prefix.equals(mutated_future))
        after = _decision_snapshot(
            _parent(m5_entry_time=420.0, m5_entry_price=102.6, m5_logical_stop=101.0)
        )
        self.assertEqual(before, after)


def _candidate_for_path() -> dict:
    result = candidate("TEST#|M5|S2A1|1", 20)
    result["fibonacci"].update(
        fib_zero_price=95.0,
        fib_hundred_price=105.0,
    )
    return result


def _path_inputs(*, early: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    m5 = candles(50)
    source = _candidate_for_path()
    parent = build_parent_contract(candidate=source, m5_data=m5, symbol="TEST#")
    m1 = m1_sequence()
    m1["time"] = m1["time"] + (
        parent["armed_time"] if early else parent["active_time"] - 180.0
    )
    return m5, m1, source


def _complete_path(
    *, m5: pd.DataFrame, m1: pd.DataFrame, source: dict, decision_time: float
) -> dict:
    parent = build_parent_contract(candidate=source, m5_data=m5, symbol="TEST#")
    child = find_m1_child_entry(
        parent=parent,
        m1_data=m1,
        sensitivity=1,
        decision_time=decision_time,
    )
    arbitration = arbitrate_first_valid_entry(
        parent=parent,
        m1_result=child,
        decision_time=decision_time,
    )
    entry = dict(child.get("entry") or {})
    quality = dict(entry.get("quality") or {})
    return {
        "trigger": {
            "index": entry.get("failure_trigger_index"),
            "available": entry.get("failure_trigger_available_at_index"),
            "price": entry.get("failure_trigger_price"),
        },
        "entry_ready": child.get("entry_ready"),
        "entry_index": entry.get("entry_index"),
        "entry_price": entry.get("entry_price"),
        "logical_stop": entry.get("logical_stop"),
        "quality_components": quality.get("component_scores"),
        "quality_total": quality.get("m1_quality_score"),
        "grade": quality.get("grade"),
        "policy": quality.get("research_policy"),
        "entry_owner": arbitration.get("entry_owner"),
        "arbitration": {
            "state": arbitration.get("state"),
            "entry": arbitration.get("entry"),
            "m1_gate_closed": arbitration.get("m1_gate_closed"),
        },
    }


class PhaseS2A1CausalityRepairTests(unittest.TestCase):
    def test_causal_parent_snapshot_contains_no_post_t_fact(self):
        m5, m1, source = _path_inputs()
        parent = build_parent_contract(candidate=source, m5_data=m5, symbol="TEST#")
        decision_time = float(m1.iloc[-1]["time"]) + 60.0
        snapshot = causal_parent_snapshot(
            parent=parent, m1_data=m1, decision_time=decision_time
        )
        forbidden = {
            "m5_entry_time",
            "m5_entry_index",
            "m5_entry_price",
            "m5_logical_stop",
            "m5_emergency_stop",
            "m5_logical_stop_contract",
            "m5_failure_trigger_index",
            "candidate",
            "retrospective_m5_outcome",
        }
        self.assertFalse(forbidden.intersection(snapshot))
        self.assertEqual(snapshot["post_decision_fields"], [])
        self.assertLessEqual(snapshot["as_of_time"], decision_time)

    def test_complete_m1_path_is_suffix_invariant(self):
        m5, m1, source = _path_inputs()
        parent = build_parent_contract(candidate=source, m5_data=m5, symbol="TEST#")
        decision_time = float(parent["active_time"]) + 360.0
        prefix_m1 = m1[m1["time"] + 60.0 <= decision_time].copy()
        prefix_m5 = m5[m5["time"] + 300.0 <= decision_time].copy()
        # Parent construction still receives the same terminal index, so keep
        # its row count while mutating only candles that close after T.
        run_a = _complete_path(m5=m5, m1=prefix_m1, source=source, decision_time=decision_time)
        suffix_a = pd.concat(
            [prefix_m1, m1[m1["time"] + 60.0 > decision_time]],
            ignore_index=True,
        )
        altered_m1 = suffix_a.copy()
        altered_m1.loc[altered_m1["time"] + 60.0 > decision_time, ["open", "high", "low", "close"]] += 50.0
        altered_m5 = m5.copy()
        post_t = altered_m5["time"] + 300.0 > decision_time
        altered_m5.loc[post_t, ["open", "high", "low", "close"]] += 75.0
        source_b = deepcopy(source)
        source_b["entry_price"] += 75.0
        run_b = _complete_path(m5=m5, m1=suffix_a, source=source, decision_time=decision_time)
        run_c = _complete_path(m5=altered_m5, m1=altered_m1, source=source_b, decision_time=decision_time)
        self.assertEqual(stable_hash(run_a), stable_hash(run_b))
        self.assertEqual(stable_hash(run_a), stable_hash(run_c))
        self.assertGreater(len(m5), len(prefix_m5))

    def test_post_hoc_m5_metrics_cannot_influence_quality(self):
        a = _parent(m5_entry_time=1800.0, m5_entry_price=106.0, m5_logical_stop=98.0)
        b = _parent(m5_entry_time=420.0, m5_entry_price=102.6, m5_logical_stop=101.0)
        qa = _decision_snapshot(a)
        qb = _decision_snapshot(b)
        for field in (
            "m1_quality_score",
            "grade",
            "research_policy",
            "observe_only",
            "entry_ready",
            "logical_stop",
            "arbitration_result",
        ):
            self.assertEqual(qa[field], qb[field])

    def test_shadow_evaluator_does_not_change_canonical_decision(self):
        m5, m1, source = _path_inputs(early=True)
        parent = build_parent_contract(candidate=source, m5_data=m5, symbol="TEST#")
        before_parent = deepcopy(parent)
        canonical_before = find_m1_child_entry(
            parent=parent,
            m1_data=m1,
            sensitivity=1,
            decision_time=float(parent["active_time"]) - 1e-6,
        )
        shadow = evaluate_armed_to_active_shadow(
            parent=parent, m1_data=m1, sensitivity=1
        )
        canonical_after = find_m1_child_entry(
            parent=parent,
            m1_data=m1,
            sensitivity=1,
            decision_time=float(parent["active_time"]) - 1e-6,
        )
        self.assertEqual(canonical_before, canonical_after)
        self.assertEqual(parent, before_parent)
        self.assertTrue(shadow["parent_unchanged"])
        self.assertFalse(shadow["canonical_behavior_changed"])
        self.assertGreaterEqual(shadow["valid_event_count"], 1)

    def test_pre_active_event_is_a_swing_not_a_bos_label(self):
        self.assertEqual(
            classify_m1_event("M1_TRIGGER_SIDE_SWING_BEFORE_PARENT_ACTIVE"),
            "M1_TRIGGER_SIDE_SWING_BEFORE_PARENT_ACTIVE",
        )
        self.assertNotIn(
            "BOS",
            classify_m1_event("M1_TRIGGER_SIDE_SWING_BEFORE_PARENT_ACTIVE"),
        )

    def test_body_close_and_wick_only_protections_are_unchanged(self):
        data = pd.DataFrame(
            [
                (0, 100.0, 101.5, 99.5, 100.5),
                (60, 100.5, 101.6, 100.0, 101.2),
            ],
            columns=["time", "open", "high", "low", "close"],
        )
        entry, rejections = _first_body_close(
            data=data,
            start_index=0,
            end_index=1,
            direction="BULLISH",
            trigger_level=101.0,
        )
        self.assertEqual(entry, 1)
        self.assertEqual(rejections[0]["state"], "M1_WICK_ONLY_BOS_REJECTED")

    def test_s2a1_modules_contain_no_order_send_call(self):
        root = Path(__file__).resolve().parents[1]
        targets = [
            root / "core" / "synchronized_m1_replay.py",
            root / "core" / "fidelity_patch.py",
            root / "tools" / "run_s2a1_causality_audit.py",
        ]
        calls = []
        for path in targets:
            if not path.exists():
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
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
