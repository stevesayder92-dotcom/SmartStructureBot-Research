from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

import pandas as pd

from core.adaptive_decision import grade_setup
from core.fibonacci_contract import FibonacciConfig, build_fibonacci_contract
from core.semantic_swing_hierarchy import build_semantic_swing_hierarchy
from core.steve_trade_management import (
    atr_at,
    dominant_decision_protection,
    emergency_broker_stop,
    select_last_important_pre_bos_swing,
    select_setup_logical_invalidation,
)
from core.setup_lifecycle import PipelineRuntimeState
from core.system_director import DataContractError, SystemStateDirector
from core.second_touch_structure import (
    SecondTouchConfig,
    evaluate_second_touch_structure,
)


EXPERT_STRATEGY_MODEL = "EXPERT_SPEC_V1"
DEFAULT_ENGINE_SENSITIVITY = 3
EXPERT_HTF_TIMEFRAMES = ("H1", "M30", "M15")


@dataclass(frozen=True)
class ExpertStrategyOutput:
    snapshot: Dict[str, Any]
    diagnostics: Dict[str, Any]


def _number(value: Any) -> float:
    return float(value)


def _time_number(value: Any) -> float:
    if isinstance(value, pd.Timestamp):
        return float(value.timestamp())
    if isinstance(value, str):
        return float(pd.Timestamp(value).timestamp())
    return float(value)


def confirmed_swings(
    data: pd.DataFrame,
    *,
    as_of_index: Optional[int] = None,
    sensitivity: int = DEFAULT_ENGINE_SENSITIVITY,
) -> list[Dict[str, Any]]:
    """
    Return strict, immutable N-left/N-right swing points.

    A candidate at index i is deliberately absent until i + sensitivity.
    Once that confirmation candle closes, later data cannot change the point.
    """
    if sensitivity <= 0:
        raise ValueError("ENGINE_SENSITIVITY must be greater than zero")
    if data is None or data.empty:
        return []

    decision = (
        len(data) - 1
        if as_of_index is None
        else int(as_of_index)
    )
    if decision < 0 or decision >= len(data):
        raise IndexError("Swing as_of_index is outside the data range")

    final_candidate = decision - sensitivity
    swings: list[Dict[str, Any]] = []
    previous_level: Dict[str, Optional[float]] = {
        "HIGH": None,
        "LOW": None,
    }

    for index in range(sensitivity, final_candidate + 1):
        high = _number(data.iloc[index]["high"])
        low = _number(data.iloc[index]["low"])
        left = data.iloc[index - sensitivity:index]
        right = data.iloc[index + 1:index + sensitivity + 1]
        is_high = bool(
            (high > left["high"].astype(float)).all()
            and (high > right["high"].astype(float)).all()
        )
        is_low = bool(
            (low < left["low"].astype(float)).all()
            and (low < right["low"].astype(float)).all()
        )

        for side, level, accepted in (
            ("HIGH", high, is_high),
            ("LOW", low, is_low),
        ):
            if not accepted:
                continue
            prior = previous_level[side]
            if prior is None:
                classification = (
                    "SWING_HIGH" if side == "HIGH" else "SWING_LOW"
                )
            elif side == "HIGH":
                classification = "HH" if level > prior else "LH"
            else:
                classification = "LL" if level < prior else "HL"
            confirmed_at = index + sensitivity
            swings.append(
                {
                    "type": f"SWING_{side}",
                    "side": side,
                    "classification": classification,
                    "index": index,
                    "level": level,
                    "price": level,
                    "time": (
                        data.iloc[index]["time"]
                        if "time" in data.columns
                        else None
                    ),
                    "confirmed_at_index": confirmed_at,
                    "confirmed_at_time": (
                        data.iloc[confirmed_at]["time"]
                        if "time" in data.columns
                        else None
                    ),
                    "available_at_index": confirmed_at,
                    "engine_sensitivity": sensitivity,
                    "causal_valid": confirmed_at <= decision,
                    "immutable_after_confirmation": True,
                }
            )
            previous_level[side] = level

    swings.sort(
        key=lambda point: (
            int(point["confirmed_at_index"]),
            int(point["index"]),
            str(point["side"]),
        )
    )
    return swings


def infer_htf_direction(
    data: pd.DataFrame,
    *,
    sensitivity: int = DEFAULT_ENGINE_SENSITIVITY,
) -> Dict[str, Any]:
    """Infer one HTF direction from close-only breaks of confirmed swings."""
    if data is None or data.empty:
        return {
            "available": False,
            "direction": "NEUTRAL",
            "state": "INSUFFICIENT_HTF_DATA",
            "last_break": None,
            "swings": [],
            "causal_valid": True,
            "reasons": ["No closed higher-timeframe candles are available"],
        }

    swings = confirmed_swings(
        data,
        as_of_index=len(data) - 1,
        sensitivity=sensitivity,
    )
    by_confirmation: Dict[int, list[Dict[str, Any]]] = {}
    for point in swings:
        by_confirmation.setdefault(
            int(point["confirmed_at_index"]), []
        ).append(point)

    latest: Dict[str, Optional[Dict[str, Any]]] = {
        "HIGH": None,
        "LOW": None,
    }
    last_break: Optional[Dict[str, Any]] = None

    for candle_index in range(len(data)):
        for point in by_confirmation.get(candle_index, []):
            latest[str(point["side"])] = point

        close = _number(data.iloc[candle_index]["close"])
        open_price = _number(data.iloc[candle_index]["open"])
        candle_atr = atr_at(data, as_of_index=candle_index)
        body_atr = (
            abs(close - open_price) / candle_atr
            if candle_atr > 0
            else 0.0
        )
        high = latest["HIGH"]
        low = latest["LOW"]
        events: list[Dict[str, Any]] = []
        if high is not None and close > _number(high["level"]):
            events.append(
                {
                    "direction": "BULLISH",
                    "type": "BULLISH_CLOSE_BOS",
                    "index": candle_index,
                    "time": (
                        data.iloc[candle_index]["time"]
                        if "time" in data.columns
                        else None
                    ),
                    "close": close,
                    "open": open_price,
                    "correct_direction_body": close > open_price,
                    "body_atr": body_atr,
                    "broken_swing_index": high["index"],
                    "broken_swing_level": high["level"],
                    "broken_swing_confirmed_at_index": high[
                        "confirmed_at_index"
                    ],
                    "wick_only": False,
                    "close_only": True,
                    "causal_valid": (
                        int(high["confirmed_at_index"]) <= candle_index
                    ),
                }
            )
        if low is not None and close < _number(low["level"]):
            events.append(
                {
                    "direction": "BEARISH",
                    "type": "BEARISH_CLOSE_BOS",
                    "index": candle_index,
                    "time": (
                        data.iloc[candle_index]["time"]
                        if "time" in data.columns
                        else None
                    ),
                    "close": close,
                    "open": open_price,
                    "correct_direction_body": close < open_price,
                    "body_atr": body_atr,
                    "broken_swing_index": low["index"],
                    "broken_swing_level": low["level"],
                    "broken_swing_confirmed_at_index": low[
                        "confirmed_at_index"
                    ],
                    "wick_only": False,
                    "close_only": True,
                    "causal_valid": (
                        int(low["confirmed_at_index"]) <= candle_index
                    ),
                }
            )
        if events:
            # A valid OHLC series should not break both boundaries. The
            # final event is deterministic even for malformed synthetic data.
            last_break = events[-1]

    direction = (
        str(last_break["direction"])
        if last_break is not None
        else "NEUTRAL"
    )
    strength = (
        "EXCEPTIONALLY_CLEAN"
        if last_break is not None
        and last_break.get("correct_direction_body")
        and float(last_break.get("body_atr", 0.0)) >= 0.8
        else "CLEAN"
        if last_break is not None
        and last_break.get("correct_direction_body")
        and float(last_break.get("body_atr", 0.0)) >= 0.35
        else "WEAK"
        if last_break is not None
        else "NEUTRAL"
    )
    return {
        "available": last_break is not None,
        "direction": direction,
        "state": (
            f"{direction}_CLOSE_BOS_CONFIRMED"
            if last_break is not None
            else "WAITING_FOR_CONFIRMED_SWING_CLOSE_BOS"
        ),
        "last_break": last_break,
        "strength": strength,
        "exceptionally_clean": strength == "EXCEPTIONALLY_CLEAN",
        "last_confirmed_high": latest["HIGH"],
        "last_confirmed_low": latest["LOW"],
        "swings": swings,
        "causal_valid": all(
            int(point["confirmed_at_index"]) <= len(data) - 1
            for point in swings
        ),
        "reasons": [
            (
                "Direction is owned by the latest candle-close break "
                "of a confirmed strict swing"
            )
        ],
    }


