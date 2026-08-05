from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Mapping, Optional

import pandas as pd

from core.expert_strategy import confirmed_swings
from core.fidelity_patch import (
    DEFAULT_PATCH_CONFIG,
    simulate_patched_profit_management,
)
from core.steve_trade_management import atr_at


def _f(value: Any) -> float:
    return float(value)


def _body_edge(row: Mapping[str, Any], direction: str) -> float:
    lower = min(_f(row["open"]), _f(row["close"]))
    upper = max(_f(row["open"]), _f(row["close"]))
    return lower if direction == "BULLISH" else upper


def _tightens(direction: str, candidate: float, current: float) -> bool:
    return candidate > current if direction == "BULLISH" else candidate < current


@dataclass(frozen=True)
class SequenceEliteConfig:
    opportunity_emerging_r: float = 0.35
    opportunity_earned_r: float = 0.75
    significant_opportunity_r: float = 1.50
    major_runner_r: float = 3.00
    continuation_proof_minimum: int = 1
    deterioration_hysteresis: int = 2
    target_rejection_weight: float = 25.0
    elevated_giveback_r: float = 0.75
    severe_giveback_r: float = 1.25
    retained_peak_warning_ratio: float = 0.40
    mature_profit_minimum_r: float = 1.50
    dynamic_partial_acceptance: float = 0.25
    dynamic_partial_wick_touch: float = 0.50
    dynamic_partial_rejection: float = 0.65
    partial_profile: str = "DYNAMIC_PARTIAL_PLUS_RUNNER"
    # Re-entry is a new decision, not permission to recycle the first attempt's
    # micro trigger.  Two M5 periods is the causal M1 freshness horizon.
    reentry_freshness_m1_candles: int = 10
    reentry_freshness_m5_candles: int = 12
    competing_trigger_policy: str = "FIRST_VALID_CLOSED_BOS_WINS"
    parent_retracement_expiry_minutes: int = 360
    normal_pullback_max_impulse_ratio: float = 0.50
    m5_atr_tolerance: float = 0.15
    meaningful_swing_atr: float = 0.35
    minimum_close_beyond_trigger_atr: float = 0.30

    def contract(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "version": "FINAL_SEQUENCE_ELITE_V1",
            "research_only": True,
            "order_execution": False,
        }


DEFAULT_SEQUENCE_CONFIG = SequenceEliteConfig()


