from __future__ import annotations

from collections import Counter
from typing import Any, Dict

import pandas as pd


REQUIRED_REVIEW_COLUMNS = (
    "setup_id",
    "symbol",
    "timeframe",
    "direction",
    "first_candidate_index",
    "first_qualification_index",
    "active_failure_trigger_index",
    "entry_index",
    "steve_verdict",
    "manual_origin_bos",
    "manual_protected_swing",
    "manual_retracement_start",
    "manual_qualification",
    "manual_trigger",
    "manual_reason",
)
ALLOWED_VERDICTS = {"", "ACCEPT", "REJECT", "UNCERTAIN"}


def validate_review_frame(frame: pd.DataFrame) -> None:
    missing = [
        column
        for column in REQUIRED_REVIEW_COLUMNS
        if column not in frame.columns
    ]
    if missing:
        raise ValueError(
            "Review CSV is missing required columns: "
            + ", ".join(missing)
        )
    verdicts = {
        str(value).strip().upper()
        for value in frame["steve_verdict"].fillna("")
    }
    invalid = sorted(verdicts.difference(ALLOWED_VERDICTS))
    if invalid:
        raise ValueError(
            "Invalid Steve verdict(s): " + ", ".join(invalid)
        )
    duplicate = frame.duplicated(
        subset=["setup_id", "entry_index"],
        keep=False,
    )
    if duplicate.any():
        raise ValueError(
            "Review CSV contains duplicate setup_id/entry_index rows"
        )


def analyze_reviews(frame: pd.DataFrame) -> Dict[str, Any]:
    validate_review_frame(frame)
    working = frame.copy()
    working["steve_verdict"] = (
        working["steve_verdict"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )
    reviewed = working[
        working["steve_verdict"] != ""
    ]
    accepted = reviewed[
        reviewed["steve_verdict"] == "ACCEPT"
    ]
    rejected = reviewed[
        reviewed["steve_verdict"] == "REJECT"
    ]
    uncertain = reviewed[
        reviewed["steve_verdict"] == "UNCERTAIN"
    ]
    categories: Counter[str] = Counter()
    for _, row in rejected.iterrows():
        row_categories: list[str] = []
        for manual, automatic, label in (
            (
                "manual_retracement_start",
                "first_candidate_index",
                "RETRACEMENT_START",
            ),
            (
                "manual_qualification",
                "first_qualification_index",
                "QUALIFICATION",
            ),
            (
                "manual_trigger",
                "active_failure_trigger_index",
                "FAILURE_TRIGGER",
            ),
        ):
            manual_value = _optional_int(row.get(manual))
            automatic_value = _optional_int(row.get(automatic))
            if (
                manual_value is not None
                and automatic_value is not None
                and manual_value != automatic_value
            ):
                categories[label] += 1
                row_categories.append(label)
        if not row_categories:
            categories["UNCLASSIFIED_REJECTION"] += 1

    reasons = [
        str(value).strip()
        for value in rejected["manual_reason"].fillna("")
        if str(value).strip()
    ]
    missed = [
        str(value).strip()
        for value in working["manual_reason"].fillna("")
        if "missed" in str(value).lower()
    ]
    definition_fixes = [
        f"Review {category.lower().replace('_', ' ')} definition"
        for category in sorted(categories)
        if category != "UNCLASSIFIED_REJECTION"
    ]
    threshold_proposals = [
        {
            "status": "REVIEW_ONLY_NOT_APPLIED",
            "source_reason": reason,
        }
        for reason in reasons
        if any(
            token in reason.lower()
            for token in (
                "weak",
                "noise",
                "score",
                "threshold",
                "late",
            )
        )
    ]
    return {
        "total_rows": len(working),
        "reviewed_rows": len(reviewed),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "uncertain": len(uncertain),
        "agreement_rate": (
            round(len(accepted) / len(reviewed), 6)
            if len(reviewed)
            else None
        ),
        "disagreement_categories": dict(categories),
        "false_positive_categories": dict(categories),
        "missed_entry_comments": missed,
        "proposed_definition_fixes": definition_fixes,
        "proposed_threshold_changes": threshold_proposals,
        "threshold_changes_auto_applied": False,
    }


def _optional_int(value: Any) -> int | None:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