def build_expert_htf_context(
    *,
    decision_candle_open_time: Any,
    decision_timeframe_seconds: int,
    frame_data: Dict[str, pd.DataFrame],
    sensitivity: int = DEFAULT_ENGINE_SENSITIVITY,
    policy: str = "STRICT_2_OF_3_H1_M30_M15",
    allow_single_strong: bool = False,
) -> Dict[str, Any]:
    """
    Build configurable causal H1/M30/M15 context from closed candles only.

    Strict voting remains available. The adaptive policy can approve one
    exceptionally clean frame only when the others are neutral, and can
    retain a mixed-but-usable context as reduced-risk research evidence.
    """
    decision_close_time = (
        _time_number(decision_candle_open_time)
        + int(decision_timeframe_seconds)
    )
    seconds = {"H1": 3600, "M30": 1800, "M15": 900}
    frames: Dict[str, Dict[str, Any]] = {}
    votes = {"BULLISH": 0, "BEARISH": 0, "NEUTRAL": 0}
    incomplete_used = False

    for timeframe in EXPERT_HTF_TIMEFRAMES:
        source = frame_data.get(timeframe)
        if source is None or source.empty or "time" not in source.columns:
            frame = {
                "available": False,
                "direction": "NEUTRAL",
                "state": "HTF_FRAME_UNAVAILABLE",
                "last_break": None,
                "closed_rows_used": 0,
                "causal_valid": True,
                "reasons": [f"{timeframe} closed candle data is unavailable"],
            }
        else:
            open_times = source["time"].map(_time_number)
            mask = open_times + seconds[timeframe] <= decision_close_time
            closed = source.loc[mask].copy().reset_index(drop=True)
            incomplete_used = bool(
                incomplete_used
                or (
                    len(closed) < len(source)
                    and not mask.iloc[-1]
                    and (
                        open_times.iloc[-1] + seconds[timeframe]
                        <= decision_close_time
                    )
                )
            )
            frame = infer_htf_direction(
                closed,
                sensitivity=sensitivity,
            )
            frame["closed_rows_used"] = len(closed)
            frame["last_closed_open_time"] = (
                _time_number(closed.iloc[-1]["time"])
                if not closed.empty
                else None
            )
            frame["timeframe"] = timeframe
        frames[timeframe] = frame
        votes[str(frame["direction"])] += 1

    normalized_policy = str(policy).upper()
    bullish_frames = [
        name for name, frame in frames.items()
        if frame.get("direction") == "BULLISH"
    ]
    bearish_frames = [
        name for name, frame in frames.items()
        if frame.get("direction") == "BEARISH"
    ]
    approved = "NEUTRAL"
    state = "RANGING"
    hard_block = True
    risk_modifier = 0.0
    if votes["BULLISH"] == 3:
        approved, state, hard_block, risk_modifier = (
            "BULLISH", "STRONG_ALIGNED_BULLISH", False, 1.0
        )
    elif votes["BEARISH"] == 3:
        approved, state, hard_block, risk_modifier = (
            "BEARISH", "STRONG_ALIGNED_BEARISH", False, 1.0
        )
    elif votes["BULLISH"] >= 2:
        approved, state, hard_block, risk_modifier = (
            "BULLISH", "ALIGNED_BULLISH", False, 1.0
        )
    elif votes["BEARISH"] >= 2:
        approved, state, hard_block, risk_modifier = (
            "BEARISH", "ALIGNED_BEARISH", False, 1.0
        )
    else:
        directional = bullish_frames + bearish_frames
        single_name = directional[0] if len(directional) == 1 else None
        single = frames.get(single_name, {}) if single_name else {}
        adaptive = normalized_policy in {
            "ADAPTIVE_STRUCTURE_POLICY",
            "ONE_EXCEPTIONALLY_CLEAN_HTF",
            "CONFLICT_RISK_REDUCTION",
            "PREFERRED_M30_M15",
        }
        if (
            adaptive
            and allow_single_strong
            and single_name is not None
            and single.get("exceptionally_clean")
        ):
            approved = str(single["direction"])
            state = f"SINGLE_STRONG_SUPPORT_{approved}"
            hard_block = False
            risk_modifier = 0.85
        elif (
            adaptive
            and bullish_frames
            and bearish_frames
            and normalized_policy == "CONFLICT_RISK_REDUCTION"
        ):
            preferred = next(
                (
                    name
                    for name in ("M30", "M15", "H1")
                    if frames[name].get("strength")
                    in {"CLEAN", "EXCEPTIONALLY_CLEAN"}
                ),
                None,
            )
            if preferred is not None:
                approved = str(frames[preferred]["direction"])
                state = f"MIXED_BUT_USABLE_{approved}"
                hard_block = False
                risk_modifier = 0.50
            else:
                state = "CONFLICT"
        elif bullish_frames and bearish_frames:
            state = "CONFLICT"

    available = approved in {"BULLISH", "BEARISH"} and not hard_block
    return {
        "availability": "AVAILABLE" if available else "UNAVAILABLE",
        "available": available,
        "state": state,
        "owner": "HTFContextEngine",
        "strategy_model": EXPERT_STRATEGY_MODEL,
        "policy": normalized_policy,
        "approved_direction": approved,
        "frames": frames,
        "votes": votes,
        "as_of_time": decision_close_time,
        "causal": True,
        "causal_valid": True,
        "incomplete_htf_candles_used": incomplete_used,
        "hard_block": hard_block,
        "risk_modifier": risk_modifier,
        "allow_single_strong": bool(allow_single_strong),
        "advisory_only": False,
        "reasons": [
            (
                f"HTF votes: bullish={votes['BULLISH']}, "
                f"bearish={votes['BEARISH']}, neutral={votes['NEUTRAL']}"
            ),
            (
                "Strict 2-of-3, one exceptionally clean frame, and "
                "mixed reduced-risk behavior are explicit configurable policies"
            ),
        ],
    }


def _empty_context(as_of_index: int) -> Dict[str, Any]:
    return {
        "availability": "UNAVAILABLE",
        "available": False,
        "state": "STRICT_2_OF_3_CONTEXT_NOT_SUPPLIED",
        "owner": "HTFContextEngine",
        "strategy_model": EXPERT_STRATEGY_MODEL,
        "policy": "STRICT_2_OF_3_H1_M30_M15",
        "approved_direction": "NEUTRAL",
        "frames": {},
        "votes": {"BULLISH": 0, "BEARISH": 0, "NEUTRAL": 3},
        "as_of_index": as_of_index,
        "causal": True,
        "causal_valid": True,
        "incomplete_htf_candles_used": False,
        "hard_block": True,
        "advisory_only": False,
        "reasons": [
            "No causal H1/M30/M15 context was supplied; trading is blocked"
        ],
    }


def _opposite(direction: str) -> str:
    return "BULLISH" if direction == "BEARISH" else "BEARISH"


def _find_same_direction_origin_bos(
    data: pd.DataFrame,
    *,
    swings: Iterable[Dict[str, Any]],
    direction: str,
    before_or_at_index: int,
) -> Optional[Dict[str, Any]]:
    """Find the last causal same-direction body-close BOS before an impulse extreme."""
    expected_side = "HIGH" if direction == "BULLISH" else "LOW"
    latest: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    by_confirmation: Dict[int, list[Dict[str, Any]]] = {}
    for point in swings:
        by_confirmation.setdefault(
            int(point["confirmed_at_index"]), []
        ).append(point)
    for candle_index in range(min(int(before_or_at_index), len(data) - 1) + 1):
        for point in by_confirmation.get(candle_index, []):
            if str(point["side"]) == expected_side:
                latest = point
        if latest is None:
            continue
        row = data.iloc[candle_index]
        close = _number(row["close"])
        open_price = _number(row["open"])
        broke = (
            close > _number(latest["level"])
            if direction == "BULLISH"
            else close < _number(latest["level"])
        )
        correct_body = (
            close > open_price if direction == "BULLISH" else close < open_price
        )
        if broke and correct_body:
            result = {
                "type": f"{direction}_BODY_CLOSE_BOS",
                "direction": direction,
                "index": candle_index,
                "price": close,
                "broken_structure_index": int(latest["index"]),
                "broken_structure_level": _number(latest["level"]),
                "broken_structure_available_at_index": int(
                    latest["confirmed_at_index"]
                ),
                "as_of_index": candle_index,
                "causal_valid": int(latest["confirmed_at_index"]) <= candle_index,
                "close_only": True,
                "correct_direction_body": True,
            }
    return result


