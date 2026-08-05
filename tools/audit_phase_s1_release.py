from __future__ import annotations

from pathlib import Path
import gzip
import json


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "simulator_evidence"


def main() -> int:
    curated = json.loads((EVIDENCE / "curated_sessions_manifest.json").read_text(encoding="utf-8"))
    sessions = []
    all_hashes: set[str] = set()
    total_seconds = 0.0
    total_events = 0
    total_orders = 0
    fail_flags = []
    reentry_sessions = []
    for row in curated["sessions"]:
        session_id = row["session_id"]
        source = EVIDENCE / "sessions" / session_id / "session.json.gz"
        payload = json.loads(gzip.decompress(source.read_bytes()))
        events = payload["events"]
        hashes = [event["state_hash"] for event in events]
        duplicates = len(hashes) - len(set(hashes))
        all_hashes.update(hashes)
        orders = sum(
            int(bool((event["snapshot"].get("management") or {}).get("order_api_called")))
            for event in events
        )
        failures = [
            {"event": event["event_number"], "title": flag["title"]}
            for event in events for flag in event["bug_flags"]
            if flag["severity"] == "FAIL"
        ]
        reentries = [
            event["event_number"] for event in events
            if event["event_type"] == "REENTRY_OPENED"
        ]
        if reentries:
            reentry_sessions.append(session_id)
        build_seconds = float((payload.get("benchmark") or {}).get("build_seconds") or 0.0)
        total_seconds += build_seconds
        total_events += len(events)
        total_orders += orders
        fail_flags.extend({"session_id": session_id, **item} for item in failures)
        sessions.append({
            "session_id": session_id,
            "events": len(events),
            "build_seconds": build_seconds,
            "duplicate_state_hashes": duplicates,
            "integrity_fail_flags": failures,
            "reentry_events": reentries,
            "orders_called": orders,
            "full_replay_export": str(EVIDENCE / "sessions" / session_id / "exports" / "full_replay_session.zip"),
        })
    audit = {
        "strategy_version": "SMARTSTRUCTUREBOT_SIMULATOR_BASELINE_V0_9",
        "simulator_version": "PHASE_S1",
        "curated_sessions": len(sessions),
        "total_events": total_events,
        "unique_state_hashes": len(all_hashes),
        "reentry_sessions": reentry_sessions,
        "trade_51_present": "S1-CASE-60" in {row["session_id"] for row in sessions},
        "integrity_fail_flags": fail_flags,
        "orders_called": total_orders,
        "sessions": sessions,
        "verdict": "PASS" if len(sessions) >= 12 and len(reentry_sessions) >= 2 and not fail_flags and not total_orders else "FAIL",
    }
    (EVIDENCE / "phase_s1_release_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    benchmark = {
        "sessions": len(sessions),
        "ready_sessions": len(sessions),
        "failed_sessions": 0,
        "total_events": total_events,
        "total_build_seconds": round(total_seconds, 3),
        "mean_build_seconds": round(total_seconds / len(sessions), 3),
        "orders_called": total_orders,
        "note": "Local frozen-data build performance only; not a trading result.",
    }
    (EVIDENCE / "performance_benchmark.json").write_text(json.dumps(benchmark, indent=2), encoding="utf-8")
    print(json.dumps({"audit": audit["verdict"], **benchmark, "reentry_sessions": reentry_sessions}, indent=2))
    return 0 if audit["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
