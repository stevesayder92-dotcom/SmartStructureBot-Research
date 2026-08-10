from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy
from typing import Any, Dict, Iterable, Optional

import pandas as pd

from core.expert_strategy import confirmed_swings
from core.fibonacci_contract import (
    FIB_ANCHOR_VERSION,
    classify_remaining,
    reassess_same_cycle,
)
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
COUNTER_CONFIRMED_ACTIVE = "COUNTER_CONFIRMED_ACTIVE"
EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE = (
    "EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE"
)
M1_PERMISSION_POLICIES = {
    COUNTER_CONFIRMED_ACTIVE,
    EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE,
}
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
    retrospective_outcome_available: bool = True,
) -> Dict[str, Any]:
    """Bind one M5 parent while separating causal context from later outcome."""
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
    active_index = min(counter_confirmation, len(m5_data) - 1)
    try:
        active_fibonacci = reassess_same_cycle(
            data=m5_data,
            original=fibonacci,
            as_of_index=active_index,
        )
    except (KeyError, TypeError, ValueError, IndexError):
        active_fibonacci = dict(fibonacci)
    active_closes = m5_data.iloc[origin_index : active_index + 1]["close"].astype(float)
    protection_intact_at_active = bool(
        not active_closes.empty
        and (
            (active_closes > origin_price).all()
            if direction == "BULLISH"
            else (active_closes < origin_price).all()
        )
    )
    causal_parent_context = {
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
        "m5_retracement_start_index": int(anchor["index"]),
        "m5_retracement_start_time": _time(
            m5_data.iloc[int(anchor["index"])]["time"]
        ),
        "price_boundary_low": min(origin_price, extreme_price),
        "price_boundary_high": max(origin_price, extreme_price),
        "dominant_protection_level": origin_price,
        "dominant_protection_intact": protection_intact_at_active,
        "dominant_protection_as_of": "PARENT_ACTIVE",
        "remaining_impulse_ratio": active_fibonacci.get(
            "remaining_impulse_ratio"
        ),
        "remaining_impulse_percent": active_fibonacci.get(
            "remaining_impulse_percent"
        ),
        "retracement_depth_ratio": active_fibonacci.get(
            "retracement_depth_ratio",
            active_fibonacci.get("depth"),
        ),
        "fibonacci_zone": active_fibonacci.get(
            "remaining_zone", active_fibonacci.get("zone")
        ),
        "fibonacci_levels": dict(active_fibonacci.get("levels") or fibonacci.get("levels") or {}),
        "fib_zero_index": origin_index,
        "fib_zero_price": origin_price,
        "fib_hundred_index": extreme_index,
        "fib_hundred_price": extreme_price,
        "fib_hundred_time": _time(m5_data.iloc[extreme_index]["time"]),
        "anchor_confirmed_at_index": anchor_confirmation,
        "counter_confirmed_at_index": counter_confirmation,
        "field_availability": {
            "identity": "CAUSAL_AT_ARMED",
            "anchor": "CAUSAL_AT_ARMED",
            "price_boundary": "CAUSAL_AT_ARMED",
            "fibonacci_anchors": "CAUSAL_AT_ARMED",
            "counter": "CAUSAL_AT_ACTIVE",
            "dominant_protection_intact": "CAUSAL_AT_M1_ENTRY_RECOMPUTED",
            "fibonacci_zone": "CAUSAL_AT_M1_ENTRY_RECOMPUTED",
        },
        "as_of_time": _close_time(m5_data, counter_confirmation, 300),
        "as_of_m5_index": counter_confirmation,
        "entry_opportunity_consumed": False,
        "reentry_count": 0,
        "maximum_reentries": 1,
        "causal_valid": bool(
            anchor_confirmation <= counter_confirmation <= entry_index
        ),
        "closed_candles_only": True,
        "research_only": True,
        "order_api_called": False,
    }
    retrospective_m5_outcome = {
        "owner": "SynchronizedM1ReplayCoordinator",
        "state": (
            "RETROSPECTIVE_M5_OUTCOME_AVAILABLE"
            if retrospective_outcome_available
            else "RETROSPECTIVE_M5_OUTCOME_PENDING"
        ),
        "availability": (
            "AVAILABLE" if retrospective_outcome_available else "PENDING"
        ),
        "analytics_only": True,
        "may_influence_canonical_m1": False,
        "m5_entry_time": _close_time(m5_data, entry_index, 300),
        "m5_entry_index": entry_index,
        "m5_entry_price": _number(candidate["entry_price"]),
        "m5_logical_stop": m5_stop,
        "m5_emergency_stop": m5_emergency_stop,
        "m5_logical_stop_structure_index": logical_index,
        "m5_logical_stop_structure_price": body_edge,
        "m5_logical_stop_contract": deepcopy(selected_invalidation),
        "m5_failure_trigger_index": int(candidate["trigger"]["index"]),
        "m5_failure_trigger_price": _number(candidate["trigger"]["level"]),
        "m5_failure_trigger_confirmed_at_index": int(candidate["qualified_at"]),
        "candidate": deepcopy(candidate),
    }
    return {
        **causal_parent_context,
        "causal_parent_context": deepcopy(causal_parent_context),
        "retrospective_m5_outcome": retrospective_m5_outcome,
        "contract_version": "S2A1_CAUSAL_PARENT_V1",
    }


