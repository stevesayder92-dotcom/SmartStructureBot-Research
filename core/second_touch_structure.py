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


def _evaluate_legacy_second_touch_structure(
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



def _raw_wick_event(data: pd.DataFrame, *, index: int, side: str) -> dict[str, Any]:
    row = data.iloc[int(index)]
    field = "low" if side == "LOW" else "high"
    return {
        "side": side,
        "swing_index": int(index),
        "available_at_index": int(index),
        "price": float(row[field]),
        "swing_id": f"PROVISIONAL_{side}_{int(index)}",
        "provisional": True,
        "confirmation_method": "CLOSED_CANDLE_CAUSAL_NO_N_RIGHT",
    }


def _repaired_second_touch_structure(
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
    """Causal S2B.1.1 second-touch lifecycle.

    Touch-1 is historical/confirmed context. Touch-2 is recognized at its own
    closed candle, without waiting for N-right swing confirmation. A
    post-Touch-2 provisional reaction is built only from already-closed
    pre-BOS candles; the BOS candle can prove that reaction but cannot create
    the level it breaks.
    """
    direction = str(direction).upper()
    if direction not in {"BULLISH", "BEARISH"}:
        raise ValueError("Second-touch direction must be BULLISH or BEARISH")
    as_of_index = min(int(as_of_index), len(data) - 1)
    base = {
        "owner": "SecondTouchStructureEngine",
        "direction": direction,
        "as_of_index": as_of_index,
        "causal_valid": True,
        "closed_candles_only": True,
        "recognition_policy": "S2B1_1_CAUSAL_PROVISIONAL",
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

    touch_side = "LOW" if direction == "BULLISH" else "HIGH"
    reaction_side = "HIGH" if direction == "BULLISH" else "LOW"
    # Touch-1 must be genuinely historical/available; only Touch-2 gets the
    # no-N-right provisional treatment.
    historical_touches = sorted(
        (_event(point) for point in swings
         if _side(point) == touch_side
         and _index(point) >= int(setup_start_index)
         and _available(point) <= as_of_index),
        key=lambda x: x["swing_index"],
    )
    selected = None
    saw_distance = False
    saw_reaction = False
    for touch_1 in historical_touches:
        start2 = max(int(touch_1["swing_index"]) + config.minimum_separation_bars, int(setup_start_index))
        for idx in range(start2, as_of_index + 1):
            touch_2 = _raw_wick_event(data, index=idx, side=touch_side)
            touch_atr = _causal_atr(data, idx)  # frozen at actual Touch_2_Index
            distance = abs(float(touch_2["price"]) - float(touch_1["price"]))
            if distance > config.proximity_atr_ratio * touch_atr:
                saw_distance = True
                continue
            between_start = int(touch_1["swing_index"]) + 1
            between_end = idx
            if between_start >= between_end:
                continue
            between = data.iloc[between_start:between_end]
            if between.empty:
                continue
            if reaction_side == "HIGH":
                rel = int(between["high"].astype(float).values.argmax())
                reaction_index = between_start + rel
            else:
                rel = int(between["low"].astype(float).values.argmin())
                reaction_index = between_start + rel
            separating = _raw_wick_event(data, index=reaction_index, side=reaction_side)
            reaction_atr = _causal_atr(data, reaction_index)
            if abs(float(separating["price"]) - float(touch_1["price"])) < config.meaningful_reaction_atr_ratio * reaction_atr:
                saw_reaction = True
                continue
            # latest valid pair wins causally; later Touch-2 supersedes earlier.
            selected = (touch_1, touch_2, separating, touch_atr)
    if selected is None:
        if saw_reaction:
            state, reasons = "SECOND_TOUCH_REJECTED_NOISE", ["SEPARATING_REACTION_NOT_MEANINGFUL"]
        elif saw_distance:
            state, reasons = "SECOND_TOUCH_TOO_DISTANT", ["TOUCH_DISTANCE_EXCEEDS_CAUSAL_ATR_TOLERANCE"]
        else:
            state, reasons = "NO_SECOND_TOUCH", ["NO_CAUSAL_TOUCH_2_CANDIDATE"]
        return {**base, "state": state, "eligible": False, "rejection_reasons": reasons}

    touch_1, touch_2, separating, touch_atr = selected
    common = {
        **base,
        "touch_1": touch_1,
        "touch_2": touch_2,
        "touch_2_index": int(touch_2["swing_index"]),
        "touch_proximity_atr": float(touch_atr),
        "touch_proximity_atr_source_index": int(touch_2["swing_index"]),
        "separating_reaction": separating,
        "first_trigger": separating,
        "double_top_or_bottom": "DOUBLE_BOTTOM" if direction == "BULLISH" else "DOUBLE_TOP",
        "touch_count": 2,
        "touch_distance": abs(float(touch_2["price"]) - float(touch_1["price"])),
        "touch_tolerance": config.proximity_atr_ratio * float(touch_atr),
        "logical_stop_owner": touch_2,
        "old_trigger_superseded": True,
        "supersession_available_at_index": int(touch_2["swing_index"]),
    }

    t2 = int(touch_2["swing_index"])
    latest_trigger = None
    # Need at least one closed reaction candle before a different BOS candle.
    for bos_index in range(t2 + 2, as_of_index + 1):
        reaction_start = t2 + 1
        reaction_end = bos_index  # excludes BOS candle by construction
        pre_bos = data.iloc[reaction_start:reaction_end]
        if pre_bos.empty:
            continue
        if reaction_side == "HIGH":
            rel = int(pre_bos["high"].astype(float).values.argmax())
            trigger_index = reaction_start + rel
        else:
            rel = int(pre_bos["low"].astype(float).values.argmin())
            trigger_index = reaction_start + rel
        trigger = _raw_wick_event(data, index=trigger_index, side=reaction_side)
        reaction_atr = _causal_atr(data, trigger_index)
        magnitude = abs(float(trigger["price"]) - float(touch_2["price"]))
        if magnitude < config.meaningful_reaction_atr_ratio * reaction_atr:
            continue
        latest_trigger = trigger
        row = data.iloc[bos_index]
        close = float(row["close"]); open_price = float(row["open"])
        level = float(trigger["price"])
        body_break = close > level if direction == "BULLISH" else close < level
        correct_body = close > open_price if direction == "BULLISH" else close < open_price
        if body_break and correct_body:
            return {
                **common,
                "state": "SECOND_TOUCH_PROVED_BY_BOS",
                "eligible": True,
                "active_trigger": trigger,
                "provisional_trigger": trigger,
                "trigger_available_at_index": int(trigger_index),
                "bos_proof_index": int(bos_index),
                "bos_proof_price": close,
                "proof_method": "BODY_CLOSE_BEYOND_PREEXISTING_PROVISIONAL_TRIGGER",
                "rejection_reasons": [],
            }
    # Candidate can publish a causal provisional trigger even before proof.
    if latest_trigger is None and as_of_index >= t2 + 1:
        post = data.iloc[t2 + 1 : as_of_index + 1]
        if not post.empty:
            if reaction_side == "HIGH":
                rel = int(post["high"].astype(float).values.argmax())
            else:
                rel = int(post["low"].astype(float).values.argmin())
            idx = t2 + 1 + rel
            candidate_trigger = _raw_wick_event(data, index=idx, side=reaction_side)
            ratr = _causal_atr(data, idx)
            if abs(float(candidate_trigger["price"]) - float(touch_2["price"])) >= config.meaningful_reaction_atr_ratio * ratr:
                latest_trigger = candidate_trigger
    return {
        **common,
        "state": "SECOND_TOUCH_CANDIDATE",
        "eligible": False,
        "active_trigger": latest_trigger,
        "provisional_trigger": latest_trigger,
        "trigger_available_at_index": (int(latest_trigger["swing_index"]) if latest_trigger else None),
        "rejection_reasons": ["SECOND_TOUCH_BOS_PROOF_NOT_AVAILABLE" if latest_trigger else "SECOND_TOUCH_TRIGGER_NOT_AVAILABLE"],
    }


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
    causal_repair: bool = False,
) -> dict[str, Any]:
    """Dispatch legacy S2B.1 control or repaired S2B.1.1 recognition."""
    kwargs = dict(
        data=data, swings=swings, direction=direction, as_of_index=as_of_index,
        setup_start_index=setup_start_index, owner=owner,
        expected_owner=expected_owner, protection_intact=protection_intact,
        setup_consumed=setup_consumed, config=config,
    )
    if causal_repair:
        return _repaired_second_touch_structure(**kwargs)
    return _evaluate_legacy_second_touch_structure(**kwargs)
