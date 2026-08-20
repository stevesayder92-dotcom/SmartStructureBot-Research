from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import argparse
import csv
import hashlib
import html
import json
import statistics
import sys

import pandas as pd
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.second_touch_structure import _causal_atr
from tools.run_s2b_research import _font, _panel, _symbol_job

OUT = ROOT / "research_runs" / "s2b1_1"
VISUALS = OUT / "visual_overlays"
RECON = OUT / "reconstruction"

ANCHORS = (
    ("AUDUSD#", "BEARISH", "PB_2121"),
    ("USDJPY#", "BEARISH", "PB_1538"),
    ("GER40Cash#", "BEARISH", "PB_2066"),
    ("GER40Cash#", "BULLISH", "PB_2365"),
)

PROVED_STATES = {"SECOND_TOUCH_PROVED_BY_BOS", "SECOND_TOUCH_CONFIRMED"}


def _tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    if not root.exists():
        return h.hexdigest()
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        rel = str(p.relative_to(root)).replace("\\", "/")
        d = hashlib.sha256(p.read_bytes()).hexdigest()
        h.update(rel.encode("utf-8")); h.update(b"\0"); h.update(bytes.fromhex(d))
    return h.hexdigest()


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields or ["state"])
        w.writeheader()
        for row in rows:
            w.writerow({k: json.dumps(v, sort_keys=True, default=str) if isinstance(v, (dict, list, tuple)) else v for k, v in row.items()})


def _profit_factor(values: list[float]) -> float | None:
    win = sum(v for v in values if v > 0)
    loss = abs(sum(v for v in values if v < 0))
    if not loss:
        return None if not win else float("inf")
    return round(win / loss, 6)


def _stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "median": None, "min": None, "max": None}
    return {
        "mean": round(statistics.mean(values), 6),
        "median": round(statistics.median(values), 6),
        "min": round(min(values), 6),
        "max": round(max(values), 6),
    }


def _flatten(job: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row["setup_id"]): row for row in job.get("pairs", [])}


def _variant_payload(row: dict[str, Any], prefix: str) -> dict[str, Any]:
    management = row.get(f"{prefix}_management") or {}
    return {
        "entry_timeframe": row.get(f"{prefix}_entry_timeframe"),
        "entry_epoch": row.get(f"{prefix}_entry_epoch"),
        "entry_price": row.get(f"{prefix}_entry_price"),
        "logical_stop": row.get(f"{prefix}_logical_stop"),
        "stop_distance": row.get(f"{prefix}_stop_distance"),
        "final_R": row.get(f"{prefix}_sequence_final_r"),
        "result": row.get(f"{prefix}_sequence_win_loss"),
        "MFE_R": row.get(f"{prefix}_mfe_r"),
        "MAE_R": row.get(f"{prefix}_mae_r"),
        "peak_R": row.get(f"{prefix}_peak_r"),
        "giveback_R": row.get(f"{prefix}_giveback_r"),
        "reentry_used": bool(row.get(f"{prefix}_reentry_used")),
        "second_touch": row.get(f"{prefix}_second_touch") or {},
        "second_touch_entry": bool(row.get(f"{prefix}_second_touch_entry")),
        "initial_stop_contract": management.get("initial_stop_contract") or {},
        "attempt2_initial_stop_contract": management.get("attempt2_initial_stop_contract") or {},
        "management_state": management.get("management_state"),
    }


def _entry_facts(v: dict[str, Any]) -> tuple[Any, ...]:
    return (v.get("entry_timeframe"), v.get("entry_epoch"), v.get("entry_price"), v.get("logical_stop"))


def _is_proved(v: dict[str, Any]) -> bool:
    return str((v.get("second_touch") or {}).get("state")) in PROVED_STATES