def ownership_payload(parent: Dict[str, Any]) -> Dict[str, Any]:
    return {field: parent.get(field) for field in OWNERSHIP_FIELDS}


def evaluate_m1_permission(
    *,
    parent: Dict[str, Any],
    decision_time: float,
    policy: str = COUNTER_CONFIRMED_ACTIVE,
) -> Dict[str, Any]:
    """Publish the causal permission state without redefining parent ACTIVE."""
    if policy not in M1_PERMISSION_POLICIES:
        raise ValueError(f"Unsupported M1 permission policy: {policy}")
    armed_time = float(parent["armed_time"])
    active_time = parent.get("active_time")
    active = active_time is not None and float(decision_time) >= float(active_time)
    armed = float(decision_time) >= armed_time
    invalid_reasons: list[str] = []
    if parent.get("causal_htf_ownership_accepted") is False:
        invalid_reasons.append("HTF_OWNERSHIP_REJECTED")
    if parent.get("parent_invalidated"):
        invalid_reasons.append("PARENT_INVALIDATED")
    if parent.get("parent_superseded"):
        invalid_reasons.append("PARENT_SUPERSEDED")
    if parent.get("dominant_protection_intact") is False:
        invalid_reasons.append("DOMINANT_M5_PROTECTION_BROKEN")
    if parent.get("entry_opportunity_consumed"):
        invalid_reasons.append("PARENT_ALREADY_CONSUMED")
    if not parent.get("parent_m5_setup_id"):
        invalid_reasons.append("PARENT_IDENTITY_UNAVAILABLE")
    if not armed:
        invalid_reasons.append("PARENT_NOT_ARMED")
    baseline_allowed = bool(active and not invalid_reasons)
    early_evaluation_allowed = bool(
        policy == EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE
        and armed
        and not active
        and not invalid_reasons
    )
    return {
        "owner": "M1PermissionPolicyEngine",
        "policy": policy,
        "parent_state": (
            "PARENT_ACTIVE" if active else "PARENT_ARMED" if armed else "PARENT_NOT_AVAILABLE"
        ),
        "state": (
            "COUNTER_CONFIRMED_ACTIVE_PERMISSION"
            if baseline_allowed
            else "EARLY_M1_EVALUATION_ALLOWED"
            if early_evaluation_allowed
            else "M1_PERMISSION_NOT_AVAILABLE"
        ),
        "observation_allowed": bool(armed and not invalid_reasons),
        "normal_active_permission": baseline_allowed,
        "early_evaluation_allowed": early_evaluation_allowed,
        "early_permission_earned": False,
        "execution_permitted": baseline_allowed,
        "reasons": invalid_reasons,
        "as_of_time": float(decision_time),
        "causal_valid": True,
        "research_only": True,
        "live_demo_capable": False,
        "order_api_called": False,
    }