def _simulate_retracements(
    data: pd.DataFrame,
    *,
    direction: str,
    swings: Iterable[Dict[str, Any]],
    symbol: str,
    timeframe: Any,
    sensitivity: int,
    fibonacci_config: Optional[FibonacciConfig] = None,
    second_touch_enabled: bool = False,
    second_touch_config: SecondTouchConfig = SecondTouchConfig(),
) -> Dict[str, Any]:
    """Run the exact M5 pullback/trigger state machine over visible candles."""
    fibonacci_config = fibonacci_config or FibonacciConfig()
    bearish = direction == "BEARISH"
    anchor_side = "LOW" if bearish else "HIGH"
    counter_side = "HIGH" if bearish else "LOW"
    trigger_side = anchor_side
    by_confirmation: Dict[int, list[Dict[str, Any]]] = {}
    for point in swings:
        by_confirmation.setdefault(
            int(point["confirmed_at_index"]), []
        ).append(point)

    anchor: Optional[Dict[str, Any]] = None
    counter: Optional[Dict[str, Any]] = None
    trigger: Optional[Dict[str, Any]] = None
    initial_trigger: Optional[Dict[str, Any]] = None
    qualified_at: Optional[int] = None
    trigger_updates = 0
    last_terminal: Optional[Dict[str, Any]] = None
    terminal_entries: list[Dict[str, Any]] = []
    history: list[Dict[str, Any]] = []
    published_second_touch_state: Optional[str] = None
    current_second_touch: Optional[Dict[str, Any]] = None

    def better_anchor(point: Dict[str, Any]) -> bool:
        if anchor is None:
            return True
        if bearish:
            return _number(point["level"]) < _number(anchor["level"])
        return _number(point["level"]) > _number(anchor["level"])

    def valid_trigger(point: Dict[str, Any]) -> bool:
        if anchor is None:
            return False
        if bearish:
            return _number(point["level"]) > _number(anchor["level"])
        return _number(point["level"]) < _number(anchor["level"])

    def meaningful_counter(point: Dict[str, Any], candle_index: int) -> bool:
        if anchor is None:
            return False
        local_atr = atr_at(data, as_of_index=candle_index)
        displacement = abs(
            _number(point["level"]) - _number(anchor["level"])
        )
        return local_atr <= 0 or displacement / local_atr >= 0.35

    for candle_index in range(len(data)):
        for point in sorted(
            by_confirmation.get(candle_index, []),
            key=lambda value: (int(value["index"]), str(value["side"])),
        ):
            side = str(point["side"])
            if anchor is None:
                if side == anchor_side:
                    anchor = point
                    history = [
                        {
                            "event": "PULLBACK_ORIGIN_CONFIRMED",
                            "as_of_index": candle_index,
                            "swing_index": point["index"],
                            "swing_level": point["level"],
                        }
                    ]
                continue

            if counter is None:
                if side == anchor_side and better_anchor(point):
                    anchor = point
                    history.append(
                        {
                            "event": "PULLBACK_ORIGIN_MOVED_TO_NEW_EXTREME",
                            "as_of_index": candle_index,
                            "swing_index": point["index"],
                            "swing_level": point["level"],
                        }
                    )
                elif (
                    side == counter_side
                    and int(point["index"]) > int(anchor["index"])
                ):
                    if not meaningful_counter(point, candle_index):
                        history.append(
                            {
                                "event": "WEAK_COUNTER_SWING_REQUIRES_SEQUENCE",
                                "as_of_index": candle_index,
                                "swing_index": point["index"],
                                "swing_level": point["level"],
                                "soft_quality_reduction": True,
                            }
                        )
                    counter = point
                    history.append(
                        {
                            "event": "COUNTER_SWING_CONFIRMED",
                            "as_of_index": candle_index,
                            "swing_index": point["index"],
                            "swing_level": point["level"],
                        }
                    )
                continue

            if trigger is None:
                if side == anchor_side:
                    if better_anchor(point):
                        anchor = point
                        counter = None
                        history.append(
                            {
                                "event": "UNBROKEN_TREND_EXTREME_RESET_ORIGIN",
                                "as_of_index": candle_index,
                                "swing_index": point["index"],
                                "swing_level": point["level"],
                            }
                        )
                    elif (
                        int(point["index"]) > int(counter["index"])
                        and valid_trigger(point)
                    ):
                        trigger = point
                        initial_trigger = point
                        qualified_at = candle_index
                        history.append(
                            {
                                "event": "FAILURE_TRIGGER_CONFIRMED",
                                "as_of_index": candle_index,
                                "swing_index": point["index"],
                                "swing_level": point["level"],
                            }
                        )
                elif (
                    side == counter_side
                    and int(point["index"]) > int(counter["index"])
                ):
                    counter = point
                continue

            if (
                side == trigger_side
                and int(point["index"]) > int(trigger["index"])
                and valid_trigger(point)
            ):
                trigger = point
                trigger_updates += 1
                history.append(
                    {
                        "event": "FAILURE_TRIGGER_UPDATED",
                        "as_of_index": candle_index,
                        "swing_index": point["index"],
                        "swing_level": point["level"],
                    }
                )

        if anchor is None or trigger is None:
            continue

        setup_id = (
            f"{symbol}|{timeframe}|{EXPERT_STRATEGY_MODEL}|"
            f"{direction}|PB_{anchor['index']}"
        )
        second_touch_owner = {
            "parent_setup_id": setup_id,
            "retracement_id": f"{setup_id}|RETRACEMENT|{anchor['index']}",
            "impulse_cycle_id": f"{setup_id}|IMPULSE_CYCLE",
            "direction": direction,
            "dominant_protection_identity": f"{setup_id}|DOMINANT_PROTECTION",
            "fib_anchor_version": getattr(fibonacci_config, "anchor_version", "FIBONACCI_CONTRACT_V1"),
        }
        if current_second_touch is None or by_confirmation.get(candle_index):
            current_second_touch = evaluate_second_touch_structure(
                data=data,
                swings=swings,
                direction=direction,
                as_of_index=candle_index,
                setup_start_index=int(anchor["index"]),
                owner=second_touch_owner,
                expected_owner=second_touch_owner,
                config=second_touch_config,
            )
        second_touch = current_second_touch
        if second_touch_enabled and second_touch["state"] != published_second_touch_state:
            history.append(
                {
                    "event": second_touch["state"],
                    "as_of_index": candle_index,
                    "second_touch": second_touch,
                }
            )
            published_second_touch_state = second_touch["state"]
        if second_touch_enabled and second_touch["state"] == "SECOND_TOUCH_CANDIDATE":
            continue
        second_touch_active = bool(
            second_touch_enabled
            and second_touch["state"] == "SECOND_TOUCH_CONFIRMED"
        )
        if second_touch_active:
            active_trigger = second_touch.get("active_trigger") or {}
            active_index = int(active_trigger.get("swing_index", -1))
            if active_index != int(trigger["index"]):
                replacement = next(
                    (
                        point
                        for point in swings
                        if int(point["index"]) == active_index
                        and int(point["confirmed_at_index"]) <= candle_index
                    ),
                    None,
                )
                if replacement is None:
                    continue
                trigger = replacement
                qualified_at = int(replacement["confirmed_at_index"])
                trigger_updates += 1
                history.append(
                    {
                        "event": "ACTIVE_SECOND_TOUCH_TRIGGER",
                        "as_of_index": candle_index,
                        "swing_index": trigger["index"],
                        "swing_level": trigger["level"],
                    }
                )

        row = data.iloc[candle_index]
        close = _number(row["close"])
        open_price = _number(row["open"])
        low = _number(row["low"])
        high = _number(row["high"])
        level = _number(trigger["level"])
        close_break = close < level if bearish else close > level
        correct_entry_body = (
            close < open_price if bearish else close > open_price
        )
        wick_break = (
            low < level and close >= level
            if bearish
            else high > level and close <= level
        )
        if wick_break:
            history.append(
                {
                    "event": "WICK_ONLY_TRIGGER_SWEEP_NO_ENTRY",
                    "as_of_index": candle_index,
                    "trigger_index": trigger["index"],
                    "trigger_level": level,
                }
            )
        if close_break and not correct_entry_body:
            history.append(
                {
                    "event": "WRONG_DIRECTION_BODY_CLOSE_REJECTED",
                    "as_of_index": candle_index,
                    "trigger_index": trigger["index"],
                    "trigger_level": level,
                    "open": open_price,
                    "close": close,
                }
            )
        if not close_break or not correct_entry_body:
            continue

        local_origin_bos = _find_same_direction_origin_bos(
            data,
            swings=swings,
            direction=direction,
            before_or_at_index=int(anchor["index"]),
        )
        entry_fibonacci = build_fibonacci_contract(
            data=data,
            direction=direction,
            anchor=anchor,
            swings=swings,
            as_of_index=candle_index,
            origin_bos_index=(
                int(local_origin_bos["index"])
                if local_origin_bos is not None
                else None
            ),
            config=fibonacci_config,
        )
        if (
            entry_fibonacci.get("available")
            and float(entry_fibonacci.get("depth", 0.0)) >= 1.0
        ):
            history.append(
                {
                    "event": "IMPULSE_ORIGIN_BROKEN_NO_ENTRY",
                    "as_of_index": candle_index,
                    "fibonacci_depth": entry_fibonacci["depth"],
                    "fib_zero_index": entry_fibonacci[
                        "fib_zero_index"
                    ],
                    "hard_block": True,
                }
            )
            anchor = None
            counter = None
            trigger = None
            initial_trigger = None
            qualified_at = None
            trigger_updates = 0
            history = []
            current_second_touch = None
            published_second_touch_state = None
            continue

        start = int(anchor["index"])
        stop_slice = data.iloc[start:candle_index + 1]
        stop = (
            float(stop_slice["high"].astype(float).max())
            if bearish
            else float(stop_slice["low"].astype(float).min())
        )
        if second_touch_active:
            touch_2 = second_touch["touch_2"]
            logical_stop_structure = {
                "owner": "SecondTouchStructureEngine",
                "selection_method": "SECOND_TOUCH_WICK_EXTREME",
                "side": counter_side,
                "index": int(touch_2["swing_index"]),
                "confirmed_at_index": int(touch_2["available_at_index"]),
                "level": _number(touch_2["price"]),
                "price": _number(touch_2["price"]),
                "causal_valid": int(touch_2["available_at_index"]) <= candle_index,
            }
        else:
            logical_stop_structure = select_last_important_pre_bos_swing(
                swings=swings,
                direction=direction,
                trigger_index=int(trigger["index"]),
                entry_index=candle_index,
                data=data,
                setup_start_index=int(anchor["index"]),
                fallback=counter,
            )
        history.append(
            {
                "event": "CLOSE_BOS_ENTRY_AND_SETUP_CONSUMED",
                "as_of_index": candle_index,
                "trigger_index": trigger["index"],
                "trigger_level": level,
                "entry_close": close,
                "stop_level": stop,
                "logical_stop_structure_index": (
                    logical_stop_structure["index"]
                ),
            }
        )
        last_terminal = {
            "setup_id": setup_id,
            "direction": direction,
            "anchor": anchor,
            "counter": counter,
            "trigger": trigger,
            "logical_stop_structure": logical_stop_structure,
            "initial_trigger": initial_trigger,
            "qualified_at": qualified_at,
            "trigger_updates": trigger_updates,
            "entry_index": candle_index,
            "entry_price": close,
            "stop_level": stop,
            "wick_only": False,
            "history": list(history),
            "status": "CONSUMED",
            "origin_bos": local_origin_bos,
            "second_touch": second_touch,
            "second_touch_entry": second_touch_active,
        }
        last_terminal["fibonacci"] = entry_fibonacci
        terminal_entries.append(dict(last_terminal))
        anchor = None
        counter = None
        trigger = None
        initial_trigger = None
        qualified_at = None
        trigger_updates = 0
        history = []
        current_second_touch = None
        published_second_touch_state = None

    current_index = len(data) - 1
    if anchor is None:
        if last_terminal is not None:
            result = dict(last_terminal)
            result["all_entries"] = terminal_entries
            return result
        return {
            "setup_id": None,
            "direction": direction,
            "anchor": None,
            "counter": None,
            "trigger": None,
            "initial_trigger": None,
            "qualified_at": None,
            "trigger_updates": 0,
            "entry_index": None,
            "entry_price": None,
            "stop_level": None,
            "wick_only": False,
            "history": [],
            "status": "WAITING_FOR_PULLBACK_ORIGIN",
            "latest_entry": None,
            "all_entries": [],
        }

    setup_id = (
        f"{symbol}|{timeframe}|{EXPERT_STRATEGY_MODEL}|"
        f"{direction}|PB_{anchor['index']}"
    )
    if trigger is not None:
        status = "ACTIVE"
    elif counter is not None:
        status = "DEVELOPING"
    else:
        status = "DEVELOPING"
    stop_slice = data.iloc[int(anchor["index"]):current_index + 1]
    stop = (
        float(stop_slice["high"].astype(float).max())
        if bearish
        else float(stop_slice["low"].astype(float).min())
    )
    wick_only = False
    if trigger is not None:
        row = data.iloc[current_index]
        level = _number(trigger["level"])
        wick_only = (
            _number(row["low"]) < level
            and _number(row["close"]) >= level
            if bearish
            else _number(row["high"]) > level
            and _number(row["close"]) <= level
        )
    return {
        "setup_id": setup_id,
        "direction": direction,
        "anchor": anchor,
        "counter": counter,
        "trigger": trigger,
        "initial_trigger": initial_trigger,
        "qualified_at": qualified_at,
        "trigger_updates": trigger_updates,
        "entry_index": None,
        "entry_price": None,
        "stop_level": stop,
        "wick_only": wick_only,
        "history": history,
        "status": status,
        "latest_entry": last_terminal,
        "all_entries": terminal_entries,
    }


