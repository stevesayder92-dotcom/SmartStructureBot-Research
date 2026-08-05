from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any, Dict, Iterable, Optional

import pandas as pd

from core.impulse_cycle import (
    DecisionProtectionPolicy,
    DecisionProtectionSelector,
    ImpulseCycleEngine,
    compare_protection_policies,
)


RETRACEMENT_STATES = {
    "NO_POST_BOS_COUNTER_MOVE",
    "MICRO_COUNTER_NOISE",
    "RETRACEMENT_CANDIDATE",
    "WAITING_FOR_COUNTER_STRUCTURE",
    "QUALIFIED_RETRACEMENT",
    "WAITING_FOR_FAILURE_TRIGGER",
    "ENTRY_CANDIDATE",
    "ENTRY_VALIDATED",
    "CONSUMED",
    "INVALIDATED_BY_PROTECTED_SWING",
    "EXPIRED",
}


@dataclass(frozen=True)
class QualifiedRetracementPolicy:
    model: str = "HYBRID"
    minimum_internal_importance: float = 3.0
    relative_range_threshold: float = 1.35
    atr_displacement_threshold: float = 0.85
    strong_atr_displacement: float = 1.35
    minimum_persistence_candles: int = 2
    maximum_overlap_ratio: float = 0.80
    hybrid_qualification_score: float = 60.0
    protected_close_requires_direction: bool = True
    maximum_origin_candidates: int = 12

    def __post_init__(self) -> None:
        allowed = {
            "FIRST_COUNTER_BREAK",
            "FIRST_COUNTER_STRUCTURE",
            "RELATIVE_RANGE",
            "ATR_AND_STRUCTURE",
            "HYBRID",
        }
        if self.model not in allowed:
            raise ValueError(
                f"Unknown qualification model {self.model!r}"
            )


