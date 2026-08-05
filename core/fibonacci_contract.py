from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

import pandas as pd


FIBONACCI_MODEL = "STEVE_REMAINING_IMPULSE_PERCENT_V2"
FIB_ANCHOR_VERSION = "M5_PARENT_IMPULSE_ANCHORS_V2"


@dataclass(frozen=True)
class FibonacciConfig:
    minimum_relevant_depth: float = 0.236
    primary_minimum: float = 0.382
    primary_maximum: float = 0.618
    deep_maximum: float = 0.786

    def __post_init__(self) -> None:
        values = (
            self.minimum_relevant_depth,
            self.primary_minimum,
            self.primary_maximum,
            self.deep_maximum,
        )
        if not (
            0 < values[0] <= values[1] <= values[2] <= values[3] <= 1
        ):
            raise ValueError("Fibonacci thresholds must be ordered in (0, 1]")


def _number(value: Any) -> float:
    return float(value)


def _unavailable(as_of_index: int, reason: str) -> Dict[str, Any]:
    return {
        "availability": "UNAVAILABLE",
        "available": False,
        "owner": "FibonacciRetracementEngine",
        "model": FIBONACCI_MODEL,
        "state": "WAITING_FOR_VALID_IMPULSE_ANCHORS",
        "zone": "UNAVAILABLE",
        "remaining_zone": "UNAVAILABLE",
        "depth": None,
        "depth_percent": None,
        "remaining_impulse_ratio": None,
        "remaining_impulse_percent": None,
        "retracement_depth_ratio": None,
        "retracement_depth_percent": None,
        "lowest_remaining_percent_reached": None,
        "deepest_retracement_percent_reached": None,
        "fib_anchor_version": FIB_ANCHOR_VERSION,
        "minimum_relevant_reached": False,
        "as_of_index": int(as_of_index),
        "causal_valid": True,
        "post_entry_data_used": False,
        "hard_filter": False,
        "reasons": [reason],
    }


def classify_depth(
    depth: float,
    *,
    config: Optional[FibonacciConfig] = None,
) -> str:
    cfg = config or FibonacciConfig()
    if depth < cfg.minimum_relevant_depth:
        return "SHALLOW"
    if depth < cfg.primary_minimum:
        return "EARLY_RELEVANT"
    if depth <= cfg.primary_maximum:
        return "PRIMARY_SWEET_SPOT"
    if depth <= cfg.deep_maximum:
        return "DEEP_BUT_VALID"
    return "EXTREME"


def classify_remaining(remaining_ratio: float) -> str:
    """Classify Steve's raw remaining-impulse ratio without hiding breaches."""
    remaining = float(remaining_ratio)
    if remaining < 0.0:
        return "BELOW_0"
    if remaining < 0.236:
        return "0_TO_23_6_REMAINING"
    if remaining <= 0.382:
        return "STEVE_PRIMARY_DEEP_SWEET_SPOT"
    if remaining <= 0.618:
        return "38_2_TO_61_8_REMAINING"
    if remaining <= 0.786:
        return "61_8_TO_78_6_REMAINING"
    return "ABOVE_78_6_REMAINING"


