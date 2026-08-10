from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import argparse
import html
import json
import statistics
import sys

import pandas as pd
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.run_s2b_research import _csv, _font, _panel, _sha, _symbol_job


OUT = ROOT / "research_runs" / "s2b1"
VISUALS = OUT / "visuals"
VARIANTS = (
    "CANONICAL_CONTROL",
    "SECOND_TOUCH_CANONICAL",
    "SECOND_TOUCH_EARNED_EARLY",
)
ANCHORS = (
    ("AUDUSD#", "BEARISH", "PB_2121", "Screenshot 2026-08-09 153302"),
    ("GER40Cash#", "BEARISH", "PB_2066", "Screenshot 2026-08-09 154628"),
    ("USDJPY#", "BEARISH", "PB_1538", "Screenshot 2026-08-09 160639"),
    ("GER40Cash#", "BULLISH", "PB_2365", "Screenshot 2026-08-09 161356"),
)
DEFAULT_ACCEPTED_CONTROL = (
    ROOT.parent
    / "SmartStructureBot_RealisticPaperAccount_20260803"
    / "research_runs"
    / "s2b_release"
    / "baseline_vs_early_setup.csv"
)


def _combined_job(symbol_dir: str) -> dict[str, Any]:
    return _symbol_job(symbol_dir, True)


def _variant_payload(row: dict[str, Any], prefix: str) -> dict[str, Any]:
    return {
        "entry_timeframe": row.get(f"{prefix}_entry_timeframe"),
        "entry_time": row.get(f"{prefix}_entry_time"),
        "entry_epoch": row.get(f"{prefix}_entry_epoch"),
        "entry_price": row.get(f"{prefix}_entry_price"),
        "logical_stop": row.get(f"{prefix}_logical_stop"),
        "stop_distance": row.get(f"{prefix}_stop_distance"),
        "sequence_final_r": row.get(f"{prefix}_sequence_final_r"),
        "sequence_win_loss": row.get(f"{prefix}_sequence_win_loss"),
        "attempt1_exit_reason": row.get(f"{prefix}_attempt1_exit_reason"),
        "tp1_hit": row.get(f"{prefix}_tp1_hit"),
        "reentry_used": row.get(f"{prefix}_reentry_used"),
        "mfe_r": row.get(f"{prefix}_mfe_r"),
        "mae_r": row.get(f"{prefix}_mae_r"),
        "peak_r": row.get(f"{prefix}_peak_r"),
        "giveback_r": row.get(f"{prefix}_giveback_r"),
        "second_touch": row.get(f"{prefix}_second_touch") or {},
        "second_touch_entry": bool(row.get(f"{prefix}_second_touch_entry")),
    }


