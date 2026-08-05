from __future__ import annotations

from typing import Any, Dict, Iterable, Optional


COMPLETE_REVIEW_STATUS = "COMPLETE"
REVIEW_STATUSES = {
    "UNREVIEWED",
    "IN_PROGRESS",
    "COMPLETE",
    "NEEDS_CANDLE_MAPPING",
}
HUMAN_DECISIONS = {"BUY", "SELL", "NO_TRADE", "UNCERTAIN"}


FIELD_COMPARISONS = (
    ("direction", "direction", "DIRECTION"),
    ("origin_bos_index", "origin_bos_index", "ORIGIN_BOS"),
    (
        "initial_pullback_start_index",
        "first_candidate_index",
        "PULLBACK_ORIGIN",
    ),
    (
        "failure_trigger_index",
        "active_failure_trigger_index",
        "FAILURE_TRIGGER",
    ),
    (
        "decision_protection_index",
        "decision_protection_index",
        "DECISION_PROTECTION",
    ),
    ("entry_index", "entry_index", "ENTRY_TIMING"),
)


def validate_manual_label(label: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a human label without interpreting missing fields as rejects."""

    errors: list[str] = []
    status = str(label.get("review_status", "UNREVIEWED")).upper()
    decision = str(label.get("human_decision", "UNCERTAIN")).upper()

    if status not in REVIEW_STATUSES:
        errors.append(f"Unknown review_status: {status}")
    if decision not in HUMAN_DECISIONS:
        errors.append(f"Unknown human_decision: {decision}")

    if status == COMPLETE_REVIEW_STATUS:
        if decision == "UNCERTAIN":
            errors.append(
                "A COMPLETE review must resolve BUY/SELL/NO_TRADE"
            )
        if not str(label.get("manual_reason", "")).strip():
            errors.append("A COMPLETE review requires manual_reason")
        if decision in {"BUY", "SELL"}:
            for field in (
                "direction",
                "origin_bos_index",
                "initial_pullback_start_index",
                "failure_trigger_index",
                "entry_index",
            ):
                if label.get(field) in {None, ""}:
                    errors.append(
                        f"A traded COMPLETE example requires {field}"
                    )

    return {
        "valid": not errors,
        "review_status": status,
        "scorable": status == COMPLETE_REVIEW_STATUS and not errors,
        "errors": errors,
    }


def _normalise(value: Any) -> Any:
    if value in {None, ""}:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lstrip("-").isdigit():
            return int(stripped)
        return stripped.upper()
    return value


def _bot_decision(bot: Dict[str, Any]) -> str:
    entry_ready = bool(bot.get("entry_ready"))
    direction = str(bot.get("direction", "")).upper()
    if not entry_ready:
        return "NO_TRADE"
    if direction == "BULLISH":
        return "BUY"
    if direction == "BEARISH":
        return "SELL"
    return "UNCERTAIN"


def compare_manual_to_bot(
    *,
    manual: Dict[str, Any],
    bot: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compare one completed human decision with one causal bot snapshot.

    This module reports disagreements only.  It never changes a threshold,
    activates a policy, or converts an incomplete review into a negative label.
    """

    validation = validate_manual_label(manual)
    if not validation["scorable"]:
        return {
            "example_id": manual.get("example_id"),
            "scorable": False,
            "agreement": None,
            "disagreements": [],
            "validation": validation,
            "thresholds_changed": False,
        }

    disagreements: list[Dict[str, Any]] = []
    human_decision = str(manual["human_decision"]).upper()
    bot_decision = _bot_decision(bot)
    if human_decision != bot_decision:
        disagreements.append(
            {
                "category": "ENTRY_DECISION",
                "human": human_decision,
                "bot": bot_decision,
            }
        )

    for human_field, bot_field, category in FIELD_COMPARISONS:
        human_value = _normalise(manual.get(human_field))
        if human_value is None:
            continue
        bot_value = _normalise(bot.get(bot_field))
        if human_value != bot_value:
            disagreements.append(
                {
                    "category": category,
                    "human": human_value,
                    "bot": bot_value,
                    "human_field": human_field,
                    "bot_field": bot_field,
                }
            )

    return {
        "example_id": manual.get("example_id"),
        "scorable": True,
        "agreement": not disagreements,
        "human_decision": human_decision,
        "bot_decision": bot_decision,
        "disagreements": disagreements,
        "validation": validation,
        "thresholds_changed": False,
    }


def summarise_comparisons(
    comparisons: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    rows = list(comparisons)
    scored = [row for row in rows if row.get("scorable")]
    agreement = [row for row in scored if row.get("agreement")]
    categories: Dict[str, int] = {}
    for row in scored:
        for disagreement in row.get("disagreements", []):
            category = str(disagreement.get("category"))
            categories[category] = categories.get(category, 0) + 1
    return {
        "total_examples": len(rows),
        "scored_examples": len(scored),
        "unscored_examples": len(rows) - len(scored),
        "exact_agreements": len(agreement),
        "exact_agreement_rate": (
            len(agreement) / len(scored) if scored else None
        ),
        "disagreement_categories": dict(
            sorted(categories.items(), key=lambda item: (-item[1], item[0]))
        ),
        "thresholds_changed": False,
        "demo_readiness_can_be_inferred": bool(len(scored) >= 30),
    }