def final_invalidation_structure(
    *,
    data: pd.DataFrame,
    direction: str,
    entry_index: int,
    setup_start_index: int,
    sensitivity: int = 2,
    timeframe: str = "M5",
    config: SequenceEliteConfig = DEFAULT_SEQUENCE_CONFIG,
) -> Dict[str, Any]:
    """Select the final meaningful pre-entry HL/LH available at entry.

    The published structure body edge is Steve's stop location.  M5's existing
    ATR tolerance is retained as a separate body-close invalidation boundary.
    """
    direction = direction.upper()
    side = "LOW" if direction == "BULLISH" else "HIGH"
    if entry_index <= setup_start_index:
        raise ValueError("entry must follow setup start")
    # Work only inside the causal setup window.  Apart from being materially
    # faster during replay, this prevents an older, unrelated swing from being
    # promoted to the current setup's invalidation structure.
    slice_start = max(0, int(setup_start_index))
    visible = data.iloc[slice_start : entry_index + 1].reset_index(drop=True)
    local_entry_index = entry_index - slice_start
    swings = confirmed_swings(
        visible,
        as_of_index=local_entry_index,
        sensitivity=sensitivity,
    )
    for point in swings:
        point["index"] = int(point["index"]) + slice_start
        point["confirmed_at_index"] = int(
            point.get("confirmed_at_index", point["index"] - slice_start)
        ) + slice_start
    atr = max(atr_at(data.iloc[: entry_index + 1], as_of_index=entry_index), 1e-12)
    eligible = [
        point
        for point in swings
        if point["side"] == side
        and setup_start_index <= int(point["index"]) < entry_index
        and int(point.get("confirmed_at_index", point["index"])) <= entry_index
    ]
    meaningful = []
    for point in eligible:
        idx = int(point["index"])
        left = data.iloc[max(slice_start, idx-3):idx+1]
        if left.empty:
            continue
        local_move = (
            _f(left["high"].max())-_f(point["level"])
            if side == "LOW"
            else _f(point["level"])-_f(left["low"].min())
        )
        if local_move/atr >= config.meaningful_swing_atr:
            meaningful.append(point)
    candidates = meaningful or eligible
    if candidates:
        selected = max(candidates, key=lambda point: int(point["index"]))
        structure_index = int(selected["index"])
        confirmation = int(selected.get("confirmed_at_index", structure_index))
        method = "LAST_CONFIRMED_MEANINGFUL_PRE_ENTRY_SWING"
    else:
        # Entry BOS causally proves the final reaction even when N-right fractal
        # confirmation is not yet available. No post-entry candle is inspected.
        window = data.iloc[max(slice_start, entry_index-12):entry_index]
        if window.empty:
            raise ValueError("no causal pre-entry structure")
        structure_index = (
            int(window["low"].astype(float).idxmin())
            if side == "LOW"
            else int(window["high"].astype(float).idxmax())
        )
        confirmation = entry_index
        method = "ENTRY_BOS_PROVED_FINAL_REACTION_STRUCTURE"
    row = data.iloc[structure_index]
    body_edge = _body_edge(row, direction)
    tolerance = config.m5_atr_tolerance*atr if timeframe.upper() == "M5" else 0.0
    invalidation_boundary = (
        body_edge-tolerance if direction == "BULLISH" else body_edge+tolerance
    )
    entry_price = _f(data.iloc[entry_index]["close"])
    correct_side = invalidation_boundary < entry_price if direction == "BULLISH" else invalidation_boundary > entry_price
    if not correct_side:
        raise ValueError("selected invalidation structure is on wrong side")
    return {
        "owner": "FinalInvalidationStructureSelector",
        "state": "FINAL_PRE_ENTRY_INVALIDATION_STRUCTURE_SELECTED",
        "direction": direction,
        "timeframe": timeframe.upper(),
        "side": side,
        "structure_index": structure_index,
        "structure_time": _f(data.iloc[structure_index]["time"]),
        "confirmed_at_index": confirmation,
        "available_at_entry": confirmation <= entry_index,
        "structure_wick": _f(row["low"] if side == "LOW" else row["high"]),
        "structure_body_edge": body_edge,
        "logical_invalidation_boundary": invalidation_boundary,
        "atr_tolerance": tolerance,
        "selection_method": method,
        "meaningful_candidate_count": len(meaningful),
        "causal_valid": confirmation <= entry_index,
    }


def evaluate_parent_after_first_failure(
    *,
    parent: Mapping[str, Any],
    first_failure_time: float,
    m5_data: pd.DataFrame,
    reentry_count: int = 0,
    config: SequenceEliteConfig = DEFAULT_SEQUENCE_CONFIG,
) -> Dict[str, Any]:
    direction = str(parent["direction"]).upper()
    dominant = _f(parent["dominant_protection_level"])
    visible = m5_data[(m5_data["time"].astype(float)+300 <= first_failure_time)].copy()
    broken = not bool(parent.get("dominant_protection_intact_at_failure", True))
    if not visible.empty and "dominant_protection_intact_at_failure" not in parent:
        if direction == "BULLISH":
            broken = bool(((visible["close"].astype(float) < dominant) & (visible["close"].astype(float) < visible["open"].astype(float))).tail(100).any())
        else:
            broken = bool(((visible["close"].astype(float) > dominant) & (visible["close"].astype(float) > visible["open"].astype(float))).tail(100).any())
    if reentry_count >= 1:
        state, eligible, reason = "PARENT_CLOSED_NO_REENTRY", False, "REENTRY_SLOT_ALREADY_CONSUMED"
    elif broken:
        state, eligible, reason = "PARENT_INVALIDATED_TREND_FAILURE", False, "DOMINANT_M5_PROTECTION_BODY_CLOSE_BROKEN"
    elif visible.empty:
        state, eligible, reason = "PARENT_EXPIRED", False, "NO_CLOSED_M5_CANDLE_INSIDE_REENTRY_WINDOW"
    else:
        state, eligible, reason = "PARENT_RETRACEMENT_STILL_ACTIVE", True, "FIRST_FAILURE_EXTENDED_SAME_RETRACEMENT_WITH_DOMINANT_PROTECTION_INTACT"
    return {
        "owner": "CrossTimeframeReentryCoordinator",
        "state": state,
        "reentry_eligible": eligible,
        "reentry_monitoring": eligible,
        "parent_setup_id": parent["parent_setup_id"],
        "trade_sequence_id": parent["parent_setup_id"],
        "parent_direction": direction,
        "reentry_count": reentry_count,
        "reason": reason,
        "dominant_protection_intact": not broken,
        "as_of_time": first_failure_time,
        "causal_valid": True,
    }


