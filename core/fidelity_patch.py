from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, Mapping, Optional

import pandas as pd

from core.fibonacci_contract import classify_remaining


def _f(value: Any) -> float:
    return float(value)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _tightens(direction: str, candidate: float, current: float) -> bool:
    return candidate > current if direction == "BULLISH" else candidate < current


@dataclass(frozen=True)
class FidelityPatchConfig:
    """Documented defaults for Final Fidelity Patch v1.0.

    All values are research parameters.  None enables order execution.
    """

    m1_quality_weights: Mapping[str, float] = field(
        default_factory=lambda: {
            "counter_trend_clarity": 20.0,
            "trigger_significance": 15.0,
            "bos_quality": 20.0,
            "compression_to_expansion": 10.0,
            "entry_location": 15.0,
            "timing_advantage": 10.0,
            "market_cleanliness": 10.0,
        }
    )
    m1_grade_thresholds: Mapping[str, float] = field(
        default_factory=lambda: {"A_PLUS_M1": 85.0, "A_M1": 70.0, "B_M1": 55.0}
    )
    m1_risk_policy: Mapping[str, str] = field(
        default_factory=lambda: {
            "A_PLUS_M1": "FULL_RESEARCH_RISK",
            "A_M1": "STANDARD_RESEARCH_RISK",
            "B_M1": "REDUCED_RESEARCH_RISK",
            "C_M1": "OBSERVE_ONLY",
        }
    )
    meaningful_m1_swing_atr: float = 0.35
    stale_trigger_candles: int = 30
    overlap_warning_ratio: float = 0.65
    bos_displacement_atr: float = 0.35
    continuation_weights: Mapping[str, float] = field(
        default_factory=lambda: {
            "progress": 0.25,
            "displacement": 0.20,
            "pullback_health": 0.20,
            "structural_progression": 0.20,
            "acceptance": 0.15,
        }
    )
    continuation_thresholds: Mapping[str, float] = field(
        default_factory=lambda: {"STRONG": 80.0, "HEALTHY": 65.0, "WEAKENING": 45.0, "EXHAUSTION": 25.0}
    )
    hysteresis_confirmations: int = 2
    favourable_progress_r: float = 0.35
    early_protection_r: float = 0.90
    small_profit_lock_r: float = 0.10
    elevated_giveback_r: float = 0.75
    severe_giveback_r: float = 1.25
    unacceptable_capture_ratio: float = 0.25
    exhaustion_thresholds: Mapping[str, float] = field(
        default_factory=lambda: {"CONFIRMED": 80.0, "HIGH": 65.0, "MEANINGFUL": 45.0, "EARLY": 25.0}
    )
    partial_exit_research: bool = True
    runner_exit_policy: str = "STRUCTURE_OR_TARGET_SUPPORTED_EXHAUSTION"

    def contract(self) -> Dict[str, Any]:
        result = asdict(self)
        result.update({"version": "FINAL_FIDELITY_PATCH_V1", "research_only": True, "order_execution": False})
        return result


DEFAULT_PATCH_CONFIG = FidelityPatchConfig()


def _grade(score: float, config: FidelityPatchConfig) -> tuple[str, str]:
    t = config.m1_grade_thresholds
    if score >= t["A_PLUS_M1"]:
        return "A_PLUS_M1", "CLEAN_EARLY_ENTRY"
    if score >= t["A_M1"]:
        return "A_M1", "ACCEPTABLE_EARLY_ENTRY"
    if score >= t["B_M1"]:
        return "B_M1", "WEAK_BUT_VALID"
    return "C_M1", "RANDOM_OR_LOW_VALUE_M1"


