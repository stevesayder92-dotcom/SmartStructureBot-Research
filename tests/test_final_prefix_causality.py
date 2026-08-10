from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path
import unittest

import pandas as pd

from core.fidelity_patch import simulate_patched_profit_management
from core.prefix_causality import (
    CausalInvarianceTester,
    CausalSwingLedger,
    PrefixParentViabilityStateMachine,
    build_prefix_trail_and_opposing_events,
    causal_swings_at,
    evaluate_reentry_candidate_at,
)
from core.presimulator_repair import (
    HybridRepairConfig,
    StrategicReentryCoordinator,
    causal_partial_decision,
    chronological_sequence_equity,
)


ROOT = Path(__file__).resolve().parents[1]


def _frame(*, seconds: int = 60) -> pd.DataFrame:
    closes = [100.0, 101.0, 100.8, 100.0, 98.0, 100.0, 102.0, 100.4, 99.8, 103.0, 103.4, 102.8]
    rows = []
    for index, close in enumerate(closes):
        opened = close - 0.45 if index in {1, 5, 6, 9, 10} else close + 0.15
        rows.append({
            "time": 10_000 + index * seconds,
            "open": opened,
            "high": max(opened, close) + 0.25,
            "low": min(opened, close) - 0.25,
            "close": close,
        })
    return pd.DataFrame(rows)


def _suffix(kind: str, *, seconds: int = 60, start: float = 20_000, count: int = 20) -> pd.DataFrame:
    rows = []
    price = 103.0
    for index in range(count):
        if kind == "HIGH":
            close = price + (50.0 if index == 2 else index * 0.2)
        elif kind == "LOW":
            close = price - (50.0 if index == 2 else index * 0.2)
        elif kind == "REVERSAL":
            close = price - index * 4.0
        elif kind == "COMPRESSION":
            close = price + (0.02 if index % 2 else -0.02)
        else:
            close = price + ((index % 4) - 1.5) * 0.25
        rows.append({"time": start + index * seconds, "open": close - 0.05,
                     "high": close + 0.2, "low": close - 0.2, "close": close})
    return pd.DataFrame(rows)


def _parent() -> dict:
    return {
        "parent_setup_id": "PARENT|1",
        "retracement_id": "RET|1",
        "impulse_cycle_id": "IMP|1",
        "direction": "BULLISH",
        "dominant_protection_level": 90.0,
        "dominant_protection_intact_at_failure": True,
    }


def _swing_signature(data: pd.DataFrame, as_of: int, timeframe: str) -> list[tuple]:
    return [(event["swing_id"], event["classification_at_confirmation"], event["price"])
            for event in causal_swings_at(data, as_of_index=as_of, timeframe=timeframe)]


