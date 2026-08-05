from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


def canonical_management_chart_contract(
    snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Return only canonical Director-owned structures for chart/audit exporters.

    This deliberately rejects descriptive nested market guesses. Export tools
    must annotate the four independent contracts and the causal manager record.
    """
    entry = deepcopy(snapshot.get("entry") or {})
    dominant = deepcopy(snapshot.get("protection") or {})
    invalidation = deepcopy(snapshot.get("setup_invalidation") or {})
    trailing = deepcopy(snapshot.get("trailing_protection") or {})
    emergency = deepcopy(
        entry.get("emergency_broker_stop_contract")
        or (
            (trailing.get("latest_attempt") or {})
            .get("emergency_broker_stop_contract")
        )
        or {}
    )
    decision_index = entry.get("index")
    if entry.get("ready") and decision_index is None:
        raise ValueError("Ready entry has no canonical decision index")
    director_index = (
        (snapshot.get("meta") or {}).get("as_of_index")
    )
    if (
        entry.get("ready")
        and director_index is not None
        and int(decision_index) != int(director_index)
    ):
        raise ValueError("Chart contract rejected stale entry trigger")
    if entry.get("ready"):
        if invalidation.get("available_at_index") is None:
            raise ValueError(
                "Canonical setup invalidation has no availability index"
            )
        if (
            int(invalidation["available_at_index"])
            > int(decision_index)
        ):
            raise ValueError(
                "Chart contract rejected future setup invalidation"
            )
    return {
        "entry": entry,
        "dominant_decision_protection": dominant,
        "setup_logical_invalidation": invalidation,
        "emergency_broker_stop": emergency,
        "trailing_protection": trailing,
        "decision_index": decision_index,
        "canonical_roots_only": True,
        "future_initial_stop_data_used": False,
        "order_api_called": False,
    }
