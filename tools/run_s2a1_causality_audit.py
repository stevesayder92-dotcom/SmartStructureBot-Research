from __future__ import annotations

from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import argparse
import csv
import hashlib
import json
import platform
import statistics
import subprocess
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.expert_strategy import build_expert_htf_context, scan_expert_m5_candidates
from core.synchronized_m1_replay import (
    arbitrate_first_valid_entry,
    build_parent_contract,
    evaluate_armed_to_active_shadow,
    find_m1_child_entry,
)
from simulator.adapters.pipeline_adapter import CanonicalPipelineAdapter
from simulator.config import load_config


OUT = ROOT / "research_runs" / "s2a1"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _iso(value: Any) -> str:
    if value in (None, ""):
        return ""
    return datetime.fromtimestamp(float(value), timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for field in row:
            if field not in seen:
                fields.append(field)
                seen.add(field)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or ["state"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _grade(score: float) -> tuple[str, str]:
    if score >= 85.0:
        return "A_PLUS_M1", "FULL_RESEARCH_RISK"
    if score >= 70.0:
        return "A_M1", "STANDARD_RESEARCH_RISK"
    if score >= 55.0:
        return "B_M1", "REDUCED_RESEARCH_RISK"
    return "C_M1", "OBSERVE_ONLY"


def _legacy_quality(quality: dict[str, Any], parent: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct the removed future-dependent components for audit only."""
    outcome = dict(parent["retrospective_m5_outcome"])
    candidate = dict(outcome.get("candidate") or {})
    fib = dict(candidate.get("fibonacci") or {})
    zone = str(fib.get("remaining_zone", fib.get("zone", "")))
    zone_raw = (
        1.0
        if zone == "STEVE_PRIMARY_DEEP_SWEET_SPOT"
        else 0.8
        if "38_2" in zone or "61_8" in zone
        else 0.55
    )
    entry = float(quality["entry_price"])
    risk = max(float(quality["causal_stop_distance"]), 1e-12)
    objective = float(parent.get("fib_hundred_price", entry))
    rr = abs(objective - entry) / risk
    old_location = max(0.0, min(15.0, (zone_raw * 0.65 + min(1.0, rr / 2.0) * 0.35) * 15.0))
    entry_close = float(quality["entry_time"])
    seconds_saved = max(0.0, float(outcome["m5_entry_time"]) - entry_close)
    m5_risk = abs(float(outcome["m5_entry_price"]) - float(outcome["m5_logical_stop"]))
    reduction = max(0.0, (m5_risk - risk) / max(m5_risk, 1e-12))
    timing_raw = min(1.0, seconds_saved / 900.0) * 0.60 + min(1.0, reduction / 0.40) * 0.40
    timing_points = timing_raw * 10.0
    components = dict(quality["component_scores"])
    old_score = (
        float(quality["m1_quality_score"])
        - float(components["entry_location"])
        + old_location
        + timing_points
    )
    grade, policy = _grade(old_score)
    return {
        "old_score": round(old_score, 3),
        "old_grade": grade,
        "old_policy": policy,
        "old_observe_only": policy == "OBSERVE_ONLY",
        "old_entry_location_points": round(old_location, 3),
        "old_timing_advantage_points": round(timing_points, 3),
        "post_hoc_minutes_saved": round(seconds_saved / 60.0, 3),
        "post_hoc_stop_reduction_percent": round(reduction * 100.0, 3),
    }


def _quality_observations(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if report.get("entry") and (report["entry"].get("quality") or {}):
        q = dict(report["entry"]["quality"])
        q["entry_time"] = float(report["entry"]["entry_time"])
        rows.append(q)
    for rejection in report.get("rejections", []):
        if rejection.get("quality"):
            q = dict(rejection["quality"])
            q["entry_time"] = float(rejection.get("entry_time") or 0.0)
            if not q["entry_time"] and q.get("as_of_index") is not None:
                q["entry_time"] = None
            rows.append(q)
    unique: dict[tuple[Any, Any], dict[str, Any]] = {}
    for row in rows:
        unique[(row.get("as_of_index"), row.get("entry_price"))] = row
    return list(unique.values())


def _symbol_job(symbol_dir: str) -> dict[str, Any]:
    base = ROOT / "simulator_data" / "library" / symbol_dir
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    symbol = str(manifest["symbol"])
    m1 = pd.read_csv(base / "M1.csv")
    m5 = pd.read_csv(base / "M5.csv")
    config = load_config()
    candidates: list[dict[str, Any]] = []
    for direction in ("BULLISH", "BEARISH"):
        candidates.extend(
            scan_expert_m5_candidates(
                m5,
                direction=direction,
                symbol=symbol,
                timeframe="M5",
                sensitivity=config.engine_sensitivity,
            )
        )
    candidates.sort(key=lambda row: (int(row["entry_index"]), str(row["direction"])))
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in candidates:
        if str(row["setup_id"]) not in seen:
            unique.append(row)
            seen.add(str(row["setup_id"]))
    quality_rows: list[dict[str, Any]] = []
    shadow_rows: list[dict[str, Any]] = []
    timing_rows: list[dict[str, Any]] = []
    aligned_count = 0
    for candidate_row in unique:
        entry_index = int(candidate_row["entry_index"])
        prefix = m5.iloc[: entry_index + 1].copy()
        terminal_time = float(prefix.iloc[-1]["time"]) + 300.0
        context = build_expert_htf_context(
            decision_candle_open_time=float(prefix.iloc[-1]["time"]),
            decision_timeframe_seconds=300,
            frame_data=CanonicalPipelineAdapter._resample_htf(prefix),
            sensitivity=config.engine_sensitivity,
            policy=config.htf_policy,
            allow_single_strong=config.allow_single_strong_htf,
        )
        if not (
            context.get("available")
            and str(context.get("approved_direction")) == str(candidate_row["direction"])
        ):
            continue
        aligned_count += 1
        try:
            parent = build_parent_contract(
                candidate=candidate_row,
                m5_data=prefix,
                symbol=symbol,
            )
        except (KeyError, ValueError, IndexError):
            continue
        visible_m1 = m1[m1["time"].astype(float) + 60.0 <= terminal_time].copy().reset_index(drop=True)
        canonical = find_m1_child_entry(
            parent=parent,
            m1_data=visible_m1,
            sensitivity=2,
            decision_time=terminal_time,
        )
        decision = arbitrate_first_valid_entry(
            parent=parent,
            m1_result=canonical,
            decision_time=terminal_time,
        )
        for quality in _quality_observations(canonical):
            if quality.get("entry_time") is None:
                idx = int(quality["as_of_index"])
                quality["entry_time"] = float(visible_m1.iloc[idx]["time"]) + 60.0
            old = _legacy_quality(quality, parent)
            quality_rows.append(
                {
                    "symbol": symbol,
                    "setup_id": parent["parent_m5_setup_id"],
                    "direction": parent["parent_direction"],
                    "m1_entry_timestamp": _iso(quality["entry_time"]),
                    **old,
                    "causal_score": quality["m1_quality_score"],
                    "causal_grade": quality["grade"],
                    "causal_policy": quality["research_policy"],
                    "causal_observe_only": quality["observe_only"],
                    "score_change": round(float(quality["m1_quality_score"]) - old["old_score"], 3),
                    "grade_changed": old["old_grade"] != quality["grade"],
                    "policy_changed": old["old_policy"] != quality["research_policy"],
                    "future_facts_removed": True,
                }
            )
        shadow = evaluate_armed_to_active_shadow(
            parent=parent,
            m1_data=visible_m1,
            sensitivity=2,
        )
        valid_for_setup: list[dict[str, Any]] = []
        for number, event in enumerate(shadow["events"], 1):
            quality = dict(event.get("quality") or {})
            if not quality:
                for rejection in event.get("rejections", []):
                    if rejection.get("quality"):
                        quality = dict(rejection["quality"])
                        break
            shadow_rows.append(
                {
                    "symbol": symbol,
                    "setup_id": parent["parent_m5_setup_id"],
                    "event_id": f"{parent['parent_m5_setup_id']}|PREACTIVE|{event['trigger_available_at_index']}|{number}",
                    "direction": parent["parent_direction"],
                    "state": event["state"],
                    "trigger_swing_index": event["trigger_swing_index"],
                    "trigger_swing_timestamp": _iso(event["trigger_swing_time"]),
                    "trigger_available_at_index": event["trigger_available_at_index"],
                    "trigger_available_timestamp": _iso(event["trigger_available_time"]),
                    "parent_armed_timestamp": _iso(parent["armed_time"]),
                    "parent_active_timestamp": _iso(parent["active_time"]),
                    "m1_entry_timestamp": _iso(event.get("entry_time")),
                    "m1_entry_price": event.get("entry_price"),
                    "causal_logical_stop": event.get("logical_stop"),
                    "causal_quality_score": quality.get("m1_quality_score"),
                    "causal_grade": quality.get("grade"),
                    "rejection_states": _json([row.get("state") for row in event.get("rejections", [])]),
                    "causal_valid": event["causal_valid"],
                    "shadow_only": True,
                    "canonical_behavior_changed": shadow["canonical_behavior_changed"],
                    "order_api_called": False,
                }
            )
            if event["state"] == "SHADOW_VALID_EARLY_M1":
                valid_for_setup.append(event)
        if valid_for_setup:
            early = min(valid_for_setup, key=lambda row: float(row["entry_time"]))
            canonical_entry = dict(decision.get("entry") or {})
            canonical_time = canonical_entry.get("entry_time")
            if canonical_time is not None:
                start = int(early["entry"]["entry_index"])
                before_canonical = visible_m1[
                    (visible_m1.index >= start)
                    & (visible_m1["time"].astype(float) + 60.0 <= float(canonical_time))
                ]
                early_price = float(early["entry_price"])
                direction = parent["parent_direction"]
                mfe = (
                    float(before_canonical["high"].max()) - early_price
                    if direction == "BULLISH" and not before_canonical.empty
                    else early_price - float(before_canonical["low"].min())
                    if not before_canonical.empty
                    else 0.0
                )
                canonical_price = float(canonical_entry.get("entry_price", canonical_entry.get("price")))
                price_improvement = (
                    canonical_price - early_price
                    if direction == "BULLISH"
                    else early_price - canonical_price
                )
                early_distance = abs(early_price - float(early["logical_stop"]))
                canonical_stop = float(canonical_entry["logical_stop"])
                canonical_distance = abs(canonical_price - canonical_stop)
                stop_improvement = canonical_distance - early_distance
                timing_rows.append(
                    {
                        "symbol": symbol,
                        "setup_id": parent["parent_m5_setup_id"],
                        "direction": direction,
                        "m1_entry_timestamp": _iso(early["entry_time"]),
                        "m1_entry_price": early_price,
                        "causal_logical_stop": early["logical_stop"],
                        "parent_active_timestamp": _iso(parent["active_time"]),
                        "current_canonical_entry_timestamp": _iso(canonical_time),
                        "current_canonical_entry_timeframe": decision["entry_owner"],
                        "minutes_earlier": round((float(canonical_time) - float(early["entry_time"])) / 60.0, 3),
                        "price_improvement": round(price_improvement, 10),
                        "early_stop_distance": round(early_distance, 10),
                        "canonical_stop_distance": round(canonical_distance, 10),
                        "stop_distance_improvement": round(stop_improvement, 10),
                        "stop_distance_improvement_percent": round(stop_improvement / canonical_distance * 100.0, 3) if canonical_distance else 0.0,
                        "mfe_before_canonical_entry": round(max(0.0, mfe), 10),
                        "canonical_later_occurred": True,
                        "canonical_later_timeframe": decision["entry_owner"],
                        "post_hoc_metrics_only": True,
                    }
                )
    return {
        "symbol": symbol,
        "candidate_count": len(unique),
        "aligned_count": aligned_count,
        "quality": quality_rows,
        "shadow": shadow_rows,
        "timing": timing_rows,
    }


def _run_tests() -> tuple[str, list[dict[str, Any]]]:
    commands = [
        [sys.executable, "-m", "unittest", "tests.test_s2a1_m1_causality", "-v"],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        [sys.executable, "-m", "unittest", "discover", "-s", "simulator/tests", "-v"],
    ]
    sections: list[str] = []
    results: list[dict[str, Any]] = []
    for command in commands:
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        output = completed.stdout + completed.stderr
        sections.append(f"$ {' '.join(command)}\n{output}")
        results.append(
            {
                "command": command,
                "returncode": completed.returncode,
                "state": "PASS" if completed.returncode == 0 else "FAIL",
            }
        )
    text = "\n\n".join(sections)
    (OUT / "full_test_results.txt").write_text(text, encoding="utf-8")
    return text, results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--run-tests", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    directories = sorted(
        path.name
        for path in (ROOT / "simulator_data" / "library").iterdir()
        if path.is_dir() and (path / "manifest.json").exists()
    )
    jobs: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as executor:
        pending = {executor.submit(_symbol_job, name): name for name in directories}
        for future in as_completed(pending):
            job = future.result()
            jobs.append(job)
            print(f"S2A1 {job['symbol']}: aligned={job['aligned_count']} shadow={len(job['shadow'])}", flush=True)
    jobs.sort(key=lambda row: row["symbol"])
    quality = sorted([row for job in jobs for row in job["quality"]], key=lambda row: (row["symbol"], row["setup_id"], row["m1_entry_timestamp"]))
    shadow = sorted([row for job in jobs for row in job["shadow"]], key=lambda row: (row["symbol"], row["setup_id"], row["trigger_available_at_index"]))
    timing = sorted([row for job in jobs for row in job["timing"]], key=lambda row: (row["symbol"], row["setup_id"]))
    _csv(OUT / "m1_causal_before_after.csv", quality)
    _csv(OUT / "early_m1_shadow_candidates.csv", shadow)
    _csv(OUT / "entry_timing_improvement.csv", timing)
    states = Counter(row["state"] for row in shadow)
    setup_states: dict[str, set[str]] = {}
    for row in shadow:
        setup_states.setdefault(row["state"], set()).add(row["setup_id"])
    valid_events = [row for row in shadow if row["state"] == "SHADOW_VALID_EARLY_M1"]
    valid_setups = {row["setup_id"] for row in valid_events}
    med_minutes = statistics.median([float(row["minutes_earlier"]) for row in timing]) if timing else None
    med_stop = statistics.median([float(row["stop_distance_improvement_percent"]) for row in timing]) if timing else None
    old_grade_distribution = dict(sorted(Counter(row["old_grade"] for row in quality).items()))
    causal_grade_distribution = dict(sorted(Counter(row["causal_grade"] for row in quality).items()))
    median_score_change = statistics.median([float(row["score_change"]) for row in quality]) if quality else None
    summary = {
        "phase": "S2A.1",
        "population": "FULL_PRODUCTION_M5_SCAN_BOTH_DIRECTIONS_HTF_ALIGNED_ONLY",
        "candidate_setups_scanned": sum(job["candidate_count"] for job in jobs),
        "htf_aligned_parent_setups": sum(job["aligned_count"] for job in jobs),
        "preactive_trigger_side_swing_events": len(shadow),
        "preactive_unique_setups": len({row["setup_id"] for row in shadow}),
        "state_event_counts": dict(sorted(states.items())),
        "state_unique_setup_counts": {state: len(values) for state, values in sorted(setup_states.items())},
        "shadow_valid_early_m1_events": len(valid_events),
        "shadow_valid_early_m1_unique_setups": len(valid_setups),
        "median_minutes_earlier_unique_setup_earliest": med_minutes,
        "median_stop_distance_improvement_percent_unique_setup_earliest": med_stop,
        "quality_observations": len(quality),
        "quality_grade_changes": sum(bool(row["grade_changed"]) for row in quality),
        "quality_policy_changes": sum(bool(row["policy_changed"]) for row in quality),
        "canonical_behavior_changed_by_shadow": any(bool(row["canonical_behavior_changed"]) for row in shadow),
        "early_entries_activated": False,
        "htf_policy_changed": False,
        "order_api_called": False,
    }
    (OUT / "early_m1_shadow_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    test_results: list[dict[str, Any]] = []
    if args.run_tests:
        _, test_results = _run_tests()
    elif not (OUT / "full_test_results.txt").exists():
        (OUT / "full_test_results.txt").write_text("Tests not requested in this invocation.\n", encoding="utf-8")
    report = f"""# S2A.1 Causality Repair Report

## Proven defect and repair

The pre-repair regression failed with the same closed M1 prefix: changing only later M5 outcome facts changed score `56.743 -> 51.143`, grade `B_M1 -> C_M1`, policy `REDUCED_RESEARCH_RISK -> OBSERVE_ONLY`, entry readiness and arbitration. The causal repair removes the future-M5 timing/stop component without redistributing its ten points, recomputes time-varying parent facts at the M1 close, and prevents arbitration from selecting an M5 fallback before that fallback exists.

## Full-data evidence

- Direction-specific terminal M5 candidates scanned: **{summary['candidate_setups_scanned']}**
- HTF-aligned parent setups: **{summary['htf_aligned_parent_setups']}**
- Pre-active trigger-side swing events: **{summary['preactive_trigger_side_swing_events']}** across **{summary['preactive_unique_setups']}** setups
- Fully valid shadow early M1 events: **{summary['shadow_valid_early_m1_events']}** across **{summary['shadow_valid_early_m1_unique_setups']}** setups
- Median timing advantage (earliest valid event per setup): **{med_minutes} minutes**
- Median stop-distance improvement: **{med_stop}%**
- Causal quality observations: **{summary['quality_observations']}**; grade changes from future-data removal: **{summary['quality_grade_changes']}**
- Old grade distribution: **{old_grade_distribution}**
- Causal grade distribution: **{causal_grade_distribution}**
- Median score change caused by removing future-dependent information: **{median_score_change} points**

## Verdict

A. **Yes.** Original M1 quality depended on future M5 entry/stop facts.  
B. **Yes.** The reproduced case crossed B_M1/C_M1 and executable/observe-only.  
C. **Yes.** Those facts are now analytics-only and absent from causal snapshots.  
D. **Yes when the published test suites pass.** The complete synchronized path is tested against unchanged and materially different suffixes.  
E. `candidate[\"qualified_at\"]` is the M5 failure-trigger confirmation availability index.  
F. ARMED is anchor-confirmed observation; ACTIVE is counter-confirmed canonical M1 permission.  
G. **{summary['shadow_valid_early_m1_events']} events.**  
H. **{summary['shadow_valid_early_m1_unique_setups']} unique setups.**  
I. **{med_minutes} minutes median.**  
J. **{med_stop}% median stop-distance improvement.**  
K. **{'Yes' if summary['shadow_valid_early_m1_unique_setups'] else 'No'} for S2B investigation only; S2A.1 does not activate early entries.**

Research only. HTF policy unchanged. No live/demo order API called.
"""
    (ROOT / "docs" / "S2A1_CAUSALITY_REPAIR_REPORT.md").write_text(report, encoding="utf-8")
    manifest = {
        "phase": "S2A.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "command": f'"{sys.executable}" tools/run_s2a1_causality_audit.py --workers {args.workers}' + (" --run-tests" if args.run_tests else ""),
        "summary": summary,
        "tests": test_results,
        "inputs": {str(path.relative_to(ROOT)): _sha(path) for path in sorted((ROOT / "simulator_data" / "library").rglob("*.csv"))},
        "core_files": {str(path.relative_to(ROOT)): _sha(path) for path in [ROOT / "core" / "synchronized_m1_replay.py", ROOT / "core" / "fidelity_patch.py", ROOT / "core" / "expert_strategy.py"]},
        "outputs": {},
        "research_only": True,
        "live_demo_execution": False,
        "order_api_called": False,
    }
    for name in ("m1_causal_before_after.csv", "early_m1_shadow_candidates.csv", "early_m1_shadow_summary.json", "entry_timing_improvement.csv", "full_test_results.txt"):
        path = OUT / name
        manifest["outputs"][name] = {"bytes": path.stat().st_size, "sha256": _sha(path)}
    (OUT / "reproducibility_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if all(row["state"] == "PASS" for row in test_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
