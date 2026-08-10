from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence

import pandas as pd

from core.sequence_recovery import final_invalidation_structure
from core.second_touch_structure import (
    SecondTouchConfig,
    evaluate_second_touch_structure,
    second_touch_logical_boundary,
)
from core.steve_trade_management import atr_at


def _f(value: Any) -> float:
    return float(value)


def _close_time(data: pd.DataFrame, index: int, seconds: int) -> float:
    return _f(data.iloc[int(index)]["time"]) + seconds


def closed_index(data: pd.DataFrame, timestamp: float, seconds: int, side: str = "left") -> int:
    return int((data["time"].astype(float) + seconds).searchsorted(float(timestamp), side=side))


class CausalSwingLedger:
    """Incremental immutable N-left/N-right swing evidence.

    A candle is inspected as a swing candidate only when its Nth right-hand
    candle closes. Classification is frozen at that confirmation event.
    """

    owner = "CausalSwingLedger"

    def __init__(self, data: pd.DataFrame, *, timeframe: str, sensitivity: int = 2, start_index: int = 0):
        if sensitivity <= 0:
            raise ValueError("sensitivity must be positive")
        self.data = data.reset_index(drop=True)
        self.timeframe = str(timeframe).upper()
        self.sensitivity = int(sensitivity)
        self.start_index = max(0, int(start_index))
        self._processed_through = self.start_index - 1
        self._events: list[Dict[str, Any]] = []
        self._last_level: Dict[str, Optional[float]] = {"HIGH": None, "LOW": None}

    @property
    def events(self) -> list[Dict[str, Any]]:
        return [dict(event) for event in self._events]

    def process_through(self, as_of_index: int) -> list[Dict[str, Any]]:
        current = int(as_of_index)
        if current < self._processed_through:
            raise ValueError("causal ledger cannot move backwards")
        if current >= len(self.data):
            raise IndexError("ledger as_of_index is outside the data range")
        created: list[Dict[str, Any]] = []
        for detected_at in range(self._processed_through + 1, current + 1):
            candidate = detected_at - self.sensitivity
            if candidate < max(self.sensitivity, self.start_index + self.sensitivity):
                continue
            left = self.data.iloc[candidate - self.sensitivity : candidate]
            right = self.data.iloc[candidate + 1 : detected_at + 1]
            if len(right) != self.sensitivity:
                continue
            high = _f(self.data.iloc[candidate]["high"])
            low = _f(self.data.iloc[candidate]["low"])
            accepted = (
                ("HIGH", high, bool((high > left["high"].astype(float)).all() and (high > right["high"].astype(float)).all())),
                ("LOW", low, bool((low < left["low"].astype(float)).all() and (low < right["low"].astype(float)).all())),
            )
            for side, price, is_swing in accepted:
                if not is_swing:
                    continue
                prior = self._last_level[side]
                classification = (
                    f"SWING_{side}" if prior is None
                    else "HH" if side == "HIGH" and price > prior
                    else "LH" if side == "HIGH"
                    else "LL" if price < prior
                    else "HL"
                )
                swing_id = f"{self.timeframe}|SWING|{side}|{candidate}|AVAILABLE|{detected_at}"
                event = {
                    "owner": self.owner,
                    "event_type": "SWING_CONFIRMED",
                    "swing_id": swing_id,
                    "structure_id": swing_id,
                    "swing_index": candidate,
                    "index": candidate,
                    "swing_type": f"SWING_{side}",
                    "type": f"SWING_{side}",
                    "side": side,
                    "price": price,
                    "level": price,
                    "detected_at_index": detected_at,
                    "confirmed_at_index": detected_at,
                    "available_at_index": detected_at,
                    "classification_at_confirmation": classification,
                    "classification": classification,
                    "role_at_confirmation": classification,
                    "source_timeframe": self.timeframe,
                    "swing_time": self.data.iloc[candidate].get("time"),
                    "confirmed_at_time": self.data.iloc[detected_at].get("time"),
                    "current_as_of_index": detected_at,
                    "prefix_rows_used": detected_at + 1,
                    "causal_valid": True,
                    "immutable": True,
                }
                self._events.append(event)
                created.append(dict(event))
                self._last_level[side] = price
        self._processed_through = current
        return created

    def visible_at(self, as_of_index: int) -> list[Dict[str, Any]]:
        current = int(as_of_index)
        if current > self._processed_through:
            self.process_through(current)
        return [dict(event) for event in self._events if int(event["available_at_index"]) <= current]