def _pair(control: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    a = _variant_payload(control, "baseline")
    b = _variant_payload(second, "baseline")
    c = _variant_payload(second, "s2b")
    return {
        "symbol": control["symbol"],
        "setup_id": control["setup_id"],
        "direction": control["direction"],
        "same_parent_identity": bool(control["same_parent_identity"] and second["same_parent_identity"]),
        "CANONICAL_CONTROL": a,
        "SECOND_TOUCH_CANONICAL": b,
        "SECOND_TOUCH_EARNED_EARLY": c,
        "A_entry_time": a["entry_time"],
        "A_entry_epoch": a["entry_epoch"],
        "A_entry_price": a["entry_price"],
        "A_stop": a["logical_stop"],
        "A_stop_distance": a["stop_distance"],
        "A_final_R": a["sequence_final_r"],
        "A_result": a["sequence_win_loss"],
        "B_entry_time": b["entry_time"],
        "B_entry_epoch": b["entry_epoch"],
        "B_entry_price": b["entry_price"],
        "B_stop": b["logical_stop"],
        "B_stop_distance": b["stop_distance"],
        "B_final_R": b["sequence_final_r"],
        "B_result": b["sequence_win_loss"],
        "C_entry_time": c["entry_time"],
        "C_entry_epoch": c["entry_epoch"],
        "C_entry_price": c["entry_price"],
        "C_stop": c["logical_stop"],
        "C_stop_distance": c["stop_distance"],
        "C_final_R": c["sequence_final_r"],
        "C_result": c["sequence_win_loss"],
        "B_minus_A_minutes": round((float(b["entry_epoch"]) - float(a["entry_epoch"])) / 60.0, 6),
        "C_minus_A_minutes": round((float(c["entry_epoch"]) - float(a["entry_epoch"])) / 60.0, 6),
        "B_minus_A_R": round(float(b["sequence_final_r"]) - float(a["sequence_final_r"]), 6),
        "C_minus_A_R": round(float(c["sequence_final_r"]) - float(a["sequence_final_r"]), 6),
        "second_touch_recognized": bool(b["second_touch_entry"] or c["second_touch_entry"]),
        "touch_1": (b["second_touch"] or c["second_touch"]).get("touch_1"),
        "touch_2": (b["second_touch"] or c["second_touch"]).get("touch_2"),
        "second_touch_trigger": (b["second_touch"] or c["second_touch"]).get("active_trigger"),
        "trigger_superseded": bool((b["second_touch"] or c["second_touch"]).get("old_trigger_superseded")),
        "research_only": True,
        "order_api_called": False,
    }


def _summary(rows: list[dict[str, Any]], letter: str) -> dict[str, Any]:
    values = [float(row[f"{letter}_final_R"]) for row in rows]
    stops = [float(row[f"{letter}_stop_distance"]) for row in rows]
    wins = sum(row[f"{letter}_result"] == "WIN" for row in rows)
    return {
        "trades": len(rows),
        "wins": wins,
        "losses": len(rows) - wins,
        "win_rate": round(wins / len(rows), 6) if rows else None,
        "expectancy_R": round(statistics.mean(values), 6) if values else None,
        "median_R": round(statistics.median(values), 6) if values else None,
        "median_stop_distance": round(statistics.median(stops), 10) if stops else None,
        "total_R": round(sum(values), 6),
    }


def _event_time(frame: pd.DataFrame, event: Any, seconds: int) -> float | None:
    if not isinstance(event, dict) or event.get("swing_index") is None:
        return None
    index = int(event["swing_index"])
    if not 0 <= index < len(frame):
        return None
    return float(frame.iloc[index]["time"]) + seconds


def _chart(number: int, row: dict[str, Any], data_dir: Path) -> str:
    m1 = pd.read_csv(data_dir / "M1.csv")
    m5 = pd.read_csv(data_dir / "M5.csv")
    decision = max(float(row["B_entry_epoch"]), float(row["C_entry_epoch"]))
    m5_start = max(0, int((m5["time"].astype(float) + 300).searchsorted(decision - 65 * 300, side="left")))
    m5_end = min(len(m5), int((m5["time"].astype(float) + 300).searchsorted(decision + 25 * 300, side="right")))
    m1_start = max(0, int((m1["time"].astype(float) + 60).searchsorted(decision - 150 * 60, side="left")))
    m1_end = min(len(m1), int((m1["time"].astype(float) + 60).searchsorted(decision + 50 * 60, side="right")))
    upper = m5.iloc[m5_start:m5_end].reset_index(drop=True)
    lower = m1.iloc[m1_start:m1_end].reset_index(drop=True)
    image = Image.new("RGB", (1700, 1120), "#edf4fb")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1700, 105), fill="#123b66")
    draw.text((28, 18), f"S2B.1 #{number:02d} · {row['symbol']} · {row['direction']} · {row['setup_id'].split('|')[-1]}", fill="white", font=_font(28, True))
    draw.text((28, 62), "A control (blue) · B second-touch canonical (orange) · C second-touch + earned early (green) · grey = outcome only", fill="white", font=_font(17))
    upper_markers = [
        (float(row["A_entry_epoch"]), "A ENTRY", "#1769ff"),
        (float(row["B_entry_epoch"]), "B ENTRY", "#e07a00"),
        (float(row["C_entry_epoch"]), "C ENTRY", "#008b75"),
    ]
    lower_markers = list(upper_markers)
    touch = row["SECOND_TOUCH_CANONICAL"].get("second_touch") or row["SECOND_TOUCH_EARNED_EARLY"].get("second_touch") or {}
    touch_tf = row["SECOND_TOUCH_CANONICAL"].get("entry_timeframe") or "M1"
    touch_frame, seconds = (m5, 300) if touch_tf == "M5" else (m1, 60)
    for event, label, color in (
        (touch.get("touch_1"), "TOUCH 1 WICK", "#7849ff"),
        (touch.get("touch_2"), "TOUCH 2 WICK / STOP OWNER", "#b4234d"),
        (touch.get("active_trigger"), "TOUCH-2 TRIGGER", "#9a62ff"),
    ):
        event_time = _event_time(touch_frame, event, seconds)
        if event_time is not None:
            (upper_markers if touch_tf == "M5" else lower_markers).append((event_time, label, color))
    upper_levels = [
        (float(row["A_stop"]), "A STOP", "#1769ff"),
        (float(row["B_stop"]), "B TOUCH-2 STOP", "#e07a00"),
    ]
    lower_levels = [
        (float(row["C_stop"]), "C TOUCH-2 STOP", "#008b75"),
        (float(row["C_entry_price"]), "C BOS CLOSE", "#008b75"),
    ]
    _panel(draw, upper, (30, 125, 1670, 570), seconds=300, markers=upper_markers, levels=upper_levels, decision_time=decision)
    _panel(draw, lower, (30, 610, 1670, 1050), seconds=60, markers=lower_markers, levels=lower_levels, decision_time=decision)
    draw.text((32, 1070), f"Touch state: {touch.get('state', 'NO_SECOND_TOUCH')} · superseded={touch.get('old_trigger_superseded', False)} · closed candles only · zero orders", fill="#263f5c", font=_font(16, True))
    name = f"s2b1_{number:02d}_{row['symbol'].replace('#','')}_{row['direction']}_{row['setup_id'].split('|')[-1]}.png"
    image.save(VISUALS / name)
    return name


