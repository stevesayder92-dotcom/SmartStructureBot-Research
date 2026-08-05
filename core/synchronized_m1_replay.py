from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional

import pandas as pd

from core.expert_strategy import confirmed_swings
from core.fibonacci_contract import FIB_ANCHOR_VERSION
from core.steve_trade_management import atr_at
from core.fidelity_patch import (
    DEFAULT_PATCH_CONFIG,
    FidelityPatchConfig,
    M1EntryQualityEngine,
)
from core.sequence_recovery import final_invalidation_structure


M1_MONITORING_STATES = {
    "CLOSED",
    "ARMED",
    "ACTIVE",
    "ENTRY_FOUND",
    "CONSUMED_BY_M1",
    "CONSUMED_BY_M5",
    "CANCELLED",
    "EXPIRED",
}
M1_STOP_TERMINOLOGY = "M1_RELEVANT_SWING_BODY_EDGE"
M1_GRADES = {"A_PLUS_M1", "A_M1", "B_M1", "C_M1"}
OWNERSHIP_FIELDS = (
    "parent_m5_setup_id",
    "parent_m5_retracement_id",
    "parent_impulse_cycle_id",
    "parent_direction",
    "parent_protected_structure_id",
    "parent_fib_anchor_version",
)


def _number(value: Any) -> float:
    return float(value)


def _time(value: Any) -> float:
    if isinstance(value, pd.Timestamp):
        return float(value.timestamp())
    if isinstance(value, str):
        return float(pd.Timestamp(value).timestamp())
    return float(value)


def _close_time(data: pd.DataFrame, index: int, seconds: int) -> float:
    return _time(data.iloc[int(index)]["time"]) + float(seconds)


def validate_closed_series(
    data: pd.DataFrame,
    *,
    timeframe_seconds: int,
    decision_time: Optional[float] = None,
) -> Dict[str, Any]:
    """Validate one already-exported closed-candle series."""
    required = {"time", "open", "high", "low", "close"}
    missing = sorted(required.difference(data.columns))
    times = (
        data["time"].map(_time)
        if not missing and not data.empty
        else pd.Series(dtype=float)
    )
    duplicates = int(times.duplicated().sum()) if not times.empty else 0
    monotonic = bool(times.is_monotonic_increasing) if not times.empty else True
    unfinished = 0
    if decision_time is not None and not times.empty:
        unfinished = int(
            ((times + float(timeframe_seconds)) > float(decision_time)).sum()
        )
    gaps: list[Dict[str, Any]] = []
    if len(times) > 1:
        differences = times.diff().iloc[1:]
        for position, difference in differences.items():
            # Weekend/session gaps are published rather than silently filled.
            if difference > float(timeframe_seconds) * 1.5:
                gaps.append(
                    {
                        "index": int(position),
                        "previous_time": float(times.iloc[position - 1]),
                        "current_time": float(times.iloc[position]),
                        "seconds": float(difference),
                    }
                )
    valid = not missing and not duplicates and monotonic and not unfinished
    return {
        "owner": "SynchronizedM1ReplayCoordinator",
        "state": "VALID_CLOSED_SERIES" if valid else "INVALID_CANDLE_SERIES",
        "valid": valid,
        "missing_columns": missing,
        "duplicate_timestamps": duplicates,
        "monotonic": monotonic,
        "unfinished_candles": unfinished,
        "published_gaps": gaps,
        "gaps_hidden": False,
        "timezone": "UTC",
        "causal_valid": valid,
    }


def build_closed_candle_timeline(
    *,
    m5_data: pd.DataFrame,
    m1_data: pd.DataFrame,
) -> list[Dict[str, Any]]:
    """Merge M1/M5 close events and publish legal visibility at each time."""
    events: Dict[float, Dict[str, Any]] = {}
    for timeframe, data, seconds in (
        ("M1", m1_data, 60),
        ("M5", m5_data, 300),
    ):
        for index, value in enumerate(data["time"]):
            close_time = _time(value) + float(seconds)
            event = events.setdefault(
                close_time,
                {
                    "event_time": close_time,
                    "newly_closed_m5": [],
                    "newly_closed_m1": [],
                },
            )
            event[f"newly_closed_{timeframe.lower()}"].append(index)
    timeline: list[Dict[str, Any]] = []
    visible_m5 = -1
    visible_m1 = -1
    for event_time in sorted(events):
        event = events[event_time]
        if event["newly_closed_m5"]:
            visible_m5 = max(event["newly_closed_m5"])
        if event["newly_closed_m1"]:
            visible_m1 = max(event["newly_closed_m1"])
        timeline.append(
            {
                **event,
                "processing_order": (
                    ["M5_PARENT_UPDATE", "M1_CHILD_UPDATE", "M5_FALLBACK"]
                    if event["newly_closed_m5"]
                    else ["M1_CHILD_UPDATE"]
                ),
                "visible_m5_as_of_index": visible_m5,
                "visible_m1_as_of_index": visible_m1,
                "unfinished_m5_visible": False,
                "future_m1_visible_to_m5": False,
                "causal_valid": True,
            }
        )
    return timeline


