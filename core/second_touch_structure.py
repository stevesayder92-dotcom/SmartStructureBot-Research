from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

import pandas as pd

from core.steve_trade_management import atr_at


SECOND_TOUCH_OWNER_FIELDS = (
    "parent_setup_id",
    "retracement_id",
    "impulse_cycle_id",
    "direction",
    "dominant_protection_identity",
    "fib_anchor_version",
)


@dataclass(frozen=True)
class SecondTouchConfig:
    proximity_atr_ratio: float = 0.25
    meaningful_reaction_atr_ratio: float = 0.35
    minimum_separation_bars: int = 3

    def __post_init__(self) -> None:
        if self.proximity_atr_ratio <= 0:
            raise ValueError("Second-touch ATR proximity must be positive")
        if self.meaningful_reaction_atr_ratio <= 0:
            raise ValueError("Meaningful reaction ATR ratio must be positive")
        if self.minimum_separation_bars < 1:
            raise ValueError("Second-touch separation must be at least one bar")


def ownership_fingerprint(owner: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(owner.get(field) for field in SECOND_TOUCH_OWNER_FIELDS)


def ownership_matches(
    expected: Mapping[str, Any], candidate: Mapping[str, Any]
) -> bool:
    return ownership_fingerprint(expected) == ownership_fingerprint(candidate)


def second_touch_logical_boundary(
    *,
    wick_extreme: float,
    direction: str,
    timeframe: str,
    causal_atr: float,
    m5_atr_tolerance_ratio: float = 0.15,
) -> dict[str, float]:
    """Publish the touch-2 wick owner and timeframe-specific boundary."""
    direction = str(direction).upper()
    timeframe = str(timeframe).upper()
    if direction not in {"BULLISH", "BEARISH"}:
        raise ValueError("Second-touch direction must be BULLISH or BEARISH")
    tolerance = (
        max(float(causal_atr), 0.0) * float(m5_atr_tolerance_ratio)
        if timeframe == "M5"
        else 0.0
    )
    wick = float(wick_extreme)
    boundary = wick - tolerance if direction == "BULLISH" else wick + tolerance
    return {
        "structure_wick": wick,
        "atr_tolerance": tolerance,
        "logical_invalidation_boundary": boundary,
    }


def _index(point: Mapping[str, Any]) -> int:
    return int(point.get("swing_index", point.get("index")))


def _available(point: Mapping[str, Any]) -> int:
    return int(
        point.get(
            "available_at_index",
            point.get("confirmed_at_index", _index(point)),
        )
    )


def _price(point: Mapping[str, Any]) -> float:
    return float(point.get("price", point.get("level")))


def _side(point: Mapping[str, Any]) -> str:
    return str(point.get("side") or "").upper()


def _event(point: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "side": _side(point),
        "swing_index": _index(point),
        "available_at_index": _available(point),
        "price": _price(point),
        "swing_id": point.get("swing_id"),
    }


def _causal_atr(data: pd.DataFrame, index: int) -> float:
    if data is None or data.empty:
        return 0.0
    current = min(max(int(index), 0), len(data) - 1)
    return max(float(atr_at(data.iloc[: current + 1], as_of_index=current)), 1e-12)


def evaluate_second_touch_structure(
    *,
    data: pd.DataFrame,
    swings: Iterable[Mapping[str, Any]],
    direction: str,
    as_of_index: int,
    setup_start_index: int,
    owner: Mapping[str, Any],
    expected_owner: Optional[Mapping[str, Any]] = None,
    protection_intact: bool = True,
    setup_consumed: bool = False,
    config: SecondTouchConfig = SecondTouchConfig(),
) -> dict[str, Any]:
    """Recognize one causal double-top/bottom and its post-touch trigger.

    The function consumes only swings whose confirmation index is visible at
    ``as_of_index``. It never infers ownership from timestamp proximity.
    """
    direction = str(direction).upper()
    if direction not in {"BULLISH", "BEARISH"}:
        raise ValueError("Second-touch direction must be BULLISH or BEARISH")
    base = {
        "owner": "SecondTouchStructureEngine",
        "direction": direction,
        "as_of_index": int(as_of_index),
        "causal_valid": True,
        "closed_candles_only": True,
        "ownership": {field: owner.get(field) for field in SECOND_TOUCH_OWNER_FIELDS},
        "config": {
            "proximity_atr_ratio": config.proximity_atr_ratio,
            "meaningful_reaction_atr_ratio": config.meaningful_reaction_atr_ratio,
            "minimum_separation_bars": config.minimum_separation_bars,
        },
        "touch_1": None,
        "touch_2": None,
        "separating_reaction": None,
        "first_trigger": None,
        "active_trigger": None,
        "logical_stop_owner": None,
        "old_trigger_superseded": False,
    }
    if expected_owner is not None and not ownership_matches(expected_owner, owner):
        return {**base, "state": "SECOND_TOUCH_FOREIGN_PARENT", "eligible": False, "rejection_reasons": ["OWNERSHIP_FINGERPRINT_MISMATCH"]}
    if setup_consumed:
        return {**base, "state": "SECOND_TOUCH_AFTER_CONSUMPTION", "eligible": False, "rejection_reasons": ["PARENT_ALREADY_CONSUMED"]}
    if not protection_intact:
        return {**base, "state": "SECOND_TOUCH_PROTECTION_FAILED", "eligible": False, "rejection_reasons": ["DOMINANT_PROTECTION_FAILED"]}

    visible = sorted(
        (
            _event(point)
            for point in swings
            if _index(point) >= int(setup_start_index)
            and _available(point) <= int(as_of_index)
        ),
        key=lambda point: (point["swing_index"], point["available_at_index"], point["side"]),
    )
    touch_side = "LOW" if direction == "BULLISH" else "HIGH"
    reaction_side = "HIGH" if direction == "BULLISH" else "LOW"
    touches = [point for point in visible if point["side"] == touch_side]
    selected: Optional[tuple[dict[str, Any], dict[str, Any], dict[str, Any], float]] = None
    saw_noise = False
    saw_too_distant = False
    for right in range(1, len(touches)):
        touch_2 = touches[right]
        for left in range(right - 1, -1, -1):
            touch_1 = touches[left]
            if touch_2["swing_index"] - touch_1["swing_index"] < config.minimum_separation_bars:
                saw_noise = True
                continue
            touch_atr = _causal_atr(data, touch_2["available_at_index"])
            if abs(touch_2["price"] - touch_1["price"]) > config.proximity_atr_ratio * touch_atr:
                saw_too_distant = True
                continue
            between = [
                point
                for point in visible
                if point["side"] == reaction_side
                and touch_1["swing_index"] < point["swing_index"] < touch_2["swing_index"]
            ]
            meaningful = [
                point
                for point in between
                if abs(point["price"] - touch_1["price"])
                >= config.meaningful_reaction_atr_ratio * _causal_atr(data, point["available_at_index"])
            ]
            if not meaningful:
                saw_noise = True
                continue
            reaction = max(meaningful, key=lambda point: point["swing_index"])
            selected = (touch_1, touch_2, reaction, touch_atr)
            break
        if selected is not None:
            # Later causally valid touch-2 structures supersede earlier pairs.
            continue
    if selected is None:
        if saw_too_distant:
            state = "SECOND_TOUCH_TOO_DISTANT"
            reasons = ["TOUCH_DISTANCE_EXCEEDS_CAUSAL_ATR_TOLERANCE"]
        elif saw_noise:
            state = "SECOND_TOUCH_REJECTED_NOISE"
            reasons = ["SEPARATION_OR_REACTION_NOT_MEANINGFUL"]
        else:
            state = "NO_SECOND_TOUCH"
            reasons = ["FEWER_THAN_TWO_CAUSAL_SAME_SIDE_TOUCHES"]
        return {**base, "state": state, "eligible": False, "rejection_reasons": reasons}

    touch_1, touch_2, separating, touch_atr = selected
    after = [
        point
        for point in visible
        if point["side"] == reaction_side and point["swing_index"] > touch_2["swing_index"]
    ]
    meaningful_after = [
        point
        for point in after
        if abs(point["price"] - touch_2["price"])
        >= config.meaningful_reaction_atr_ratio * _causal_atr(data, point["available_at_index"])
    ]
    common = {
        **base,
        "touch_1": touch_1,
        "touch_2": touch_2,
        "separating_reaction": separating,
        "first_trigger": separating,
        "double_top_or_bottom": "DOUBLE_BOTTOM" if direction == "BULLISH" else "DOUBLE_TOP",
        "touch_count": 2,
        "touch_distance": abs(touch_2["price"] - touch_1["price"]),
        "touch_tolerance": config.proximity_atr_ratio * touch_atr,
        "logical_stop_owner": touch_2,
        "old_trigger_superseded": True,
    }
    if not meaningful_after:
        return {
            **common,
            "state": "SECOND_TOUCH_CANDIDATE",
            "eligible": False,
            "supersession_available_at_index": touch_2["available_at_index"],
            "rejection_reasons": ["SECOND_TOUCH_TRIGGER_NOT_AVAILABLE"],
        }
    trigger = min(meaningful_after, key=lambda point: point["swing_index"])
    return {
        **common,
        "state": "SECOND_TOUCH_CONFIRMED",
        "eligible": True,
        "active_trigger": trigger,
        "supersession_available_at_index": touch_2["available_at_index"],
        "trigger_available_at_index": trigger["available_at_index"],
        "rejection_reasons": [],
    }