class M1EntryQualityEngine:
    owner = "M1EntryQualityEngine"

    def __init__(self, config: FidelityPatchConfig = DEFAULT_PATCH_CONFIG):
        self.config = config

    def evaluate(
        self,
        *,
        data: pd.DataFrame,
        parent: Mapping[str, Any],
        initial_index: int,
        counter_index: int,
        trigger_index: int,
        trigger_available_index: int,
        entry_index: int,
        trigger_level: float,
        entry_price: float,
        logical_stop: float,
        local_atr: float,
        internal_swings: int,
        overlap_ratio: float,
    ) -> Dict[str, Any]:
        direction = str(parent["parent_direction"]).upper()
        atr = max(float(local_atr), 1e-12)
        entry = data.iloc[int(entry_index)]
        recent = data.iloc[max(0, int(entry_index) - 7) : int(entry_index) + 1]
        pre = data.iloc[max(0, int(entry_index) - 5) : int(entry_index)]
        body = abs(_f(entry["close"]) - _f(entry["open"]))
        candle_range = max(_f(entry["high"]) - _f(entry["low"]), 1e-12)
        close_beyond = (
            _f(entry["close"]) - float(trigger_level)
            if direction == "BULLISH"
            else float(trigger_level) - _f(entry["close"])
        )
        counter_move = abs(_f(data.iloc[int(initial_index)]["close"]) - _f(data.iloc[int(counter_index)]["close"]))
        counter_bars = max(1, int(counter_index) - int(initial_index))
        clarity_raw = min(1.0, counter_move / atr / 1.5) * 0.45 + min(1.0, counter_bars / 6.0) * 0.30 + min(1.0, internal_swings / 5.0) * 0.25
        trigger_age = int(entry_index) - int(trigger_available_index)
        trigger_raw = 1.0 - min(1.0, trigger_age / max(1, self.config.stale_trigger_candles))
        touches = 0
        if not pre.empty:
            if direction == "BULLISH":
                touches = int((pre["high"].astype(float) >= float(trigger_level)).sum())
            else:
                touches = int((pre["low"].astype(float) <= float(trigger_level)).sum())
        trigger_raw = _clamp((trigger_raw - max(0, touches - 1) * 0.15) * 100.0) / 100.0
        body_atr = body / atr
        wick_ratio = 1.0 - body / candle_range
        median_body = max(float((recent["close"].astype(float) - recent["open"].astype(float)).abs().median()), 1e-12)
        bos_raw = min(1.0, body_atr / 1.0) * 0.45 + min(1.0, max(0.0, close_beyond) / atr / 0.35) * 0.30 + min(1.0, body / median_body / 2.0) * 0.15 + max(0.0, 1.0 - wick_ratio) * 0.10
        pre_ranges = pre["high"].astype(float) - pre["low"].astype(float) if not pre.empty else pd.Series(dtype=float)
        compression_raw = min(1.0, body / max(float(pre_ranges.mean()) if not pre_ranges.empty else atr, 1e-12))
        zero = parent.get("fib_zero_price")
        hundred = parent.get("fib_hundred_price")
        if zero is not None and hundred is not None and float(hundred) != float(zero):
            impulse = abs(float(hundred) - float(zero))
            remaining = (
                (float(entry_price) - float(zero)) / impulse
                if direction == "BULLISH"
                else (float(zero) - float(entry_price)) / impulse
            )
            zone = classify_remaining(remaining)
        else:
            # Compatibility for explicitly causal test/legacy callers that do
            # not yet publish fixed Fibonacci anchors.
            remaining = None
            zone = str(parent.get("fibonacci_zone") or "")
        zone_raw = 1.0 if zone == "STEVE_PRIMARY_DEEP_SWEET_SPOT" else 0.8 if "38_2" in zone or "61_8" in zone else 0.55
        risk = max(abs(float(entry_price) - float(logical_stop)), 1e-12)
        objective = float(parent.get("fib_hundred_price", entry_price))
        rr = abs(objective - float(entry_price)) / risk
        location_raw = zone_raw * 0.65 + min(1.0, rr / 2.0) * 0.35
        # S2A.1: the former timing component compared this earlier decision to
        # an eventual M5 entry/stop.  That is post-hoc outcome information.  Its
        # configured ten-point allocation intentionally remains unassigned;
        # thresholds and all other weights are unchanged.
        timing_raw = 0.0
        alternating = 0
        wick_density = 0.0
        if len(recent) > 1:
            signs = (recent["close"].astype(float) - recent["open"].astype(float)).map(lambda x: 1 if x > 0 else -1 if x < 0 else 0).tolist()
            alternating = sum(a != 0 and b != 0 and a != b for a, b in zip(signs, signs[1:]))
            ranges = (recent["high"].astype(float) - recent["low"].astype(float)).clip(lower=1e-12)
            bodies = (recent["close"].astype(float) - recent["open"].astype(float)).abs()
            wick_density = float((1.0 - bodies / ranges).mean())
        clean_raw = 1.0 - (min(1.0, float(overlap_ratio)) * 0.45 + min(1.0, alternating / 5.0) * 0.30 + min(1.0, wick_density) * 0.25)
        raw = {
            "counter_trend_clarity": clarity_raw,
            "trigger_significance": trigger_raw,
            "bos_quality": bos_raw,
            "compression_to_expansion": compression_raw,
            "entry_location": location_raw,
            "timing_advantage": timing_raw,
            "market_cleanliness": clean_raw,
        }
        components = {name: round(_clamp(raw[name] * weight, 0.0, weight), 3) for name, weight in self.config.m1_quality_weights.items()}
        score = round(sum(components.values()), 3)
        grade, classification = _grade(score, self.config)
        positive = [name.upper() for name, value in raw.items() if name != "timing_advantage" and value >= 0.68]
        negative = [name.upper() for name, value in raw.items() if name != "timing_advantage" and value < 0.45]
        policy = self.config.m1_risk_policy[grade]
        post_hoc: Dict[str, Any] = {
            "availability": "UNAVAILABLE",
            "analytics_only": True,
            "influences_causal_quality": False,
            "minutes_saved_vs_eventual_m5": None,
            "stop_reduction_percent_vs_eventual_m5": None,
            "reason": "Published by the separate post-hoc outcome analytics layer",
        }
        return {
            "owner": self.owner,
            "state": classification,
            "structurally_valid": True,
            "m1_quality_score": score,
            "causal_quality_score": score,
            "grade": grade,
            "classification": classification,
            "component_scores": components,
            "positive_reasons": positive,
            "negative_reasons": negative,
            "research_policy": policy,
            "observe_only": policy == "OBSERVE_ONLY",
            "trigger_age_candles": trigger_age,
            "counter_trend_bars": counter_bars,
            "counter_trend_atr": round(counter_move / atr, 4),
            "bos_body_atr": round(body_atr, 4),
            "close_beyond_trigger_atr": round(max(0.0, close_beyond) / atr, 4),
            "overlap_ratio": round(float(overlap_ratio), 4),
            "entry_price": float(entry_price),
            "logical_stop": float(logical_stop),
            "causal_stop_distance": round(risk, 10),
            "causal_fibonacci_zone": zone,
            "causal_remaining_impulse_ratio": (
                round(float(remaining), 6) if remaining is not None else None
            ),
            "excluded_weight_points": self.config.m1_quality_weights["timing_advantage"],
            "quality_basis": "CAUSAL_M1_ENTRY_CLOSE_ONLY",
            "post_hoc_advantage_diagnostics": post_hoc,
            "causal_valid": int(trigger_available_index) <= int(entry_index),
            "as_of_index": int(entry_index),
            "closed_candles_only": True,
        }