def _scan_timeframe_candidate(
    *,
    data: pd.DataFrame,
    timeframe: str,
    direction: str,
    failure_time: float,
    review_end_time: float,
    parent: Mapping[str, Any],
    config: SequenceEliteConfig,
) -> Optional[Dict[str, Any]]:
    seconds = 60 if timeframe == "M1" else 300
    direction = direction.upper()
    trigger_side = "HIGH" if direction == "BULLISH" else "LOW"
    counter_side = "LOW" if direction == "BULLISH" else "HIGH"
    start = int((data["time"].astype(float)+seconds).searchsorted(failure_time, side="right"))
    end = int((data["time"].astype(float)+seconds).searchsorted(review_end_time, side="right")-1)
    max_age = config.reentry_freshness_m1_candles if timeframe == "M1" else config.reentry_freshness_m5_candles
    if end < max(start,3):
        return None
    # Only the failed-attempt recovery window belongs to this re-entry search.
    # This keeps old market structures out of the candidate set and makes long
    # multi-symbol replays deterministic and quick.
    local_start = max(0, start - 30)
    local = data.iloc[local_start : end + 1].reset_index(drop=True)
    local_end = len(local) - 1
    all_swings = confirmed_swings(
        local,
        as_of_index=local_end,
        sensitivity=2,
    )
    for point in all_swings:
        point["index"] = int(point["index"]) + local_start
        point["confirmed_at_index"] = int(
            point.get("confirmed_at_index", point["index"] - local_start)
        ) + local_start
    for index in range(max(start, 3), min(end, len(data)-1)+1):
        triggers = [p for p in all_swings if p["side"] == trigger_side and int(p.get("confirmed_at_index", p["index"])) <= index and int(p["index"]) < index]
        if not triggers:
            continue
        trigger = max(triggers, key=lambda p:int(p["index"]))
        if index-int(trigger.get("confirmed_at_index", trigger["index"])) > max_age:
            continue
        # A close beyond an isolated micro fractal is not a new continuation
        # setup.  The failed attempt must first produce a fresh, meaningful
        # counter-structure inside the recovery window.  It may print before or
        # after the trigger swing, but it must be confirmed before this entry.
        counters = [
            point for point in all_swings
            if point["side"] == counter_side
            and start <= int(point["index"]) < index
            and int(point.get("confirmed_at_index", point["index"])) <= index
        ]
        if not counters:
            continue
        counter = max(counters, key=lambda point: int(point["index"]))
        row=data.iloc[index]
        close, open_price = _f(row["close"]), _f(row["open"])
        valid = (close > _f(trigger["level"]) and close > open_price) if direction == "BULLISH" else (close < _f(trigger["level"]) and close < open_price)
        if not valid:
            continue
        previous_close = _f(data.iloc[index-1]["close"])
        fresh_cross = (
            previous_close <= _f(trigger["level"])
            if direction == "BULLISH"
            else previous_close >= _f(trigger["level"])
        )
        if not fresh_cross:
            # A trigger crossed before its counter-structure was confirmed is
            # stale evidence; confirmation cannot retroactively create a BOS.
            continue
        atr=max(atr_at(data,as_of_index=index),1e-12)
        counter_displacement = abs(_f(counter["level"])-_f(trigger["level"]))/atr
        body_displacement = abs(close-open_price)/atr
        close_beyond_trigger = (
            close-_f(trigger["level"])
            if direction == "BULLISH"
            else _f(trigger["level"])-close
        )/atr
        if (
            counter_displacement < config.meaningful_swing_atr
            or body_displacement < config.meaningful_swing_atr
        ):
            continue
        structure=final_invalidation_structure(data=data, direction=direction, entry_index=index, setup_start_index=max(start-2,0), timeframe=timeframe, config=config)
        stop=structure["logical_invalidation_boundary"]
        if not ((stop < close) if direction == "BULLISH" else (stop > close)):
            continue
        return {
            "owner":"CrossTimeframeReentryCoordinator",
            "state":"VALID_REENTRY_CANDIDATE",
            "parent_setup_id":parent["parent_setup_id"],
            "trade_sequence_id":parent["parent_setup_id"],
            "execution_attempt_id":f"{parent['parent_setup_id']}|ATTEMPT|2|{timeframe}|{index}",
            "attempt_number":2,
            "entry_timeframe":timeframe,
            "direction":direction,
            "entry_index":index,
            "entry_time":_f(row["time"])+seconds,
            "entry_price":close,
            "reentry_trigger_index":int(trigger["index"]),
            "reentry_trigger_time":_f(data.iloc[int(trigger["index"])]["time"])+seconds,
            "reentry_trigger_price":_f(trigger["level"]),
            "counter_structure_index":int(counter["index"]),
            "counter_structure_time":_f(data.iloc[int(counter["index"])]["time"])+seconds,
            "counter_structure_price":_f(counter["level"]),
            "counter_structure_displacement_atr":counter_displacement,
            "bos_body_displacement_atr":body_displacement,
            "close_beyond_trigger_atr":close_beyond_trigger,
            "quality_factors":[
                "CLEAN_CLOSE_BEYOND_TRIGGER"
                if close_beyond_trigger >= config.minimum_close_beyond_trigger_atr
                else "SHALLOW_CLOSE_BEYOND_TRIGGER"
            ],
            "reentry_available_at":_f(row["time"])+seconds,
            "logical_stop":stop,
            "stop_structure":structure,
            "emergency_stop":stop-atr if direction=="BULLISH" else stop+atr,
            "entry_reason":f"{timeframe}_REENTRY_AFTER_FIRST_FAILURE",
            "fresh_trigger":True,
            "causal_valid":True,
        }
    return None