class CounterMoveSignificance:
    """Explainable, impulse-relative counter-move comparison."""

    def __init__(
        self,
        data: pd.DataFrame,
        policy: QualifiedRetracementPolicy,
    ) -> None:
        self.data = data
        self.policy = policy

    def assess(
        self,
        *,
        trend: str,
        origin_index: int,
        candidate_index: int,
        as_of_index: int,
        structure_break_count: int,
        counter_structure_count: int,
    ) -> Dict[str, Any]:
        prior_moves = self._prior_micro_moves(
            trend=trend,
            start=origin_index + 1,
            end=candidate_index - 1,
        )
        candidate_range = self._counter_excursion(
            trend=trend,
            start=origin_index,
            candidate=candidate_index,
            end=as_of_index,
        )
        baseline = (
            median(prior_moves)
            if prior_moves
            else self._atr(origin_index, candidate_index)
        )
        relative_ratio = (
            candidate_range / baseline
            if baseline > 0
            else 0.0
        )
        atr = self._atr(
            max(origin_index, candidate_index - 20),
            candidate_index,
        )
        atr_normalized = (
            candidate_range / atr if atr > 0 else 0.0
        )
        duration = as_of_index - candidate_index + 1
        overlap = self._overlap_ratio(
            candidate_index,
            as_of_index,
        )
        body_distance = self._directional_body_distance(
            trend,
            candidate_index,
            as_of_index,
        )
        raw_score = 0.0
        reasons: list[str] = []

        if structure_break_count:
            raw_score += 30.0
            reasons.append(
                f"Counter move broke {structure_break_count} "
                "approved internal continuation structure(s)"
            )
        if relative_ratio >= self.policy.relative_range_threshold:
            raw_score += min(25.0, 15.0 * relative_ratio)
            reasons.append(
                f"Candidate is {relative_ratio:.2f}x the "
                "prior micro-correction baseline"
            )
        else:
            reasons.append(
                f"Relative size {relative_ratio:.2f}x is below "
                f"{self.policy.relative_range_threshold:.2f}x"
            )
        if atr_normalized >= self.policy.atr_displacement_threshold:
            raw_score += min(20.0, 12.0 * atr_normalized)
            reasons.append(
                f"Excursion is {atr_normalized:.2f} ATR"
            )
        if duration >= self.policy.minimum_persistence_candles:
            raw_score += 10.0
            reasons.append(
                f"Counter move persisted {duration} candles"
            )
        if overlap <= self.policy.maximum_overlap_ratio:
            raw_score += 8.0
            reasons.append(
                f"Overlap ratio {overlap:.2f} shows displacement"
            )
        if counter_structure_count:
            raw_score += min(
                20.0,
                12.0 + 4.0 * counter_structure_count,
            )
            reasons.append(
                f"{counter_structure_count} causal counter-structure "
                "point(s) support intent"
            )

        if not structure_break_count:
            classification = "MICRO_NOISE"
        elif (
            raw_score >= self.policy.hybrid_qualification_score
            and counter_structure_count > 0
        ):
            classification = "QUALIFIED_RETRACEMENT"
        else:
            classification = "EMERGING_COUNTER_MOVE"

        return {
            "significance_score": round(
                min(100.0, raw_score),
                3,
            ),
            "raw_significance_score": round(raw_score, 3),
            "score_minimum": 0.0,
            "score_maximum": 100.0,
            "score_contract": (
                "DISPLAY_SCORE_CAPPED_0_100_"
                "RAW_SCORE_PRESERVED"
            ),
            "relative_size_ratio": round(relative_ratio, 6),
            "prior_micro_move_count": len(prior_moves),
            "prior_micro_median_excursion": (
                round(float(median(prior_moves)), 8)
                if prior_moves
                else None
            ),
            "prior_micro_max_excursion": (
                round(max(prior_moves), 8)
                if prior_moves
                else None
            ),
            "candidate_range": round(candidate_range, 8),
            "candidate_directional_body_distance": round(
                body_distance,
                8,
            ),
            "atr_normalized_displacement": round(
                atr_normalized,
                6,
            ),
            "duration_candles": duration,
            "overlap_ratio": round(overlap, 6),
            "structure_break_count": structure_break_count,
            "counter_structure_count": counter_structure_count,
            "classification": classification,
            "reason": reasons,
        }

    def _prior_micro_moves(
        self,
        *,
        trend: str,
        start: int,
        end: int,
    ) -> list[float]:
        if end < start:
            return []
        moves: list[float] = []
        active_start: Optional[int] = None
        for index in range(start, end + 1):
            opposite = self._is_opposite_candle(trend, index)
            if opposite and active_start is None:
                active_start = index
            if not opposite and active_start is not None:
                moves.append(
                    self._run_excursion(
                        trend,
                        active_start,
                        index - 1,
                    )
                )
                active_start = None
        if active_start is not None:
            moves.append(
                self._run_excursion(trend, active_start, end)
            )
        return [move for move in moves if move > 0]

    def _is_opposite_candle(
        self,
        trend: str,
        index: int,
    ) -> bool:
        open_price = float(self.data.at[index, "open"])
        close_price = float(self.data.at[index, "close"])
        return (
            close_price < open_price
            if trend == "BULLISH"
            else close_price > open_price
        )

    def _run_excursion(
        self,
        trend: str,
        start: int,
        end: int,
    ) -> float:
        frame = self.data.iloc[start : end + 1]
        if frame.empty:
            return 0.0
        if trend == "BULLISH":
            return max(
                0.0,
                float(self.data.at[start, "open"])
                - float(frame["low"].min()),
            )
        return max(
            0.0,
            float(frame["high"].max())
            - float(self.data.at[start, "open"]),
        )

    def _counter_excursion(
        self,
        *,
        trend: str,
        start: int,
        candidate: int,
        end: int,
    ) -> float:
        impulse = self.data.iloc[start : candidate + 1]
        counter = self.data.iloc[candidate : end + 1]
        if trend == "BULLISH":
            extreme = float(impulse["high"].max())
            return max(0.0, extreme - float(counter["low"].min()))
        extreme = float(impulse["low"].min())
        return max(0.0, float(counter["high"].max()) - extreme)

    def _directional_body_distance(
        self,
        trend: str,
        start: int,
        end: int,
    ) -> float:
        frame = self.data.iloc[start : end + 1]
        if frame.empty:
            return 0.0
        if trend == "BULLISH":
            return max(
                0.0,
                float(frame["open"].max())
                - float(frame["close"].min()),
            )
        return max(
            0.0,
            float(frame["close"].max())
            - float(frame["open"].min()),
        )

    def _atr(self, start: int, end: int) -> float:
        frame = self.data.iloc[max(0, start) : end + 1]
        if frame.empty:
            return 0.0
        return float((frame["high"] - frame["low"]).median())

    def _overlap_ratio(self, start: int, end: int) -> float:
        if end <= start:
            return 1.0
        overlaps = 0
        comparisons = 0
        for index in range(start + 1, end + 1):
            previous_low = float(self.data.at[index - 1, "low"])
            previous_high = float(self.data.at[index - 1, "high"])
            low = float(self.data.at[index, "low"])
            high = float(self.data.at[index, "high"])
            comparisons += 1
            if min(previous_high, high) > max(previous_low, low):
                overlaps += 1
        return overlaps / comparisons if comparisons else 1.0


