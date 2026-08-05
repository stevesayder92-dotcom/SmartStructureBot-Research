from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional

import pandas as pd

from core.fibonacci_contract import reassess_same_cycle


STEVE_MANAGEMENT_MODEL = "STEVE_STOP_MANAGEMENT_V3"
MANAGEMENT_PROFILES = {
    "STRUCTURE_RUNNER_ONLY",
    "TWIN_POSITION_50_50",
    "PARTIAL_PLUS_RUNNER",
}
TP1_MODELS = {
    "PREVIOUS_HTF_EXTREME",
    "PREVIOUS_IMPULSE_EXTREME",
    "CONFIGURABLE_R",
    "NEAREST_MEANINGFUL_LIQUIDITY",
}


def _number(value: Any) -> float:
    return float(value)


def atr_at(
    data: pd.DataFrame,
    *,
    as_of_index: int,
    period: int = 14,
) -> float:
    """Causal simple ATR using only candles available at ``as_of_index``."""
    current = int(as_of_index)
    if current < 0 or current >= len(data):
        raise IndexError("ATR as_of_index is outside the data range")
    if period <= 0:
        raise ValueError("ATR period must be greater than zero")
    # Only the final ``period`` true ranges and one preceding close are
    # required. Keeping the causal window bounded is important during
    # synchronized M1 replay, where ATR is queried many times.
    start = max(0, current - period)
    visible = data.iloc[start : current + 1]
    high = visible["high"].astype(float)
    low = visible["low"].astype(float)
    close = visible["close"].astype(float)
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return float(true_range.iloc[-period:].mean())


@dataclass(frozen=True)
class SteveManagementConfig:
    """
    Research parameters, deliberately configurable and not outcome-optimized.

    M5 uses a modest buffer beyond the relevant structure body boundary and
    requires a meaningful body close. M1 uses the relevant lower/upper body
    edge exactly. Wicks remain evidence, not logical invalidation.
    """

    m5_atr_tolerance: float = 0.15
    m5_min_body_atr: float = 0.35
    m5_min_close_distance_atr: float = 0.10
    emergency_atr_buffer: float = 1.00
    trail_atr_tolerance: float = 0.10
    trail_min_body_atr: float = 0.25
    management_profile: str = "TWIN_POSITION_50_50"
    tp1_model: str = "PREVIOUS_IMPULSE_EXTREME"
    configurable_r_target: float = 1.0

    def __post_init__(self) -> None:
        if self.m5_atr_tolerance < 0:
            raise ValueError("m5_atr_tolerance cannot be negative")
        if self.emergency_atr_buffer <= 0:
            raise ValueError("emergency_atr_buffer must be positive")
        if self.trail_min_body_atr < 0:
            raise ValueError("trail_min_body_atr cannot be negative")
        if self.management_profile not in MANAGEMENT_PROFILES:
            raise ValueError("Unknown management profile")
        if self.tp1_model not in TP1_MODELS:
            raise ValueError("Unknown TP1 model")


def _timeframe_name(timeframe: Any) -> str:
    return str(timeframe).upper().replace("TIMEFRAME_", "")