def retrospective_m5_outcome(parent: Dict[str, Any]) -> Dict[str, Any]:
    """Return analytics-only M5 outcome, with legacy fixture compatibility."""
    nested = dict(parent.get("retrospective_m5_outcome") or {})
    if nested:
        return nested
    legacy = {
        key: parent.get(key)
        for key in (
            "m5_entry_time",
            "m5_entry_index",
            "m5_entry_price",
            "m5_logical_stop",
            "m5_emergency_stop",
        )
        if parent.get(key) is not None
    }
    return {
        "availability": "AVAILABLE" if legacy else "UNAVAILABLE",
        "analytics_only": True,
        "may_influence_canonical_m1": False,
        **legacy,
    }


def causal_parent_snapshot(
    *,
    parent: Dict[str, Any],
    m1_data: pd.DataFrame,
    decision_time: float,
) -> Dict[str, Any]:
    """Recompute time-varying parent facts using only M1 closes visible at T."""
    context = deepcopy(parent.get("causal_parent_context") or parent)
    closes = m1_data["time"].map(_time) + 60.0
    as_of_index = int(closes.searchsorted(float(decision_time), side="right") - 1)
    visible = m1_data.iloc[: max(0, as_of_index + 1)]
    hundred_time = float(context.get("fib_hundred_time") or context["armed_time"])
    retracement = visible[
        visible["time"].map(_time) >= hundred_time
    ]
    direction = str(context["parent_direction"]).upper()
    zero = _number(
        context.get("fib_zero_price")
        if context.get("fib_zero_price") is not None
        else context["price_boundary_low"]
        if direction == "BULLISH"
        else context["price_boundary_high"]
    )
    hundred = _number(context["fib_hundred_price"])
    context.setdefault("fib_zero_price", zero)
    impulse = abs(hundred - zero)
    remaining: Optional[float] = None
    if impulse > 0.0 and not retracement.empty:
        if str(context["parent_direction"]).upper() == "BULLISH":
            retracement_price = float(retracement["low"].astype(float).min())
            remaining = (retracement_price - zero) / impulse
        else:
            retracement_price = float(retracement["high"].astype(float).max())
            remaining = (zero - retracement_price) / impulse
    protection_visible = visible[
        closes.iloc[: len(visible)] >= float(context["armed_time"])
    ]
    protection_intact = bool(
        not protection_visible.empty
        and (
            (protection_visible["close"].astype(float) > zero).all()
            if direction == "BULLISH"
            else (protection_visible["close"].astype(float) < zero).all()
        )
    )
    context.update(
        {
            "dominant_protection_intact": protection_intact,
            "dominant_protection_as_of": "M1_DECISION_CLOSE",
            "remaining_impulse_ratio": remaining,
            "remaining_impulse_percent": (
                remaining * 100.0 if remaining is not None else None
            ),
            "retracement_depth_ratio": (
                1.0 - remaining if remaining is not None else None
            ),
            "fibonacci_zone": (
                classify_remaining(remaining)
                if remaining is not None
                else "UNAVAILABLE"
            ),
            "as_of_time": float(decision_time),
            "as_of_m1_index": as_of_index,
            "causal_valid": bool(
                as_of_index >= 0
                and float(decision_time) >= float(context["armed_time"])
            ),
            "post_decision_fields": [],
        }
    )
    # Analytics are kept visible for reporting, but explicitly outside the
    # decision snapshot passed to M1 structure and quality.
    for field in (
        "retrospective_m5_outcome",
        "m5_entry_time",
        "m5_entry_index",
        "m5_entry_price",
        "m5_logical_stop",
        "m5_emergency_stop",
        "m5_logical_stop_contract",
        "m5_logical_stop_structure_index",
        "m5_failure_trigger_index",
        "m5_failure_trigger_price",
        "m5_failure_trigger_confirmed_at_index",
        "candidate",
    ):
        context.pop(field, None)
    return context


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


