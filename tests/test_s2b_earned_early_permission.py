from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import ast
import unittest

import pandas as pd

from core.final_fidelity_management import transition_m1_to_m5_management
from core.synchronized_m1_replay import (
    COUNTER_CONFIRMED_ACTIVE,
    EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE,
    M1_STOP_TERMINOLOGY,
    ParentEntryLifecycle,
    _first_body_close,
    arbitrate_first_valid_entry,
    evaluate_armed_to_active_shadow,
    evaluate_m1_permission,
    find_m1_child_entry,
    validate_m1_ownership,
)
from simulator.services.observability import director_decision
from tests.test_final_fidelity_contract import m1_sequence, parent_contract


VARIANT = EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE


def early_parent() -> dict:
    parent = parent_contract()
    parent.update(
        active_time=1200.0,
        m5_entry_time=1800.0,
        m5_entry_price=106.0,
        m5_logical_stop=97.0,
        m5_emergency_stop=96.0,
        causal_htf_ownership_accepted=True,
        parent_invalidated=False,
        parent_superseded=False,
        entry_opportunity_consumed=False,
        maximum_reentries=1,
    )
    return parent


def early_result(
    *, parent: dict | None = None, data: pd.DataFrame | None = None,
    decision_time: float = 600.0, **kwargs,
) -> dict:
    return find_m1_child_entry(
        parent=parent or early_parent(),
        m1_data=data if data is not None else m1_sequence(),
        sensitivity=1,
        decision_time=decision_time,
        permission_policy=VARIANT,
        **kwargs,
    )


def decision_signature(parent: dict, data: pd.DataFrame) -> dict:
    result = early_result(parent=parent, data=data)
    entry = dict(result.get("entry") or {})
    quality = dict(entry.get("quality") or {})
    arbitration = arbitrate_first_valid_entry(
        parent=parent, m1_result=result, decision_time=600.0
    )
    snapshot = {
        "identity": {"entry_owner": arbitration.get("entry_owner")},
        "management": {},
        "entry": {},
        "m1_entry": result,
    }
    director = director_decision(
        snapshot=snapshot,
        event_time=600.0,
        new_entry=entry or None,
    )
    return {
        "parent_id": entry.get("parent_m5_setup_id"),
        "early_permission_state": result.get("early_permission_state"),
        "trigger": (
            entry.get("failure_trigger_index"),
            entry.get("failure_trigger_available_at_index"),
            entry.get("failure_trigger_price"),
        ),
        "bos_valid": bool(entry and not entry.get("wick_only_bos")),
        "quality_components": quality.get("component_scores"),
        "quality_total": quality.get("m1_quality_score"),
        "grade": quality.get("grade"),
        "policy": quality.get("research_policy"),
        "entry_ready": result.get("entry_ready"),
        "entry_index": entry.get("entry_index"),
        "entry_time": entry.get("entry_time"),
        "entry_price": entry.get("entry_price"),
        "logical_stop": entry.get("logical_stop"),
        "emergency_stop": entry.get("emergency_stop"),
        "entry_owner": arbitration.get("entry_owner"),
        "director_action": director.committed_action,
    }