def build_fibonacci_contract(
    *,
    data: pd.DataFrame,
    direction: str,
    anchor: Optional[Dict[str, Any]],
    swings: Iterable[Dict[str, Any]],
    as_of_index: int,
    origin_bos_index: Optional[int] = None,
    config: Optional[FibonacciConfig] = None,
) -> Dict[str, Any]:
    """
    Build a causal Fibonacci contract for the current dominant impulse.

    Steve orientation: 0% is the same-cycle impulse origin/full structural
    retest and 100% is the impulse extreme where retracement begins. No candle
    after ``as_of_index`` is inspected.
    """
    cfg = config or FibonacciConfig()
    direction = str(direction).upper()
    current = int(as_of_index)
    if direction not in {"BULLISH", "BEARISH"}:
        return _unavailable(current, "A directional dominant trend is required")
    if anchor is None or anchor.get("index") is None:
        return _unavailable(current, "The impulse extreme is not available")

    impulse_extreme_index = int(anchor["index"])
    impulse_extreme_available = int(
        anchor.get(
            "confirmed_at_index",
            anchor.get("available_at_index", impulse_extreme_index),
        )
    )
    if (
        impulse_extreme_index > current
        or impulse_extreme_available > current
    ):
        return _unavailable(current, "The impulse extreme is not causally available")

    origin_side = "LOW" if direction == "BULLISH" else "HIGH"
    visible_origins = [
        dict(point)
        for point in swings
        if str(point.get("side")).upper() == origin_side
        and point.get("index") is not None
        and int(point["index"]) < impulse_extreme_index
        and int(point.get("confirmed_at_index", point["index"])) <= current
        and (
            origin_bos_index is None
            or int(point["index"]) <= int(origin_bos_index)
        )
    ]
    if not visible_origins:
        return _unavailable(
            current,
            "No causally confirmed same-cycle impulse-origin swing is available",
        )

    origin = max(visible_origins, key=lambda point: int(point["index"]))
    fib_zero_index = int(origin["index"])
    fib_hundred_index = impulse_extreme_index
    fib_zero_price = _number(origin.get("level", origin.get("price")))
    fib_hundred_price = _number(anchor.get("level", anchor.get("price")))
    impulse_range = (
        fib_hundred_price - fib_zero_price
        if direction == "BULLISH"
        else fib_zero_price - fib_hundred_price
    )
    if impulse_range <= 0:
        return _unavailable(current, "Impulse anchors are inverted or have zero range")

    retracement_start = fib_hundred_index + 1
    visible = data.iloc[retracement_start : current + 1]
    if visible.empty:
        return _unavailable(current, "No closed candles exist between anchor and decision")
    if direction == "BULLISH":
        extreme_offset = int(visible["low"].astype(float).argmin())
        retracement_price = _number(visible.iloc[extreme_offset]["low"])
        remaining = (
            retracement_price - fib_zero_price
        ) / impulse_range
    else:
        extreme_offset = int(visible["high"].astype(float).argmax())
        retracement_price = _number(visible.iloc[extreme_offset]["high"])
        remaining = (
            fib_zero_price - retracement_price
        ) / impulse_range
    retracement_index = retracement_start + extreme_offset
    depth = 1.0 - remaining

    def price_at_remaining(ratio: float) -> float:
        if direction == "BULLISH":
            return fib_zero_price + ratio * impulse_range
        return fib_zero_price - ratio * impulse_range

    levels = {
        label: price_at_remaining(ratio)
        for label, ratio in (
            ("100.0", 1.0),
            ("78.6", 0.786),
            ("61.8", 0.618),
            ("50.0", 0.5),
            ("38.2", 0.382),
            ("23.6", 0.236),
            ("0.0", 0.0),
        )
    }
    remaining_zone = classify_remaining(remaining)
    legacy_zone = classify_depth(max(0.0, depth), config=cfg)
    display_remaining = min(1.0, max(0.0, remaining))
    display_depth = min(1.0, max(0.0, depth))
    origin_available = int(
        origin.get("confirmed_at_index", fib_zero_index)
    )
    return {
        "availability": "AVAILABLE",
        "available": True,
        "owner": "FibonacciRetracementEngine",
        "model": FIBONACCI_MODEL,
        "state": (
            "DOMINANT_IMPULSE_ORIGIN_BREACHED"
            if remaining < 0.0
            else "REMAINING_IMPULSE_AVAILABLE"
        ),
        "direction": direction,
        "fib_anchor_version": FIB_ANCHOR_VERSION,
        "fib_zero_role": "FULL_STRUCTURE_RETEST_ORIGIN",
        "fib_zero_index": fib_zero_index,
        "fib_zero_price": fib_zero_price,
        "fib_zero_available_at_index": origin_available,
        "fib_hundred_role": "RETRACEMENT_START_IMPULSE_EXTREME",
        "fib_hundred_index": fib_hundred_index,
        "fib_hundred_price": fib_hundred_price,
        "fib_hundred_available_at_index": impulse_extreme_available,
        # Compatibility aliases now follow the corrected orientation.
        "zero_anchor_role": "FULL_STRUCTURE_RETEST_ORIGIN",
        "zero_anchor_index": fib_zero_index,
        "zero_anchor_price": fib_zero_price,
        "zero_anchor_available_at_index": origin_available,
        "hundred_anchor_role": "RETRACEMENT_START_IMPULSE_EXTREME",
        "hundred_anchor_index": fib_hundred_index,
        "hundred_anchor_price": fib_hundred_price,
        "hundred_anchor_available_at_index": impulse_extreme_available,
        "origin_bos_index": (
            int(origin_bos_index) if origin_bos_index is not None else None
        ),
        "retracement_extreme_index": retracement_index,
        "retracement_extreme_price": retracement_price,
        "remaining_impulse_ratio": remaining,
        "remaining_impulse_percent": remaining * 100.0,
        "retracement_depth_ratio": depth,
        "retracement_depth_percent": depth * 100.0,
        "lowest_remaining_percent_reached": remaining * 100.0,
        "deepest_retracement_percent_reached": depth * 100.0,
        "display_remaining_impulse_percent": display_remaining * 100.0,
        "display_retracement_depth_percent": display_depth * 100.0,
        "depth": depth,
        "depth_percent": depth * 100.0,
        "zone": remaining_zone,
        "remaining_zone": remaining_zone,
        "legacy_depth_zone": legacy_zone,
        "levels": levels,
        "minimum_relevant_depth": cfg.minimum_relevant_depth,
        "minimum_relevant_reached": depth >= cfg.minimum_relevant_depth,
        "primary_zone": [0.236, 0.382],
        "primary_zone_basis": "REMAINING_IMPULSE_RATIO",
        "deep_valid_maximum": cfg.deep_maximum,
        "as_of_index": current,
        "causal_valid": bool(
            fib_zero_index < fib_hundred_index <= retracement_index <= current
            and impulse_extreme_available <= current
            and origin_available <= current
        ),
        "post_entry_data_used": False,
        "dominant_origin_breached": remaining < 0.0,
        "hard_filter": remaining < 0.0,
        "reasons": [
            "Steve 0% origin and 100% impulse-extreme anchors are causal",
            "Remaining impulse and retracement depth use only closed candles available at decision time",
            "Fibonacci grades location; it does not manufacture a setup or override broken protection",
        ],
    }


