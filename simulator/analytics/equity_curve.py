from __future__ import annotations

from typing import Any


def compact_equity_curve(history: list[dict[str, Any]], maximum_points: int = 2000) -> list[dict[str, Any]]:
    if len(history) <= maximum_points:
        return list(history)
    stride = max(1, len(history) // maximum_points)
    rows = history[::stride]
    if rows[-1] != history[-1]:
        rows.append(history[-1])
    return rows