class S2BEarnedEarlyPermissionTests(unittest.TestCase):
    def test_early_m1_cannot_execute_before_parent_armed(self):
        result = early_result(decision_time=59.0)
        self.assertFalse(result["entry_ready"])
        self.assertEqual(result["parent_state_at_decision"], "PARENT_NOT_AVAILABLE")

    def test_parent_armed_alone_does_not_permit_entry(self):
        result = early_result(data=m1_sequence().iloc[:1], decision_time=60.0)
        self.assertFalse(result["entry_ready"])
        self.assertNotEqual(result.get("early_permission_state"), "EARNED")

    def test_valid_m1_counter_structure_is_required(self):
        data = m1_sequence().copy()
        data["high"] = range(101, 101 + len(data))
        data["low"] = range(99, 99 + len(data))
        data["open"] = data["low"] + 0.2
        data["close"] = data["low"] + 0.4
        result = early_result(data=data)
        self.assertFalse(result["entry_ready"])

    def test_complete_m1_sequence_is_required(self):
        parent = early_parent()
        parent["armed_time"] = 240.0
        result = early_result(parent=parent)
        self.assertFalse(result["entry_ready"])
        self.assertTrue(any("INCOMPLETE_SEQUENCE" in r["state"] for r in result["rejections"]))

    def test_wick_only_bos_remains_rejected(self):
        data = pd.DataFrame([(0, 100, 102, 99, 100.5)], columns=["time", "open", "high", "low", "close"])
        entry, rejected = _first_body_close(data=data, start_index=0, end_index=0, direction="BULLISH", trigger_level=101)
        self.assertIsNone(entry)
        self.assertEqual(rejected[0]["state"], "M1_WICK_ONLY_BOS_REJECTED")

    def test_wrong_body_direction_remains_rejected(self):
        data = pd.DataFrame([(0, 102, 102.2, 100, 101.5)], columns=["time", "open", "high", "low", "close"])
        entry, rejected = _first_body_close(data=data, start_index=0, end_index=0, direction="BULLISH", trigger_level=101)
        self.assertIsNone(entry)
        self.assertEqual(rejected[0]["state"], "M1_WRONG_BODY_DIRECTION_REJECTED")

    def test_one_candle_micro_noise_remains_rejected(self):
        result = early_result(minimum_counter_bars=10)
        self.assertFalse(result["entry_ready"])
        self.assertTrue(any("ONE_CANDLE_NOISE" in r["state"] for r in result["rejections"]))

    def test_stale_trigger_remains_rejected(self):
        result = early_result(max_trigger_age=0)
        self.assertFalse(result["entry_ready"])
        self.assertTrue(any("STALE_TRIGGER" in r["state"] for r in result["rejections"]))

    def test_protected_structure_failure_blocks_early_entry(self):
        parent = early_parent()
        parent["dominant_protection_intact"] = False
        result = early_result(parent=parent)
        self.assertFalse(result["entry_ready"])
        self.assertTrue(any("PROTECTION_BROKEN" in r["state"] for r in result["rejections"]))

    def test_unrelated_m1_structure_cannot_hijack_parent(self):
        parent = early_parent()
        child = {key: parent[key] for key in (
            "parent_m5_setup_id", "parent_m5_retracement_id", "parent_impulse_cycle_id",
            "parent_direction", "parent_protected_structure_id", "parent_fib_anchor_version",
        )}
        child["parent_impulse_cycle_id"] = "OTHER"
        self.assertTrue(validate_m1_ownership(parent=parent, child=child)["hard_block"])

    def test_timestamp_proximity_cannot_establish_ownership(self):
        parent = early_parent()
        child = {key: parent[key] for key in (
            "parent_m5_setup_id", "parent_m5_retracement_id", "parent_impulse_cycle_id",
            "parent_direction", "parent_protected_structure_id", "parent_fib_anchor_version",
        )}
        child["parent_m5_setup_id"] = "NEARBY_BUT_UNRELATED"
        self.assertFalse(validate_m1_ownership(parent=parent, child=child)["matched"])

    def test_early_m1_entry_occurs_on_bos_candle_close(self):
        entry = early_result()["entry"]
        data = m1_sequence()
        self.assertEqual(entry["entry_price"], float(data.iloc[entry["entry_index"]]["close"]))
        self.assertEqual(entry["entry_time"], float(data.iloc[entry["entry_index"]]["time"]) + 60.0)

    def test_first_early_m1_consumes_later_m1_m5_attempt1(self):
        result = early_result()
        decision = arbitrate_first_valid_entry(parent=early_parent(), m1_result=result, decision_time=2000.0)
        self.assertEqual(decision["entry_owner"], "M1")
        self.assertTrue(decision["duplicate_m5_entry_blocked"])

    def test_one_parent_still_produces_one_first_entry(self):
        lifecycle = ParentEntryLifecycle("SETUP")
        self.assertTrue(lifecycle.claim(timeframe="M1", event_time=540))
        self.assertFalse(lifecycle.claim(timeframe="M5", event_time=1800))

    def test_existing_one_reentry_limit_remains_one(self):
        lifecycle = ParentEntryLifecycle("SETUP")
        lifecycle.claim(timeframe="M1", event_time=540)
        lifecycle.fail_first_attempt(dominant_protection_intact=True, parent_retracement_valid=True)
        self.assertTrue(lifecycle.claim_reentry(timeframe="M5", event_time=1800))
        self.assertFalse(lifecycle.claim_reentry(timeframe="M1", event_time=1900))
        self.assertEqual(lifecycle.reentry_count, 1)

    def test_m1_logical_stop_uses_existing_contract(self):
        entry = early_result()["entry"]
        self.assertEqual(entry["logical_stop_terminology"], M1_STOP_TERMINOLOGY)
        self.assertEqual(entry["logical_stop"], 98.5)

    def test_post_entry_candles_cannot_rewrite_initial_stop(self):
        prefix = m1_sequence()
        suffix = pd.DataFrame([(600, 1, 999, 0, 500)], columns=prefix.columns[:5])
        for column in prefix.columns[5:]:
            suffix[column] = 0
        extended = pd.concat([prefix, suffix], ignore_index=True)
        self.assertEqual(early_result(data=prefix)["entry"]["logical_stop"], early_result(data=extended)["entry"]["logical_stop"])

    def test_m1_to_m5_transition_never_widens_protection(self):
        result = transition_m1_to_m5_management(direction="BULLISH", current_m1_protection=100, proposed_m5_protection=99, proof_index=10, proof_reason="M5_BOS")
        self.assertEqual(result["selected_level"], 100)
        self.assertEqual(result["management_state"], "TRANSITION_REJECTED_WOULD_LOOSEN")

    def _suffix_signatures(self) -> list[dict]:
        prefix = m1_sequence()
        columns = list(prefix.columns)
        def suffix(rows):
            frame = pd.DataFrame(rows, columns=columns[:5])
            for column in columns[5:]: frame[column] = 0
            return pd.concat([prefix, frame], ignore_index=True)
        parent_e = early_parent()
        parent_e.update(m5_entry_time=3600.0, m5_entry_price=80.0, m5_logical_stop=120.0)
        return [
            decision_signature(early_parent(), prefix),
            decision_signature(early_parent(), suffix([(600, 101, 102, 100, 101)])),
            decision_signature(early_parent(), suffix([(600, 500, 700, 400, 650)])),
            decision_signature(early_parent(), suffix([(600, 101, 102, 1, 2)])),
            decision_signature(parent_e, prefix),
        ]

    def test_future_suffix_cannot_change_early_permission(self):
        values = self._suffix_signatures(); self.assertEqual(len({v["early_permission_state"] for v in values}), 1)

    def test_future_suffix_cannot_change_m1_quality(self):
        values = self._suffix_signatures(); self.assertEqual(len({repr(v["quality_components"]) for v in values}), 1)

    def test_future_suffix_cannot_change_entry_price(self):
        values = self._suffix_signatures(); self.assertEqual(len({v["entry_price"] for v in values}), 1)

    def test_future_suffix_cannot_change_logical_stop(self):
        values = self._suffix_signatures(); self.assertEqual(len({v["logical_stop"] for v in values}), 1)

    def test_future_m5_outcome_cannot_change_early_decision(self):
        values = self._suffix_signatures(); self.assertTrue(all(v == values[0] for v in values))

    def test_first_valid_arbitration_uses_earliest_bos_not_trigger_loop_order(self):
        root = Path(__file__).resolve().parents[1]
        data = pd.read_csv(root / "simulator_data" / "library" / "GOLD" / "M1.csv").iloc[23720:23770].reset_index(drop=True)
        parent = early_parent()
        parent.update(
            parent_m5_setup_id="GOLD_TRIGGER_ORDER_REGRESSION",
            parent_m5_retracement_id="GOLD_TRIGGER_ORDER_REGRESSION|R",
            parent_impulse_cycle_id="GOLD_TRIGGER_ORDER_REGRESSION|I",
            parent_protected_structure_id="GOLD_TRIGGER_ORDER_REGRESSION|P",
            parent_direction="BEARISH",
            armed_time=1784827500.0,
            active_time=1784829900.0,
            m5_entry_time=1784830200.0,
            m5_entry_price=4051.99,
            m5_logical_stop=4057.14,
            m5_emergency_stop=4060.0,
            price_boundary_low=4040.11,
            price_boundary_high=4089.03,
            fib_zero_price=4089.03,
            fib_hundred_price=4040.11,
        )
        result = early_result(parent=parent, data=data, decision_time=1784830200.0)
        self.assertEqual(result["state"], "EARLY_M1_PERMISSION_EARNED")
        self.assertEqual(result["entry"]["entry_time"], 1784829300.0)
        self.assertEqual(result["first_valid_arbitration"]["method"], "EARLIEST_VALID_PREACTIVE_BOS_CLOSE_ACROSS_CAUSALLY_AVAILABLE_TRIGGERS")

    def test_variant_returns_exact_baseline_resolution_after_active(self):
        parent = early_parent()
        parent["active_time"] = 300.0
        baseline = find_m1_child_entry(
            parent=parent,
            m1_data=m1_sequence(),
            sensitivity=1,
            decision_time=600.0,
            permission_policy=COUNTER_CONFIRMED_ACTIVE,
        )
        variant = find_m1_child_entry(
            parent=parent,
            m1_data=m1_sequence(),
            sensitivity=1,
            decision_time=600.0,
            permission_policy=VARIANT,
        )
        self.assertEqual(variant, baseline)

    def test_retrospective_analytics_cannot_enter_entry_calculation(self):
        snapshot = early_result()["entry"]["causal_parent_snapshot"]
        self.assertFalse({"m5_entry_time", "m5_entry_price", "m5_logical_stop", "retrospective_m5_outcome"}.intersection(snapshot))

    def test_baseline_policy_reproduces_s2a1_results(self):
        parent = parent_contract()
        implicit = find_m1_child_entry(parent=parent, m1_data=m1_sequence(), sensitivity=1)
        explicit = find_m1_child_entry(parent=parent, m1_data=m1_sequence(), sensitivity=1, permission_policy=COUNTER_CONFIRMED_ACTIVE)
        self.assertEqual(implicit, explicit)

    def test_shadow_diagnostics_cannot_mutate_director_action(self):
        parent = early_parent(); before = deepcopy(parent)
        canonical = find_m1_child_entry(parent=parent, m1_data=m1_sequence(), sensitivity=1, decision_time=600.0)
        evaluate_armed_to_active_shadow(parent=parent, m1_data=m1_sequence(), sensitivity=1)
        after = find_m1_child_entry(parent=parent, m1_data=m1_sequence(), sensitivity=1, decision_time=600.0)
        self.assertEqual(canonical, after); self.assertEqual(parent, before)

    def test_no_duplicate_first_entry_after_early_m1(self):
        lifecycle = ParentEntryLifecycle("SETUP")
        claims = [lifecycle.claim(timeframe="M1", event_time=540), lifecycle.claim(timeframe="M1", event_time=600), lifecycle.claim(timeframe="M5", event_time=1800)]
        self.assertEqual(claims, [True, False, False])

    def test_no_live_demo_order_api_enabled_or_called(self):
        root = Path(__file__).resolve().parents[1]
        targets = [root / "core" / "synchronized_m1_replay.py", root / "simulator" / "adapters" / "pipeline_adapter.py"]
        calls = []
        for path in targets:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ""
                    if name in {"order_send", "OrderSend"}: calls.append((path.name, node.lineno))
        self.assertEqual(calls, [])
        permission = evaluate_m1_permission(parent=early_parent(), decision_time=600, policy=VARIANT)
        self.assertFalse(permission["live_demo_capable"]); self.assertFalse(permission["order_api_called"])


if __name__ == "__main__":
    unittest.main()