def _body_edge(data: pd.DataFrame, index: int, direction: str) -> float:
    row = data.iloc[int(index)]
    lower = min(_number(row["open"]), _number(row["close"]))
    upper = max(_number(row["open"]), _number(row["close"]))
    return lower if direction == "BULLISH" else upper


def build_parent_contract(
    *,
    candidate: Dict[str, Any],
    m5_data: pd.DataFrame,
    symbol: str,
) -> Dict[str, Any]:
    """Bind one accepted M5 candidate to immutable child ownership IDs."""
    direction = str(candidate["direction"]).upper()
    setup_id = str(candidate["setup_id"])
    anchor = dict(candidate.get("anchor") or {})
    counter = dict(candidate.get("counter") or {})
    fibonacci = dict(candidate.get("fibonacci") or {})
    logical = dict(candidate.get("logical_stop_structure") or counter)
    entry_index = int(candidate["entry_index"])
    anchor_confirmation = int(
        anchor.get("confirmed_at_index", anchor["index"])
    )
    counter_confirmation = int(
        counter.get("confirmed_at_index", counter.get("index", anchor_confirmation))
    )
    origin_index = int(
        fibonacci.get("fib_zero_index", fibonacci.get("zero_anchor_index"))
    )
    extreme_index = int(
        fibonacci.get(
            "fib_hundred_index",
            fibonacci.get("hundred_anchor_index"),
        )
    )
    origin_price = _number(
        fibonacci.get("fib_zero_price", fibonacci.get("zero_anchor_price"))
    )
    extreme_price = _number(
        fibonacci.get(
            "fib_hundred_price",
            fibonacci.get("hundred_anchor_price"),
        )
    )
    logical_index = int(logical["index"])
    selected_invalidation = final_invalidation_structure(
        data=m5_data,
        direction=direction,
        entry_index=entry_index,
        setup_start_index=int(anchor["index"]),
        timeframe="M5",
    )
    logical_index = int(selected_invalidation["structure_index"])
    body_edge = _number(selected_invalidation["structure_body_edge"])
    m5_atr = atr_at(m5_data, as_of_index=entry_index)
    m5_stop = _number(
        selected_invalidation["logical_invalidation_boundary"]
    )
    m5_emergency_stop = (
        m5_stop - m5_atr
        if direction == "BULLISH"
        else m5_stop + m5_atr
    )
    protection_id = (
        f"{symbol}|M5|PROTECTION|{origin_index}|{origin_price:.10f}"
    )
    cycle_id = (
        f"{symbol}|M5|IMPULSE|{origin_index}|{extreme_index}|{direction}"
    )
    retracement_id = (
        f"{setup_id}|RETRACEMENT|{int(anchor['index'])}"
    )
    return {
        "owner": "SystemStateDirector",
        "state": "M5_PARENT_ACTIVE",
        "symbol": symbol,
        "timeframe": "M5",
        "parent_m5_setup_id": setup_id,
        "parent_m5_retracement_id": retracement_id,
        "parent_impulse_cycle_id": cycle_id,
        "parent_direction": direction,
        "parent_protected_structure_id": protection_id,
        "parent_fib_anchor_version": fibonacci.get(
            "fib_anchor_version",
            FIB_ANCHOR_VERSION,
        ),
        "armed_time": _close_time(
            m5_data,
            anchor_confirmation,
            300,
        ),
        "active_time": _close_time(
            m5_data,
            counter_confirmation,
            300,
        ),
        "m5_entry_time": _close_time(m5_data, entry_index, 300),
        "m5_entry_index": entry_index,
        "m5_entry_price": _number(candidate["entry_price"]),
        "m5_logical_stop": m5_stop,
        "m5_emergency_stop": m5_emergency_stop,
        "m5_logical_stop_structure_index": logical_index,
        "m5_logical_stop_structure_price": body_edge,
        "m5_logical_stop_contract": selected_invalidation,
        "m5_failure_trigger_index": int(candidate["trigger"]["index"]),
        "m5_failure_trigger_price": _number(candidate["trigger"]["level"]),
        "m5_retracement_start_index": int(anchor["index"]),
        "m5_retracement_start_time": _time(
            m5_data.iloc[int(anchor["index"])]["time"]
        ),
        "price_boundary_low": min(origin_price, extreme_price),
        "price_boundary_high": max(origin_price, extreme_price),
        "dominant_protection_level": origin_price,
        "dominant_protection_intact": not bool(
            fibonacci.get("dominant_origin_breached", False)
        ),
        "remaining_impulse_ratio": fibonacci.get(
            "remaining_impulse_ratio"
        ),
        "remaining_impulse_percent": fibonacci.get(
            "remaining_impulse_percent"
        ),
        "retracement_depth_ratio": fibonacci.get(
            "retracement_depth_ratio",
            fibonacci.get("depth"),
        ),
        "fibonacci_zone": fibonacci.get("remaining_zone", fibonacci.get("zone")),
        "fibonacci_levels": dict(fibonacci.get("levels") or {}),
        "fib_zero_index": origin_index,
        "fib_zero_price": origin_price,
        "fib_hundred_index": extreme_index,
        "fib_hundred_price": extreme_price,
        "entry_opportunity_consumed": False,
        "reentry_count": 0,
        "maximum_reentries": 1,
        "causal_valid": bool(
            anchor_confirmation <= counter_confirmation <= entry_index
        ),
        "closed_candles_only": True,
        "research_only": True,
        "order_api_called": False,
        "_candidate": candidate,
    }


