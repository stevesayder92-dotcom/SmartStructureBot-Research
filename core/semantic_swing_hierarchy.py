from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

import pandas as pd

from core.steve_trade_management import atr_at


SEMANTIC_ROLES = {
    "MICRO_NOISE",
    "INTERNAL_CONTINUATION_STRUCTURE",
    "COUNTER_TREND_STRUCTURE",
    "SETUP_TRIGGER_STRUCTURE",
    "SETUP_INVALIDATION_STRUCTURE",
    "DOMINANT_PROTECTED_STRUCTURE",
    "TRAILING_STRUCTURE_CANDIDATE",
    "PROVEN_TRAILING_STRUCTURE",
}


def build_semantic_swing_hierarchy(
    *,
    data: pd.DataFrame,
    swings: Iterable[Dict[str, Any]],
    direction: str,
    as_of_index: int,
    model: Optional[Dict[str, Any]] = None,
    protection: Optional[Dict[str, Any]] = None,
    management: Optional[Dict[str, Any]] = None,
    minimum_displacement_atr: float = 0.35,
) -> Dict[str, Any]:
    """
    Assign decision roles to causal raw fractals.

    Roles are contextual and may differ from generic HH/HL/LH/LL labels.
    A candidate is never promoted before its confirmation candle closes.
    """
    current = int(as_of_index)
    direction = str(direction).upper()
    model = dict(model or {})
    points = [
        dict(point)
        for point in swings
        if int(point.get("confirmed_at_index", point.get("index", current + 1)))
        <= current
    ]
    atr_value = atr_at(data, as_of_index=current)
    meaningful_distance = max(atr_value * float(minimum_displacement_atr), 1e-12)
    anchor_index = (model.get("anchor") or {}).get("index")
    counter_index = (model.get("counter") or {}).get("index")
    trigger_index = (model.get("trigger") or {}).get("index")
    dominant_index = (protection or {}).get("index")
    attempts = (management or {}).get("attempts") or []
    trail_candidates = {
        int(item["structure_index"]): str(item.get("state"))
        for attempt in attempts
        for item in attempt.get("trail_candidates", [])
        if item.get("structure_index") is not None
    }

    semantic: list[Dict[str, Any]] = []
    prior_opposite: Optional[Dict[str, Any]] = None
    for point in sorted(points, key=lambda item: int(item["index"])):
        side = str(point.get("side")).upper()
        level = float(point.get("level", point.get("price")))
        displacement = (
            abs(level - float(prior_opposite["level"]))
            if prior_opposite is not None and prior_opposite.get("side") != side
            else 0.0
        )
        displacement_atr = displacement / atr_value if atr_value > 0 else 0.0
        role = (
            "INTERNAL_CONTINUATION_STRUCTURE"
            if (
                direction == "BULLISH" and side == "HIGH"
                or direction == "BEARISH" and side == "LOW"
            )
            else "COUNTER_TREND_STRUCTURE"
        )
        reasons = ["Role assigned relative to the active dominant direction"]
        if displacement < meaningful_distance:
            role = "MICRO_NOISE"
            reasons = [
                "Alternating swing displacement is below the configured causal ATR meaning threshold"
            ]
        index = int(point["index"])
        if index == anchor_index:
            role = "INTERNAL_CONTINUATION_STRUCTURE"
            reasons = ["This swing is the active impulse extreme/pullback origin"]
        if index == counter_index:
            role = "SETUP_INVALIDATION_STRUCTURE"
            reasons = ["This meaningful counter swing owns initial logical invalidation"]
        if index == trigger_index:
            role = "SETUP_TRIGGER_STRUCTURE"
            reasons = ["This swing is the active retracement-failure BOS trigger"]
        if dominant_index is not None and index == int(dominant_index):
            role = "DOMINANT_PROTECTED_STRUCTURE"
            reasons = ["This swing owns dominant-direction decision protection"]
        if index in trail_candidates:
            role = (
                "PROVEN_TRAILING_STRUCTURE"
                if trail_candidates[index] in {"TRAIL_PROVEN", "TRAIL_MOVED", "TRAIL_HELD"}
                else "TRAILING_STRUCTURE_CANDIDATE"
            )
            reasons = [
                "Post-entry structure remains a candidate until a later meaningful continuation BOS proves it"
            ]
        semantic.append(
            {
                **point,
                "semantic_role": role,
                "meaningful": role != "MICRO_NOISE",
                "displacement": displacement,
                "displacement_atr": displacement_atr,
                "role_available_at_index": int(
                    point.get("confirmed_at_index", point["index"])
                ),
                "as_of_index": current,
                "causal_valid": int(
                    point.get("confirmed_at_index", point["index"])
                )
                <= current,
                "role_reasons": reasons,
            }
        )
        if prior_opposite is None or prior_opposite.get("side") != side:
            prior_opposite = point

    counts = {role: 0 for role in sorted(SEMANTIC_ROLES)}
    for point in semantic:
        counts[point["semantic_role"]] += 1
    return {
        "availability": "AVAILABLE" if semantic else "UNAVAILABLE",
        "available": bool(semantic),
        "owner": "SemanticSwingHierarchyEngine",
        "state": "SEMANTIC_ROLES_PUBLISHED" if semantic else "WAITING_FOR_SWINGS",
        "direction": direction,
        "minimum_displacement_atr": float(minimum_displacement_atr),
        "atr_at_decision": atr_value,
        "points": semantic,
        "role_counts": counts,
        "as_of_index": current,
        "causal_valid": all(item["causal_valid"] for item in semantic),
        "reasons": [
            "Raw strict fractals are candidates; semantic role and causal availability determine decision use"
        ],
    }
