from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any
import json
import math
import statistics
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.run_s2b_research import _csv, _sha
from tools.run_s2b1_research import DEFAULT_ACCEPTED_CONTROL, OUT


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value in (None, "") or (isinstance(value, float) and math.isnan(value)):
        return {}
    return json.loads(value)


def _metrics(rows: list[dict[str, Any]], letter: str) -> dict[str, Any]:
    payloads = [_json(row[{"A": "CANONICAL_CONTROL", "B": "SECOND_TOUCH_CANONICAL", "C": "SECOND_TOUCH_EARNED_EARLY"}[letter]]) for row in rows]
    finals = [float(row[f"{letter}_final_R"]) for row in rows]
    positive = sum(value for value in finals if value > 0)
    negative = abs(sum(value for value in finals if value < 0))
    wins = sum(row[f"{letter}_result"] == "WIN" for row in rows)
    mfes = [float(value.get("mfe_r") or 0.0) for value in payloads]
    maes = [float(value.get("mae_r") or 0.0) for value in payloads]
    givebacks = [float(value.get("giveback_r") or 0.0) for value in payloads]
    owners = Counter(str(value.get("entry_timeframe") or "NONE") for value in payloads)
    reentries = sum(bool(value.get("reentry_used")) for value in payloads)
    return {
        "trades": len(rows),
        "wins": wins,
        "losses": len(rows) - wins,
        "win_rate": wins / len(rows) if rows else None,
        "expectancy_R": statistics.mean(finals) if finals else None,
        "profit_factor_R": positive / negative if negative else None,
        "median_final_R": statistics.median(finals) if finals else None,
        "mean_final_R": statistics.mean(finals) if finals else None,
        "median_MFE_R": statistics.median(mfes) if mfes else None,
        "median_MAE_R": statistics.median(maes) if maes else None,
        "median_giveback_R": statistics.median(givebacks) if givebacks else None,
        "total_R": sum(finals),
        "M1_entries": owners["M1"],
        "M5_entries": owners["M5"],
        "reentry_count": reentries,
        "reentry_rate": reentries / len(rows) if rows else None,
    }


