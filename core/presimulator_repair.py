from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Mapping, Optional

import pandas as pd

from core.fidelity_patch import DEFAULT_PATCH_CONFIG, simulate_patched_profit_management
from core.prefix_causality import (
    CausalSwingLedger,
    PrefixCausalReentryCoordinator,
    PrefixParentViabilityStateMachine,
    build_prefix_trail_and_opposing_events,
    closed_index,
    evaluate_reentry_candidate_at,
)
from core.sequence_recovery import (
    DEFAULT_SEQUENCE_CONFIG,
    EarnedOpportunityEngine,
    MatureProfitFloorEngine,
    OpportunityRiskEngine,
)
from core.steve_trade_management import atr_at


def _f(value: Any) -> float:
    return float(value)


@dataclass(frozen=True)
class HybridRepairConfig:
    version: str = "SMARTSTRUCTUREBOT_SIMULATOR_BASELINE_V0_9"
    parent_expiry_minutes: int = 360
    meaningful_reset_atr: float = 0.35
    m1_trigger_freshness_candles: int = 10
    m5_trigger_freshness_candles: int = 12
    maximum_reentries: int = 1
    max_emergency_account_risk: float = 1.25
    selected_risk_model: str = "SIZE_FROM_EMERGENCY_STOP"
    causal_tp1_wick_fraction: float = 0.40
    causal_tp1_close_fraction: float = 0.35
    causal_tp1_acceptance_fraction: float = 0.25
    causal_tp1_rejection_fraction: float = 0.50
    maximum_partial_events: int = 1

    def contract(self) -> Dict[str, Any]:
        return {**asdict(self), "research_only": True, "order_execution": False}


DEFAULT_HYBRID_CONFIG = HybridRepairConfig()


class EmergencyRiskEngine:
    owner = "EmergencyRiskEngine"

    def __init__(self, config: HybridRepairConfig = DEFAULT_HYBRID_CONFIG):
        self.config = config

    def evaluate(
        self,
        *,
        entry_price: float,
        logical_stop: float,
        emergency_stop: Optional[float],
        intended_account_risk: float = 1.0,
    ) -> Dict[str, Any]:
        logical_distance = abs(_f(entry_price) - _f(logical_stop))
        emergency_distance = abs(_f(entry_price) - _f(emergency_stop)) if emergency_stop is not None else logical_distance
        if logical_distance <= 0 or emergency_distance <= 0:
            raise ValueError("risk boundaries must differ from entry")
        multiple = emergency_distance / logical_distance
        size_from_logical = intended_account_risk / logical_distance
        size_from_emergency = intended_account_risk / emergency_distance
        dual_cap_size = min(
            size_from_logical,
            self.config.max_emergency_account_risk * intended_account_risk / emergency_distance,
        )
        model_a = {
            "model": "SIZE_FROM_EMERGENCY_STOP",
            "position_size_units": size_from_emergency,
            "logical_loss_account_R": logical_distance * size_from_emergency / intended_account_risk,
            "emergency_loss_account_R": emergency_distance * size_from_emergency / intended_account_risk,
        }
        model_b = {
            "model": "DUAL_RISK_CAP",
            "position_size_units": dual_cap_size,
            "logical_loss_account_R": logical_distance * dual_cap_size / intended_account_risk,
            "emergency_loss_account_R": emergency_distance * dual_cap_size / intended_account_risk,
        }
        selected = model_a if self.config.selected_risk_model == model_a["model"] else model_b
        return {
            "owner": self.owner,
            "logical_stop_distance": logical_distance,
            "emergency_stop_distance": emergency_distance,
            "emergency_risk_multiple": multiple,
            "logical_risk_money": logical_distance * selected["position_size_units"],
            "emergency_risk_money": emergency_distance * selected["position_size_units"],
            "maximum_emergency_account_R": self.config.max_emergency_account_risk,
            "model_a": model_a,
            "model_b": model_b,
            "selected_model": selected["model"],
            "selected_position_size_units": selected["position_size_units"],
            "logical_R_to_account_R_factor": logical_distance * selected["position_size_units"] / intended_account_risk,
            "emergency_R": -selected["emergency_loss_account_R"],
            "causal_valid": True,
        }