def reassess_same_cycle(
    *,
    data: pd.DataFrame,
    original: Dict[str, Any],
    as_of_index: int,
    config: Optional[FibonacciConfig] = None,
) -> Dict[str, Any]:
    """Extend an existing parent setup's anchors without creating a new setup."""
    current = int(as_of_index)
    if not original.get("available"):
        return _unavailable(current, "Original parent Fibonacci anchors unavailable")
    direction = str(original["direction"]).upper()
    zero_index = int(original["fib_zero_index"])
    zero_price = _number(original["fib_zero_price"])
    hundred_index = int(original["fib_hundred_index"])
    hundred_price = _number(original["fib_hundred_price"])
    impulse_range = abs(hundred_price - zero_price)
    retracement_start = hundred_index + 1
    visible = data.iloc[retracement_start : current + 1]
    if visible.empty or impulse_range <= 0:
        return _unavailable(current, "Parent Fibonacci anchor range is invalid")
    if direction == "BULLISH":
        offset = int(visible["low"].astype(float).argmin())
        price = _number(visible.iloc[offset]["low"])
        remaining = (price - zero_price) / impulse_range
    else:
        offset = int(visible["high"].astype(float).argmax())
        price = _number(visible.iloc[offset]["high"])
        remaining = (zero_price - price) / impulse_range
    depth = 1.0 - remaining
    cfg = config or FibonacciConfig()
    result = dict(original)
    result.update(
        {
            "state": "FIBONACCI_REASSESSED_SAME_PARENT",
            "retracement_extreme_index": retracement_start + offset,
            "retracement_extreme_price": price,
            "depth": depth,
            "depth_percent": depth * 100.0,
            "remaining_impulse_ratio": remaining,
            "remaining_impulse_percent": remaining * 100.0,
            "retracement_depth_ratio": depth,
            "retracement_depth_percent": depth * 100.0,
            "lowest_remaining_percent_reached": remaining * 100.0,
            "deepest_retracement_percent_reached": depth * 100.0,
            "display_remaining_impulse_percent": (
                min(1.0, max(0.0, remaining)) * 100.0
            ),
            "display_retracement_depth_percent": (
                min(1.0, max(0.0, depth)) * 100.0
            ),
            "zone": classify_remaining(remaining),
            "remaining_zone": classify_remaining(remaining),
            "legacy_depth_zone": classify_depth(
                max(0.0, depth),
                config=cfg,
            ),
            "minimum_relevant_reached": depth >= cfg.minimum_relevant_depth,
            "as_of_index": current,
            "causal_valid": (
                zero_index < hundred_index
                <= retracement_start + offset
                <= current
            ),
            "dominant_origin_breached": remaining < 0.0,
            "hard_filter": remaining < 0.0,
            "same_parent_anchors_preserved": True,
            "post_entry_data_used": False,
        }
    )
    return result
