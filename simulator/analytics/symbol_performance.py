from __future__ import annotations

from collections import defaultdict
from typing import Any


def by_symbol(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"sample_size": 0, "net_zar": 0.0, "wins": 0})
    for row in attempts:
        symbol = str((row.get("position") or {}).get("symbol") or "UNKNOWN")
        net = float(row.get("net_pl_zar", 0.0))
        grouped[symbol]["sample_size"] += 1
        grouped[symbol]["net_zar"] += net
        grouped[symbol]["wins"] += int(net > 0)
    return [{"symbol": key, **value, "win_rate": value["wins"] / value["sample_size"] * 100.0 if value["sample_size"] else 0.0} for key, value in grouped.items()]
