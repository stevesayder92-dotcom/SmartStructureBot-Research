from __future__ import annotations

from typing import Any, Dict


class EntryValidator:
    """
    Validate the current-candle entry candidate produced by ContinuationEngine.

    ContinuationEngine owns structural BOS detection.
    EntryValidator owns whether the BOS candle is executable.

    The validator is causal:
    - it reads only the current candle;
    - it never examines future candles;
    - it never changes the BOS trigger itself.
    """

    def __init__(self, data, as_of_index=None):
        self.data = data.copy().reset_index(drop=True)
        self.as_of_index = (
            len(self.data) - 1
            if as_of_index is None
            else int(as_of_index)
        )

        if (
            self.as_of_index < 0
            or self.as_of_index >= len(self.data)
        ):
            raise IndexError(
                f"as_of_index {self.as_of_index} is outside "
                f"0..{len(self.data) - 1}"
            )

    def validate(
        self,
        *,
        trend: str,
        continuation_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        result = {
            "validated": False,
            "allowed": False,
            "state": "NO_ENTRY_CANDIDATE",
            "trend": trend,
            "as_of_index": self.as_of_index,
            "entry_index": None,
            "entry_price": None,
            "directional_body_valid": False,
            "trigger_break_valid": False,
            "current_candle_only": True,
            "causal_valid": True,
            "reason": [],
        }

        if not continuation_state.get("entry_ready", False):
            result["reason"].append(
                "Continuation engine has no current entry candidate"
            )
            return result

        candidate = continuation_state.get("continuation_bos") or {}
        candidate_index = candidate.get("index")

        if candidate_index != self.as_of_index:
            result["state"] = "BLOCKED_STALE_ENTRY"
            result["causal_valid"] = False
            result["reason"].append(
                "Entry candidate does not belong to the current candle"
            )
            return result

        if trend not in {"BULLISH", "BEARISH"}:
            result["state"] = "BLOCKED_UNKNOWN_DIRECTION"
            result["reason"].append(
                "Entry candidate has no valid directional trend"
            )
            return result

        candle_open = float(
            self.data.at[self.as_of_index, "open"]
        )
        candle_close = float(
            self.data.at[self.as_of_index, "close"]
        )

        trigger_level = candidate.get(
            "broken_structure_price"
        )

        if not isinstance(trigger_level, (int, float)):
            result["state"] = "BLOCKED_INVALID_TRIGGER"
            result["reason"].append(
                "Entry candidate has no numeric broken-structure price"
            )
            return result

        directional_body_valid = (
            candle_close > candle_open
            if trend == "BULLISH"
            else candle_close < candle_open
        )

        trigger_break_valid = (
            candle_close > float(trigger_level)
            if trend == "BULLISH"
            else candle_close < float(trigger_level)
        )

        result["entry_index"] = candidate_index
        result["entry_price"] = candle_close
        result["directional_body_valid"] = directional_body_valid
        result["trigger_break_valid"] = trigger_break_valid

        if not trigger_break_valid:
            result["state"] = "BLOCKED_TRIGGER_NOT_BROKEN"
            result["reason"].append(
                "Current candle close did not break the BOS trigger"
            )
            return result

        if not directional_body_valid:
            result["state"] = "BLOCKED_WRONG_CANDLE_DIRECTION"
            result["reason"].append(
                "BOS close crossed the trigger, but the candle body "
                "closed against the intended trade direction"
            )
            return result

        result["validated"] = True
        result["allowed"] = True
        result["state"] = "ENTRY_VALIDATED"
        result["reason"].append(
            "Current candle has a directional body and closes "
            "beyond the failed-pullback trigger"
        )

        return result