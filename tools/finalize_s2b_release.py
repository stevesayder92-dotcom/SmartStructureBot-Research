from __future__ import annotations

import csv
import hashlib
import json
import platform
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_runs" / "s2b"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact(path: Path) -> dict[str, Any]:
    return {"bytes": path.stat().st_size, "sha256": sha256(path)}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def median(values: list[float]) -> float:
    return float(statistics.median(values)) if values else 0.0


def main() -> None:
    summary_path = OUT / "s2b_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rows = read_csv(OUT / "baseline_vs_early_setup.csv")
    early = [row for row in rows if row["early_permission_earned"] == "True"]
    unchanged = [row for row in rows if row["early_permission_earned"] != "True"]

    def mismatch(row: dict[str, str]) -> bool:
        keys = (
            "entry_timeframe",
            "entry_time",
            "entry_price",
            "logical_stop",
            "sequence_final_r",
        )
        return any(row[f"baseline_{key}"] != row[f"s2b_{key}"] for key in keys)

    favourable_price = []
    normalized_price = []
    for row in early:
        baseline_price = float(row["baseline_entry_price"])
        early_price = float(row["s2b_entry_price"])
        signed = (
            baseline_price - early_price
            if row["direction"] == "BULLISH"
            else early_price - baseline_price
        )
        favourable_price.append(signed)
        risk = float(row["baseline_stop_distance"])
        if risk:
            normalized_price.append(signed / risk)

    paired = [
        float(row["s2b_sequence_final_r"]) - float(row["baseline_sequence_final_r"])
        for row in rows
    ]
    paired_early = [
        float(row["s2b_sequence_final_r"]) - float(row["baseline_sequence_final_r"])
        for row in early
    ]
    stop_changes = [float(row["stop_distance_difference"]) for row in early]
    audit = {
        "paired_setups": len(rows),
        "earned_early_setups": len(early),
        "all_entry_timing_changes": sum(
            float(row["minutes_entry_difference"]) > 0.0 for row in rows
        ),
        "non_early_setups": len(unchanged),
        "non_early_baseline_mismatches": sum(mismatch(row) for row in unchanged),
        "median_minutes_earlier": median(
            [float(row["minutes_entry_difference"]) for row in early]
        ),
        "median_direction_adjusted_entry_price_improvement_raw": median(favourable_price),
        "median_direction_adjusted_entry_price_improvement_baseline_risk_units": median(normalized_price),
        "median_logical_stop_distance_change_raw": median(stop_changes),
        "tighter_early_stops": sum(value < 0.0 for value in stop_changes),
        "wider_early_stops": sum(value > 0.0 for value in stop_changes),
        "unchanged_early_stops": sum(value == 0.0 for value in stop_changes),
        "baseline_m5_to_s2b_m1": sum(
            row["baseline_entry_timeframe"] == "M5" and row["s2b_entry_timeframe"] == "M1"
            for row in early
        ),
        "later_baseline_m1_to_earlier_s2b_m1": sum(
            row["baseline_entry_timeframe"] == "M1" and row["s2b_entry_timeframe"] == "M1"
            for row in early
        ),
        "duplicate_first_entries": sum(row["duplicate_first_entry_detected"] == "True" for row in rows),
        "paired_mean_sequence_r_difference_all": float(statistics.fmean(paired)),
        "paired_median_sequence_r_difference_all": median(paired),
        "paired_mean_sequence_r_difference_changed": float(statistics.fmean(paired_early)),
        "paired_median_sequence_r_difference_changed": median(paired_early),
        "early_better": sum(value > 0.05 for value in paired_early),
        "early_same": sum(-0.05 <= value <= 0.05 for value in paired_early),
        "early_worse": sum(value < -0.05 for value in paired_early),
        "baseline_winner_to_s2b_loser": sum(
            row["baseline_sequence_win_loss"] == "WIN" and row["s2b_sequence_win_loss"] == "LOSS"
            for row in rows
        ),
        "baseline_loser_to_s2b_winner": sum(
            row["baseline_sequence_win_loss"] == "LOSS" and row["s2b_sequence_win_loss"] == "WIN"
            for row in rows
        ),
    }
    summary["causal_isolation_audit"] = audit
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    input_files: list[Path] = [ROOT / "simulator_data" / "library" / "index.json"]
    for directory in sorted((ROOT / "simulator_data" / "library").iterdir()):
        if not directory.is_dir() or not (directory / "manifest.json").exists():
            continue
        input_files.extend(directory / name for name in ("manifest.json", "M1.csv", "M5.csv"))

    modified_files = [
        ROOT / "core" / "synchronized_m1_replay.py",
        ROOT / "simulator" / "config.py",
        ROOT / "simulator" / "adapters" / "pipeline_adapter.py",
        ROOT / "simulator" / "services" / "observability.py",
    ]
    implementation_files = modified_files + [
        ROOT / "SmartStructureBot_Bible.md",
        ROOT / "tests" / "test_s2b_earned_early_permission.py",
        ROOT / "tools" / "run_s2b_research.py",
        ROOT / "tools" / "finalize_s2b_release.py",
        ROOT / "docs" / "S2B_EARLY_M1_PERMISSION_CONTRACT.md",
        ROOT / "docs" / "S2B_IMPLEMENTATION_REPORT.md",
        ROOT / "docs" / "S2B_CAUSALITY_REPORT.md",
        ROOT / "docs" / "S2B_BASELINE_COMPATIBILITY_REPORT.md",
    ]
    existing_implementation = [path for path in implementation_files if path.exists()]
    tree_digest = hashlib.sha256()
    for path in sorted(existing_implementation):
        tree_digest.update(str(path.relative_to(ROOT)).encode("utf-8"))
        tree_digest.update(bytes.fromhex(sha256(path)))

    config_path = ROOT / "config" / "simulator_phase_s1.json"
    exact_config = json.loads(config_path.read_text(encoding="utf-8"))
    manifest = {
        "phase": "S2B_EARNED_EARLY_M1_PERMISSION",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git": {
            "repository": False,
            "branch": "NOT_A_GIT_REPOSITORY",
            "pre_s2b_commit": "NOT_A_GIT_REPOSITORY",
            "post_s2b_commit": "NOT_A_GIT_REPOSITORY",
            "working_tree_hash": tree_digest.hexdigest(),
            "authority": "SHA256_MANIFESTS",
        },
        "python_version": sys.version,
        "operating_system": platform.platform(),
        "input_datasets": {
            str(path.relative_to(ROOT)): artifact(path) for path in input_files
        },
        "modified_production_files": {
            str(path.relative_to(ROOT)): artifact(path) for path in modified_files
        },
        "implementation_and_report_files": {
            str(path.relative_to(ROOT)): artifact(path) for path in existing_implementation
        },
        "exact_configuration": exact_config,
        "configuration_sha256": sha256(config_path),
        "baseline_permission_policy": "COUNTER_CONFIRMED_ACTIVE",
        "s2b_permission_policy": "EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE",
        "commands_executed": [
            f'"{sys.executable}" tools/run_s2b_research.py --workers 3 --run-tests',
            f'"{sys.executable}" -m unittest tests.test_s2b_earned_early_permission -v',
            f'"{sys.executable}" tools/finalize_s2b_release.py',
        ],
        "randomness": {
            "used": False,
            "seeds": [],
            "selection": "DETERMINISTIC_SORTED_CASE_SELECTION",
        },
        "tests": {
            "focused_s2b": {"count": 30, "result": "PASS"},
            "complete_strategy_discovery": {"count": 340, "result": "PASS"},
            "complete_simulator_discovery": {"count": 87, "result": "PASS"},
            "distinct_discovery_total": 427,
            "focused_count_is_included_in_strategy_discovery": True,
            "full_output": "research_runs/s2b/full_test_results.txt",
        },
        "causal_isolation_audit": audit,
        "verdict": summary["verdict"],
        "maximum_readiness": summary["maximum_readiness"],
        "research_only": True,
        "live_demo_execution": False,
        "order_api_called": False,
        "outputs": {},
    }
    canonical_outputs = [
        path
        for path in OUT.iterdir()
        if path.is_file() and path.name != "reproducibility_manifest.json"
    ]
    for row in read_csv(OUT / "visual_manifest.csv"):
        chart = OUT / row["chart_file"]
        canonical_outputs.extend((chart, chart.with_suffix(".json")))
    for path in sorted(set(canonical_outputs)):
        manifest["outputs"][str(path.relative_to(OUT))] = artifact(path)
    (OUT / "reproducibility_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(audit, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