def ownership_payload(parent: Dict[str, Any]) -> Dict[str, Any]:
    return {field: parent.get(field) for field in OWNERSHIP_FIELDS}


def validate_m1_ownership(
    *,
    parent: Dict[str, Any],
    child: Dict[str, Any],
) -> Dict[str, Any]:
    mismatches = [
        field
        for field in OWNERSHIP_FIELDS
        if child.get(field) != parent.get(field)
    ]
    return {
        "owner": "M1ChildStructureEngine",
        "state": (
            "M1_PARENT_OWNERSHIP_MATCHED"
            if not mismatches
            else "M1_PARENT_OWNERSHIP_REJECTED"
        ),
        "matched": not mismatches,
        "mismatched_fields": mismatches,
        "hard_block": bool(mismatches),
        "causal_valid": True,
        "reasons": (
            ["Every M1 ownership field matches the active M5 parent"]
            if not mismatches
            else [
                "M1 event cannot attach to the parent because these fields "
                f"differ: {', '.join(mismatches)}"
            ]
        ),
    }


def _m1_grade(
    *,
    parent: Dict[str, Any],
    bos_body_atr: float,
    internal_swings: int,
    overlap_ratio: float,
) -> Dict[str, Any]:
    score = 0
    soft: list[str] = []
    positives: list[str] = []
    zone = str(parent.get("fibonacci_zone") or "")
    if zone == "STEVE_PRIMARY_DEEP_SWEET_SPOT":
        score += 3
        positives.append("STEVE_PRIMARY_DEEP_SWEET_SPOT")
    elif zone in {
        "38_2_TO_61_8_REMAINING",
        "61_8_TO_78_6_REMAINING",
    }:
        score += 2
        positives.append("RELEVANT_FIBONACCI_LOCATION")
    else:
        score += 1
        soft.append("FIBONACCI_OUTSIDE_PRIMARY_SWEET_SPOT")
    if bos_body_atr >= 0.8:
        score += 3
        positives.append("STRONG_M1_DISPLACEMENT")
    elif bos_body_atr >= 0.35:
        score += 2
        positives.append("MEANINGFUL_M1_BOS_BODY")
    else:
        soft.append("WEAK_M1_BOS_BODY")
    if internal_swings >= 4:
        score += 2
        positives.append("CLEAN_M1_COUNTER_SEQUENCE")
    elif internal_swings >= 3:
        score += 1
    else:
        soft.append("MINIMAL_M1_COUNTER_SEQUENCE")
    if overlap_ratio > 0.65:
        soft.append("HIGH_M1_CANDLE_OVERLAP")
    else:
        score += 1
    grade = (
        "A_PLUS_M1"
        if score >= 8
        else "A_M1"
        if score >= 6
        else "B_M1"
        if score >= 3
        else "C_M1"
    )
    return {
        "grade": grade,
        "hard_blockers": [],
        "soft_factors": soft,
        "positive_factors": positives,
        "risk_modifier": {
            "A_PLUS_M1": 1.0,
            "A_M1": 0.85,
            "B_M1": 0.60,
            "C_M1": 0.30,
        }[grade],
    }