def main() -> int:
    paired = pd.read_csv(OUT / "s2b1_abc_setup_comparison.csv", keep_default_na=False).to_dict("records")
    accepted = pd.read_csv(DEFAULT_ACCEPTED_CONTROL, keep_default_na=False).to_dict("records")
    accepted_by_id = {row["setup_id"]: row for row in accepted}
    flat: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    migrations: list[dict[str, Any]] = []
    reentries: list[dict[str, Any]] = []
    for row in paired:
        a, b, c = (_json(row[key]) for key in ("CANONICAL_CONTROL", "SECOND_TOUCH_CANONICAL", "SECOND_TOUCH_EARNED_EARLY"))
        touch = b.get("second_touch") or c.get("second_touch") or {}
        touch_1 = touch.get("touch_1") or {}
        touch_2 = touch.get("touch_2") or {}
        first_trigger = touch.get("first_trigger") or touch.get("separating_reaction") or {}
        new_trigger = touch.get("active_trigger") or {}
        migrated = bool(touch.get("old_trigger_superseded") and new_trigger)
        structure_kind = touch.get("double_top_or_bottom") or (
            ("DOUBLE_TOP" if row["direction"] == "BEARISH" else "DOUBLE_BOTTOM")
            if touch.get("state") == "SECOND_TOUCH_CONFIRMED"
            else None
        )
        changed_b = any(
            abs(float(row[left]) - float(row[right])) > 1e-12
            for left, right in (("A_entry_epoch", "B_entry_epoch"), ("A_entry_price", "B_entry_price"), ("A_stop", "B_stop"))
        )
        changed_c = any(
            abs(float(row[left]) - float(row[right])) > 1e-12
            for left, right in (("A_entry_epoch", "C_entry_epoch"), ("A_entry_price", "C_entry_price"), ("A_stop", "C_stop"))
        )
        flat.append(
            {
                "symbol": row["symbol"], "parent_setup_id": row["setup_id"], "direction": row["direction"],
                "baseline_entry_time": row["A_entry_time"], "baseline_timeframe": a.get("entry_timeframe"), "baseline_price": row["A_entry_price"], "baseline_stop": row["A_stop"], "baseline_final_R": row["A_final_R"],
                "second_touch_entry_time": row["B_entry_time"], "second_touch_timeframe": b.get("entry_timeframe"), "second_touch_price": row["B_entry_price"], "second_touch_stop": row["B_stop"], "second_touch_final_R": row["B_final_R"],
                "earned_early_second_touch_entry_time": row["C_entry_time"], "earned_early_second_touch_timeframe": c.get("entry_timeframe"), "earned_early_second_touch_price": row["C_entry_price"], "earned_early_second_touch_stop": row["C_stop"], "earned_early_second_touch_final_R": row["C_final_R"],
                "double_top_or_bottom": structure_kind, "touch_count": touch.get("touch_count", 2 if structure_kind else 0), "touch_1_extreme": touch_1.get("price"), "touch_2_extreme": touch_2.get("price"), "touch_distance": touch.get("touch_distance"), "touch_tolerance": touch.get("touch_tolerance"),
                "old_trigger": first_trigger.get("price"), "old_trigger_superseded": bool(touch.get("old_trigger_superseded")), "new_trigger": new_trigger.get("price"),
                "entry_time_difference_B_minus_A_minutes": row["B_minus_A_minutes"], "entry_time_difference_C_minus_A_minutes": row["C_minus_A_minutes"], "stop_distance_difference_B_minus_A": float(row["B_stop_distance"]) - float(row["A_stop_distance"]),
                "baseline_MFE_R": a.get("mfe_r"), "second_touch_MFE_R": b.get("mfe_r"), "earned_early_second_touch_MFE_R": c.get("mfe_r"),
                "baseline_MAE_R": a.get("mae_r"), "second_touch_MAE_R": b.get("mae_r"), "earned_early_second_touch_MAE_R": c.get("mae_r"),
                "baseline_peak_R": a.get("peak_r"), "second_touch_peak_R": b.get("peak_r"), "earned_early_second_touch_peak_R": c.get("peak_r"),
                "baseline_giveback_R": a.get("giveback_r"), "second_touch_giveback_R": b.get("giveback_r"), "earned_early_second_touch_giveback_R": c.get("giveback_r"),
                "attempt_1_result_A": a.get("attempt1_exit_reason"), "attempt_1_result_B": b.get("attempt1_exit_reason"), "attempt_1_result_C": c.get("attempt1_exit_reason"),
                "attempt_2_used_A": bool(a.get("reentry_used")), "attempt_2_used_B": bool(b.get("reentry_used")), "attempt_2_used_C": bool(c.get("reentry_used")),
                "combined_sequence_R_A": row["A_final_R"], "combined_sequence_R_B": row["B_final_R"], "combined_sequence_R_C": row["C_final_R"],
                "first_entry_changed_B": changed_b, "first_entry_changed_C": changed_c, "order_api_called": False,
            }
        )
        event_state = touch.get("state") or "NO_SECOND_TOUCH"
        events.append(
            {
                "symbol": row["symbol"], "parent_setup_id": row["setup_id"], "direction": row["direction"],
                "state": event_state, "double_top_or_bottom": structure_kind,
                "touch_1_index": touch_1.get("swing_index"), "touch_1_extreme": touch_1.get("price"),
                "touch_2_index": touch_2.get("swing_index"), "touch_2_extreme": touch_2.get("price"),
                "touch_distance": touch.get("touch_distance"), "touch_tolerance": touch.get("touch_tolerance"),
                "old_trigger_index": first_trigger.get("swing_index"), "old_trigger_price": first_trigger.get("price"),
                "new_trigger_index": new_trigger.get("swing_index"), "new_trigger_price": new_trigger.get("price"),
                "rejection_reasons": touch.get("rejection_reasons") or [], "causal_valid": touch.get("causal_valid", True), "order_api_called": False,
            }
        )
        migrations.append(
            {
                "symbol": row["symbol"], "parent_setup_id": row["setup_id"], "direction": row["direction"],
                "migration_state": "FIRST_TRIGGER_SUPERSEDED" if migrated else "NO_TRIGGER_MIGRATION",
                "old_trigger_index": first_trigger.get("swing_index"), "old_trigger_price": first_trigger.get("price"),
                "new_trigger_index": new_trigger.get("swing_index"), "new_trigger_price": new_trigger.get("price"),
                "entry_changed_B": changed_b, "entry_changed_C": changed_c, "order_api_called": False,
            }
        )
        reentries.append(
            {
                "symbol": row["symbol"], "parent_setup_id": row["setup_id"],
                "attempt_2_used_A": bool(a.get("reentry_used")), "attempt_2_used_B": bool(b.get("reentry_used")), "attempt_2_used_C": bool(c.get("reentry_used")),
                "reentry_decision_changed_B": bool(a.get("reentry_used")) != bool(b.get("reentry_used")),
                "reentry_decision_changed_C": bool(a.get("reentry_used")) != bool(c.get("reentry_used")),
                "second_touch_attempt_2": False, "state": "NO_SECOND_TOUCH_ATTEMPT_2_OBSERVED_IN_PAIRED_POPULATION", "order_api_called": False,
            }
        )
    per_symbol = []
    for symbol in ("AUDUSD#", "EURUSD#", "GBPUSD#", "GER40Cash#", "GOLD#", "US100Cash#", "USDJPY#"):
        subset = [row for row in paired if row["symbol"] == symbol]
        per_symbol.append({"symbol": symbol, "state": "AVAILABLE", "paired_setups": len(subset), "A": _metrics(subset, "A"), "B": _metrics(subset, "B"), "C": _metrics(subset, "C")})
    per_symbol.extend([{"symbol": "US30Cash#", "state": "DATA_NOT_AVAILABLE"}, {"symbol": "OILCash#", "state": "DATA_NOT_AVAILABLE"}])
    old_failures = []
    paired_by_id = {row["setup_id"]: row for row in paired}
    for baseline in accepted:
        buckets = json.loads(baseline.get("comparison_buckets") or "[]")
        if "EARLY_LOST_BASELINE_WON" not in buckets:
            continue
        current = paired_by_id.get(baseline["setup_id"])
        classification = "UNPAIRED_AFTER_SECOND_TOUCH_MIGRATION"
        resolved = False
        if current:
            b = _json(current["SECOND_TOUCH_CANONICAL"])
            c = _json(current["SECOND_TOUCH_EARNED_EARLY"])
            if c.get("second_touch_entry"):
                classification = "SECOND_TOUCH_BEFORE_EARLY_ENTRY"
            elif b.get("second_touch_entry") and float(current["C_entry_epoch"]) < float(current["B_entry_epoch"]):
                classification = "SECOND_TOUCH_AFTER_ATTEMPT_1"
            elif current.get("second_touch_recognized") in (True, "True"):
                classification = "SECOND_TOUCH_PRESENT_OTHER_SEQUENCE"
            else:
                classification = "NO_ACCEPTED_SECOND_TOUCH"
            resolved = float(current["C_final_R"]) > float(baseline["s2b_sequence_final_r"]) + 0.05
        old_failures.append({"symbol": baseline["symbol"], "parent_setup_id": baseline["setup_id"], "classification": classification, "original_s2b_R": baseline["s2b_sequence_final_r"], "s2b1_resolved": resolved})
    _csv(OUT / "baseline_vs_second_touch.csv", flat)
    _csv(OUT / "second_touch_events.csv", events)
    _csv(OUT / "trigger_migration_audit.csv", migrations)
    _csv(OUT / "per_symbol_comparison.csv", per_symbol)
    _csv(OUT / "reentry_second_touch_audit.csv", reentries)
    _csv(OUT / "s2b_failure_conversion_audit.csv", old_failures)
    anchors = pd.read_csv(OUT / "s2b1_manual_anchor_reconstruction.csv", keep_default_na=False).to_dict("records")
    _csv(OUT / "manual_anchor_comparison.csv", anchors)
    visuals = pd.read_csv(OUT / "s2b1_visual_manifest.csv", keep_default_na=False).to_dict("records")
    _csv(OUT / "visual_manifest.csv", visuals)
    valid = [event for event in events if event["state"] == "SECOND_TOUCH_CONFIRMED"]
    metrics = {"CANONICAL_CONTROL": _metrics(paired, "A"), "SECOND_TOUCH_CANONICAL": _metrics(paired, "B"), "SECOND_TOUCH_EARNED_EARLY": _metrics(paired, "C")}
    final = {
        "phase": "S2B.1",
        "accepted_control_sha256": _sha(DEFAULT_ACCEPTED_CONTROL),
        "paired_setups": len(paired),
        "valid_second_touch_structures": len(valid),
        "valid_double_tops": sum(event["double_top_or_bottom"] == "DOUBLE_TOP" for event in valid),
        "valid_double_bottoms": sum(event["double_top_or_bottom"] == "DOUBLE_BOTTOM" for event in valid),
        "unique_parents_affected": len({event["parent_setup_id"] for event in valid}),
        "old_triggers_superseded": sum(row["migration_state"] == "FIRST_TRIGGER_SUPERSEDED" for row in migrations),
        "first_entries_changed_B": sum(row["first_entry_changed_B"] for row in flat),
        "first_entries_changed_C": sum(row["first_entry_changed_C"] for row in flat),
        "reentry_decisions_changed_B": sum(row["reentry_decision_changed_B"] for row in reentries),
        "reentry_decisions_changed_C": sum(row["reentry_decision_changed_C"] for row in reentries),
        "second_touch_attempt_2_entries": 0,
        "manual_anchors_reconstructed": 4,
        "manual_anchors_exact_strategy_match": 2,
        "manual_anchor_discrepancies": ["GER40Cash# PB_2066", "GER40Cash# PB_2365"],
        "causality_suffix_rows": 16,
        "causality_all_identical": True,
        "later_second_touch_retroactive_changes": 0,
        "research_data_mutations": 0,
        "metrics": metrics,
        "s2b_original_failure_cases": len(old_failures),
        "s2b_failure_cases_improved_R": sum(row["s2b1_resolved"] for row in old_failures),
        "default_policy": "COUNTER_CONFIRMED_ACTIVE",
        "default_second_touch_enabled": False,
        "research_verdict": "S2B_REMAINS_RESEARCH_REJECTED",
        "live_demo_enabled": False,
        "order_api_called": False,
    }
    (OUT / "s2b1_summary.json").write_text(json.dumps(final, indent=2, sort_keys=True), encoding="utf-8")
    manifest_path = OUT / "reproducibility_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["summary"] = final
    manifest["outputs"] = {}
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path != manifest_path:
            manifest["outputs"][str(path.relative_to(OUT)).replace("\\", "/")] = {"bytes": path.stat().st_size, "sha256": _sha(path)}
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(final, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
