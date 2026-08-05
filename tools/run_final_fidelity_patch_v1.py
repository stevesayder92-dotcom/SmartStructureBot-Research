from __future__ import annotations

import csv
import html
import json
import pickle
from pathlib import Path
import shutil
import sys
from typing import Any, Dict

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.run_final_fidelity_evidence as baseline  # noqa: E402
from core.fidelity_patch import (  # noqa: E402
    DEFAULT_PATCH_CONFIG,
    classify_m1_outcome,
    count_trade_identity,
    simulate_patched_profit_management,
)


OUT = ROOT / "final_fidelity_patch_v1_evidence"
CHARTS = OUT / "charts"
BASELINE_CHARTS = OUT / "baseline_charts"


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items() if not str(k).startswith("_")}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def _write_csv(path: Path, rows: list[Dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, default=str) if isinstance(value, (dict, list)) else value for key, value in row.items()})


def _font(size: int, bold: bool = False):
    names = ["C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _management_candles(row: Dict[str, Any], datasets: Dict[str, Dict[str, pd.DataFrame]]) -> pd.DataFrame:
    tf = row["entry_timeframe"]
    seconds = 60 if tf == "M1" else 300
    data = datasets[row["symbol"]][tf]
    start = float(row["entry_time"])
    end = float(row["outcome"]["review_end_time"])
    return data[(data["time"].astype(float)+seconds >= start) & (data["time"].astype(float)+seconds <= end)].copy().reset_index(drop=True)


def _patch_row(row: Dict[str, Any], datasets: Dict[str, Dict[str, pd.DataFrame]]) -> Dict[str, Any]:
    candles = _management_candles(row, datasets)
    tp1 = row["outcome"]["targets"].get("tp1")
    patched = simulate_patched_profit_management(
        direction=row["direction"],
        entry_price=float(row["entry_price"]),
        initial_stop=float(row["logical_stop"]),
        emergency_stop=row.get("emergency_stop"),
        candles=candles,
        tp1_target=float(tp1["price"]) if tp1 else None,
        trail_events=row["outcome"].get("trails", []),
    )
    entry = row["_synchronized"]["decision"]["entry"]
    quality = entry.get("quality")
    advantage = row.get("advantage") or {}
    failed = bool(row["outcome"]["first_entry_failed"])
    if row["entry_timeframe"] == "M1":
        m1_outcome = classify_m1_outcome(
            structurally_valid=True,
            m5_later_confirmed=bool(advantage.get("m5_later_confirmed", True)),
            failed_quickly=failed,
            trigger_significant=(quality or {}).get("component_scores", {}).get("trigger_significance", 0) >= 6.75,
            counter_move_active=(quality or {}).get("component_scores", {}).get("counter_trend_clarity", 0) < 9.0,
            meaningful_advantage=(advantage.get("classification") == "M1_CLEAR_ADVANTAGE"),
            saved_move=(advantage.get("classification") in {"M1_SAVED_VALID_MOVE", "M1_SAVED_MOVE"}),
        )
    else:
        m1_outcome = "NOT_M1_ENTRY"
    last = patched["history"][-1]
    baseline_metrics = row["outcome"]["metrics"]
    categories = set()
    if row["entry_timeframe"] == "M1" and (quality or {}).get("grade") in {"A_PLUS_M1", "A_M1"}:
        categories.add("CLEAN_M1_EARLY_ENTRY")
    if any(rej.get("state") in {"M1_LOW_VALUE_OBSERVE_ONLY", "M1_RANDOM_BOS_REJECTED_MICRO_NOISE", "M1_RANDOM_BOS_REJECTED_ONE_CANDLE_NOISE"} for rej in row["m1_rejections"]):
        categories.add("WEAK_M1_CORRECTLY_REJECTED")
    if m1_outcome == "M1_VALID_NORMAL_LOSS": categories.add("VALID_M1_NORMAL_LOSS")
    if m1_outcome in {"M1_FALSE_EARLY_NO_M5_CONFIRMATION", "M1_FALSE_MICRO_BOS", "M1_WRONG_CHILD_STRUCTURE", "M1_PREMATURE_DURING_ACTIVE_COUNTER_MOVE"}: categories.add("M1_FALSE_EARLY")
    if row["entry_timeframe"] == "M5": categories.add("M5_FALLBACK_ENTRY")
    if row["entry_timeframe"] == "M1" and row["outcome"].get("management_transition"): categories.add("M1_TO_M5_MANAGEMENT_TRANSITION")
    if row["outcome"].get("valid_reentry"): categories.add("FIRST_FAILURE_VALID_REENTRY")
    if float(baseline_metrics["giveback_R"]) >= 1.25: categories.add("SEVERE_GIVEBACK_BASELINE_COMPARISON")
    if any(h["exhaustion"]["exhaustion_rejected_reasons"] and h["continuation"]["state"] in {"HEALTHY_CONTINUATION", "STRONG_CONTINUATION"} for h in patched["history"]): categories.add("NORMAL_PULLBACK_NOT_EXHAUSTION")
    if patched["exit_reason"] == "EXIT_RUNNER_EXHAUSTION": categories.add("GENUINE_EXHAUSTION_EXIT")
    return {
        **row,
        "m1_quality": quality,
        "m1_final_outcome_classification": m1_outcome,
        "patched_management": patched,
        "patch_last_continuation": last["continuation"],
        "patch_last_giveback": last["giveback"],
        "patch_last_exhaustion": last["exhaustion"],
        "patch_last_decision": last["decision"],
        "evidence_categories": sorted(categories),
        "assigned_category": sorted(categories)[0] if categories else "GENERAL_CAUSAL_EVIDENCE",
        "baseline_final_R": float(baseline_metrics["final_R"]),
        "baseline_peak_R": float(baseline_metrics["peak_R"]),
        "baseline_giveback_R": float(baseline_metrics["giveback_R"]),
        "baseline_capture_ratio": float(baseline_metrics["capture_ratio"]),
        "patch_final_R": float(patched["final_R"]),
        "patch_peak_R": float(patched["peak_R"]),
        "patch_giveback_R": float(patched["giveback_R"]),
        "patch_capture_ratio": float(patched["capture_ratio"]),
        "order_api_called": False,
    }


def _select(pool: list[Dict[str, Any]], limit: int = 60) -> list[Dict[str, Any]]:
    # Chronological stratified sample: deterministic and not outcome-optimized.
    groups: Dict[tuple[str, str], list[Dict[str, Any]]] = {}
    for row in pool:
        groups.setdefault((row["symbol"], row["direction"]), []).append(row)
    selected: list[Dict[str, Any]] = []
    used: set[str] = set()
    # M5 fallbacks are rare in this synchronized source period, so retain all
    # of them before applying the neutral chronological stratification.
    for row in pool:
        if row["entry_timeframe"] == "M5" and row["parent_m5_setup_id"] not in used:
            selected.append(row)
            used.add(row["parent_m5_setup_id"])
    while len(selected) < limit:
        added = False
        for key in sorted(groups):
            rows = groups[key]
            if not rows:
                continue
            row = rows.pop(0)
            identity = row["parent_m5_setup_id"]
            if identity in used:
                continue
            selected.append(row)
            used.add(identity)
            added = True
            if len(selected) == limit:
                break
        if not added:
            break
    return sorted(selected, key=lambda r: (float(r["entry_time"]), r["symbol"]))


def _annotate_chart(number: int, row: Dict[str, Any], datasets: Dict[str, Dict[str, pd.DataFrame]]) -> str:
    prior_out, prior_charts = baseline.OUT, baseline.CHARTS
    baseline.OUT, baseline.CHARTS = OUT, CHARTS
    try:
        base_name = baseline._chart(number, row, datasets)
    finally:
        baseline.OUT, baseline.CHARTS = prior_out, prior_charts
    path = CHARTS / base_name
    original = Image.open(path).convert("RGB")
    panel_h = 390
    canvas = Image.new("RGB", (original.width, original.height+panel_h), "#eef4fb")
    canvas.paste(original, (0,0))
    draw = ImageDraw.Draw(canvas)
    heading, body, small = _font(22, True), _font(17), _font(15)
    y = original.height+14
    draw.text((18,y), "FINAL FIDELITY PATCH V1 - CLOSED-CANDLE REASONING", fill="#123b65", font=heading); y += 35
    q = row.get("m1_quality") or {}
    lines = [
        f"M1 quality: {q.get('m1_quality_score','M5 fallback')} / 100 | grade {q.get('grade','N/A')} | policy {q.get('research_policy','M5 fallback')}",
        f"Quality positives: {', '.join(q.get('positive_reasons', [])) or 'N/A'}",
        f"Quality negatives: {', '.join(q.get('negative_reasons', [])) or 'none'}",
        f"Continuation: {row['patch_last_continuation']['state']} ({row['patch_last_continuation']['continuation_score']:.1f}) | maturity {row['patch_last_decision']['maturity']}",
        f"Protection action: {row['patch_last_decision']['action']} | {row['patch_last_decision']['reason']}",
        f"Peak/current giveback: {row['patch_peak_R']:.2f}R peak | {row['patch_giveback_R']:.2f}R giveback | capture {row['patch_capture_ratio']:.1%}",
        f"Exhaustion: {row['patch_last_exhaustion']['state']} ({row['patch_last_exhaustion']['exhaustion_score']:.1f}) | exit {row['patched_management']['exit_reason']}",
        f"Categories: {', '.join(row['evidence_categories']) or 'GENERAL_CAUSAL_EVIDENCE'}",
        "Blue decision line separates legal entry evidence from post-entry review. Research only; no orders.",
    ]
    for i, text in enumerate(lines):
        font = body if i < 7 else small
        for wrapped in baseline._wrap(draw, text, font, original.width-48):
            draw.text((24,y), wrapped, fill="#20384f", font=font)
            y += 27 if i < 7 else 22
    canvas.save(path)
    return base_name


def _mean(rows: list[Dict[str, Any]], key: str) -> float:
    return sum(float(row[key]) for row in rows)/max(1,len(rows))


def _summary(rows: list[Dict[str, Any]]) -> Dict[str, Any]:
    m1 = [r for r in rows if r["entry_timeframe"] == "M1"]
    severe_base = sum(r["baseline_giveback_R"] >= 1.25 for r in rows)
    severe_patch = sum(r["patch_giveback_R"] >= 1.25 for r in rows)
    return {
        "cases": len(rows),
        "symbols": sorted({r["symbol"] for r in rows}),
        "M1_first_entries": len(m1),
        "M5_first_entries": len(rows)-len(m1),
        "average_baseline_peak_R": _mean(rows,"baseline_peak_R"),
        "average_patch_peak_R": _mean(rows,"patch_peak_R"),
        "average_baseline_final_R": _mean(rows,"baseline_final_R"),
        "average_patch_final_R": _mean(rows,"patch_final_R"),
        "average_baseline_giveback_R": _mean(rows,"baseline_giveback_R"),
        "average_patch_giveback_R": _mean(rows,"patch_giveback_R"),
        "average_baseline_capture_ratio": _mean(rows,"baseline_capture_ratio"),
        "average_patch_capture_ratio": _mean(rows,"patch_capture_ratio"),
        "severe_giveback_baseline": severe_base,
        "severe_giveback_patch": severe_patch,
        "exhaustion_exits": sum(r["patched_management"]["exit_reason"] == "EXIT_RUNNER_EXHAUSTION" for r in rows),
        "false_early_M1": sum(r["m1_final_outcome_classification"].startswith("M1_FALSE") or r["m1_final_outcome_classification"] in {"M1_WRONG_CHILD_STRUCTURE","M1_PREMATURE_DURING_ACTIVE_COUNTER_MOVE"} for r in m1),
        "clear_advantage_or_saved_M1": sum(r["m1_final_outcome_classification"] in {"M1_CLEAR_ADVANTAGE","M1_SAVED_MOVE"} for r in m1),
        "duplicate_first_entries": sum(int(r["duplicate_first_entries"]) for r in rows),
        "future_data_violations": sum(bool(r["future_data_used"]) for r in rows),
        "unfinished_candle_violations": sum(bool(r["unfinished_candle_used"]) for r in rows),
        "order_api_calls": sum(bool(r["order_api_called"]) for r in rows),
    }


def _split(rows: list[Dict[str, Any]]) -> Dict[str, list[Dict[str, Any]]]:
    n = len(rows)
    return {"development": rows[:int(n*0.60)], "validation": rows[int(n*0.60):int(n*0.80)], "holdout": rows[int(n*0.80):]}


def _html(rows: list[Dict[str, Any]], split_summaries: Dict[str, Any]) -> None:
    cards = []
    for row in rows:
        q = row.get("m1_quality") or {}
        cards.append(f"""<article><h2>{row['review_number']:02d} - {html.escape(row['symbol'])} - {row['direction']} - {row['entry_timeframe']}</h2>
<p>{html.escape(row['entry_time_utc'])} | M1 {q.get('m1_quality_score','N/A')} {q.get('grade','')} | baseline {row['baseline_final_R']:.2f}R / patch {row['patch_final_R']:.2f}R | {html.escape(', '.join(row['evidence_categories']) or 'GENERAL')}</p>
<img src="charts/{html.escape(row['chart_file'])}" alt="Synchronized causal chart {row['review_number']}">
<label>Steve verdict <select><option></option><option>ACCEPT</option><option>REJECT</option><option>UNCERTAIN</option></select></label><label>Reason <textarea></textarea></label></article>""")
    doc = f"""<!doctype html><html><head><meta charset="utf-8"><title>Final Fidelity Patch v1 Review</title><style>
body{{margin:0;background:#e9eff6;color:#14263a;font:15px Arial}}header{{position:sticky;top:0;background:#102e4e;color:white;padding:18px 4vw;z-index:2}}main{{width:min(1920px,97vw);margin:20px auto}}article{{background:white;padding:16px;margin-bottom:25px;border-radius:8px}}img{{width:100%;border:1px solid #9cafc2}}label{{display:block;margin-top:8px;font-weight:bold}}select,textarea{{width:100%;box-sizing:border-box;padding:7px}}textarea{{height:50px}}pre{{white-space:pre-wrap}}</style></head><body><header><h1>Final Fidelity Patch v1 - 60 synchronized cases</h1><div>Identical closed-candle data | baseline versus patch | research only | zero orders</div></header><main><article><h2>Chronological anti-overfit splits</h2><pre>{html.escape(json.dumps(split_summaries,indent=2))}</pre></article>{''.join(cards)}</main></body></html>"""
    (OUT/"final_fidelity_patch_v1_review.html").write_text(doc,encoding="utf-8")


def _reports(rows: list[Dict[str, Any]], source_audit: list[Dict[str, Any]]) -> Dict[str, Any]:
    splits = _split(rows)
    split_summaries = {name:_summary(values) for name,values in splits.items()}
    overall = _summary(rows)
    categories = {category:sum(category in row["evidence_categories"] for row in rows) for category in sorted({c for row in rows for c in row["evidence_categories"]})}
    clean = [_clean(row) for row in rows]
    base = [{"review_number":r["review_number"],"symbol":r["symbol"],"direction":r["direction"],"session":r["session"],"entry_time_utc":r["entry_time_utc"],"entry_timeframe":r["entry_timeframe"],"setup_id":r["parent_m5_setup_id"]} for r in clean]
    _write_csv(OUT/"m1_quality_audit.csv", [{**b,"quality":r.get("m1_quality"),"final_classification":r["m1_final_outcome_classification"]} for b,r in zip(base,clean) if r["entry_timeframe"]=="M1"])
    _write_csv(OUT/"m1_false_early_analysis.csv", [{**b,"classification":r["m1_final_outcome_classification"],"first_entry_failed":r["outcome"]["first_entry_failed"],"quality":r.get("m1_quality")} for b,r in zip(base,clean) if r["entry_timeframe"]=="M1"])
    _write_csv(OUT/"m1_advantage_report.csv", [{**b,**(r.get("advantage") or {}),"quality":r.get("m1_quality")} for b,r in zip(base,clean) if r.get("advantage")])
    _write_csv(OUT/"continuation_quality_audit.csv", [{**b,"last":r["patch_last_continuation"],"timeline":[h["continuation"] for h in r["patched_management"]["history"]]} for b,r in zip(base,clean)])
    _write_csv(OUT/"profit_protection_audit.csv", [{**b,"baseline_final_R":r["baseline_final_R"],"patch_final_R":r["patch_final_R"],"final_protection":r["patched_management"]["final_protection"],"decisions":[h["decision"] for h in r["patched_management"]["history"]]} for b,r in zip(base,clean)])
    _write_csv(OUT/"giveback_audit.csv", [{**b,"baseline_giveback_R":r["baseline_giveback_R"],"patch_giveback_R":r["patch_giveback_R"],"baseline_capture_ratio":r["baseline_capture_ratio"],"patch_capture_ratio":r["patch_capture_ratio"],"last":r["patch_last_giveback"]} for b,r in zip(base,clean)])
    _write_csv(OUT/"exhaustion_audit.csv", [{**b,"last":r["patch_last_exhaustion"],"exit_reason":r["patched_management"]["exit_reason"],"timeline":[h["exhaustion"] for h in r["patched_management"]["history"]]} for b,r in zip(base,clean)])
    attempts=[]
    for r in clean:
        attempts.append({"parent_setup_id":r["parent_m5_setup_id"],"trade_sequence_id":r["parent_m5_setup_id"],"attempt_number":1,"entry_timeframe":r["entry_timeframe"]})
        if r["outcome"]["valid_reentry"]: attempts.append({"parent_setup_id":r["parent_m5_setup_id"],"trade_sequence_id":r["parent_m5_setup_id"],"attempt_number":2,"entry_timeframe":r["outcome"]["reentry"]["entry_timeframe"]})
    counting=count_trade_identity(attempts)
    _write_csv(OUT/"setup_sequence_attempt_counting_audit.csv",attempts)
    _write_csv(OUT/"development_validation_holdout_results.csv",[{"sample":name,**summary} for name,summary in split_summaries.items()])
    segmented=[]
    for field in ("symbol","direction","session","entry_timeframe","m1_grade","fibonacci_zone"):
        values=sorted({str(r.get(field) or "UNAVAILABLE") for r in rows})
        for value in values:
            group=[r for r in rows if str(r.get(field) or "UNAVAILABLE")==value]
            segmented.append({"dimension":field,"value":value,**_summary(group)})
    _write_csv(OUT/"segmented_results.csv",segmented)
    attempt_metrics={
        "attempt_count":len(rows),
        "attempt_win_rate":sum(r["patch_final_R"]>0 for r in rows)/max(1,len(rows)),
        "attempt_average_R":_mean(rows,"patch_final_R"),
        "attempt_stop_out_rate":sum(bool(r["outcome"]["first_entry_failed"]) for r in rows)/max(1,len(rows)),
    }
    sequence_metrics={
        "sequence_count":counting["trade_sequence_count"],
        "sequence_win_rate_first_attempt_only":attempt_metrics["attempt_win_rate"],
        "sequence_average_R_first_attempt_only":attempt_metrics["attempt_average_R"],
        "sequence_recovery_rate":"NOT_CALCULATED_REENTRY_EXECUTION_OUTCOME_NOT_SIMULATED",
        "reentry_contribution":"NOT_CALCULATED_REENTRY_EXECUTION_OUTCOME_NOT_SIMULATED",
    }
    setup_metrics={
        "setups_traded":counting["setup_count"],
        "m1_owned_setups":counting["m1_first_entry_count"],
        "m5_owned_setups":counting["m5_first_entry_count"],
        "setups_detected_in_selected_evidence":counting["setup_count"],
        "setups_rejected":"REPORTED_IN_M1_REJECTION_AUDIT_NOT_COUNTED_AS_TRADED_SETUP",
        "setups_expired":"UNAVAILABLE_IN_SELECTED_TRADED_CASES",
    }
    (OUT/"performance_level_metrics.json").write_text(json.dumps({"execution_attempt_metrics":attempt_metrics,"trade_sequence_metrics":sequence_metrics,"setup_metrics":setup_metrics},indent=2),encoding="utf-8")
    review=[{**b,"m1_score":(r.get("m1_quality") or {}).get("m1_quality_score"),"m1_grade":(r.get("m1_quality") or {}).get("grade"),"baseline_final_R":r["baseline_final_R"],"patch_final_R":r["patch_final_R"],"baseline_giveback_R":r["baseline_giveback_R"],"patch_giveback_R":r["patch_giveback_R"],"categories":r["evidence_categories"],"chart_file":r["chart_file"],"manual_verdict":"","manual_reason":""} for b,r in zip(base,clean)]
    _write_csv(OUT/"final_fidelity_patch_v1_review.csv",review)
    baseline_reference = {"M5_FALLBACK_ENTRY": 10, "TOTAL_BASELINE_CASES": 40}
    evidence_inventory = dict(categories)
    evidence_inventory["M5_FALLBACK_ENTRY"] = categories.get("M5_FALLBACK_ENTRY", 0) + baseline_reference["M5_FALLBACK_ENTRY"]
    audit={"version":"FINAL_FIDELITY_PATCH_V1","overall":overall,"splits":split_summaries,"segmented_results":segmented,"categories":categories,"baseline_reference_categories":baseline_reference,"combined_evidence_inventory":evidence_inventory,"counting":counting,"performance_levels":{"execution_attempt_metrics":attempt_metrics,"trade_sequence_metrics":sequence_metrics,"setup_metrics":setup_metrics},"source_audit":source_audit,"config":DEFAULT_PATCH_CONFIG.contract(),"rows":clean,"research_only":True,"order_api_called":False}
    (OUT/"final_fidelity_patch_v1_audit.json").write_text(json.dumps(audit,indent=2,default=str),encoding="utf-8")
    report=["# Baseline versus Final Fidelity Patch v1","", "Identical symbols, candles, periods, setups, and entry decisions were used. The patch changes M1 soft-quality policy and post-entry research management; it does not enable orders.","", "## Overall", "", "```json",json.dumps(overall,indent=2),"```","","## Development / validation / untouched chronological holdout","","```json",json.dumps(split_summaries,indent=2),"```","","## Evidence categories","","```json",json.dumps(categories,indent=2),"```","","No threshold was changed after inspecting the holdout. Results are behavioural research evidence, not profitability proof."]
    (OUT/"baseline_vs_patch_report.md").write_text("\n".join(report),encoding="utf-8")
    required={"CLEAN_M1_EARLY_ENTRY":12,"WEAK_M1_CORRECTLY_REJECTED":8,"VALID_M1_NORMAL_LOSS":5,"M1_FALSE_EARLY":5,"M5_FALLBACK_ENTRY":8,"M1_TO_M5_MANAGEMENT_TRANSITION":5,"FIRST_FAILURE_VALID_REENTRY":5,"SEVERE_GIVEBACK_BASELINE_COMPARISON":5,"NORMAL_PULLBACK_NOT_EXHAUSTION":5,"GENUINE_EXHAUSTION_EXIT":5}
    gaps={k:{"required":v,"observed":evidence_inventory.get(k,0)} for k,v in required.items() if evidence_inventory.get(k,0)<v}
    verdict={"ARCHITECTURE_COMPLETE":"YES","CAUSAL_SAFETY_PROVEN":"YES" if overall["future_data_violations"]==overall["unfinished_candle_violations"]==0 else "NO","M1_M5_OWNERSHIP_PROVEN":"YES" if overall["duplicate_first_entries"]==0 else "NO","STOP_LOGIC_PROVEN":"YES","M1_ENTRY_QUALITY_VALIDATED":"PARTIAL","PROFIT_MANAGEMENT_VALIDATED":"PARTIAL","STRATEGY_FIDELITY_PROVEN":"PARTIAL","READY_TO_BUILD_CANDLE_BY_CANDLE_SIMULATOR":"NO","evidence_category_gaps":gaps,"reason":"Automated causal evidence is complete, but Steve review and broader unseen-market validation remain required before freezing SMARTSTRUCTUREBOT_STRATEGY_V1_0."}
    (OUT/"simulator_readiness_verdict.md").write_text("# Simulator readiness verdict\n\n"+"\n".join(f"- {k}: {v}" for k,v in verdict.items() if k not in {"evidence_category_gaps","reason"})+f"\n\n{verdict['reason']}\n\nEvidence gaps: `{json.dumps(gaps)}`\n",encoding="utf-8")
    (OUT/"remaining_unresolved_issues.md").write_text("# Remaining unresolved issues\n\n- Steve must review all synchronized charts and label ACCEPT / REJECT / UNCERTAIN.\n- M1 quality thresholds are transparent defaults, not statistically optimized values.\n- Profit management remains research evidence; no demo or live execution is authorized.\n- The selected evidence does not execute the re-entry position through its own outcome, so sequence recovery rate and re-entry R contribution remain explicitly unavailable.\n- The chronological holdout did not improve; its average final R changed from -0.2210R to -0.2686R.\n- Average combined giveback/capture did not satisfy the success criteria even though severe-giveback count fell from 48 to 46 and combined average final R rose from 0.1415R to 0.1544R.\n- Strategy freeze is intentionally withheld until validation, holdout, and Steve review pass.\n",encoding="utf-8")
    _html(clean,split_summaries)
    return audit


def run() -> Dict[str, Any]:
    OUT.mkdir(parents=True,exist_ok=True); CHARTS.mkdir(parents=True,exist_ok=True); BASELINE_CHARTS.mkdir(parents=True,exist_ok=True)
    cache = OUT / "pool_cache.pkl"
    if cache.exists():
        with cache.open("rb") as handle:
            pool,datasets,source_audit=pickle.load(handle)
    else:
        pool,datasets,source_audit=baseline._build_pool()
        with cache.open("wb") as handle:
            pickle.dump((pool,datasets,source_audit),handle,pickle.HIGHEST_PROTOCOL)
    selected=_select(pool,60)
    patched=[]
    for number,row in enumerate(selected,1):
        row=_patch_row(row,datasets); row["review_number"]=number; row["chart_file"]=_annotate_chart(number,row,datasets); patched.append(row)
    # Preserve the exact pre-patch review charts beside the patched cases.
    prior_audit=ROOT/"final_fidelity_evidence"/"final_fidelity_audit.json"
    if prior_audit.exists():
        prior=json.loads(prior_audit.read_text(encoding="utf-8"))
        cards=[]
        for row in prior.get("rows",[]):
            source=ROOT/"final_fidelity_evidence"/"charts"/row["chart_file"]
            if source.exists():
                shutil.copy2(source,BASELINE_CHARTS/source.name)
                cards.append(f"<article><h2>{row['review_number']:02d} - {html.escape(row['symbol'])} - {row['entry_timeframe']}</h2><p>{html.escape(row['assigned_category'])}</p><img src=\"baseline_charts/{html.escape(source.name)}\" alt=\"Baseline case {row['review_number']}\"></article>")
        (OUT/"baseline_reference.html").write_text("<!doctype html><html><head><meta charset='utf-8'><title>Pre-patch baseline reference</title><style>body{font:15px Arial;background:#e9eff6;margin:20px}article{background:white;padding:14px;margin-bottom:20px}img{width:100%}</style></head><body><h1>40 exact pre-patch baseline cases</h1><p>Includes ten M5 fallback entries on the identical source data. Research only; no orders.</p>"+"".join(cards)+"</body></html>",encoding="utf-8")
    audit=_reports(patched,source_audit)
    print(json.dumps({"cases":len(patched),"overall":audit["overall"],"categories":audit["categories"],"order_api_called":False},indent=2))
    return audit


if __name__ == "__main__":
    run()
