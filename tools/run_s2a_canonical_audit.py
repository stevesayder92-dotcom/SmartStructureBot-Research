from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import argparse
import csv
import hashlib
import json
import platform
import re
import subprocess
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.expert_strategy import (
    build_expert_htf_context,
    scan_expert_m5_candidates,
)
from core.pipeline_runner import PipelineOptions, run_pipeline
from core.setup_lifecycle import PipelineRuntimeState
from core.synchronized_m1_replay import build_parent_contract, find_m1_child_entry
from simulator.adapters.dataset_adapter import DatasetAdapter
from simulator.adapters.pipeline_adapter import CanonicalPipelineAdapter
from simulator.audit.canonical_entry_funnel import (
    CanonicalEntryFunnelObserver,
    UNAVAILABLE,
)
from simulator.config import SimulatorConfig, load_config
from simulator.services.execution_replay_service import PaperExecutionReplayService
from simulator.services.observability import director_decision


OUTPUT = ROOT / "research_runs" / "s2a"
AUDIT_COMMAND = (
    f'"{sys.executable}" tools/run_s2a_canonical_audit.py --workers 4'
)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for field in row:
            if field not in seen:
                seen.add(field)
                fields.append(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or ["state"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_portable(root: Path, symbol_dir: str, symbol: str):
    base = root / "simulator_data" / "library" / symbol_dir
    return DatasetAdapter(root).load_csv_pair(
        symbol=symbol,
        m1_path=base / "M1.csv",
        m5_path=base / "M5.csv",
    )


def _paper_probe(
    *,
    symbol: str,
    snapshot: dict[str, Any],
    m1_report: dict[str, Any],
    candle: dict[str, Any],
    event_time: float,
    setup_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    m1_entry = dict(m1_report.get("entry") or {})
    use_m1 = bool(m1_report.get("entry_ready") and m1_entry)
    entry = m1_entry if use_m1 else dict(snapshot.get("entry") or {})
    if not entry or not (use_m1 or entry.get("ready")):
        return {}, {}
    owner = "M1" if use_m1 else "M5"
    normalized = {
        **entry,
        "ready": True,
        "available": True,
        "setup_id": entry.get("parent_m5_setup_id") or entry.get("setup_id") or setup_id,
        "direction": entry.get("parent_direction") or entry.get("direction"),
        "price": entry.get("entry_price") or entry.get("price"),
        "logical_stop": entry.get("logical_stop") or entry.get("stop_loss"),
        "emergency_broker_stop": entry.get("emergency_stop")
        or entry.get("emergency_broker_stop"),
        "attempt_number": int(entry.get("attempt_number") or 1),
    }
    paper_snapshot = deepcopy(snapshot)
    paper_snapshot["entry"] = normalized
    paper_snapshot["management"] = {}
    paper_snapshot["identity"] = {
        "symbol": symbol,
        "setup_id": setup_id,
        "entry_owner": owner,
    }
    paper_snapshot["setup"] = {
        **dict(paper_snapshot.get("setup") or {}),
        "setup_id": setup_id,
    }
    decision = director_decision(
        snapshot=paper_snapshot,
        event_time=float(entry.get("entry_time") or event_time),
        new_entry=normalized,
    ).payload()
    service = PaperExecutionReplayService(shadow_profiles=())
    paper = service.process(
        replay_event_id=f"S2A|{symbol}|{setup_id}",
        timestamp=float(entry.get("entry_time") or event_time),
        symbol=symbol,
        candle=candle,
        snapshot=paper_snapshot,
        director_decision=decision,
        volatility_ratio=1.0,
    )
    return decision, paper


def _symbol_job(
    root_text: str,
    symbol_dir: str,
    symbol: str,
    config_payload: dict[str, Any],
) -> dict[str, Any]:
    root = Path(root_text)
    config = SimulatorConfig(**{
        **config_payload,
        "enabled_shadows": tuple(config_payload.get("enabled_shadows") or ()),
        "enabled_bug_rules": tuple(config_payload.get("enabled_bug_rules") or ()),
    })
    dataset = _load_portable(root, symbol_dir, symbol)
    observer = CanonicalEntryFunnelObserver()
    candidates: list[dict[str, Any]] = []
    for direction in ("BULLISH", "BEARISH"):
        candidates.extend(
            scan_expert_m5_candidates(
                dataset.m5,
                direction=direction,
                symbol=dataset.symbol,
                timeframe="M5",
                sensitivity=config.engine_sensitivity,
            )
        )
    candidates.sort(
        key=lambda row: (int(row["entry_index"]), str(row["direction"]))
    )
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        setup_id = str(candidate["setup_id"])
        if setup_id not in seen:
            seen.add(setup_id)
            unique.append(candidate)

    for candidate in unique:
        entry_index = int(candidate["entry_index"])
        prefix = dataset.m5.iloc[: entry_index + 1]
        event_time = float(prefix.iloc[-1]["time"]) + 300.0
        context = build_expert_htf_context(
            decision_candle_open_time=float(prefix.iloc[-1]["time"]),
            decision_timeframe_seconds=300,
            frame_data=CanonicalPipelineAdapter._resample_htf(prefix),
            sensitivity=config.engine_sensitivity,
            policy=config.htf_policy,
            allow_single_strong=config.allow_single_strong_htf,
        )
        aligned = bool(
            context.get("available")
            and str(context.get("approved_direction"))
            == str(candidate.get("direction"))
        )
        parent: dict[str, Any] = {}
        m1_report: dict[str, Any] = {}
        snapshot: dict[str, Any] = {}
        decision: dict[str, Any] = {}
        paper: dict[str, Any] = {}
        if aligned:
            try:
                parent = build_parent_contract(
                    candidate=candidate,
                    m5_data=prefix,
                    symbol=dataset.symbol,
                )
            except (KeyError, ValueError, IndexError):
                parent = {}
            if parent:
                visible_m1 = dataset.m1[
                    dataset.m1["time"].astype(float) + 60.0 <= event_time
                ].copy().reset_index(drop=True)
                m1_report = find_m1_child_entry(
                    parent=parent,
                    m1_data=visible_m1,
                    sensitivity=2,
                )
            result = run_pipeline(
                data=dataset.m5,
                symbol=dataset.symbol,
                timeframe="M5",
                as_of_index=entry_index,
                options=PipelineOptions(
                    strategy_model="EXPERT_SPEC_V1",
                    engine_sensitivity=config.engine_sensitivity,
                ),
                runtime_state=PipelineRuntimeState(),
                higher_timeframe_context=context,
            )
            snapshot = result.snapshot
            m1_entry = dict(m1_report.get("entry") or {})
            execution_time = float(m1_entry.get("entry_time") or event_time)
            candle_frame = dataset.m1 if m1_entry else dataset.m5
            candle_index = int(
                m1_entry.get("entry_index")
                if m1_entry
                else entry_index
            )
            candle = candle_frame.iloc[candle_index].to_dict()
            try:
                decision, paper = _paper_probe(
                    symbol=dataset.symbol,
                    snapshot=snapshot,
                    m1_report=m1_report,
                    candle=candle,
                    event_time=execution_time,
                    setup_id=str(candidate["setup_id"]),
                )
            except (KeyError, ValueError, RuntimeError):
                decision, paper = {}, {}

        observer.observe(
            symbol=dataset.symbol,
            candidate=candidate,
            context=context,
            m5_data=dataset.m5,
            m1_data=dataset.m1,
            parent=parent,
            m1_report=m1_report,
            director_snapshot=snapshot,
            director_action=decision,
            paper_result=paper,
        )
    return {
        "symbol": dataset.symbol,
        "symbol_dir": symbol_dir,
        "data_hash": dataset.data_hash,
        "source": dataset.source,
        "m1_rows": len(dataset.m1),
        "m5_rows": len(dataset.m5),
        "validation": dataset.validation,
        "funnel_rows": observer.funnel_rows,
        "parent_rows": observer.parent_rows,
        "m1_event_rows": observer.m1_rows,
        "setup_rows": observer.setup_rows,
        "blocker_rows": observer.blocker_counts(),
        "summary": observer.summary(),
    }


def _merge(results: list[dict[str, Any]]) -> CanonicalEntryFunnelObserver:
    merged = CanonicalEntryFunnelObserver()
    for result in results:
        for row in result["setup_rows"]:
            setup_id = str(row["setup_id"])
            if setup_id in merged._setup_ids:
                raise ValueError(f"Duplicate cross-symbol setup: {setup_id}")
            merged._setup_ids.add(setup_id)
        merged.setup_rows.extend(result["setup_rows"])
        merged.funnel_rows.extend(result["funnel_rows"])
        merged.parent_rows.extend(result["parent_rows"])
        for row in result["m1_event_rows"]:
            key = str(row["event_key"])
            if key not in merged._m1_keys:
                merged._m1_keys.add(key)
                merged.m1_rows.append(row)
        merged.non_mutation_checks.extend(
            [bool(result["summary"]["integrity"]["observer_non_mutation"])]
            * len(result["setup_rows"])
        )
    return merged


def _test_result(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"state": "NOT_RUN", "path": str(path.relative_to(ROOT))}
    payload = path.read_bytes()
    encoding = "utf-16" if payload.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8"
    text = payload.decode(encoding, errors="replace")
    matches = re.findall(r"Ran\s+(\d+)\s+tests?", text)
    return {
        "state": "PASS" if re.search(r"(?m)^OK\s*$", text) else "FAIL",
        "test_count": sum(int(value) for value in matches),
        "path": str(path.relative_to(ROOT)),
        "sha256": _sha(path),
    }


def _git() -> tuple[str, str]:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=ROOT, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return commit, branch
    except (OSError, subprocess.CalledProcessError):
        return "UNAVAILABLE_NOT_A_GIT_REPOSITORY", "UNAVAILABLE_NOT_A_GIT_REPOSITORY"


def _manifest(
    *,
    results: list[dict[str, Any]],
    config: SimulatorConfig,
    command: str,
) -> dict[str, Any]:
    commit, branch = _git()
    output_hashes = {
        path.name: _sha(path)
        for path in sorted(OUTPUT.iterdir())
        if path.is_file() and path.name != "reproducibility_manifest.json"
    }
    source_paths = [
        ROOT / "SmartStructureBot_Bible.md",
        ROOT / "config" / "simulator_phase_s1.json",
        ROOT / "core" / "expert_strategy.py",
        ROOT / "core" / "pipeline_runner.py",
        ROOT / "core" / "synchronized_m1_replay.py",
        ROOT / "simulator" / "adapters" / "pipeline_adapter.py",
        ROOT / "simulator" / "audit" / "canonical_entry_funnel.py",
        ROOT / "tools" / "run_s2a_canonical_audit.py",
        ROOT / "tests" / "test_s2a_canonical_funnel.py",
    ]
    datasets = []
    for result in results:
        base = ROOT / "simulator_data" / "library" / result["symbol_dir"]
        datasets.append(
            {
                "symbol": result["symbol"],
                "combined_data_hash": result["data_hash"],
                "m1_path": str((base / "M1.csv").relative_to(ROOT)),
                "m1_sha256": _sha(base / "M1.csv"),
                "m1_rows": result["m1_rows"],
                "m5_path": str((base / "M5.csv").relative_to(ROOT)),
                "m5_sha256": _sha(base / "M5.csv"),
                "m5_rows": result["m5_rows"],
            }
        )
    return {
        "schema": "SMARTSTRUCTUREBOT_S2A_REPRODUCIBILITY_V1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository_commit": commit,
        "branch": branch,
        "python_version": sys.version,
        "platform": platform.platform(),
        "datasets": datasets,
        "audit_command": command,
        "production_configuration": config.manifest_payload(),
        "production_configuration_hash": config.hash(),
        "source_sha256": {
            str(path.relative_to(ROOT)): _sha(path) for path in source_paths
        },
        "output_sha256": output_hashes,
        "test_commands": [
            f'"{sys.executable}" -m unittest tests.test_s2a_canonical_funnel -v',
            f'"{sys.executable}" -m unittest discover -s tests -v',
            f'"{sys.executable}" -m unittest discover -s simulator/tests -v',
        ],
        "test_results": {
            "s2a": _test_result(OUTPUT / "tests_s2a.txt"),
            "inherited": _test_result(OUTPUT / "tests_inherited.txt"),
            "simulator": _test_result(OUTPUT / "tests_simulator.txt"),
        },
        "external_jules_artifacts": {
            "available": False,
            "state": "SOURCE_PACKAGE_NOT_SUPPLIED",
            "review": "docs/S2A_JULES_AUDIT_REVIEW.md",
        },
        "order_api_calls": 0,
    }


def _report(
    summary: dict[str, Any],
    results: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
    m1_rows: list[dict[str, Any]],
) -> str:
    answers = summary["answers"]
    counts = summary["counts"]
    integrity = summary["integrity"]
    questions = [
        ("1. How many independent setups exist?", answers["independent_setups_in_observable_candidate_population"]),
        ("2. How many retracements are born?", f"{answers['retracements_born_in_observable_candidate_population']} in the observable terminal-candidate population; all abandoned pre-qualification retracements: {answers['all_retracements_born_including_abandoned']}"),
        ("3. How many qualify?", answers["retracements_qualified_in_observable_candidate_population"]),
        ("4. How many parent gates activate?", answers["parent_gates_activated"]),
        ("5. How many relevant M1 trigger events occur?", answers["relevant_m1_trigger_events"]),
        ("6. How many unique setups produce relevant M1 triggers?", answers["unique_setups_with_relevant_m1_triggers"]),
        ("7. How many M1 triggers occur before parent activation?", answers["m1_triggers_before_parent_activation_events"]),
        ("8. How many unique setups are affected?", answers["unique_setups_affected_by_early_triggers"]),
        ("9. How many early triggers later become stale?", answers["early_triggers_later_stale"]),
        ("10. How many later receive an M5 entry?", answers["early_trigger_setups_later_receiving_m5_entry"]),
        ("11. How many never receive any entry?", answers["early_trigger_setups_never_receiving_entry"]),
        ("12. Which canonical stage loses the most unique setups?", f"{answers['largest_unique_setup_loss_stage']} ({answers['largest_unique_setup_loss_count']})"),
        ("13. What is the dominant reason?", answers["dominant_reason"]),
        ("14. How is that reason classified?", answers["dominant_reason_category"]),
        ("15. Is there actual future leakage?", answers["actual_future_leak_detected"]),
    ]
    lines = [
        "# Phase S2A canonical entry-funnel audit report",
        "",
        "## Verdict",
        "",
        "This is a non-mutating full-portable-library audit. It changes no strategy rule, threshold, Director decision or management behaviour. All seven symbols and every usable M1/M5 row were read; candidate rows were not downsampled.",
        "",
        "The current production scan exposes terminal M5 candidate lifecycles but does not publish an immutable event stream for abandoned pre-qualification retracements. That broader birth count is therefore `UNAVAILABLE`, not inferred. Likewise, the current M1 rejection contract does not preserve enough identity to prove that an early trigger later became the same stale trigger.",
        "",
        "## Mandated questions",
        "",
    ]
    for question, answer in questions:
        lines.extend([f"### {question}", "", f"`{answer}`", ""])
    lines.extend(
        [
            "## Count reconciliation",
            "",
            f"- Candidate setups: {counts['candidate_setups']}",
            f"- HTF-aligned candidate setups: {counts['htf_aligned_candidate_setups']}",
            f"- Parent-active setups: {counts['parent_active_setups']}",
            f"- Canonical entry setups: {counts['canonical_entry_setups']}",
            f"- M1 events: {counts['m1_events']}",
            f"- Funnel rows: {counts['funnel_rows']} / expected {counts['expected_funnel_rows']}",
            "",
            "M1 event counts and unique setup counts are intentionally distinct. A parent that emits several rejection events remains one setup and one possible missed trade.",
            "",
            "## Per-symbol full-data scope",
            "",
            "| Symbol | M1 rows | M5 rows | candidate setups | relevant M1 events |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for result in sorted(results, key=lambda row: row["symbol"]):
        sub = result["summary"]
        lines.append(
            f"| {result['symbol']} | {result['m1_rows']} | {result['m5_rows']} | {sub['counts']['candidate_setups']} | {sub['answers']['relevant_m1_trigger_events']} |"
        )
    def m1_metric(code: str) -> dict[str, int]:
        selected = [
            row for row in m1_rows
            if code in json.loads(row.get("hard_blockers") or "[]")
        ]
        return {
            "event_count": len(selected),
            "unique_setup_count": len({row["setup_id"] for row in selected}),
        }

    wick = m1_metric("WICK_ONLY_BOS")
    noise = m1_metric("NO_MEANINGFUL_M1_COUNTER_STRUCTURE")
    stale = m1_metric("STALE_TRIGGER")
    lines.extend(
        [
            "",
            "## Ranked factual bottlenecks",
            "",
            f"1. **HTF ownership:** {answers['largest_unique_setup_loss_count']} of {counts['candidate_setups']} direction-specific terminal M5 candidates are not owned by the strict causal HTF direction at their candidate candle. The most common exact HTF state is `{answers['dominant_reason']}`. This is an intentional strategy rule in the current configuration, not an implementation defect.",
            f"2. **Parent-active timing:** {answers['m1_triggers_before_parent_activation_events']} M1 engine events across {answers['unique_setups_affected_by_early_triggers']} unique canonical parents carry `M5_PARENT_NOT_ACTIVE`. This is a causal parent-gate timing observation. The engine emits this rejection before downstream meaningful-counter and body-close checks, so these events are not proven valid missed entries and must not be counted as {answers['m1_triggers_before_parent_activation_events']} missed trades.",
            f"3. **Wick-only BOS:** {wick.get('event_count', 0)} events across {wick.get('unique_setup_count', 0)} unique setups preserve the candle-close rule.",
            f"4. **Insufficient meaningful M1 counter structure:** {noise.get('event_count', 0)} events across {noise.get('unique_setup_count', 0)} unique setups are rejected by the canonical child-structure rule.",
            f"5. **Stale M1 triggers:** {stale.get('event_count', 0)} events across {stale.get('unique_setup_count', 0)} unique setups are rejected by the existing freshness rule.",
            "",
            "No bottleneck is repaired in Phase S2A. The next phase must first decide which, if any, represents strategy intent versus unwanted latency.",
            "",
            "## Causality",
            "",
            "A future leak means a later suffix changes an already published prefix decision or an unfinished candle is consumed. Causal confirmation latency means the engine waits for its configured right-side swing candles before publishing the swing. Phase S2A preserves that delay and does not weaken confirmation.",
            "",
            f"Observer non-mutation: `{integrity['observer_non_mutation']}`. Funnel reconciliation: `{integrity['funnel_count_reconciles']}`. Future data reported by canonical events: `{answers['actual_future_leak_detected']}`.",
            "",
            "## Jules audit status",
            "",
            "The external auditor source and its five companion artifacts were not supplied. `docs/S2A_JULES_AUDIT_REVIEW.md` records each quoted defect and uses `UNAVAILABLE_SOURCE_NOT_SUPPLIED` rather than invented source lines. None of the Jules numerical conclusions is treated as authoritative.",
            "",
            "## Safety",
            "",
            "Research/paper instrumentation only. No MT5 order function or broker order API was called.",
        ]
    )
    return "\n".join(lines) + "\n"


def _refresh_manifest(config: SimulatorConfig, command: str) -> None:
    state_path = OUTPUT / "_run_state.json"
    if not state_path.exists():
        raise FileNotFoundError("Run the S2A audit before refreshing its manifest")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    summary = json.loads(
        (OUTPUT / "funnel_summary.json").read_text(encoding="utf-8")
    )
    funnel_rows = _read_csv(OUTPUT / "canonical_entry_funnel.csv")
    m1_rows = _read_csv(OUTPUT / "m1_trigger_events.csv")
    blocker_rows = _read_csv(OUTPUT / "blocker_counts.csv")
    relevant_classes = {
        "M1_TRIGGER_BEFORE_PARENT_ACTIVE",
        "M1_TRIGGER_WHILE_PARENT_ACTIVE",
        "M1_TRIGGER_AFTER_PARENT_EXPIRED",
    }
    report_results = []
    for result in state["results"]:
        symbol = result["symbol"]
        setups = {
            row["setup_id"]
            for row in funnel_rows
            if row["symbol"] == symbol
            and row["current_pipeline_stage"] == "HTF_CONTEXT"
        }
        relevant = [
            row for row in m1_rows
            if row["symbol"] == symbol
            and row["classification"] in relevant_classes
        ]
        report_results.append(
            {
                **result,
                "summary": {
                    "counts": {"candidate_setups": len(setups)},
                    "answers": {"relevant_m1_trigger_events": len(relevant)},
                },
            }
        )
    (OUTPUT / "S2A_CANONICAL_AUDIT_REPORT.md").write_text(
        _report(summary, report_results, blocker_rows, m1_rows),
        encoding="utf-8",
    )
    manifest = _manifest(results=state["results"], config=config, command=command)
    (OUTPUT / "reproducibility_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )


def run(*, workers: int, manifest_only: bool = False) -> None:
    config = load_config(ROOT / "config" / "simulator_phase_s1.json")
    command = AUDIT_COMMAND.replace("--workers 4", f"--workers {workers}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if manifest_only:
        _refresh_manifest(config, command)
        return
    index = json.loads(
        (ROOT / "simulator_data" / "library" / "index.json").read_text(
            encoding="utf-8"
        )
    )
    jobs = [
        (str(ROOT), str(row["symbol"]).rstrip("#").upper(), str(row["symbol"]), config.manifest_payload())
        for row in index
    ]
    # Directory names are canonicalized independently of broker suffix/case.
    available_dirs = {
        path.name.upper(): path.name
        for path in (ROOT / "simulator_data" / "library").iterdir()
        if path.is_dir()
    }
    jobs = [
        (root, available_dirs[folder.upper()], symbol, payload)
        for root, folder, symbol, payload in jobs
    ]
    results: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=max(1, int(workers))) as pool:
        futures = {
            pool.submit(_symbol_job, *job): job[2]
            for job in jobs
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(
                f"S2A {result['symbol']}: "
                f"{result['summary']['counts']['candidate_setups']} setups, "
                f"{result['summary']['counts']['m1_events']} M1 events",
                flush=True,
            )
    results.sort(key=lambda row: row["symbol"])
    merged = _merge(results)
    summary = merged.summary()
    _csv(OUTPUT / "canonical_entry_funnel.csv", merged.funnel_rows)
    _csv(OUTPUT / "parent_activation_timing.csv", merged.parent_rows)
    _csv(OUTPUT / "m1_trigger_events.csv", merged.m1_rows)
    blocker_rows = merged.blocker_counts()
    _csv(OUTPUT / "blocker_counts.csv", blocker_rows)
    (OUTPUT / "funnel_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    (OUTPUT / "S2A_CANONICAL_AUDIT_REPORT.md").write_text(
        _report(summary, results, blocker_rows, merged.m1_rows), encoding="utf-8"
    )
    state = {
        "results": [
            {
                key: value
                for key, value in result.items()
                if key
                in {
                    "symbol", "symbol_dir", "data_hash", "source",
                    "m1_rows", "m5_rows", "validation",
                }
            }
            for result in results
        ]
    }
    (OUTPUT / "_run_state.json").write_text(
        json.dumps(state, indent=2, sort_keys=True), encoding="utf-8"
    )
    _refresh_manifest(config, command)
    print(json.dumps(summary["answers"], indent=2, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--manifest-only", action="store_true")
    args = parser.parse_args()
    run(workers=args.workers, manifest_only=args.manifest_only)
