from __future__ import annotations

from typing import Any, Dict


EVIDENCE_FIELDS = (
    "first_candidate_index",
    "first_qualification_index",
    "qualification_available_at_index",
    "initial_failure_trigger_index",
    "active_failure_trigger_index",
    "active_failure_trigger_level",
    "trigger_updated_at_index",
    "trigger_update_count",
    "entry_index",
)


def canonical_entry_evidence(
    snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """Return the one decision-time evidence vocabulary used everywhere."""
    retracement = snapshot.get("retracement", {}) or {}
    entry = snapshot.get("entry", {}) or {}
    meta = snapshot.get("meta", {}) or {}
    significance = retracement.get("significance", {}) or {}

    evidence = {
        "setup_id": (
            entry.get("setup_id")
            or (snapshot.get("setup", {}) or {}).get("setup_id")
        ),
        "symbol": meta.get("symbol"),
        "timeframe": meta.get("timeframe"),
        "direction": (
            entry.get("direction")
            or retracement.get("trend")
        ),
        "first_candidate_index": retracement.get(
            "first_candidate_index"
        ),
        "first_qualification_index": retracement.get(
            "first_qualification_index"
        ),
        "qualification_available_at_index": retracement.get(
            "qualification_available_at_index"
        ),
        "initial_failure_trigger_index": retracement.get(
            "initial_failure_trigger_index"
        ),
        "active_failure_trigger_index": retracement.get(
            "active_failure_trigger_index"
        ),
        "active_failure_trigger_level": retracement.get(
            "active_failure_trigger_level"
        ),
        "trigger_updated_at_index": retracement.get(
            "trigger_updated_at_index"
        ),
        "trigger_update_count": int(
            retracement.get("trigger_update_count", 0) or 0
        ),
        "entry_index": entry.get("index"),
        "entry_price": entry.get("price"),
        "entry_ready": bool(entry.get("ready", False)),
        "significance_score": significance.get(
            "significance_score"
        ),
        "raw_significance_score": significance.get(
            "raw_significance_score"
        ),
        "score_contract": significance.get("score_contract"),
        "as_of_index": meta.get("as_of_index"),
    }
    _validate_evidence(evidence, retracement, entry)
    return evidence


def _validate_evidence(
    evidence: Dict[str, Any],
    retracement: Dict[str, Any],
    entry: Dict[str, Any],
) -> None:
    if (
        retracement.get("qualification_index")
        != evidence["first_qualification_index"]
    ):
        raise ValueError(
            "qualification_index must alias first_qualification_index"
        )
    active = retracement.get("active_failure_trigger") or {}
    legacy = retracement.get("failure_trigger") or {}
    if active != legacy:
        raise ValueError(
            "failure_trigger must alias active_failure_trigger"
        )
    if active and (
        active.get("index")
        != evidence["active_failure_trigger_index"]
        or active.get("level")
        != evidence["active_failure_trigger_level"]
    ):
        raise ValueError(
            "Active trigger scalar fields disagree with trigger contract"
        )
    if entry.get("ready"):
        entry_index = evidence["entry_index"]
        as_of_index = evidence["as_of_index"]
        if entry_index != as_of_index:
            raise ValueError(
                "Canonical entry must belong to the current decision candle"
            )
        ordered = [
            evidence["first_candidate_index"],
            evidence["first_qualification_index"],
            evidence["active_failure_trigger_index"],
            entry_index,
        ]
        if any(value is None for value in ordered):
            raise ValueError(
                "Ready entry is missing canonical retracement evidence"
            )
        if ordered != sorted(ordered):
            raise ValueError(
                "Canonical entry evidence chronology is incoherent"
            )
        if not active.get(
            "belongs_to_same_qualified_retracement",
            False,
        ):
            raise ValueError(
                "Active trigger does not belong to the current setup"
            )

