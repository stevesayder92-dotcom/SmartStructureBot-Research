from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

import pandas as pd

from core.steve_trade_management import (
    transition_protection_without_loosening,
)


TARGET_STATES = {
    "CREATED",
    "APPROACHED",
    "WICK_TOUCHED",
    "BODY_CLOSED_THROUGH",
    "ACCEPTED_BEYOND",
    "REJECTED",
    "RECLAIMED",
    "EXTENDED",
    "EXPIRED",
}
PROFIT_STATES = {
    "INITIAL_RISK",
    "EARLY_PROGRESS",
    "FIRST_PROFIT_LOCK",
    "FIRST_PROVEN_STRUCTURE",
    "CONTINUATION_TRAIL",
    "EXHAUSTION_REVIEW",
    "EXITED",
}
TRAIL_STRENGTHS = {
    "MICRO_REJECTED",
    "EARLY_M1_PROVEN",
    "M5_CONTINUATION_PROVEN",
    "MAJOR_CONTINUATION_PROVEN",
}


def _number(value: Any) -> float:
    return float(value)


def _favourable(
    *,
    direction: str,
    price: float,
    reference: float,
) -> bool:
    return (
        price > reference
        if str(direction).upper() == "BULLISH"
        else price < reference
    )


def build_target_hierarchy(
    *,
    direction: str,
    entry_price: float,
    logical_stop: float,
    previous_impulse_extreme: Optional[float],
    external_objectives: Iterable[Dict[str, Any]] = (),
    spread_price: float = 0.0,
    fallback_r_multiple: float = 1.0,
) -> Dict[str, Any]:
    """Create ranked, directionally valid objectives without inventing price."""
    normalized = str(direction).upper()
    entry = _number(entry_price)
    risk = abs(entry - _number(logical_stop))
    candidates: list[Dict[str, Any]] = []

    def add(
        price: Optional[float],
        *,
        source: str,
        owner: str,
        freshness: str = "CURRENT",
        already_traded_through: bool = False,
    ) -> None:
        if price is None:
            return
        value = _number(price)
        if not _favourable(
            direction=normalized,
            price=value,
            reference=entry,
        ):
            return
        distance = abs(value - entry)
        room = distance - max(0.0, _number(spread_price))
        candidates.append(
            {
                "price": value,
                "source": source,
                "structure_owner": owner,
                "distance": distance,
                "reward_to_risk": distance / risk if risk > 0 else None,
                "freshness": freshness,
                "already_traded_through": bool(already_traded_through),
                "enough_room_after_spread": room > 0,
                "selection_reason": (
                    "Causal structure lies favourably beyond entry"
                ),
            }
        )

    add(
        previous_impulse_extreme,
        source="PREVIOUS_M5_IMPULSE_EXTREME",
        owner="M5ImpulseCycleEngine",
    )
    source_priority = {
        "EXTERNAL_LIQUIDITY": 1,
        "HTF_SWING": 2,
        "MEASURED_CONTINUATION": 3,
        "UNMITIGATED_LIQUIDITY": 4,
    }
    for objective in external_objectives:
        add(
            objective.get("price"),
            source=str(objective.get("source", "EXTERNAL_LIQUIDITY")),
            owner=str(
                objective.get("structure_owner", "TargetLifecycleEngine")
            ),
            freshness=str(objective.get("freshness", "CURRENT")),
            already_traded_through=bool(
                objective.get("already_traded_through", False)
            ),
        )
    candidates.sort(
        key=lambda row: (
            0
            if row["source"] == "PREVIOUS_M5_IMPULSE_EXTREME"
            else source_priority.get(row["source"], 5),
            row["distance"],
        )
    )
    usable = [
        row
        for row in candidates
        if row["enough_room_after_spread"]
        and not row["already_traded_through"]
    ]
    if not usable and risk > 0:
        fallback = (
            entry + fallback_r_multiple * risk
            if normalized == "BULLISH"
            else entry - fallback_r_multiple * risk
        )
        add(
            fallback,
            source=f"RESEARCH_{fallback_r_multiple:.2f}R_FALLBACK",
            owner="TargetLifecycleEngine",
            freshness="BENCHMARK_ONLY",
        )
        usable = [candidates[-1]]
    tp1 = usable[0] if usable else None
    tp2 = usable[1] if len(usable) > 1 else None
    return {
        "owner": "TargetLifecycleEngine",
        "state": "TARGETS_CREATED" if tp1 else "NO_VALID_TARGET",
        "direction": normalized,
        "initial_risk": risk,
        "candidates": candidates,
        "tp1": (
            {**tp1, "target_id": "TP1", "state": "CREATED"}
            if tp1
            else None
        ),
        "tp2": (
            {**tp2, "target_id": "TP2", "state": "CREATED"}
            if tp2
            else None
        ),
        "runner": {
            "target_id": "RUNNER",
            "state": "CREATED",
            "source": "STRUCTURE_MANAGED_EXTENSION",
            "structure_owner": "ProfitProtectionEngine",
        },
        "causal_valid": True,
    }