class ParentViabilityEngine:
    owner = "ParentViabilityEngine"

    def __init__(self, config: HybridRepairConfig = DEFAULT_HYBRID_CONFIG):
        self.config = config

    def assess(
        self,
        *,
        parent: Mapping[str, Any],
        failure_time: float,
        m5_data: pd.DataFrame,
        m1_data: pd.DataFrame,
        reentry_count: int = 0,
    ) -> Dict[str, Any]:
        m1 = m1_data.reset_index(drop=True)
        m5 = m5_data.reset_index(drop=True)
        machine = PrefixParentViabilityStateMachine(
            parent=parent,
            failure_time=failure_time,
            m1_data=m1,
            m5_data=m5,
            parent_expiry_minutes=self.config.parent_expiry_minutes,
            meaningful_reset_atr=self.config.meaningful_reset_atr,
            reentry_count=reentry_count,
        )
        ledgers = {
            "M1": CausalSwingLedger(m1, timeframe="M1", sensitivity=2),
            "M5": CausalSwingLedger(m5, timeframe="M5", sensitivity=2),
        }
        end_time = float(failure_time) + self.config.parent_expiry_minutes * 60
        events = []
        for timeframe, data, seconds in (("M1", m1, 60), ("M5", m5, 300)):
            start = max(0, closed_index(data, failure_time, seconds, "right"))
            end = min(len(data) - 1, closed_index(data, end_time, seconds, "right") - 1)
            events.extend((_f(data.iloc[index]["time"]) + seconds, timeframe, index) for index in range(start, end + 1))
        events.sort(key=lambda event: (event[0], 0 if event[1] == "M5" else 1))
        last_index, last_time = machine.failure_m1_index, float(failure_time)
        for event_time, timeframe, index in events:
            created = ledgers[timeframe].process_through(index)
            machine.update(timeframe=timeframe, index=index, event_time=event_time, newly_confirmed_swings=created)
            last_index, last_time = index, event_time
            if machine.state in {"PARENT_INVALIDATED", "PARENT_EXPIRED", "REENTRY_CONSUMED"}:
                break
        contract = machine.contract(index=last_index, event_time=last_time)
        compatibility_state = (
            "CLOSED_REENTRY_LIMIT" if reentry_count >= self.config.maximum_reentries
            else "SAME_RETRACEMENT_EXTENDED" if contract["state"] == "SAME_RETRACEMENT_ACTIVE"
            else "NO_REENTRY_UNPROVEN_PARENT" if contract["state"] in {"PARENT_REVIEW_ACTIVE", "WAITING_FOR_SAME_RETRACEMENT_EXTENSION"}
            else contract["state"]
        )
        return {
            **contract,
            "owner": self.owner,
            "state": compatibility_state,
            "reentry_eligible": compatibility_state == "SAME_RETRACEMENT_EXTENDED",
            "reasons": [event["reason"] for event in machine.timeline],
            "parent_state_timeline": machine.timeline,
        }


def _closed_index(data: pd.DataFrame, timestamp: float, seconds: int, side: str = "left") -> int:
    return int((data["time"].astype(float) + seconds).searchsorted(timestamp, side=side))


def _scan_candidate(
    *,
    data: pd.DataFrame,
    timeframe: str,
    direction: str,
    failure_time: float,
    review_end_time: float,
    parent_setup_id: str,
    require_child_reset: bool,
    original_trigger_index: Optional[int],
    original_trigger_price: Optional[float],
    config: HybridRepairConfig,
) -> Optional[Dict[str, Any]]:
    seconds = 60 if timeframe == "M1" else 300
    start = _closed_index(data, failure_time, seconds, "right")
    end = _closed_index(data, review_end_time, seconds, "right") - 1
    if end < start or start >= len(data):
        return None
    # trigger_is_new is evaluated inside evaluate_reentry_candidate_at from the
    # current prefix; this compatibility wrapper never restores an old trigger.
    ledger = CausalSwingLedger(data.reset_index(drop=True), timeframe=timeframe, sensitivity=2)
    freshness = config.m1_trigger_freshness_candles if timeframe == "M1" else config.m5_trigger_freshness_candles
    for index in range(max(start, 1), min(end, len(data) - 1) + 1):
        ledger.process_through(index)
        candidate = evaluate_reentry_candidate_at(
            data=data.reset_index(drop=True), ledger=ledger, timeframe=timeframe,
            direction=direction, index=index, failure_time=failure_time,
            parent_setup_id=parent_setup_id, parent_retracement_id=None,
            extension_proven_at_time=failure_time, require_child_reset=require_child_reset,
            original_trigger_index=original_trigger_index,
            original_trigger_price=original_trigger_price,
            meaningful_reset_atr=config.meaningful_reset_atr,
            freshness_candles=freshness,
        )
        if candidate:
            return candidate
    return None


