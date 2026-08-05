from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from simulator.execution.spread_engine import market_session


def by_session(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"sample_size": 0, "net_zar": 0.0})
    for row in attempts:
        opened = float((row.get("position") or {}).get("opened_at", 0.0))
        session = market_session(opened)
        grouped[session]["sample_size"] += 1
        grouped[session]["net_zar"] += float(row.get("net_pl_zar", 0.0))
    return [{"session": key, **value} for key, value in grouped.items()]