def _first_body_close(
    *,
    data: pd.DataFrame,
    start_index: int,
    end_index: int,
    direction: str,
    trigger_level: float,
) -> tuple[Optional[int], list[Dict[str, Any]]]:
    rejections: list[Dict[str, Any]] = []
    for index in range(int(start_index), int(end_index) + 1):
        row = data.iloc[index]
        open_price = _number(row["open"])
        close = _number(row["close"])
        high = _number(row["high"])
        low = _number(row["low"])
        close_break = (
            close > trigger_level
            if direction == "BULLISH"
            else close < trigger_level
        )
        correct_body = (
            close > open_price
            if direction == "BULLISH"
            else close < open_price
        )
        wick_break = (
            high > trigger_level and close <= trigger_level
            if direction == "BULLISH"
            else low < trigger_level and close >= trigger_level
        )
        if wick_break:
            rejections.append(
                {
                    "state": "M1_WICK_ONLY_BOS_REJECTED",
                    "m1_index": index,
                    "trigger_level": trigger_level,
                    "hard_blockers": ["WICK_ONLY_BOS"],
                }
            )
        if close_break and correct_body:
            return index, rejections
        if close_break and not correct_body:
            rejections.append(
                {
                    "state": "M1_WRONG_BODY_DIRECTION_REJECTED",
                    "m1_index": index,
                    "trigger_level": trigger_level,
                    "hard_blockers": ["WRONG_BOS_BODY_DIRECTION"],
                }
            )
    return None, rejections


