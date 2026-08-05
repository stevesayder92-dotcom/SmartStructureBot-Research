from __future__ import annotations

from pathlib import Path
import unittest

import pandas as pd

from core.management_evidence import (
    canonical_management_chart_contract,
)
from core.m1_fallback import evaluate_m1_fallback
from core.runtime_config import load_runtime_config
from core.steve_trade_management import (
    SteveManagementConfig,
    SteveTradeManagementEngine,
    emergency_broker_stop,
    logical_invalidation_decision,
    select_setup_logical_invalidation,
    transition_protection_without_loosening,
)


def frame(
    *,
    opens,
    highs,
    lows,
    closes,
    seconds: int = 300,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": [
                1_700_000_000 + index * seconds
                for index in range(len(closes))
            ],
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "tick_volume": [100] * len(closes),
        }
    )


def initial_data() -> pd.DataFrame:
    return frame(
        opens=[92, 96, 100, 101, 102, 103, 104, 103, 102, 101],
        highs=[94, 100, 102, 103, 104, 105, 106, 105, 104, 103],
        lows=[90, 92, 98, 99, 100, 101, 102, 101, 100, 99],
        closes=[92, 98, 101, 102, 103, 104, 105, 104, 103, 102],
    )


def bullish_entry(
    *,
    entry_index: int = 2,
    broad_extreme: float = 85.0,
) -> dict:
    return {
        "setup_id": "PARENT-BULL-1",
        "direction": "BULLISH",
        "entry_index": entry_index,
        "entry_price": 101.0,
        "anchor": {
            "side": "HIGH",
            "index": 0,
            "level": 94.0,
            "confirmed_at_index": 0,
        },
        "counter": {
            "side": "LOW",
            "classification": "LL",
            "index": 0,
            "level": 90.0,
            "confirmed_at_index": 0,
        },
        "trigger": {
            "side": "HIGH",
            "classification": "LH",
            "index": 1,
            "level": 100.0,
            "confirmed_at_index": 1,
        },
        "stop_level": broad_extreme,
    }


def context(
    direction: str = "BULLISH",
    *,
    level: float = 80.0,
) -> dict:
    field = (
        "last_confirmed_low"
        if direction == "BULLISH"
        else "last_confirmed_high"
    )
    return {
        "approved_direction": direction,
        "frames": {
            "M30": {
                "direction": direction,
                field: {
                    "index": 0,
                    "level": level,
                    "confirmed_at_index": 0,
                },
            },
            "M15": {
                "direction": direction,
                field: {
                    "index": 0,
                    "level": (
                        level + 1
                        if direction == "BULLISH"
                        else level - 1
                    ),
                    "confirmed_at_index": 0,
                },
            },
        },
    }


def trail_data() -> pd.DataFrame:
    opens = [92, 97, 100, 102, 103, 104, 103, 103, 104, 104, 104, 106]
    highs = [94, 100, 102, 104, 105, 105, 104, 105, 105, 105, 107, 107]
    lows = [90, 92, 98, 100, 102, 103, 102, 102, 103, 103, 103, 99]
    closes = [92, 98, 101, 103, 104, 104, 103, 104, 104, 104, 106, 100]
    return frame(opens=opens, highs=highs, lows=lows, closes=closes)


def trail_swings() -> list[dict]:
    return [
        {
            "side": "HIGH",
            "classification": "HH",
            "index": 4,
            "level": 105.0,
            "confirmed_at_index": 7,
        },
        {
            "side": "LOW",
            "classification": "HL",
            "index": 6,
            "level": 102.0,
            "confirmed_at_index": 9,
        },
    ]


def bearish_mirror(
    data: pd.DataFrame,
    *,
    ceiling: float = 200.0,
) -> pd.DataFrame:
    result = data.copy()
    result["open"] = ceiling - data["open"]
    result["high"] = ceiling - data["low"]
    result["low"] = ceiling - data["high"]
    result["close"] = ceiling - data["close"]
    return result


class SteveStopContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = SteveManagementConfig()

    # 1
    def test_initial_stop_uses_relevant_pre_bos_structure(self):
        contract = select_setup_logical_invalidation(
            data=initial_data(),
            entry_model=bullish_entry(),
            timeframe="M5",
            config=self.config,
        )
        self.assertEqual(contract["structure_index"], 0)
        self.assertEqual(contract["wick_price"], 90.0)
        expected_body_edge = min(
            initial_data().iloc[0]["open"],
            initial_data().iloc[0]["close"],
        )
        self.assertLess(contract["logical_boundary"], expected_body_edge)
        self.assertLess(contract["available_at_index"], 2)

    # 2
    def test_post_entry_candles_cannot_change_initial_stop(self):
        original = initial_data()
        changed = original.copy()
        changed.loc[3:, "low"] = 10.0
        first = select_setup_logical_invalidation(
            data=original,
            entry_model=bullish_entry(),
            timeframe="M5",
            config=self.config,
        )
        second = select_setup_logical_invalidation(
            data=changed,
            entry_model=bullish_entry(),
            timeframe="M5",
            config=self.config,
        )
        self.assertEqual(
            first["logical_boundary"],
            second["logical_boundary"],
        )
        self.assertFalse(first["post_entry_candles_used"])

    # 3
    def test_broad_pullback_wick_is_rejected_when_irrelevant(self):
        contract = select_setup_logical_invalidation(
            data=initial_data(),
            entry_model=bullish_entry(broad_extreme=85.0),
            timeframe="M5",
            config=self.config,
        )
        self.assertTrue(contract["broad_pullback_extreme_rejected"])
        self.assertNotEqual(
            contract["logical_boundary"],
            contract["broad_pullback_extreme"],
        )

    # 4
    def test_m1_wick_through_logical_level_survives(self):
        contract = select_setup_logical_invalidation(
            data=initial_data(),
            entry_model=bullish_entry(),
            timeframe="M1",
            config=self.config,
        )
        row = pd.Series(
            {"open": 93, "high": 94, "low": 90, "close": 93}
        )
        decision = logical_invalidation_decision(
            row=row,
            direction="BULLISH",
            timeframe="M1",
            contract=contract,
            config=self.config,
        )
        self.assertFalse(decision["invalidated"])
        self.assertTrue(decision["wick_only_survived"])

    # 5
    def test_m1_body_close_beyond_level_invalidates(self):
        contract = select_setup_logical_invalidation(
            data=initial_data(),
            entry_model=bullish_entry(),
            timeframe="M1",
            config=self.config,
        )
        decision = logical_invalidation_decision(
            row=pd.Series(
                {"open": 93, "high": 94, "low": 90, "close": 91}
            ),
            direction="BULLISH",
            timeframe="M1",
            contract=contract,
            config=self.config,
        )
        self.assertTrue(decision["invalidated"])

    # 6
    def test_m5_wick_through_logical_level_survives(self):
        contract = select_setup_logical_invalidation(
            data=initial_data(),
            entry_model=bullish_entry(),
            timeframe="M5",
            config=self.config,
        )
        boundary = contract["logical_boundary"]
        decision = logical_invalidation_decision(
            row=pd.Series(
                {
                    "open": boundary + 1,
                    "high": boundary + 2,
                    "low": boundary - 1,
                    "close": boundary + 0.2,
                }
            ),
            direction="BULLISH",
            timeframe="M5",
            contract=contract,
            config=self.config,
        )
        self.assertFalse(decision["invalidated"])
        self.assertTrue(decision["wick_only_survived"])

    # 7
    def test_m5_small_marginal_close_respects_tolerance(self):
        contract = select_setup_logical_invalidation(
            data=initial_data(),
            entry_model=bullish_entry(),
            timeframe="M5",
            config=self.config,
        )
        boundary = contract["logical_boundary"]
        atr = contract["atr_at_entry"]
        close = boundary - 0.02 * atr
        decision = logical_invalidation_decision(
            row=pd.Series(
                {
                    "open": close + 0.01 * atr,
                    "high": boundary + atr,
                    "low": close - 0.01 * atr,
                    "close": close,
                }
            ),
            direction="BULLISH",
            timeframe="M5",
            contract=contract,
            config=self.config,
        )
        self.assertFalse(decision["invalidated"])
        self.assertTrue(decision["close_beyond_boundary"])

    # 8
    def test_m5_momentum_close_beyond_boundary_invalidates(self):
        contract = select_setup_logical_invalidation(
            data=initial_data(),
            entry_model=bullish_entry(),
            timeframe="M5",
            config=self.config,
        )
        boundary = contract["logical_boundary"]
        atr = contract["atr_at_entry"]
        decision = logical_invalidation_decision(
            row=pd.Series(
                {
                    "open": boundary + 0.4 * atr,
                    "high": boundary + 0.5 * atr,
                    "low": boundary - 0.3 * atr,
                    "close": boundary - 0.2 * atr,
                }
            ),
            direction="BULLISH",
            timeframe="M5",
            contract=contract,
            config=self.config,
        )
        self.assertTrue(decision["invalidated"])
        self.assertGreaterEqual(decision["body_strength_atr"], 0.35)

    # 9
    def test_emergency_stop_is_separate_and_wider(self):
        contract = select_setup_logical_invalidation(
            data=initial_data(),
            entry_model=bullish_entry(),
            timeframe="M5",
            config=self.config,
        )
        emergency = emergency_broker_stop(
            logical_invalidation=contract,
            config=self.config,
        )
        self.assertLess(emergency["price"], contract["logical_boundary"])
        self.assertEqual(
            emergency["protection_role"],
            "EMERGENCY_BROKER_STOP",
        )
        self.assertFalse(emergency["order_api_called"])

    # 10
    def test_raw_post_entry_fractal_cannot_move_trail(self):
        engine = SteveTradeManagementEngine()
        result = engine.evaluate(
            data=trail_data(),
            symbol="GOLD#",
            timeframe="M5",
            as_of_index=9,
            direction="BULLISH",
            context=context(),
            confirmed_swings=trail_swings(),
            canonical_entry=bullish_entry(),
        )
        attempt = result["active_attempt"]
        self.assertEqual(
            attempt["trail_state"],
            "TRAIL_CANDIDATE_UNPROVEN",
        )
        self.assertEqual(
            attempt["current_protection_source"],
            "SETUP_LOGICAL_INVALIDATION",
        )
        self.assertEqual(len(attempt["trail_movements"]), 0)

    # 11
    def test_proven_continuation_hl_moves_buy_protection(self):
        engine = SteveTradeManagementEngine()
        result = engine.evaluate(
            data=trail_data(),
            symbol="GOLD#",
            timeframe="M5",
            as_of_index=10,
            direction="BULLISH",
            context=context(),
            confirmed_swings=trail_swings(),
            canonical_entry=bullish_entry(),
        )
        attempt = result["active_attempt"]
        self.assertEqual(attempt["trail_state"], "TRAIL_MOVED")
        self.assertEqual(attempt["trail_movements"][0]["proof_index"], 10)
        self.assertGreater(attempt["current_protection"], 90.0)

    # 12
    def test_proven_continuation_lh_moves_sell_protection(self):
        data = bearish_mirror(trail_data())
        entry = {
            **bullish_entry(),
            "setup_id": "PARENT-SELL-1",
            "direction": "BEARISH",
            "entry_price": 99.0,
            "counter": {
                "side": "HIGH",
                "classification": "HH",
                "index": 0,
                "level": 110.0,
                "confirmed_at_index": 0,
            },
            "trigger": {
                "side": "LOW",
                "classification": "HL",
                "index": 1,
                "level": 100.0,
                "confirmed_at_index": 1,
            },
            "stop_level": 115.0,
        }
        swings = [
            {
                "side": "LOW",
                "classification": "LL",
                "index": 4,
                "level": 95.0,
                "confirmed_at_index": 7,
            },
            {
                "side": "HIGH",
                "classification": "LH",
                "index": 6,
                "level": 98.0,
                "confirmed_at_index": 9,
            },
        ]
        result = SteveTradeManagementEngine().evaluate(
            data=data,
            symbol="US100Cash#",
            timeframe="M5",
            as_of_index=10,
            direction="BEARISH",
            context=context("BEARISH", level=120.0),
            confirmed_swings=swings,
            canonical_entry=entry,
        )
        attempt = result["active_attempt"]
        self.assertEqual(attempt["trail_state"], "TRAIL_MOVED")
        self.assertLess(attempt["current_protection"], 110.0)

    # 13
    def test_trailing_protection_never_loosens(self):
        transition = transition_protection_without_loosening(
            direction="BULLISH",
            current_level=102.0,
            candidate_m5_level=100.0,
        )
        self.assertEqual(transition["selected_level"], 102.0)
        self.assertFalse(transition["loosened"])

    # 14
    def test_opposing_meaningful_bos_exits(self):
        result = SteveTradeManagementEngine().evaluate(
            data=trail_data(),
            symbol="GOLD#",
            timeframe="M5",
            as_of_index=11,
            direction="BULLISH",
            context=context(),
            confirmed_swings=trail_swings(),
            canonical_entry=bullish_entry(),
        )
        attempt = result["latest_attempt"]
        self.assertEqual(
            attempt["exit_reason"],
            "OPPOSING_MEANINGFUL_BOS",
        )
        self.assertTrue(
            attempt["opposing_bos"]["body_close_confirmed"]
        )

    # 15
    def test_micro_opposing_bos_does_not_force_exit(self):
        data = trail_data().iloc[:11].copy()
        result = SteveTradeManagementEngine().evaluate(
            data=data,
            symbol="GOLD#",
            timeframe="M5",
            as_of_index=10,
            direction="BULLISH",
            context=context(),
            confirmed_swings=trail_swings(),
            canonical_entry=bullish_entry(),
        )
        self.assertEqual(result["active_attempt"]["status"], "ACTIVE")
        self.assertIsNone(result["active_attempt"]["opposing_bos"])

    def _reentry_data(self) -> pd.DataFrame:
        closes = [92, 98, 101, 88, 89, 91, 96, 97, 101, 80]
        opens = [92, 97, 100, 94, 88, 90, 95, 96, 99, 95]
        return frame(
            opens=opens,
            highs=[
                max(o, c) + 1 for o, c in zip(opens, closes)
            ],
            lows=[
                min(o, c) - 1 for o, c in zip(opens, closes)
            ],
            closes=closes,
        )

    def _reentry_swings(self) -> list[dict]:
        return [
            {
                "side": "LOW",
                "classification": "LL",
                "index": 4,
                "level": 87.0,
                "confirmed_at_index": 5,
            },
            {
                "side": "HIGH",
                "classification": "HH",
                "index": 6,
                "level": 97.0,
                "confirmed_at_index": 7,
            },
        ]

    # 16
    def test_first_stop_alone_does_not_arm_reentry(self):
        result = SteveTradeManagementEngine().evaluate(
            data=self._reentry_data(),
            symbol="GER40Cash#",
            timeframe="M5",
            as_of_index=3,
            direction="BULLISH",
            context=context(),
            confirmed_swings=self._reentry_swings(),
            canonical_entry=bullish_entry(),
        )
        self.assertEqual(result["attempt_count"], 1)
        self.assertFalse(result["reentry_attempted"])
        self.assertEqual(
            result["reentry_state"],
            "FIRST_ENTRY_FAILED_RETRACEMENT_ACTIVE",
        )

    # 17
    def test_fresh_qualified_bos_arms_only_one_reentry(self):
        result = SteveTradeManagementEngine().evaluate(
            data=self._reentry_data(),
            symbol="GER40Cash#",
            timeframe="M5",
            as_of_index=8,
            direction="BULLISH",
            context=context(),
            confirmed_swings=self._reentry_swings(),
            canonical_entry=bullish_entry(),
        )
        self.assertEqual(result["attempt_count"], 2)
        self.assertEqual(result["reentry_count"], 1)
        self.assertTrue(result["reentry_attempted"])
        self.assertNotEqual(
            result["attempts"][0]["event_id"],
            result["attempts"][1]["event_id"],
        )
        self.assertTrue(
            result["attempts"][1]["sizing"]["sizing_logic_cloned"]
        )

    # 18
    def test_second_failure_permanently_closes_parent_setup(self):
        result = SteveTradeManagementEngine().evaluate(
            data=self._reentry_data(),
            symbol="GER40Cash#",
            timeframe="M5",
            as_of_index=9,
            direction="BULLISH",
            context=context(),
            confirmed_swings=self._reentry_swings(),
            canonical_entry=bullish_entry(),
        )
        self.assertEqual(result["attempt_count"], 2)
        self.assertEqual(
            result["reentry_state"],
            "CLOSED_AFTER_SECOND_FAILURE",
        )
        self.assertTrue(result["parent_setup_closed"])

    def test_brand_new_parent_setup_resets_one_reentry_allowance(self):
        engine = SteveTradeManagementEngine()
        data = self._reentry_data()
        engine.evaluate(
            data=data,
            symbol="GER40Cash#",
            timeframe="M5",
            as_of_index=3,
            direction="BULLISH",
            context=context(),
            confirmed_swings=self._reentry_swings(),
            canonical_entry=bullish_entry(),
        )
        new_entry = {
            **bullish_entry(entry_index=8),
            "setup_id": "PARENT-BULL-NEW",
            "entry_price": 101.0,
            "counter": {
                "side": "LOW",
                "classification": "LL",
                "index": 4,
                "level": 87.0,
                "confirmed_at_index": 5,
            },
            "trigger": {
                "side": "HIGH",
                "classification": "HH",
                "index": 6,
                "level": 97.0,
                "confirmed_at_index": 7,
            },
        }
        result = engine.evaluate(
            data=data,
            symbol="GER40Cash#",
            timeframe="M5",
            as_of_index=8,
            direction="BULLISH",
            context=context(),
            confirmed_swings=self._reentry_swings(),
            canonical_entry=new_entry,
        )
        self.assertEqual(result["attempt_count"], 1)
        self.assertEqual(result["reentry_count"], 0)
        self.assertEqual(
            result["latest_attempt"]["setup_id"],
            "PARENT-BULL-NEW",
        )

    # 19
    def test_m1_to_m5_management_transition_never_loosens(self):
        accepted = transition_protection_without_loosening(
            direction="BULLISH",
            current_level=90.0,
            candidate_m5_level=95.0,
        )
        rejected = transition_protection_without_loosening(
            direction="BEARISH",
            current_level=110.0,
            candidate_m5_level=115.0,
        )
        self.assertEqual(accepted["selected_level"], 95.0)
        self.assertEqual(rejected["selected_level"], 110.0)
        self.assertFalse(accepted["loosened"])
        self.assertFalse(rejected["loosened"])

    def test_qualified_m5_pullback_can_use_current_m1_close_bos(self):
        highs = [
            13, 12, 11, 10, 11, 12, 13, 16,
            13, 12, 11, 10, 11, 12, 11, 10,
        ]
        lows = [
            10, 9, 8, 5, 8, 9, 10, 12,
            10, 9, 8.5, 8, 9, 9.5, 9.2, 7,
        ]
        closes = [
            11, 10, 9, 6, 9, 10, 12, 14,
            11, 10, 9, 9, 10, 10, 10, 7,
        ]
        m1 = frame(
            opens=closes,
            highs=highs,
            lows=lows,
            closes=closes,
            seconds=60,
        )
        m1.loc[15, "open"] = 10.0
        result = evaluate_m1_fallback(
            m5_snapshot={
                "context": {"approved_direction": "BEARISH"},
                "market": {"trend": "BEARISH"},
                "retracement": {
                    "qualified": True,
                    "origin_swing": {"time": m1.iloc[0]["time"]},
                },
                "entry": {"ready": False},
                "setup": {"setup_id": "M5-PARENT"},
            },
            m1_data=m1,
            symbol="GER40Cash#",
            m1_as_of_index=15,
            higher_timeframe_context={
                "approved_direction": "BEARISH",
                "frames": {},
                "votes": {
                    "BULLISH": 0,
                    "BEARISH": 2,
                    "NEUTRAL": 1,
                },
            },
        )
        self.assertTrue(result["entry_ready"])
        self.assertEqual(
            result["state"],
            "M1_FALLBACK_ENTRY_VALIDATED",
        )
        self.assertEqual(
            result["entry"]["setup_invalidation_contract"][
                "timeframe"
            ],
            "M1",
        )

    # 20
    def test_chart_audit_uses_canonical_decision_time_contracts(self):
        invalidation = select_setup_logical_invalidation(
            data=initial_data(),
            entry_model=bullish_entry(),
            timeframe="M5",
            config=self.config,
        )
        emergency = emergency_broker_stop(
            logical_invalidation=invalidation,
            config=self.config,
        )
        chart = canonical_management_chart_contract(
            {
                "meta": {"as_of_index": 2},
                "entry": {
                    "ready": True,
                    "index": 2,
                    "emergency_broker_stop_contract": emergency,
                },
                "protection": {
                    "protection_role":
                    "DOMINANT_DECISION_PROTECTION"
                },
                "setup_invalidation": invalidation,
                "trailing_protection": {
                    "state": "NO_TRAIL_AVAILABLE"
                },
            }
        )
        self.assertTrue(chart["canonical_roots_only"])
        self.assertFalse(chart["future_initial_stop_data_used"])

    # 21
    def test_future_structures_are_rejected(self):
        entry = bullish_entry()
        entry["counter"] = {
            **entry["counter"],
            "confirmed_at_index": 3,
        }
        with self.assertRaises(ValueError):
            select_setup_logical_invalidation(
                data=initial_data(),
                entry_model=entry,
                timeframe="M5",
                config=self.config,
            )

    # 22
    def test_stale_trigger_is_rejected_by_chart_contract(self):
        with self.assertRaisesRegex(ValueError, "stale"):
            canonical_management_chart_contract(
                {
                    "meta": {"as_of_index": 9},
                    "entry": {"ready": True, "index": 2},
                    "setup_invalidation": {
                        "available_at_index": 1
                    },
                }
            )

    # 23
    def test_no_order_api_is_imported_or_called(self):
        root = Path(__file__).resolve().parents[1]
        forbidden = "order" + "_send"
        offenders = []
        runtime_paths = [
            root / "core",
            root / "tools",
            root / "main.py",
        ]
        files = []
        for runtime_path in runtime_paths:
            if runtime_path.is_file():
                files.append(runtime_path)
            elif runtime_path.exists():
                files.extend(runtime_path.rglob("*.py"))
        for path in files:
            if path.name == Path(__file__).name:
                continue
            if forbidden in path.read_text(
                encoding="utf-8",
                errors="ignore",
            ):
                offenders.append(str(path.relative_to(root)))
        self.assertEqual(offenders, [])

    def test_management_research_parameters_load_from_config(self):
        root = Path(__file__).resolve().parents[1]
        config = load_runtime_config(
            root / "config" / "research.example.json"
        )
        self.assertEqual(
            config.management_profile,
            "TWIN_POSITION_50_50",
        )
        self.assertEqual(config.m5_logical_atr_tolerance, 0.15)
        self.assertIn("M1_FALLBACK", config.entry_timeframes)
        self.assertIn("LONDON", config.allowed_sessions)


if __name__ == "__main__":
    unittest.main()
