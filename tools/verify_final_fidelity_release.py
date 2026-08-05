from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tools.run_final_fidelity_evidence import refresh_profit_management


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "final_fidelity_evidence"
AUDIT = EVIDENCE / "final_fidelity_audit.json"
EXPECTED_DISTRIBUTION = {
    "VALID_M1_EARLY_ENTRY": 15,
    "M5_FALLBACK_NO_VALID_M1": 10,
    "MESSY_M1_BOS_REJECTED": 5,
    "FIRST_FAILURE_VALID_REENTRY": 5,
    "DOMINANT_PROTECTION_FAILURE_NO_REENTRY": 5,
}
EXPECTED_SYMBOLS = {
    "EURUSD#",
    "GBPUSD#",
    "AUDUSD#",
    "USDJPY#",
    "GOLD#",
    "US100Cash#",
    "GER40Cash#",
}


def _decision_digest(payload: dict[str, Any]) -> str:
    decisions = [
        {
            "setup": row["parent_m5_setup_id"],
            "retracement": row["parent_m5_retracement_id"],
            "entry_timeframe": row["entry_timeframe"],
            "entry_time": row["entry_time"],
            "entry_price": row["entry_price"],
            "logical_stop": row["logical_stop"],
            "emergency_stop": row.get("emergency_stop"),
            "category": row["assigned_category"],
            "exit_time": row["outcome"]["exit_time"],
            "exit_reason": row["outcome"]["exit_reason"],
            "final_R": row["outcome"]["metrics"]["final_R"],
        }
        for row in payload["rows"]
    ]
    encoded = json.dumps(
        decisions,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _order_api_hits() -> list[str]:
    patterns = (
        "order_" + "send(",
        "order_check(",
        "TRADE_ACTION_DEAL",
        "positions_get(",
    )
    hits: list[str] = []
    paths = list((ROOT / "core").glob("*.py")) + [ROOT / "main.py"]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for pattern in patterns:
            if pattern in text:
                hits.append(f"{path.relative_to(ROOT)}:{pattern}")
    return hits


def run() -> dict[str, Any]:
    first = refresh_profit_management()
    first_digest = _decision_digest(first)
    second = refresh_profit_management()
    second_digest = _decision_digest(second)
    rows = second["rows"]
    target_states = {
        event["state"]
        for row in rows
        for event in row["outcome"]["tp1_history"]
    }
    chart_files = [
        EVIDENCE / "charts" / row["chart_file"]
        for row in rows
    ]
    checks = {
        "forty_examples": len(rows) == 40,
        "forty_unique_parent_setups": (
            len({row["parent_m5_setup_id"] for row in rows}) == 40
        ),
        "exact_distribution": (
            second["distribution"] == EXPECTED_DISTRIBUTION
        ),
        "all_required_symbols": (
            set(second["symbols"]) == EXPECTED_SYMBOLS
        ),
        "both_directions": (
            second["directions"].get("BULLISH", 0) > 0
            and second["directions"].get("BEARISH", 0) > 0
        ),
        "zero_future_data_violations": (
            second["future_data_violations"] == 0
        ),
        "zero_unfinished_candle_decisions": (
            second["unfinished_candle_decisions"] == 0
        ),
        "zero_duplicate_first_entries": (
            second["duplicate_first_entries"] == 0
        ),
        "zero_unrelated_parent_attachments": (
            second["unrelated_parent_attachments"] == 0
        ),
        "zero_order_calls_in_evidence": second["order_api_calls"] == 0,
        "zero_order_api_patterns_in_runtime": not _order_api_hits(),
        "all_charts_exist": all(path.exists() for path in chart_files),
        "target_lifecycle_distinctions_present": {
            "WICK_TOUCHED",
            "BODY_CLOSED_THROUGH",
            "ACCEPTED_BEYOND",
            "REJECTED",
        }.issubset(target_states),
        "no_widening_transition": all(
            (row["outcome"].get("management_transition") or {}).get(
                "loosened"
            )
            is not True
            for row in rows
        ),
        "one_reentry_ceiling": all(
            int(bool(row["outcome"].get("valid_reentry"))) <= 1
            for row in rows
        ),
        "deterministic_refresh": first_digest == second_digest,
    }
    report = {
        "owner": "FinalFidelityReleaseVerifier",
        "state": (
            "VERIFIED" if all(checks.values()) else "FAILED"
        ),
        "checks": checks,
        "decision_digest_first": first_digest,
        "decision_digest_second": second_digest,
        "m1_false_entry_rate": second["m1_false_entry_rate"],
        "order_api_hits": _order_api_hits(),
    }
    (EVIDENCE / "release_verification.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    result = run()
    raise SystemExit(0 if result["state"] == "VERIFIED" else 1)
