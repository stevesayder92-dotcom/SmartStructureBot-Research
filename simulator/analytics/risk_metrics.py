from __future__ import annotations

from typing import Any


def risk_summary(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    logical = [float(row.get("position", {}).get("actual_logical_risk_zar", 0.0)) for row in attempts]
    emergency = [float(row.get("position", {}).get("actual_emergency_risk_zar", 0.0)) for row in attempts]
    return {
        "attempts": len(attempts),
        "average_logical_risk_zar": sum(logical) / len(logical) if logical else 0.0,
        "maximum_logical_risk_zar": max(logical, default=0.0),
        "maximum_emergency_risk_zar": max(emergency, default=0.0),
    }
