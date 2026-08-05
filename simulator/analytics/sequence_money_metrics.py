from __future__ import annotations

from collections import defaultdict
from typing import Any


def sequence_totals(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"attempts": 0, "gross_zar": 0.0, "costs_zar": 0.0, "net_zar": 0.0})
    for row in attempts:
        position = row.get("position") or {}
        key = str(position.get("sequence_id") or position.get("setup_id") or "UNASSIGNED")
        item = grouped[key]
        item["sequence_id"] = key
        item["attempts"] += 1
        item["gross_zar"] += float(row.get("gross_pl_zar", 0.0))
        item["costs_zar"] += sum(float(value or 0.0) for value in (row.get("costs_zar") or {}).values())
        item["net_zar"] += float(row.get("net_pl_zar", 0.0))
    return list(grouped.values())