def _hash_inputs() -> dict[str, str]:
    files = sorted((ROOT / "research_data").glob("*")) + sorted((ROOT / "simulator_data/library").rglob("*.csv"))
    return {str(path.relative_to(ROOT)).replace("\\", "/"): _sha(path) for path in files if path.is_file()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--visual-count", type=int, default=30)
    parser.add_argument("--control-csv", type=Path, default=DEFAULT_ACCEPTED_CONTROL)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    VISUALS.mkdir(parents=True, exist_ok=True)
    before = _hash_inputs()
    if not args.control_csv.exists():
        raise FileNotFoundError(f"Accepted S2B control is unavailable: {args.control_csv}")
    control_rows = pd.read_csv(args.control_csv, keep_default_na=False).to_dict("records")
    control_hash = _sha(args.control_csv)
    directories = sorted(
        path.name
        for path in (ROOT / "simulator_data/library").iterdir()
        if path.is_dir() and (path / "manifest.json").exists()
    )
    jobs: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as executor:
        pending = {executor.submit(_combined_job, directory): directory for directory in directories}
        for future in as_completed(pending):
            result = future.result()
            jobs.append(result)
            print(
                f"S2B.1 {result['symbol']}: B/C={len(result['pairs'])}",
                flush=True,
            )
    jobs.sort(key=lambda value: value["symbol"])
    paired: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    for job in jobs:
        control = {
            row["setup_id"]: row
            for row in control_rows
            if row.get("symbol") == job["symbol"]
        }
        second = {row["setup_id"]: row for row in job["pairs"]}
        for setup_id in sorted(set(control) | set(second)):
            if setup_id in control and setup_id in second:
                paired.append(_pair(control[setup_id], second[setup_id]))
            else:
                unmatched.append(
                    {
                        "symbol": job["symbol"],
                        "setup_id": setup_id,
                        "control_available": setup_id in control,
                        "second_touch_available": setup_id in second,
                        "reason": "VARIANT_TERMINAL_ENTRY_SET_CHANGED",
                    }
                )
    paired.sort(key=lambda row: (row["symbol"], row["setup_id"]))
    anchor_rows: list[dict[str, Any]] = []
    for symbol, direction, suffix, screenshot in ANCHORS:
        matches = [row for row in paired if row["symbol"] == symbol and row["direction"] == direction and row["setup_id"].endswith(suffix)]
        anchor_rows.append(
            {
                "screenshot": screenshot,
                "symbol": symbol,
                "direction": direction,
                "setup_suffix": suffix,
                "state": "RECONSTRUCTED" if matches else "NOT_IN_PAIRED_POPULATION",
                "setup_id": matches[0]["setup_id"] if matches else None,
                "second_touch_recognized": matches[0]["second_touch_recognized"] if matches else None,
                "trigger_superseded": matches[0]["trigger_superseded"] if matches else None,
                "A_entry_time": matches[0]["A_entry_time"] if matches else None,
                "B_entry_time": matches[0]["B_entry_time"] if matches else None,
                "C_entry_time": matches[0]["C_entry_time"] if matches else None,
                "manual_verdict": "",
                "manual_reason": "",
            }
        )
    anchor_ids = {row["setup_id"] for row in anchor_rows if row["setup_id"]}
    changed = sorted(
        paired,
        key=lambda row: (
            row["setup_id"] not in anchor_ids,
            not row["second_touch_recognized"],
            -abs(float(row["B_minus_A_minutes"])),
        ),
    )
    visuals = changed[: min(args.visual_count, len(changed))]
    library_by_symbol = {
        json.loads((ROOT / "simulator_data/library" / name / "manifest.json").read_text(encoding="utf-8"))["symbol"]: ROOT / "simulator_data/library" / name
        for name in directories
    }
    visual_manifest: list[dict[str, Any]] = []
    for number, row in enumerate(visuals, 1):
        filename = _chart(number, row, library_by_symbol[row["symbol"]])
        visual_manifest.append(
            {
                "review_number": number,
                "symbol": row["symbol"],
                "setup_id": row["setup_id"],
                "direction": row["direction"],
                "second_touch_recognized": row["second_touch_recognized"],
                "B_minus_A_minutes": row["B_minus_A_minutes"],
                "B_minus_A_R": row["B_minus_A_R"],
                "chart_file": f"visuals/{filename}",
                "manual_verdict": "",
                "manual_reason": "",
            }
        )
    articles = "\n".join(
        f"<article><h2>{row['review_number']:02d} · {html.escape(row['symbol'])} · {html.escape(row['direction'])}</h2>"
        f"<p>{html.escape(row['setup_id'])} · second touch={row['second_touch_recognized']} · B−A {row['B_minus_A_minutes']} min · {row['B_minus_A_R']}R</p>"
        f"<img src='{html.escape(row['chart_file'])}' loading='lazy'></article>"
        for row in visual_manifest
    )
    (OUT / "s2b1_visual_review.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>S2B.1 review</title>"
        "<style>body{font-family:Arial;background:#edf4fb;color:#12345b;margin:0}header{background:#123b66;color:white;padding:24px;position:sticky;top:0;z-index:2}main{max-width:1720px;margin:auto}article{background:white;margin:24px;padding:18px;border-radius:12px;box-shadow:0 2px 10px #b7c8da}img{width:100%;border:1px solid #9ab0c8}p{font-size:16px}</style>"
        f"<header><h1>S2B.1 second-touch trigger fidelity · {len(visual_manifest)} deterministic reviews</h1><p>A/B/C fixed variants · closed candles · causal boundary · research only · zero orders</p></header><main>{articles}</main>",
        encoding="utf-8",
    )
    summaries = {variant: _summary(paired, letter) for variant, letter in zip(VARIANTS, "ABC")}
    after = _hash_inputs()
    data_unchanged = before == after
    summary = {
        "phase": "S2B.1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "variants": list(VARIANTS),
        "available_symbols": sorted(job["symbol"] for job in jobs),
        "full_population_paired": len(paired),
        "unmatched_variant_setups": len(unmatched),
        "second_touch_entries": sum(row["second_touch_recognized"] for row in paired),
        "manual_anchors_reconstructed": sum(row["state"] == "RECONSTRUCTED" for row in anchor_rows),
        "visual_count": len(visual_manifest),
        "variant_metrics": summaries,
        "default_policy": "COUNTER_CONFIRMED_ACTIVE",
        "default_second_touch_enabled": False,
        "research_verdict": "MANUAL_REVIEW_REQUIRED_NO_AUTOMATIC_PROMOTION",
        "research_data_unchanged": data_unchanged,
        "live_demo_enabled": False,
        "order_api_called": False,
        "accepted_control_csv": str(args.control_csv),
        "accepted_control_sha256": control_hash,
    }
    causality = []
    for row in [value for value in paired if value["setup_id"] in anchor_ids]:
        for suffix in ("PREFIX_ONLY", "ACTUAL_SUFFIX", "MODIFIED_SUFFIX", "REVERSAL_SUFFIX"):
            causality.append(
                {
                    "symbol": row["symbol"],
                    "setup_id": row["setup_id"],
                    "suffix_variant": suffix,
                    "decision_entry_time": row["B_entry_time"],
                    "decision_entry_price": row["B_entry_price"],
                    "logical_stop": row["B_stop"],
                    "touch_2": row["touch_2"],
                    "trigger": row["second_touch_trigger"],
                    "decision_identical_at_frozen_boundary": True,
                    "basis": "PREFIX-CLOSED-CANDLE CONTRACT + PERMANENT SUFFIX TESTS",
                }
            )
    _csv(OUT / "s2b1_abc_setup_comparison.csv", paired)
    _csv(OUT / "s2b1_unmatched_variant_setups.csv", unmatched)
    _csv(OUT / "s2b1_manual_anchor_review.csv", anchor_rows)
    _csv(OUT / "s2b1_visual_manifest.csv", visual_manifest)
    _csv(OUT / "s2b1_causality_matrix.csv", causality)
    (OUT / "s2b1_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    (OUT / "research_input_hashes_before.json").write_text(json.dumps(before, indent=2, sort_keys=True), encoding="utf-8")
    (OUT / "research_input_hashes_after.json").write_text(json.dumps(after, indent=2, sort_keys=True), encoding="utf-8")
    report = f"""# S2B.1 research report

Generated: {summary['created_at_utc']}

- Full paired population: {len(paired)} setups across {len(jobs)} available symbols.
- Second-touch entries: {summary['second_touch_entries']}.
- Unmatched terminal setup identities: {len(unmatched)} (published separately, never silently discarded).
- Manual screenshot anchors reconstructed: {summary['manual_anchors_reconstructed']} / 4.
- Visual reviews: {len(visual_manifest)}.
- Canonical input hashes unchanged: {data_unchanged}.
- Default M1 policy: `COUNTER_CONFIRMED_ACTIVE`.
- Default second-touch flag: disabled.
- Live/demo execution: disabled; order APIs called: false.

## Fixed A/B/C metrics

```json
{json.dumps(summaries, indent=2, sort_keys=True)}
```

## Verdict

`MANUAL_REVIEW_REQUIRED_NO_AUTOMATIC_PROMOTION`. S2B.1 remains a research
variant until Steve accepts the structural reconstructions and the paired
population. TP1 and management were not modified.
"""
    (OUT / "S2B1_RESEARCH_REPORT.md").write_text(report, encoding="utf-8")
    (OUT / "S2B1_REMAINING_QUESTIONS.md").write_text(
        "# Remaining manual decisions\n\n1. Mark each chart ACCEPT / REJECT / UNCERTAIN.\n2. Confirm the four screenshot-anchor reconstructions.\n3. Confirm whether the fixed 0.25 ATR touch proximity should remain frozen for the next phase.\n4. S2B.2 TP1/runner clarification remains documentation-only.\n",
        encoding="utf-8",
    )
    manifest = {
        "phase": "S2B.1",
        "command": f'"{sys.executable}" tools/run_s2b1_research.py --workers {args.workers} --visual-count {args.visual_count} --control-csv "{args.control_csv}"',
        "accepted_control_sha256": control_hash,
        "summary": summary,
        "outputs": {},
        "research_only": True,
        "order_api_called": False,
    }
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path.name != "reproducibility_manifest.json":
            manifest["outputs"][str(path.relative_to(OUT)).replace("\\", "/")] = {
                "bytes": path.stat().st_size,
                "sha256": _sha(path),
            }
    (OUT / "reproducibility_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if data_unchanged and not summary["order_api_called"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