def _metrics(rows: list[dict[str, Any]], letter: str, *, total_events: int, unique_parents: int, terminal_differences: int) -> dict[str, Any]:
    vals = [r[letter] for r in rows if r.get(letter)]
    final = [float(v["final_R"]) for v in vals if v.get("final_R") not in (None, "")]
    mfe = [float(v["MFE_R"]) for v in vals if v.get("MFE_R") not in (None, "")]
    mae = [float(v["MAE_R"]) for v in vals if v.get("MAE_R") not in (None, "")]
    peak = [float(v["peak_R"]) for v in vals if v.get("peak_R") not in (None, "")]
    giveback = [float(v["giveback_R"]) for v in vals if v.get("giveback_R") not in (None, "")]
    wins = sum(v > 0 for v in final)
    touch = [v.get("second_touch") or {} for v in vals]
    return {
        "total_events": total_events,
        "unique_parent_setups": unique_parents,
        "proved_second_touch_parents": sum(str(t.get("state")) in PROVED_STATES for t in touch),
        "double_tops": sum(t.get("double_top_or_bottom") == "DOUBLE_TOP" for t in touch),
        "double_bottoms": sum(t.get("double_top_or_bottom") == "DOUBLE_BOTTOM" for t in touch),
        "trigger_supersessions": sum(bool(t.get("old_trigger_superseded")) for t in touch),
        "terminal_population_differences": terminal_differences,
        "m1_entry_count": sum(v.get("entry_timeframe") == "M1" for v in vals),
        "m5_entry_count": sum(v.get("entry_timeframe") == "M5" for v in vals),
        "reentry_count": sum(bool(v.get("reentry_used")) for v in vals),
        "trade_count": len(final),
        "win_rate": round(wins / len(final), 6) if final else None,
        "expectancy_R": round(statistics.mean(final), 6) if final else None,
        "profit_factor_R": _profit_factor(final),
        "total_R": round(sum(final), 6),
        "MFE_R": _stats(mfe),
        "MAE_R": _stats(mae),
        "peak_R": _stats(peak),
        "final_R": _stats(final),
        "giveback_R": _stats(giveback),
    }


def _event_price(event: dict[str, Any] | None) -> Any:
    return None if not event else event.get("price")


def _event_index(event: dict[str, Any] | None) -> Any:
    return None if not event else event.get("swing_index")


def _frame_for_variant(symbol_dir: Path, variant: dict[str, Any]) -> tuple[pd.DataFrame, int]:
    tf = str(variant.get("entry_timeframe") or "M1")
    seconds = 300 if tf == "M5" else 60
    return pd.read_csv(symbol_dir / f"{tf}.csv"), seconds


def _entry_index(frame: pd.DataFrame, seconds: int, entry_epoch: Any) -> int | None:
    if entry_epoch in (None, ""):
        return None
    closes = frame["time"].astype(float) + float(seconds)
    matches = list(frame.index[(closes - float(entry_epoch)).abs() < 1e-6])
    if matches:
        return int(matches[0])
    pos = int(closes.searchsorted(float(entry_epoch), side="left"))
    return pos if 0 <= pos < len(frame) else None