def advance_target_lifecycle(
    *,
    target: Dict[str, Any],
    direction: str,
    candle: Dict[str, Any] | pd.Series,
    prior_closes_beyond: int = 0,
    approach_distance: float = 0.0,
) -> Dict[str, Any]:
    """Advance one objective while preserving touch versus acceptance."""
    normalized = str(direction).upper()
    previous_state = str(target.get("state", "CREATED"))
    price = _number(target["price"])
    high = _number(candle["high"])
    low = _number(candle["low"])
    open_price = _number(candle["open"])
    close = _number(candle["close"])
    wick_touch = high >= price if normalized == "BULLISH" else low <= price
    body_through = close >= price if normalized == "BULLISH" else close <= price
    body_direction = (
        close > open_price
        if normalized == "BULLISH"
        else close < open_price
    )
    distance = (
        max(0.0, price - high)
        if normalized == "BULLISH"
        else max(0.0, low - price)
    )
    approached = distance <= max(0.0, float(approach_distance))
    rejected = bool(
        wick_touch
        and not body_through
        and (
            close < open_price
            if normalized == "BULLISH"
            else close > open_price
        )
    )
    if previous_state == "EXPIRED":
        state = "EXPIRED"
    elif previous_state in {"ACCEPTED_BEYOND", "EXTENDED"}:
        if body_through:
            state = "EXTENDED"
        else:
            state = "REJECTED"
    elif previous_state == "REJECTED" and body_through:
        state = "RECLAIMED"
    elif (
        previous_state == "RECLAIMED"
        and body_through
        and prior_closes_beyond >= 1
    ):
        state = "ACCEPTED_BEYOND"
    elif body_through and body_direction and prior_closes_beyond >= 1:
        state = "ACCEPTED_BEYOND"
    elif body_through:
        state = "BODY_CLOSED_THROUGH"
    elif rejected:
        state = "REJECTED"
    elif wick_touch:
        state = "WICK_TOUCHED"
    elif approached:
        state = "APPROACHED"
    else:
        state = str(target.get("state", "CREATED"))
    return {
        **target,
        "state": state,
        "wick_touched": wick_touch,
        "body_closed_through": body_through,
        "accepted_beyond": state == "ACCEPTED_BEYOND",
        "rejected": rejected,
        "partial_fill_allowed": wick_touch,
        "prior_closes_beyond": int(prior_closes_beyond),
        "causal_valid": True,
    }