class CrossTimeframeReentryCoordinator:
    owner="CrossTimeframeReentryCoordinator"
    def __init__(self,config:SequenceEliteConfig=DEFAULT_SEQUENCE_CONFIG): self.config=config

    def evaluate(self,*,parent:Mapping[str,Any],first_failure_time:float,review_end_time:float,m1_data:pd.DataFrame,m5_data:pd.DataFrame,reentry_count:int=0)->Dict[str,Any]:
        viability=evaluate_parent_after_first_failure(parent=parent,first_failure_time=first_failure_time,m5_data=m5_data,reentry_count=reentry_count,config=self.config)
        if not viability["reentry_eligible"]:
            return {**viability,"competing_M1_candidate":None,"competing_M5_candidate":None,"winner":None,"reentry_executed":False}
        kwargs=dict(direction=parent["direction"],failure_time=first_failure_time,review_end_time=review_end_time,parent=parent,config=self.config)
        m1=_scan_timeframe_candidate(data=m1_data,timeframe="M1",**kwargs)
        m5=_scan_timeframe_candidate(data=m5_data,timeframe="M5",**kwargs)
        def intact(candidate:Optional[Mapping[str,Any]])->bool:
            if candidate is None: return False
            end=float(candidate["entry_time"]); direction=str(parent["direction"]).upper(); level=_f(parent["dominant_protection_level"])
            window=m5_data[(m5_data["time"].astype(float)+300>first_failure_time)&(m5_data["time"].astype(float)+300<=end)]
            if direction=="BULLISH": return not bool(((window["close"].astype(float)<level)&(window["close"].astype(float)<window["open"].astype(float))).any())
            return not bool(((window["close"].astype(float)>level)&(window["close"].astype(float)>window["open"].astype(float))).any())
        if m1 is not None and not intact(m1): m1=None
        if m5 is not None and not intact(m5): m5=None
        available=[candidate for candidate in (m1,m5) if candidate is not None]
        winner=min(available,key=lambda c:(float(c["entry_time"]),0 if c["entry_timeframe"]=="M1" else 1)) if available else None
        return {
            **viability,
            "state":"REENTRY_CONSUMED" if winner else "REENTRY_NOT_FOUND",
            "competing_M1_candidate":m1,
            "competing_M5_candidate":m5,
            "winner":winner,
            "reentry_executed":winner is not None,
            "reentry_owner_timeframe":winner["entry_timeframe"] if winner else None,
            "winning_candidate_reason":"FIRST_VALID_CLOSED_BOS_WINS" if winner else None,
            "competing_gate_closed":winner is not None,
            "reentry_count":1 if winner else 0,
            "allow_no_further_attempts":winner is not None,
            "order_api_called":False,
        }


