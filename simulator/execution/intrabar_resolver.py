from __future__ import annotations

from typing import Any


class IntrabarResolver:
    """Resolve same-candle target/stop ambiguity without inventing tick order."""

    @staticmethod
    def _touches(direction: str, candle: dict[str, Any], stop: float, target: float) -> tuple[bool, bool]:
        low = float(candle["low"])
        high = float(candle["high"])
        if direction == "BULLISH":
            return low <= stop, high >= target
        return high >= stop, low <= target

    def resolve(
        self,
        *,
        direction: str,
        parent_candle: dict[str, Any],
        stop: float,
        target: float,
        policy: str,
        closed_child_candles: list[dict[str, Any]] | None = None,
        parent_close_time: float | None = None,
    ) -> dict[str, Any]:
        stop_hit, target_hit = self._touches(direction, parent_candle, stop, target)
        if not (stop_hit and target_hit):
            outcome = "STOP_FIRST" if stop_hit else "TARGET_FIRST" if target_hit else "NEITHER"
            return {"ambiguous": False, "resolution": outcome, "resolution_source": "PARENT_CANDLE_SINGLE_TOUCH", "causal_valid": True}

        children = sorted(closed_child_candles or [], key=lambda row: float(row["time"]))
        if policy == "LOWER_TIMEFRAME_THEN_CONSERVATIVE_STOP_FIRST" and children:
            for child in children:
                if parent_close_time is not None and float(child["time"]) > float(parent_close_time):
                    continue
                child_stop, child_target = self._touches(direction, child, stop, target)
                if child_stop and child_target:
                    break
                if child_stop or child_target:
                    return {
                        "ambiguous": True,
                        "resolution": "STOP_FIRST" if child_stop else "TARGET_FIRST",
                        "resolution_source": "CLOSED_LOWER_TIMEFRAME",
                        "causal_valid": True,
                    }

        if policy == "FLAG_AS_AMBIGUOUS":
            return {"ambiguous": True, "resolution": "UNRESOLVED", "resolution_source": "EXPLICIT_AMBIGUITY_FLAG", "causal_valid": True}
        return {"ambiguous": True, "resolution": "STOP_FIRST", "resolution_source": "CONSERVATIVE_STOP_FIRST_FALLBACK", "causal_valid": True}
