from __future__ import annotations

from collections import defaultdict
from typing import Any


def aggregate_costs(events: list[dict[str, Any]]) -> dict[str, Any]:
    totals = defaultdict(float)
    by_symbol: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for event in events:
        for name, amount in (event.get("costs") or {}).items():
            totals[name] += float(amount or 0.0)
            by_symbol[str(event.get("symbol"))][name] += float(amount or 0.0)
    totals["total"] = sum(value for key, value in totals.items() if key != "total")
    return {"totals": dict(totals), "by_symbol": {key: dict(value) for key, value in by_symbol.items()}}
