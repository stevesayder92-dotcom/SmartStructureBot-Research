from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


EVIDENCE_DIR = PROJECT_ROOT / "phase9_evidence"
AUDIT_PATH = EVIDENCE_DIR / "phase9_management_audit.json"
OLD_MANIFEST = (
    PROJECT_ROOT
    / "phase7_evidence"
    / "NY_OPEN_10"
    / "ny_open_10_manifest.json"
)


def finalize() -> dict:
    report = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    rows = report["rows"]
    old_manifest = json.loads(
        OLD_MANIFEST.read_text(encoding="utf-8")
    )
    old_by_key = {
        (item["symbol"], int(item["entry_index"])): item
        for item in old_manifest["entries"]
    }
    stop_columns = [
        "review_number",
        "source_group",
        "symbol",
        "entry_index",
        "time_utc",
        "direction",
        "setup_id",
        "trigger_index",
        "logical_structure_index",
        "logical_structure_type",
        "logical_wick_price",
        "logical_body_close",
        "atr_at_entry",
        "atr_tolerance",
        "logical_boundary",
        "emergency_broker_stop",
        "broad_pullback_extreme",
        "broad_extreme_rejected",
        "causal_valid",
        "order_api_called",
    ]
    pd.DataFrame(
        [{key: row.get(key) for key in stop_columns} for row in rows]
    ).to_csv(EVIDENCE_DIR / "stop_selection_audit.csv", index=False)

    trail_columns = [
        "review_number",
        "symbol",
        "entry_index",
        "direction",
        "trail_candidate_count",
        "proven_trail_count",
        "trail_movement_count",
        "exit_index",
        "exit_reason",
        "classifications",
    ]
    trail_rows = []
    for row in rows:
        record = {key: row.get(key) for key in trail_columns}
        record["classifications"] = "|".join(
            row.get("classifications", [])
        )
        trail_rows.append(record)
    pd.DataFrame(trail_rows).to_csv(
        EVIDENCE_DIR / "trailing_audit.csv",
        index=False,
    )

    reentry_columns = [
        "review_number",
        "symbol",
        "entry_index",
        "direction",
        "reentry_count",
        "reentry_state",
        "exit_index",
        "exit_reason",
        "classifications",
    ]
    reentry_rows = []
    for row in rows:
        record = {key: row.get(key) for key in reentry_columns}
        record["classifications"] = "|".join(
            row.get("classifications", [])
        )
        reentry_rows.append(record)
    pd.DataFrame(reentry_rows).to_csv(
        EVIDENCE_DIR / "reentry_audit.csv",
        index=False,
    )

    old_vs_new_rows = []
    for row in rows[:10]:
        old_entry = old_by_key[
            (row["symbol"], int(row["entry_index"]))
        ]
        old_extreme = row.get("broad_pullback_extreme")
        logical = row.get("logical_boundary")
        old_vs_new_rows.append(
            {
                "review_number": row["review_number"],
                "symbol": row["symbol"],
                "entry_index": row["entry_index"],
                "direction": row["direction"],
                "old_broad_retracement_extreme": old_extreme,
                "old_phase8_stop_loss": old_entry.get("stop_loss"),
                "new_relevant_structure_index": row[
                    "logical_structure_index"
                ],
                "new_relevant_structure_wick": row[
                    "logical_wick_price"
                ],
                "new_logical_boundary": logical,
                "emergency_broker_stop": row[
                    "emergency_broker_stop"
                ],
                "old_and_new_differ": (
                    old_entry.get("stop_loss") is not None
                    and logical is not None
                    and abs(
                        float(old_entry["stop_loss"])
                        - float(logical)
                    )
                    > 1e-12
                ),
                "entry_index_unchanged": (
                    int(old_entry["entry_index"])
                    == int(row["entry_index"])
                ),
                "entry_price_unchanged": (
                    abs(
                        float(old_entry["entry_price"])
                        - float(row["entry_price"])
                    )
                    < 1e-12
                ),
            }
        )
    pd.DataFrame(old_vs_new_rows).to_csv(
        EVIDENCE_DIR / "old_vs_new_stop_comparison.csv",
        index=False,
    )
    summary = {
        "stop_rows": len(rows),
        "trail_rows": len(trail_rows),
        "reentry_rows": len(reentry_rows),
        "old_vs_new_rows": len(old_vs_new_rows),
        "broad_extreme_rejected_count": sum(
            bool(row.get("broad_extreme_rejected")) for row in rows
        ),
        "proven_trail_examples": sum(
            int(row.get("proven_trail_count", 0)) > 0 for row in rows
        ),
        "opposing_bos_exits": sum(
            row.get("exit_reason") == "OPPOSING_MEANINGFUL_BOS"
            for row in rows
        ),
        "valid_reentries": sum(
            int(row.get("reentry_count", 0)) == 1 for row in rows
        ),
        "dominant_failure_rejections": sum(
            row.get("reentry_state")
            == "REENTRY_REJECTED_DOMINANT_PROTECTION_FAILED"
            for row in rows
        ),
        "order_api_calls": report["order_api_calls"],
    }
    (EVIDENCE_DIR / "audit_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(finalize(), indent=2))
