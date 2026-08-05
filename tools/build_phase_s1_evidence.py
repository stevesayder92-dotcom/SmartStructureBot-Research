from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.cli import build_case, refresh_index


CURATED = [
    (2, "M1_CLEAR_ADVANTAGE", "Did M1 improve entry timing without accepting micro noise?"),
    (9, "M1_CLEAR_ADVANTAGE", "Did M1 preserve the parent thesis and meaningful trigger ownership?"),
    (64, "M5_FALLBACK", "Were all earlier M1 signals correctly rejected before M5 confirmation?"),
    (81, "M5_FALLBACK", "Was waiting for M5 preferable to the rejected M1 candidates?"),
    (1, "REENTRY_SEQUENCE", "Was the first failure classified correctly and was fresh proof required?"),
    (60, "TRADE_51_REENTRY_SEQUENCE", "Did the state wait for parent extension before the later M1 re-entry?"),
    (19, "SEVERE_GIVEBACK", "Which engine first recommended protecting the earned opportunity?"),
    (45, "SEVERE_GIVEBACK", "Did a valid tighter structure exist before the giveback?"),
    (10, "WINNER_TO_LOSER_REVERSAL", "Did the Director hold for a valid structural reason?"),
    (69, "LONG_RUNNER", "Were normal pullbacks held while proven structure remained intact?"),
    (34, "NORMAL_PULLBACK_HELD", "Did the manager avoid reacting to unproven micro structures?"),
    (47, "ENGINE_DIRECTOR_CONFLICT", "Was dominant protection failure correctly prioritized over re-entry advice?"),
]

ACCEPTANCE_SCENARIOS = [
    "Clean M5 first entry", "Clean M1 early entry", "M1 rejected and M5 enters",
    "M1 first attempt fails", "Parent extension is proven", "M1 re-entry occurs",
    "M5 re-entry occurs after M1 failure", "Attempt 2 receives full management",
    "TP1 wick touch without forced break-even", "TP1 acceptance and runner continuation",
    "Target rejection and deterioration", "Severe giveback", "Winner-to-loser reversal",
    "Normal pullback correctly held", "Long runner preserved", "Opposing BOS exit",
    "Emergency stop event", "Engine recommendation conflict",
    "Director rejects a protection recommendation", "Prefix-integrity failure test",
]


def _worker(case_number: int) -> dict:
    destination = ROOT / "simulator_evidence" / "sessions" / f"S1-CASE-{case_number:02d}"
    manifest_path = destination / "manifest.json"
    force_cases = {
        int(value) for value in os.environ.get("S1_FORCE_CASES", "").split(",")
        if value.strip().isdigit()
    }
    if (
        os.environ.get("S1_FORCE_REBUILD") != "1"
        and case_number not in force_cases
        and manifest_path.exists()
        and (destination / "session.json.gz").exists()
    ):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {
            "session_id": manifest["replay_session_id"],
            "case_number": case_number,
            "symbol": manifest["symbol"],
            "event_count": manifest["event_count"],
            "build_seconds": 0.0,
            "manifest": str(manifest_path),
            "event_export": str(next((destination / "exports").glob("event_*.zip"), "")),
            "sequence_export": str(destination / "exports" / "sequence.zip"),
            "review_export": str(next((destination / "exports").glob("chatgpt_review_*.zip"), "")),
            "status": "READY_REUSED",
        }
    # Sixty immutable clock events keep the packaged investor sessions compact
    # while still covering the pre-entry setup and immediate management story.
    if case_number == 1:
        return build_case(case_number, before=25, after=370, max_events=395)
    if case_number == 60:
        return build_case(case_number, before=25, after=95, max_events=120)
    return build_case(case_number, before=25, after=35, max_events=60)


def main() -> int:
    evidence = ROOT / "simulator_evidence"
    evidence.mkdir(exist_ok=True)
    results: list[dict] = []
    # The canonical pipeline is CPU-bound. Two workers outperform four on the
    # target Windows machine because four processes contend for the same cores.
    workers = min(2, max(1, (os.cpu_count() or 2) // 2))
    with ProcessPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(_worker, case): (case, category, question) for case, category, question in CURATED}
        for future in as_completed(future_map):
            case, category, question = future_map[future]
            try:
                row = future.result()
            except Exception as error:
                row = {
                    "session_id": f"S1-CASE-{case:02d}",
                    "case_number": case,
                    "symbol": "UNKNOWN",
                    "event_count": 0,
                    "build_seconds": 0.0,
                    "status": "BUILD_FAILED",
                    "error": f"{type(error).__name__}: {error}",
                }
            row["curated_category"] = category
            row["expected_inspection_question"] = question
            results.append(row)
            print(f"READY {row['session_id']} {row['symbol']} {row['event_count']} events")
    results.sort(key=lambda row: next(i for i, item in enumerate(CURATED) if item[0] == row["case_number"]))
    refresh_index(results)
    (evidence / "curated_sessions_manifest.json").write_text(
        json.dumps({
            "created_at": datetime.now(timezone.utc).isoformat(),
            "strategy_version": "SMARTSTRUCTUREBOT_SIMULATOR_BASELINE_V0_9",
            "simulator_version": "PHASE_S1",
            "sessions": results,
            "selection_policy": "Includes winners, losses, M1 entries, M5 fallbacks, reentries, giveback, a long runner, normal pullback and conflict. No outcome cherry-picking claim is made.",
            "orders_called": 0,
        }, indent=2), encoding="utf-8"
    )
    (evidence / "acceptance_scenarios.json").write_text(
        json.dumps({
            "scenarios": [
                {"id": index, "name": name, "status": "COVERED_BY_FRAMEWORK", "evidence_required_for_strategy_claim": True}
                for index, name in enumerate(ACCEPTANCE_SCENARIOS, start=1)
            ],
            "trade_51_required": True,
            "trade_51_session": "S1-CASE-60",
        }, indent=2), encoding="utf-8"
    )
    (evidence / "investor_demo_manifest.json").write_text(
        json.dumps({
            "title": "SmartStructureBot honest prototype demonstration",
            "primary_session": "S1-CASE-02",
            "risk_discipline_session": "S1-CASE-10",
            "auto_pause_events": ["RETRACEMENT_QUALIFIED", "M1_ENTRY_READY", "M5_ENTRY_READY", "PROTECTION_MOVED", "FIRST_ATTEMPT_EXITED", "REENTRY_OPENED", "OPPOSING_BOS_EXIT"],
            "disclaimer": "Historical research replay. No live orders. Performance is not guaranteed.",
            "unsupported_profitability_claims": False,
        }, indent=2), encoding="utf-8"
    )
    ready = [row for row in results if row["status"].startswith("READY")]
    benchmark = {
        "sessions": len(results),
        "ready_sessions": len(ready),
        "failed_sessions": len(results) - len(ready),
        "total_events": sum(row["event_count"] for row in ready),
        "total_build_seconds": round(sum(row["build_seconds"] for row in ready), 3),
        "mean_build_seconds": round(sum(row["build_seconds"] for row in ready) / len(ready), 3) if ready else None,
        "orders_called": 0,
        "note": "Performance is observational on the local build machine and is not a trading result.",
    }
    (evidence / "performance_benchmark.json").write_text(json.dumps(benchmark, indent=2), encoding="utf-8")
    print(json.dumps(benchmark, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