class EarnedOpportunityEngine:
    owner="EarnedOpportunityEngine"
    def __init__(self,config:SequenceEliteConfig=DEFAULT_SEQUENCE_CONFIG): self.config=config
    def evaluate(self,*,current_r:float,peak_r:float,continuation_state:str,target_state:str,proven_structures:int=0)->Dict[str,Any]:
        structural=proven_structures>=self.config.continuation_proof_minimum or continuation_state in {"HEALTHY_CONTINUATION","STRONG_CONTINUATION"}
        target=target_state in {"WICK_TOUCHED","BODY_CLOSED_THROUGH","ACCEPTED_BEYOND","EXTENDED"}
        if peak_r>=self.config.major_runner_r or target_state in {"ACCEPTED_BEYOND","EXTENDED"} or proven_structures>=2: state="MAJOR_RUNNER_OPPORTUNITY"
        elif peak_r>=self.config.significant_opportunity_r and structural: state="SIGNIFICANT_OPPORTUNITY_EARNED"
        elif (peak_r>=self.config.opportunity_earned_r and structural) or target: state="OPPORTUNITY_EARNED"
        elif peak_r>=self.config.opportunity_emerging_r or structural: state="OPPORTUNITY_EMERGING"
        else: state="NOT_EARNED"
        return {"owner":self.owner,"state":state,"current_R":current_r,"peak_R":peak_r,"structural_progress":structural,"target_progress":target,"supporting_only":True,"causal_valid":True}


class OpportunityRiskEngine:
    owner="OpportunityRiskEngine"
    def __init__(self,config:SequenceEliteConfig=DEFAULT_SEQUENCE_CONFIG): self.config=config
    def evaluate(self,*,continuation_state:str,target_state:str,giveback_r:float,retained_peak_ratio:float,failed_extensions:int,opposing_displacement:bool,protection_intact:bool,prior_state:str="NO_DANGER",pending:int=0)->Dict[str,Any]:
        score=min(30,failed_extensions*8)+(self.config.target_rejection_weight if target_state=="REJECTED" else 0)+(20 if continuation_state in {"EXHAUSTION_WARNING","CONTINUATION_FAILED"} else 10 if continuation_state=="WEAKENING_CONTINUATION" else 0)+(20 if opposing_displacement else 0)+(20 if giveback_r>=self.config.severe_giveback_r else 10 if giveback_r>=self.config.elevated_giveback_r else 0)+(15 if retained_peak_ratio<self.config.retained_peak_warning_ratio else 0)
        if continuation_state in {"HEALTHY_CONTINUATION","STRONG_CONTINUATION"} and protection_intact: score=min(score,24)
        raw="OPPORTUNITY_FAILURE" if score>=80 else "HIGH_RISK" if score>=65 else "ELEVATED_RISK" if score>=45 else "WATCH" if score>=25 else "NO_DANGER"
        state=raw
        next_pending=0
        if raw!=prior_state and raw not in {"OPPORTUNITY_FAILURE"}:
            next_pending=pending+1
            if next_pending<self.config.deterioration_hysteresis: state=prior_state
            else: next_pending=0
        return {"owner":self.owner,"state":state,"raw_state":raw,"risk_score":score,"pending":next_pending,"normal_pullback_allowed":state in {"NO_DANGER","WATCH"} and protection_intact and continuation_state in {"HEALTHY_CONTINUATION","STRONG_CONTINUATION"},"reasons":[reason for condition,reason in [(target_state=="REJECTED","TARGET_REJECTION"),(failed_extensions>=2,"FAILED_EXTENSION"),(opposing_displacement,"OPPOSING_DISPLACEMENT"),(giveback_r>=self.config.elevated_giveback_r,"ELEVATED_GIVEBACK"),(protection_intact,"PROVEN_PROTECTION_INTACT")] if condition],"supporting_only":True,"causal_valid":True}