def transition_m1_to_m5_management(
    *,
    direction: str,
    current_m1_protection: float,
    proposed_m5_protection: float,
    proof_index: int,
    proof_reason: str,
) -> Dict[str, Any]:
    transition = transition_protection_without_loosening(
        direction=direction,
        current_level=current_m1_protection,
        candidate_m5_level=proposed_m5_protection,
    )
    accepted = not bool(transition["loosened"]) and (
        _number(transition["selected_level"])
        == _number(proposed_m5_protection)
    )
    return {
        **transition,
        "owner": "ProfitProtectionEngine",
        "management_state": (
            "M1_TO_M5_TRANSITIONED"
            if accepted
            else "TRANSITION_REJECTED_WOULD_LOOSEN"
        ),
        "entry_timeframe_history_preserved": True,
        "proof_index": int(proof_index),
        "proof_reason": str(proof_reason),
        "causal_valid": True,
    }


def prove_trail_candidate(
    *,
    entry_timeframe: str,
    candidate: Dict[str, Any],
    proof_bos: Optional[Dict[str, Any]],
    direction: str,
    current_protection: float,
    current_price: float,
) -> Dict[str, Any]:
    level = _number(candidate["level"])
    normalized = str(direction).upper()
    tightens = (
        level > _number(current_protection)
        if normalized == "BULLISH"
        else level < _number(current_protection)
    )
    correct_side = (
        level < _number(current_price)
        if normalized == "BULLISH"
        else level > _number(current_price)
    )
    micro = bool(candidate.get("micro_noise", False))
    proved = bool(
        proof_bos
        and proof_bos.get("body_close_confirmed")
        and str(proof_bos.get("direction", "")).upper() == normalized
        and int(proof_bos["index"]) > int(candidate["index"])
        and tightens
        and correct_side
        and not micro
    )
    if not proved:
        strength = "MICRO_REJECTED"
    elif str(entry_timeframe).upper() == "M1":
        strength = "EARLY_M1_PROVEN"
    elif candidate.get("major"):
        strength = "MAJOR_CONTINUATION_PROVEN"
    else:
        strength = "M5_CONTINUATION_PROVEN"
    return {
        "owner": "ProfitProtectionEngine",
        "state": "TRAIL_PROVEN" if proved else "TRAIL_REJECTED",
        "strength": strength,
        "candidate_index": int(candidate["index"]),
        "candidate_level": level,
        "proof_index": (
            int(proof_bos["index"]) if proof_bos is not None else None
        ),
        "tightens": tightens,
        "correct_side_of_price": correct_side,
        "micro_noise": micro,
        "selected_protection": (
            level if proved else _number(current_protection)
        ),
        "causal_valid": (
            proof_bos is None
            or int(proof_bos["index"]) > int(candidate["index"])
        ),
    }


def evaluate_opposing_bos_exit(
    *,
    direction: str,
    current_protection: Dict[str, Any],
    bos: Dict[str, Any],
    timeframe: str,
) -> Dict[str, Any]:
    normalized = str(direction).upper()
    opposite = "BEARISH" if normalized == "BULLISH" else "BULLISH"
    meaningful = bool(
        str(bos.get("direction", "")).upper() == opposite
        and bos.get("body_close_confirmed")
        and bos.get("broken_protection_id")
        == current_protection.get("protection_id")
        and current_protection.get("proven")
        and not bos.get("micro_noise")
    )
    return {
        "owner": "ProfitProtectionEngine",
        "state": (
            "OPPOSING_MEANINGFUL_BOS_EXIT"
            if meaningful
            else "MICRO_OPPOSING_BOS_REJECTED"
        ),
        "exit": meaningful,
        "opposing_bos_strength": (
            str(bos.get("strength", "MEANINGFUL"))
            if meaningful
            else "MICRO_REJECTED"
        ),
        "broken_protection_id": bos.get("broken_protection_id"),
        "exit_timeframe": str(timeframe).upper() if meaningful else None,
        "exit_reason": (
            "BODY_CLOSE_BROKE_CURRENTLY_OWNED_PROVEN_PROTECTION"
            if meaningful
            else None
        ),
        "micro_bos_rejected": not meaningful,
        "causal_valid": True,
    }