class FinalPrefixCausalityTest(unittest.TestCase):
    def _machine(self):
        m1 = _frame()
        m5 = _frame(seconds=300)
        failure = float(m1.iloc[2]["time"]) + 60
        return PrefixParentViabilityStateMachine(
            parent=_parent(), failure_time=failure, m1_data=m1, m5_data=m5,
            parent_expiry_minutes=360, meaningful_reset_atr=0.35,
        ), m1, m5, failure

    def _candidate(self, data: pd.DataFrame, timeframe: str, index: int):
        seconds = 60 if timeframe == "M1" else 300
        failure = float(data.iloc[2]["time"]) + seconds
        ledger = CausalSwingLedger(data, timeframe=timeframe, sensitivity=2)
        ledger.process_through(index)
        return evaluate_reentry_candidate_at(
            data=data, ledger=ledger, timeframe=timeframe, direction="BULLISH",
            index=index, failure_time=failure, parent_setup_id="PARENT|1",
            parent_retracement_id="RET|1", extension_proven_at_time=failure,
            require_child_reset=timeframe == "M1", original_trigger_index=None,
            original_trigger_price=None, meaningful_reset_atr=0.35,
            freshness_candles=12,
        )

    def test_parent_viability_never_scans_beyond_current_index(self):
        machine, m1, _, failure = self._machine()
        ledger = CausalSwingLedger(m1, timeframe="M1", sensitivity=2)
        for index in range(3, 6):
            machine.update(timeframe="M1", index=index, event_time=float(m1.iloc[index]["time"]) + 60,
                           newly_confirmed_swings=ledger.process_through(index))
        self.assertIsNone(machine.extension_event)
        self.assertTrue(all(event["prefix_rows_used"] <= event["event_index"] + 1 for event in machine.timeline))

    def test_extension_proof_has_precise_causal_availability_candle(self):
        machine, m1, _, _ = self._machine()
        ledger = CausalSwingLedger(m1, timeframe="M1", sensitivity=2)
        for index in range(3, 7):
            machine.update(timeframe="M1", index=index, event_time=float(m1.iloc[index]["time"]) + 60,
                           newly_confirmed_swings=ledger.process_through(index))
        self.assertEqual(machine.extension_event["extension_proven_at_index"], 6)

    def test_candidate_before_extension_proof_remains_invalid_permanently(self):
        data = _frame()
        self.assertIsNone(self._candidate(data, "M1", 5))

    def test_future_extension_cannot_retroactively_validate_old_candidate(self):
        data = _frame()
        prefix_result = self._candidate(data.iloc[:6].copy(), "M1", 5)
        full_result = self._candidate(pd.concat([data.iloc[:6], _suffix("LOW")], ignore_index=True), "M1", 5)
        self.assertEqual(prefix_result, full_result)

    def test_m1_swing_classification_is_prefix_invariant(self):
        data = _frame()
        expected = _swing_signature(data.iloc[:10], 9, "M1")
        for kind in ("HIGH", "LOW", "REVERSAL", "COMPRESSION", "MICRO"):
            combined = pd.concat([data.iloc[:10], _suffix(kind)], ignore_index=True)
            self.assertEqual(expected, _swing_signature(combined, 9, "M1"))

    def test_m5_swing_classification_is_prefix_invariant(self):
        data = _frame(seconds=300)
        expected = _swing_signature(data.iloc[:10], 9, "M5")
        combined = pd.concat([data.iloc[:10], _suffix("HIGH", seconds=300)], ignore_index=True)
        self.assertEqual(expected, _swing_signature(combined, 9, "M5"))

    def test_m1_reentry_trigger_is_suffix_invariant(self):
        data = _frame()
        expected = self._candidate(data, "M1", 9)
        combined = pd.concat([data.iloc[:10], _suffix("REVERSAL")], ignore_index=True)
        actual = self._candidate(combined, "M1", 9)
        self.assertEqual(None if expected is None else expected["trigger_id"], None if actual is None else actual["trigger_id"])

    def test_m5_reentry_trigger_is_suffix_invariant(self):
        data = _frame(seconds=300)
        expected = self._candidate(data, "M5", 9)
        combined = pd.concat([data.iloc[:10], _suffix("LOW", seconds=300)], ignore_index=True)
        actual = self._candidate(combined, "M5", 9)
        self.assertEqual(None if expected is None else expected["trigger_id"], None if actual is None else actual["trigger_id"])

    def test_reentry_owner_is_suffix_invariant(self):
        m1, m5 = _frame(), _frame(seconds=300)
        failure = float(m1.iloc[2]["time"]) + 60
        end = float(m1.iloc[-1]["time"]) + 60
        coordinator = StrategicReentryCoordinator()
        first = coordinator.evaluate(parent=_parent(), failure_time=failure, review_end_time=end, m1_data=m1, m5_data=m5)
        extended_m1 = pd.concat([m1, _suffix("REVERSAL", start=50_000)], ignore_index=True)
        extended_m5 = pd.concat([m5, _suffix("HIGH", seconds=300, start=50_000)], ignore_index=True)
        second = coordinator.evaluate(parent=_parent(), failure_time=failure, review_end_time=end, m1_data=extended_m1, m5_data=extended_m5)
        self.assertEqual(first["selected_owner"], second["selected_owner"])

    def test_attempt2_initial_stop_is_suffix_invariant(self):
        data = _frame()
        expected = self._candidate(data, "M1", 9)
        combined = pd.concat([data.iloc[:10], _suffix("HIGH")], ignore_index=True)
        actual = self._candidate(combined, "M1", 9)
        self.assertEqual(None if expected is None else expected["logical_stop"], None if actual is None else actual["logical_stop"])

    def test_attempt2_trail_candidates_are_prefix_causal(self):
        data = _frame()
        trails, _ = build_prefix_trail_and_opposing_events(data, direction="BULLISH", initial_stop=95,
                                                           attempt_id="A2", timeframe="M1")
        self.assertTrue(all(event["candidate_confirmed_at"] <= event["trail_committed_at"] for event in trails))

    def test_attempt2_proof_bos_is_prefix_causal(self):
        trails, _ = build_prefix_trail_and_opposing_events(_frame(), direction="BULLISH", initial_stop=95,
                                                           attempt_id="A2", timeframe="M1")
        self.assertTrue(all(event["proof_bos_available_at"] == event["current_as_of_index"] for event in trails))

    def test_trail_commitment_is_suffix_invariant(self):
        prefix = _frame().iloc[:10].copy()
        expected, _ = build_prefix_trail_and_opposing_events(prefix, direction="BULLISH", initial_stop=95,
                                                             attempt_id="A2", timeframe="M1")
        combined = pd.concat([prefix, _suffix("LOW")], ignore_index=True)
        actual, _ = build_prefix_trail_and_opposing_events(combined, direction="BULLISH", initial_stop=95,
                                                           attempt_id="A2", timeframe="M1")
        actual_prefix = [event for event in actual if event["trail_committed_at"] <= 9]
        self.assertEqual(expected, actual_prefix)

    def test_target_state_at_index_is_suffix_invariant(self):
        data = _frame()
        def decision(frame, as_of):
            result = simulate_patched_profit_management(direction="BULLISH", entry_price=100, initial_stop=95,
                emergency_stop=94, candles=frame.iloc[:as_of+1], tp1_target=102)
            return {"target_state": result["history"][-1]["target_state"]}
        audit = CausalInvarianceTester.compare(decision_fn=decision, prefix=data.iloc[:10],
            suffixes=[_suffix("HIGH"), _suffix("LOW")], as_of_index=9, fields=["target_state"])
        self.assertTrue(audit["suffix_invariant"])

    def test_partial_decision_at_index_is_suffix_invariant(self):
        history = [{"index": 1, "target_state": "WICK_TOUCHED", "close": 1.0}]
        self.assertEqual(causal_partial_decision(history), causal_partial_decision(history + [{"index": 2, "target_state": "REJECTED", "close": 0.5}]))

    def test_management_action_at_index_is_suffix_invariant(self):
        data = _frame()
        def action(frame):
            result = simulate_patched_profit_management(direction="BULLISH", entry_price=100, initial_stop=95,
                emergency_stop=94, candles=frame.iloc[:10], tp1_target=102)
            return result["history"][-1]["decision"]
        self.assertEqual(action(data), action(pd.concat([data.iloc[:10], _suffix("REVERSAL")], ignore_index=True)))

    def test_sequence_equity_at_index_is_suffix_invariant(self):
        attempt = {"attempt_number": 1, "final_R": 0.5, "history": [{"index": 0, "giveback": {"current_R": 0.0}}, {"index": 1, "giveback": {"current_R": 0.5}}]}
        before = chronological_sequence_equity(parent_setup_id="P", attempt_1=attempt)
        after = chronological_sequence_equity(parent_setup_id="P", attempt_1={**attempt, "history": attempt["history"] + [{"index": 2, "giveback": {"current_R": -5}}]})
        self.assertEqual(before["sequence_equity_curve"][:2], after["sequence_equity_curve"][:2])

    def test_full_future_reversal_cannot_change_earlier_action(self):
        data = _frame().iloc[:10].copy()
        before = simulate_patched_profit_management(direction="BULLISH", entry_price=100, initial_stop=95,
            emergency_stop=94, candles=data, tp1_target=102)["history"][-1]["decision"]
        combined = pd.concat([data, _suffix("REVERSAL")], ignore_index=True)
        after = simulate_patched_profit_management(direction="BULLISH", entry_price=100, initial_stop=95,
            emergency_stop=94, candles=combined.iloc[:10], tp1_target=102)["history"][-1]["decision"]
        self.assertEqual(before, after)

    def test_trade_51_chronological_regression(self):
        with (ROOT / "research_data_sync" / "sequence_elite_source.pkl").open("rb") as handle:
            pool, datasets, _ = pickle.load(handle)
        baseline = json.loads((ROOT / "test_data" / "final_fidelity_patch_v1_population.json").read_text(encoding="utf-8"))
        setup = baseline["rows"][50]["parent_m5_setup_id"]
        row = next(item for item in pool if item["parent_m5_setup_id"] == setup)
        failure = row["outcome"]["first_failure_time"]
        parent = {"parent_setup_id": setup, "retracement_id": row["parent_m5_retracement_id"],
                  "impulse_cycle_id": row["parent_impulse_cycle_id"], "direction": row["direction"],
                  "dominant_protection_level": row["dominant_protection_level"],
                  "dominant_protection_intact_at_failure": True}
        result = StrategicReentryCoordinator().evaluate(parent=parent, failure_time=float(failure),
            review_end_time=float(row["outcome"]["review_end_time"]), m1_data=datasets[row["symbol"]]["M1"],
            m5_data=datasets[row["symbol"]]["M5"], original_trigger_index=row.get("m1_failure_trigger_index"),
            original_trigger_price=row.get("m1_failure_trigger_price"))
        self.assertTrue(result["parent_state_timeline"])
        if result["winner"]:
            self.assertGreaterEqual(result["winner"]["entry_time"], result["extension_proven_at_time"])

    def test_frozen_60_first_entry_population_remains_unchanged(self):
        baseline = json.loads((ROOT / "test_data" / "final_fidelity_patch_v1_population.json").read_text(encoding="utf-8"))
        setup_ids = [row["parent_m5_setup_id"] for row in baseline["rows"]]
        digest = hashlib.sha256("\n".join(setup_ids).encode("utf-8")).hexdigest()
        self.assertEqual(len(setup_ids), 60)
        self.assertEqual(digest, "ba994b6aa0cbdd899851944000b79dd903e63b92497e5b58627997151a255476")

    def test_no_future_data(self):
        source = (ROOT / "core" / "prefix_causality.py").read_text(encoding="utf-8")
        self.assertNotIn("future_window", source)
        self.assertNotIn("as_of_index=len(", source)

    def test_no_unfinished_bars(self):
        event = causal_swings_at(_frame(), as_of_index=6, timeframe="M1")[-1]
        self.assertLessEqual(event["available_at_index"], 6)

    def test_no_duplicate_first_entries(self):
        baseline = json.loads((ROOT / "test_data" / "final_fidelity_patch_v1_population.json").read_text(encoding="utf-8"))
        ids = [row["parent_m5_setup_id"] for row in baseline["rows"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_maximum_one_reentry(self):
        self.assertEqual(HybridRepairConfig().maximum_reentries, 1)

    def test_no_order_apis(self):
        source = (ROOT / "core" / "prefix_causality.py").read_text(encoding="utf-8")
        self.assertNotIn("order_send(", source)


if __name__ == "__main__":
    unittest.main()