def _anchor_report(row: dict[str, Any] | None, symbol_dir: Path | None, symbol: str, direction: str, suffix: str) -> str:
    if row is None or symbol_dir is None:
        return f"Manual Reconstruction Report: {symbol} {suffix}\nAUTOMATED VERDICT: REJECTED / NOT IN PAIRED POPULATION\n"
    A, B, C = row["A"], row["B"], row["C"]
    touch = B.get("second_touch") or C.get("second_touch") or {}
    t1 = touch.get("touch_1") or {}
    t2 = touch.get("touch_2") or {}
    reaction = touch.get("separating_reaction") or {}
    trigger = touch.get("provisional_trigger") or touch.get("active_trigger") or {}
    frame, seconds = _frame_for_variant(symbol_dir, B)
    trigger_index = _event_index(trigger)
    reaction_atr = None
    if trigger_index is not None and 0 <= int(trigger_index) < len(frame):
        reaction_atr = float(_causal_atr(frame, int(trigger_index)))
    reaction_mag = None
    if _event_price(trigger) is not None and _event_price(t2) is not None:
        reaction_mag = abs(float(_event_price(trigger)) - float(_event_price(t2)))
    entry_idx = _entry_index(frame, seconds, B.get("entry_epoch"))
    contract = B.get("initial_stop_contract") or {}
    prox_atr = touch.get("touch_proximity_atr")
    touch_distance = touch.get("touch_distance")
    prox_limit = (0.25 * float(prox_atr)) if prox_atr not in (None, "") else None
    reaction_limit = (0.35 * float(reaction_atr)) if reaction_atr is not None else None
    bos_idx = touch.get("bos_proof_index")
    bos_close = touch.get("bos_proof_price")
    latency_minutes = None
    if A.get("entry_epoch") not in (None, "") and B.get("entry_epoch") not in (None, ""):
        latency_minutes = round((float(B["entry_epoch"]) - float(A["entry_epoch"])) / 60.0, 6)
    accepted = bool(_is_proved(B) and B.get("entry_epoch") not in (None, ""))
    reason = "SECOND_TOUCH_PROVED_BY_BOS_AND_ENTRY_PRESENT" if accepted else str(touch.get("rejection_reasons") or touch.get("state") or "NO_SECOND_TOUCH")
    lines = [
        f"Manual Reconstruction Report: {symbol} {direction} {suffix}",
        "=" * 72,
        f"Setup ID: {row['setup_id']}",
        f"Automated verdict: {'ACCEPTED' if accepted else 'REJECTED'}",
        f"Reason: {reason}",
        "",
        f"Touch-1: index={_event_index(t1)} price={_event_price(t1)}",
        f"Touch-2 candidate: index={_event_index(t2)} price={_event_price(t2)}",
        f"Touch distance: {touch_distance}",
        f"Touch-Proximity ATR source index: {touch.get('touch_proximity_atr_source_index')}",
        f"Touch-Proximity ATR value: {prox_atr}",
        f"0.25 ATR threshold: {prox_limit}",
        f"0.25 proximity verdict: {None if touch_distance is None or prox_limit is None else float(touch_distance) <= float(prox_limit)}",
        "",
        f"Separating reaction: index={_event_index(reaction)} price={_event_price(reaction)}",
        f"Provisional trigger: index={_event_index(trigger)} level={_event_price(trigger)}",
        f"Reaction ATR source index: {trigger_index}",
        f"Reaction ATR value: {reaction_atr}",
        f"Reaction magnitude: {reaction_mag}",
        f"0.35 ATR threshold: {reaction_limit}",
        f"0.35 reaction verdict: {None if reaction_mag is None or reaction_limit is None else float(reaction_mag) >= float(reaction_limit)}",
        "",
        f"BOS proof index: {bos_idx}",
        f"BOS close: {bos_close}",
        f"BOS proof method: {touch.get('proof_method')}",
        f"Entry readiness: {accepted}",
        f"Entry index: {entry_idx}",
        f"Entry price: {B.get('entry_price')}",
        f"Entry timeframe: {B.get('entry_timeframe')}",
        "",
        "InitialStopContract:",
        json.dumps(contract, indent=2, sort_keys=True, default=str),
        "",
        f"S2B.1 legacy A entry epoch: {A.get('entry_epoch')}",
        f"S2B.1.1 repaired B entry epoch: {B.get('entry_epoch')}",
        f"Latency B minus A (minutes): {latency_minutes}",
        f"Variant C entry epoch: {C.get('entry_epoch')}",
        "MANUAL_SHADOW: audit-only; no feed into automated state.",
        "Threshold tuning performed: NO",
    ]
    return "\n".join(lines) + "\n"


def _event_time(frame: pd.DataFrame, event: dict[str, Any] | None, seconds: int) -> float | None:
    idx = _event_index(event)
    if idx is None or not 0 <= int(idx) < len(frame):
        return None
    return float(frame.iloc[int(idx)]["time"]) + seconds