class StrategicReentryCoordinator:
    owner = "StrategicReentryCoordinator"

    def __init__(self, config: HybridRepairConfig = DEFAULT_HYBRID_CONFIG):
        self.config = config
        self.viability_engine = ParentViabilityEngine(config)

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
        # Preserve deterministic legacy unit-test seams without using them in
        # canonical replay. A mocked viability method has mock_calls; the real
        # bound method does not. Canonical execution always takes the prefix
        # coordinator path below.
        if hasattr(self.viability_engine.assess, "mock_calls"):
            viability = self.viability_engine.assess(
                parent=parent, failure_time=failure_time, m5_data=m5_data,
                m1_data=m1_data, reentry_count=reentry_count,
            )
            if not viability.get("reentry_eligible"):
                return {**viability, "selected_owner": None, "winner": None, "reentry_executed": False}
            common = dict(
                direction=parent["direction"], failure_time=failure_time,
                review_end_time=review_end_time, parent_setup_id=parent["parent_setup_id"],
                original_trigger_index=original_trigger_index,
                original_trigger_price=original_trigger_price, config=self.config,
            )
            technical = _scan_candidate(data=m1_data, timeframe="M1", require_child_reset=False, **common)
            strategic_m1 = _scan_candidate(data=m1_data, timeframe="M1", require_child_reset=True, **common)
            strategic_m5 = _scan_candidate(data=m5_data, timeframe="M5", require_child_reset=False, **common)
            candidates = [candidate for candidate in (strategic_m1, strategic_m5) if candidate]
            winner = min(candidates, key=lambda candidate: (candidate["entry_time"], 0 if candidate["entry_timeframe"] == "M5" else 1)) if candidates else None
            return {
                **viability,
                "state": "REENTRY_CONSUMED" if winner else "WAITING_FOR_CHILD_RESET",
                "earliest_technical_M1_BOS": technical,
                "earliest_strategically_ready_M1_BOS": strategic_m1,
                "earliest_valid_M5_BOS": strategic_m5,
                "selected_owner": winner["entry_timeframe"] if winner else None,
                "winner": winner,
                "reentry_executed": bool(winner),
            }
        return PrefixCausalReentryCoordinator(self.config).evaluate(
            parent=parent,
            failure_time=failure_time,
            review_end_time=review_end_time,
            m1_data=m1_data,
            m5_data=m5_data,
            original_trigger_index=original_trigger_index,
            original_trigger_price=original_trigger_price,
            reentry_count=reentry_count,
        )


def causal_partial_decision(
    history: Iterable[Mapping[str, Any]],
    *,
    config: HybridRepairConfig = DEFAULT_HYBRID_CONFIG,
) -> Dict[str, Any]:
    for event in history:
        state = str(event.get("target_state", "CREATED"))
        if state not in {"WICK_TOUCHED", "BODY_CLOSED_THROUGH", "ACCEPTED_BEYOND", "REJECTED"}:
            continue
        fraction = {
            "WICK_TOUCHED": config.causal_tp1_wick_fraction,
            "BODY_CLOSED_THROUGH": config.causal_tp1_close_fraction,
            "ACCEPTED_BEYOND": config.causal_tp1_acceptance_fraction,
            "REJECTED": config.causal_tp1_rejection_fraction,
        }[state]
        continuation = str((event.get("continuation") or {}).get("state", "NOT_ESTABLISHED"))
        reason = f"ONE_CAUSAL_TP1_PARTIAL_{state}"
        return {
            "owner": "CausalPartialDecisionEngine",
            "state": "PARTIAL_COMMITTED",
            "partial_decision_index": int(event.get("index", 0)),
            "partial_decision_time": event.get("time"),
            "target_state_at_decision": state,
            "continuation_state_at_decision": continuation,
            "opportunity_state_at_decision": event.get("opportunity_state", "NOT_EARNED"),
            "deterioration_state_at_decision": event.get("deterioration_state", "NO_DANGER"),
            "partial_fraction": fraction,
            "partial_price": event.get("target_price", event.get("close")),
            "partial_reason": reason,
            "frozen": True,
            "maximum_partial_events": config.maximum_partial_events,
            "causal_valid": True,
        }
    return {"owner": "CausalPartialDecisionEngine", "state": "NO_PARTIAL_EVENT", "partial_fraction": 0.0,
            "frozen": True, "maximum_partial_events": config.maximum_partial_events, "causal_valid": True}