def select_last_important_pre_bos_swing(
    *,
    swings: Iterable[Dict[str, Any]],
    direction: str,
    trigger_index: int,
    entry_index: int,
    data: Optional[pd.DataFrame] = None,
    setup_start_index: Optional[int] = None,
    fallback: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Select the latest causal setup-invalidating swing before the entry BOS.

    The preferred structure is the final opposing reaction between the failure
    trigger and entry. The entry BOS itself proves that reaction extreme at the
    entry close, so this remains causal even when the fixed N-right fractal
    delay has not completed. If no opposing reaction exists, the latest
    fixed-delay confirmed LOW/HIGH inside the same qualified retracement is
    used. Nothing after entry is consulted.
    """
    normalized = str(direction).upper()
    if normalized not in {"BULLISH", "BEARISH"}:
        raise ValueError("Direction must be BULLISH or BEARISH")
    expected_side = "LOW" if normalized == "BULLISH" else "HIGH"
    lower_bound = (
        int(setup_start_index)
        if setup_start_index is not None
        else -1
    )
    reaction_start = int(trigger_index) + 1
    reaction_end = int(entry_index)
    if (
        data is not None
        and 0 <= reaction_start < reaction_end <= len(data)
    ):
        reaction = data.iloc[reaction_start:reaction_end]
        if normalized == "BULLISH":
            opposing = (
                reaction["close"].astype(float)
                < reaction["open"].astype(float)
            )
            price_field = "low"
            relative_index = reaction_start + int(
                reaction[price_field].astype(float).to_numpy().argmin()
            )
        else:
            opposing = (
                reaction["close"].astype(float)
                > reaction["open"].astype(float)
            )
            price_field = "high"
            relative_index = reaction_start + int(
                reaction[price_field].astype(float).to_numpy().argmax()
            )
        if bool(opposing.any()):
            structure_index = int(relative_index)
            return {
                "side": expected_side,
                "index": structure_index,
                "level": _number(
                    data.iloc[structure_index][price_field]
                ),
                "confirmed_at_index": int(entry_index),
                "available_at_index": int(entry_index),
                "classification": (
                    "PRE_BOS_REACTION_LOW"
                    if normalized == "BULLISH"
                    else "PRE_BOS_REACTION_HIGH"
                ),
                "selection_scope": (
                    "ENTRY_BOS_PROVED_LAST_IMPORTANT_REACTION_SWING"
                ),
                "confirmation_method": (
                    "CAUSAL_ENTRY_BOS_PROOF_NO_FUTURE_CANDLES"
                ),
                "available_at_entry": True,
            }
    eligible = [
        dict(point)
        for point in swings
        if str(point.get("side")).upper() == expected_side
        and point.get("index") is not None
        and lower_bound <= int(point["index"]) < int(entry_index)
        and int(
            point.get("confirmed_at_index", point["index"])
        ) <= int(entry_index)
    ]
    after_trigger = [
        point
        for point in eligible
        if int(point["index"]) > int(trigger_index)
    ]
    candidates = after_trigger or eligible
    if candidates:
        selected = max(
            candidates,
            key=lambda point: (
                int(point["index"]),
                int(
                    point.get(
                        "confirmed_at_index",
                        point["index"],
                    )
                ),
            ),
        )
        selected["selection_scope"] = (
            "LATEST_CONFIRMED_AFTER_FAILURE_TRIGGER"
            if after_trigger
            else "LATEST_CONFIRMED_INSIDE_QUALIFIED_RETRACEMENT"
        )
        selected["available_at_entry"] = True
        return selected
    fallback_point = dict(fallback or {})
    if (
        str(fallback_point.get("side")).upper() == expected_side
        and fallback_point.get("index") is not None
        and lower_bound <= int(fallback_point["index"]) < int(entry_index)
        and int(
            fallback_point.get(
                "confirmed_at_index",
                fallback_point["index"],
            )
        ) <= int(entry_index)
    ):
        fallback_point["selection_scope"] = (
            "QUALIFIED_COUNTER_FALLBACK"
        )
        fallback_point["available_at_entry"] = True
        return fallback_point
    raise ValueError(
        "No causal last-important pre-BOS invalidation swing is available"
    )


def select_setup_logical_invalidation(
    *,
    data: pd.DataFrame,
    entry_model: Dict[str, Any],
    timeframe: Any,
    config: SteveManagementConfig,
) -> Dict[str, Any]:
    """
    Select the last important pre-BOS structure published by the entry model.

    For a BUY this is the latest causal LOW/LL inside the qualified
    retracement before the bullish entry BOS. For a SELL it is the latest
    causal HIGH/HH before the bearish entry BOS. The original counter-swing is
    retained only as a compatibility fallback.
    """
    direction = str(entry_model.get("direction")).upper()
    if direction not in {"BULLISH", "BEARISH"}:
        raise ValueError("Entry direction must be BULLISH or BEARISH")
    entry_index = int(entry_model["entry_index"])
    counter = dict(entry_model.get("counter") or {})
    structure = dict(
        entry_model.get("logical_stop_structure") or counter
    )
    trigger = dict(entry_model.get("trigger") or {})
    if structure.get("index") is None or trigger.get("index") is None:
        raise ValueError(
            "Qualified entry must publish its logical structure and trigger"
        )
    structure_index = int(structure["index"])
    trigger_index = int(trigger["index"])
    available_at = int(
        structure.get("confirmed_at_index", structure_index)
    )
    trigger_available_at = int(
        trigger.get("confirmed_at_index", trigger_index)
    )
    expected_side = "LOW" if direction == "BULLISH" else "HIGH"
    if str(structure.get("side")).upper() != expected_side:
        raise ValueError("Logical stop structure is on the wrong side")
    if not (
        structure_index < entry_index
        and trigger_index < entry_index
        and available_at <= entry_index
        and trigger_available_at <= entry_index
    ):
        raise ValueError(
            "Invalidation must be confirmed before the trigger/entry"
        )

    row = data.iloc[structure_index]
    wick_price = (
        _number(row["low"])
        if direction == "BULLISH"
        else _number(row["high"])
    )
    body_lower_edge = min(_number(row["open"]), _number(row["close"]))
    body_upper_edge = max(_number(row["open"]), _number(row["close"]))
    body_close_level = (
        body_lower_edge if direction == "BULLISH" else body_upper_edge
    )
    atr_value = atr_at(data, as_of_index=entry_index)
    is_m1 = _timeframe_name(timeframe) == "M1"
    tolerance = 0.0 if is_m1 else float(config.m5_atr_tolerance)
    logical_boundary = (
        body_close_level
        if is_m1
        else body_close_level - tolerance * atr_value
        if direction == "BULLISH"
        else body_close_level + tolerance * atr_value
    )
    entry_price = _number(entry_model["entry_price"])
    correct_side = (
        logical_boundary < entry_price
        if direction == "BULLISH"
        else logical_boundary > entry_price
    )
    broad_extreme = entry_model.get("stop_level")
    broad_rejected = (
        broad_extreme is not None
        and abs(_number(broad_extreme) - body_close_level) > 1e-12
    )
    reasons = [
        "Selected the last important pre-BOS LOW/LL for a buy or HIGH/HH "
        "for a sell inside the same qualified retracement",
        "The structure and its fixed-delay confirmation were available no "
        "later than the entry candle close",
    ]
    if structure_index > trigger_index:
        reasons.append(
            "The selected swing formed after the failure trigger and was the "
            "final opposing structure supporting the entry BOS"
        )
    else:
        reasons.append(
            "No later confirmed protective swing existed, so the latest "
            "same-retracement structure was retained"
        )
    if is_m1:
        reasons.append(
            "M1 logical invalidation uses M1_RELEVANT_SWING_BODY_EDGE; "
            "a wick alone cannot invalidate"
        )
    else:
        reasons.append(
            "M5 logical boundary is beyond the relevant body edge by the "
            "configured causal ATR tolerance"
        )
    if broad_rejected:
        reasons.append(
            "The broad pullback extreme was retained for comparison but "
            "rejected as the logical stop because it was not the directly "
            "relevant defended pre-BOS structure"
        )
    return {
        "invalidation_role": "SETUP_LOGICAL_INVALIDATION",
        "availability": "AVAILABLE",
        "available": True,
        "state": "LOGICAL_STRUCTURE_SELECTED",
        "owner": "ProtectedStructureEngine",
        "setup_id": entry_model.get("setup_id"),
        "direction": direction,
        "timeframe": _timeframe_name(timeframe),
        "structure_index": structure_index,
        "structure_type": (
            str(structure.get("classification"))
            if structure.get("classification")
            else expected_side
        ),
        "selection_scope": structure.get(
            "selection_scope",
            "ENTRY_MODEL_PUBLISHED_LOGICAL_STRUCTURE",
        ),
        "wick_price": wick_price,
        "body_close_level": body_close_level,
        "body_lower_edge": body_lower_edge,
        "body_upper_edge": body_upper_edge,
        "atr_at_entry": atr_value,
        "atr_tolerance": tolerance,
        "logical_boundary": logical_boundary,
        "logical_stop": logical_boundary,
        "broad_pullback_extreme": (
            _number(broad_extreme)
            if broad_extreme is not None
            else None
        ),
        "broad_pullback_extreme_rejected": broad_rejected,
        "failure_trigger_index": trigger_index,
        "failure_trigger_level": _number(trigger["level"]),
        "selection_reason": reasons,
        "reasons": reasons,
        "available_at_index": available_at,
        "as_of_index": entry_index,
        "causal_valid": bool(correct_side),
        "correct_side_of_entry": bool(correct_side),
        "post_entry_candles_used": False,
    }


def emergency_broker_stop(
    *,
    logical_invalidation: Dict[str, Any],
    config: SteveManagementConfig,
) -> Dict[str, Any]:
    direction = str(logical_invalidation["direction"])
    logical = _number(logical_invalidation["logical_boundary"])
    atr_value = _number(logical_invalidation["atr_at_entry"])
    buffer_value = float(config.emergency_atr_buffer) * atr_value
    hard_stop = (
        logical - buffer_value
        if direction == "BULLISH"
        else logical + buffer_value
    )
    return {
        "protection_role": "EMERGENCY_BROKER_STOP",
        "availability": "AVAILABLE",
        "available": True,
        "state": "RESEARCH_CALCULATED_NOT_SENT",
        "owner": "TradeGuardian",
        "direction": direction,
        "price": hard_stop,
        "logical_stop": logical,
        "atr_buffer": float(config.emergency_atr_buffer),
        "atr_at_entry": atr_value,
        "as_of_index": logical_invalidation["as_of_index"],
        "available_at_index": logical_invalidation["available_at_index"],
        "causal_valid": True,
        "research_only": True,
        "order_api_called": False,
        "emergency_exit_condition": (
            "BROKER_HARD_STOP_ONLY_FOR_CATASTROPHIC_OR_SOFTWARE_RISK"
        ),
        "reasons": [
            "This is wider than the strategy logical stop and is not the "
            "normal strategy loss level"
        ],
    }


def dominant_decision_protection(
    *,
    context: Optional[Dict[str, Any]],
    direction: str,
    as_of_index: int,
) -> Dict[str, Any]:
    normalized = str(direction).upper()
    field = (
        "last_confirmed_low"
        if normalized == "BULLISH"
        else "last_confirmed_high"
    )
    points: list[Dict[str, Any]] = []
    for timeframe in ("M30", "M15", "H1"):
        point = (
            ((context or {}).get("frames", {}) or {})
            .get(timeframe, {})
            .get(field)
            or {}
        )
        if point.get("level") is None:
            continue
        available_at = point.get(
            "available_at_index",
            point.get("confirmed_at_index", point.get("index")),
        )
        points.append(
            {
                "timeframe": timeframe,
                "index": point.get("index"),
                "level": _number(point["level"]),
                "available_at_index": available_at,
                "classification": point.get("classification"),
            }
        )
    if points:
        selected = (
            max(points, key=lambda item: item["level"])
            if normalized == "BULLISH"
            else min(points, key=lambda item: item["level"])
        )
    else:
        selected = {}
    return {
        "protection_role": "DOMINANT_DECISION_PROTECTION",
        "availability": "AVAILABLE" if selected else "UNAVAILABLE",
        "available": bool(selected),
        "state": (
            "DOMINANT_STRUCTURE_INTACT"
            if selected
            else "DOMINANT_STRUCTURE_NOT_PUBLISHED"
        ),
        "owner": "ProtectedStructureEngine",
        "direction": normalized,
        "type": (
            "DOMINANT_HL"
            if normalized == "BULLISH"
            else "DOMINANT_LH"
        ),
        "index": selected.get("index"),
        "level": selected.get("level"),
        "timeframe": selected.get("timeframe"),
        "sources": points,
        "as_of_index": int(as_of_index),
        "available_at_index": selected.get("available_at_index"),
        "causal_valid": True,
        "intact": True if selected else None,
        "reasons": [
            "Dominant protection is independent of setup invalidation, "
            "emergency protection and post-entry trailing"
        ],
    }


def logical_invalidation_decision(
    *,
    row: pd.Series,
    direction: str,
    timeframe: Any,
    contract: Dict[str, Any],
    config: SteveManagementConfig,
) -> Dict[str, Any]:
    """Evaluate a closed candle; wick-only crossings never invalidate."""
    normalized = str(direction).upper()
    close = _number(row["close"])
    open_price = _number(row["open"])
    high = _number(row["high"])
    low = _number(row["low"])
    atr_value = _number(contract["atr_at_entry"])
    boundary = _number(contract["logical_boundary"])
    body_atr = (
        abs(close - open_price) / atr_value
        if atr_value > 0
        else 0.0
    )
    distance = (
        boundary - close
        if normalized == "BULLISH"
        else close - boundary
    )
    distance_atr = distance / atr_value if atr_value > 0 else 0.0
    close_beyond = distance > 0
    correct_invalidating_direction = (
        close < open_price
        if normalized == "BULLISH"
        else close > open_price
    )
    wick_beyond = (
        low < boundary <= close
        if normalized == "BULLISH"
        else high > boundary >= close
    )
    is_m1 = _timeframe_name(timeframe) == "M1"
    invalidated = bool(
        close_beyond and correct_invalidating_direction
        if is_m1
        else close_beyond
        and correct_invalidating_direction
        and (
            body_atr >= float(config.m5_min_body_atr)
            or distance_atr
            >= float(config.m5_min_close_distance_atr)
        )
    )
    return {
        "invalidated": invalidated,
        "wick_only_survived": bool(wick_beyond and not invalidated),
        "close_beyond_boundary": bool(close_beyond),
        "correct_invalidating_direction": bool(
            correct_invalidating_direction
        ),
        "close": close,
        "boundary": boundary,
        "body_strength_atr": body_atr,
        "close_distance_beyond_atr": max(0.0, distance_atr),
        "rule": (
            "M1_BODY_CLOSE_BEYOND_RELEVANT_SWING_BODY_EDGE"
            if is_m1
            else "M5_MOMENTUM_BODY_CLOSE_BEYOND_TOLERANT_BOUNDARY"
        ),
    }


def transition_protection_without_loosening(
    *,
    direction: str,
    current_level: float,
    candidate_m5_level: float,
) -> Dict[str, Any]:
    normalized = str(direction).upper()
    favourable = (
        candidate_m5_level >= current_level
        if normalized == "BULLISH"
        else candidate_m5_level <= current_level
    )
    return {
        "state": (
            "M1_TO_M5_PROTECTION_TRANSITIONED"
            if favourable
            else "M1_TO_M5_TRANSITION_REJECTED_WOULD_LOOSEN"
        ),
        "previous_level": float(current_level),
        "candidate_m5_level": float(candidate_m5_level),
        "selected_level": (
            float(candidate_m5_level)
            if favourable
            else float(current_level)
        ),
        "loosened": False,
        "causal_valid": True,
    }


def _sizing_plan(profile: str, attempt_number: int) -> Dict[str, Any]:
    if profile == "STRUCTURE_RUNNER_ONLY":
        fractions = [1.0]
    elif profile == "TWIN_POSITION_50_50":
        fractions = [0.5, 0.5]
    else:
        fractions = [0.5, 0.5]
    return {
        "management_profile": profile,
        "attempt_number": int(attempt_number),
        "position_count": len(fractions),
        "risk_fractions": fractions,
        "sizing_logic_id": f"{profile}_V1",
        "sizing_logic_cloned": attempt_number == 2,
        "broker_volume_computed": False,
    }


def select_tp1_target(
    *,
    context: Optional[Dict[str, Any]],
    entry_model: Dict[str, Any],
    logical_stop: float,
    config: SteveManagementConfig,
) -> Dict[str, Any]:
    direction = str(entry_model["direction"]).upper()
    entry_price = _number(entry_model["entry_price"])
    model = config.tp1_model
    candidates: list[tuple[float, str]] = []
    if model in {
        "PREVIOUS_HTF_EXTREME",
        "NEAREST_MEANINGFUL_LIQUIDITY",
    }:
        side = "HIGH" if direction == "BULLISH" else "LOW"
        for timeframe in ("H1", "M30", "M15"):
            frame = (
                ((context or {}).get("frames", {}) or {})
                .get(timeframe, {})
            )
            for point in frame.get("swings", []) or []:
                if str(point.get("side")).upper() != side:
                    continue
                level = point.get("level")
                if level is None:
                    continue
                value = _number(level)
                favourable = (
                    value > entry_price
                    if direction == "BULLISH"
                    else value < entry_price
                )
                if favourable:
                    candidates.append((value, timeframe))
    elif model == "PREVIOUS_IMPULSE_EXTREME":
        anchor = entry_model.get("anchor") or {}
        if anchor.get("level") is not None:
            value = _number(anchor["level"])
            favourable = (
                value > entry_price
                if direction == "BULLISH"
                else value < entry_price
            )
            if favourable:
                candidates.append((value, "ENTRY_IMPULSE"))
    elif model == "CONFIGURABLE_R":
        risk = abs(entry_price - float(logical_stop))
        value = (
            entry_price + config.configurable_r_target * risk
            if direction == "BULLISH"
            else entry_price - config.configurable_r_target * risk
        )
        candidates.append((value, f"{config.configurable_r_target:.2f}R"))
    selected = None
    source = None
    if candidates:
        selected, source = min(
            candidates,
            key=lambda item: abs(item[0] - entry_price),
        )
    return {
        "model": model,
        "price": selected,
        "source": source,
        "available": selected is not None,
        "research_only": True,
        "redefines_structural_stop": False,
    }


@dataclass
class SteveTradeManagementEngine:
    """Persistent causal research manager; it never imports or calls MT5."""

    config: SteveManagementConfig = field(
        default_factory=SteveManagementConfig
    )
    markets: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @staticmethod
    def _key(symbol: str, timeframe: Any) -> str:
        return f"{symbol}|{_timeframe_name(timeframe)}"

    def _new_state(self, direction: str) -> Dict[str, Any]:
        return {
            "direction": direction,
            "parent_setup_id": None,
            "attempts": [],
            "active_attempt": None,
            "reentry_count": 0,
            "reentry_state": "NOT_ELIGIBLE_BEFORE_FIRST_FAILURE",
            "fresh_counter": None,
            "fresh_trigger": None,
            "parent_retracement_active": False,
            "reentry_monitoring": False,
            "last_processed_index": -1,
            "terminal": False,
            "history": [],
        }

    def _open_attempt(
        self,
        *,
        state: Dict[str, Any],
        data: pd.DataFrame,
        timeframe: Any,
        entry_model: Dict[str, Any],
        attempt_number: int,
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        invalidation = select_setup_logical_invalidation(
            data=data,
            entry_model=entry_model,
            timeframe=timeframe,
            config=self.config,
        )
        emergency = emergency_broker_stop(
            logical_invalidation=invalidation,
            config=self.config,
        )
        dominant = dominant_decision_protection(
            context=context,
            direction=entry_model["direction"],
            as_of_index=int(entry_model["entry_index"]),
        )
        tp1 = select_tp1_target(
            context=context,
            entry_model=entry_model,
            logical_stop=invalidation["logical_boundary"],
            config=self.config,
        )
        attempt = {
            "attempt_number": attempt_number,
            "event_id": (
                f"{entry_model.get('setup_id')}|"
                f"{'ENTRY' if attempt_number == 1 else 'REENTRY'}_"
                f"{entry_model['entry_index']}"
            ),
            "setup_id": entry_model.get("setup_id"),
            "direction": entry_model["direction"],
            "timeframe": _timeframe_name(timeframe),
            "entry_index": int(entry_model["entry_index"]),
            "entry_price": _number(entry_model["entry_price"]),
            "status": "ACTIVE",
            "logical_invalidation": invalidation,
            "dominant_decision_protection": dominant,
            "emergency_broker_stop_contract": emergency,
            "logical_stop": invalidation["logical_boundary"],
            "emergency_broker_stop": emergency["price"],
            "current_protection": invalidation["logical_boundary"],
            "current_protection_source": "SETUP_LOGICAL_INVALIDATION",
            "trail_state": "NO_TRAIL_AVAILABLE",
            "trail_candidates": [],
            "proven_trails": [],
            "trail_movements": [],
            "opposing_bos": None,
            "exit_index": None,
            "exit_price": None,
            "exit_reason": None,
            "sizing": _sizing_plan(
                self.config.management_profile,
                attempt_number,
            ),
            "management_profile": self.config.management_profile,
            "tp1_model": self.config.tp1_model,
            "position_1_target": tp1["price"],
            "position_1_target_source": tp1["source"],
            "tp1_contract": tp1,
            "tp1_triggered": False,
            "fibonacci": deepcopy(entry_model.get("fibonacci") or {}),
            "initial_failure_trigger": deepcopy(
                entry_model.get("trigger") or {}
            ),
            "history": [
                {
                    "event": "ATTEMPT_OPENED_RESEARCH_ONLY",
                    "as_of_index": int(entry_model["entry_index"]),
                    "logical_stop": invalidation["logical_boundary"],
                    "emergency_broker_stop": emergency["price"],
                }
            ],
        }
        state["attempts"].append(attempt)
        state["active_attempt"] = attempt_number
        if attempt_number == 1 and state["last_processed_index"] < 0:
            state["last_processed_index"] = (
                int(entry_model["entry_index"]) - 1
            )
        return attempt

    @staticmethod
    def _active(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        number = state.get("active_attempt")
        if number is None:
            return None
        for attempt in state["attempts"]:
            if attempt["attempt_number"] == number:
                return attempt
        return None

    def _trail_boundary(
        self,
        *,
        data: pd.DataFrame,
        point: Dict[str, Any],
        direction: str,
        timeframe: Any,
        proof_index: int,
    ) -> float:
        row = data.iloc[int(point["index"])]
        body_edge = (
            min(_number(row["open"]), _number(row["close"]))
            if direction == "BULLISH"
            else max(_number(row["open"]), _number(row["close"]))
        )
        if _timeframe_name(timeframe) == "M1":
            return body_edge
        atr_value = atr_at(data, as_of_index=proof_index)
        return (
            body_edge
            - self.config.trail_atr_tolerance * atr_value
            if direction == "BULLISH"
            else body_edge
            + self.config.trail_atr_tolerance * atr_value
        )

    def _register_candidates(
        self,
        *,
        attempt: Dict[str, Any],
        swings: list[Dict[str, Any]],
        candle_index: int,
    ) -> None:
        direction = attempt["direction"]
        wanted_side = "LOW" if direction == "BULLISH" else "HIGH"
        wanted_class = "HL" if direction == "BULLISH" else "LH"
        opposite_side = "HIGH" if direction == "BULLISH" else "LOW"
        existing = {
            int(candidate["structure_index"])
            for candidate in attempt["trail_candidates"]
        }
        confirmed_now = [
            point
            for point in swings
            if int(point["confirmed_at_index"]) == candle_index
        ]
        for point in confirmed_now:
            if (
                str(point["side"]) != wanted_side
                or str(point.get("classification")) != wanted_class
                or int(point["index"]) <= int(attempt["entry_index"])
                or int(point["index"]) in existing
            ):
                continue
            preceding = [
                candidate
                for candidate in swings
                if str(candidate["side"]) == opposite_side
                and int(attempt["entry_index"])
                < int(candidate["index"])
                < int(point["index"])
                and int(candidate["confirmed_at_index"]) <= candle_index
            ]
            candidate = {
                "state": "TRAIL_CANDIDATE_UNPROVEN",
                "structure_index": int(point["index"]),
                "structure_level": _number(point["level"]),
                "structure_type": wanted_class,
                "confirmed_at_index": candle_index,
                "proof_structure_index": (
                    int(preceding[-1]["index"]) if preceding else None
                ),
                "proof_level": (
                    _number(preceding[-1]["level"]) if preceding else None
                ),
                "proof_index": None,
                "logical_boundary": None,
                "moved": False,
                "rejection_reason": (
                    None
                    if preceding
                    else "NO_MEANINGFUL_PRECEDING_IMPULSE_EXTREME"
                ),
            }
            attempt["trail_candidates"].append(candidate)
            attempt["trail_state"] = "TRAIL_CANDIDATE_UNPROVEN"
            attempt["history"].append(
                {
                    "event": "TRAIL_CANDIDATE_UNPROVEN",
                    "as_of_index": candle_index,
                    "structure_index": int(point["index"]),
                }
            )

    def _prove_and_move_trails(
        self,
        *,
        attempt: Dict[str, Any],
        data: pd.DataFrame,
        timeframe: Any,
        candle_index: int,
    ) -> None:
        direction = attempt["direction"]
        row = data.iloc[candle_index]
        close = _number(row["close"])
        open_price = _number(row["open"])
        candle_atr = atr_at(data, as_of_index=candle_index)
        body_atr = (
            abs(close - open_price) / candle_atr
            if candle_atr > 0
            else 0.0
        )
        correct_direction = (
            close > open_price
            if direction == "BULLISH"
            else close < open_price
        )
        for candidate in attempt["trail_candidates"]:
            if candidate["state"] != "TRAIL_CANDIDATE_UNPROVEN":
                continue
            proof_level = candidate.get("proof_level")
            if proof_level is None:
                continue
            proved = (
                close > _number(proof_level)
                if direction == "BULLISH"
                else close < _number(proof_level)
            )
            if (
                not proved
                or not correct_direction
                or body_atr < float(self.config.trail_min_body_atr)
            ):
                continue
            boundary = self._trail_boundary(
                data=data,
                point={
                    "index": candidate["structure_index"],
                    "level": candidate["structure_level"],
                },
                direction=direction,
                timeframe=timeframe,
                proof_index=candle_index,
            )
            candidate.update(
                {
                    "state": "TRAIL_PROVEN",
                    "proof_index": candle_index,
                    "logical_boundary": boundary,
                    "proof_body_atr": body_atr,
                    "proof_correct_direction": correct_direction,
                }
            )
            attempt["proven_trails"].append(deepcopy(candidate))
            attempt["trail_state"] = "TRAIL_PROVEN"
            current = _number(attempt["current_protection"])
            favourable = (
                boundary > current
                if direction == "BULLISH"
                else boundary < current
            )
            if favourable:
                if (
                    attempt.get("tp1_triggered")
                    and attempt["management_profile"]
                    in {
                        "TWIN_POSITION_50_50",
                        "PARTIAL_PLUS_RUNNER",
                    }
                ):
                    boundary = (
                        max(boundary, _number(attempt["entry_price"]))
                        if direction == "BULLISH"
                        else min(
                            boundary,
                            _number(attempt["entry_price"]),
                        )
                    )
                attempt["current_protection"] = boundary
                attempt["current_protection_source"] = (
                    "TRAILING_PROTECTION"
                )
                candidate["state"] = "TRAIL_MOVED"
                candidate["moved"] = True
                attempt["trail_state"] = "TRAIL_MOVED"
                movement = {
                    "event": "TRAIL_MOVED",
                    "as_of_index": candle_index,
                    "structure_index": candidate["structure_index"],
                    "proof_index": candle_index,
                    "old_level": current,
                    "new_level": boundary,
                }
                attempt["trail_movements"].append(movement)
                attempt["history"].append(movement)
            else:
                candidate["state"] = "TRAIL_HELD"
                attempt["trail_state"] = "TRAIL_HELD"
                attempt["history"].append(
                    {
                        "event": "TRAIL_HELD",
                        "as_of_index": candle_index,
                        "reason": "CANDIDATE_WOULD_LOOSEN_PROTECTION",
                    }
                )

    def _dominant_intact(
        self,
        *,
        attempt: Dict[str, Any],
        close: float,
    ) -> bool:
        contract = attempt["dominant_decision_protection"]
        if not contract.get("available"):
            return False
        level = _number(contract["level"])
        return (
            close > level
            if attempt["direction"] == "BULLISH"
            else close < level
        )

    def _process_active(
        self,
        *,
        state: Dict[str, Any],
        attempt: Dict[str, Any],
        data: pd.DataFrame,
        timeframe: Any,
        swings: list[Dict[str, Any]],
        candle_index: int,
    ) -> None:
        if candle_index <= int(attempt["entry_index"]):
            return
        target = attempt.get("position_1_target")
        if target is not None and not attempt.get("tp1_triggered"):
            row = data.iloc[candle_index]
            reached = (
                _number(row["high"]) >= _number(target)
                if attempt["direction"] == "BULLISH"
                else _number(row["low"]) <= _number(target)
            )
            if reached:
                attempt["tp1_triggered"] = True
                attempt["history"].append(
                    {
                        "event": "TP1_TRIGGERED_RESEARCH",
                        "as_of_index": candle_index,
                        "target": _number(target),
                        "model": attempt["tp1_model"],
                    }
                )
        self._register_candidates(
            attempt=attempt,
            swings=swings,
            candle_index=candle_index,
        )
        self._prove_and_move_trails(
            attempt=attempt,
            data=data,
            timeframe=timeframe,
            candle_index=candle_index,
        )
        active_contract = dict(attempt["logical_invalidation"])
        active_contract["logical_boundary"] = attempt[
            "current_protection"
        ]
        decision = logical_invalidation_decision(
            row=data.iloc[candle_index],
            direction=attempt["direction"],
            timeframe=timeframe,
            contract=active_contract,
            config=self.config,
        )
        if not decision["invalidated"]:
            if decision["wick_only_survived"]:
                attempt["history"].append(
                    {
                        "event": "WICK_THROUGH_LOGICAL_LEVEL_SURVIVED",
                        "as_of_index": candle_index,
                        "level": attempt["current_protection"],
                    }
                )
            return
        close = _number(data.iloc[candle_index]["close"])
        source = attempt["current_protection_source"]
        attempt["status"] = "CLOSED_LOGICAL_INVALIDATION"
        attempt["exit_index"] = candle_index
        attempt["exit_price"] = close
        attempt["exit_reason"] = (
            "OPPOSING_MEANINGFUL_BOS"
            if source == "TRAILING_PROTECTION"
            else "SETUP_LOGICAL_BODY_CLOSE_INVALIDATION"
        )
        if source == "TRAILING_PROTECTION":
            attempt["trail_state"] = "TRAIL_INVALIDATED"
            attempt["opposing_bos"] = {
                "state": "OPPOSING_MEANINGFUL_BOS_EXIT",
                "index": candle_index,
                "close": close,
                "broken_protection": attempt["current_protection"],
                "body_close_confirmed": True,
                "micro_swing_exit": False,
            }
        attempt["history"].append(
            {
                "event": attempt["exit_reason"],
                "as_of_index": candle_index,
                **decision,
            }
        )
        state["active_attempt"] = None
        if attempt["attempt_number"] == 1:
            state["reentry_state"] = (
                "FIRST_ENTRY_FAILED_RETRACEMENT_ACTIVE"
            )
            state["parent_retracement_active"] = True
            state["reentry_monitoring"] = True
            state["fresh_counter"] = None
            state["fresh_trigger"] = None
            state["history"].append(
                {
                    "event": state["reentry_state"],
                    "as_of_index": candle_index,
                    "reentry_armed": False,
                    "parent_setup_id": state["parent_setup_id"],
                    "parent_retracement_active": True,
                }
            )
        else:
            state["reentry_state"] = "CLOSED_AFTER_SECOND_FAILURE"
            state["terminal"] = True
            state["parent_retracement_active"] = False
            state["reentry_monitoring"] = False
            state["history"].append(
                {
                    "event": "CLOSED_AFTER_SECOND_FAILURE",
                    "as_of_index": candle_index,
                }
            )

    def _fresh_reentry(
        self,
        *,
        state: Dict[str, Any],
        data: pd.DataFrame,
        timeframe: Any,
        swings: list[Dict[str, Any]],
        candle_index: int,
        context: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if (
            state["reentry_state"]
            != "FIRST_ENTRY_FAILED_RETRACEMENT_ACTIVE"
            or state["reentry_count"] != 0
            or state["terminal"]
            or not state["parent_retracement_active"]
            or not state["reentry_monitoring"]
        ):
            return None
        first = state["attempts"][0]
        failure_index = int(first["exit_index"])
        close = _number(data.iloc[candle_index]["close"])
        if not self._dominant_intact(attempt=first, close=close):
            state["reentry_state"] = (
                "REENTRY_REJECTED_DOMINANT_PROTECTION_FAILED"
            )
            state["terminal"] = True
            state["parent_retracement_active"] = False
            state["reentry_monitoring"] = False
            return None
        direction = state["direction"]
        counter_side = "LOW" if direction == "BULLISH" else "HIGH"
        trigger_side = "HIGH" if direction == "BULLISH" else "LOW"
        for point in swings:
            if int(point["confirmed_at_index"]) != candle_index:
                continue
            if int(point["index"]) <= failure_index:
                continue
            if (
                state["fresh_counter"] is None
                and str(point["side"]) == counter_side
            ):
                state["fresh_counter"] = dict(point)
            elif (
                state["fresh_counter"] is not None
                and str(point["side"]) == trigger_side
                and int(point["index"])
                > int(state["fresh_counter"]["index"])
            ):
                state["fresh_trigger"] = dict(point)
        trigger = state.get("fresh_trigger")
        counter = state.get("fresh_counter")
        if not trigger or not counter:
            return None
        broke = (
            close > _number(trigger["level"])
            if direction == "BULLISH"
            else close < _number(trigger["level"])
        )
        row = data.iloc[candle_index]
        correct_entry_body = (
            close > _number(row["open"])
            if direction == "BULLISH"
            else close < _number(row["open"])
        )
        if (
            not broke
            or not correct_entry_body
            or candle_index <= int(trigger["confirmed_at_index"])
        ):
            return None
        fibonacci = reassess_same_cycle(
            data=data,
            original=first.get("fibonacci") or {},
            as_of_index=candle_index,
        )
        entry_model = {
            "setup_id": state["parent_setup_id"],
            "direction": direction,
            "entry_index": candle_index,
            "entry_price": close,
            "counter": counter,
            "trigger": trigger,
            "anchor": counter,
            "stop_level": counter["level"],
            "fibonacci": fibonacci,
        }
        entry_model["logical_stop_structure"] = (
            select_last_important_pre_bos_swing(
                swings=swings,
                direction=direction,
                trigger_index=int(trigger["index"]),
                entry_index=candle_index,
                data=data,
                setup_start_index=int(counter["index"]),
                fallback=counter,
            )
        )
        attempt = self._open_attempt(
            state=state,
            data=data,
            timeframe=timeframe,
            entry_model=entry_model,
            attempt_number=2,
            context=context,
        )
        state["reentry_count"] = 1
        state["reentry_state"] = "ONE_REENTRY_CONSUMED"
        state["parent_retracement_active"] = False
        state["reentry_monitoring"] = False
        state["history"].append(
            {
                "event": "FRESH_QUALIFIED_REENTRY_BOS",
                "as_of_index": candle_index,
                "counter_index": counter["index"],
                "trigger_index": trigger["index"],
                "reentry_event_id": attempt["event_id"],
                "parent_setup_id": state["parent_setup_id"],
                "fibonacci_zone": fibonacci.get("zone"),
            }
        )
        return attempt

    def evaluate(
        self,
        *,
        data: pd.DataFrame,
        symbol: str,
        timeframe: Any,
        as_of_index: int,
        direction: str,
        context: Optional[Dict[str, Any]],
        confirmed_swings: Iterable[Dict[str, Any]],
        canonical_entry: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        key = self._key(symbol, timeframe)
        normalized = str(direction).upper()
        state = self.markets.setdefault(
            key,
            self._new_state(normalized),
        )
        swings = [dict(point) for point in confirmed_swings]
        entry_model = dict(canonical_entry or {})
        incoming_setup_id = entry_model.get("setup_id")
        if (
            entry_model.get("entry_index") is not None
            and incoming_setup_id is not None
            and state.get("parent_setup_id") is not None
            and incoming_setup_id != state.get("parent_setup_id")
            and self._active(state) is None
        ):
            previous_setup_id = state.get("parent_setup_id")
            state = self._new_state(normalized)
            state["history"].append(
                {
                    "event": "NEW_PARENT_SETUP_MANAGEMENT_RESET",
                    "as_of_index": int(entry_model["entry_index"]),
                    "previous_setup_id": previous_setup_id,
                    "new_setup_id": incoming_setup_id,
                }
            )
            self.markets[key] = state
        if (
            entry_model.get("entry_index") is not None
            and not state["attempts"]
        ):
            state["parent_setup_id"] = entry_model.get("setup_id")
            self._open_attempt(
                state=state,
                data=data,
                timeframe=timeframe,
                entry_model=entry_model,
                attempt_number=1,
                context=context,
            )
        start = max(
            int(state["last_processed_index"]) + 1,
            0,
        )
        reentry_signal = None
        for candle_index in range(start, int(as_of_index) + 1):
            active = self._active(state)
            if active is not None:
                self._process_active(
                    state=state,
                    attempt=active,
                    data=data,
                    timeframe=timeframe,
                    swings=swings,
                    candle_index=candle_index,
                )
            if self._active(state) is None:
                fired = self._fresh_reentry(
                    state=state,
                    data=data,
                    timeframe=timeframe,
                    swings=swings,
                    candle_index=candle_index,
                    context=context,
                )
                if fired is not None:
                    reentry_signal = fired
            state["last_processed_index"] = candle_index
        latest = state["attempts"][-1] if state["attempts"] else None
        active = self._active(state)
        if active:
            manager_state = active["trail_state"]
        elif latest:
            manager_state = latest["status"]
        else:
            manager_state = "NO_MANAGED_ENTRY"
        return {
            "availability": "AVAILABLE" if latest else "UNAVAILABLE",
            "available": bool(latest),
            "state": manager_state,
            "owner": "TrailingProtectionEngine",
            "model": STEVE_MANAGEMENT_MODEL,
            "as_of_index": int(as_of_index),
            "causal_valid": True,
            "management_profile": self.config.management_profile,
            "tp1_model": self.config.tp1_model,
            "attempt_count": len(state["attempts"]),
            "attempts": deepcopy(state["attempts"]),
            "latest_attempt": deepcopy(latest),
            "active_attempt": deepcopy(active),
            "trailing_stop": (
                active.get("current_protection") if active else None
            ),
            "trailing_structure_index": (
                (
                    active.get("trail_movements") or [{}]
                )[-1].get("structure_index")
                if active and active.get("trail_movements")
                else None
            ),
            "reentry_count": int(state["reentry_count"]),
            "reentry_state": state["reentry_state"],
            "reentry_attempted": state["reentry_count"] == 1,
            "parent_retracement_active": bool(
                state["parent_retracement_active"]
            ),
            "reentry_monitoring": bool(state["reentry_monitoring"]),
            "reentry_capability_remaining": (
                0 if state["reentry_count"] or state["terminal"] else 1
            ),
            "reentry_trigger": deepcopy(state.get("fresh_trigger")),
            "reentry_counter": deepcopy(state.get("fresh_counter")),
            "reentry_signal": deepcopy(reentry_signal),
            "parent_setup_closed": bool(state["terminal"]),
            "history": deepcopy(state["history"]),
            "research_only": True,
            "order_api_called": False,
            "reasons": [
                "Raw post-entry fractals remain unproven until a later "
                "same-direction body-close BOS",
                "A first failure only starts fresh-structure observation; "
                "it does not arm re-entry by itself",
            ],
        }