class QualifiedRetracementEngine:
    """
    Single owner of post-origin retracement genesis and entry structure.

    It deliberately ignores every pre-origin counter move.
    """

    def __init__(
        self,
        data: pd.DataFrame,
        *,
        as_of_index: Optional[int] = None,
        policy: Optional[QualifiedRetracementPolicy] = None,
        symbol: str = "UNKNOWN",
        timeframe: str = "UNKNOWN",
        protection_policy: str = "ORIGIN_DEFENDING_SWING",
    ) -> None:
        if (
            isinstance(data.index, pd.RangeIndex)
            and data.index.start == 0
            and data.index.step == 1
        ):
            self.data = data
        else:
            self.data = data.reset_index(drop=True)
        self.as_of_index = (
            len(self.data) - 1
            if as_of_index is None
            else int(as_of_index)
        )
        if not 0 <= self.as_of_index < len(self.data):
            raise IndexError("Qualified retracement as_of_index is invalid")
        self.policy = policy or QualifiedRetracementPolicy()
        self.symbol = str(symbol)
        self.timeframe = str(timeframe)
        self.protection_policy = DecisionProtectionPolicy(
            name=protection_policy
        )
        self.significance = CounterMoveSignificance(
            self.data,
            self.policy,
        )

    def analyze(
        self,
        *,
        trend: str,
        structure_points: Iterable[Dict[str, Any]],
        bos_events: Iterable[Dict[str, Any]],
        protected_structure: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        points = [
            dict(point)
            for point in structure_points
            if self._available(point)
        ]
        events = [
            dict(event)
            for event in bos_events
            if self._available(event)
        ]
        result = self._base(trend)
        if trend not in {"BULLISH", "BEARISH"}:
            result["reason"].append("No dominant directional trend")
            return result

        origins = self._origin_candidates(trend, events)
        if not origins:
            result["reason"].append(
                "No causal same-direction BOS can own an impulse leg"
            )
            return result

        selected: Optional[tuple[Dict[str, Any], Dict[str, Any]]] = None
        for origin in reversed(
            origins[-self.policy.maximum_origin_candidates :]
        ):
            candidate = self._first_counter_break(
                trend=trend,
                origin=origin,
                points=points,
            )
            if candidate is not None:
                selected = (origin, candidate)
                break

        if selected is None:
            origin = origins[-1]
            result["setup_origin_bos"] = self._origin_contract(origin)
            result["origin_bos_index"] = int(origin["index"])
            noise = self._has_opposing_noise(
                trend,
                int(origin["index"]) + 1,
                self.as_of_index,
            )
            result["state"] = (
                "MICRO_COUNTER_NOISE"
                if noise
                else "NO_POST_BOS_COUNTER_MOVE"
            )
            result["reason"].append(
                "Opposing movement did not close through an approved "
                "internal continuation structure"
            )
            return result

        origin, candidate = selected
        origin_index = int(origin["index"])
        candidate_index = int(candidate["break_index"])
        result["setup_origin_bos"] = self._origin_contract(origin)
        result["origin_bos_index"] = origin_index
        result["candidate_start_index"] = candidate_index
        result["first_candidate_index"] = candidate_index
        result["qualified_retracement_start_index"] = candidate_index
        result["current_pullback_end"] = self.as_of_index
        result["broken_internal_structure"] = dict(
            candidate["structure"]
        )
        result["candidate"] = {
            "candidate_start_index": candidate_index,
            "detected_at_index": candidate_index,
            "confirmed_at_index": candidate_index,
            "decision_available_at_index": candidate_index,
            "broken_internal_structure": dict(candidate["structure"]),
            "break_distance": candidate["break_distance"],
            "candle_direction": candidate["candle_direction"],
            "displacement": candidate["displacement"],
            "protected_swing_status": "PENDING",
            "causal_valid": True,
        }

        impulse_cycle = ImpulseCycleEngine(
            symbol=self.symbol,
            timeframe=self.timeframe,
        ).build(
            trend=trend,
            origin_bos=origin,
            structure_points=points,
            bos_events=events,
            as_of_index=self.as_of_index,
            qualified_retracement_start_index=candidate_index,
        )
        result["impulse_cycle"] = impulse_cycle
        protected = DecisionProtectionSelector(
            policy=self.protection_policy
        ).select(
            cycle=impulse_cycle,
            trend=trend,
            structure_points=points,
            bos_events=events,
            as_of_index=self.as_of_index,
            current_price=float(
                origin.get(
                    "break_price",
                    self.data.at[origin_index, "close"],
                )
            ),
            entry_index=self.as_of_index,
        )
        result["protection_policy_comparison"] = (
            compare_protection_policies(
                cycle=impulse_cycle,
                trend=trend,
                structure_points=points,
                bos_events=events,
                as_of_index=self.as_of_index,
                current_price=float(
                    origin.get(
                        "break_price",
                        self.data.at[origin_index, "close"],
                    )
                ),
                entry_index=self.as_of_index,
            )
        )
        result["decision_protected_swing"] = protected
        if not protected.get("available"):
            result["state"] = "RETRACEMENT_CANDIDATE"
            result["reason"].append(
                "WAITING_FOR_VALID_DECISION_PROTECTION"
            )
            return result

        invalidation_evidence = (
            self._protected_violation_evidence(
                trend=trend,
                protected=protected,
                start=candidate_index,
            )
        )
        invalidated_at = (
            invalidation_evidence.get("index")
            if invalidation_evidence
            else None
        )
        result["protected_swing_invalidation"] = (
            invalidation_evidence
        )
        result["protected_wick_crossings"] = (
            self._protected_wick_crossings(
                trend=trend,
                protected=protected,
                start=candidate_index,
            )
        )
        result["protected_swing_intact"] = invalidated_at is None
        result["protected_swing_invalidated_at"] = invalidated_at
        result["candidate"]["protected_swing_status"] = (
            "INTACT" if invalidated_at is None else "INVALIDATED"
        )
        if invalidated_at is not None:
            result["state"] = "INVALIDATED_BY_PROTECTED_SWING"
            result["reason"].append(
                "Directional body close violated dominant protection"
            )
            return result

        counter_points = self._counter_structure(
            trend=trend,
            candidate_index=candidate_index,
            points=points,
        )
        result["counter_structure_points"] = counter_points
        result["setup_invalidation"] = self._setup_invalidation(
            trend=trend,
            candidate_index=candidate_index,
            points=counter_points,
        )
        break_count = self._structure_break_count(
            trend=trend,
            candidate_index=candidate_index,
            points=points,
            origin_index=origin_index,
        )
        significance = self.significance.assess(
            trend=trend,
            origin_index=origin_index,
            candidate_index=candidate_index,
            as_of_index=self.as_of_index,
            structure_break_count=break_count,
            counter_structure_count=len(counter_points),
        )
        result["significance"] = significance
        qualified = self._qualified(
            significance=significance,
            counter_points=counter_points,
        )
        if not qualified:
            result["state"] = (
                "WAITING_FOR_COUNTER_STRUCTURE"
                if candidate_index < self.as_of_index
                else "RETRACEMENT_CANDIDATE"
            )
            result["reason"].extend(significance["reason"])
            return result

        qualification_index = (
            self._first_qualification_index(
                trend=trend,
                origin_index=origin_index,
                candidate_index=candidate_index,
                points=points,
                counter_points=counter_points,
                current_significance=significance,
            )
        )
        result["qualified"] = True
        result["qualification_index"] = qualification_index
        result["first_qualification_index"] = (
            qualification_index
        )
        result["qualification_available_at_index"] = qualification_index
        result["state"] = "QUALIFIED_RETRACEMENT"
        result["reason"].extend(significance["reason"])
        result["reason"].append(
            f"Qualification model {self.policy.model} accepted the candidate"
        )

        trigger_history = self._failure_trigger_history(
            trend=trend,
            qualification_index=qualification_index,
            points=counter_points,
            origin_index=origin_index,
            candidate_index=candidate_index,
        )
        initial_trigger = (
            trigger_history[0]["trigger"]
            if trigger_history
            else None
        )
        trigger = (
            trigger_history[-1]["trigger"]
            if trigger_history
            else None
        )
        result["failure_trigger_history"] = trigger_history
        result["initial_failure_trigger"] = initial_trigger
        result["initial_failure_trigger_index"] = (
            initial_trigger.get("index")
            if initial_trigger
            else None
        )
        result["active_failure_trigger"] = trigger
        result["active_failure_trigger_index"] = (
            trigger.get("index") if trigger else None
        )
        result["active_failure_trigger_level"] = (
            trigger.get("level") if trigger else None
        )
        result["trigger_updated_at_index"] = (
            trigger_history[-1]["selected_at_index"]
            if trigger_history
            else None
        )
        result["trigger_update_count"] = max(
            0,
            len(trigger_history) - 1,
        )
        result["failure_trigger"] = trigger
        if trigger is None:
            result["state"] = "WAITING_FOR_FAILURE_TRIGGER"
            result["reason"].append(
                "No post-qualification counter-trend failure trigger"
            )
            return result

        result["state"] = "WAITING_FOR_FAILURE_TRIGGER"
        if self._entry_break(trend, trigger):
            result["state"] = "ENTRY_CANDIDATE"
            result["entry_ready"] = True
            result["entry_index"] = self.as_of_index
            result["entry_price"] = float(
                self.data.at[self.as_of_index, "close"]
            )
            result["continuation_bos"] = self._entry_bos(
                trend=trend,
                trigger=trigger,
                protected=protected,
                setup_invalidation=result.get(
                    "setup_invalidation"
                ),
            )
            result["reason"].append(
                "Current directional body close broke the qualified "
                "retracement failure trigger"
            )
        return result

    def _base(self, trend: str) -> Dict[str, Any]:
        return {
            "availability": "AVAILABLE",
            "available": True,
            "owner": "QualifiedRetracementEngine",
            "model": self.policy.model,
            "trend": trend,
            "state": "NO_POST_BOS_COUNTER_MOVE",
            "as_of_index": self.as_of_index,
            "causal_valid": True,
            "current_candle_only": True,
            "setup_origin_bos": None,
            "origin_bos_index": None,
            "candidate_start_index": None,
            "first_candidate_index": None,
            "qualified_retracement_start_index": None,
            "current_pullback_end": None,
            "qualification_index": None,
            "first_qualification_index": None,
            "qualification_available_at_index": None,
            "broken_internal_structure": None,
            "candidate": None,
            "significance": None,
            "decision_protected_swing": None,
            "impulse_cycle": None,
            "protection_policy_comparison": {},
            "setup_invalidation": None,
            "protected_swing_intact": None,
            "protected_swing_invalidated_at": None,
            "protected_swing_invalidation": None,
            "protected_wick_crossings": [],
            "counter_structure_points": [],
            "failure_trigger": None,
            "failure_trigger_history": [],
            "initial_failure_trigger": None,
            "initial_failure_trigger_index": None,
            "active_failure_trigger": None,
            "active_failure_trigger_index": None,
            "active_failure_trigger_level": None,
            "trigger_updated_at_index": None,
            "trigger_update_count": 0,
            "qualified": False,
            "entry_ready": False,
            "entry_index": None,
            "entry_price": None,
            "continuation_bos": None,
            "reason": [],
        }

    def _origin_candidates(
        self,
        trend: str,
        events: list[Dict[str, Any]],
    ) -> list[Dict[str, Any]]:
        expected = "BULLISH_BOS" if trend == "BULLISH" else "BEARISH_BOS"
        return sorted(
            [
                event
                for event in events
                if event.get("type") == expected
                and event.get("index") is not None
                and int(event["index"]) < self.as_of_index
                and event.get("bos_role") != "EXTENSION_BOS"
            ],
            key=lambda event: int(event["index"]),
        )

    def _first_counter_break(
        self,
        *,
        trend: str,
        origin: Dict[str, Any],
        points: list[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        origin_index = int(origin["index"])
        side = "LOW" if trend == "BULLISH" else "HIGH"
        structures = [
            point
            for point in points
            if point.get("side") == side
            and int(point.get("index", -1)) >= origin_index
            and self._importance(point)
            >= self.policy.minimum_internal_importance
        ]
        breaks: list[Dict[str, Any]] = []
        for point in structures:
            level = point.get("body_price", point.get("price"))
            if not isinstance(level, (int, float)):
                continue
            available = self._availability(point)
            start = max(origin_index + 1, int(point["index"]) + 1, available)
            frame = self.data.iloc[
                start : self.as_of_index + 1
            ]
            if frame.empty:
                continue
            mask = (
                (frame["close"] < frame["open"])
                & (frame["close"] < float(level))
                if trend == "BULLISH"
                else (frame["close"] > frame["open"])
                & (frame["close"] > float(level))
            )
            matched = frame.index[mask]
            if len(matched) == 0:
                continue
            index = int(matched[0])
            close = float(self.data.at[index, "close"])
            candle_range = float(
                self.data.at[index, "high"]
                - self.data.at[index, "low"]
            )
            breaks.append(
                {
                    "break_index": index,
                    "structure": self._internal_contract(
                        point,
                        origin_index,
                    ),
                    "break_distance": abs(close - float(level)),
                    "candle_direction": (
                        "BEARISH" if trend == "BULLISH" else "BULLISH"
                    ),
                    "displacement": candle_range,
                }
            )
        if not breaks:
            return None
        return sorted(
            breaks,
            key=lambda item: (
                item["break_index"],
                -float(item["structure"]["importance"]),
                -int(item["structure"]["index"]),
            ),
        )[0]

    def _internal_contract(
        self,
        point: Dict[str, Any],
        origin_index: int,
    ) -> Dict[str, Any]:
        return {
            "type": str(point.get("type")),
            "side": str(point.get("side")),
            "index": int(point["index"]),
            "price": float(
                point.get("body_price", point.get("price"))
            ),
            "confirmed_at_index": self._availability(point),
            "tradeable_at_index": int(
                point.get("tradeable_at_index")
                or self._availability(point)
            ),
            "origin_bos_index": origin_index,
            "role": "INTERNAL_CONTINUATION_STRUCTURE",
            "importance": self._importance(point),
            "causal_valid": True,
        }

    def _resolve_protected_swing(
        self,
        *,
        trend: str,
        origin: Dict[str, Any],
        points: list[Dict[str, Any]],
        supplied: Dict[str, Any],
        previous_origin_index: Optional[int],
    ) -> Dict[str, Any]:
        origin_index = int(origin["index"])
        impulse_cycle_start = (
            int(previous_origin_index)
            if previous_origin_index is not None
            else 0
        )
        expected_side = "LOW" if trend == "BULLISH" else "HIGH"
        expected_type = "HL" if trend == "BULLISH" else "LH"
        supplied_point = (
            supplied.get("protected_low")
            if trend == "BULLISH"
            else supplied.get("protected_high")
        )
        candidates = [
            point
            for point in points
            if point.get("side") == expected_side
            and int(point.get("index", origin_index)) < origin_index
            and self._available(point)
        ]
        if (
            isinstance(supplied_point, dict)
            and supplied_point.get("index") is not None
            and int(supplied_point["index"]) < origin_index
            and self._available(supplied_point)
        ):
            candidates.append(dict(supplied_point))
        if not candidates:
            return {
                "available": False,
                "role": "DOMINANT_PROTECTED_SWING",
                "reason": ["No causal pre-origin protected swing"],
            }
        chosen = sorted(
            candidates,
            key=lambda point: (
                point.get("type") == expected_type,
                int(point.get("index", -1)),
                self._importance(point),
            ),
        )[-1]
        level = chosen.get("body_price", chosen.get("price"))
        newer_candidates = [
            point
            for point in candidates
            if int(point.get("index", -1))
            > int(chosen["index"])
            and int(point.get("index", -1)) < origin_index
        ]
        belongs_to_cycle = (
            int(chosen["index"]) >= impulse_cycle_start
        )
        return {
            "available": isinstance(level, (int, float)),
            "type": chosen.get("type"),
            "side": expected_side,
            "index": int(chosen["index"]),
            "level": float(level) if isinstance(level, (int, float)) else None,
            "confirmed_at_index": self._availability(chosen),
            "decision_available_at_index": (
                self._availability(chosen)
            ),
            "origin_bos_index": origin_index,
            "impulse_cycle_start_index": impulse_cycle_start,
            "belongs_to_origin_impulse_cycle": (
                belongs_to_cycle
            ),
            "newer_valid_protected_swing_exists": bool(
                newer_candidates
            ),
            "newer_protected_swing_candidates": [
                {
                    "index": int(point["index"]),
                    "type": point.get("type"),
                    "level": point.get(
                        "body_price",
                        point.get("price"),
                    ),
                    "confirmed_at_index": (
                        self._availability(point)
                    ),
                }
                for point in newer_candidates
            ],
            "role": "DOMINANT_PROTECTED_SWING",
            "body_close_invalidation": True,
            "wick_invalidation": False,
            "causal_valid": True,
            "reason": [
                "Selected the latest meaningful expected-type protected "
                "swing preceding the origin BOS",
                (
                    "Protected swing belongs to the same impulse cycle"
                    if belongs_to_cycle
                    else "Protected swing predates the current impulse "
                    "cycle and requires manual review"
                ),
            ],
        }

    @staticmethod
    def _previous_origin_index(
        origins: list[Dict[str, Any]],
        origin_index: int,
    ) -> Optional[int]:
        previous = [
            int(item["index"])
            for item in origins
            if int(item["index"]) < origin_index
        ]
        return max(previous) if previous else None

    def _protected_violation(
        self,
        *,
        trend: str,
        protected: Dict[str, Any],
        start: int,
    ) -> Optional[int]:
        level = protected.get("level")
        if not isinstance(level, (int, float)):
            return None
        frame = self.data.iloc[start : self.as_of_index + 1]
        if frame.empty:
            return None
        broken = (
            frame["close"] < float(level)
            if trend == "BULLISH"
            else frame["close"] > float(level)
        )
        if self.policy.protected_close_requires_direction:
            directional = (
                frame["close"] < frame["open"]
                if trend == "BULLISH"
                else frame["close"] > frame["open"]
            )
            broken = broken & directional
        matched = frame.index[broken]
        return int(matched[0]) if len(matched) else None

    def _protected_violation_evidence(
        self,
        *,
        trend: str,
        protected: Dict[str, Any],
        start: int,
    ) -> Optional[Dict[str, Any]]:
        index = self._protected_violation(
            trend=trend,
            protected=protected,
            start=start,
        )
        if index is None:
            return None
        level = float(protected["level"])
        row = self.data.iloc[index]
        wick_crossed = (
            float(row["low"]) < level
            if trend == "BULLISH"
            else float(row["high"]) > level
        )
        return {
            "index": index,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "protected_level": level,
            "wick_crossed": wick_crossed,
            "body_close_crossed": True,
            "wick_only": False,
            "directional_body_close": True,
            "decision_available_at_index": index,
            "causal_valid": index <= self.as_of_index,
        }

    def _protected_wick_crossings(
        self,
        *,
        trend: str,
        protected: Dict[str, Any],
        start: int,
    ) -> list[Dict[str, Any]]:
        level = protected.get("level")
        if not isinstance(level, (int, float)):
            return []
        crossings: list[Dict[str, Any]] = []
        for index in range(start, self.as_of_index + 1):
            row = self.data.iloc[index]
            wick_crossed = (
                float(row["low"]) < float(level)
                if trend == "BULLISH"
                else float(row["high"]) > float(level)
            )
            body_crossed = (
                float(row["close"]) < float(level)
                if trend == "BULLISH"
                else float(row["close"]) > float(level)
            )
            if wick_crossed and not body_crossed:
                crossings.append(
                    {
                        "index": index,
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "protected_level": float(level),
                        "wick_only": True,
                        "survived": True,
                    }
                )
        return crossings

    def _counter_structure(
        self,
        *,
        trend: str,
        candidate_index: int,
        points: list[Dict[str, Any]],
    ) -> list[Dict[str, Any]]:
        types = {"LH", "LL"} if trend == "BULLISH" else {"HH", "HL"}
        return sorted(
            [
                dict(point)
                for point in points
                if point.get("type") in types
                and int(point.get("index", -1)) >= candidate_index
                and self._importance(point) >= 1.0
            ],
            key=lambda point: int(point["index"]),
        )

    def _structure_break_count(
        self,
        *,
        trend: str,
        candidate_index: int,
        points: list[Dict[str, Any]],
        origin_index: int,
    ) -> int:
        close = float(self.data.at[candidate_index, "close"])
        side = "LOW" if trend == "BULLISH" else "HIGH"
        return sum(
            1
            for point in points
            if point.get("side") == side
            and origin_index <= int(point.get("index", -1)) < candidate_index
            and self._importance(point)
            >= self.policy.minimum_internal_importance
            and isinstance(
                point.get("body_price", point.get("price")),
                (int, float),
            )
            and (
                close
                < float(point.get("body_price", point.get("price")))
                if trend == "BULLISH"
                else close
                > float(point.get("body_price", point.get("price")))
            )
        )

    def _qualified(
        self,
        *,
        significance: Dict[str, Any],
        counter_points: list[Dict[str, Any]],
    ) -> bool:
        model = self.policy.model
        if model == "FIRST_COUNTER_BREAK":
            return True
        if model == "FIRST_COUNTER_STRUCTURE":
            return bool(counter_points)
        if model == "RELATIVE_RANGE":
            return bool(
                significance["relative_size_ratio"]
                >= self.policy.relative_range_threshold
                and significance["duration_candles"]
                >= self.policy.minimum_persistence_candles
            )
        if model == "ATR_AND_STRUCTURE":
            return bool(
                significance["atr_normalized_displacement"]
                >= self.policy.atr_displacement_threshold
                and counter_points
            )
        return (
            significance["classification"]
            == "QUALIFIED_RETRACEMENT"
        )

    def _first_qualification_index(
        self,
        *,
        trend: str,
        origin_index: int,
        candidate_index: int,
        points: list[Dict[str, Any]],
        counter_points: list[Dict[str, Any]],
        current_significance: Dict[str, Any],
    ) -> int:
        break_count = self._structure_break_count(
            trend=trend,
            candidate_index=candidate_index,
            points=points,
            origin_index=origin_index,
        )
        for decision_index in range(
            candidate_index,
            self.as_of_index + 1,
        ):
            visible_counter = [
                point
                for point in counter_points
                if self._availability(point) <= decision_index
                and int(point.get("index", -1))
                <= decision_index
            ]
            significance = self.significance.assess(
                trend=trend,
                origin_index=origin_index,
                candidate_index=candidate_index,
                as_of_index=decision_index,
                structure_break_count=break_count,
                counter_structure_count=len(
                    visible_counter
                ),
            )
            if self._qualified(
                significance=significance,
                counter_points=visible_counter,
            ):
                return decision_index

        # The caller has already confirmed that the current state qualifies.
        # This defensive fallback preserves that outcome without backdating it.
        if self._qualified(
            significance=current_significance,
            counter_points=counter_points,
        ):
            return self.as_of_index
        raise RuntimeError(
            "Qualification index requested for an unqualified retracement"
        )

    def _failure_trigger(
        self,
        *,
        trend: str,
        qualification_index: int,
        points: list[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        expected_side = "HIGH" if trend == "BULLISH" else "LOW"
        expected_type = "LH" if trend == "BULLISH" else "HL"
        candidates = [
            point
            for point in points
            if point.get("side") == expected_side
            and int(point.get("index", -1)) >= qualification_index
            and self._availability(point) <= self.as_of_index
        ]
        preferred = [
            point
            for point in candidates
            if point.get("type") == expected_type
        ]
        selected = preferred or candidates
        if not selected:
            return None
        chosen = sorted(
            selected,
            key=lambda point: (
                self._importance(point),
                int(point["index"]),
            ),
        )[-1]
        level = chosen.get("body_price", chosen.get("price"))
        if not isinstance(level, (int, float)):
            return None
        return {
            "type": chosen.get("type"),
            "side": expected_side,
            "index": int(chosen["index"]),
            "level": float(level),
            "confirmed_at_index": self._availability(chosen),
            # Keep the early, causal fractal observation separate from the
            # later locked-structure confirmation.  Phase 5B collapsed these
            # into one timestamp, which made a visually obvious pullback
            # swing look as if it did not exist until the entry candle.
            #
            # This is evidence only: the locked-structure rule remains the
            # active trigger policy until Steve labels the same examples.
            "fractal_confirmed_at_index": chosen.get(
                "fractal_confirmed_at_index"
            ),
            "structural_confirmed_at_index": self._availability(chosen),
            "tradeable_at_index": int(
                chosen.get("tradeable_at_index")
                or self._availability(chosen)
            ),
            "confirmation_policy": "LOCKED_STRUCTURE_ONLY",
            "qualification_index": qualification_index,
            "first_qualification_index": qualification_index,
            "role": "QUALIFIED_RETRACEMENT_FAILURE_TRIGGER",
            "causal_valid": True,
        }

    def _failure_trigger_history(
        self,
        *,
        trend: str,
        qualification_index: int,
        points: list[Dict[str, Any]],
        origin_index: int,
        candidate_index: int,
    ) -> list[Dict[str, Any]]:
        history: list[Dict[str, Any]] = []
        previous_key: Optional[tuple[Any, ...]] = None
        for decision_index in range(
            qualification_index,
            self.as_of_index + 1,
        ):
            visible = [
                point
                for point in points
                if int(point.get("index", -1))
                <= decision_index
                and self._availability(point)
                <= decision_index
            ]
            trigger = self._failure_trigger(
                trend=trend,
                qualification_index=qualification_index,
                points=visible,
            )
            if trigger is None:
                continue
            trigger.update(
                {
                    "origin_bos_index": origin_index,
                    "first_candidate_index": candidate_index,
                    "belongs_to_same_qualified_retracement": True,
                }
            )
            key = (
                trigger.get("index"),
                trigger.get("level"),
                trigger.get("type"),
            )
            if key == previous_key:
                continue
            history.append(
                {
                    "selected_at_index": decision_index,
                    "trigger": trigger,
                }
            )
            previous_key = key
        return history

    def _entry_break(
        self,
        trend: str,
        trigger: Dict[str, Any],
    ) -> bool:
        close = float(self.data.at[self.as_of_index, "close"])
        open_price = float(self.data.at[self.as_of_index, "open"])
        level = float(trigger["level"])
        return (
            close > open_price and close > level
            if trend == "BULLISH"
            else close < open_price and close < level
        )

    def _entry_bos(
        self,
        *,
        trend: str,
        trigger: Dict[str, Any],
        protected: Dict[str, Any],
        setup_invalidation: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        close = float(self.data.at[self.as_of_index, "close"])
        invalidation = setup_invalidation or {}
        return {
            "type": (
                "BULLISH_ENTRY_BOS"
                if trend == "BULLISH"
                else "BEARISH_ENTRY_BOS"
            ),
            "index": self.as_of_index,
            "break_price": close,
            "entry_price": close,
            "broken_structure_index": trigger["index"],
            "broken_structure_confirmed_at_index": trigger[
                "confirmed_at_index"
            ],
            "broken_structure_price": trigger["level"],
            "broken_structure_type": trigger["type"],
            "bos_role": "QUALIFIED_RETRACEMENT_FAILURE_BOS",
            "entry_quality": "QUALIFIED_STRUCTURE",
            "entry_confidence_score": 100,
            "decision_available_at_index": self.as_of_index,
            "break_semantics": "DIRECTIONAL_CLOSE_ONLY",
            "decision_protection_level": protected.get("level"),
            "setup_invalidation_level": invalidation.get("level"),
            "setup_invalidation_index": invalidation.get("index"),
            "setup_invalidation_type": invalidation.get("type"),
            "setup_invalidation_intact_at_entry": True,
            "causal_valid": True,
            "current_candle_only": True,
        }

    def _setup_invalidation(
        self,
        *,
        trend: str,
        candidate_index: int,
        points: list[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        side = "LOW" if trend == "BULLISH" else "HIGH"
        candidates = [
            point
            for point in points
            if point.get("side") == side
            and int(point.get("index", -1)) >= candidate_index
            and isinstance(
                point.get("body_price", point.get("price")),
                (int, float),
            )
        ]
        if not candidates:
            return None
        chosen = (
            min(
                candidates,
                key=lambda point: float(
                    point.get("body_price", point.get("price"))
                ),
            )
            if trend == "BULLISH"
            else max(
                candidates,
                key=lambda point: float(
                    point.get("body_price", point.get("price"))
                ),
            )
        )
        return {
            "type": chosen.get("type"),
            "side": side,
            "index": int(chosen["index"]),
            "level": float(
                chosen.get("body_price", chosen.get("price"))
            ),
            "confirmed_at_index": self._availability(chosen),
            "role": "SETUP_INVALIDATION_STRUCTURE",
            "body_close_invalidation": True,
            "causal_valid": True,
        }

    def _has_opposing_noise(
        self,
        trend: str,
        start: int,
        end: int,
    ) -> bool:
        return any(
            self.significance._is_opposite_candle(trend, index)
            for index in range(max(0, start), end + 1)
        )

    def _origin_contract(
        self,
        origin: Dict[str, Any],
    ) -> Dict[str, Any]:
        index = int(origin["index"])
        available = int(
            origin.get("decision_available_at_index", index)
        )
        return {
            **origin,
            "index": index,
            "detected_at_index": index,
            "confirmed_at_index": available,
            "decision_available_at_index": available,
            "role": "SETUP_ORIGIN_BOS",
            "causal_valid": available <= self.as_of_index,
        }

    def _importance(self, point: Dict[str, Any]) -> float:
        score = float(point.get("decision_weight", 0) or 0)
        if point.get("is_tradeable_structure"):
            score = max(score, 3.0)
        if point.get("is_major"):
            score += 2.0
        if point.get("is_protected"):
            score += 2.0
        return score

    def _available(self, item: Dict[str, Any]) -> bool:
        index = item.get("index")
        if index is None or int(index) > self.as_of_index:
            return False
        return self._availability(item) <= self.as_of_index

    @staticmethod
    def _availability(item: Dict[str, Any]) -> int:
        index = int(item.get("index", 0))
        values = [
            item.get("confirmed_at_index"),
            item.get("tradeable_at_index"),
            item.get("decision_available_at_index"),
        ]
        present = [
            int(value)
            for value in values
            if value is not None
        ]
        return max([index, *present])
