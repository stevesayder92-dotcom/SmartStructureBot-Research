from __future__ import annotations

import unittest

import pandas as pd

from core.qualified_retracement import (
    QualifiedRetracementEngine,
    QualifiedRetracementPolicy,
)
from core.setup_lifecycle import SetupLifecycleRegistry


def bearish_fixture() -> tuple[pd.DataFrame, list[dict], list[dict]]:
    rows = []
    price = 106.0
    for index in range(24):
        open_price = price
        close = price - 0.8
        high = max(open_price, close) + 0.5
        low = min(open_price, close) - 0.5
        rows.append(
            {
                "time": index * 300,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
            }
        )
        price = close
    # Candidate bullish break.
    rows[10].update(
        open=96.5,
        high=100.0,
        low=96.0,
        close=99.0,
    )
    rows[11].update(
        open=99.0,
        high=101.0,
        low=98.5,
        close=100.5,
    )
    rows[12].update(
        open=100.5,
        high=101.5,
        low=99.0,
        close=100.0,
    )
    rows[13].update(
        open=100.0,
        high=100.8,
        low=98.0,
        close=99.0,
    )
    rows[14].update(
        open=99.0,
        high=100.5,
        low=98.7,
        close=100.0,
    )
    rows[15].update(
        open=100.0,
        high=100.3,
        low=98.7,
        close=99.2,
    )
    rows[16].update(
        open=99.2,
        high=99.4,
        low=97.0,
        close=97.8,
    )
    data = pd.DataFrame(rows)
    points = [
        {
            "type": "LH",
            "side": "HIGH",
            "index": 2,
            "body_price": 110.0,
            "confirmed_at_index": 3,
            "tradeable_at_index": 3,
            "decision_weight": 8,
            "is_tradeable_structure": True,
        },
        {
            "type": "LH",
            "side": "HIGH",
            "index": 7,
            "body_price": 98.0,
            "confirmed_at_index": 8,
            "tradeable_at_index": 8,
            "decision_weight": 5,
            "is_tradeable_structure": True,
        },
        {
            "type": "HH",
            "side": "HIGH",
            "index": 11,
            "body_price": 100.5,
            "confirmed_at_index": 12,
            "tradeable_at_index": 12,
            "decision_weight": 4,
            "is_tradeable_structure": True,
        },
        {
            "type": "HL",
            "side": "LOW",
            "index": 13,
            "body_price": 98.5,
            "confirmed_at_index": 14,
            "tradeable_at_index": 14,
            "decision_weight": 4,
            "is_tradeable_structure": True,
        },
    ]
    bos = [
        {
            "type": "BEARISH_BOS",
            "index": 5,
            "break_price": 101.0,
            "broken_structure_index": 4,
            "broken_structure_type": "LL",
            "bos_class": "BEARISH_CONTINUATION_BOS",
            "bos_role": "NEW_SETUP_BOS",
            "decision_available_at_index": 5,
            "causal_valid": True,
        }
    ]
    return data, points, bos


def mirror_bullish(
    data: pd.DataFrame,
    points: list[dict],
    bos: list[dict],
) -> tuple[pd.DataFrame, list[dict], list[dict]]:
    pivot = 200.0
    mirrored = data.copy()
    for column in ("open", "high", "low", "close"):
        mirrored[column] = pivot - data[column]
    original_high = mirrored["high"].copy()
    mirrored["high"] = mirrored["low"]
    mirrored["low"] = original_high
    mirrored_points = []
    type_map = {"LH": "HL", "HH": "LL", "HL": "LH"}
    for point in points:
        copy = dict(point)
        copy["type"] = type_map[point["type"]]
        copy["side"] = "LOW" if point["side"] == "HIGH" else "HIGH"
        copy["body_price"] = pivot - float(point["body_price"])
        mirrored_points.append(copy)
    mirrored_bos = [
        {
            **bos[0],
            "type": "BULLISH_BOS",
            "break_price": pivot - float(bos[0]["break_price"]),
            "broken_structure_type": "HH",
            "bos_class": "BULLISH_CONTINUATION_BOS",
        }
    ]
    return mirrored, mirrored_points, mirrored_bos