def _find_m1_child_entry_single(
    *,
    parent: Dict[str, Any],
    m1_data: pd.DataFrame,
    sensitivity: int = 2,
    max_trigger_age: int = 30,
    minimum_counter_bars: int = 3,
    quality_config: FidelityPatchConfig = DEFAULT_PATCH_CONFIG,
    decision_time: Optional[float] = None,
    trigger_available_filter: Optional[int] = None,
    permission_policy: str = COUNTER_CONFIRMED_ACTIVE,
) -> Dict[str, Any]:
    """
    Find the first causal M1 entry inside one active M5 parent window.

    The detector recognizes a trigger-side swing, a meaningful opposing swing,
    and a fresh trigger-side reaction before requiring the body-close BOS.
    """
    if permission_policy not in M1_PERMISSION_POLICIES:
        raise ValueError(f"Unsupported M1 permission policy: {permission_policy}")
    direction = str(parent["parent_direction"]).upper()
    times = m1_data["time"].map(_time)
    closes = times + 60.0
    outcome = retrospective_m5_outcome(parent)
    evaluation_time = (
        float(decision_time)
        if decision_time is not None
        else float(outcome["m5_entry_time"])
    )
    armed_global = int(closes.searchsorted(float(parent["armed_time"]), side="left"))
    active_time = parent.get("active_time")
    active_global = (
        int(closes.searchsorted(float(active_time), side="left"))
        if active_time is not None
        else len(m1_data)
    )
    end_global = int(
        closes.searchsorted(evaluation_time, side="right") - 1
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
        "decision_time": evaluation_time,
        "causal_valid": True,
        "closed_candles_only": True,
        "future_data_used": False,
        "research_only": True,
        "order_api_called": False,
    }
    if permission_policy == EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE:
        permission = evaluate_m1_permission(
            parent=parent,
            decision_time=evaluation_time,
            policy=permission_policy,
        )
        base.update(
            {
                "permission_policy": permission_policy,
                "permission": permission,
                "parent_state_at_decision": permission["parent_state"],
                "early_permission_state": "NOT_EARNED",
                "m1_was_monitored": bool(permission["observation_allowed"]),
            }
        )
        if not permission["observation_allowed"]:
            return {
                **base,
                "state": permission["parent_state"],
                "entry_ready": False,
                "entry": None,
                "rejections": [
                    {
                        "state": (
                            "M1_REJECTED_DOMINANT_PROTECTION_BROKEN"
                            if "DOMINANT_M5_PROTECTION_BROKEN" in permission["reasons"]
                            else "M1_REJECTED_PARENT_NOT_ELIGIBLE"
                        ),
                        "hard_blockers": permission["reasons"] or ["PARENT_NOT_ARMED"],
                    }
                ],
            }
        permission_start_global = armed_global
    else:
        permission_start_global = active_global

    if permission_start_global > end_global or end_global < 0:
        return {
            **base,
            "state": (
                "PARENT_ARMED_OBSERVING"
                if permission_policy == EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE
                and armed_global <= end_global
                else "CLOSED"
            ),
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
        and (
            trigger_available_filter is None
            or int(point["global_confirmed_at_index"])
            == int(trigger_available_filter)
        )
    ]
    for trigger in trigger_points:
        trigger_index = int(trigger["global_index"])
        trigger_available = int(trigger["global_confirmed_at_index"])
        if trigger_available < permission_start_global:
            rejections.append(
                {
                    "state": (
                        "M1_TRIGGER_SIDE_SWING_BEFORE_PARENT_ARMED"
                        if permission_policy
                        == EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE
                        else "M1_TRIGGER_SIDE_SWING_BEFORE_PARENT_ACTIVE"
                    ),
                    "m1_index": trigger_available,
                    "trigger_swing_index": trigger_index,
                    "trigger_available_at_index": trigger_available,
                    "event_semantics": "TRIGGER_SIDE_SWING_NOT_PROVEN_BOS",
                    "hard_blockers": [
                        "M5_PARENT_NOT_ARMED"
                        if permission_policy
                        == EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE
                        else "M5_PARENT_NOT_ACTIVE"
                    ],
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
        if entry_index < permission_start_global:
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
        entry_time = _close_time(m1_data, entry_index, 60)
        causal_parent = causal_parent_snapshot(
            parent=parent,
            m1_data=m1_data,
            decision_time=entry_time,
        )
        early_entry = bool(
            permission_policy == EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE
            and (active_time is None or entry_time < float(active_time))
        )
        if early_entry:
            # The eventual counter-confirmed ACTIVE clock is not an input to
            # early quality, stops, ownership, arbitration or commitment.
            for field in (
                "active_time",
                "counter_confirmed_at_index",
            ):
                causal_parent.pop(field, None)
            causal_parent["state"] = "PARENT_ARMED"
            causal_parent["parent_state_at_decision"] = "PARENT_ARMED"
        if not causal_parent.get("dominant_protection_intact"):
            rejections.append(
                {
                    "state": "M1_REJECTED_DOMINANT_PROTECTION_BROKEN",
                    "m1_index": entry_index,
                    "hard_blockers": ["DOMINANT_M5_PROTECTION_BROKEN"],
                }
            )
            continue
        location_buffer = max(local_atr * 0.25, 1e-12)
        in_parent_price = (
            _number(causal_parent["price_boundary_low"]) - location_buffer
            <= entry_price
            <= _number(causal_parent["price_boundary_high"]) + location_buffer
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
            parent={
                **causal_parent,
                "retrospective_m5_outcome": retrospective_m5_outcome(parent),
            },
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
            "entry_time": entry_time,
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
            "causal_parent_snapshot": causal_parent,
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
                and entry_time <= evaluation_time
                and causal_parent.get("causal_valid")
            ),
            "future_data_used": False,
            "closed_candles_only": True,
            "order_api_called": False,
        }
        if permission_policy == EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE:
            permission_at_entry = evaluate_m1_permission(
                parent=parent,
                decision_time=entry_time,
                policy=permission_policy,
            )
            if early_entry:
                permission_at_entry.update(
                    {
                        "state": "EARLY_M1_PERMISSION_EARNED",
                        "early_permission_earned": True,
                        "execution_permitted": True,
                        "reason": "COMPLETE_CAUSAL_M1_SEQUENCE_AND_BODY_CLOSE_BOS",
                    }
                )
            child.update(
                {
                    "permission_policy": permission_policy,
                    "permission_state": permission_at_entry["state"],
                    "early_permission_earned": early_entry,
                    "parent_state_at_entry": (
                        "PARENT_ARMED" if early_entry else "PARENT_ACTIVE"
                    ),
                    "permission": permission_at_entry,
                    "attempt_number": 1,
                    "first_entry_consumes_parent": True,
                }
            )
        return {
            **base,
            "state": (
                "EARLY_M1_PERMISSION_EARNED" if early_entry else "ENTRY_FOUND"
            ),
            "entry_ready": True,
            "entry": child,
            "rejections": rejections,
            **(
                {
                    "early_permission_state": "EARNED" if early_entry else "NOT_EARNED",
                    "permission": permission_at_entry,
                }
                if permission_policy == EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE
                else {}
            ),
        }
    return {
        **base,
        "state": (
            "PARENT_ARMED_OBSERVING"
            if permission_policy == EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE
            and evaluation_time < float(active_time or float("inf"))
            else "ACTIVE"
        ),
        "entry_ready": False,
        "entry": None,
        "rejections": rejections,
    }


def find_m1_child_entry(
    *,
    parent: Dict[str, Any],
    m1_data: pd.DataFrame,
    sensitivity: int = 2,
    max_trigger_age: int = 30,
    minimum_counter_bars: int = 3,
    quality_config: FidelityPatchConfig = DEFAULT_PATCH_CONFIG,
    decision_time: Optional[float] = None,
    trigger_available_filter: Optional[int] = None,
    permission_policy: str = COUNTER_CONFIRMED_ACTIVE,
) -> Dict[str, Any]:
    """Resolve an earned pre-ACTIVE entry without changing ACTIVE-era baseline."""
    arguments = {
        "parent": parent,
        "m1_data": m1_data,
        "sensitivity": sensitivity,
        "max_trigger_age": max_trigger_age,
        "minimum_counter_bars": minimum_counter_bars,
        "quality_config": quality_config,
        "decision_time": decision_time,
        "permission_policy": permission_policy,
    }
    if (
        permission_policy != EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE
        or trigger_available_filter is not None
        or m1_data.empty
    ):
        return _find_m1_child_entry_single(
            **arguments,
            trigger_available_filter=trigger_available_filter,
        )

    # S2B owns only the interval [ARMED, ACTIVE).  Once ACTIVE is reached the
    # accepted S2A.1 resolver remains authoritative, byte-for-byte in result.
    # This baseline result is therefore the required fallback for every case
    # where no complete M1 sequence earned permission before ACTIVE.
    baseline_arguments = dict(arguments)
    baseline_arguments["permission_policy"] = COUNTER_CONFIRMED_ACTIVE
    baseline_report = _find_m1_child_entry_single(
        **baseline_arguments,
        trigger_available_filter=None,
    )
    active_time = float(parent["active_time"])

    times = m1_data["time"].map(_time)
    closes = times + 60.0
    outcome = retrospective_m5_outcome(parent)
    evaluation_time = (
        float(decision_time)
        if decision_time is not None
        else float(outcome["m5_entry_time"])
    )
    armed_global = int(closes.searchsorted(float(parent["armed_time"]), side="left"))
    end_global = int(closes.searchsorted(evaluation_time, side="right") - 1)
    if end_global < armed_global or end_global < 0:
        return _find_m1_child_entry_single(
            **arguments,
            trigger_available_filter=None,
        )
    window_start = max(0, armed_global - sensitivity)
    window_end = min(len(m1_data) - 1, end_global)
    window = m1_data.iloc[window_start : window_end + 1].reset_index(drop=True)
    direction = str(parent["parent_direction"]).upper()
    trigger_side = "HIGH" if direction == "BULLISH" else "LOW"
    filters = sorted(
        {
            window_start + int(point["confirmed_at_index"])
            for point in confirmed_swings(
                window,
                as_of_index=len(window) - 1,
                sensitivity=sensitivity,
            )
            if point["side"] == trigger_side
            and window_start + int(point["confirmed_at_index"]) <= end_global
        }
    )
    valid: list[Dict[str, Any]] = []
    for available_index in filters:
        report = _find_m1_child_entry_single(
            **arguments,
            trigger_available_filter=available_index,
        )
        if (
            report.get("entry_ready")
            and report.get("entry")
            and float(report["entry"]["entry_time"]) < active_time
        ):
            valid.append(report)
    if not valid:
        if evaluation_time < active_time:
            # During the research observation window retain the variant's
            # exact rejection evidence for diagnostics.  It has no entry
            # authority and cannot mutate the Director.
            return _find_m1_child_entry_single(
                **arguments,
                trigger_available_filter=None,
            )
        return baseline_report
    selected = min(
        valid,
        key=lambda report: (
            float(report["entry"]["entry_time"]),
            -int(report["entry"]["failure_trigger_available_at_index"]),
        ),
    )
    selected = deepcopy(selected)
    selected["first_valid_arbitration"] = {
        "owner": "M1PermissionPolicyEngine",
        "method": "EARLIEST_VALID_PREACTIVE_BOS_CLOSE_ACROSS_CAUSALLY_AVAILABLE_TRIGGERS",
        "active_time_exclusive": active_time,
        "evaluated_trigger_count": len(filters),
        "valid_trigger_count": len(valid),
        "selected_entry_time": selected["entry"]["entry_time"],
        "causal_valid": True,
    }
    return selected


def _shadow_terminal_state(report: Dict[str, Any]) -> str:
    if report.get("entry_ready") and report.get("entry"):
        return "SHADOW_VALID_EARLY_M1"
    states = [str(row.get("state") or "") for row in report.get("rejections", [])]
    precedence = (
        ("DOMINANT_PROTECTION_BROKEN", "SHADOW_PROTECTION_BROKEN"),
        ("LOW_VALUE_OBSERVE_ONLY", "SHADOW_LOW_CAUSAL_QUALITY"),
        ("OUTSIDE_PARENT_PRICE", "SHADOW_OUTSIDE_PARENT"),
        ("STALE_TRIGGER", "SHADOW_STALE"),
        ("MICRO_NOISE", "SHADOW_MICRO_NOISE"),
        ("ONE_CANDLE_NOISE", "SHADOW_MICRO_NOISE"),
        ("INCOMPLETE_SEQUENCE", "SHADOW_INCOMPLETE_SEQUENCE"),
        ("NO_COUNTER_STRUCTURE", "SHADOW_NO_COUNTER_STRUCTURE"),
        ("WRONG_BODY_DIRECTION", "SHADOW_WRONG_BODY_DIRECTION"),
        ("LOGICAL_STOP_WRONG_SIDE", "SHADOW_LOGICAL_STOP_WRONG_SIDE"),
        ("WICK_ONLY", "SHADOW_WICK_ONLY"),
    )
    for token, terminal in precedence:
        if any(token in state for state in states):
            return terminal
    return "SHADOW_NO_BODY_CLOSE_BOS"


def evaluate_armed_to_active_shadow(
    *,
    parent: Dict[str, Any],
    m1_data: pd.DataFrame,
    sensitivity: int = 2,
    max_trigger_age: int = 30,
    minimum_counter_bars: int = 3,
    quality_config: FidelityPatchConfig = DEFAULT_PATCH_CONFIG,
) -> Dict[str, Any]:
    """Evaluate every pre-active trigger-side swing without changing canon."""
    parent_before = deepcopy(parent)
    times = m1_data["time"].map(_time)
    closes = times + 60.0
    armed_global = int(closes.searchsorted(float(parent["armed_time"]), side="left"))
    active_global = int(closes.searchsorted(float(parent["active_time"]), side="left"))
    end_global = min(len(m1_data) - 1, active_global - 1)
    base = {
        "owner": "S2A1EarlyM1ShadowEvaluator",
        "state": "SHADOW_AUDIT_COMPLETE",
        "parent_m5_setup_id": parent.get("parent_m5_setup_id"),
        "armed_time": float(parent["armed_time"]),
        "active_time": float(parent["active_time"]),
        "canonical_behavior_changed": False,
        "research_only": True,
        "order_api_called": False,
        "events": [],
    }
    if end_global < armed_global:
        return {**base, "state": "SHADOW_NO_ARMED_TO_ACTIVE_INTERVAL"}
    window_start = max(0, armed_global - sensitivity)
    window = m1_data.iloc[window_start : end_global + 1].reset_index(drop=True)
    swings = confirmed_swings(
        window,
        as_of_index=len(window) - 1,
        sensitivity=sensitivity,
    )
    direction = str(parent["parent_direction"]).upper()
    trigger_side = "HIGH" if direction == "BULLISH" else "LOW"
    trigger_points: list[Dict[str, Any]] = []
    for point in swings:
        global_index = window_start + int(point["index"])
        available_index = window_start + int(point["confirmed_at_index"])
        if (
            point["side"] == trigger_side
            and armed_global <= available_index < active_global
        ):
            trigger_points.append(
                {
                    **point,
                    "global_index": global_index,
                    "global_confirmed_at_index": available_index,
                }
            )
    events: list[Dict[str, Any]] = []
    for trigger in trigger_points:
        report = find_m1_child_entry(
            parent=parent,
            m1_data=m1_data.iloc[: end_global + 1].copy(),
            sensitivity=sensitivity,
            max_trigger_age=max_trigger_age,
            minimum_counter_bars=minimum_counter_bars,
            quality_config=quality_config,
            decision_time=float(parent["active_time"]) - 1e-6,
            trigger_available_filter=int(trigger["global_confirmed_at_index"]),
            permission_policy=EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE,
        )
        entry = dict(report.get("entry") or {})
        terminal = _shadow_terminal_state(report)
        events.append(
            {
                "owner": "S2A1EarlyM1ShadowEvaluator",
                "state": terminal,
                "event_semantics": "PREACTIVE_TRIGGER_SIDE_SWING_FULL_SHADOW_EVALUATION",
                "parent_m5_setup_id": parent.get("parent_m5_setup_id"),
                "direction": direction,
                "trigger_swing_index": int(trigger["global_index"]),
                "trigger_swing_time": _time(
                    m1_data.iloc[int(trigger["global_index"])]["time"]
                ),
                "trigger_available_at_index": int(
                    trigger["global_confirmed_at_index"]
                ),
                "trigger_available_time": _close_time(
                    m1_data,
                    int(trigger["global_confirmed_at_index"]),
                    60,
                ),
                "entry_ready": bool(report.get("entry_ready")),
                "entry": entry or None,
                "entry_time": entry.get("entry_time"),
                "entry_price": entry.get("entry_price"),
                "logical_stop": entry.get("logical_stop"),
                "quality": entry.get("quality"),
                "rejections": deepcopy(report.get("rejections") or []),
                "causal_valid": bool(
                    not entry
                    or float(entry.get("entry_time")) < float(parent["active_time"])
                ),
                "canonical_eligible": False,
                "shadow_only": True,
                "order_api_called": False,
            }
        )
    result = {
        **base,
        "events": events,
        "event_count": len(events),
        "valid_event_count": sum(
            row["state"] == "SHADOW_VALID_EARLY_M1" for row in events
        ),
        "parent_unchanged": parent == parent_before,
    }
    result["canonical_behavior_changed"] = not result["parent_unchanged"]
    return result


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
    decision_time: Optional[float] = None,
) -> Dict[str, Any]:
    """Commit only facts available by T; compare later M5 outcome post hoc."""
    m1_entry = m1_result.get("entry") if m1_result.get("entry_ready") else None
    outcome = retrospective_m5_outcome(parent)
    outcome_available = bool(
        outcome.get("availability") == "AVAILABLE"
        and outcome.get("m5_entry_time") is not None
    )
    m5_time = float(outcome["m5_entry_time"]) if outcome_available else None
    evaluation_time = (
        float(decision_time)
        if decision_time is not None
        else float(m1_result.get("decision_time"))
        if m1_result.get("decision_time") is not None
        else float(m5_time)
        if m5_time is not None
        else float("-inf")
    )
    if m1_entry is not None and float(m1_entry["entry_time"]) <= evaluation_time:
        owner = "M1"
        chosen = dict(m1_entry)
        advantage = build_post_hoc_m1_advantage(
            parent=parent,
            m1_entry=m1_entry,
        )
    elif outcome_available and m5_time is not None and m5_time <= evaluation_time:
        owner = "M5"
        m5_price = _number(outcome["m5_entry_price"])
        m5_stop = _number(outcome["m5_logical_stop"])
        chosen = {
            **ownership_payload(parent),
            "state": "M5_FALLBACK_ENTRY",
            "entry_ready": True,
            "entry_timeframe": "M5",
            "entry_reason": "NO_VALID_EARLIER_M1_ENTRY",
            "entry_index": int(outcome["m5_entry_index"]),
            "entry_time": m5_time,
            "entry_price": m5_price,
            "logical_stop": m5_stop,
            "emergency_stop": outcome.get("m5_emergency_stop"),
            "stop_distance_m5": abs(m5_price - m5_stop),
            "causal_valid": True,
            "future_data_used": False,
            "order_api_called": False,
        }
        advantage = None
    else:
        owner = "NONE"
        chosen = {
            **ownership_payload(parent),
            "state": "WAITING_FOR_FIRST_VALID_ENTRY",
            "entry_ready": False,
            "causal_valid": True,
            "as_of_time": evaluation_time,
            "future_data_used": False,
            "order_api_called": False,
        }
        advantage = None
    return {
        "owner": "FirstValidEntryArbiter",
        "state": (
            "CONSUMED_BY_M1"
            if owner == "M1"
            else "CONSUMED_BY_M5"
            if owner == "M5"
            else "MONITORING_FIRST_VALID_ENTRY"
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
        "m1_gate_closed": owner in {"M1", "M5"},
        "advantage": advantage,
        "decision_time": evaluation_time,
        "causal_valid": bool(chosen.get("causal_valid", True)),
        "future_data_used": False,
        "order_api_called": False,
    }


def build_post_hoc_m1_advantage(
    *,
    parent: Dict[str, Any],
    m1_entry: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Analytics-only comparison that has no authority over entry selection."""
    outcome = retrospective_m5_outcome(parent)
    if outcome.get("availability") != "AVAILABLE":
        return None
    m5_time = float(outcome["m5_entry_time"])
    m5_price = _number(outcome["m5_entry_price"])
    m5_stop = _number(outcome["m5_logical_stop"])
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
    objective = _number(parent["fib_hundred_price"])
    if not (
        (
            parent["parent_direction"] == "BULLISH"
            and objective > _number(m1_entry["entry_price"])
        )
        or (
            parent["parent_direction"] == "BEARISH"
            and objective < _number(m1_entry["entry_price"])
        )
    ):
        objective = m5_price
    m1_rr = abs(objective - _number(m1_entry["entry_price"])) / m1_risk
    m5_rr = abs(objective - m5_price) / m5_risk
    return {
        "analytics_only": True,
        "influences_arbitration": False,
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