class MatureProfitFloorEngine:
    owner="MatureProfitFloorEngine"
    def select(self,*,direction:str,current_protection:float,current_price:float,opportunity_state:str,risk_state:str,structures:Iterable[Mapping[str,Any]])->Dict[str,Any]:
        mature=opportunity_state in {"SIGNIFICANT_OPPORTUNITY_EARNED","MAJOR_RUNNER_OPPORTUNITY"}
        endangered=risk_state in {"ELEVATED_RISK","HIGH_RISK","OPPORTUNITY_FAILURE"}
        candidates=[]
        for item in structures:
            if not item.get("proven") or item.get("level") is None or item.get("available_at") is None: continue
            level=_f(item["level"])
            correct_side=level<current_price if direction=="BULLISH" else level>current_price
            if correct_side and _tightens(direction,level,current_protection): candidates.append(dict(item))
        if not mature or not endangered: return {"owner":self.owner,"state":"FLOOR_NOT_ELIGIBLE","selected_level":current_protection,"supporting_only":True}
        if not candidates: return {"owner":self.owner,"state":"NO_VALID_PROFIT_FLOOR_STRUCTURE","selected_level":current_protection,"supporting_only":True}
        selected=max(candidates,key=lambda x:_f(x["level"])) if direction=="BULLISH" else min(candidates,key=lambda x:_f(x["level"]))
        return {"owner":self.owner,"state":"MATURE_PROFIT_FLOOR_AVAILABLE","selected_level":_f(selected["level"]),"structure_owner":selected.get("owner"),"structure_id":selected.get("structure_id"),"protection_tightens":True,"supporting_only":True}


def dynamic_partial_fraction(*,profile:str,target_state:str,opportunity_state:str,risk_state:str,config:SequenceEliteConfig=DEFAULT_SEQUENCE_CONFIG)->float:
    if profile=="STRUCTURE_RUNNER_ONLY": return 0.0
    if profile=="PARTIAL_PLUS_RUNNER": return config.dynamic_partial_wick_touch
    if target_state in {"ACCEPTED_BEYOND","EXTENDED"}: return config.dynamic_partial_acceptance
    if target_state=="REJECTED": return config.dynamic_partial_rejection
    if target_state in {"WICK_TOUCHED","BODY_CLOSED_THROUGH"}: return config.dynamic_partial_wick_touch
    if opportunity_state in {"SIGNIFICANT_OPPORTUNITY_EARNED","MAJOR_RUNNER_OPPORTUNITY"} and risk_state in {"HIGH_RISK","OPPORTUNITY_FAILURE"}: return config.dynamic_partial_rejection
    return 0.0