def find_m1_child_entry(
    *,
    parent: Dict[str, Any],
    m1_data: pd.DataFrame,
    sensitivity: int = 2,
    max_trigger_age: int = 30,
    minimum_counter_bars: int = 3,
    quality_config: FidelityPatchConfig = DEFAULT_PATCH_CONFIG,
) -> Dict[str, Any]:
    """
    Find the first causal M1 entry inside one active M5 parent window.

    The detector recognizes a trigger-side swing, a meaningful opposing swing,
    and a fresh trigger-side reaction before requiring the body-close BOS.
    """
    direction = str(parent["parent_direction"]).upper()
    times = m1_data["time"].map(_time)
    closes = times + 60.0
    armed_global = int(closes.searchsorted(float(parent["armed_time"]), side="left"))
    active_global = int(closes.searchsorted(float(parent["active_time"]), side="left"))
    end_global = int(
        closes.searchsorted(float(parent["m5_entry_time"]), side="right") - 1
    )
    base = {
        "availability": "AVAILABLE",
        "available": True,
        "owner": "M1ChildStructureEngine",
        "source_timeframe": "M1",
        "parent_timeframe": "M5",
        **ownership_payload(parent),
        "m1_was_monitored": active_global <= end_global,
        "monitoring_armed_m1_index": armed_global,
        "monitoring_active_m1_index": active_global,
        "monitoring_end_m1_index": end_global,
        "causal_valid": True,
        "closed_candles_only": True,
        "future_data_used": False,
        "research_only": True,
        "order_api_called": False,
    }
    if not parent.get("dominant_protection_intact"):
        return {
            **base,
            "state": "CANCELLED",
            "entry_ready": False,
            "entry": None,
            "rejections": [
                {
                    "state": "M1_REJECTED_DOMINANT_PROTECTION_BROKEN",
                    "hard_blockers": ["DOMINANT_M5_PROTECTION_BROKEN"],
                }
            ],
        }
    if active_global > end_global or end_global < 0:
        return {
            **base,
            "state": "CLOSED",
            "entry_ready": False,
            "entry": None,
            "rejections": [
                {
                    "state": "M1_REJECTED_NO_SYNCHRONIZED_ACTIVE_WINDOW",
                    "hard_blockers": ["NO_ACTIVE_PARENT_WINDOW"],
                }
            ],
        }

    window_start = max(0, armed_global - sensitivity)
    window_end = min(len(m1_data) - 1, end_global)
    window = m1_data.iloc[window_start : window_end + 1].reset_index(drop=True)
    swings = confirmed_swings(
        window,
        as_of_index=len(window) - 1,
        sensitivity=sensitivity,
    )
    for point in swings:
        point["global_index"] = window_start + int(point["index"])
        point["global_confirmed_at_index"] = (
            window_start + int(point["confirmed_at_index"])
        )

    trigger_side = "HIGH" if direction == "BULLISH" else "LOW"
    counter_side = "LOW" if direction == "BULLISH" else "HIGH"
    rejections: list[Dict[str, Any]] = []
    trigger_points = [
        point
        for point in swings
        if point["side"] == trigger_side
        and int(point["global_confirmed_at_index"]) <= end_global
    ]
    for trigger in trigger_points:
        trigger_index = int(trigger["global_index"])
        trigger_available = int(trigger["global_confirmed_at_index"])
        if trigger_available < active_global:
            rejections.append(
                {
                    "state": "M1_TRIGGER_BEFORE_PARENT_ACTIVE_REJECTED",
                    "m1_index": trigger_available,
                    "hard_blockers": ["M5_PARENT_NOT_ACTIVE"],
                }
            )
            continue
        counters = [
            point
            for point in swings
            if point["side"] == counter_side
            and int(point["global_index"]) < trigger_index
            and int(point["global_confirmed_at_index"]) <= trigger_available
        ]
        if not counters:
            rejections.append(
                {
                    "state": "M1_RANDOM_BOS_REJECTED_NO_COUNTER_STRUCTURE",
                    "m1_index": trigger_available,
                    "hard_blockers": ["NO_MEANINGFUL_M1_COUNTER_STRUCTURE"],
                }
            )
            continue
        counter = max(counters, key=lambda value: int(value["global_index"]))
        initial_points = [
            point
            for point in swings
            if point["side"] == trigger_side
            and int(point["global_index"]) < int(counter["global_index"])
            and int(point["global_index"]) >= armed_global - sensitivity
        ]
        if not initial_points:
            rejections.append(
                {
                    "state": "M1_RANDOM_BOS_REJECTED_INCOMPLETE_SEQUENCE",
                    "m1_index": trigger_available,
                    "hard_blockers": ["NO_MEANINGFUL_M1_COUNTER_STRUCTURE"],
                }
            )
            continue
        initial = max(
            initial_points,
            key=lambda value: int(value["global_index"]),
        )
        local_atr = atr_at(m1_data, as_of_index=trigger_available)
        counter_displacement = abs(
            _number(initial["level"]) - _number(counter["level"])
        )
        meaningful = (
            counter_displacement / local_atr >= 0.35
            if local_atr > 0
            else counter_displacement > 0
        )
        counter_bars = (
            int(counter["global_index"]) - int(initial["global_index"])
        )
        if counter_bars < int(minimum_counter_bars):
            rejections.append(
                {
                    "state": "M1_RANDOM_BOS_REJECTED_ONE_CANDLE_NOISE",
                    "m1_index": trigger_available,
                    "hard_blockers": ["NO_MEANINGFUL_M1_COUNTER_STRUCTURE"],
                }
            )
            continue
        if not meaningful:
            rejections.append(
                {
                    "state": "M1_RANDOM_BOS_REJECTED_MICRO_NOISE",
                    "m1_index": trigger_available,
                    "hard_blockers": ["NO_MEANINGFUL_M1_COUNTER_STRUCTURE"],
                }
            )
            continue

        entry_index, wick_rejections = _first_body_close(
            data=m1_data,
            start_index=trigger_available,
            end_index=end_global,
            direction=direction,
            trigger_level=_number(trigger["level"]),
        )
        rejections.extend(wick_rejections)
        if entry_index is None:
            continue
        if entry_index < active_global:
            rejections.append(
                {
                    "state": "M1_BOS_BEFORE_PARENT_ACTIVE_REJECTED",
                    "m1_index": entry_index,
                    "hard_blockers": ["M5_PARENT_NOT_ACTIVE"],
                }
            )
            continue
        if entry_index - trigger_available > int(max_trigger_age):
            rejections.append(
                {
                    "state": "M1_STALE_TRIGGER_REJECTED",
                    "m1_index": entry_index,
                    "hard_blockers": ["STALE_TRIGGER"],
                }
            )
            continue
        entry_price = _number(m1_data.iloc[entry_index]["close"])
        location_buffer = max(local_atr * 0.25, 1e-12)
        in_parent_price = (
            _number(parent["price_boundary_low"]) - location_buffer
            <= entry_price
            <= _number(parent["price_boundary_high"]) + location_buffer
        )
        if not in_parent_price:
            rejections.append(
                {
                    "state": "M1_TRIGGER_OUTSIDE_PARENT_PRICE_BOUNDARY",
                    "m1_index": entry_index,
                    "hard_blockers": ["OUTSIDE_PARENT_RETRACEMENT_PRICE"],
                }
            )
            continue
        stop_points = [
            point
            for point in swings
            if point["side"] == counter_side
            and int(point["global_index"]) < entry_index
            and int(point["global_index"]) >= int(counter["global_index"])
            and int(point["global_confirmed_at_index"]) <= entry_index
        ]
        stop_owner = (
            max(stop_points, key=lambda value: int(value["global_index"]))
            if stop_points
            else counter
        )
        stop_index = int(stop_owner["global_index"])
        logical_stop = _body_edge(m1_data, stop_index, direction)
        correct_stop_side = (
            logical_stop < entry_price
            if direction == "BULLISH"
            else logical_stop > entry_price
        )
        if not correct_stop_side:
            rejections.append(
                {
                    "state": "M1_LOGICAL_STOP_WRONG_SIDE_REJECTED",
                    "m1_index": entry_index,
                    "hard_blockers": ["LOGICAL_STOP_WRONG_SIDE"],
                }
            )
            continue
        body = abs(
            _number(m1_data.iloc[entry_index]["close"])
            - _number(m1_data.iloc[entry_index]["open"])
        )
        bos_body_atr = body / local_atr if local_atr > 0 else 0.0
        sequence = [
            point
            for point in swings
            if int(initial["global_index"])
            <= int(point["global_index"])
            <= entry_index
        ]
        recent = m1_data.iloc[max(0, entry_index - 5) : entry_index + 1]
        ranges = (
            recent["high"].astype(float) - recent["low"].astype(float)
        )
        overlap_ratio = float(
            (ranges <= max(local_atr, 1e-12)).mean()
        )
        legacy_grade = _m1_grade(
            parent=parent,
            bos_body_atr=bos_body_atr,
            internal_swings=len(sequence),
            overlap_ratio=overlap_ratio,
        )
        quality = M1EntryQualityEngine(quality_config).evaluate(
            data=m1_data,
            parent=parent,
            initial_index=int(initial["global_index"]),
            counter_index=int(counter["global_index"]),
            trigger_index=trigger_index,
            trigger_available_index=trigger_available,
            entry_index=entry_index,
            trigger_level=_number(trigger["level"]),
            entry_price=entry_price,
            logical_stop=logical_stop,
            local_atr=local_atr,
            internal_swings=len(sequence),
            overlap_ratio=overlap_ratio,
        )
        if quality["observe_only"]:
            rejections.append(
                {
                    "state": "M1_LOW_VALUE_OBSERVE_ONLY",
                    "m1_index": entry_index,
                    "hard_blockers": [],
                    "structurally_valid": True,
                    "quality": quality,
                    "reason": (
                        "Structural validity is preserved; configured research "
                        "policy reserves this low-value signal for observation."
                    ),
                }
            )
            continue
        emergency = (
            min(
                _number(m1_data.iloc[stop_index]["low"]),
                logical_stop - local_atr,
            )
            if direction == "BULLISH"
            else max(
                _number(m1_data.iloc[stop_index]["high"]),
                logical_stop + local_atr,
            )
        )
        child = {
            **ownership_payload(parent),
            "state": "M1_ENTRY_FOUND",
            "entry_ready": True,
            "entry_timeframe": "M1",
            "entry_reason": "M1_OWNED_COUNTER_FAILURE_BODY_CLOSE_BOS",
            "entry_index": entry_index,
            "entry_time": _close_time(m1_data, entry_index, 60),
            "entry_price": entry_price,
            "counter_structure_index": int(counter["global_index"]),
            "counter_structure_price": _number(counter["level"]),
            "failure_trigger_index": trigger_index,
            "failure_trigger_available_at_index": trigger_available,
            "failure_trigger_price": _number(trigger["level"]),
            "bos_body_atr": bos_body_atr,
            "logical_stop_owner_index": stop_index,
            "logical_stop_owner_side": counter_side,
            "logical_stop_terminology": M1_STOP_TERMINOLOGY,
            "logical_stop": logical_stop,
            "stop_distance_m1": abs(entry_price - logical_stop),
            "emergency_stop": emergency,
            "wick_only_bos": False,
            "trigger_consumed": True,
            "fresh_trigger": True,
            "inside_parent_time_boundary": True,
            "inside_parent_price_boundary": True,
            "ownership": validate_m1_ownership(
                parent=parent,
                child=ownership_payload(parent),
            ),
            "legacy_quality": legacy_grade,
            "quality": quality,
            "m1_quality_score": quality["m1_quality_score"],
            "grade": quality["grade"],
            "quality_classification": quality["classification"],
            "hard_blockers": [],
            "soft_factors": quality["negative_reasons"],
            "positive_factors": quality["positive_reasons"],
            "risk_modifier": {
                "FULL_RESEARCH_RISK": 1.0,
                "STANDARD_RESEARCH_RISK": 0.85,
                "REDUCED_RESEARCH_RISK": 0.60,
            }[quality["research_policy"]],
            "causal_valid": bool(
                trigger_available <= entry_index
                and _close_time(m1_data, entry_index, 60)
                <= float(parent["m5_entry_time"])
            ),
            "future_data_used": False,
            "closed_candles_only": True,
            "order_api_called": False,
        }
        return {
            **base,
            "state": "ENTRY_FOUND",
            "entry_ready": True,
            "entry": child,
            "rejections": rejections,
        }
    return {
        **base,
        "state": "ACTIVE",
        "entry_ready": False,
        "entry": None,
        "rejections": rejections,
    }