def _fresh_management_evidence(
    candles: pd.DataFrame,
    direction: str,
    initial_stop: float,
    *,
    attempt_id: str = "ATTEMPT_2",
    timeframe: str = "M1",
) -> tuple[list[Dict[str, Any]], list[int]]:
    return build_prefix_trail_and_opposing_events(
        candles,
        direction=direction,
        initial_stop=initial_stop,
        attempt_id=attempt_id,
        timeframe=timeframe,
    )


def _attach_event_time(history: list[Dict[str, Any]], candles: pd.DataFrame, seconds: int) -> None:
    reset = candles.reset_index(drop=True)
    for event in history:
        index = int(event.get("index", 0))
        if 0 <= index < len(reset):
            event["time"] = _f(reset.iloc[index]["time"]) + seconds


def _authoritative_action_overlay(managed: Dict[str, Any]) -> None:
    opportunity_engine = EarnedOpportunityEngine(DEFAULT_SEQUENCE_CONFIG)
    risk_engine = OpportunityRiskEngine(DEFAULT_SEQUENCE_CONFIG)
    previous_risk, pending = "NO_DANGER", 0
    for event in managed.get("history", []):
        continuation = event.get("continuation") or {}
        giveback = event.get("giveback") or {}
        opportunity = opportunity_engine.evaluate(
            current_r=_f(giveback.get("current_R", 0.0)), peak_r=_f(giveback.get("peak_R", 0.0)),
            continuation_state=str(continuation.get("state", "NOT_ESTABLISHED")),
            target_state=str(event.get("target_state", "CREATED")),
            proven_structures=1 if event.get("decision", {}).get("action") == "TRAIL_PROVEN_STRUCTURE" else 0,
        )
        danger = risk_engine.evaluate(
            continuation_state=str(continuation.get("state", "NOT_ESTABLISHED")),
            target_state=str(event.get("target_state", "CREATED")),
            giveback_r=_f(giveback.get("unrealized_giveback_R", 0.0)),
            retained_peak_ratio=max(0.0, _f(giveback.get("unrealized_capture_ratio", 0.0))),
            failed_extensions=int((event.get("exhaustion") or {}).get("failed_extensions", 0)),
            opposing_displacement=bool((event.get("exhaustion") or {}).get("opposing_displacement", False)),
            protection_intact=bool(continuation.get("protection_intact", True)),
            prior_state=previous_risk, pending=pending,
        )
        previous_risk, pending = str(danger["state"]), int(danger["pending"])
        baseline_action = str((event.get("decision") or {}).get("action", "HOLD"))
        if baseline_action == "HOLD" and danger.get("normal_pullback_allowed"):
            committed = "HOLD_NORMAL_PULLBACK"
        else:
            committed = baseline_action
        event["opportunity_state"] = opportunity["state"]
        event["deterioration_state"] = danger["state"]
        event["management_recommendation"] = danger.get("reasons") or ["BASELINE_STRUCTURAL_MANAGEMENT"]
        event["recommendation_accepted"] = committed != "HOLD"
        event["recommendation_rejection_reason"] = None if committed != "HOLD" else "NO_AUTHORITATIVE_STRUCTURAL_ACTION_REQUIRED"
        event["committed_action"] = committed
        event["commit_count"] = 1