def profit_capture_metrics(
    *,
    direction: str,
    entry_price: float,
    initial_stop: float,
    candles: pd.DataFrame,
    exit_price: float,
    entry_time: Optional[float] = None,
    exit_time: Optional[float] = None,
    peak_time: Optional[float] = None,
    tp1_state: str = "CREATED",
    tp2_state: str = "CREATED",
    first_trail_delay: Optional[int] = None,
    trail_count: int = 0,
    entry_timeframe: str = "M5",
    exit_timeframe: str = "M5",
) -> Dict[str, Any]:
    normalized = str(direction).upper()
    entry = _number(entry_price)
    stop = _number(initial_stop)
    risk = abs(entry - stop)
    if risk <= 0:
        raise ValueError("initial_risk must be positive")
    if candles.empty:
        raise ValueError("profit metrics require closed post-entry candles")
    if normalized == "BULLISH":
        mfe_price = _number(candles["high"].astype(float).max())
        mae_price = _number(candles["low"].astype(float).min())
        favourable = mfe_price - entry
        adverse = entry - mae_price
        realized = _number(exit_price) - entry
    else:
        mfe_price = _number(candles["low"].astype(float).min())
        mae_price = _number(candles["high"].astype(float).max())
        favourable = entry - mfe_price
        adverse = mae_price - entry
        realized = entry - _number(exit_price)
    peak_r = max(0.0, favourable / risk)
    final_r = realized / risk
    giveback_r = max(0.0, peak_r - final_r)
    capture_ratio = final_r / peak_r if peak_r > 0 else 0.0
    giveback_ratio = giveback_r / peak_r if peak_r > 0 else 0.0
    if peak_r <= 0:
        classification = "EARLY_EXIT"
    elif capture_ratio >= 0.80:
        classification = "EXCELLENT_CAPTURE"
    elif capture_ratio >= 0.60:
        classification = "GOOD_CAPTURE"
    elif capture_ratio >= 0.40:
        classification = "ACCEPTABLE_CAPTURE"
    elif giveback_ratio >= 0.75:
        classification = "SEVERE_GIVEBACK"
    elif trail_count >= 4 and peak_r < 1.0:
        classification = "OVER_MANAGED"
    elif trail_count == 0 and peak_r >= 1.0:
        classification = "UNDER_PROTECTED"
    else:
        classification = "POOR_CAPTURE"
    return {
        "owner": "ProfitCaptureMetricsEngine",
        "state": "PROFIT_CAPTURE_MEASURED",
        "initial_risk": risk,
        "mfe_price": mfe_price,
        "mae_price": mae_price,
        "MFE": max(0.0, favourable),
        "MAE": max(0.0, adverse),
        "peak_R": peak_r,
        "final_R": final_r,
        "giveback_R": giveback_r,
        "capture_ratio": capture_ratio,
        "giveback_ratio": giveback_ratio,
        "time_to_peak": (
            float(peak_time) - float(entry_time)
            if peak_time is not None and entry_time is not None
            else None
        ),
        "time_from_peak_to_exit": (
            float(exit_time) - float(peak_time)
            if exit_time is not None and peak_time is not None
            else None
        ),
        "TP1_state": tp1_state,
        "TP2_state": tp2_state,
        "first_trail_delay": first_trail_delay,
        "trail_count": int(trail_count),
        "entry_timeframe": str(entry_timeframe).upper(),
        "exit_timeframe": str(exit_timeframe).upper(),
        "classification": classification,
        "closed_candle_evidence_only": True,
        "causal_valid": True,
    }