class QualifiedRetracementTest(unittest.TestCase):
    def _analyse(
        self,
        index: int,
        *,
        data=None,
        points=None,
        bos=None,
        model: str = "HYBRID",
    ):
        base_data, base_points, base_bos = bearish_fixture()
        return QualifiedRetracementEngine(
            base_data if data is None else data,
            as_of_index=index,
            policy=QualifiedRetracementPolicy(model=model),
        ).analyze(
            trend="BEARISH",
            structure_points=(
                base_points if points is None else points
            ),
            bos_events=base_bos if bos is None else bos,
        )

    def test_01_micro_noise_only(self):
        data, points, bos = bearish_fixture()
        data.loc[10, ["open", "high", "low", "close"]] = [
            97.2,
            98.2,
            96.8,
            97.7,
        ]
        result = self._analyse(
            10,
            data=data,
            points=points,
            bos=bos,
        )
        self.assertEqual(result["state"], "MICRO_COUNTER_NOISE")
        self.assertFalse(result["qualified"])
        self.assertFalse(result["entry_ready"])

    def test_02_internal_break_without_maturity(self):
        result = self._analyse(10)
        self.assertEqual(result["state"], "RETRACEMENT_CANDIDATE")
        self.assertIsNotNone(result["broken_internal_structure"])
        self.assertFalse(result["entry_ready"])

    def test_03_qualified_bearish_trend_retracement(self):
        result = self._analyse(14)
        self.assertTrue(result["qualified"])
        self.assertEqual(
            result["state"],
            "WAITING_FOR_FAILURE_TRIGGER",
        )
        self.assertTrue(result["protected_swing_intact"])

    def test_04_valid_bearish_entry(self):
        result = self._analyse(16)
        self.assertEqual(result["state"], "ENTRY_CANDIDATE")
        self.assertTrue(result["entry_ready"])
        self.assertEqual(
            result["continuation_bos"]["type"],
            "BEARISH_ENTRY_BOS",
        )
        self.assertEqual(result["entry_price"], 97.8)

    def test_05_valid_bullish_mirror(self):
        data, points, bos = bearish_fixture()
        data, points, bos = mirror_bullish(data, points, bos)
        result = QualifiedRetracementEngine(
            data,
            as_of_index=16,
        ).analyze(
            trend="BULLISH",
            structure_points=points,
            bos_events=bos,
        )
        self.assertEqual(result["state"], "ENTRY_CANDIDATE")
        self.assertEqual(
            result["continuation_bos"]["type"],
            "BULLISH_ENTRY_BOS",
        )

    def test_06_protected_swing_violation(self):
        data, points, bos = bearish_fixture()
        data.loc[15, ["open", "high", "low", "close"]] = [
            109.0,
            112.0,
            108.5,
            111.0,
        ]
        result = self._analyse(
            15,
            data=data,
            points=points,
            bos=bos,
        )
        self.assertEqual(
            result["state"],
            "INVALIDATED_BY_PROTECTED_SWING",
        )
        self.assertFalse(result["entry_ready"])

    def test_07_wick_through_protection(self):
        data, points, bos = bearish_fixture()
        data.loc[15, ["open", "high", "low", "close"]] = [
            109.0,
            112.0,
            108.5,
            109.5,
        ]
        result = self._analyse(
            15,
            data=data,
            points=points,
            bos=bos,
        )
        self.assertNotEqual(
            result["state"],
            "INVALIDATED_BY_PROTECTED_SWING",
        )
        self.assertTrue(result["protected_swing_intact"])

    def test_08_pre_origin_compression_is_ignored(self):
        data, points, bos = bearish_fixture()
        points.insert(
            0,
            {
                "type": "LH",
                "side": "HIGH",
                "index": 1,
                "body_price": 104.0,
                "confirmed_at_index": 2,
                "tradeable_at_index": 2,
                "decision_weight": 8,
                "is_tradeable_structure": True,
            },
        )
        result = self._analyse(
            10,
            data=data,
            points=points,
            bos=bos,
        )
        self.assertGreaterEqual(
            result["candidate_start_index"],
            result["origin_bos_index"],
        )
        self.assertEqual(result["candidate_start_index"], 10)

    def test_09_one_strong_counter_structure_can_qualify(self):
        _, points, _ = bearish_fixture()
        points = [
            point
            for point in points
            if point["type"] != "HL"
        ]
        result = self._analyse(14, points=points)
        self.assertTrue(result["qualified"])
        self.assertEqual(
            len(result["counter_structure_points"]),
            1,
        )

    def test_10_weak_first_bounce_stays_candidate(self):
        data, points, bos = bearish_fixture()
        data.loc[10, ["open", "high", "low", "close"]] = [
            97.9,
            98.3,
            97.7,
            98.1,
        ]
        points = points[:2]
        result = self._analyse(
            10,
            data=data,
            points=points,
            bos=bos,
        )
        self.assertIn(
            result["state"],
            {
                "RETRACEMENT_CANDIDATE",
                "WAITING_FOR_COUNTER_STRUCTURE",
            },
        )
        self.assertFalse(result["entry_ready"])

    def test_11_identity_stability(self):
        registry = SetupLifecycleRegistry()
        first = registry.observe(
            symbol="TEST#",
            timeframe=5,
            direction="BEARISH",
            origin_trend_bos_index=5,
            initial_pullback_start=10,
            current_pullback_end=14,
            as_of_index=14,
            descriptive_status="QUALIFIED_RETRACEMENT",
        )
        updated = registry.observe(
            symbol="TEST#",
            timeframe=5,
            direction="BEARISH",
            origin_trend_bos_index=5,
            initial_pullback_start=10,
            current_pullback_end=18,
            as_of_index=18,
            descriptive_status="WAITING_FOR_TRIGGER",
        )
        self.assertEqual(first["setup_id"], updated["setup_id"])

    def test_12_new_impulse_cycle_gets_new_identity(self):
        registry = SetupLifecycleRegistry()
        old = registry.observe(
            symbol="TEST#",
            timeframe=5,
            direction="BEARISH",
            origin_trend_bos_index=5,
            initial_pullback_start=10,
            current_pullback_end=14,
            as_of_index=14,
            descriptive_status="QUALIFIED_RETRACEMENT",
        )
        registry.close_for_new_impulse(
            old["setup_id"],
            20,
            new_origin_trend_bos_index=19,
        )
        new = registry.observe(
            symbol="TEST#",
            timeframe=5,
            direction="BEARISH",
            origin_trend_bos_index=19,
            initial_pullback_start=21,
            current_pullback_end=24,
            as_of_index=24,
            descriptive_status="QUALIFIED_RETRACEMENT",
        )
        self.assertNotEqual(old["setup_id"], new["setup_id"])

    def test_13_prequalification_trigger_is_rejected(self):
        _, points, _ = bearish_fixture()
        points = [
            point
            for point in points
            if point["type"] != "HL"
        ] + [
            {
                "type": "HL",
                "side": "LOW",
                "index": 11,
                "body_price": 98.5,
                "confirmed_at_index": 12,
                "tradeable_at_index": 12,
                "decision_weight": 4,
                "is_tradeable_structure": True,
            }
        ]
        result = self._analyse(16, points=points)
        self.assertTrue(result["qualified"])
        self.assertIsNone(result["failure_trigger"])
        self.assertFalse(result["entry_ready"])

    def test_14_future_confirmed_structure_is_unavailable(self):
        _, points, _ = bearish_fixture()
        points[1]["confirmed_at_index"] = 15
        points[1]["tradeable_at_index"] = 15
        result = self._analyse(10, points=points)
        self.assertEqual(result["state"], "MICRO_COUNTER_NOISE")
        self.assertIsNone(result["candidate_start_index"])

    def test_15_compression_merging_creates_no_setup_ids(self):
        data, points, bos = bearish_fixture()
        points = points[:1]
        states = []
        for index in range(6, 10):
            states.append(
                self._analyse(
                    index,
                    data=data,
                    points=points,
                    bos=bos,
                )["state"]
            )
        self.assertTrue(
            set(states).issubset(
                {
                    "MICRO_COUNTER_NOISE",
                    "NO_POST_BOS_COUNTER_MOVE",
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