def simulate_attempt(*,candidate:Mapping[str,Any],direction:str,candles:pd.DataFrame,tp1_target:Optional[float],trail_events:Iterable[Mapping[str,Any]]=())->Dict[str,Any]:
    managed=simulate_patched_profit_management(direction=direction,entry_price=_f(candidate["entry_price"]),initial_stop=_f(candidate["logical_stop"]),emergency_stop=candidate.get("emergency_stop"),candles=candles,tp1_target=tp1_target,trail_events=trail_events,config=DEFAULT_PATCH_CONFIG)
    risk=abs(_f(candidate["entry_price"])-_f(candidate["logical_stop"]))
    if direction=="BULLISH": mfe=(_f(candles["high"].max())-_f(candidate["entry_price"]))/risk; mae=(_f(candidate["entry_price"])-_f(candles["low"].min()))/risk
    else: mfe=(_f(candidate["entry_price"])-_f(candles["low"].min()))/risk; mae=(_f(candles["high"].max())-_f(candidate["entry_price"]))/risk
    return {**managed,"execution_attempt_id":candidate["execution_attempt_id"],"attempt_number":candidate["attempt_number"],"entry_timeframe":candidate["entry_timeframe"],"entry_price":candidate["entry_price"],"logical_stop":candidate["logical_stop"],"initial_risk":risk,"MFE_R":max(0,mfe),"MAE_R":max(0,mae)}


def elite_management_overlay(
    *,
    managed: Mapping[str, Any],
    profile: str = "DYNAMIC_PARTIAL_PLUS_RUNNER",
    config: SequenceEliteConfig = DEFAULT_SEQUENCE_CONFIG,
) -> Dict[str, Any]:
    """Add two-key opportunity/risk evidence and profile economics.

    The underlying single-owner candle actions remain authoritative.  This
    overlay changes only the configured research partial allocation and records
    why mature protection was or was not eligible.
    """
    opportunity_engine=EarnedOpportunityEngine(config)
    risk_engine=OpportunityRiskEngine(config)
    timeline=[]
    prior_risk="NO_DANGER"; pending=0
    histories=list(managed.get("history",[]))
    for i,event in enumerate(histories):
        continuation=event.get("continuation",{})
        giveback=event.get("giveback",{})
        target_state=str(event.get("target_state","CREATED"))
        current_r=_f(giveback.get("current_R",0)); peak_r=_f(giveback.get("peak_R",max(0,current_r)))
        opportunity=opportunity_engine.evaluate(current_r=current_r,peak_r=peak_r,continuation_state=str(continuation.get("state","NOT_ESTABLISHED")),target_state=target_state,proven_structures=sum(h.get("decision",{}).get("action")=="TRAIL_PROVEN_STRUCTURE" for h in histories[:i+1]))
        risk=risk_engine.evaluate(continuation_state=str(continuation.get("state","NOT_ESTABLISHED")),target_state=target_state,giveback_r=_f(giveback.get("unrealized_giveback_R",0)),retained_peak_ratio=_f(giveback.get("unrealized_capture_ratio",0)),failed_extensions=int(event.get("exhaustion",{}).get("failed_extensions",0)),opposing_displacement=bool(event.get("exhaustion",{}).get("opposing_displacement",False)),protection_intact=bool(continuation.get("protection_intact",True)),prior_state=prior_risk,pending=pending)
        prior_risk=str(risk["state"]); pending=int(risk["pending"])
        timeline.append({"index":event.get("index",i),"opportunity":opportunity,"opportunity_risk":risk,"normal_pullback_event":"NORMAL_PULLBACK_ALLOWED" if risk["normal_pullback_allowed"] else None,"committed_action":event.get("decision",{})})
    final_target=str(histories[-1].get("target_state","CREATED")) if histories else "CREATED"
    last_opp=timeline[-1]["opportunity"]["state"] if timeline else "NOT_EARNED"
    last_risk=timeline[-1]["opportunity_risk"]["state"] if timeline else "NO_DANGER"
    requested_fraction=dynamic_partial_fraction(profile=profile,target_state=final_target,opportunity_state=last_opp,risk_state=last_risk,config=config)
    partial_available=bool(managed.get("tp1_partial_filled"))
    fraction=requested_fraction if partial_available else 0.0
    runner_r=_f(managed.get("runner_R",managed.get("final_R",0)))
    partial_r=_f(managed.get("partial_R",0) or 0)
    final_r=fraction*partial_r+(1-fraction)*runner_r if partial_available else runner_r
    peak_r=_f(managed.get("peak_R",0))
    return {**dict(managed),"owner":"EliteTradeManagementOverlay","profile":profile,"opportunity_timeline":timeline,"final_opportunity_state":last_opp,"final_opportunity_risk_state":last_risk,"research_partial_fraction":fraction,"runner_fraction":1-fraction,"final_R":final_r,"giveback_R":max(0,peak_r-final_r),"capture_ratio":final_r/peak_r if peak_r>0 else 0.0,"single_owner_preserved":True,"order_api_called":False}


