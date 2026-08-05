from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd


FRESHNESS_POLICIES = {
    "STRUCTURE_ONLY",
    "STRUCTURE_PLUS_ATR_DISTANCE",
    "STRUCTURE_PLUS_TIME_AND_DISTANCE",
    "TRIGGER_REFRESH",
}


@dataclass(frozen=True)
class EntryFreshnessPolicy:
    atr_distance_limit: float = 3.0
    mature_atr_distance: float = 1.5
    mature_candle_limits: tuple[tuple[str, int], ...] = (
        ("M1", 30),
        ("M5", 18),
        ("M15", 12),
        ("M30", 8),
        ("H1", 6),
    )

    def candle_limit(self, timeframe: str) -> int:
        limits = dict(self.mature_candle_limits)
        return int(limits.get(str(timeframe).upper(), 18))


class EntryFreshnessEngine:
    """Describe entry age without changing the canonical strategy outcome."""

    def __init__(
        self,
        data: pd.DataFrame,
        *,
        timeframe: str,
        policy: Optional[EntryFreshnessPolicy] = None,
    ) -> None:
        self.data = data.reset_index(drop=True)
        self.timeframe = str(timeframe).upper()
        self.policy = policy or EntryFreshnessPolicy()

    def assess(
        self,
        *,
        retracement: Dict[str, Any],
        entry_index: Optional[int],
    ) -> Dict[str, Any]:
        qualification = retracement.get("first_qualification_index")
        trigger = (
            retracement.get("active_failure_trigger") or {}
        )
        trigger_index = retracement.get(
            "active_failure_trigger_index",
            trigger.get("index"),
        )
        trigger_fractal_confirmed_at = trigger.get(
            "fractal_confirmed_at_index"
        )
        trigger_structurally_confirmed_at = trigger.get(
            "structural_confirmed_at_index",
            trigger.get("confirmed_at_index"),
        )
        trigger_tradeable_at = trigger.get("tradeable_at_index")
        trigger_updates = int(
            retracement.get("trigger_update_count", 0) or 0
        )
        same_retracement = bool(
            trigger
            and trigger.get(
                "belongs_to_same_qualified_retracement",
                False,
            )
        )
        counter_active = bool(
            retracement.get("qualified", False)
            and retracement.get("protected_swing_intact", False)
            and retracement.get("state")
            not in {
                "CONSUMED",
                "INVALIDATED_BY_PROTECTED_SWING",
                "EXPIRED",
            }
        )
        current = (
            int(entry_index)
            if entry_index is not None
            else int(retracement.get("as_of_index", len(self.data) - 1))
        )
        reasons: list[str] = []

        if qualification is None or trigger_index is None or entry_index is None:
            classification = "AMBIGUOUS"
            reasons.append(
                "Qualification, active trigger and canonical entry are "
                "all required for a complete freshness assessment"
            )
            candles_q = None
            candles_trigger = None
            candles_after_fractal_confirmation = None
            trigger_confirmation_delay = None
            atr_distance = 0.0
        else:
            qualification = int(qualification)
            trigger_index = int(trigger_index)
            candles_q = current - qualification
            candles_trigger = current - trigger_index
            candles_after_fractal_confirmation = (
                current - int(trigger_fractal_confirmed_at)
                if trigger_fractal_confirmed_at is not None
                else None
            )
            trigger_confirmation_delay = (
                int(trigger_structurally_confirmed_at)
                - int(trigger_fractal_confirmed_at)
                if trigger_fractal_confirmed_at is not None
                and trigger_structurally_confirmed_at is not None
                else None
            )
            atr = self._atr_at(qualification)
            qualification_close = float(
                self.data.at[qualification, "close"]
            )
            entry_close = float(self.data.at[current, "close"])
            atr_distance = (
                abs(entry_close - qualification_close) / atr
                if atr > 0
                else 0.0
            )
            limit = self.policy.candle_limit(self.timeframe)

            if not same_retracement or not counter_active:
                classification = "STALE_RETRACEMENT_ENTRY"
                reasons.append(
                    "The trigger or counter structure no longer belongs "
                    "to an active qualified retracement"
                )
            elif (
                candles_q <= max(3, limit // 3)
                and atr_distance <= self.policy.mature_atr_distance
            ):
                classification = "FRESH_ENTRY"
                reasons.append(
                    "Entry is close to first qualification in time and ATR"
                )
            elif (
                candles_q <= limit
                and atr_distance <= self.policy.atr_distance_limit
            ):
                classification = "MATURE_ENTRY"
                reasons.append(
                    "Entry remains inside the timeframe-scaled maturity window"
                )
            elif trigger_updates > 0 and same_retracement:
                classification = "DELAYED_SAME_RETRACEMENT"
                reasons.append(
                    "A newer causal trigger refreshed the same retracement"
                )
            else:
                classification = "STALE_RETRACEMENT_ENTRY"
                reasons.append(
                    "Entry exceeds the advisory time/distance envelope"
                )

        assessment = {
            "availability": (
                "AVAILABLE"
                if classification != "AMBIGUOUS"
                else "UNAVAILABLE"
            ),
            "available": classification != "AMBIGUOUS",
            "owner": "EntryFreshnessEngine",
            "state": classification,
            "first_qualification_index": qualification,
            "active_trigger_index": trigger_index,
            "trigger_fractal_confirmed_at_index": (
                trigger_fractal_confirmed_at
            ),
            "trigger_structurally_confirmed_at_index": (
                trigger_structurally_confirmed_at
            ),
            "trigger_tradeable_at_index": trigger_tradeable_at,
            "entry_index": entry_index,
            "candles_since_qualification": candles_q,
            "candles_since_trigger": candles_trigger,
            "candles_after_fractal_confirmation": (
                candles_after_fractal_confirmation
            ),
            "trigger_confirmation_delay_candles": (
                trigger_confirmation_delay
            ),
            "trigger_confirmation_coincident_with_entry": bool(
                entry_index is not None
                and trigger_structurally_confirmed_at is not None
                and int(entry_index)
                == int(trigger_structurally_confirmed_at)
            ),
            "atr_distance_since_qualification": round(
                float(atr_distance), 6
            ),
            "trigger_update_count": trigger_updates,
            "same_retracement": same_retracement,
            "counter_structure_still_active": counter_active,
            "classification": classification,
            "reason": reasons,
            "causal_valid": bool(
                entry_index is None
                or (
                    int(entry_index) <= len(self.data) - 1
                    and (
                        qualification is None
                        or int(qualification) <= int(entry_index)
                    )
                    and (
                        trigger_index is None
                        or int(trigger_index) <= int(entry_index)
                    )
                )
            ),
            "advisory_only": True,
            "strategy_outcome_changed": False,
        }
        assessment["policy_comparison"] = self.compare_policies(
            assessment
        )
        return assessment

    def compare_policies(
        self,
        assessment: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        complete = bool(assessment.get("available"))
        structure_valid = bool(
            assessment.get("same_retracement")
            and assessment.get("counter_structure_still_active")
        )
        distance = float(
            assessment.get("atr_distance_since_qualification", 0.0)
        )
        candles = assessment.get("candles_since_qualification")
        time_valid = bool(
            candles is not None
            and int(candles)
            <= self.policy.candle_limit(self.timeframe)
        )
        refreshed = int(
            assessment.get("trigger_update_count", 0) or 0
        ) > 0
        delayed = bool(
            candles is not None
            and int(candles)
            > max(3, self.policy.candle_limit(self.timeframe) // 3)
        )
        outcomes = {
            "STRUCTURE_ONLY": (
                complete and structure_valid,
                "Same retracement and counter structure remain active",
            ),
            "STRUCTURE_PLUS_ATR_DISTANCE": (
                complete
                and structure_valid
                and distance <= self.policy.atr_distance_limit,
                f"ATR distance <= {self.policy.atr_distance_limit}",
            ),
            "STRUCTURE_PLUS_TIME_AND_DISTANCE": (
                complete
                and structure_valid
                and time_valid
                and distance <= self.policy.atr_distance_limit,
                "Timeframe candle limit and ATR limit both satisfied",
            ),
            "TRIGGER_REFRESH": (
                complete
                and structure_valid
                and (not delayed or refreshed),
                "Delayed entries require a newer same-setup trigger",
            ),
        }
        return {
            name: {
                "policy": name,
                "classification": "ADVISORY_ALLOW" if allowed else "ADVISORY_BLOCK",
                "allowed": bool(allowed),
                "reason": [reason],
                "advisory_only": True,
                "strategy_outcome_changed": False,
            }
            for name, (allowed, reason) in outcomes.items()
        }

    def _atr_at(self, index: int, period: int = 14) -> float:
        start = max(0, int(index) - period + 1)
        frame = self.data.iloc[start : int(index) + 1]
        if frame.empty:
            return 0.0
        return float((frame["high"] - frame["low"]).median())
