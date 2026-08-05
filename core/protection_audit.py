from __future__ import annotations

from typing import Any, Dict


def reproduce_protection_invalidation(
    *,
    snapshot: Dict[str, Any],
    candle: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Reproduce one invalidation from its exact canonical decision snapshot.

    This function deliberately refuses descriptive full-history catalogs.
    """
    meta = snapshot.get("meta") or {}
    retracement = snapshot.get("retracement") or {}
    protection = snapshot.get("protection") or {}
    cycle = snapshot.get("impulse_cycle") or {}
    as_of_index = meta.get("as_of_index")
    invalidation = (
        retracement.get("protected_swing_invalidation") or {}
    )
    reasons: list[str] = []
    canonical_source = bool(
        protection.get("owner")
        in {
            "DecisionProtectionSelector",
            "ProtectedStructureEngine",
        }
        and cycle.get("owner") == "ImpulseCycleEngine"
        and protection.get("cycle_id") == cycle.get("cycle_id")
        and retracement.get("as_of_index") == as_of_index
    )
    if not canonical_source:
        reasons.append(
            "Snapshot does not contain matching canonical cycle/protection"
        )

    direction = (
        cycle.get("direction")
        or retracement.get("trend")
    )
    level = protection.get("level")
    if level is None:
        level = (
            retracement.get("decision_protected_swing") or {}
        ).get("level")
    candle_index = candle.get("source_index", as_of_index)
    if direction == "BULLISH" and level is not None:
        body_close = float(candle["close"]) < float(level)
        wick_crossed = float(candle["low"]) < float(level)
    elif direction == "BEARISH" and level is not None:
        body_close = float(candle["close"]) > float(level)
        wick_crossed = float(candle["high"]) > float(level)
    else:
        body_close = False
        wick_crossed = False
        reasons.append("Direction or protection level is unavailable")

    reported_index = invalidation.get("index")
    reproduced = bool(
        canonical_source
        and reported_index is not None
        and int(reported_index) == int(candle_index)
        and body_close
        and invalidation.get("body_close_crossed") is True
        and invalidation.get("wick_only") is False
    )
    if reproduced:
        reasons.append(
            "Directional close reproduces the canonical invalidation"
        )
    elif canonical_source:
        reasons.append(
            "Canonical snapshot does not reproduce at this candle"
        )

    return {
        "canonical_as_of_index": as_of_index,
        "cycle_id": cycle.get("cycle_id"),
        "origin_bos_index": cycle.get("origin_bos_index"),
        "selected_protection_index": protection.get("index"),
        "selected_protection_level": level,
        "replacement_policy": protection.get("selection_policy"),
        "invalidating_candle_index": candle_index,
        "invalidating_candle_open": float(candle["open"]),
        "invalidating_candle_high": float(candle["high"]),
        "invalidating_candle_low": float(candle["low"]),
        "invalidating_candle_close": float(candle["close"]),
        "body_close_result": body_close,
        "wick_crossed": wick_crossed,
        "wick_only_result": bool(wick_crossed and not body_close),
        "canonical_source": canonical_source,
        "canonical_reproduction_result": reproduced,
        "reason": reasons,
    }