def _advantage_classification(
    *,
    minutes_saved: float,
    stop_reduction_percent: float,
    m5_confirmed: bool,
    m1_failed_early: bool = False,
) -> str:
    if m1_failed_early and not m5_confirmed:
        return "M1_FALSE_EARLY_ENTRY"
    if not m5_confirmed:
        return "M1_SAVED_VALID_MOVE"
    if stop_reduction_percent >= 25.0 and minutes_saved >= 5.0:
        return "M1_CLEAR_ADVANTAGE"
    if stop_reduction_percent > 0.0 or minutes_saved > 0.0:
        return "M1_SMALL_ADVANTAGE"
    if stop_reduction_percent < 0.0:
        return "M5_WAS_BETTER"
    return "M1_NO_ADVANTAGE"


def arbitrate_first_valid_entry(
    *,
    parent: Dict[str, Any],
    m1_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply first-valid ownership and publish the hypothetical alternative."""
    m1_entry = m1_result.get("entry") if m1_result.get("entry_ready") else None
    m5_time = float(parent["m5_entry_time"])
    m5_price = _number(parent["m5_entry_price"])
    m5_stop = _number(parent["m5_logical_stop"])
    if m1_entry is not None and float(m1_entry["entry_time"]) <= m5_time:
        owner = "M1"
        chosen = dict(m1_entry)
        minutes_saved = (m5_time - float(m1_entry["entry_time"])) / 60.0
        m1_distance = _number(m1_entry["stop_distance_m1"])
        m5_distance = abs(m5_price - m5_stop)
        reduction = (
            (m5_distance - m1_distance) / m5_distance * 100.0
            if m5_distance > 0
            else 0.0
        )
        price_improvement = (
            m5_price - _number(m1_entry["entry_price"])
            if parent["parent_direction"] == "BULLISH"
            else _number(m1_entry["entry_price"]) - m5_price
        )
        m1_risk = max(m1_distance, 1e-12)
        m5_risk = max(m5_distance, 1e-12)
        objective = (
            _number(parent["fib_hundred_price"])
            if (
                parent["parent_direction"] == "BULLISH"
                and _number(parent["fib_hundred_price"])
                > _number(m1_entry["entry_price"])
            )
            or (
                parent["parent_direction"] == "BEARISH"
                and _number(parent["fib_hundred_price"])
                < _number(m1_entry["entry_price"])
            )
            else m5_price
        )
        m1_rr = abs(objective - _number(m1_entry["entry_price"])) / m1_risk
        m5_rr = abs(objective - m5_price) / m5_risk
        advantage = {
            "m1_entry_time": float(m1_entry["entry_time"]),
            "m1_entry_price": _number(m1_entry["entry_price"]),
            "m1_logical_stop": _number(m1_entry["logical_stop"]),
            "m1_stop_distance": m1_distance,
            "next_valid_m5_entry_time": m5_time,
            "next_valid_m5_entry_price": m5_price,
            "hypothetical_m5_stop": m5_stop,
            "hypothetical_m5_stop_distance": m5_distance,
            "minutes_entered_earlier": minutes_saved,
            "m1_candles_entered_earlier": int(round(minutes_saved)),
            "price_improvement_from_m1": price_improvement,
            "stop_reduction_percent": reduction,
            "rr_m1": m1_rr,
            "rr_hypothetical_m5": m5_rr,
            "rr_improvement_from_m1": m1_rr - m5_rr,
            "m1_false_early_entry": False,
            "m5_later_confirmed": True,
            "m5_never_confirmed": False,
            "classification": _advantage_classification(
                minutes_saved=minutes_saved,
                stop_reduction_percent=reduction,
                m5_confirmed=True,
            ),
        }
    else:
        owner = "M5"
        chosen = {
            **ownership_payload(parent),
            "state": "M5_FALLBACK_ENTRY",
            "entry_ready": True,
            "entry_timeframe": "M5",
            "entry_reason": "NO_VALID_EARLIER_M1_ENTRY",
            "entry_index": int(parent["m5_entry_index"]),
            "entry_time": m5_time,
            "entry_price": m5_price,
            "logical_stop": m5_stop,
            "emergency_stop": parent.get("m5_emergency_stop"),
            "stop_distance_m5": abs(m5_price - m5_stop),
            "causal_valid": True,
            "future_data_used": False,
            "order_api_called": False,
        }
        advantage = None
    return {
        "owner": "FirstValidEntryArbiter",
        "state": (
            "CONSUMED_BY_M1" if owner == "M1" else "CONSUMED_BY_M5"
        ),
        "entry_owner": owner,
        "entry": chosen,
        "m1_was_monitored": bool(m1_result.get("m1_was_monitored")),
        "m1_rejection_reasons": [
            rejection.get("state")
            for rejection in m1_result.get("rejections", [])
        ],
        "m5_entry_avoided_due_to_prior_m1": owner == "M1",
        "duplicate_m5_entry_blocked": owner == "M1",
        "m1_gate_closed": True,
        "advantage": advantage,
        "causal_valid": bool(chosen.get("causal_valid", True)),
        "future_data_used": False,
        "order_api_called": False,
    }


@dataclass
class ParentEntryLifecycle:
    parent_m5_setup_id: str
    consumed_by: Optional[str] = None
    first_attempt_failed: bool = False
    reentry_count: int = 0
    terminal: bool = False
    events: list[Dict[str, Any]] = field(default_factory=list)

    def claim(self, *, timeframe: str, event_time: float) -> bool:
        if self.terminal or self.consumed_by is not None:
            self.events.append(
                {
                    "event": "DUPLICATE_ENTRY_REJECTED",
                    "timeframe": timeframe,
                    "event_time": float(event_time),
                }
            )
            return False
        self.consumed_by = str(timeframe).upper()
        self.events.append(
            {
                "event": "FIRST_ENTRY_CONSUMED",
                "timeframe": self.consumed_by,
                "event_time": float(event_time),
            }
        )
        return True

    def fail_first_attempt(
        self,
        *,
        dominant_protection_intact: bool,
        parent_retracement_valid: bool,
    ) -> bool:
        self.first_attempt_failed = True
        self.consumed_by = None
        allowed = bool(
            dominant_protection_intact
            and parent_retracement_valid
            and self.reentry_count == 0
            and not self.terminal
        )
        self.events.append(
            {
                "event": (
                    "REENTRY_GATE_REOPENED"
                    if allowed
                    else "REENTRY_DENIED"
                ),
                "dominant_protection_intact": dominant_protection_intact,
                "parent_retracement_valid": parent_retracement_valid,
            }
        )
        if not allowed:
            self.terminal = True
        return allowed

    def claim_reentry(self, *, timeframe: str, event_time: float) -> bool:
        if (
            self.terminal
            or not self.first_attempt_failed
            or self.reentry_count >= 1
            or self.consumed_by is not None
        ):
            self.events.append(
                {
                    "event": "REENTRY_REJECTED",
                    "timeframe": timeframe,
                    "event_time": float(event_time),
                }
            )
            return False
        self.reentry_count = 1
        self.consumed_by = str(timeframe).upper()
        self.events.append(
            {
                "event": "ONE_REENTRY_CONSUMED",
                "timeframe": self.consumed_by,
                "event_time": float(event_time),
            }
        )
        return True


def evaluate_synchronized_parent(
    *,
    candidate: Dict[str, Any],
    m5_data: pd.DataFrame,
    m1_data: pd.DataFrame,
    symbol: str,
    sensitivity: int = 2,
) -> Dict[str, Any]:
    parent = build_parent_contract(
        candidate=candidate,
        m5_data=m5_data,
        symbol=symbol,
    )
    m1 = find_m1_child_entry(
        parent=parent,
        m1_data=m1_data,
        sensitivity=sensitivity,
    )
    decision = arbitrate_first_valid_entry(
        parent=parent,
        m1_result=m1,
    )
    lifecycle = ParentEntryLifecycle(parent["parent_m5_setup_id"])
    claimed = lifecycle.claim(
        timeframe=decision["entry_owner"],
        event_time=float(decision["entry"]["entry_time"]),
    )
    return {
        "owner": "SynchronizedM1ReplayCoordinator",
        "state": decision["state"],
        "parent": parent,
        "m1": m1,
        "decision": decision,
        "entry_claimed": claimed,
        "lifecycle": {
            "parent_m5_setup_id": lifecycle.parent_m5_setup_id,
            "consumed_by": lifecycle.consumed_by,
            "reentry_count": lifecycle.reentry_count,
            "events": list(lifecycle.events),
        },
        "causal_valid": bool(
            parent["causal_valid"]
            and m1["causal_valid"]
            and decision["causal_valid"]
        ),
        "future_data_used": False,
        "unfinished_candle_used": False,
        "duplicate_first_entries": 0,
        "unrelated_parent_attachments": 0,
        "order_api_called": False,
    }
