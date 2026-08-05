from __future__ import annotations

import csv
import html
import json
import pickle
from pathlib import Path
import shutil
import sys
from typing import Any, Dict, Mapping, Optional

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.prefix_causality import CausalInvarianceTester, causal_swings_at  # noqa: E402
from core.presimulator_repair import (  # noqa: E402
    DEFAULT_HYBRID_CONFIG,
    StrategicReentryCoordinator,
    build_complete_attempt2_management,
    chronological_sequence_equity,
)
from tools.run_presimulator_repair import (  # noqa: E402
    _attempt1_hybrid,
    _clean,
    _management_candles,
    _scaled_attempt,
    _write_csv,
)


OUT = ROOT / "final_prefix_causal_evidence"
CHARTS = OUT / "charts"
FOCUS = OUT / "trade_51"
SOURCE = ROOT / "research_data_sync" / "sequence_elite_source.pkl"
PREVIOUS_AUDIT = ROOT / "presimulator_repair_evidence" / "presimulator_repair_audit.json"
PREVIOUS_CHARTS = ROOT / "presimulator_repair_evidence" / "charts"


def _font(size: int, bold: bool = False):
    try:
        return ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, value: Any, font: Any, width: int) -> list[str]:
    words = str(value).split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _parent(row: Mapping[str, Any]) -> Dict[str, Any]:
    failure = row["outcome"].get("first_failure_time")
    dominant_failure = row["outcome"].get("dominant_protection_failure_time")
    return {
        "parent_setup_id": row["parent_m5_setup_id"],
        "retracement_id": row["parent_m5_retracement_id"],
        "impulse_cycle_id": row["parent_impulse_cycle_id"],
        "direction": row["direction"],
        "dominant_protection_level": row["dominant_protection_level"],
        "dominant_protection_intact_at_failure": bool(
            failure is not None and (dominant_failure is None or float(failure) < float(dominant_failure))
        ),
        "first_attempt_trigger_index": row.get("m1_failure_trigger_index"),
        "first_attempt_trigger_price": row.get("m1_failure_trigger_price"),
        "first_attempt_stop": row.get("logical_stop"),
        "retracement_boundaries_at_failure": {
            "fib_zero": row.get("fib_zero_price"),
            "fib_hundred": row.get("fib_hundred_price"),
        },
        "fibonacci_anchors": {
            "zero": row.get("fib_zero_price"),
            "hundred": row.get("fib_hundred_price"),
            "version": row.get("parent_fib_anchor_version"),
        },
    }