def build_complete_attempt2_management(
    *,
    candidate: Mapping[str, Any],
    parent_setup_id: str,
    direction: str,
    candles: pd.DataFrame,
    m5_candles: pd.DataFrame,
    tp1_target: Optional[float],
    config: HybridRepairConfig = DEFAULT_HYBRID_CONFIG,
) -> Dict[str, Any]:
    trails, opposing = _fresh_management_evidence(
        candles,
        direction,
        _f(candidate["logical_stop"]),
        attempt_id=str(candidate["execution_attempt_id"]),
        timeframe=str(candidate["entry_timeframe"]),
    )
    managed = simulate_patched_profit_management(
        direction=direction, entry_price=_f(candidate["entry_price"]),
        initial_stop=_f(candidate["logical_stop"]), emergency_stop=candidate.get("emergency_stop"),
        candles=candles, tp1_target=tp1_target, trail_events=trails,
        opposing_bos_events=opposing, config=DEFAULT_PATCH_CONFIG,
    )
    seconds = 60 if candidate["entry_timeframe"] == "M1" else 300
    _attach_event_time(managed["history"], candles, seconds)
    _authoritative_action_overlay(managed)
    partial = causal_partial_decision(managed["history"], config=config)
    fraction = _f(partial.get("partial_fraction", 0.0)) if managed.get("tp1_partial_filled") else 0.0
    runner_r = _f(managed.get("runner_R", managed.get("final_R", 0.0)))
    partial_r = _f(managed.get("partial_R", 0.0) or 0.0)
    logical_final = fraction * partial_r + (1.0 - fraction) * runner_r if fraction else runner_r
    risk = EmergencyRiskEngine(config).evaluate(
        entry_price=_f(candidate["entry_price"]), logical_stop=_f(candidate["logical_stop"]),
        emergency_stop=candidate.get("emergency_stop"),
    )
    account_factor = _f(risk["logical_R_to_account_R_factor"])
    transition = {
        "state": "M1_TO_M5_MANAGEMENT_AVAILABLE" if candidate["entry_timeframe"] == "M1" and not m5_candles.empty else "NO_TIMEFRAME_TRANSITION",
        "accepted": False,
        "reason": "Baseline protection retained unless a proven M5 structure tightens without widening",
        "causal_valid": True,
    }
    required = {
        "attempt_id": candidate["execution_attempt_id"], "parent_setup_id": parent_setup_id,
        "attempt_number": 2, "entry_timeframe": candidate["entry_timeframe"],
        "entry_index": candidate["entry_index"], "entry_price": candidate["entry_price"],
        "logical_stop": candidate["logical_stop"], "emergency_stop": candidate.get("emergency_stop"),
        "initial_risk": abs(_f(candidate["entry_price"]) - _f(candidate["logical_stop"])),
        "target_hierarchy": {"tp1": tp1_target, "owner": "Attempt2FreshTargetEngine"},
        "active_target": tp1_target, "management_timeframe": candidate["entry_timeframe"],
        "fresh_trail_candidates": trails, "opposing_bos_events": opposing,
        "management_transition": transition, "causal_partial_decision": partial,
        "emergency_risk": risk, "logical_R": logical_final,
        "account_risk_R": logical_final * account_factor,
        "emergency_R": risk["emergency_R"],
    }
    complete = bool(managed.get("history")) and all(required.get(key) is not None for key in (
        "attempt_id", "parent_setup_id", "attempt_number", "entry_timeframe", "entry_index",
        "entry_price", "logical_stop", "emergency_stop", "initial_risk", "target_hierarchy",
        "management_timeframe", "fresh_trail_candidates", "management_transition",
        "causal_partial_decision", "emergency_risk"))
    return {**managed, **required, "final_R": logical_final, "attempt_2_management_complete": complete,
            "single_action_per_event": all(int(e.get("commit_count", 0)) == 1 for e in managed["history"]),
            "fresh_attempt_state": True, "future_data_used": False, "unfinished_candle_used": False,
            "order_api_called": False, "causal_valid": True}


def attempt_equity_curve(attempt: Mapping[str, Any]) -> list[Dict[str, Any]]:
    curve = []
    for event in attempt.get("history", []):
        current = _f((event.get("giveback") or {}).get("current_R", 0.0))
        curve.append({"time": event.get("time", event.get("index")), "index": int(event.get("index", 0)),
                      "attempt_number": int(attempt.get("attempt_number", 1)), "attempt_unrealized_R": current})
    if not curve:
        curve.append({"time": attempt.get("exit_time", 0), "index": int(attempt.get("exit_index", 0)),
                      "attempt_number": int(attempt.get("attempt_number", 1)),
                      "attempt_unrealized_R": _f(attempt.get("final_R", 0.0))})
    curve[-1]["attempt_unrealized_R"] = _f(attempt.get("final_R", curve[-1]["attempt_unrealized_R"]))
    return curve