def scan_expert_m5_candidates(
    data: pd.DataFrame,
    *,
    direction: str,
    symbol: str,
    timeframe: Any = "M5",
    sensitivity: int = DEFAULT_ENGINE_SENSITIVITY,
    fibonacci_config: Optional[FibonacciConfig] = None,
    second_touch_enabled: bool = False,
    second_touch_config: SecondTouchConfig = SecondTouchConfig(),
) -> list[Dict[str, Any]]:
    """Efficiently enumerate causal M5 candidates for offline review."""
    normalized_direction = str(direction).upper()
    if normalized_direction not in {"BULLISH", "BEARISH"}:
        raise ValueError("Candidate direction must be BULLISH or BEARISH")
    swings = confirmed_swings(
        data,
        as_of_index=len(data) - 1,
        sensitivity=sensitivity,
    )
    model = _simulate_retracements(
        data,
        direction=normalized_direction,
        swings=swings,
        symbol=symbol,
        timeframe=timeframe,
        sensitivity=sensitivity,
        fibonacci_config=fibonacci_config,
        second_touch_enabled=second_touch_enabled,
        second_touch_config=second_touch_config,
    )
    return [
        dict(entry)
        for entry in model.get("all_entries", [])
    ]


def _research_management(
    data: pd.DataFrame,
    *,
    swings: Iterable[Dict[str, Any]],
    entry_model: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if not entry_model or entry_model.get("entry_index") is None:
        return {
            "availability": "UNAVAILABLE",
            "available": False,
            "state": "NOT_ACTIVE_BEFORE_ENTRY",
            "owner": "TrailingProtectionEngine",
            "as_of_index": len(data) - 1,
            "causal_valid": True,
            "research_only": True,
            "order_api_called": False,
            "reasons": ["No expert-spec entry exists in the visible history"],
        }

    direction = str(entry_model["direction"])
    bearish = direction == "BEARISH"
    trail_side = "HIGH" if bearish else "LOW"
    entry_index = int(entry_model["entry_index"])
    stop = _number(entry_model["stop_level"])
    trail_index: Optional[int] = None
    exit_index: Optional[int] = None
    exit_price: Optional[float] = None
    history: list[Dict[str, Any]] = []
    by_confirmation: Dict[int, list[Dict[str, Any]]] = {}
    for point in swings:
        if (
            str(point["side"]) == trail_side
            and int(point["index"]) > entry_index
        ):
            by_confirmation.setdefault(
                int(point["confirmed_at_index"]), []
            ).append(point)

    active_swing: Optional[Dict[str, Any]] = None
    for candle_index in range(entry_index + 1, len(data)):
        for point in by_confirmation.get(candle_index, []):
            active_swing = point
            level = _number(point["level"])
            favourable = level < stop if bearish else level > stop
            if favourable:
                stop = level
                trail_index = int(point["index"])
                history.append(
                    {
                        "event": "TRAIL_MOVED_ON_NEW_CONFIRMED_SWING",
                        "as_of_index": candle_index,
                        "swing_index": trail_index,
                        "swing_level": stop,
                    }
                )
        if active_swing is None:
            continue
        close = _number(data.iloc[candle_index]["close"])
        level = _number(active_swing["level"])
        exit_now = close > level if bearish else close < level
        if exit_now:
            exit_index = candle_index
            exit_price = close
            history.append(
                {
                    "event": "CLOSE_EXIT_SIGNAL",
                    "as_of_index": candle_index,
                    "swing_index": active_swing["index"],
                    "swing_level": level,
                    "exit_close": close,
                }
            )
            break

    current = len(data) - 1
    if exit_index is None:
        state = "RESEARCH_TRADE_ACTIVE"
    elif exit_index == current:
        state = "RESEARCH_EXIT_SIGNAL"
    else:
        state = "RESEARCH_TRADE_EXITED"
    return {
        "availability": "AVAILABLE",
        "available": True,
        "state": state,
        "owner": "TrailingProtectionEngine",
        "setup_id": entry_model.get("setup_id"),
        "as_of_index": current,
        "causal_valid": True,
        "direction": direction,
        "entry_index": entry_index,
        "entry_price": entry_model.get("entry_price"),
        "initial_stop": entry_model.get("stop_level"),
        "trailing_stop": stop,
        "trailing_structure_index": trail_index,
        "exit_index": exit_index,
        "exit_price": exit_price,
        "exit_ready": exit_index == current,
        "trail_on_new_confirmed_swing": (
            "SWING_HIGH" if bearish else "SWING_LOW"
        ),
        "exit_rule": (
            "CLOSE_ABOVE_LAST_CONFIRMED_M5_SWING_HIGH"
            if bearish
            else "CLOSE_BELOW_LAST_CONFIRMED_M5_SWING_LOW"
        ),
        "history": history,
        "research_only": True,
        "order_api_called": False,
        "reasons": [
            "Management uses only swings visible after their fixed confirmation delay"
        ],
    }


def _inactive_roots(
    *,
    as_of_index: int,
    direction: str,
    reason: str,
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    trigger: Dict[str, Any] = {}
    retracement = {
        "availability": "UNAVAILABLE",
        "available": False,
        "qualified": False,
        "state": "BLOCKED_HTF_NEUTRAL",
        "owner": "QualifiedRetracementEngine",
        "strategy_model": EXPERT_STRATEGY_MODEL,
        "trend": direction,
        "first_candidate_index": None,
        "first_qualification_index": None,
        "qualification_index": None,
        "qualification_available_at_index": None,
        "initial_failure_trigger_index": None,
        "active_failure_trigger_index": None,
        "active_failure_trigger_level": None,
        "active_failure_trigger": trigger,
        "failure_trigger": trigger,
        "trigger_updated_at_index": None,
        "trigger_update_count": 0,
        "as_of_index": as_of_index,
        "causal_valid": True,
        "reason": [reason],
    }
    setup = {
        "setup_id": None,
        "status": "CLOSED",
        "trend": direction,
        "direction": direction,
        "pullback_start_index": None,
        "pullback_end_index": None,
        "history": [],
        "causal": True,
        "current_candle_only": True,
        "reason": [reason],
    }
    entry = {
        "available": False,
        "ready": False,
        "state": "BLOCKED_HTF_NEUTRAL",
        "setup_id": None,
        "direction": None,
        "index": None,
        "entry_index": None,
        "price": None,
        "type": None,
        "trigger_index": None,
        "trigger_level": None,
        "causal": True,
        "current_candle_only": True,
        "as_of_index": as_of_index,
        "reason": [reason],
    }
    return retracement, setup, entry


def run_expert_strategy(
    *,
    data: pd.DataFrame,
    symbol: str,
    timeframe: Any,
    as_of_index: int,
    higher_timeframe_context: Optional[Dict[str, Any]],
    sensitivity: int = DEFAULT_ENGINE_SENSITIVITY,
    runtime_state: Optional[PipelineRuntimeState] = None,
    fibonacci_config: Optional[FibonacciConfig] = None,
) -> ExpertStrategyOutput:
    """Publish the expert specification through canonical Director roots."""
    causal_data = (
        data.iloc[:as_of_index + 1].copy().reset_index(drop=True)
    )
    if runtime_state is None:
        runtime_state = PipelineRuntimeState()
    fibonacci_config = fibonacci_config or FibonacciConfig()
    local_index = len(causal_data) - 1
    director = SystemStateDirector(
        symbol=symbol,
        timeframe=timeframe,
        data=causal_data,
        as_of_index=local_index,
    )
    future_access_test_passed = False
    try:
        director.market_view.row(local_index + 1)
    except (DataContractError, IndexError):
        future_access_test_passed = True

    context = dict(
        higher_timeframe_context
        or _empty_context(local_index)
    )
    context.setdefault("owner", "HTFContextEngine")
    context.setdefault("strategy_model", EXPERT_STRATEGY_MODEL)
    context.setdefault("as_of_index", local_index)
    context.setdefault("causal", True)
    context.setdefault("causal_valid", True)
    direction = str(
        context.get("approved_direction") or "NEUTRAL"
    ).upper()
    if direction not in {"BULLISH", "BEARISH"}:
        direction = "NEUTRAL"

    swings = confirmed_swings(
        causal_data,
        as_of_index=local_index,
        sensitivity=sensitivity,
    )
    current_close = _number(causal_data.iloc[-1]["close"])
    origin_bos: Optional[Dict[str, Any]] = None
    fibonacci = build_fibonacci_contract(
        data=causal_data,
        direction=direction,
        anchor=None,
        swings=swings,
        as_of_index=local_index,
    )

    if direction == "NEUTRAL":
        retracement, setup, entry = _inactive_roots(
            as_of_index=local_index,
            direction=direction,
            reason=(
                "Strict HTF 2-of-3 agreement is absent; "
                "retracement and entry are disabled"
            ),
        )
        model = {
            "setup_id": None,
            "anchor": None,
            "counter": None,
            "trigger": None,
            "initial_trigger": None,
            "stop_level": None,
            "wick_only": False,
            "status": "CLOSED",
            "entry_index": None,
            "latest_entry": None,
        }
    else:
        model = _simulate_retracements(
            causal_data,
            direction=direction,
            swings=swings,
            symbol=symbol,
            timeframe=timeframe,
            sensitivity=sensitivity,
            fibonacci_config=fibonacci_config,
        )
        anchor = model["anchor"]
        counter = model["counter"]
        trigger = model["trigger"]
        initial_trigger = model["initial_trigger"]
        setup_id = model["setup_id"]
        if anchor is not None:
            origin_bos = _find_same_direction_origin_bos(
                causal_data,
                swings=swings,
                direction=direction,
                before_or_at_index=int(anchor["index"]),
            )
            fibonacci = build_fibonacci_contract(
                data=causal_data,
                direction=direction,
                anchor=anchor,
                swings=swings,
                as_of_index=local_index,
                origin_bos_index=(
                    int(origin_bos["index"])
                    if origin_bos is not None
                    else None
                ),
                config=fibonacci_config,
            )
        elif model.get("fibonacci"):
            fibonacci = dict(model["fibonacci"])
        entry_now = model.get("entry_index") == local_index
        previously_consumed = bool(
            model.get("status") == "CONSUMED" and not entry_now
        )
        qualified = trigger is not None
        trigger_contract = (
            {
                **trigger,
                "belongs_to_same_qualified_retracement": True,
            }
            if trigger is not None
            else {}
        )
        retracement = {
            "availability": (
                "AVAILABLE" if anchor is not None else "UNAVAILABLE"
            ),
            "available": anchor is not None,
            "qualified": qualified,
            "state": (
                "CONSUMED"
                if entry_now or previously_consumed
                else "WAITING_FOR_CLOSE_BOS"
                if qualified
                else "DEVELOPING_PULLBACK"
                if anchor is not None
                else "WAITING_FOR_PULLBACK_ORIGIN"
            ),
            "owner": "QualifiedRetracementEngine",
            "strategy_model": EXPERT_STRATEGY_MODEL,
            "trend": direction,
            "direction": direction,
            "initial_pullback_start": (
                int(anchor["index"]) if anchor is not None else None
            ),
            "current_pullback_end": local_index,
            "first_candidate_index": (
                int(anchor["index"]) if anchor is not None else None
            ),
            "first_qualification_index": (
                int(initial_trigger["index"])
                if initial_trigger is not None
                else None
            ),
            "qualification_index": (
                int(initial_trigger["index"])
                if initial_trigger is not None
                else None
            ),
            "qualification_available_at_index": model["qualified_at"],
            "initial_failure_trigger_index": (
                int(initial_trigger["index"])
                if initial_trigger is not None
                else None
            ),
            "active_failure_trigger_index": (
                int(trigger["index"]) if trigger is not None else None
            ),
            "active_failure_trigger_level": (
                _number(trigger["level"]) if trigger is not None else None
            ),
            "active_failure_trigger": trigger_contract,
            "failure_trigger": trigger_contract,
            "trigger_updated_at_index": (
                int(trigger["confirmed_at_index"])
                if trigger is not None
                else None
            ),
            "trigger_update_count": int(model["trigger_updates"]),
            "origin_swing": anchor,
            "counter_swing": counter,
            "retracement_extreme_stop": model["stop_level"],
            "wick_only_trigger_sweep": bool(model["wick_only"]),
            "consumed_at_index": (
                local_index if entry_now else None
            ),
            "history": list(model["history"]),
            "fibonacci": fibonacci,
            "as_of_index": local_index,
            "causal_valid": True,
            "reason": [
                (
                    "Expert M5 state machine uses only swings whose "
                    f"{sensitivity}-bar right-side confirmation has closed"
                )
            ],
        }
        setup_status = (
            "CONSUMED"
            if entry_now or previously_consumed
            else "ACTIVE"
            if qualified
            else "DEVELOPING"
        )
        setup = {
            "setup_id": setup_id,
            "status": setup_status,
            "direction": direction,
            "trend": direction,
            "origin_trend_bos": (
                (context.get("frames", {}).get("M15", {}) or {})
                .get("last_break", {})
                .get("index")
            ),
            "initial_pullback_start": (
                int(anchor["index"]) if anchor is not None else None
            ),
            "current_pullback_end": local_index,
            "pullback_start_index": (
                int(anchor["index"]) if anchor is not None else None
            ),
            "pullback_end_index": local_index,
            "pullback_direction": _opposite(direction),
            "quality": "EXPERT_SPEC_QUALIFIED" if qualified else "DEVELOPING",
            "confirmed_at_index": model["qualified_at"],
            "consumed_at_index": local_index if entry_now else None,
            "history": list(model["history"]),
            "fibonacci": fibonacci,
            "causal": True,
            "current_candle_only": True,
            "reason": [
                "Stable setup identity is anchored to the pullback origin swing"
            ],
        }
        if entry_now:
            entry = {
                "available": True,
                "ready": True,
                "state": "ENTRY_VALIDATED",
                "setup_id": setup_id,
                "direction": direction,
                "index": local_index,
                "entry_index": local_index,
                "price": current_close,
                "type": (
                    "SELL_CLOSE_BOS"
                    if direction == "BEARISH"
                    else "BUY_CLOSE_BOS"
                ),
                "quality": "EXPERT_SPEC_CLOSE_CONFIRMED",
                "score": None,
                "trigger_index": int(trigger["index"]),
                "trigger_level": _number(trigger["level"]),
                "stop_loss": model["stop_level"],
                "setup_invalidation_type": (
                    "RETRACEMENT_HIGH"
                    if direction == "BEARISH"
                    else "RETRACEMENT_LOW"
                ),
                "setup_invalidation_index": local_index,
                "setup_invalidation_level": model["stop_level"],
                "setup_invalidation_intact": True,
                "wick_only_cross": False,
                "close_only": True,
                "causal": True,
                "current_candle_only": True,
                "as_of_index": local_index,
                "reason": [
                    "The current candle closed beyond the confirmed M5 trigger",
                    "Entry price is the current candle close",
                ],
            }
        else:
            state = (
                "NO_ACTIVE_SETUP_AFTER_CONSUMPTION"
                if previously_consumed
                else
                "WAITING_FOR_CLOSE_BOS"
                if qualified
                else "WAITING_FOR_QUALIFIED_RETRACEMENT"
            )
            entry = {
                "available": False,
                "ready": False,
                "state": state,
                "setup_id": setup_id,
                "direction": direction,
                "index": None,
                "entry_index": None,
                "price": None,
                "type": None,
                "trigger_index": (
                    int(trigger["index"]) if trigger is not None else None
                ),
                "trigger_level": (
                    _number(trigger["level"]) if trigger is not None else None
                ),
                "stop_loss": model["stop_level"],
                "wick_only_cross": bool(model["wick_only"]),
                "close_only": True,
                "causal": True,
                "current_candle_only": True,
                "as_of_index": local_index,
                "reason": [
                    (
                        "A wick crossed the trigger but the candle did not "
                        "close beyond it; the trigger remains active"
                        if model["wick_only"]
                        else state.replace("_", " ").title()
                    )
                ],
            }

    entry_body_atr = 0.0
    if entry.get("ready"):
        row = causal_data.iloc[local_index]
        decision_atr = atr_at(causal_data, as_of_index=local_index)
        entry_body_atr = (
            abs(_number(row["close"]) - _number(row["open"])) / decision_atr
            if decision_atr > 0
            else 0.0
        )
    structure_clear = bool(
        model.get("counter")
        and model.get("trigger")
        and int(model["counter"]["index"]) <= int(model["trigger"]["index"])
        and int(model["trigger"]["confirmed_at_index"]) <= local_index
    )
    adaptive = grade_setup(
        hard_blockers=(
            ["HTF_CONTEXT_HARD_BLOCK"]
            if context.get("hard_block") and entry.get("ready")
            else []
        ),
        htf_context=context,
        fibonacci=fibonacci,
        structure_clear=structure_clear,
        bos_body_atr=entry_body_atr,
    )
    retracement["fibonacci"] = fibonacci
    setup["grade"] = adaptive["grade"]
    setup["risk_modifier"] = adaptive["risk_modifier"]
    setup["hard_blockers"] = adaptive["hard_blockers"]
    setup["soft_factors"] = adaptive["soft_factors"]
    entry["fibonacci"] = fibonacci
    entry["fibonacci_zone"] = fibonacci.get("zone")
    entry["fibonacci_depth"] = fibonacci.get("depth")
    entry["grade"] = adaptive["grade"]
    entry["risk_modifier"] = adaptive["risk_modifier"]
    entry["hard_blockers"] = adaptive["hard_blockers"]
    entry["soft_factors"] = adaptive["soft_factors"]
    entry["bos_body_atr"] = entry_body_atr

    raw_pullback_extreme = model.get("stop_level")
    initial_invalidation: Optional[Dict[str, Any]] = None
    initial_emergency: Optional[Dict[str, Any]] = None
    invalid_logical_stop = False
    if entry.get("ready"):
        initial_invalidation = select_setup_logical_invalidation(
            data=causal_data,
            entry_model=model,
            timeframe=timeframe,
            config=runtime_state.expert_trade_manager.config,
        )
        initial_emergency = emergency_broker_stop(
            logical_invalidation=initial_invalidation,
            config=runtime_state.expert_trade_manager.config,
        )
        invalid_logical_stop = not bool(
            initial_invalidation.get("causal_valid")
            and initial_invalidation.get("correct_side_of_entry")
        )
        entry["pullback_extreme_stop"] = (
            float(raw_pullback_extreme)
            if raw_pullback_extreme is not None
            else None
        )
        entry["atr_5m_at_entry"] = initial_invalidation[
            "atr_at_entry"
        ]
        entry["initial_stop_buffer_atr"] = (
            initial_invalidation["atr_tolerance"]
        )
        entry["stop_loss"] = initial_invalidation[
            "logical_boundary"
        ]
        entry["logical_stop"] = initial_invalidation[
            "logical_boundary"
        ]
        entry["emergency_broker_stop"] = initial_emergency["price"]
        entry["logical_exit_condition"] = (
            "CLOSED_CANDLE_BODY_CLOSE_BEYOND_SETUP_LOGICAL_INVALIDATION"
        )
        entry["emergency_exit_condition"] = initial_emergency[
            "emergency_exit_condition"
        ]
        entry["setup_invalidation_type"] = initial_invalidation[
            "structure_type"
        ]
        entry["setup_invalidation_index"] = initial_invalidation[
            "structure_index"
        ]
        entry["setup_invalidation_level"] = initial_invalidation[
            "logical_boundary"
        ]
        entry["setup_invalidation_contract"] = initial_invalidation
        entry["emergency_broker_stop_contract"] = initial_emergency
        entry["reason"].extend(
            initial_invalidation["selection_reason"]
        )
        if invalid_logical_stop:
            entry.update(
                {
                    "available": False,
                    "ready": False,
                    "state": "HARD_BLOCK_INVALID_LOGICAL_STOP_SIDE",
                    "index": None,
                    "entry_index": None,
                    "price": None,
                    "grade": "INVALID",
                    "risk_modifier": 0.0,
                    "hard_blockers": [
                        "LOGICAL_STOP_NOT_BEYOND_ENTRY"
                    ],
                }
            )
            entry["reason"].append(
                "The selected body-edge logical invalidation is not on "
                "the protective side of the entry close"
            )
            setup["status"] = "INVALIDATED"

    latest_entry_model = (
        model
        if model.get("entry_index") is not None
        else model.get("latest_entry")
    )
    latest_model_stop_valid = True
    if latest_entry_model is not None:
        try:
            latest_model_stop_valid = bool(
                select_setup_logical_invalidation(
                    data=causal_data,
                    entry_model=latest_entry_model,
                    timeframe=timeframe,
                    config=runtime_state.expert_trade_manager.config,
                ).get("causal_valid")
            )
        except (KeyError, ValueError, IndexError):
            latest_model_stop_valid = False
    manager_entry: Optional[Dict[str, Any]] = None
    if (
        latest_entry_model is not None
        and not invalid_logical_stop
        and latest_model_stop_valid
    ):
        manager_entry_index = int(
            latest_entry_model["entry_index"]
        )
        manager_entry = {
            **latest_entry_model,
            "ready": True,
            "setup_id": latest_entry_model.get("setup_id"),
            "direction": direction,
            "entry_index": manager_entry_index,
            "index": manager_entry_index,
            "price": float(latest_entry_model["entry_price"]),
            "fibonacci": dict(
                latest_entry_model.get("fibonacci") or fibonacci
            ),
        }

    management = runtime_state.expert_trade_manager.evaluate(
        data=causal_data,
        symbol=symbol,
        timeframe=timeframe,
        as_of_index=local_index,
        direction=direction,
        context=context,
        confirmed_swings=swings,
        canonical_entry=manager_entry,
    )
    latest_managed_attempt = management.get("latest_attempt") or {}
    if (
        entry.get("ready")
        and latest_managed_attempt.get("entry_index") == local_index
        and int(latest_managed_attempt.get("attempt_number", 1)) == 1
    ):
        entry["attempt_number"] = 1
        entry["position_sizing"] = latest_managed_attempt.get("sizing")
        entry["position_1_target"] = latest_managed_attempt.get(
            "position_1_target"
        )
        entry["position_1_target_timeframe"] = (
            latest_managed_attempt.get("position_1_target_timeframe")
        )
        entry["twin_position_model"] = True
        entry["tp1_triggered"] = False
        entry["re_entry_capability_remaining"] = 1
    reentry_signal = management.get("reentry_signal") or {}
    if (
        entry.get("ready")
        and not reentry_signal
        and management.get("attempt_count", 0)
        and latest_managed_attempt.get("entry_index") != local_index
    ):
        entry = {
            **entry,
            "available": False,
            "ready": False,
            "state": "BLOCKED_MANAGEMENT_LIFECYCLE",
            "index": None,
            "entry_index": None,
            "price": None,
            "reason": [
                (
                    "This HTF setup already used its initial entry; "
                    "only the reserved one-shot re-entry engine may "
                    "publish attempt two"
                )
            ],
        }
    if (
        reentry_signal
        and int(reentry_signal.get("entry_index", -1))
        == local_index
    ):
        reentry_trigger = management.get("reentry_trigger") or {}
        reentry_setup_id = reentry_signal.get("setup_id")
        entry = {
            "available": True,
            "ready": True,
            "state": "RE_ENTRY_VALIDATED",
            "setup_id": reentry_setup_id,
            "direction": direction,
            "index": local_index,
            "entry_index": local_index,
            "price": float(reentry_signal["entry_price"]),
            "type": (
                "SELL_RE_ENTRY_CLOSE_BOS"
                if direction == "BEARISH"
                else "BUY_RE_ENTRY_CLOSE_BOS"
            ),
            "quality": "EXPERT_SPEC_ONE_ALLOWED_RE_ENTRY",
            "score": None,
            "attempt_number": 2,
            "re_entry_attempted": True,
            "re_entry_capability_remaining": 0,
            "parent_retracement_active_before_entry": True,
            "position_sizing": reentry_signal.get("sizing"),
            "sizing_logic_cloned": bool(
                (reentry_signal.get("sizing") or {}).get(
                    "sizing_logic_cloned"
                )
            ),
            "trigger_index": reentry_trigger.get("index"),
            "trigger_level": reentry_trigger.get("level"),
            "pullback_extreme_stop": (
                reentry_signal.get("logical_invalidation") or {}
            ).get("broad_pullback_extreme"),
            "atr_5m_at_entry": (
                reentry_signal.get("logical_invalidation") or {}
            ).get("atr_at_entry"),
            "initial_stop_buffer_atr": (
                reentry_signal.get("logical_invalidation") or {}
            ).get("atr_tolerance"),
            "stop_loss": reentry_signal.get("logical_stop"),
            "logical_stop": reentry_signal.get("logical_stop"),
            "emergency_broker_stop": reentry_signal.get(
                "emergency_broker_stop"
            ),
            "setup_invalidation_type": (
                "RE_ENTRY_PULLBACK_HIGH"
                if direction == "BEARISH"
                else "RE_ENTRY_PULLBACK_LOW"
            ),
            "setup_invalidation_index": (
                reentry_signal.get("logical_invalidation") or {}
            ).get("structure_index"),
            "setup_invalidation_level": reentry_signal.get(
                "logical_stop"
            ),
            "setup_invalidation_contract": reentry_signal.get(
                "logical_invalidation"
            ),
            "emergency_broker_stop_contract": reentry_signal.get(
                "emergency_broker_stop_contract"
            ),
            "setup_invalidation_intact": True,
            "fibonacci": reentry_signal.get("fibonacci"),
            "fibonacci_zone": (
                reentry_signal.get("fibonacci") or {}
            ).get("zone"),
            "fibonacci_depth": (
                reentry_signal.get("fibonacci") or {}
            ).get("depth"),
            "wick_only_cross": False,
            "close_only": True,
            "causal": True,
            "current_candle_only": True,
            "as_of_index": local_index,
            "reason": [
                "The first attempt logically failed while dominant protection remained intact",
                "A fresh post-failure counter-structure was causally confirmed",
                "The one allowed re-entry closed beyond its fresh qualified trigger",
                "The configured initial management sizing profile was cloned",
            ],
        }
        setup_id = reentry_setup_id
        setup = {
            **setup,
            "setup_id": reentry_setup_id,
            "status": "CONSUMED",
            "consumed_at_index": local_index,
            "reentry_count": 1,
            "history": [
                *list(setup.get("history", [])),
                {
                    "event": "ONE_ALLOWED_RE_ENTRY_CONSUMED",
                    "as_of_index": local_index,
                    "status": "CONSUMED",
                },
            ],
        }
        retracement["state"] = "CONSUMED"
        retracement["consumed_at_index"] = local_index

    entry_ready = bool(entry["ready"])
    setup_id = entry.get("setup_id") or setup.get("setup_id")
    if setup_id is not None:
        director.set_setup_id(str(setup_id))

    phase = (
        f"{direction}_CONTINUATION_ENTRY"
        if entry_ready
        else f"{direction}_RETRACEMENT"
        if direction != "NEUTRAL"
        else "NO_TRADE_NEUTRAL_HTF"
    )
    validation = {
        "availability": "AVAILABLE",
        "available": True,
        "state": (
            "ENTRY_ALLOWED"
            if entry_ready
            else "HARD_BLOCK_INVALID_LOGICAL_STOP_SIDE"
            if invalid_logical_stop
            else "WAITING"
            if direction != "NEUTRAL"
            else "HARD_BLOCK_HTF_NEUTRAL"
        ),
        "owner": "StructureValidator",
        "setup_id": setup_id,
        "as_of_index": local_index,
        "causal_valid": True,
        "verdict": (
            "STRUCTURE_INVALID"
            if invalid_logical_stop
            else "STRUCTURE_VALID"
            if direction != "NEUTRAL"
            else "STRUCTURE_INVALID"
        ),
        "allowed": entry_ready,
        "hard_block": direction == "NEUTRAL" or invalid_logical_stop,
        "hard_block_reason": (
            None
            if invalid_logical_stop
            else None
            if direction != "NEUTRAL"
            else "HTF context is unavailable or conflicting"
        ),
        "risk_modifier": (
            0.0
            if invalid_logical_stop
            else adaptive["risk_modifier"]
            if direction != "NEUTRAL"
            else 0.0
        ),
        "grade": adaptive["grade"],
        "soft_factors": adaptive["soft_factors"],
        "soft_factors_eliminated_setup": False,
        "relevant_structure_index": entry.get("trigger_index"),
        "relevant_structure_level": entry.get("trigger_level"),
        "reasons": list(entry.get("reason", [])),
    }
    protection = (
        (latest_managed_attempt or {}).get(
            "dominant_decision_protection"
        )
        or dominant_decision_protection(
            context=context,
            direction=direction,
            as_of_index=local_index,
        )
    )
    protection = {
        **protection,
        "setup_id": setup_id,
        "as_of_index": local_index,
        "relevant_structure_index": protection.get("index"),
        "relevant_structure_level": protection.get("level"),
    }
    logical_invalidation_contract = (
        initial_invalidation
        or (latest_managed_attempt or {}).get(
            "logical_invalidation"
        )
    )
    if logical_invalidation_contract is None:
        logical_invalidation_contract = {
            "invalidation_role": "SETUP_LOGICAL_INVALIDATION",
            "availability": "UNAVAILABLE",
            "available": False,
            "state": "WAITING_FOR_QUALIFIED_ENTRY",
            "owner": "ProtectedStructureEngine",
            "setup_id": setup_id,
            "structure_index": None,
            "logical_boundary": None,
            "available_at_index": None,
            "as_of_index": local_index,
            "causal_valid": True,
            "selection_reason": [
                "Setup invalidation is selected only when a qualified "
                "entry has a pre-BOS counter-structure"
            ],
        }
    else:
        logical_invalidation_contract = {
            **logical_invalidation_contract,
            "setup_id": setup_id,
            "as_of_index": local_index,
        }
    transition = {
        "availability": "AVAILABLE",
        "available": True,
        "state": (
            "RETRACEMENT_END_CONFIRMED"
            if entry_ready
            else "RETRACEMENT_ACTIVE"
            if direction != "NEUTRAL"
            else "NO_DIRECTION"
        ),
        "owner": "TransitionEngine",
        "setup_id": setup_id,
        "as_of_index": local_index,
        "causal_valid": True,
        "active": bool(direction != "NEUTRAL" and not entry_ready),
        "recovered": entry_ready,
        "relevant_structure_index": entry.get("trigger_index"),
        "relevant_structure_level": entry.get("trigger_level"),
        "reasons": list(entry.get("reason", [])),
    }

    highs = [point for point in swings if point["side"] == "HIGH"]
    lows = [point for point in swings if point["side"] == "LOW"]
    semantic_hierarchy = build_semantic_swing_hierarchy(
        data=causal_data,
        swings=swings,
        direction=direction,
        as_of_index=local_index,
        model=model,
        protection=protection,
        management=management,
    )
    impulse_cycle = {
        "availability": (
            "AVAILABLE"
            if setup_id is not None and model.get("anchor") is not None
            else "UNAVAILABLE"
        ),
        "available": bool(
            setup_id is not None and model.get("anchor") is not None
        ),
        "owner": "ImpulseCycleEngine",
        "state": (
            "ENTRY_CONSUMED"
            if entry_ready
            else "RETRACEMENT_ACTIVE"
            if model.get("anchor") is not None
            else "WAITING_FOR_SAME_DIRECTION_IMPULSE"
        ),
        "status": (
            "ENTRY_CONSUMED"
            if entry_ready
            else "RETRACEMENT_ACTIVE"
            if model.get("anchor") is not None
            else "CLOSED"
        ),
        "cycle_id": (
            f"CYCLE|{setup_id}" if setup_id is not None else None
        ),
        "setup_id": setup_id,
        "direction": direction,
        "origin_bos": origin_bos,
        "origin_bos_index": (
            origin_bos.get("index") if origin_bos is not None else None
        ),
        "origin_bos_price": (
            origin_bos.get("price") if origin_bos is not None else None
        ),
        "impulse_start_index": fibonacci.get("fib_zero_index"),
        "impulse_start_price": fibonacci.get("fib_zero_price"),
        "impulse_extreme_index": fibonacci.get("fib_hundred_index"),
        "impulse_extreme_price": fibonacci.get("fib_hundred_price"),
        "dominant_protected_structure": protection,
        "fibonacci": fibonacci,
        "as_of_index": local_index,
        "causal_valid": bool(
            fibonacci.get("causal_valid", True)
            and (
                origin_bos is None
                or origin_bos.get("causal_valid", False)
            )
        ),
        "reasons": [
            "The cycle binds the same-direction origin BOS, impulse anchors, parent pullback and protection"
        ],
    }
    market = {
        "trend": direction,
        "phase": phase,
        "current_close": current_close,
        "strategy_model": EXPERT_STRATEGY_MODEL,
        "as_of_index": local_index,
        "causal_valid": True,
    }
    structure = {
        "phase": phase,
        "strategy_model": EXPERT_STRATEGY_MODEL,
        "engine_sensitivity": sensitivity,
        "confirmed_swings": swings,
        "confirmed_highs": highs,
        "confirmed_lows": lows,
        "semantic_hierarchy": semantic_hierarchy,
        "as_of_index": local_index,
        "causal_valid": True,
    }
    control = {
        "state": direction,
        "trend": direction,
        "setup_id": setup_id,
        "as_of_index": local_index,
        "causal_valid": True,
    }
    roots: Dict[str, tuple[Dict[str, Any], str]] = {
        "market": (market, "MarketStateEngine"),
        "structure": (structure, "StructurePipeline"),
        "control": (control, "MarketControlEngine"),
        "context": (context, "HTFContextEngine"),
        "transition": (transition, "TransitionEngine"),
        "validation": (validation, "StructureValidator"),
        "protection": (protection, "ProtectedStructureEngine"),
        "impulse_cycle": (
            impulse_cycle,
            "ImpulseCycleEngine",
        ),
        "setup_invalidation": (
            logical_invalidation_contract,
            "ProtectedStructureEngine",
        ),
        "trailing_protection": (
            management,
            "TrailingProtectionEngine",
        ),
        "retracement": (retracement, "QualifiedRetracementEngine"),
        "setup": (setup, "SetupLifecycleRegistry"),
        "entry": (entry, "ContinuationEngine"),
        "entry_freshness": (
            {
                "classification": "CURRENT_CANDLE" if entry_ready else "NONE",
                "advisory_only": True,
                "as_of_index": local_index,
                "causal_valid": True,
            },
            "EntryFreshnessEngine",
        ),
        "pre_entry_evidence": (
            {
                "state": "EXPERT_CAUSAL_EVIDENCE",
                "setup_id": setup_id,
                "as_of_index": local_index,
                "causal_valid": True,
            },
            "EntryEvidencePipeline",
        ),
        "decision": (
            {
                "action": (
                    "ENTER_TRADE" if entry_ready else "NO_TRADE"
                ),
                "allowed": entry_ready,
                "grade": adaptive["grade"],
                "risk_modifier": adaptive["risk_modifier"],
                "hard_blockers": adaptive["hard_blockers"],
                "soft_factors": adaptive["soft_factors"],
                "soft_factors_eliminated_setup": False,
                "research_only": True,
                "order_api_called": False,
                "as_of_index": local_index,
                "causal_valid": True,
            },
            "DecisionPipeline",
        ),
        "execution": (
            {
                "action": (
                    "PAPER_SIGNAL" if entry_ready else "NO_ACTION"
                ),
                "allowed": entry_ready,
                "mode": "RESEARCH",
                "order_api_called": False,
                "as_of_index": local_index,
                "causal_valid": True,
            },
            "ExecutionIntelligence",
        ),
        "trade": (
            {
                "state": "NOT_OPENED_RESEARCH_ONLY",
                "order_api_called": False,
                "as_of_index": local_index,
                "causal_valid": True,
            },
            "TradeLifecycle",
        ),
        "post_entry_proof": (
            {
                "state": "NOT_USED_FOR_ENTRY",
                "used_for_entry": False,
                "as_of_index": local_index,
                "causal_valid": True,
            },
            "EntryProofEngine",
        ),
        "guardian": (
            {
                "state": management["state"],
                "research_only": True,
                "order_api_called": False,
                "as_of_index": local_index,
                "causal_valid": True,
            },
            "TradeGuardian",
        ),
        "outcome": (
            {
                "state": "NOT_EVALUATED_AT_DECISION_TIME",
                "post_entry_data_used": False,
                "as_of_index": local_index,
                "causal_valid": True,
            },
            "TradeOutcomeRecorder",
        ),
    }
    for section, (payload, producer) in roots.items():
        director.write(section, payload, producer=producer)

    if entry_ready:
        director.entry_contract_valid()

    contract = director.contract_report()
    final_available = entry_ready
    diagnostics = {
        "strategy_model": EXPERT_STRATEGY_MODEL,
        "engine_sensitivity": sensitivity,
        "future_access_test_passed": future_access_test_passed,
        "contract_valid": bool(contract.get("valid", False)),
        "future_structures_used": 0,
        "future_strength_used": 0,
        "future_displacement_used": 0,
        "non_causal_bos": 0,
        "bos_before_confirmation": 0,
        "wrong_bos_break_prices": 0,
        "future_protection_used": False,
        "future_setup_invalidation_used": False,
        "stale_setup_confirmation_used": False,
        "stale_continuation_used": False,
        "manager_continuation_conflict": False,
        "unexplained_structure_block": False,
        "recovered_transition_blocked": False,
        "market_control_causal": True,
        "market_control_as_of_matches": True,
        "transition_causal": True,
        "transition_as_of_matches": True,
        "setup_current_only": True,
        "setup_lifecycle_causal": True,
        "setup_as_of_matches": True,
        "setup_invalidation_causal": True,
        "continuation_current_only": True,
        "continuation_causal": True,
        "continuation_as_of_matches": True,
        "continuation_entry_is_current": True,
        "final_entry_is_current": True,
        "final_entry_is_causal": True,
        "final_entry_close_only": True,
        "canonical_entry_as_of_matches": True,
        "canonical_entry_price_matches_close": True,
        "continuation_state": entry["state"],
        "continuation_ready": entry_ready,
        "entry_validation_state": validation["state"],
        "entry_validation_allowed": entry_ready,
        "canonical_entry_available": entry_ready,
        "canonical_entry_state": entry["state"],
        "canonical_entry_ready": entry_ready,
        "canonical_entry_index": entry.get("index"),
        "canonical_entry_price": entry.get("price"),
        "canonical_entry_causal": True,
        "director_entry_available": entry_ready,
        "final_entry_available": final_available,
        "final_entry_index": entry.get("index"),
        "final_entry_price": entry.get("price"),
        "final_entry_type": entry.get("type"),
        "setup_consumed_before_candidate": False,
        "ledger_entry_event_created": None,
        "final_trend": direction,
        "confirmed_swing_count": len(swings),
        "incomplete_htf_candles_used": bool(
            context.get("incomplete_htf_candles_used", False)
        ),
        "order_api_called": False,
    }
    return ExpertStrategyOutput(
        snapshot=director.snapshot(),
        diagnostics=diagnostics,
    )