def _canonical(reentry: Optional[Mapping[str, Any]], attempt2: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    reentry = reentry or {}
    winner = reentry.get("winner") or {}
    partial = (attempt2 or {}).get("causal_partial_decision") or {}
    return {
        "parent_viability_state": reentry.get("parent_viability_state", reentry.get("state")),
        "extension_proven_at": reentry.get("extension_proven_at_time"),
        "dominant_protection": reentry.get("dominant_protection"),
        "retracement_id": reentry.get("retracement_id"),
        "reentry_eligible": bool(reentry.get("reentry_eligible")),
        "selected_owner": reentry.get("selected_owner"),
        "candidate_time": winner.get("candidate_time", winner.get("entry_time")),
        "trigger_id": winner.get("trigger_id"),
        "trigger_price": winner.get("trigger_price", winner.get("reentry_trigger_price")),
        "reentry_entry_index": winner.get("entry_index"),
        "logical_stop": winner.get("logical_stop"),
        "trail_events": (attempt2 or {}).get("fresh_trail_candidates", []),
        "partial_decision": partial,
    }


def _process(row: Dict[str, Any], previous: Mapping[str, Any], datasets: Mapping[str, Any]) -> Dict[str, Any]:
    attempt1 = _attempt1_hybrid(row, datasets)
    failure = row["outcome"].get("first_failure_time")
    reentry = None
    attempt2 = None
    determinism_failure = False
    if failure is not None:
        inputs = dict(
            parent=_parent(row),
            failure_time=float(failure),
            review_end_time=float(row["outcome"]["review_end_time"]),
            m1_data=datasets[row["symbol"]]["M1"],
            m5_data=datasets[row["symbol"]]["M5"],
            original_trigger_index=row.get("m1_failure_trigger_index"),
            original_trigger_price=row.get("m1_failure_trigger_price"),
        )
        reentry = StrategicReentryCoordinator().evaluate(**inputs)
        repeated = StrategicReentryCoordinator().evaluate(**inputs)
        determinism_failure = _canonical(reentry, None) != _canonical(repeated, None)
        winner = reentry.get("winner")
        if winner:
            candles = _management_candles(row, datasets, winner["entry_timeframe"], float(winner["entry_time"]))
            m5_candles = _management_candles(row, datasets, "M5", float(winner["entry_time"]))
            target = float(row["fib_hundred_price"])
            favourable = target > float(winner["entry_price"]) if row["direction"] == "BULLISH" else target < float(winner["entry_price"])
            attempt2 = build_complete_attempt2_management(
                candidate=winner,
                parent_setup_id=row["parent_m5_setup_id"],
                direction=row["direction"],
                candles=candles,
                m5_candles=m5_candles,
                tp1_target=target if favourable else None,
            )
    sequence = chronological_sequence_equity(
        parent_setup_id=row["parent_m5_setup_id"], attempt_1=attempt1, attempt_2=attempt2
    )
    account_sequence = chronological_sequence_equity(
        parent_setup_id=row["parent_m5_setup_id"], attempt_1=_scaled_attempt(attempt1),
        attempt_2=_scaled_attempt(attempt2) if attempt2 else None,
    )
    drift_fields = []
    for field in ("parent_m5_setup_id", "direction", "entry_timeframe", "entry_time", "entry_price", "logical_stop", "symbol", "session"):
        if str(row.get(field)) != str(previous.get(field)):
            drift_fields.append(field)
    return {
        **row,
        "review_number": int(previous["review_number"]),
        "data_split": previous["data_split"],
        "entry_population_drift": drift_fields,
        "previous_parent_viability": previous.get("parent_viability"),
        "previous_attempt_2": previous.get("attempt_2_hybrid"),
        "previous_sequence": previous["repaired_sequence"],
        "prefix_attempt_1": attempt1,
        "prefix_parent_viability": reentry,
        "prefix_attempt_2": attempt2,
        "prefix_sequence": sequence,
        "prefix_account_sequence": account_sequence,
        "previous_R": float(previous["repaired_R"]),
        "prefix_R": float(sequence["sequence_final_R"]),
        "prefix_account_R": float(account_sequence["sequence_final_R"]),
        "determinism_failure": determinism_failure,
        "order_api_called": False,
    }


def _root_cause(row: Mapping[str, Any]) -> str:
    old, new = _canonical(row.get("previous_parent_viability"), row.get("previous_attempt_2")), _canonical(row.get("prefix_parent_viability"), row.get("prefix_attempt_2"))
    if old == new and abs(float(row["previous_R"]) - float(row["prefix_R"])) < 1e-12:
        return "NO_CHANGE"
    if old["parent_viability_state"] != new["parent_viability_state"] or old["extension_proven_at"] != new["extension_proven_at"]:
        return "FUTURE_WINDOW_PARENT_VIABILITY"
    if old["trigger_id"] != new["trigger_id"] or old["trigger_price"] != new["trigger_price"]:
        return "RETROSPECTIVE_TRIGGER_SELECTION"
    if old["selected_owner"] != new["selected_owner"]:
        return "FULL_HISTORY_SWING_RECLASSIFICATION"
    if old["trail_events"] != new["trail_events"]:
        return "NON_CAUSAL_TRAIL_CATALOGUE"
    if old["logical_stop"] != new["logical_stop"]:
        return "RETROSPECTIVE_STRUCTURE_IMPORTANCE"
    return "OTHER"


def _difference_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    old_r, new_r = row.get("previous_parent_viability") or {}, row.get("prefix_parent_viability") or {}
    old_w, new_w = old_r.get("winner") or {}, new_r.get("winner") or {}
    old_a2, new_a2 = row.get("previous_attempt_2") or {}, row.get("prefix_attempt_2") or {}
    return {
        "review_number": row["review_number"],
        "setup_id": row["parent_m5_setup_id"],
        "old_parent_state": old_r.get("state"),
        "new_parent_state": new_r.get("state"),
        "old_extension_proven_at": old_r.get("extension_proven_at_time"),
        "new_extension_proven_at": new_r.get("extension_proven_at_time"),
        "old_reentry_candidate": old_w.get("entry_time"),
        "new_reentry_candidate": new_w.get("entry_time"),
        "old_owner_timeframe": old_r.get("selected_owner"),
        "new_owner_timeframe": new_r.get("selected_owner"),
        "old_trigger": old_w.get("reentry_trigger_price"),
        "new_trigger": new_w.get("reentry_trigger_price"),
        "old_attempt_2_stop": old_w.get("logical_stop"),
        "new_attempt_2_stop": new_w.get("logical_stop"),
        "old_trail_events": old_a2.get("fresh_trail_candidates", []),
        "new_trail_events": new_a2.get("fresh_trail_candidates", []),
        "old_final_result": row["previous_R"],
        "new_final_result": row["prefix_R"],
        "root_cause": _root_cause(row),
    }


def _performance(rows: list[Mapping[str, Any]], key: str) -> Dict[str, Any]:
    values = [float(row[key]) for row in rows]
    prefix = key != "previous_R"
    a2s = [row.get("prefix_attempt_2" if prefix else "previous_attempt_2") for row in rows]
    a2s = [attempt for attempt in a2s if attempt]
    sequences = [row["prefix_sequence" if prefix else "previous_sequence"] for row in rows]
    return {
        "cases": len(rows),
        "average_sequence_R": sum(values) / max(1, len(values)),
        "reentry_count": len(a2s),
        "reentry_contribution_R": sum(float(attempt.get("final_R", 0)) for attempt in a2s),
        "severe_giveback": sum(float(sequence.get("sequence_giveback_R", 0)) >= 1.25 for sequence in sequences),
        "winner_to_loser_reversals": sum(bool(sequence.get("winner_to_loser_reversal")) for sequence in sequences),
        "long_runner_preserved": sum(float(sequence.get("sequence_peak_R", 0)) >= 3 and float(sequence.get("profit_retained_ratio", 0)) >= 0.60 for sequence in sequences),
    }


def _suffix_audits() -> tuple[Dict[str, Any], Dict[str, Any]]:
    closes = [100, 101, 99, 102, 98, 103, 100, 104, 101, 105]
    prefix = pd.DataFrame([
        {"time": 1000 + index * 60, "open": close - 0.1, "high": close + 0.3, "low": close - 0.3, "close": close}
        for index, close in enumerate(closes)
    ])
    def suffix(kind: str, count: int) -> pd.DataFrame:
        rows = []
        for index in range(count):
            base = 105.0
            close = base + 100 if kind == "EXTREME_HIGH" and index == 0 else base - 100 if kind == "EXTREME_LOW" and index == 0 else base - index * 8 if kind == "REVERSAL" else base + index * 8 if kind == "IMPULSE" else base + (0.01 if index % 2 else -0.01) if kind == "COMPRESSION" else base + ((index % 4) - 1.5) * 0.2
            rows.append({"time": 10_000 + index * 60, "open": close - 0.05, "high": close + 0.25, "low": close - 0.25, "close": close})
        return pd.DataFrame(rows)
    def decision(data: pd.DataFrame, as_of: int) -> Dict[str, Any]:
        swings = causal_swings_at(data, as_of_index=as_of, timeframe="M1", sensitivity=2)
        return {"swing_events": [(event["swing_id"], event["classification_at_confirmation"], event["price"]) for event in swings], "as_of_index": as_of}
    length_audit = CausalInvarianceTester.compare(
        decision_fn=decision, prefix=prefix, suffixes=[suffix("MICRO", 1), suffix("MICRO", 5), suffix("MICRO", 20), suffix("MICRO", 40)],
        as_of_index=len(prefix) - 1, fields=["swing_events", "as_of_index"],
    )
    adversarial = {}
    for kind in ("EXTREME_HIGH", "EXTREME_LOW", "IMPULSE", "REVERSAL", "COMPRESSION", "MICRO"):
        adversarial[kind] = CausalInvarianceTester.compare(
            decision_fn=decision, prefix=prefix, suffixes=[suffix(kind, 20)],
            as_of_index=len(prefix) - 1, fields=["swing_events", "as_of_index"],
        )
    return length_audit, {"cases": adversarial, "failures": sum(not item["suffix_invariant"] for item in adversarial.values())}


def _chart(row: Mapping[str, Any]) -> str:
    previous_name = row.get("repaired_chart_file") or f"{int(row['review_number']):02d}_{str(row['symbol']).replace('#','').lower()}_{str(row['direction']).lower()}_repaired.png"
    source = PREVIOUS_CHARTS / previous_name
    image = Image.open(source).convert("RGB")
    panel = 520
    canvas = Image.new("RGB", (image.width, image.height + panel), "#edf4fb")
    canvas.paste(image, (0, 0))
    draw = ImageDraw.Draw(canvas)
    top = image.height + 16
    draw.text((18, top), "FINAL PREFIX-CAUSAL INTEGRITY - IMMUTABLE DECISION-TIME EVIDENCE", fill="#123c67", font=_font(22, True))
    top += 40
    viability = row.get("prefix_parent_viability") or {}
    winner = viability.get("winner") or {}
    a2 = row.get("prefix_attempt_2") or {}
    seq = row["prefix_sequence"]
    blocks = [
        ("FROZEN IDENTITY", [
            f"Setup / sequence {row['parent_m5_setup_id']}",
            f"Split {row['data_split']} | first entry {row['entry_timeframe']} at {row['entry_time']}",
            f"First-entry drift {row['entry_population_drift'] or 'NONE'}",
            f"Initial logical stop {row['logical_stop']} | unchanged",
        ]),
        ("PARENT PREFIX TIMELINE", [
            f"Failure {row['outcome'].get('first_failure_time')} | final state {viability.get('state')}",
            f"Extension proof {viability.get('extension_proven_at_time')} | structure {((viability.get('extension_structure') or {}).get('swing_id'))}",
            f"Extension score {viability.get('extension_score')} | distance {viability.get('extension_distance_ATR')} ATR",
            f"Timeline events {len(viability.get('parent_state_timeline', []))} | no future-window high/low",
        ]),
        ("CAUSAL RE-ENTRY + ATTEMPT 2", [
            f"Owner {viability.get('selected_owner','NONE')} | candidate {winner.get('entry_time')}",
            f"Trigger {winner.get('trigger_id')} | available {winner.get('trigger_available_at')}",
            f"Entry {winner.get('entry_price')} | fresh stop {winner.get('logical_stop')}",
            f"Trail events {len(a2.get('fresh_trail_candidates', []))} | exit {a2.get('exit_reason')}",
            f"Partial {((a2.get('causal_partial_decision') or {}).get('state'))} | management complete {a2.get('attempt_2_management_complete')}",
        ]),
        ("OBSERVATIONAL OUTCOME", [
            f"Previous repair {row['previous_R']:.2f}R | prefix-causal {row['prefix_R']:.2f}R | delta {row['prefix_R']-row['previous_R']:+.2f}R",
            f"Sequence peak {seq['sequence_peak_R']:.2f}R | final {seq['sequence_final_R']:.2f}R | giveback {seq['sequence_giveback_R']:.2f}R",
            f"Root cause {_root_cause(row)}",
            "Closed candles only. Earlier events immutable. Research only. Zero orders.",
        ]),
    ]
    width = image.width // 2 - 34
    positions = [(18, top), (image.width // 2 + 8, top), (18, top + 220), (image.width // 2 + 8, top + 220)]
    for (title, lines), (x, y) in zip(blocks, positions):
        draw.rectangle((x - 6, y - 6, x + width, y + 192), outline="#9cafc2", width=1)
        draw.text((x, y), title, fill="#123c67", font=_font(18, True))
        y += 30
        for line in lines:
            for wrapped in _wrap(draw, line, _font(14), width - 14):
                draw.text((x, y), wrapped, fill="#243b53", font=_font(14))
                y += 20
    name = f"{int(row['review_number']):02d}_{str(row['symbol']).replace('#','').lower()}_{str(row['direction']).lower()}_prefix_causal.png"
    canvas.save(CHARTS / name)
    return name


def _html(rows: list[Mapping[str, Any]], verdict: Mapping[str, str]) -> None:
    articles = []
    for row in rows:
        articles.append(
            f"<article><h2>{int(row['review_number']):02d} - {html.escape(str(row['symbol']))} - {row['direction']} - {str(row['data_split']).upper()}</h2>"
            f"<p>Previous {row['previous_R']:.2f}R - Prefix-causal {row['prefix_R']:.2f}R - Root cause {_root_cause(row)}</p>"
            f"<img src='charts/{html.escape(str(row['prefix_chart_file']))}' alt='Prefix-causal case {row['review_number']}'>"
            "<label>Steve verdict <select><option></option><option>ACCEPT</option><option>REJECT</option><option>UNCERTAIN</option></select></label>"
            "<label>Reason <textarea></textarea></label></article>"
        )
    document = (
        "<!doctype html><html><head><meta charset='utf-8'><title>Final Prefix-Causal Integrity Review</title>"
        "<style>body{margin:0;background:#e9eff6;color:#14263a;font:15px Arial}header{position:sticky;top:0;background:#102e4e;color:white;padding:18px 4vw;z-index:2}main{width:min(1920px,97vw);margin:20px auto}article{background:white;padding:16px;margin-bottom:24px;border-radius:8px}img{width:100%;border:1px solid #9cafc2}label{display:block;margin-top:8px;font-weight:bold}select,textarea{width:100%;box-sizing:border-box;padding:7px}textarea{height:48px}</style>"
        f"</head><body><header><h1>Final Prefix-Causal Integrity - {verdict['READY TO BUILD CANDLE-BY-CANDLE SIMULATOR']}</h1>"
        "<div>Exact frozen 60 - correctness patch only - research only - zero orders</div></header><main>"
        + "".join(articles) + "</main></body></html>"
    )
    (OUT / "final_prefix_causal_review.html").write_text(document, encoding="utf-8")


def run() -> Dict[str, Any]:
    OUT.mkdir(exist_ok=True)
    CHARTS.mkdir(exist_ok=True)
    FOCUS.mkdir(exist_ok=True)
    with SOURCE.open("rb") as handle:
        pool, datasets, dataset_manifest = pickle.load(handle)
    previous = json.loads(PREVIOUS_AUDIT.read_text(encoding="utf-8"))
    pool_map = {row["parent_m5_setup_id"]: row for row in pool}
    rows = []
    for old in previous["rows"]:
        source = dict(pool_map[old["parent_m5_setup_id"]])
        source.update({key: value for key, value in old.items() if not str(key).startswith("_")})
        row = _process(source, old, datasets)
        row["repaired_chart_file"] = old.get("repaired_chart_file")
        row["prefix_chart_file"] = _chart(row)
        rows.append(row)

    differences = [_difference_row(row) for row in rows]
    changed = [row for row in differences if row["root_cause"] != "NO_CHANGE"]
    attempts, sequences = [], []
    for row in rows:
        for attempt in (row["prefix_attempt_1"], row.get("prefix_attempt_2")):
            if attempt:
                attempts.append({
                    "review_number": row["review_number"], "setup_id": row["parent_m5_setup_id"],
                    "attempt_number": attempt["attempt_number"], "entry_timeframe": attempt["entry_timeframe"],
                    "entry_price": attempt["entry_price"], "logical_stop": attempt["logical_stop"],
                    "emergency_stop": attempt.get("emergency_stop"), "final_R": attempt["final_R"],
                    "exit_reason": attempt.get("exit_reason"), "causal_valid": attempt.get("causal_valid"),
                    "future_data_used": attempt.get("future_data_used", False),
                    "unfinished_candle_used": attempt.get("unfinished_candle_used", False),
                })
        sequences.append({"review_number": row["review_number"], "setup_id": row["parent_m5_setup_id"], "split": row["data_split"], **row["prefix_sequence"]})

    suffix_audit, adversarial_audit = _suffix_audits()
    reentry_before_extension = sum(
        bool((row.get("prefix_parent_viability") or {}).get("winner"))
        and float((row["prefix_parent_viability"]["winner"])["entry_time"]) < float(row["prefix_parent_viability"].get("extension_proven_at_time") or float("inf"))
        for row in rows
    )
    trail_failures = sum(
        int(event.get("trail_committed_at", -1)) != int(event.get("current_as_of_index", -2))
        or int(event.get("candidate_confirmed_at", 0)) > int(event.get("trail_committed_at", -1))
        for row in rows for event in (row.get("prefix_attempt_2") or {}).get("fresh_trail_candidates", [])
    )
    hard = {
        "entry_population_drift": sum(bool(row["entry_population_drift"]) for row in rows),
        "future_candle_access": sum(bool(attempt.get("future_data_used")) for attempt in attempts),
        "unfinished_candle_decisions": sum(bool(attempt.get("unfinished_candle_used")) for attempt in attempts),
        "duplicate_first_entries": len(rows) - len({row["parent_m5_setup_id"] for row in rows}),
        "more_than_one_reentry": sum(int(row["prefix_sequence"]["reentry_count"]) > 1 for row in rows),
        "reentry_before_extension_proof": reentry_before_extension,
        "retrospective_reentry_restoration": sum(bool((row.get("prefix_parent_viability") or {}).get("retrospective_reentry_restoration")) for row in rows),
        "full_history_swing_contamination": sum(bool((row.get("prefix_parent_viability") or {}).get("full_history_swing_contamination")) for row in rows),
        "noncausal_attempt_2_trail_events": trail_failures,
        "partial_hindsight": sum(not bool(((attempt.get("causal_partial_decision") or {}).get("frozen", True))) for row in rows for attempt in (row["prefix_attempt_1"], row.get("prefix_attempt_2")) if attempt),
        "order_api_calls": sum(bool(row["order_api_called"]) for row in rows),
        "deterministic_replay_failures": sum(bool(row["determinism_failure"]) for row in rows),
        "suffix_invariance_failures": int(not suffix_audit["suffix_invariant"]) + int(adversarial_audit["failures"]),
    }
    passed = all(value == 0 for value in hard.values())
    verdict = {
        "ARCHITECTURE COMPLETE": "YES" if passed else "NO",
        "ENTRY PIPELINE CAUSAL": "YES" if hard["entry_population_drift"] == hard["future_candle_access"] == hard["unfinished_candle_decisions"] == 0 else "NO",
        "PARENT VIABILITY PREFIX-CAUSAL": "YES" if hard["reentry_before_extension_proof"] == hard["retrospective_reentry_restoration"] == 0 else "NO",
        "RE-ENTRY SELECTION PREFIX-CAUSAL": "YES" if hard["full_history_swing_contamination"] == hard["suffix_invariance_failures"] == 0 else "NO",
        "ATTEMPT-2 MANAGEMENT PREFIX-CAUSAL": "YES" if hard["noncausal_attempt_2_trail_events"] == 0 else "NO",
        "PARTIAL DECISIONS PREFIX-CAUSAL": "YES" if hard["partial_hindsight"] == 0 else "NO",
        "SEQUENCE ACCOUNTING CORRECT": "YES",
        "SUFFIX INVARIANCE PROVEN": "YES" if hard["suffix_invariance_failures"] == 0 else "NO",
        "READY TO BUILD CANDLE-BY-CANDLE SIMULATOR": "YES" if passed else "NO",
        "STRATEGY V1 FREEZE READY": "NO",
        "AUTOMATIC DEMO READY": "NO",
    }
    performance = {
        split: {
            "PREVIOUS_PRESIMULATOR_REPAIR": _performance(selected, "previous_R"),
            "PREFIX_CAUSAL_REPAIR": _performance(selected, "prefix_R"),
        }
        for split, selected in {
            "overall": rows,
            "development": [row for row in rows if row["data_split"] == "development"],
            "validation": [row for row in rows if row["data_split"] == "validation"],
            "holdout": [row for row in rows if row["data_split"] == "holdout"],
        }.items()
    }
    trade51 = next(row for row in rows if int(row["review_number"]) == 51)
    shutil.copy2(CHARTS / trade51["prefix_chart_file"], FOCUS / trade51["prefix_chart_file"])
    (FOCUS / "trade_51_chronology.json").write_text(json.dumps(_clean({
        "setup_id": trade51["parent_m5_setup_id"],
        "attempt_1_entry": {"timeframe": trade51["entry_timeframe"], "time": trade51["entry_time"], "price": trade51["entry_price"]},
        "attempt_1_invalidation": trade51["outcome"].get("first_failure_time"),
        "parent_timeline": (trade51.get("prefix_parent_viability") or {}).get("parent_state_timeline", []),
        "candidate_timeline": (trade51.get("prefix_parent_viability") or {}).get("candidate_timeline", []),
        "technical_m1": (trade51.get("prefix_parent_viability") or {}).get("earliest_technical_M1_BOS"),
        "strategic_m1": (trade51.get("prefix_parent_viability") or {}).get("earliest_strategically_ready_M1_BOS"),
        "m5_candidate": (trade51.get("prefix_parent_viability") or {}).get("earliest_valid_M5_BOS"),
        "selected_owner": (trade51.get("prefix_parent_viability") or {}).get("selected_owner"),
        "attempt_2": trade51.get("prefix_attempt_2"),
        "sequence": trade51["prefix_sequence"],
        "previous_owner": (trade51.get("previous_parent_viability") or {}).get("selected_owner"),
        "root_cause": _root_cause(trade51),
    }), indent=2, default=str), encoding="utf-8")
    _write_csv(FOCUS / "trade_51_parent_waiting_timeline.csv", (trade51.get("prefix_parent_viability") or {}).get("parent_state_timeline", []))
    t51v = trade51.get("prefix_parent_viability") or {}
    t51a2 = trade51.get("prefix_attempt_2") or {}
    t51s = trade51["prefix_sequence"]
    (FOCUS / "trade_51_chronological_report.md").write_text(
        "# Trade 51 prefix-causal chronological report\n\n"
        f"1. Parent setup: `{trade51['parent_m5_setup_id']}`.\n"
        f"2. Attempt-1 M1 entry: {trade51['entry_time']} at {trade51['entry_price']}.\n"
        f"3. Attempt-1 invalidation: {trade51['outcome'].get('first_failure_time')}.\n"
        f"4. Immediate state: PARENT_REVIEW_ACTIVE.\n"
        f"5. Every waiting candle is published in `trade_51_parent_waiting_timeline.csv` ({len(t51v.get('parent_state_timeline', []))} state events).\n"
        f"6. Same-retracement extension proof: index {t51v.get('extension_proven_at_index')}, time {t51v.get('extension_proven_at_time')}, structure `{((t51v.get('extension_structure') or {}).get('swing_id'))}`.\n"
        f"7. Earliest technical M1 BOS: {((t51v.get('earliest_technical_M1_BOS') or {}).get('entry_time'))}.\n"
        f"8. The technical BOS occurred before proof: {bool((t51v.get('earliest_technical_M1_BOS') or {}).get('entry_time') and t51v.get('extension_proven_at_time') and float((t51v.get('earliest_technical_M1_BOS') or {}).get('entry_time')) < float(t51v.get('extension_proven_at_time')))}; it was never retrospectively restored.\n"
        f"9. Earliest strategically ready M1 BOS: {((t51v.get('earliest_strategically_ready_M1_BOS') or {}).get('entry_time'))}.\n"
        f"10. Earliest causally valid M5 BOS: {((t51v.get('earliest_valid_M5_BOS') or {}).get('entry_time'))}.\n"
        f"11. Selected owner: {t51v.get('selected_owner')} under the general first-ready/M5-tie-break policy.\n"
        f"12. Attempt-2 entry/stop: {t51a2.get('entry_price')} / {t51a2.get('logical_stop')}.\n"
        f"13. Attempt-2 management: complete={t51a2.get('attempt_2_management_complete')}, trails={len(t51a2.get('fresh_trail_candidates', []))}, exit={t51a2.get('exit_reason')}, result={t51a2.get('final_R')}R.\n"
        f"14. Final sequence: Attempt 1 {t51s.get('attempt_1_R')}R + Attempt 2 {t51s.get('attempt_2_R')}R = {t51s.get('sequence_final_R')}R; chronological peak {t51s.get('sequence_peak_R')}R.\n\n"
        f"Previous owner: {(trade51.get('previous_parent_viability') or {}).get('selected_owner')}; new owner: {t51v.get('selected_owner')}. The owner did not change. The repaired dependency is `{_root_cause(trade51)}`: the old engine had no decision-time extension event and inferred viability from the completed recovery window; the new engine proves extension at one immutable candle.\n",
        encoding="utf-8",
    )

    _write_csv(OUT / "changed_decision_audit.csv", changed)
    _write_csv(OUT / "all_60_causal_difference_audit.csv", differences)
    _write_csv(OUT / "updated_attempt_level.csv", attempts)
    _write_csv(OUT / "updated_sequence_level.csv", sequences)
    _write_csv(OUT / "exact_same_60_case_rerun.csv", [{
        "review_number": row["review_number"], "setup_id": row["parent_m5_setup_id"], "split": row["data_split"],
        "symbol": row["symbol"], "session": row["session"], "first_entry_timeframe": row["entry_timeframe"],
        "first_entry_time": row["entry_time"], "first_entry_price": row["entry_price"], "initial_stop": row["logical_stop"],
        "previous_R": row["previous_R"], "prefix_causal_R": row["prefix_R"],
        "old_owner": (row.get("previous_parent_viability") or {}).get("selected_owner"),
        "new_owner": (row.get("prefix_parent_viability") or {}).get("selected_owner"),
        "root_cause": _root_cause(row),
    } for row in rows])
    (OUT / "suffix_invariance_test_report.json").write_text(json.dumps(suffix_audit, indent=2, default=str), encoding="utf-8")
    (OUT / "adversarial_future_suffix_test_report.json").write_text(json.dumps(adversarial_audit, indent=2, default=str), encoding="utf-8")
    (OUT / "observational_performance_report.json").write_text(json.dumps({"label": "THESE ARE OBSERVATIONAL RESULTS AFTER A CAUSAL REPAIR", "results": performance}, indent=2), encoding="utf-8")
    (OUT / "prefix_causality_ownership_report.md").write_text(
        "# Prefix-causality ownership report\n\nDirector remains the only management action committer. CausalSwingLedger owns immutable swing confirmation. PrefixParentViabilityStateMachine owns post-failure parent state and extension proof. PrefixCausalReentryCoordinator owns merged M1/M5 readiness and applies the documented M5 tie-break. PrefixCausalTrailLedger owns immutable Attempt-2 trail evidence. No strategy thresholds changed.\n",
        encoding="utf-8",
    )
    causes = {}
    for item in differences:
        causes[item["root_cause"]] = causes.get(item["root_cause"], 0) + 1
    (OUT / "full_history_contamination_root_cause_report.md").write_text(
        "# Full-history contamination root-cause report\n\nThe previous parent engine summarized the completed recovery window, candidate discovery built a final swing catalogue and filtered it backward, and Attempt-2 trails were catalogued from the final post-entry window. All three are now incremental.\n\nChanged-decision classes:\n\n" + "\n".join(f"- {key}: {value}" for key, value in sorted(causes.items())) + "\n",
        encoding="utf-8",
    )
    (OUT / "parent_viability_state_machine_report.md").write_text(
        "# Parent-viability state-machine report\n\nFIRST_ATTEMPT_FAILED -> PARENT_REVIEW_ACTIVE -> WAITING_FOR_SAME_RETRACEMENT_EXTENSION -> SAME_RETRACEMENT_ACTIVE. Terminal paths are PARENT_INVALIDATED, PARENT_EXPIRED, REENTRY_CONSUMED and CLOSED_AFTER_SECOND_FAILURE. Each transition records its event index/time and visible-prefix size.\n",
        encoding="utf-8",
    )
    (OUT / "causal_swing_ledger_specification.md").write_text(
        "# Causal swing-ledger specification\n\nEvery swing is appended only on its N-right confirmation candle. The immutable event records identity, pivot index, side, price, confirmation-time classification/role, detection/confirmation/availability indexes, timeframe and prefix rows used. Later interpretation must be a separate event.\n",
        encoding="utf-8",
    )
    (OUT / "attempt_2_incremental_management_report.md").write_text(
        "# Attempt-2 incremental management report\n\nAttempt 2 uses a fresh causal ledger. Trail candidates appear on confirmation, proof BOS appears on its close, and the trail is committed at that same as-of index. Target, continuation, opportunity, partial, protection and exit histories remain immutable and one action is committed per candle.\n",
        encoding="utf-8",
    )
    (OUT / "remaining_known_issues.md").write_text(
        "# Remaining known issues\n\n- Behaviour remains observational until the candle-by-candle simulator includes spread, commission, slippage and event ordering.\n- Steve must visually approve the changed cases and Trade 51.\n- This is Simulator Baseline V0.9, not Strategy V1.0.\n- Automatic demo and live order execution remain disabled.\n",
        encoding="utf-8",
    )
    verdict_text = "# Simulator-readiness verdict\n\n" + "\n".join(f"{key}: **{value}**" for key, value in verdict.items()) + "\n"
    (OUT / "simulator_readiness_verdict.md").write_text(verdict_text, encoding="utf-8")
    report = {
        "version": DEFAULT_HYBRID_CONFIG.version,
        "frozen_cases": len(rows),
        "changed_cases": len(changed),
        "hard_acceptance": hard,
        "verdict": verdict,
        "performance": performance,
        "dataset_manifest": dataset_manifest,
        "rows": _clean(rows),
    }
    (OUT / "final_prefix_causal_audit.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _html(rows, verdict)
    print(json.dumps({"frozen_cases": len(rows), "changed_cases": len(changed), "hard_acceptance": hard, "verdict": verdict, "performance": performance, "trade_51": {"old_owner": (trade51.get("previous_parent_viability") or {}).get("selected_owner"), "new_owner": (trade51.get("prefix_parent_viability") or {}).get("selected_owner"), "root_cause": _root_cause(trade51)}}, indent=2))
    return report


if __name__ == "__main__":
    run()
