from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from simulator.models.financial import ContractSpecification, ExecutionConfig


SESSION_MULTIPLIER = {
    "ASIA": 1.25,
    "LONDON": 1.0,
    "OVERLAP": 0.85,
    "NEW_YORK": 1.0,
    "ROLLOVER": 3.0,
    "OFF_SESSION": 1.75,
}

COST_MULTIPLIER = {
    "IDEALIZED_CONTROL": 0.5,
    "NORMAL_ESTIMATED": 1.0,
    "STRESSED_COSTS": 2.0,
}


def market_session(timestamp: float) -> str:
    dt = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
    if dt.weekday() >= 5:
        return "OFF_SESSION"
    hour = dt.hour + dt.minute / 60.0
    if 21 <= hour < 22:
        return "ROLLOVER"
    if 0 <= hour < 7:
        return "ASIA"
    if 7 <= hour < 12:
        return "LONDON"
    if 12 <= hour < 16:
        return "OVERLAP"
    if 16 <= hour < 21:
        return "NEW_YORK"
    return "OFF_SESSION"


class SpreadEngine:
    def calculate(
        self,
        *,
        spec: ContractSpecification,
        config: ExecutionConfig,
        timestamp: float,
        candle: dict[str, Any],
        volatility_ratio: float = 1.0,
    ) -> dict[str, Any]:
        native = candle.get("spread")
        if config.spread_model == "FIXED_USER_SPREAD" and config.fixed_spread_points is not None:
            points = float(config.fixed_spread_points)
            source = "FIXED_USER_SPREAD"
            estimated = True
        elif native is not None and float(native) > 0 and config.spread_model != "FIXED_USER_SPREAD":
            points = float(native)
            source = "NATIVE_HISTORICAL_SPREAD"
            estimated = False
        else:
            session = market_session(timestamp)
            session_factor = SESSION_MULTIPLIER[session]
            cost_factor = COST_MULTIPLIER[config.cost_profile]
            volatility_factor = 1.0
            if config.spread_model == "VOLATILITY_ADJUSTED_RESEARCH_SPREAD":
                volatility_factor = max(0.75, min(2.5, float(volatility_ratio)))
            points = spec.base_spread_points * session_factor * cost_factor * volatility_factor
            source = "SYMBOL_SESSION_ESTIMATED"
            estimated = True
        session = market_session(timestamp)
        if session == "ROLLOVER":
            state = "ROLLOVER_EXTREME"
        elif points >= spec.base_spread_points * 2:
            state = "HIGH"
        elif points >= spec.base_spread_points * 1.25:
            state = "ELEVATED"
        else:
            state = "DATA_ESTIMATED" if estimated else "NORMAL"
        return {
            "spread_points": round(max(0.0, points), 6),
            "spread_price": round(max(0.0, points) * spec.point_size, 10),
            "spread_state": state,
            "spread_source": source,
            "session": session,
            "estimated": estimated,
        }
