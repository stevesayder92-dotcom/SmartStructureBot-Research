from __future__ import annotations

from pathlib import Path
import argparse
import gzip
import json
import sys

from simulator.adapters.dataset_adapter import DatasetAdapter
from simulator.app import serve
from simulator.config import load_config, project_root
from simulator.kernel.replay_session import ReplaySession
from simulator.services.export_service import ExportService
from simulator.models.financial import AccountConfig, ExecutionConfig
from simulator.services.data_library_service import DataLibraryService, parse_replay_time


def build_case(case_number: int, before: int, after: int, max_events: int | None = None) -> dict:
    root = project_root()
    adapter = DatasetAdapter(root)
    session = ReplaySession.from_case(
        adapter, case_number=case_number, config=load_config(),
        before_minutes=before, after_minutes=after,
    ).build(max_events=max_events)
    destination = root / "simulator_evidence" / "sessions" / session.session_id
    destination.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(session.browser_payload(), separators=(",", ":")).encode("utf-8")
    (destination / "session.json.gz").write_bytes(gzip.compress(raw, compresslevel=9))
    (destination / "manifest.json").write_text(
        json.dumps(session.manifest(), indent=2, sort_keys=True), encoding="utf-8"
    )
    exports = ExportService(session, destination / "exports")
    significant = [event.event_number for event in session.events if event.event_priority >= 80]
    focus = significant[0] if significant else len(session.events) - 1
    event_zip = exports.export_event(focus)
    review_zip = exports.export_review_package(focus)
    sequence_zip = exports.export_sequence()
    full_replay_zip = exports.export_full_replay()
    financial_zip = exports.export_financial()
    return {
        "session_id": session.session_id,
        "case_number": case_number,
        "symbol": session.dataset.symbol,
        "event_count": len(session.events),
        "build_seconds": round(session.build_seconds, 3),
        "focus_event": focus,
        "manifest": str(destination / "manifest.json"),
        "event_export": str(event_zip),
        "sequence_export": str(sequence_zip),
        "review_export": str(review_zip),
        "full_replay_export": str(full_replay_zip),
        "financial_export": str(financial_zip),
        "status": "READY",
    }


def refresh_index(rows: list[dict] | None = None) -> Path:
    root = project_root() / "simulator_evidence" / "sessions"
    root.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict] = {}
    index_path = root / "index.json"
    if index_path.exists():
        existing = {row["session_id"]: row for row in json.loads(index_path.read_text(encoding="utf-8"))}
    for row in rows or []:
        existing[row["session_id"]] = row
    for manifest_path in root.glob("*/manifest.json"):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        session_id = manifest["replay_session_id"]
        existing.setdefault(session_id, {
            "session_id": session_id,
            "case_number": manifest.get("case_number"),
            "symbol": manifest.get("symbol"),
            "event_count": manifest.get("event_count"),
            "status": "READY",
        })
    index_path.write_text(json.dumps(sorted(existing.values(), key=lambda row: row["session_id"]), indent=2), encoding="utf-8")
    return index_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SmartStructureBot Phase S1 causal simulator")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("serve", help="Launch the local browser simulator")
    run.add_argument("--host", default="127.0.0.1")
    run.add_argument("--port", default=8765, type=int)
    run.add_argument("--no-browser", action="store_true")
    build = sub.add_parser("build", help="Build an immutable frozen-case replay")
    build.add_argument("--case", type=int, required=True)
    build.add_argument("--before-minutes", type=int, default=55)
    build.add_argument("--after-minutes", type=int, default=120)
    build.add_argument("--max-events", type=int)
    cases = sub.add_parser("cases", help="List frozen replay cases")
    cases.add_argument("--limit", type=int, default=60)
    sub.add_parser("library", help="List portable replay datasets")
    dynamic = sub.add_parser("build-range", help="Build an arbitrary closed-candle replay range")
    dynamic.add_argument("--symbol", required=True)
    dynamic.add_argument("--start", required=True)
    dynamic.add_argument("--end", required=True)
    dynamic.add_argument("--balance", type=float, default=1000.0)
    dynamic.add_argument("--risk-percent", type=float, default=1.0)
    dynamic.add_argument("--max-events", type=int)
    args = parser.parse_args(argv)
    if args.command == "serve":
        serve(host=args.host, port=args.port, open_browser=not args.no_browser)
        return 0
    if args.command == "build":
        result = build_case(args.case, args.before_minutes, args.after_minutes, args.max_events)
        refresh_index([result])
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "library":
        print(json.dumps(DataLibraryService().list_symbols(), indent=2))
        return 0
    if args.command == "build-range":
        library = DataLibraryService()
        dataset = library.load(args.symbol)
        account = AccountConfig(starting_balance=args.balance, risk_percent=args.risk_percent)
        execution = ExecutionConfig()
        session_id = f"S1B-CLI-{args.symbol.replace('#','')}-{int(parse_replay_time(args.start))}"
        session = ReplaySession(
            dataset=dataset,
            config=load_config(),
            session_id=session_id,
            start_time=parse_replay_time(args.start),
            end_time=parse_replay_time(args.end),
            case_metadata={"source": "CLI_DYNAMIC_RANGE"},
            account_config=account,
            execution_config=execution,
        ).build(max_events=args.max_events)
        destination = project_root() / "simulator_runtime" / "sessions" / session_id
        destination.mkdir(parents=True, exist_ok=False)
        (destination / "session.json.gz").write_bytes(gzip.compress(json.dumps(session.browser_payload(), separators=(",", ":")).encode("utf-8"), compresslevel=6))
        (destination / "manifest.json").write_text(json.dumps(session.manifest(), indent=2), encoding="utf-8")
        financial = ExportService(session, destination / "exports").export_financial()
        print(json.dumps({"session_id": session_id, "events": len(session.events), "financial_export": str(financial), "orders_called": 0}, indent=2))
        return 0
    adapter = DatasetAdapter(project_root())
    print(json.dumps(adapter.cases(args.limit), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