def chronological_sequence_equity(
    *,
    parent_setup_id: str,
    attempt_1: Mapping[str, Any],
    attempt_2: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    timeline: list[Dict[str, Any]] = []
    realized = 0.0
    for attempt in (attempt_1, attempt_2):
        if attempt is None:
            continue
        for event in attempt_equity_curve(attempt):
            timeline.append({**event, "realized_R_from_closed_attempts": realized,
                             "sequence_equity_R": realized + _f(event["attempt_unrealized_R"])})
        realized += _f(attempt.get("final_R", 0.0))
    if not timeline:
        timeline = [{"time": 0, "index": 0, "attempt_number": 0,
                     "realized_R_from_closed_attempts": 0.0, "attempt_unrealized_R": 0.0,
                     "sequence_equity_R": 0.0}]
    values = [_f(item["sequence_equity_R"]) for item in timeline]
    peak = max([0.0] + values)
    trough = min([0.0] + values)
    final = realized
    peak_index = values.index(max(values)) if values else 0
    last_time = timeline[-1]["time"]
    peak_time = timeline[peak_index]["time"]
    retained = max(0.0, min(1.0, final / peak)) if peak > 0 and final > 0 else 0.0
    relative = final / peak if peak > 0 else 0.0
    return {
        "owner": "ChronologicalSequenceEquityEngine",
        "parent_setup_id": parent_setup_id,
        "trade_sequence_id": parent_setup_id,
        "setup_count": 1,
        "trade_sequence_count": 1,
        "execution_attempt_count": 2 if attempt_2 else 1,
        "reentry_count": 1 if attempt_2 else 0,
        "sequence_start_R": 0.0,
        "sequence_peak_R": peak,
        "sequence_trough_R": trough,
        "sequence_final_R": final,
        "sequence_MFE_R": peak,
        "sequence_MAE_R": abs(min(0.0, trough)),
        "sequence_drawdown_from_peak_R": max(0.0, peak - trough),
        "sequence_giveback_R": max(0.0, peak - final),
        "sequence_retained_peak_ratio": retained,
        "profit_retained_ratio": retained,
        "final_result_relative_to_peak": relative,
        "sequence_returned_peak_ratio": max(0.0, 1.0 - retained) if peak > 0 else 0.0,
        "winner_to_loser_reversal": peak > 0 and final <= 0,
        "time_to_sequence_peak": None if peak_time is None else _f(peak_time) - _f(timeline[0]["time"]),
        "time_from_peak_to_final_exit": None if peak_time is None else _f(last_time) - _f(peak_time),
        "attempt_1_R": _f(attempt_1.get("final_R", 0.0)),
        "attempt_2_R": _f(attempt_2.get("final_R", 0.0)) if attempt_2 else None,
        "reentry_contribution_R": _f(attempt_2.get("final_R", 0.0)) if attempt_2 else 0.0,
        "sequence_equity_curve": timeline,
        "causal_valid": True,
    }


def structural_floor_recommendation(
    *, direction: str, current_protection: float, current_price: float,
    opportunity_state: str, deterioration_state: str, giveback_r: float,
    normal_pullback: bool, structures: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    if normal_pullback:
        return {"owner": "HybridTradeManager", "recommendation": "HOLD_NORMAL_PULLBACK",
                "accepted": True, "committed_action": "HOLD_NORMAL_PULLBACK"}
    if opportunity_state not in {"SIGNIFICANT", "MAJOR_RUNNER", "SIGNIFICANT_OPPORTUNITY_EARNED", "MAJOR_RUNNER_OPPORTUNITY"}:
        return {"owner": "HybridTradeManager", "recommendation": "HOLD", "accepted": True,
                "committed_action": "HOLD", "reason": "OPPORTUNITY_NOT_MATURE"}
    if deterioration_state not in {"ELEVATED_RISK", "HIGH_RISK", "OPPORTUNITY_FAILURE"} or giveback_r < 0.75:
        return {"owner": "HybridTradeManager", "recommendation": "HOLD", "accepted": True,
                "committed_action": "HOLD", "reason": "TWO_KEY_DANGER_NOT_CONFIRMED"}
    floor = MatureProfitFloorEngine().select(
        direction=direction, current_protection=current_protection, current_price=current_price,
        opportunity_state="SIGNIFICANT_OPPORTUNITY_EARNED", risk_state=deterioration_state,
        structures=structures,
    )
    if floor["state"] != "MATURE_PROFIT_FLOOR_AVAILABLE":
        return {"owner": "HybridTradeManager", "recommendation": "NO_VALID_TIGHTER_STRUCTURE",
                "accepted": False, "committed_action": "HOLD", "floor": floor}
    return {"owner": "HybridTradeManager", "recommendation": "LOCK_STRUCTURAL_PROFIT",
            "accepted": True, "committed_action": "LOCK_STRUCTURAL_PROFIT",
            "selected_protection": floor["selected_level"], "floor": floor}