def simulate_profit_management(
    *,
    direction: str,
    entry_price: float,
    initial_stop: float,
    candles: pd.DataFrame,
    tp1_target: Optional[float],
    emergency_stop: Optional[float] = None,
    target_events: Iterable[Dict[str, Any]] = (),
    trail_events: Iterable[Dict[str, Any]] = (),
    profit_lock_trigger_r: float = 1.0,
    profit_lock_r: float = 0.10,
    tp1_partial_fraction: float = 0.50,
) -> Dict[str, Any]:
    """
    Apply closed-candle profit protection and partial-target accounting.

    TP1 touch can fill the configured partial but does not itself force
    break-even. A positive-R close, or a causally proven structural trail,
    may tighten protection. Protection never loosens.
    """
    normalized = str(direction).upper()
    entry = _number(entry_price)
    original_stop = _number(initial_stop)
    risk = abs(entry - original_stop)
    if risk <= 0:
        raise ValueError("initial risk must be positive")
    if not 0.0 <= float(tp1_partial_fraction) <= 1.0:
        raise ValueError("tp1_partial_fraction must be in [0, 1]")
    if candles.empty:
        raise ValueError("closed management candles are required")
    current_protection = original_stop
    state = "INITIAL_RISK"
    history = [
        {
            "state": state,
            "index": 0,
            "protection": current_protection,
        }
    ]
    trails_by_proof: Dict[int, list[Dict[str, Any]]] = {}
    for event in trail_events:
        if event.get("state") != "TRAIL_PROVEN":
            continue
        proof_index = event.get("proof_index")
        if proof_index is not None:
            trails_by_proof.setdefault(int(proof_index), []).append(event)
    target_events_by_index: Dict[int, list[Dict[str, Any]]] = {}
    for event in target_events:
        event_index = event.get("index")
        if event_index is not None:
            target_events_by_index.setdefault(
                int(event_index),
                [],
            ).append(event)
    partial_filled = False
    partial_r = 0.0
    partial_fraction = float(tp1_partial_fraction)
    runner_fraction = 1.0
    exit_index = len(candles) - 1
    exit_price = _number(candles.iloc[-1]["close"])
    exit_reason = "OPEN_AT_REVIEW_END"

    for index, row in candles.reset_index(drop=True).iterrows():
        open_price = _number(row["open"])
        high = _number(row["high"])
        low = _number(row["low"])
        close = _number(row["close"])
        close_r = (
            (close - entry) / risk
            if normalized == "BULLISH"
            else (entry - close) / risk
        )
        emergency_hit = (
            emergency_stop is not None
            and (
                low <= _number(emergency_stop)
                if normalized == "BULLISH"
                else high >= _number(emergency_stop)
            )
        )
        if emergency_hit:
            emergency = _number(emergency_stop)
            exit_index = int(index)
            exit_price = (
                min(open_price, emergency)
                if normalized == "BULLISH"
                else max(open_price, emergency)
            )
            exit_reason = "EMERGENCY_BROKER_STOP_HIT"
            state = "EXITED"
            history.append(
                {
                    "state": state,
                    "index": exit_index,
                    "reason": exit_reason,
                    "protection": current_protection,
                    "exit_price": exit_price,
                }
            )
            break
        if state == "INITIAL_RISK" and close_r > 0:
            state = "EARLY_PROGRESS"
            history.append(
                {
                    "state": state,
                    "index": int(index),
                    "reason": "CLOSED_CANDLE_POSITIVE_PROGRESS",
                    "protection": current_protection,
                }
            )
        if (
            tp1_target is not None
            and not partial_filled
            and (
                high >= _number(tp1_target)
                if normalized == "BULLISH"
                else low <= _number(tp1_target)
            )
        ):
            partial_filled = True
            runner_fraction = 1.0 - partial_fraction
            partial_r = (
                (_number(tp1_target) - entry) / risk
                if normalized == "BULLISH"
                else (entry - _number(tp1_target)) / risk
            )
            history.append(
                {
                    "state": "TP1_PARTIAL_FILLED",
                    "index": int(index),
                    "reason": "TP1_WICK_TOUCH",
                    "partial_fraction": partial_fraction,
                    "partial_R": partial_r,
                    "break_even_forced": False,
                }
            )
        for target_event in target_events_by_index.get(int(index), []):
            target_state = str(target_event.get("state", ""))
            if target_state == "ACCEPTED_BEYOND":
                state = "EXHAUSTION_REVIEW"
                history.append(
                    {
                        "state": state,
                        "index": int(index),
                        "reason": "TP1_ACCEPTED_BEYOND",
                        "protection": current_protection,
                    }
                )
            elif (
                target_state == "REJECTED"
                and any(
                    event.get("state") == "EXHAUSTION_REVIEW"
                    for event in history
                )
            ):
                exit_index = int(index)
                exit_price = close
                exit_reason = "TP1_ACCEPTANCE_REJECTED_RUNNER_EXIT"
                state = "EXITED"
                history.append(
                    {
                        "state": state,
                        "index": exit_index,
                        "reason": exit_reason,
                        "protection": current_protection,
                        "exit_price": exit_price,
                    }
                )
                break
        if state == "EXITED":
            break
        if close_r >= float(profit_lock_trigger_r):
            proposed = (
                entry + float(profit_lock_r) * risk
                if normalized == "BULLISH"
                else entry - float(profit_lock_r) * risk
            )
            tightens = (
                proposed > current_protection
                if normalized == "BULLISH"
                else proposed < current_protection
            )
            correct_side = (
                proposed < close
                if normalized == "BULLISH"
                else proposed > close
            )
            if tightens and correct_side:
                current_protection = proposed
                state = "FIRST_PROFIT_LOCK"
                history.append(
                    {
                        "state": state,
                        "index": int(index),
                        "reason": "CONFIGURABLE_POSITIVE_R_CLOSE",
                        "protection": current_protection,
                        "trigger_R": float(profit_lock_trigger_r),
                        "locked_R": float(profit_lock_r),
                    }
                )
        for trail in trails_by_proof.get(int(index), []):
            proposed = _number(trail["selected_protection"])
            tightens = (
                proposed > current_protection
                if normalized == "BULLISH"
                else proposed < current_protection
            )
            correct_side = (
                proposed < close
                if normalized == "BULLISH"
                else proposed > close
            )
            if tightens and correct_side:
                current_protection = proposed
                state = (
                    "FIRST_PROVEN_STRUCTURE"
                    if not any(
                        item["state"] == "FIRST_PROVEN_STRUCTURE"
                        for item in history
                    )
                    else "CONTINUATION_TRAIL"
                )
                history.append(
                    {
                        "state": state,
                        "index": int(index),
                        "reason": trail["strength"],
                        "protection": current_protection,
                    }
                )
        invalidated = (
            close < current_protection and close < open_price
            if normalized == "BULLISH"
            else close > current_protection and close > open_price
        )
        if invalidated and index > 0:
            exit_index = int(index)
            exit_price = close
            exit_reason = "OWNED_PROTECTION_BODY_CLOSE_EXIT"
            state = "EXITED"
            history.append(
                {
                    "state": state,
                    "index": exit_index,
                    "reason": exit_reason,
                    "protection": current_protection,
                    "exit_price": exit_price,
                }
            )
            break
    runner_r = (
        (exit_price - entry) / risk
        if normalized == "BULLISH"
        else (entry - exit_price) / risk
    )
    realized_r = (
        partial_fraction * partial_r + runner_fraction * runner_r
        if partial_filled
        else runner_r
    )
    equivalent_exit_price = (
        entry + realized_r * risk
        if normalized == "BULLISH"
        else entry - realized_r * risk
    )
    return {
        "owner": "ProfitProtectionEngine",
        "state": state,
        "history": history,
        "initial_protection": original_stop,
        "final_protection": current_protection,
        "protection_never_loosened": True,
        "tp1_partial_filled": partial_filled,
        "tp1_partial_fraction": partial_fraction if partial_filled else 0.0,
        "runner_fraction": runner_fraction,
        "partial_R": partial_r if partial_filled else None,
        "runner_R": runner_r,
        "realized_R": realized_r,
        "exit_index": exit_index,
        "exit_price": exit_price,
        "equivalent_exit_price": equivalent_exit_price,
        "exit_reason": exit_reason,
        "closed_candle_evidence_only": True,
        "causal_valid": True,
    }