def classify_m1_outcome(*, structurally_valid: bool, m5_later_confirmed: bool, failed_quickly: bool, trigger_significant: bool, counter_move_active: bool, meaningful_advantage: bool, saved_move: bool) -> str:
    if saved_move:
        return "M1_SAVED_MOVE"
    if meaningful_advantage and m5_later_confirmed:
        return "M1_CLEAR_ADVANTAGE"
    if not trigger_significant:
        return "M1_WRONG_CHILD_STRUCTURE"
    if counter_move_active:
        return "M1_PREMATURE_DURING_ACTIVE_COUNTER_MOVE"
    if failed_quickly and not m5_later_confirmed:
        return "M1_FALSE_EARLY_NO_M5_CONFIRMATION"
    if structurally_valid:
        return "M1_VALID_NORMAL_LOSS" if failed_quickly else "M1_CLEAR_ADVANTAGE"
    return "M1_FALSE_MICRO_BOS"


def count_trade_identity(sequences: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
    rows = list(sequences)
    setup_ids = {str(row["parent_setup_id"]) for row in rows}
    sequence_ids = {
        (str(row["parent_setup_id"]), str(row.get("trade_sequence_id", row["parent_setup_id"])))
        for row in rows
    }
    return {
        "setup_count": len(setup_ids),
        "trade_sequence_count": len(sequence_ids),
        "execution_attempt_count": len(rows),
        "reentry_count": sum(int(row.get("attempt_number", 1)) == 2 for row in rows),
        "m1_first_entry_count": sum(str(row.get("entry_timeframe", "")).upper() == "M1" and int(row.get("attempt_number", 1)) == 1 for row in rows),
        "m5_first_entry_count": sum(str(row.get("entry_timeframe", "")).upper() == "M5" and int(row.get("attempt_number", 1)) == 1 for row in rows),
    }


def _state_for_continuation(score: float, progress_r: float, failed: bool, config: FidelityPatchConfig) -> str:
    if failed:
        return "CONTINUATION_FAILED"
    if progress_r <= 0.0:
        return "NOT_ESTABLISHED"
    t = config.continuation_thresholds
    if score >= t["STRONG"]:
        return "STRONG_CONTINUATION"
    if score >= t["HEALTHY"]:
        return "HEALTHY_CONTINUATION"
    if score >= t["WEAKENING"]:
        return "WEAKENING_CONTINUATION"
    if score >= t["EXHAUSTION"]:
        return "EXHAUSTION_WARNING"
    return "CONTINUATION_FAILED"


class ContinuationQualityEngine:
    owner = "ContinuationQualityEngine"

    def __init__(self, config: FidelityPatchConfig = DEFAULT_PATCH_CONFIG):
        self.config = config

    def evaluate(self, *, direction: str, entry_price: float, initial_risk: float, candles: pd.DataFrame, current_protection: float, target_state: str = "CREATED", previous_state: str = "NOT_ESTABLISHED", pending_state_count: int = 0) -> Dict[str, Any]:
        direction = direction.upper()
        if candles.empty:
            raise ValueError("continuation evaluation requires closed candles")
        data = candles.reset_index(drop=True)
        close = _f(data.iloc[-1]["close"])
        closes = data["close"].astype(float)
        opens = data["open"].astype(float)
        progress_r = (close - entry_price) / initial_risk if direction == "BULLISH" else (entry_price - close) / initial_risk
        favourable = (data["high"].astype(float).max() - entry_price) / initial_risk if direction == "BULLISH" else (entry_price - data["low"].astype(float).min()) / initial_risk
        net = abs(close - entry_price)
        total = float(closes.diff().abs().sum()) or initial_risk
        progress_score = _clamp(35.0 * max(0.0, progress_r) + 35.0 * min(1.0, favourable / 2.0) + 30.0 * min(1.0, net / total))
        recent = data.iloc[-min(6, len(data)) :]
        bodies = (recent["close"].astype(float) - recent["open"].astype(float)).abs()
        ranges = (recent["high"].astype(float) - recent["low"].astype(float)).clip(lower=1e-12)
        directional = ((recent["close"] > recent["open"]) if direction == "BULLISH" else (recent["close"] < recent["open"])).astype(float)
        displacement_score = _clamp(55.0 * float(directional.mean()) + 45.0 * float((bodies / ranges).mean()))
        peak_close = float(closes.max()) if direction == "BULLISH" else float(closes.min())
        pullback_r = (peak_close - close) / initial_risk if direction == "BULLISH" else (close - peak_close) / initial_risk
        protection_intact = close > current_protection if direction == "BULLISH" else close < current_protection
        pullback_health_score = _clamp(100.0 - 45.0 * max(0.0, pullback_r) + (15.0 if protection_intact else -60.0))
        extremes = data["high"].astype(float).cummax().diff().gt(0).sum() if direction == "BULLISH" else data["low"].astype(float).cummin().diff().lt(0).sum()
        structural_score = _clamp(25.0 + 15.0 * min(5, int(extremes)) + (15.0 if protection_intact else -40.0))
        acceptance_score = {"ACCEPTED_BEYOND": 100.0, "EXTENDED": 100.0, "BODY_CLOSED_THROUGH": 75.0, "WICK_TOUCHED": 55.0, "REJECTED": 20.0}.get(target_state, 35.0)
        shrinking = 0.0
        if len(bodies) >= 4:
            first = float(bodies.iloc[: len(bodies)//2].mean())
            last = float(bodies.iloc[len(bodies)//2 :].mean())
            shrinking = _clamp((first - last) / max(first, 1e-12) * 100.0)
        overlap = _clamp((1.0 - net / max(total, 1e-12)) * 100.0)
        deterioration = _clamp(0.55 * shrinking + 0.45 * overlap)
        components = {"progress_score": progress_score, "displacement_score": displacement_score, "pullback_health_score": pullback_health_score, "structural_progression_score": structural_score, "acceptance_score": acceptance_score, "deterioration_penalty": deterioration}
        w = self.config.continuation_weights
        score = _clamp(progress_score*w["progress"] + displacement_score*w["displacement"] + pullback_health_score*w["pullback_health"] + structural_score*w["structural_progression"] + acceptance_score*w["acceptance"] - deterioration*0.20)
        hard_failed = not protection_intact and len(data) > 1
        raw_state = _state_for_continuation(score, progress_r, hard_failed, self.config)
        state = raw_state
        next_count = pending_state_count
        if not hard_failed and previous_state not in {"NOT_ESTABLISHED", raw_state}:
            next_count += 1
            if next_count < self.config.hysteresis_confirmations:
                state = previous_state
            else:
                next_count = 0
        else:
            next_count = 0
        return {"owner": self.owner, "state": state, "raw_state": raw_state, "continuation_score": round(score, 3), **{k: round(v, 3) for k,v in components.items()}, "progress_R": round(progress_r, 4), "peak_R": round(max(0.0, favourable), 4), "pullback_R": round(max(0.0, pullback_r), 4), "protection_intact": protection_intact, "pending_state_count": next_count, "hard_structural_failure": hard_failed, "as_of_index": len(data)-1, "causal_valid": True}


def trade_maturity(*, current_r: float, target_state: str, continuation_state: str, proven_trail: bool, exited: bool = False) -> str:
    if exited:
        return "EXITED"
    if continuation_state in {"EXHAUSTION_WARNING", "CONTINUATION_FAILED"} and current_r > 0:
        return "EXHAUSTION_REVIEW"
    if proven_trail and target_state in {"BODY_CLOSED_THROUGH", "ACCEPTED_BEYOND", "EXTENDED"}:
        return "RUNNER_PHASE"
    if target_state in {"BODY_CLOSED_THROUGH", "ACCEPTED_BEYOND", "EXTENDED"}:
        return "CONTINUATION_CONFIRMED"
    if target_state in {"WICK_TOUCHED", "REJECTED"}:
        return "FIRST_OBJECTIVE_REACHED"
    if current_r >= 0.75:
        return "PROFIT_OPPORTUNITY"
    if current_r > 0:
        return "EARLY_PROGRESS"
    return "INITIAL_RISK"


class GivebackControlEngine:
    owner = "GivebackControlEngine"

    def __init__(self, config: FidelityPatchConfig = DEFAULT_PATCH_CONFIG): self.config = config

    def evaluate(self, *, current_r: float, peak_r: float, maturity: str, continuation_state: str, protection_intact: bool) -> Dict[str, Any]:
        giveback = max(0.0, peak_r-current_r)
        capture = current_r/peak_r if peak_r > 0 else 0.0
        if continuation_state in {"STRONG_CONTINUATION", "HEALTHY_CONTINUATION"} and protection_intact:
            state = "NORMAL_FLUCTUATION" if giveback < self.config.severe_giveback_r else "ACCEPTABLE_GIVEBACK"
            action = "NO_ACTION"
        elif maturity in {"RUNNER_PHASE", "EXHAUSTION_REVIEW", "CONTINUATION_CONFIRMED"} and giveback >= self.config.severe_giveback_r and capture <= self.config.unacceptable_capture_ratio:
            state, action = "UNACCEPTABLE_GIVEBACK", "PROTECT_MAJORITY_OF_OPEN_PROFIT"
        elif giveback >= self.config.severe_giveback_r:
            state, action = "SEVERE_GIVEBACK_WARNING", "TIGHTEN_TO_LATEST_PROVEN_STRUCTURE"
        elif giveback >= self.config.elevated_giveback_r:
            state, action = "ELEVATED_GIVEBACK", "REVIEW_PROTECTION"
        else:
            state, action = "ACCEPTABLE_GIVEBACK", "NO_ACTION"
        return {"owner": self.owner, "state": state, "recommended_action": action, "current_R": round(current_r,4), "peak_R": round(peak_r,4), "unrealized_giveback_R": round(giveback,4), "unrealized_capture_ratio": round(capture,4), "supporting_only": True, "causal_valid": True}


class ExhaustionEngine:
    owner = "ExhaustionEngine"

    def __init__(self, config: FidelityPatchConfig = DEFAULT_PATCH_CONFIG): self.config = config

    def evaluate(self, *, continuation: Mapping[str, Any], giveback: Mapping[str, Any], target_state: str, failed_extensions: int, opposing_displacement: bool, protection_intact: bool) -> Dict[str, Any]:
        rejected_reasons = []
        score = 0.0
        score += min(30.0, max(0, int(failed_extensions))*10.0)
        score += max(0.0, (55.0-float(continuation["continuation_score"]))*0.55)
        score += 20.0 if target_state == "REJECTED" else 10.0 if target_state == "WICK_TOUCHED" else 0.0
        score += 20.0 if opposing_displacement else 0.0
        score += min(20.0, float(giveback["unrealized_giveback_R"])*8.0)
        if protection_intact and continuation["state"] in {"STRONG_CONTINUATION", "HEALTHY_CONTINUATION"}:
            score = min(score, 24.0)
            rejected_reasons += ["PROTECTION_INTACT", "CONTINUATION_STILL_HEALTHY"]
        if not opposing_displacement:
            rejected_reasons.append("NO_OPPOSING_DISPLACEMENT")
        score = _clamp(score)
        t = self.config.exhaustion_thresholds
        state = "EXHAUSTION_CONFIRMED" if score >= t["CONFIRMED"] else "HIGH_EXHAUSTION" if score >= t["HIGH"] else "MEANINGFUL_WARNING" if score >= t["MEANINGFUL"] else "EARLY_WARNING" if score >= t["EARLY"] else "NO_EXHAUSTION"
        return {"owner": self.owner, "state": state, "exhaustion_score": round(score,3), "failed_extensions": int(failed_extensions), "target_reaction": target_state, "opposing_displacement": opposing_displacement, "exhaustion_rejected_reasons": rejected_reasons, "supporting_only": True, "causal_valid": True}


class TradeManagementCoordinator:
    """Single commit owner.  All supplied engine reports are immutable evidence."""
    owner = "TradeManagementCoordinator"

    def decide(self, *, direction: str, current_price: float, current_protection: float, initial_stop: float, entry_price: float, maturity: str, continuation: Mapping[str, Any], giveback: Mapping[str, Any], exhaustion: Mapping[str, Any], target_state: str, proven_trail: Optional[float], emergency_hit: bool, logical_invalidated: bool, opposing_bos_exit: bool, config: FidelityPatchConfig = DEFAULT_PATCH_CONFIG) -> Dict[str, Any]:
        direction = direction.upper()
        action, reason, proposed = "HOLD", "NORMAL_MANAGEMENT", current_protection
        risk = abs(entry_price-initial_stop)
        current_r = ((current_price-entry_price)/risk if direction == "BULLISH" else (entry_price-current_price)/risk) if risk > 0 else 0.0
        if emergency_hit:
            action, reason = "EXIT_EMERGENCY", "EMERGENCY_STOP_HIT"
        elif logical_invalidated:
            action, reason = "EXIT_LOGICAL_INVALIDATION", "OWNED_LOGICAL_PROTECTION_BROKEN"
        elif opposing_bos_exit:
            action, reason = "EXIT_OPPOSING_BOS", "MEANINGFUL_OPPOSING_BOS_BROKE_OWNED_PROTECTION"
        elif proven_trail is not None and _tightens(direction, float(proven_trail), current_protection):
            proposed, action, reason = float(proven_trail), "TRAIL_PROVEN_STRUCTURE", "LATEST_CAUSALLY_PROVEN_STRUCTURE"
        elif current_r >= 1.0 and continuation["state"] in {"STRONG_CONTINUATION", "HEALTHY_CONTINUATION"}:
            # This retains the accepted small-profit lock, but only when the
            # fixed-R event is accompanied by healthy continuation evidence.
            lock = entry_price + config.small_profit_lock_r*risk if direction == "BULLISH" else entry_price-config.small_profit_lock_r*risk
            if _tightens(direction, lock, current_protection) and ((lock < current_price) if direction == "BULLISH" else (lock > current_price)):
                proposed, action, reason = lock, "LOCK_SMALL_PROFIT", "POSITIVE_R_PLUS_HEALTHY_CONTINUATION"
            else:
                action, reason = "HOLD", "HEALTHY_CONTINUATION_PROTECTION_ALREADY_EQUAL_OR_TIGHTER"
        elif continuation["state"] in {"STRONG_CONTINUATION", "HEALTHY_CONTINUATION"}:
            action, reason = "HOLD", "HEALTHY_CONTINUATION_ALLOWS_NORMAL_PULLBACK"
        elif exhaustion["state"] == "EXHAUSTION_CONFIRMED" and (target_state == "REJECTED" or continuation["state"] == "CONTINUATION_FAILED"):
            action, reason = "EXIT_RUNNER_EXHAUSTION", "STRUCTURE_OR_TARGET_SUPPORTED_EXHAUSTION"
        elif exhaustion["state"] in {"HIGH_EXHAUSTION", "MEANINGFUL_WARNING"} and giveback["state"] in {"SEVERE_GIVEBACK_WARNING", "UNACCEPTABLE_GIVEBACK"}:
            lock = entry_price + config.small_profit_lock_r*abs(entry_price-initial_stop) if direction == "BULLISH" else entry_price-config.small_profit_lock_r*abs(entry_price-initial_stop)
            if _tightens(direction, lock, current_protection) and ((lock < current_price) if direction == "BULLISH" else (lock > current_price)):
                proposed, action, reason = lock, "AGGRESSIVE_EXHAUSTION_PROTECTION", "MATURE_TRADE_SEVERE_GIVEBACK_AND_EXHAUSTION"
            else:
                action, reason = "HOLD_WITH_PROTECTION", "NO_VALID_TIGHTER_STRUCTURE_AVAILABLE"
        elif maturity == "PROFIT_OPPORTUNITY" and continuation["continuation_score"] >= 65.0:
            action, reason = "HOLD", "PROGRESS_WITHOUT_PROVEN_STRUCTURE"
        elif giveback["state"] in {"ELEVATED_GIVEBACK", "SEVERE_GIVEBACK_WARNING"}:
            action, reason = "HOLD_WITH_PROTECTION", "GIVEBACK_MONITORED_WITHOUT_PANIC_EXIT"
        return {"owner": self.owner, "action": action, "reason": reason, "previous_protection": current_protection, "selected_protection": proposed, "protection_tightened": _tightens(direction, proposed, current_protection), "protection_never_widened": not _tightens(direction, current_protection, proposed), "commit_count": 1, "maturity": maturity, "causal_valid": True}


def simulate_patched_profit_management(*, direction: str, entry_price: float, initial_stop: float, candles: pd.DataFrame, tp1_target: Optional[float], emergency_stop: Optional[float] = None, trail_events: Iterable[Mapping[str, Any]] = (), opposing_bos_events: Iterable[int] = (), config: FidelityPatchConfig = DEFAULT_PATCH_CONFIG) -> Dict[str, Any]:
    if candles.empty:
        raise ValueError("closed management candles are required")
    direction = direction.upper()
    risk = abs(entry_price-initial_stop)
    if risk <= 0: raise ValueError("initial risk must be positive")
    trails = {int(e["proof_index"]): float(e["selected_protection"]) for e in trail_events if e.get("state") == "TRAIL_PROVEN" and e.get("proof_index") is not None}
    opposing_bos_indexes = {int(index) for index in opposing_bos_events}
    continuation_engine, giveback_engine, exhaustion_engine, manager = ContinuationQualityEngine(config), GivebackControlEngine(config), ExhaustionEngine(config), TradeManagementCoordinator()
    current_protection = float(initial_stop)
    peak_r, prev_state, pending, failed_extensions = 0.0, "NOT_ESTABLISHED", 0, 0
    history = []
    exit_index, exit_price, exit_reason = len(candles)-1, _f(candles.iloc[-1]["close"]), "OPEN_AT_REVIEW_END"
    target_state = "CREATED"
    partial_filled = False
    partial_fraction = 0.50 if config.partial_exit_research else 0.0
    partial_r = 0.0
    for i, row in candles.reset_index(drop=True).iterrows():
        close, high, low = _f(row["close"]), _f(row["high"]), _f(row["low"])
        current_r = (close-entry_price)/risk if direction == "BULLISH" else (entry_price-close)/risk
        peak_r = max(peak_r, (high-entry_price)/risk if direction == "BULLISH" else (entry_price-low)/risk)
        if tp1_target is not None:
            touched = high >= tp1_target if direction == "BULLISH" else low <= tp1_target
            body = close >= tp1_target if direction == "BULLISH" else close <= tp1_target
            if touched and not partial_filled and partial_fraction > 0:
                partial_filled = True
                partial_r = ((tp1_target-entry_price)/risk if direction == "BULLISH" else (entry_price-tp1_target)/risk)
            if body: target_state = "BODY_CLOSED_THROUGH"
            elif touched: target_state = "WICK_TOUCHED"
            elif target_state in {"WICK_TOUCHED", "BODY_CLOSED_THROUGH"}: target_state = "REJECTED"
        window = candles.reset_index(drop=True).iloc[:i+1]
        cont = continuation_engine.evaluate(direction=direction, entry_price=entry_price, initial_risk=risk, candles=window, current_protection=current_protection, target_state=target_state, previous_state=prev_state, pending_state_count=pending)
        prev_state, pending = cont["state"], int(cont["pending_state_count"])
        if i >= 2:
            prior_extreme = float(window.iloc[:-1]["high"].max()) if direction == "BULLISH" else float(window.iloc[:-1]["low"].min())
            extended = high > prior_extreme if direction == "BULLISH" else low < prior_extreme
            failed_extensions = 0 if extended else failed_extensions+1
        maturity = trade_maturity(current_r=current_r, target_state=target_state, continuation_state=cont["state"], proven_trail=i in trails)
        protection_intact = close > current_protection if direction == "BULLISH" else close < current_protection
        giveback = giveback_engine.evaluate(current_r=current_r, peak_r=peak_r, maturity=maturity, continuation_state=cont["state"], protection_intact=protection_intact)
        opposing = bool((close < _f(row["open"]) and abs(close-_f(row["open"])) > risk*0.35) if direction == "BULLISH" else (close > _f(row["open"]) and abs(close-_f(row["open"])) > risk*0.35))
        exhaustion = exhaustion_engine.evaluate(continuation=cont, giveback=giveback, target_state=target_state, failed_extensions=failed_extensions, opposing_displacement=opposing, protection_intact=protection_intact)
        emergency_hit = emergency_stop is not None and (low <= emergency_stop if direction == "BULLISH" else high >= emergency_stop)
        logical_invalidated = i > 0 and ((close < current_protection and close < _f(row["open"])) if direction == "BULLISH" else (close > current_protection and close > _f(row["open"])))
        decision = manager.decide(direction=direction, current_price=close, current_protection=current_protection, initial_stop=initial_stop, entry_price=entry_price, maturity=maturity, continuation=cont, giveback=giveback, exhaustion=exhaustion, target_state=target_state, proven_trail=trails.get(i), emergency_hit=emergency_hit, logical_invalidated=logical_invalidated, opposing_bos_exit=i in opposing_bos_indexes, config=config)
        current_protection = float(decision["selected_protection"])
        history.append({"index": int(i), "close": close, "target_state": target_state, "maturity": maturity, "continuation": cont, "giveback": giveback, "exhaustion": exhaustion, "opposing_bos_exit": i in opposing_bos_indexes, "decision": decision, "protection": current_protection})
        if decision["action"].startswith("EXIT"):
            exit_index, exit_price, exit_reason = int(i), (float(emergency_stop) if emergency_hit else close), decision["action"]
            break
    runner_r = (exit_price-entry_price)/risk if direction == "BULLISH" else (entry_price-exit_price)/risk
    final_r = partial_fraction*partial_r + (1.0-partial_fraction)*runner_r if partial_filled else runner_r
    giveback_r = max(0.0, peak_r-final_r)
    return {"owner": "TradeManagementCoordinator", "state": "EXITED" if exit_reason != "OPEN_AT_REVIEW_END" else "OPEN", "history": history, "initial_protection": initial_stop, "final_protection": current_protection, "protection_never_loosened": all(not h["decision"]["protection_never_widened"] is False for h in history), "tp1_partial_filled": partial_filled, "tp1_partial_fraction": partial_fraction if partial_filled else 0.0, "partial_R": partial_r if partial_filled else None, "runner_R": runner_r, "peak_R": peak_r, "final_R": final_r, "giveback_R": giveback_r, "capture_ratio": final_r/peak_r if peak_r > 0 else 0.0, "exit_index": exit_index, "exit_price": exit_price, "exit_reason": exit_reason, "single_action_per_event": all(h["decision"]["commit_count"] == 1 for h in history), "closed_candle_evidence_only": True, "future_data_used": False, "order_api_called": False, "causal_valid": True}
