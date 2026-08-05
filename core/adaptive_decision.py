from __future__ import annotations

from typing import Any, Dict, Iterable


GRADE_RISK = {
    "A_PLUS": 1.00,
    "A": 0.85,
    "B": 0.60,
    "C": 0.30,
    "INVALID": 0.00,
}


def grade_setup(
    *,
    hard_blockers: Iterable[str],
    htf_context: Dict[str, Any],
    fibonacci: Dict[str, Any],
    structure_clear: bool,
    bos_body_atr: float,
    session_quality: str = "UNSCORED",
) -> Dict[str, Any]:
    """
    Separate structural invalidity from quality/risk.

    Soft weakness can reduce grade and risk, but cannot silently become a
    no-trade rule.
    """
    hard = sorted({str(item) for item in hard_blockers if item})
    soft: list[str] = []
    positives: list[str] = []
    if hard:
        grade = "INVALID"
    else:
        score = 0
        context_state = str(htf_context.get("state", ""))
        if context_state.startswith("STRONG_ALIGNED") or "3_OF_3" in context_state:
            score += 3
            positives.append("STRONG_HTF_ALIGNMENT")
        elif htf_context.get("available"):
            score += 2
            positives.append("USABLE_HTF_CONTEXT")
        else:
            soft.append("HTF_CONTEXT_WEAK")

        zone = str(fibonacci.get("zone", "UNAVAILABLE"))
        if zone in {
            "PRIMARY_SWEET_SPOT",
            "STEVE_PRIMARY_DEEP_SWEET_SPOT",
        }:
            score += 3
            positives.append("PRIMARY_FIBONACCI_SWEET_SPOT")
        elif zone in {
            "EARLY_RELEVANT",
            "DEEP_BUT_VALID",
            "38_2_TO_61_8_REMAINING",
            "61_8_TO_78_6_REMAINING",
        }:
            score += 2
            positives.append(zone)
        elif zone in {"SHALLOW", "ABOVE_78_6_REMAINING"}:
            soft.append("SHALLOW_RETRACEMENT")
        elif zone in {"EXTREME", "0_TO_23_6_REMAINING"}:
            soft.append("EXTREME_RETRACEMENT_REQUIRES_PROTECTION")
        elif zone == "BELOW_0":
            soft.append("DOMINANT_IMPULSE_ORIGIN_BREACHED")
        else:
            soft.append("FIBONACCI_LOCATION_UNAVAILABLE")

        if structure_clear:
            score += 2
            positives.append("CLEAR_RETRACEMENT_FAILURE_STRUCTURE")
        else:
            soft.append("STRUCTURE_CLARITY_REDUCED")
        if float(bos_body_atr) >= 0.8:
            score += 2
            positives.append("STRONG_BOS_DISPLACEMENT")
        elif float(bos_body_atr) >= 0.35:
            score += 1
            positives.append("MEANINGFUL_BOS_DISPLACEMENT")
        else:
            soft.append("LOW_BOS_DISPLACEMENT")
        if session_quality not in {"UNSCORED", "LONDON", "NEW_YORK", "OVERLAP"}:
            soft.append("OUTSIDE_PRIMARY_SESSION")

        grade = "A_PLUS" if score >= 9 else "A" if score >= 7 else "B" if score >= 4 else "C"

    context_risk = float(htf_context.get("risk_modifier", 1.0) or 0.0)
    risk = min(GRADE_RISK[grade], context_risk) if grade != "INVALID" else 0.0
    return {
        "availability": "AVAILABLE",
        "available": True,
        "owner": "AdaptiveDecisionEngine",
        "state": "HARD_BLOCKED" if hard else "GRADED_VALID_SETUP",
        "grade": grade,
        "risk_modifier": risk,
        "hard_block": bool(hard),
        "hard_blockers": hard,
        "soft_factors": soft,
        "positive_factors": positives,
        "soft_factors_eliminated_setup": False,
        "allowed": not hard,
        "reasons": (
            [f"Hard invalidity: {item}" for item in hard]
            if hard
            else [
                f"Valid structure graded {grade}; soft weaknesses adjust risk rather than erase the setup"
            ]
        ),
    }
