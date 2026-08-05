from __future__ import annotations

from typing import Any


def drawdown_series(equity_history: list[dict[str, Any]]) -> list[dict[str, float]]:
    peak = 0.0
    result: list[dict[str, float]] = []
    for row in equity_history:
        equity = float(row.get("equity", 0.0))
        peak = max(peak, equity)
        money = max(0.0, peak - equity)
        result.append({"timestamp": float(row.get("timestamp", 0.0)), "drawdown_money": money, "drawdown_percent": money / peak * 100.0 if peak > 0 else 0.0})
    return result