def causal_swings_at(
    data: pd.DataFrame,
    *,
    as_of_index: int,
    timeframe: str,
    sensitivity: int = 2,
) -> list[Dict[str, Any]]:
    ledger = CausalSwingLedger(data, timeframe=timeframe, sensitivity=sensitivity)
    ledger.process_through(int(as_of_index))
    return ledger.visible_at(int(as_of_index))


@dataclass
class ParentFailureSnapshot:
    failure_index: int
    failure_time: float
    failure_price: float
    parent_direction: str
    parent_protection: Optional[float]
    retracement_boundaries_at_failure: Mapping[str, Any]
    fibonacci_anchors: Mapping[str, Any]
    first_attempt_trigger: Mapping[str, Any]
    first_attempt_stop: Optional[float]


class PrefixParentViabilityStateMachine:
    owner = "PrefixParentViabilityStateMachine"

    def __init__(
        self,
        *,
        parent: Mapping[str, Any],
        failure_time: float,
        m1_data: pd.DataFrame,
        m5_data: pd.DataFrame,
        parent_expiry_minutes: int,
        meaningful_reset_atr: float,
        reentry_count: int = 0,
    ):
        self.parent = dict(parent)
        self.failure_time = float(failure_time)
        self.m1 = m1_data.reset_index(drop=True)
        self.m5 = m5_data.reset_index(drop=True)
        self.expiry_time = self.failure_time + int(parent_expiry_minutes) * 60
        self.meaningful_reset_atr = float(meaningful_reset_atr)
        self.direction = str(parent["direction"]).upper()
        self.failure_m1_index = min(max(closed_index(self.m1, self.failure_time, 60, "left"), 0), len(self.m1) - 1)
        self.failure_price = _f(self.m1.iloc[self.failure_m1_index]["close"])
        self.failure_atr = max(atr_at(self.m1.iloc[: self.failure_m1_index + 1], as_of_index=self.failure_m1_index), 1e-12)
        self.counter_side = "LOW" if self.direction == "BULLISH" else "HIGH"
        self.state = "FIRST_ATTEMPT_FAILED"
        self.extension_event: Optional[Dict[str, Any]] = None
        self.timeline: list[Dict[str, Any]] = []
        self.reentry_count = int(reentry_count)
        self.snapshot = ParentFailureSnapshot(
            failure_index=self.failure_m1_index,
            failure_time=self.failure_time,
            failure_price=self.failure_price,
            parent_direction=self.direction,
            parent_protection=parent.get("dominant_protection_level"),
            retracement_boundaries_at_failure=dict(parent.get("retracement_boundaries_at_failure") or {}),
            fibonacci_anchors=dict(parent.get("fibonacci_anchors") or {}),
            first_attempt_trigger={"index": parent.get("first_attempt_trigger_index"), "price": parent.get("first_attempt_trigger_price")},
            first_attempt_stop=parent.get("first_attempt_stop"),
        )
        if self.reentry_count > 0:
            self.state = "REENTRY_CONSUMED"
        elif not bool(parent.get("dominant_protection_intact_at_failure", True)):
            self.state = "PARENT_INVALIDATED"
        else:
            self.state = "PARENT_REVIEW_ACTIVE"
        self._publish(self.failure_m1_index, self.failure_time, "ATTEMPT_1_FAILURE_REVIEW_OPENED")

    def _publish(self, index: int, event_time: float, reason: str, **extra: Any) -> None:
        self.timeline.append({
            "owner": self.owner,
            "state": self.state,
            "event_index": int(index),
            "event_time": float(event_time),
            "reason": reason,
            "parent_setup_id": self.parent.get("parent_setup_id"),
            "retracement_id": self.parent.get("retracement_id"),
            "impulse_cycle_id": self.parent.get("impulse_cycle_id"),
            "extension_proven_at_index": None if self.extension_event is None else self.extension_event["extension_proven_at_index"],
            "extension_proven_at_time": None if self.extension_event is None else self.extension_event["extension_proven_at_time"],
            "prefix_rows_used": int(index) + 1,
            "causal_valid": True,
            **extra,
        })

    def _protection_failed(self, timeframe: str, index: int) -> bool:
        protection = self.parent.get("dominant_protection_level")
        if protection is None or timeframe != "M5":
            return False
        close = _f(self.m5.iloc[int(index)]["close"])
        return close < _f(protection) if self.direction == "BULLISH" else close > _f(protection)

    def update(
        self,
        *,
        timeframe: str,
        index: int,
        event_time: float,
        newly_confirmed_swings: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        timeframe = str(timeframe).upper()
        if self.state in {"PARENT_INVALIDATED", "PARENT_EXPIRED", "REENTRY_CONSUMED", "CLOSED_AFTER_SECOND_FAILURE"}:
            return self.contract(index=index, event_time=event_time)
        if float(event_time) > self.expiry_time:
            self.state = "PARENT_EXPIRED"
            self._publish(index, event_time, "PARENT_REENTRY_WINDOW_EXPIRED")
            return self.contract(index=index, event_time=event_time)
        if self._protection_failed(timeframe, index):
            self.state = "PARENT_INVALIDATED"
            self._publish(index, event_time, "DOMINANT_PROTECTION_BODY_CLOSE_FAILED")
            return self.contract(index=index, event_time=event_time)
        if self.extension_event is None:
            self.state = "WAITING_FOR_SAME_RETRACEMENT_EXTENSION"
            source = self.m1 if timeframe == "M1" else self.m5
            seconds = 60 if timeframe == "M1" else 300
            first_post_failure = closed_index(source, self.failure_time, seconds, "right")
            eligible = [
                swing for swing in newly_confirmed_swings
                if str(swing.get("side")) == self.counter_side
                and float(event_time) > self.failure_time
                and int(swing.get("swing_index", swing.get("index", -1))) >= first_post_failure
            ]
            if eligible:
                structure = eligible[-1]
                distance = (
                    self.failure_price - _f(structure["price"])
                    if self.direction == "BULLISH"
                    else _f(structure["price"]) - self.failure_price
                )
                distance_atr = max(0.0, distance / self.failure_atr)
                structure_evidence = distance > 0
                meaningful = structure_evidence and distance_atr >= self.meaningful_reset_atr
                if meaningful:
                    score = 1.0 + min(2.0, distance_atr) + 1.0
                    self.extension_event = {
                        "extension_status": "SAME_RETRACEMENT_EXTENSION_PROVEN",
                        "extension_score": score,
                        "extension_structure": dict(structure),
                        "extension_structure_id": structure.get("swing_id"),
                        "extension_distance_ATR": distance_atr,
                        "extension_proven_at_index": int(index),
                        "extension_proven_at_time": float(event_time),
                        "extension_available_at": float(event_time),
                        "extension_price": _f(structure["price"]),
                        "extension_reason": "CAUSALLY_CONFIRMED_DEEPER_COUNTER_STRUCTURE_WITH_PROTECTION_INTACT",
                        "parent_still_same_retracement": True,
                        "causal_valid": True,
                    }
                    self.state = "SAME_RETRACEMENT_ACTIVE"
                    self._publish(index, event_time, "SAME_RETRACEMENT_EXTENSION_PROVEN", **self.extension_event)
                else:
                    self._publish(index, event_time, "COUNTER_STRUCTURE_NOT_YET_MEANINGFUL", extension_distance_ATR=distance_atr)
            else:
                self._publish(index, event_time, "NO_REENTRY_YET")
        else:
            self.state = "SAME_RETRACEMENT_ACTIVE"
        return self.contract(index=index, event_time=event_time)

    def consume_reentry(self, *, index: int, event_time: float) -> None:
        self.state = "REENTRY_CONSUMED"
        self.reentry_count = 1
        self._publish(index, event_time, "ATTEMPT_2_OPENED")

    def contract(self, *, index: int, event_time: float) -> Dict[str, Any]:
        event = self.extension_event or {}
        return {
            "owner": self.owner,
            "state": self.state,
            "parent_viability_state": self.state,
            "reentry_eligible": self.state == "SAME_RETRACEMENT_ACTIVE",
            "parent_setup_id": self.parent.get("parent_setup_id"),
            "retracement_id": self.parent.get("retracement_id"),
            "impulse_cycle_id": self.parent.get("impulse_cycle_id"),
            "dominant_protection": self.parent.get("dominant_protection_level"),
            "dominant_protection_intact": self.state != "PARENT_INVALIDATED",
            "extension_status": event.get("extension_status", "WAITING_FOR_SAME_RETRACEMENT_EXTENSION"),
            "extension_score": event.get("extension_score", 0.0),
            "extension_structure": event.get("extension_structure"),
            "extension_distance_ATR": event.get("extension_distance_ATR"),
            "extension_proven_at_index": event.get("extension_proven_at_index"),
            "extension_proven_at_time": event.get("extension_proven_at_time"),
            "extension_available_at": event.get("extension_available_at"),
            "parent_still_same_retracement": bool(event),
            "parent_viability_reason": self.timeline[-1]["reason"] if self.timeline else "FIRST_ATTEMPT_FAILED",
            "failure_snapshot": self.snapshot.__dict__.copy(),
            "current_as_of_index": int(index),
            "as_of_time": float(event_time),
            "prefix_rows_used": int(index) + 1,
            "causal_valid": True,
        }


def evaluate_reentry_candidate_at(
    *,
    data: pd.DataFrame,
    ledger: CausalSwingLedger,
    timeframe: str,
    direction: str,
    index: int,
    failure_time: float,
    parent_setup_id: str,
    parent_retracement_id: Optional[str],
    extension_proven_at_time: Optional[float],
    require_child_reset: bool,
    original_trigger_index: Optional[int],
    original_trigger_price: Optional[float],
    meaningful_reset_atr: float,
    freshness_candles: int,
    second_touch_enabled: bool = False,
    second_touch_config: SecondTouchConfig = SecondTouchConfig(),
) -> Optional[Dict[str, Any]]:
    timeframe = str(timeframe).upper()
    seconds = 60 if timeframe == "M1" else 300
    current = int(index)
    event_time = _close_time(data, current, seconds)
    start = closed_index(data, failure_time, seconds, "right")
    if current < max(start, 1):
        return None
    visible = ledger.visible_at(current)
    trigger_side = "HIGH" if str(direction).upper() == "BULLISH" else "LOW"
    counter_side = "LOW" if str(direction).upper() == "BULLISH" else "HIGH"
    triggers = [event for event in visible if event["side"] == trigger_side and start <= int(event["swing_index"]) < current]
    if not triggers:
        return None
    trigger = max(triggers, key=lambda event: int(event["swing_index"]))
    if current - int(trigger["available_at_index"]) > int(freshness_candles):
        return None
    row = data.iloc[current]
    close, opened, previous = _f(row["close"]), _f(row["open"]), _f(data.iloc[current - 1]["close"])
    crossed = (
        close > _f(trigger["price"]) and opened < close and previous <= _f(trigger["price"])
        if str(direction).upper() == "BULLISH"
        else close < _f(trigger["price"]) and opened > close and previous >= _f(trigger["price"])
    )
    if not crossed:
        return None
    second_touch_owner = {
        "parent_setup_id": parent_setup_id,
        "retracement_id": parent_retracement_id,
        "impulse_cycle_id": parent_setup_id,
        "direction": str(direction).upper(),
        "dominant_protection_identity": parent_setup_id,
        "fib_anchor_version": "PARENT_OWNED",
    }
    second_touch = evaluate_second_touch_structure(
        data=data,
        swings=visible,
        direction=direction,
        as_of_index=current,
        setup_start_index=start,
        owner=second_touch_owner,
        expected_owner=second_touch_owner,
        config=second_touch_config,
    )
    if second_touch_enabled and second_touch["state"] == "SECOND_TOUCH_CANDIDATE":
        return None
    second_touch_active = bool(
        second_touch_enabled
        and second_touch["state"] == "SECOND_TOUCH_CONFIRMED"
    )
    if second_touch_active:
        active_trigger = second_touch.get("active_trigger") or {}
        if int(active_trigger.get("swing_index", -1)) != int(trigger["swing_index"]):
            return None
    counters = [event for event in visible if event["side"] == counter_side and start <= int(event["swing_index"]) < current]
    counter = max(counters, key=lambda event: int(event["swing_index"])) if counters else None
    atr = max(atr_at(data.iloc[: current + 1], as_of_index=current), 1e-12)
    reset_displacement = abs(_f(counter["price"]) - _f(trigger["price"])) / atr if counter else 0.0
    trigger_is_new = (
        original_trigger_index is None
        or int(trigger["swing_index"]) != int(original_trigger_index)
        or original_trigger_price is None
        or abs(_f(trigger["price"]) - _f(original_trigger_price)) > 1e-12
    )
    child_reset = bool(counter and trigger_is_new and reset_displacement >= float(meaningful_reset_atr))
    if require_child_reset and not child_reset:
        return None
    if extension_proven_at_time is not None and event_time < float(extension_proven_at_time):
        return None
    if second_touch_active:
        touch_2 = second_touch["touch_2"]
        boundary = second_touch_logical_boundary(
            wick_extreme=_f(touch_2["price"]),
            direction=direction,
            timeframe=timeframe,
            causal_atr=atr,
        )
        logical_stop = boundary["logical_invalidation_boundary"]
        stop = {
            "owner": "SecondTouchStructureEngine",
            "state": "SECOND_TOUCH_WICK_INVALIDATION_STRUCTURE_SELECTED",
            "structure_index": int(touch_2["swing_index"]),
            "confirmed_at_index": int(touch_2["available_at_index"]),
            "structure_wick": boundary["structure_wick"],
            "atr_tolerance": boundary["atr_tolerance"],
            "logical_invalidation_boundary": logical_stop,
            "selection_method": "SECOND_TOUCH_WICK_EXTREME",
            "causal_valid": int(touch_2["available_at_index"]) <= current,
        }
    else:
        try:
            stop = final_invalidation_structure(
                data=data.iloc[: current + 1],
                direction=direction,
                entry_index=current,
                setup_start_index=max(start - 2, 0),
                timeframe=timeframe,
            )
        except ValueError:
            return None
        logical_stop = _f(stop["logical_invalidation_boundary"])
    if not (logical_stop < close if str(direction).upper() == "BULLISH" else logical_stop > close):
        return None
    return {
        "owner": "PrefixCausalReentryCoordinator",
        "state": "M1_REENTRY_CANDIDATE" if timeframe == "M1" else "M5_REENTRY_CANDIDATE",
        "parent_setup_id": parent_setup_id,
        "parent_retracement_id": parent_retracement_id,
        "trade_sequence_id": parent_setup_id,
        "execution_attempt_id": f"{parent_setup_id}|ATTEMPT|2|{timeframe}|{current}",
        "attempt_number": 2,
        "entry_timeframe": timeframe,
        "candidate_index": current,
        "candidate_time": event_time,
        "entry_index": current,
        "entry_time": event_time,
        "entry_price": close,
        "child_cycle_id": None if counter is None else counter["swing_id"],
        "trigger_id": trigger["swing_id"],
        "trigger_index": int(trigger["swing_index"]),
        "trigger_available_at": int(trigger["available_at_index"]),
        "trigger_price": _f(trigger["price"]),
        "reentry_trigger_index": int(trigger["swing_index"]),
        "reentry_trigger_time": _close_time(data, int(trigger["swing_index"]), seconds),
        "reentry_trigger_price": _f(trigger["price"]),
        "new_counter_structure": counter,
        "child_reset_detected": child_reset,
        "child_reset_proven_at": None if counter is None else int(counter["available_at_index"]),
        "child_reset_start": start if child_reset else None,
        "difference_from_attempt_1_trigger": None if original_trigger_price is None else _f(trigger["price"]) - _f(original_trigger_price),
        "reentry_structure_reason": "FRESH_M1_CHILD_RESET" if timeframe == "M1" and child_reset else "VALID_PARENT_M5_CONTINUATION_CONFIRMATION" if timeframe == "M5" else "TECHNICAL_M1_RECROSS_ONLY",
        "logical_stop": logical_stop,
        "emergency_stop": logical_stop - atr if str(direction).upper() == "BULLISH" else logical_stop + atr,
        "stop_structure": stop,
        "current_as_of_index": current,
        "prefix_rows_used": current + 1,
        "parent_extension_proven_at": extension_proven_at_time,
        "causal_valid": True,
        "second_touch": second_touch,
        "second_touch_entry": second_touch_active,
        "fresh_second_touch_attempt_2": second_touch_active,
    }


class PrefixCausalReentryCoordinator:
    owner = "PrefixCausalReentryCoordinator"

    def __init__(self, config: Any):
        self.config = config

    def evaluate(
        self,
        *,
        parent: Mapping[str, Any],
        failure_time: float,
        review_end_time: float,
        m1_data: pd.DataFrame,
        m5_data: pd.DataFrame,
        original_trigger_index: Optional[int] = None,
        original_trigger_price: Optional[float] = None,
        reentry_count: int = 0,
    ) -> Dict[str, Any]:
        m1 = m1_data.reset_index(drop=True)
        m5 = m5_data.reset_index(drop=True)
        second_touch_enabled = bool(getattr(self.config, "second_touch_enabled", False))
        second_touch_config = SecondTouchConfig(
            proximity_atr_ratio=float(
                getattr(self.config, "second_touch_proximity_atr_ratio", 0.25)
            ),
            meaningful_reaction_atr_ratio=float(
                getattr(self.config, "second_touch_meaningful_reaction_atr_ratio", 0.35)
            ),
            minimum_separation_bars=int(
                getattr(self.config, "second_touch_minimum_separation_bars", 3)
            ),
        )
        machine = PrefixParentViabilityStateMachine(
            parent={**dict(parent), "first_attempt_trigger_index": original_trigger_index, "first_attempt_trigger_price": original_trigger_price},
            failure_time=failure_time,
            m1_data=m1,
            m5_data=m5,
            parent_expiry_minutes=self.config.parent_expiry_minutes,
            meaningful_reset_atr=self.config.meaningful_reset_atr,
            reentry_count=reentry_count,
        )
        m1_start = max(0, closed_index(m1, failure_time, 60, "right"))
        m5_start = max(0, closed_index(m5, failure_time, 300, "right"))
        m1_ledger = CausalSwingLedger(m1, timeframe="M1", sensitivity=2, start_index=max(0, m1_start - 30))
        m5_ledger = CausalSwingLedger(m5, timeframe="M5", sensitivity=2, start_index=max(0, m5_start - 30))
        events: list[tuple[float, str, int]] = []
        for timeframe, data, seconds, start in (("M1", m1, 60, m1_start), ("M5", m5, 300, m5_start)):
            end = min(len(data) - 1, closed_index(data, review_end_time, seconds, "right") - 1)
            events.extend((_close_time(data, index, seconds), timeframe, index) for index in range(start, end + 1))
        events.sort(key=lambda item: (item[0], 0 if item[1] == "M5" else 1))
        earliest_technical: Optional[Dict[str, Any]] = None
        earliest_m1: Optional[Dict[str, Any]] = None
        earliest_m5: Optional[Dict[str, Any]] = None
        candidate_timeline: list[Dict[str, Any]] = []
        winner: Optional[Dict[str, Any]] = None
        cursor = 0
        while cursor < len(events):
            event_time = events[cursor][0]
            batch: list[tuple[float, str, int]] = []
            while cursor < len(events) and events[cursor][0] == event_time:
                batch.append(events[cursor])
                cursor += 1
            current_candidates: list[Dict[str, Any]] = []
            for _, timeframe, index in batch:
                ledger = m1_ledger if timeframe == "M1" else m5_ledger
                created = ledger.process_through(index)
                snapshot = machine.update(timeframe=timeframe, index=index, event_time=event_time, newly_confirmed_swings=created)
                data = m1 if timeframe == "M1" else m5
                if timeframe == "M1" and earliest_technical is None:
                    earliest_technical = evaluate_reentry_candidate_at(
                        data=data, ledger=ledger, timeframe=timeframe, direction=parent["direction"], index=index,
                        failure_time=failure_time, parent_setup_id=str(parent["parent_setup_id"]),
                        parent_retracement_id=parent.get("retracement_id"), extension_proven_at_time=None,
                        require_child_reset=False, original_trigger_index=original_trigger_index,
                        original_trigger_price=original_trigger_price, meaningful_reset_atr=self.config.meaningful_reset_atr,
                        freshness_candles=self.config.m1_trigger_freshness_candles,
                        second_touch_enabled=second_touch_enabled,
                        second_touch_config=second_touch_config,
                    )
                if snapshot["state"] != "SAME_RETRACEMENT_ACTIVE":
                    candidate_timeline.append({"event_time": event_time, "timeframe": timeframe, "index": index, "parent_state": snapshot["state"], "candidate": None, "reason": "PARENT_EXTENSION_NOT_AVAILABLE"})
                    continue
                candidate = evaluate_reentry_candidate_at(
                    data=data, ledger=ledger, timeframe=timeframe, direction=parent["direction"], index=index,
                    failure_time=failure_time, parent_setup_id=str(parent["parent_setup_id"]),
                    parent_retracement_id=parent.get("retracement_id"), extension_proven_at_time=snapshot["extension_proven_at_time"],
                    require_child_reset=timeframe == "M1", original_trigger_index=original_trigger_index,
                    original_trigger_price=original_trigger_price, meaningful_reset_atr=self.config.meaningful_reset_atr,
                    freshness_candles=self.config.m1_trigger_freshness_candles if timeframe == "M1" else self.config.m5_trigger_freshness_candles,
                    second_touch_enabled=second_touch_enabled,
                    second_touch_config=second_touch_config,
                )
                candidate_timeline.append({"event_time": event_time, "timeframe": timeframe, "index": index, "parent_state": snapshot["state"], "candidate": candidate, "reason": "CURRENT_PREFIX_EVALUATED"})
                if candidate:
                    current_candidates.append(candidate)
                    if timeframe == "M1" and earliest_m1 is None:
                        earliest_m1 = candidate
                    if timeframe == "M5" and earliest_m5 is None:
                        earliest_m5 = candidate
            if current_candidates:
                winner = min(current_candidates, key=lambda candidate: (candidate["candidate_time"], 0 if candidate["entry_timeframe"] == "M5" else 1))
                machine.consume_reentry(index=int(winner["entry_index"]), event_time=float(winner["entry_time"]))
                break
            if machine.state in {"PARENT_INVALIDATED", "PARENT_EXPIRED", "REENTRY_CONSUMED"}:
                break
        final_index = int(events[min(max(cursor - 1, 0), len(events) - 1)][2]) if events else machine.failure_m1_index
        final_time = float(events[min(max(cursor - 1, 0), len(events) - 1)][0]) if events else float(failure_time)
        contract = machine.contract(index=final_index, event_time=final_time)
        cancelled = machine.state in {"PARENT_INVALIDATED", "PARENT_EXPIRED"}
        return {
            **contract,
            "state": "REENTRY_CONSUMED" if winner else "REENTRY_CANCELLED" if cancelled else machine.state,
            "earliest_technical_M1_BOS": earliest_technical,
            "earliest_strategically_ready_M1_BOS": earliest_m1,
            "earliest_valid_M5_BOS": earliest_m5,
            "selected_owner": winner["entry_timeframe"] if winner else None,
            "selection_reason": "FIRST_STRATEGICALLY_READY_BOS_WINS_PARENT_M5_TIE_BREAK" if winner else "NO_STRATEGICALLY_READY_CANDIDATE",
            "winner": winner,
            "reentry_executed": bool(winner),
            "reentry_count": 1 if winner else 0,
            "competing_gates_closed": bool(winner),
            "allow_no_further_attempts": bool(winner),
            "parent_state_timeline": machine.timeline,
            "candidate_timeline": candidate_timeline,
            "m1_swing_ledger": m1_ledger.events,
            "m5_swing_ledger": m5_ledger.events,
            "full_history_swing_contamination": False,
            "retrospective_reentry_restoration": False,
            "order_api_called": False,
            "causal_valid": True,
        }


def build_prefix_trail_and_opposing_events(
    candles: pd.DataFrame,
    *,
    direction: str,
    initial_stop: float,
    attempt_id: str,
    timeframe: str,
) -> tuple[list[Dict[str, Any]], list[int]]:
    data = candles.reset_index(drop=True)
    if data.empty:
        return [], []
    direction = str(direction).upper()
    timeframe = str(timeframe).upper()
    side = "LOW" if direction == "BULLISH" else "HIGH"
    ledger = CausalSwingLedger(data, timeframe=timeframe, sensitivity=2)
    active: list[Dict[str, Any]] = []
    trails: list[Dict[str, Any]] = []
    opposing: list[int] = []
    protection = float(initial_stop)
    committed_structures: set[str] = set()
    for index in range(len(data)):
        created = ledger.process_through(index)
        active.extend(event for event in created if event["side"] == side)
        row = data.iloc[index]
        for candidate in list(active):
            if candidate["swing_id"] in committed_structures or index <= int(candidate["available_at_index"]):
                continue
            candidate_index = int(candidate["swing_index"])
            prior = data.iloc[candidate_index:index]
            if prior.empty:
                continue
            close, opened = _f(row["close"]), _f(row["open"])
            bos = close > _f(prior["high"].max()) and close > opened if direction == "BULLISH" else close < _f(prior["low"].min()) and close < opened
            if not bos:
                continue
            structure_row = data.iloc[candidate_index]
            level = min(_f(structure_row["open"]), _f(structure_row["close"])) if direction == "BULLISH" else max(_f(structure_row["open"]), _f(structure_row["close"]))
            tightens = level > protection if direction == "BULLISH" else level < protection
            correct_side = level < close if direction == "BULLISH" else level > close
            committed_structures.add(candidate["swing_id"])
            if tightens and correct_side:
                event_id = f"{attempt_id}|TRAIL|{timeframe}|{candidate_index}|PROOF|{index}"
                trails.append({
                    "owner": "PrefixCausalTrailLedger",
                    "state": "TRAIL_PROVEN",
                    "trail_event_id": event_id,
                    "attempt_id": attempt_id,
                    "timeframe": timeframe,
                    "structure_id": candidate["swing_id"],
                    "structure_index": candidate_index,
                    "structure_price": level,
                    "structure_role": candidate["role_at_confirmation"],
                    "candidate_index": candidate_index,
                    "candidate_level": level,
                    "candidate_detected_at": int(candidate["detected_at_index"]),
                    "candidate_confirmed_at": int(candidate["confirmed_at_index"]),
                    "proof_bos_index": index,
                    "proof_index": index,
                    "proof_bos_available_at": index,
                    "trail_committed_at": index,
                    "old_protection": protection,
                    "new_protection": level,
                    "selected_protection": level,
                    "available_at_index": index,
                    "current_as_of_index": index,
                    "prefix_rows_used": index + 1,
                    "causal_valid": True,
                    "immutable": True,
                })
                protection = level
        if index >= 2:
            atr = max(atr_at(data.iloc[: index + 1], as_of_index=index), 1e-12)
            body = abs(_f(row["close"]) - _f(row["open"]))
            recent = data.iloc[max(0, index - 8) : index]
            if body / atr >= 0.35 and not recent.empty:
                broken = _f(row["close"]) < _f(recent["low"].min()) and _f(row["close"]) < _f(row["open"]) if direction == "BULLISH" else _f(row["close"]) > _f(recent["high"].max()) and _f(row["close"]) > _f(row["open"])
                if broken:
                    opposing.append(index)
    return trails, opposing


class CausalInvarianceTester:
    owner = "CausalInvarianceTester"

    @staticmethod
    def compare(
        *,
        decision_fn: Callable[[pd.DataFrame, int], Mapping[str, Any]],
        prefix: pd.DataFrame,
        suffixes: Iterable[pd.DataFrame],
        as_of_index: int,
        fields: Iterable[str],
    ) -> Dict[str, Any]:
        current = int(as_of_index)
        reference = dict(decision_fn(prefix.iloc[: current + 1].copy(), current))
        comparisons = []
        failures = []
        for number, suffix in enumerate(suffixes, start=1):
            combined = pd.concat([prefix.iloc[: current + 1], suffix], ignore_index=True)
            result = dict(decision_fn(combined, current))
            changed = [field for field in fields if reference.get(field) != result.get(field)]
            comparisons.append({"suffix_number": number, "rows": len(suffix), "changed_fields": changed})
            failures.extend(changed)
        return {
            "owner": CausalInvarianceTester.owner,
            "as_of_index": current,
            "fields": list(fields),
            "reference": reference,
            "comparisons": comparisons,
            "failures": sorted(set(failures)),
            "suffix_invariant": not failures,
            "causal_valid": not failures,
        }