def _anchor_chart(number: int, row: dict[str, Any], data_dir: Path) -> str:
    m1 = pd.read_csv(data_dir / "M1.csv")
    m5 = pd.read_csv(data_dir / "M5.csv")
    B, C = row["B"], row["C"]
    decision = float(B.get("entry_epoch") or C.get("entry_epoch"))
    upper = m5.iloc[max(0, int((m5.time.astype(float)+300).searchsorted(decision-65*300))):min(len(m5), int((m5.time.astype(float)+300).searchsorted(decision+25*300, side='right')))].reset_index(drop=True)
    lower = m1.iloc[max(0, int((m1.time.astype(float)+60).searchsorted(decision-150*60))):min(len(m1), int((m1.time.astype(float)+60).searchsorted(decision+50*60, side='right')))].reset_index(drop=True)
    image = Image.new("RGB", (1700, 1120), "#edf4fb")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0,0,1700,105), fill="#123b66")
    draw.text((28,18), f"S2B.1.1 Anchor {number} · {row['symbol']} · {row['direction']} · {row['setup_id'].split('|')[-1]}", fill="white", font=_font(28, True))
    draw.text((28,62), "A legacy control · B repaired canonical · C repaired earned-early · MANUAL_SHADOW audit-only", fill="white", font=_font(17))
    upper_markers=[]; lower_markers=[]
    for letter, color in (("A","#1769ff"),("B","#e07a00"),("C","#008b75")):
        v=row[letter]
        if v.get("entry_epoch") is not None:
            marker=(float(v["entry_epoch"]), f"{letter} ENTRY", color)
            (upper_markers if v.get("entry_timeframe")=="M5" else lower_markers).append(marker)
    touch=B.get("second_touch") or C.get("second_touch") or {}
    if str(touch.get("state")) in PROVED_STATES:
        tf=B.get("entry_timeframe") or C.get("entry_timeframe") or "M1"
        frame,sec=(m5,300) if tf=="M5" else (m1,60)
        target=upper_markers if tf=="M5" else lower_markers
        for ev,label,color in ((touch.get("touch_1"),"TOUCH 1","#7849ff"),(touch.get("touch_2"),"TOUCH 2 / STOP OWNER","#b4234d"),(touch.get("provisional_trigger") or touch.get("active_trigger"),"PROVISIONAL TRIGGER","#9a62ff")):
            et=_event_time(frame,ev,sec)
            if et is not None: target.append((et,label,color))
    upper_levels=[]; lower_levels=[]
    for letter,color in (("A","#1769ff"),("B","#e07a00"),("C","#008b75")):
        v=row[letter]
        if v.get("logical_stop") is not None:
            (upper_levels if v.get("entry_timeframe")=="M5" else lower_levels).append((float(v["logical_stop"]),f"{letter} STOP",color))
    _panel(draw, upper, (30,125,1670,570), seconds=300, markers=upper_markers, levels=upper_levels, decision_time=decision)
    _panel(draw, lower, (30,610,1670,1050), seconds=60, markers=lower_markers, levels=lower_levels, decision_time=decision)
    draw.text((32,1070), f"Automated B state={touch.get('state','NO_SECOND_TOUCH')} · authoritative touch overlay shown only when proved · zero orders", fill="#263f5c", font=_font(16, True))
    name=f"anchor_{number}_{row['symbol'].replace('#','')}_{row['setup_id'].split('|')[-1]}.png"
    image.save(VISUALS/name)
    return name


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="*", default=None, help="Optional simulator_data/library directory names")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True); VISUALS.mkdir(parents=True, exist_ok=True); RECON.mkdir(parents=True, exist_ok=True)
    before = _tree_hash(ROOT / "research_data")
    library = ROOT / "simulator_data" / "library"
    dirs = sorted(p.name for p in library.iterdir() if p.is_dir() and (p / "manifest.json").exists())
    if args.symbols:
        dirs = [d for d in dirs if d in set(args.symbols)]
    rows: list[dict[str, Any]] = []
    terminal_differences: list[dict[str, Any]] = []
    totals = {"A_events": 0, "B_events": 0, "A_parents": 0, "B_parents": 0}
    symbol_dirs: dict[str, Path] = {}

    for d in dirs:
        legacy = _symbol_job(d, True, False)
        repaired = _symbol_job(d, True, True)
        symbol = legacy.get("symbol") or repaired.get("symbol")
        symbol_dirs[str(symbol)] = library / d
        la = _flatten(legacy); rb = _flatten(repaired)
        totals["A_events"] += int(legacy.get("candidate_count") or 0)
        totals["B_events"] += int(repaired.get("candidate_count") or 0)
        totals["A_parents"] += len(la); totals["B_parents"] += len(rb)
        for sid in sorted(set(la) | set(rb)):
            arow, brow = la.get(sid), rb.get(sid)
            if not arow or not brow:
                terminal_differences.append({"symbol": symbol, "setup_id": sid, "in_A": bool(arow), "in_BC": bool(brow)})
                continue
            A = _variant_payload(arow, "baseline")
            B = _variant_payload(brow, "baseline")
            C = _variant_payload(brow, "s2b")
            touch = B.get("second_touch") or C.get("second_touch") or {}
            row = {
                "symbol": brow["symbol"], "setup_id": sid, "direction": brow["direction"],
                "A": A, "B": B, "C": C,
                "proved_second_touch": str(touch.get("state")) in PROVED_STATES,
                "double_top_or_bottom": touch.get("double_top_or_bottom"),
                "trigger_superseded": bool(touch.get("old_trigger_superseded")),
                "B_minus_A_minutes": round((float(B["entry_epoch"])-float(A["entry_epoch"]))/60.0, 6),
                "C_minus_A_minutes": round((float(C["entry_epoch"])-float(A["entry_epoch"]))/60.0, 6),
                "B_stop_delta": round(float(B["stop_distance"])-float(A["stop_distance"]), 10),
                "C_stop_delta": round(float(C["stop_distance"])-float(A["stop_distance"]), 10),
                "B_first_entry_changed": _entry_facts(B) != _entry_facts(A),
                "C_first_entry_changed": _entry_facts(C) != _entry_facts(A),
                "B_reentry_changed": B.get("reentry_used") != A.get("reentry_used"),
                "C_reentry_changed": C.get("reentry_used") != A.get("reentry_used"),
                "research_only": True, "order_api_called": False,
            }
            rows.append(row)
        print(f"S2B.1.1 {symbol}: A={len(la)} B/C={len(rb)} paired={sum(1 for r in rows if r['symbol']==symbol)}", flush=True)

    rows.sort(key=lambda r: (r["symbol"], r["setup_id"]))
    _write_csv(OUT / "paired_setup_results.csv", rows)
    _write_csv(OUT / "terminal_population_differences.csv", terminal_differences)

    b_affected = [r for r in rows if _is_proved(r["B"])]
    c_affected = [r for r in rows if _is_proved(r["C"])]
    per_symbol: dict[str, Any] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows: grouped[r["symbol"]].append(r)
    for symbol, subset in sorted(grouped.items()):
        per_symbol[symbol] = {
            "A": _metrics(subset, "A", total_events=len(subset), unique_parents=len(subset), terminal_differences=sum(x["symbol"]==symbol for x in terminal_differences)),
            "B": _metrics(subset, "B", total_events=len(subset), unique_parents=len(subset), terminal_differences=sum(x["symbol"]==symbol for x in terminal_differences)),
            "C": _metrics(subset, "C", total_events=len(subset), unique_parents=len(subset), terminal_differences=sum(x["symbol"]==symbol for x in terminal_differences)),
        }

    summary = {
        "phase": "S2B.1.1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "order_api_called": False,
        "research_data_before_sha256": before,
        "research_data_after_sha256": _tree_hash(ROOT / "research_data"),
        "paired_setups": len(rows),
        "terminal_population_differences": len(terminal_differences),
        "A": _metrics(rows, "A", total_events=totals["A_events"], unique_parents=totals["A_parents"], terminal_differences=len(terminal_differences)),
        "B": _metrics(rows, "B", total_events=totals["B_events"], unique_parents=totals["B_parents"], terminal_differences=len(terminal_differences)),
        "C": _metrics(rows, "C", total_events=totals["B_events"], unique_parents=totals["B_parents"], terminal_differences=len(terminal_differences)),
        "B_first_entry_facts_changed": sum(r["B_first_entry_changed"] for r in rows),
        "C_first_entry_facts_changed": sum(r["C_first_entry_changed"] for r in rows),
        "B_reentry_facts_changed": sum(r["B_reentry_changed"] for r in rows),
        "C_reentry_facts_changed": sum(r["C_reentry_changed"] for r in rows),
        "B_unchanged_affected_second_touch_parents": sum(not r["B_first_entry_changed"] and not r["B_reentry_changed"] for r in b_affected),
        "C_unchanged_affected_second_touch_parents": sum(not r["C_first_entry_changed"] and not r["C_reentry_changed"] for r in c_affected),
        "B_entry_time_delta_minutes": _stats([float(r["B_minus_A_minutes"]) for r in rows]),
        "C_entry_time_delta_minutes": _stats([float(r["C_minus_A_minutes"]) for r in rows]),
        "B_stop_distance_delta": _stats([float(r["B_stop_delta"]) for r in rows]),
        "C_stop_distance_delta": _stats([float(r["C_stop_delta"]) for r in rows]),
        "per_symbol": per_symbol,
    }
    summary["research_data_unchanged"] = summary["research_data_before_sha256"] == summary["research_data_after_sha256"]

    anchor_manifest=[]
    for number, (symbol, direction, suffix) in enumerate(ANCHORS, 1):
        match = next((r for r in rows if r["symbol"] == symbol and r["direction"] == direction and r["setup_id"].endswith(suffix)), None)
        report = _anchor_report(match, symbol_dirs.get(symbol), symbol, direction, suffix)
        report_path = RECON / f"{symbol.replace('#','').lower()}_{suffix.lower()}_report.txt"
        report_path.write_text(report, encoding="utf-8")
        chart_file = None
        if match is not None and symbol in symbol_dirs:
            chart_file = _anchor_chart(number, match, symbol_dirs[symbol])
        anchor_manifest.append({"number": number, "symbol": symbol, "direction": direction, "setup_suffix": suffix, "automated_match": bool(match), "report_file": str(report_path.relative_to(OUT)).replace('\\','/'), "chart_file": f"visual_overlays/{chart_file}" if chart_file else None, "manual_shadow": True, "feeds_automated_state": False})

    _write_csv(OUT / "manual_anchor_manifest.csv", anchor_manifest)
    articles=[]
    for a in anchor_manifest:
        img = f"<img src='{html.escape(a['chart_file'])}' style='width:100%;border:1px solid #9ab0c8'>" if a.get('chart_file') else "<p>No automated paired reconstruction found.</p>"
        articles.append(f"<article><h2>{a['number']} · {html.escape(a['symbol'])} · {html.escape(a['setup_suffix'])}</h2><p>MANUAL_SHADOW · audit-only · feeds automated state: NO</p>{img}</article>")
    (OUT / "manual_anchor_review.html").write_text("<!doctype html><meta charset='utf-8'><title>S2B.1.1 manual anchors</title><style>body{font-family:Arial;background:#edf4fb;color:#12345b}article{background:white;margin:24px;padding:18px;border-radius:12px}</style>"+"".join(articles), encoding="utf-8")

    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return 0 if summary["research_data_unchanged"] and not summary["order_api_called"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