def sequence_outcome(*,parent_setup_id:str,attempt_1:Mapping[str,Any],attempt_2:Optional[Mapping[str,Any]])->Dict[str,Any]:
    attempts=[attempt_1]+([attempt_2] if attempt_2 else [])
    final=sum(_f(a["final_R"]) for a in attempts)
    peak=max(_f(a.get("peak_R",0)) for a in attempts)
    mfe=max(_f(a.get("MFE_R",a.get("peak_R",0))) for a in attempts)
    mae=max(_f(a.get("MAE_R",0)) for a in attempts)
    giveback=max(0,peak-final)
    return {"owner":"SequenceAccountingEngine","parent_setup_id":parent_setup_id,"trade_sequence_id":parent_setup_id,"setup_count":1,"trade_sequence_count":1,"execution_attempt_count":len(attempts),"reentry_count":1 if attempt_2 else 0,"attempt_1_R":_f(attempt_1["final_R"]),"attempt_2_R":_f(attempt_2["final_R"]) if attempt_2 else None,"combined_sequence_R":final,"sequence_final_R":final,"sequence_peak_R":peak,"sequence_MFE_R":mfe,"sequence_MAE_R":mae,"sequence_giveback_R":giveback,"sequence_capture_ratio":final/peak if peak>0 else 0.0,"sequence_recovered_first_loss":bool(attempt_2 and _f(attempt_1["final_R"])<0 and final>0),"reentry_contribution_R":_f(attempt_2["final_R"]) if attempt_2 else 0.0,"causal_valid":True}


def winner_to_loser_metrics(rows:Iterable[Mapping[str,Any]])->Dict[str,Any]:
    values=list(rows)
    result={}
    for threshold in (0.5,1.0,2.0,3.0): result[f"peak_gte_{threshold:.1f}R_final_lt_0"] = sum(_f(r["peak_R"])>=threshold and _f(r["final_R"])<0 for r in values)
    result.update({"peak_gte_1R_final_lte_minus_1R":sum(_f(r["peak_R"])>=1 and _f(r["final_R"])<=-1 for r in values),"peak_gte_2R_final_lte_0R":sum(_f(r["peak_R"])>=2 and _f(r["final_R"])<=0 for r in values),"peak_gte_3R_final_lt_1R":sum(_f(r["peak_R"])>=3 and _f(r["final_R"])<1 for r in values)})
    return result


def long_runner_metrics(rows:Iterable[Mapping[str,Any]])->Dict[str,Any]:
    values=list(rows); large=[r for r in values if _f(r["peak_R"])>=3]
    return {"trades_reaching_3R":len(large),"trades_reaching_5R":sum(_f(r["peak_R"])>=5 for r in values),"average_final_R_of_3R_peak":sum(_f(r["final_R"]) for r in large)/max(1,len(large)),"average_retained_ratio_of_3R_peak":sum(_f(r["final_R"])/_f(r["peak_R"]) for r in large)/max(1,len(large)),"LONG_RUNNER_PRESERVED":sum(_f(r["final_R"])/_f(r["peak_R"])>=0.6 for r in large),"LONG_RUNNER_PROTECTED_EFFECTIVELY":sum(0.3<=_f(r["final_R"])/_f(r["peak_R"])<0.6 for r in large),"LONG_RUNNER_GAVE_BACK_EXCESSIVELY":sum(_f(r["final_R"])/_f(r["peak_R"])<0.3 for r in large)}
