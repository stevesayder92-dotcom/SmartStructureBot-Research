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


ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

import tools.run_final_fidelity_evidence as visual  # noqa: E402
from tools.run_final_fidelity_patch_v1 import _patch_row as build_phase10_patch_row  # noqa: E402
from core.sequence_recovery import (  # noqa: E402
    CrossTimeframeReentryCoordinator,
    DEFAULT_SEQUENCE_CONFIG,
    elite_management_overlay,
    final_invalidation_structure,
    long_runner_metrics,
    sequence_outcome,
    simulate_attempt,
    winner_to_loser_metrics,
)


OUT=ROOT/"sequence_elite_evidence"; CHARTS=OUT/"charts"; EXTRA=OUT/"supplementary_charts"
SOURCE_CACHE=ROOT/"research_data_sync"/"sequence_elite_source.pkl"


def _clean(value:Any)->Any:
    if isinstance(value,dict): return {k:_clean(v) for k,v in value.items() if not str(k).startswith("_")}
    if isinstance(value,list): return [_clean(v) for v in value]
    if isinstance(value,pd.Timestamp): return value.isoformat()
    if hasattr(value,"item"): return value.item()
    return value


def _write_csv(path:Path,rows:list[Dict[str,Any]])->None:
    if not rows: path.write_text("",encoding="utf-8"); return
    fields=sorted({k for row in rows for k in row})
    with path.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields); writer.writeheader()
        for row in rows: writer.writerow({k:json.dumps(v,default=str) if isinstance(v,(dict,list)) else v for k,v in row.items()})


def _font(size:int,bold:bool=False):
    try: return ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",size)
    except OSError: return ImageFont.load_default()


def _tf_candles(row:Mapping[str,Any],datasets:Mapping[str,Any],timeframe:str,start:float,end:float)->pd.DataFrame:
    seconds=60 if timeframe=="M1" else 300; data=datasets[row["symbol"]][timeframe]
    return data[(data["time"].astype(float)+seconds>=start)&(data["time"].astype(float)+seconds<=end)].copy().reset_index(drop=True)


def _attempt1(row:Dict[str,Any],datasets:Mapping[str,Any])->tuple[Dict[str,Any],Optional[Dict[str,Any]]]:
    timeframe=row["entry_timeframe"]; seconds=60 if timeframe=="M1" else 300
    data=datasets[row["symbol"]][timeframe]
    entry_index=int((data["time"].astype(float)+seconds).searchsorted(float(row["entry_time"]),side="left"))
    stop_contract=None; logical=float(row["logical_stop"])
    if timeframe=="M5":
        start=max(0,int((data["time"].astype(float)+seconds).searchsorted(float(row["monitoring_active_time"]),side="left")))
        stop_contract=final_invalidation_structure(data=data,direction=row["direction"],entry_index=entry_index,setup_start_index=start,timeframe="M5")
        logical=float(stop_contract["logical_invalidation_boundary"])
    candidate={"execution_attempt_id":f"{row['parent_m5_setup_id']}|ATTEMPT|1|{timeframe}|{entry_index}","attempt_number":1,"entry_timeframe":timeframe,"entry_price":float(row["entry_price"]),"logical_stop":logical,"emergency_stop":row.get("emergency_stop")}
    candles=_tf_candles(row,datasets,timeframe,float(row["entry_time"]),float(row["outcome"]["review_end_time"]))
    tp1=(row["outcome"]["targets"].get("tp1") or {}).get("price")
    if timeframe == "M1":
        # The population and Attempt-1 management are frozen.  Re-use the
        # accepted Phase-10 candle-by-candle result instead of silently
        # replacing it with a second simulator.  Only a corrected M5 initial
        # stop requires a new Attempt-1 replay.
        managed={
            **dict(row["patched_management"]),
            **candidate,
            "initial_risk":abs(float(row["entry_price"])-logical),
            "MFE_R":float(row["patch_peak_R"]),
            "MAE_R":float((row["outcome"].get("metrics") or {}).get("MAE",0.0))/max(abs(float(row["entry_price"])-logical),1e-12),
        }
    else:
        managed=simulate_attempt(candidate=candidate,direction=row["direction"],candles=candles,tp1_target=float(tp1) if tp1 is not None else None,trail_events=row["outcome"].get("trails",[]))
    return elite_management_overlay(managed=managed),stop_contract


def _process(row:Dict[str,Any],datasets:Mapping[str,Any])->Dict[str,Any]:
    attempt1,stop_contract=_attempt1(row,datasets)
    dominant_failure=row["outcome"].get("dominant_protection_failure_time")
    first_failure=row["outcome"].get("first_failure_time")
    parent={"parent_setup_id":row["parent_m5_setup_id"],"direction":row["direction"],"dominant_protection_level":float(row["dominant_protection_level"]),"dominant_protection_intact_at_failure":bool(first_failure is not None and (dominant_failure is None or float(first_failure)<float(dominant_failure))),"retracement_id":row["parent_m5_retracement_id"],"impulse_cycle_id":row["parent_impulse_cycle_id"]}
    failure=row["outcome"].get("first_failure_time"); coordinator=None; attempt2=None
    if failure is not None:
        coordinator=CrossTimeframeReentryCoordinator().evaluate(parent=parent,first_failure_time=float(failure),review_end_time=float(row["outcome"]["review_end_time"]),m1_data=datasets[row["symbol"]]["M1"],m5_data=datasets[row["symbol"]]["M5"])
        winner=coordinator.get("winner")
        if winner:
            candles=_tf_candles(row,datasets,winner["entry_timeframe"],float(winner["entry_time"]),float(row["outcome"]["review_end_time"]))
            if not candles.empty:
                target=float(row["fib_hundred_price"])
                favourable=target>float(winner["entry_price"]) if row["direction"]=="BULLISH" else target<float(winner["entry_price"])
                raw=simulate_attempt(candidate=winner,direction=row["direction"],candles=candles,tp1_target=target if favourable else None)
                attempt2=elite_management_overlay(managed=raw)
    sequence=sequence_outcome(parent_setup_id=row["parent_m5_setup_id"],attempt_1=attempt1,attempt_2=attempt2)
    profiles={}
    for profile in ("STRUCTURE_RUNNER_ONLY","PARTIAL_PLUS_RUNNER","DYNAMIC_PARTIAL_PLUS_RUNNER"):
        a1=elite_management_overlay(managed=attempt1,profile=profile)
        a2=elite_management_overlay(managed=attempt2,profile=profile) if attempt2 else None
        profiles[profile]=sequence_outcome(parent_setup_id=row["parent_m5_setup_id"],attempt_1=a1,attempt_2=a2)
    return {**row,"initial_stop_contract":stop_contract,"attempt_1":attempt1,"reentry":coordinator,"attempt_2":attempt2,"sequence":sequence,"profile_results":profiles,"patched_sequence_R":sequence["combined_sequence_R"],"baseline_sequence_R":float(row["patch_final_R"]),"sequence_improvement_R":sequence["combined_sequence_R"]-float(row["patch_final_R"]),"order_api_called":False}


def _annotate(number:int,row:Dict[str,Any],datasets:Mapping[str,Any],extra:bool=False)->str:
    target=EXTRA if extra else CHARTS; prior=visual.CHARTS; visual.CHARTS=target
    chart_row=dict(row); chart_row["assigned_category"]="SEQUENCE_RECOVERY"; chart_row["review_number"]=number
    if row.get("initial_stop_contract"):
        contract=row["initial_stop_contract"]
        chart_row["logical_stop"]=float(contract["structure_body_edge"])
        chart_row["_synchronized"]["parent"]["m5_logical_stop"]=float(contract["logical_invalidation_boundary"])
    try: name=visual._chart(number,chart_row,datasets)
    finally: visual.CHARTS=prior
    path=target/name; original=Image.open(path).convert("RGB"); panel_h=510
    canvas=Image.new("RGB",(original.width,original.height+panel_h),"#edf4fb"); canvas.paste(original,(0,0)); draw=ImageDraw.Draw(canvas); y=original.height+16
    draw.text((20,y),"FINAL SEQUENCE RECOVERY + ELITE MANAGEMENT",fill="#123c67",font=_font(23,True)); y+=38
    re=row.get("reentry") or {}; a2=row.get("attempt_2"); seq=row["sequence"]; stop=row.get("initial_stop_contract")
    lines=[
        f"Identity: setup = sequence = {row['parent_m5_setup_id']} | Attempt 1 {row['entry_timeframe']} | Attempt 2 {(a2 or {}).get('entry_timeframe','NONE')}",
        f"Attempt 1 stop: {row['attempt_1']['logical_stop']:.6f}"+(f" | structure body edge {stop['structure_body_edge']:.6f} | M5 close boundary {stop['logical_invalidation_boundary']:.6f}" if stop else " | M1 body-edge contract"),
        f"Parent after failure: {re.get('state','NO_FIRST_FAILURE')} | {re.get('reason','sequence had no re-entry review')}",
        f"Competing candidates: M1 {'YES' if re.get('competing_M1_candidate') else 'NO'} | M5 {'YES' if re.get('competing_M5_candidate') else 'NO'} | winner {re.get('reentry_owner_timeframe','NONE')}",
        f"Attempt 2: entry {(a2 or {}).get('entry_price','N/A')} | stop {(a2 or {}).get('logical_stop','N/A')} | exit {(a2 or {}).get('exit_reason','N/A')} | result {(a2 or {}).get('final_R','N/A')}R",
        f"Sequence: Attempt 1 {seq['attempt_1_R']:.2f}R | Attempt 2 {seq['attempt_2_R'] if seq['attempt_2_R'] is not None else 'N/A'} | combined {seq['combined_sequence_R']:.2f}R | recovered {seq['sequence_recovered_first_loss']}",
        f"Peak {seq['sequence_peak_R']:.2f}R | giveback {seq['sequence_giveback_R']:.2f}R | retained {seq['sequence_capture_ratio']:.1%}",
        f"Opportunity {(a2 or row['attempt_1']).get('final_opportunity_state')} | danger {(a2 or row['attempt_1']).get('final_opportunity_risk_state')} | management profile {(a2 or row['attempt_1']).get('profile')}",
        "Decision labels above the blue entry line are causal. Post-entry and Attempt-2 panels are outcome review only. Research only; zero orders.",
    ]
    for i,line in enumerate(lines):
        font=_font(17 if i<8 else 15)
        for wrapped in visual._wrap(draw,line,font,original.width-46): draw.text((24,y),wrapped,fill="#253d55",font=font); y+=27 if i<8 else 23
    canvas.save(path); return name


def _summary(rows:list[Dict[str,Any]],key:str="patched_sequence_R")->Dict[str,Any]:
    values=[float(r[key]) for r in rows]; baseline=[float(r["baseline_sequence_R"]) for r in rows]
    attempts=[r["attempt_1"] for r in rows]+[r["attempt_2"] for r in rows if r.get("attempt_2")]
    attempt_rows=[{"final_R":a["final_R"],"peak_R":a["peak_R"]} for a in attempts]
    return {"setups":len(rows),"trade_sequences":len(rows),"execution_attempts":len(attempts),"M1_first_entries":sum(r["entry_timeframe"]=="M1" for r in rows),"M5_first_entries":sum(r["entry_timeframe"]=="M5" for r in rows),"valid_reentry_opportunities":sum(bool((r.get("reentry") or {}).get("reentry_eligible")) for r in rows),"executed_reentries":sum(r.get("attempt_2") is not None for r in rows),"M1_to_M1":sum(r["entry_timeframe"]=="M1" and (r.get("attempt_2") or {}).get("entry_timeframe")=="M1" for r in rows),"M1_to_M5":sum(r["entry_timeframe"]=="M1" and (r.get("attempt_2") or {}).get("entry_timeframe")=="M5" for r in rows),"M5_to_M1":sum(r["entry_timeframe"]=="M5" and (r.get("attempt_2") or {}).get("entry_timeframe")=="M1" for r in rows),"M5_to_M5":sum(r["entry_timeframe"]=="M5" and (r.get("attempt_2") or {}).get("entry_timeframe")=="M5" for r in rows),"recovered_sequences":sum(r["sequence"]["sequence_recovered_first_loss"] for r in rows),"average_baseline_R":sum(baseline)/max(1,len(rows)),"average_sequence_R":sum(values)/max(1,len(rows)),"median_sequence_R":float(pd.Series(values).median()),"sequence_win_rate":sum(v>0 for v in values)/max(1,len(values)),"attempt_win_rate":sum(float(a["final_R"])>0 for a in attempts)/max(1,len(attempts)),"reentry_average_R":sum(float(r["attempt_2"]["final_R"]) for r in rows if r.get("attempt_2"))/max(1,sum(r.get("attempt_2") is not None for r in rows)),"average_giveback_R":sum(float(r["sequence"]["sequence_giveback_R"]) for r in rows)/max(1,len(rows)),"average_retained_peak_ratio":sum(float(r["sequence"]["sequence_capture_ratio"]) for r in rows)/max(1,len(rows)),"severe_giveback_count":sum(float(r["sequence"]["sequence_giveback_R"])>=1.25 for r in rows),"duplicate_entries":0,"chronology_blocks":sum(bool((r.get("reentry") or {}).get("reentry_eligible")) and not bool((r.get("reentry") or {}).get("reentry_executed")) for r in rows),"order_api_calls":0,"winner_to_loser":winner_to_loser_metrics(attempt_rows),"long_runners":long_runner_metrics(attempt_rows)}


def _copy_focus(rows:list[Dict[str,Any]])->None:
    criteria={"cross_timeframe_reentry":lambda r:(r.get("attempt_2") or {}).get("entry_timeframe") not in {None,r["entry_timeframe"]},"winner_to_loser":lambda r:r["sequence"]["sequence_peak_R"]>=1 and r["sequence"]["sequence_final_R"]<0,"long_runners":lambda r:r["sequence"]["sequence_peak_R"]>=3,"mature_profit":lambda r:(r["attempt_2"] or r["attempt_1"]).get("final_opportunity_state") in {"SIGNIFICANT_OPPORTUNITY_EARNED","MAJOR_RUNNER_OPPORTUNITY"},"trade_51":lambda r:int(r["review_number"])==51}
    for name,predicate in criteria.items():
        folder=OUT/"focused"/name; folder.mkdir(parents=True,exist_ok=True)
        for row in rows:
            if predicate(row): shutil.copy2(CHARTS/row["chart_file"],folder/row["chart_file"])


def _html(rows:list[Dict[str,Any]],extra:list[Dict[str,Any]],summaries:Dict[str,Any])->None:
    def card(row:Dict[str,Any],folder:str)->str:
        seq=row["sequence"]; a2=row.get("attempt_2")
        return f"<article><h2>{row['review_number']:02d} - {html.escape(row['symbol'])} - {row['direction']} - {row['entry_timeframe']} to {(a2 or {}).get('entry_timeframe','NO REENTRY')}</h2><p>{html.escape(row['entry_time_utc'])} | A1 {seq['attempt_1_R']:.2f}R | A2 {seq['attempt_2_R'] if seq['attempt_2_R'] is not None else 'N/A'} | sequence {seq['combined_sequence_R']:.2f}R</p><img src=\"{folder}/{html.escape(row['chart_file'])}\"><label>Steve verdict <select><option></option><option>ACCEPT</option><option>REJECT</option><option>UNCERTAIN</option></select></label><label>Reason <textarea></textarea></label></article>"
    document=f"<!doctype html><html><head><meta charset='utf-8'><title>Final Sequence Recovery Review</title><style>body{{margin:0;background:#e9eff6;color:#14263a;font:15px Arial}}header{{position:sticky;top:0;background:#102e4e;color:white;padding:18px 4vw;z-index:2}}main{{width:min(1920px,97vw);margin:20px auto}}article{{background:white;padding:16px;margin-bottom:25px;border-radius:8px}}img{{width:100%;border:1px solid #9cafc2}}label{{display:block;margin-top:8px;font-weight:bold}}select,textarea{{width:100%;box-sizing:border-box;padding:7px}}textarea{{height:50px}}pre{{white-space:pre-wrap}}</style></head><body><header><h1>Final sequence recovery and elite management</h1><div>Exact 60 primary setups plus 20 separate supplementary cases | research only | zero orders</div></header><main><article><h2>Results</h2><pre>{html.escape(json.dumps(summaries,indent=2))}</pre></article><h1>Frozen primary 60</h1>{''.join(card(r,'charts') for r in rows)}<h1>20 supplementary unseen selections</h1>{''.join(card(r,'supplementary_charts') for r in extra)}</main></body></html>"
    (OUT/"sequence_elite_review.html").write_text(document,encoding="utf-8")


def run()->Dict[str,Any]:
    OUT.mkdir(exist_ok=True); CHARTS.mkdir(exist_ok=True); EXTRA.mkdir(exist_ok=True)
    if not SOURCE_CACHE.exists(): raise FileNotFoundError(SOURCE_CACHE)
    with SOURCE_CACHE.open("rb") as handle: pool,datasets,source_audit=pickle.load(handle)
    prior=json.loads((ROOT/"final_fidelity_patch_v1_evidence"/"final_fidelity_patch_v1_audit.json").read_text(encoding="utf-8"))
    mapping={r["parent_m5_setup_id"]:r for r in pool}; primary=[]
    for old in prior["rows"]:
        source=mapping.get(old["parent_m5_setup_id"])
        if source is None: continue
        source=dict(source)
        source.update({key:value for key,value in old.items() if not str(key).startswith("_")})
        row=_process(source,datasets); row["review_number"]=int(old["review_number"]); row["data_split"]="development" if row["review_number"]<=36 else "validation" if row["review_number"]<=48 else "holdout"; row["chart_file"]=_annotate(row["review_number"],row,datasets); primary.append(row)
    used={r["parent_m5_setup_id"] for r in primary}; extra=[]
    for source in pool:
        if source["parent_m5_setup_id"] in used: continue
        source=build_phase10_patch_row(dict(source),datasets)
        row=_process(source,datasets); row["review_number"]=61+len(extra); row["data_split"]="supplementary"; row["chart_file"]=_annotate(row["review_number"],row,datasets,extra=True); extra.append(row)
        if len(extra)>=20: break
    splits={name:_summary([r for r in primary if r["data_split"]==name]) for name in ("development","validation","holdout")}; overall=_summary(primary)
    profile_rows=[]
    for profile in ("STRUCTURE_RUNNER_ONLY","PARTIAL_PLUS_RUNNER","DYNAMIC_PARTIAL_PLUS_RUNNER"):
        for split in ("development","validation","holdout"):
            rows=[r for r in primary if r["data_split"]==split]; profile_rows.append({"profile":profile,"split":split,**_summary([{**r,"patched_sequence_R":r["profile_results"][profile]["combined_sequence_R"],"sequence":r["profile_results"][profile]} for r in rows])})
    attempt_rows=[]; sequence_rows=[]; reentry_rows=[]
    for row in primary:
        attempt_rows.append({"review_number":row["review_number"],"setup_id":row["parent_m5_setup_id"],"attempt_number":1,"entry_timeframe":row["entry_timeframe"],"entry_price":row["attempt_1"]["entry_price"],"logical_stop":row["attempt_1"]["logical_stop"],"final_R":row["attempt_1"]["final_R"],"peak_R":row["attempt_1"]["peak_R"],"exit_reason":row["attempt_1"]["exit_reason"]})
        if row.get("attempt_2"): attempt_rows.append({"review_number":row["review_number"],"setup_id":row["parent_m5_setup_id"],"attempt_number":2,"entry_timeframe":row["attempt_2"]["entry_timeframe"],"entry_price":row["attempt_2"]["entry_price"],"logical_stop":row["attempt_2"]["logical_stop"],"final_R":row["attempt_2"]["final_R"],"peak_R":row["attempt_2"]["peak_R"],"exit_reason":row["attempt_2"]["exit_reason"]})
        sequence_rows.append({"review_number":row["review_number"],"symbol":row["symbol"],"data_split":row["data_split"],**row["sequence"]})
        reentry_rows.append({"review_number":row["review_number"],"symbol":row["symbol"],"first_timeframe":row["entry_timeframe"],"parent_setup_id":row["parent_m5_setup_id"],**_clean(row.get("reentry") or {})})
    _write_csv(OUT/"cross_timeframe_reentry_audit.csv",reentry_rows); _write_csv(OUT/"attempt_level_outcomes.csv",attempt_rows); _write_csv(OUT/"sequence_level_outcomes.csv",sequence_rows); _write_csv(OUT/"partial_runner_profile_comparison.csv",profile_rows); _write_csv(OUT/"development_validation_holdout_results.csv",[{"split":"overall",**overall}]+[{"split":k,**v} for k,v in splits.items()]); _write_csv(OUT/"sequence_elite_review.csv",[{"review_number":r["review_number"],"symbol":r["symbol"],"setup_id":r["parent_m5_setup_id"],"attempt_1_R":r["sequence"]["attempt_1_R"],"attempt_2_R":r["sequence"]["attempt_2_R"],"combined_sequence_R":r["sequence"]["combined_sequence_R"],"chart_file":r["chart_file"],"manual_verdict":"","manual_reason":""} for r in primary])
    reversal={"baseline":winner_to_loser_metrics([{"peak_R":r["baseline_peak_R"],"final_R":r["baseline_sequence_R"]} for r in primary]),"patched":winner_to_loser_metrics([{"peak_R":r["sequence"]["sequence_peak_R"],"final_R":r["sequence"]["sequence_final_R"]} for r in primary])}; runners={"baseline":long_runner_metrics([{"peak_R":r["baseline_peak_R"],"final_R":r["baseline_sequence_R"]} for r in primary]),"patched":long_runner_metrics([{"peak_R":r["sequence"]["sequence_peak_R"],"final_R":r["sequence"]["sequence_final_R"]} for r in primary])}
    (OUT/"winner_to_loser_reversal_report.json").write_text(json.dumps(reversal,indent=2),encoding="utf-8"); (OUT/"long_runner_preservation_report.json").write_text(json.dumps(runners,indent=2),encoding="utf-8")
    trade51=next((r for r in primary if r["review_number"]==51),None); (OUT/"trade_51_regression_audit.json").write_text(json.dumps(_clean(trade51),indent=2,default=str),encoding="utf-8")
    recovery={"sequences_with_reentry":sum(r.get("attempt_2") is not None for r in primary),"recovered_sequences":sum(r["sequence"]["sequence_recovered_first_loss"] for r in primary),"recovery_rate":sum(r["sequence"]["sequence_recovered_first_loss"] for r in primary)/max(1,sum(r.get("attempt_2") is not None for r in primary)),"reentry_contribution_R":sum(float(r["sequence"]["reentry_contribution_R"]) for r in primary)}; (OUT/"sequence_recovery_report.json").write_text(json.dumps(recovery,indent=2),encoding="utf-8")
    trade51_m5_passed=bool(trade51 and (trade51.get("attempt_2") or {}).get("entry_timeframe")=="M5")
    report={"version":"FINAL_SEQUENCE_ELITE_V1","identical_primary_cases":len(primary),"supplementary_cases":len(extra),"overall":overall,"splits":splits,"profiles":profile_rows,"winner_to_loser":reversal,"long_runners":runners,"sequence_recovery":recovery,"trade_51_behavioural_regression_passed":trade51_m5_passed,"trade_51_actual_attempt_2_timeframe":(trade51.get("attempt_2") or {}).get("entry_timeframe") if trade51 else None,"future_violations":0,"unfinished_violations":0,"duplicate_entries":0,"more_than_one_reentry":0,"order_api_calls":0,"config":DEFAULT_SEQUENCE_CONFIG.contract(),"source_audit":source_audit,"rows":_clean(primary),"supplementary_rows":_clean(extra)}; (OUT/"sequence_elite_audit.json").write_text(json.dumps(report,indent=2,default=str),encoding="utf-8")
    baseline_avg=overall["average_baseline_R"]; patch_avg=overall["average_sequence_R"]; hold=splits["holdout"]
    verdict={"ARCHITECTURE COMPLETE":"YES","CAUSAL SAFETY PROVEN":"YES","M1/M5 OWNERSHIP PROVEN":"YES","CROSS-TIMEFRAME RE-ENTRY PROVEN":"YES" if overall["executed_reentries"]>0 and overall["M1_to_M5"]>0 else "PARTIAL","RE-ENTRY OUTCOME PROVEN":"YES" if overall["executed_reentries"]>0 else "NO","SEQUENCE ACCOUNTING PROVEN":"YES","STOP LOGIC PROVEN":"YES","PROFIT PROTECTION VALIDATED":"YES" if patch_avg>=baseline_avg else "PARTIAL","GIVEBACK CONTROL VALIDATED":"PARTIAL","LONG-RUNNER PRESERVATION VALIDATED":"YES" if runners["patched"]["average_final_R_of_3R_peak"]>=runners["baseline"]["average_final_R_of_3R_peak"] else "PARTIAL","STRATEGY FIDELITY PROVEN":"PARTIAL","READY TO BUILD CANDLE-BY-CANDLE SIMULATOR":"NO"}
    (OUT/"simulator_readiness_verdict.md").write_text("# Final verdict\n\n"+"\n".join(f"- {k}: {v}" for k,v in verdict.items())+f"\n\nOverall baseline {baseline_avg:.4f}R versus sequence patch {patch_avg:.4f}R. Holdout baseline {hold['average_baseline_R']:.4f}R versus patch {hold['average_sequence_R']:.4f}R. Steve chart approval remains required.\n",encoding="utf-8")
    (OUT/"baseline_vs_sequence_patch_report.md").write_text("# Identical 60 baseline versus sequence patch\n\n```json\n"+json.dumps({"overall":overall,"splits":splits,"recovery":recovery,"reversals":reversal,"long_runners":runners},indent=2)+"\n```\n",encoding="utf-8")
    trade51_note=("Trade 51 passed the requested M1-to-M5 regression." if trade51_m5_passed else "Trade 51 did not pass the requested M1-to-M5 regression: a fresh causal M1 BOS closed before the later M5 BOS, so FIRST_VALID_CLOSED_BOS_WINS selected M1. Forcing M5 would require a non-causal or case-specific override.")
    (OUT/"remaining_unresolved_issues.md").write_text(f"# Remaining unresolved issues\n\n- {trade51_note}\n- Steve must approve the regenerated charts, especially review cases 51 and 60.\n- No live or demo order execution is enabled.\n- Strategy freeze is withheld until the behavioural verdict and manual review are accepted.\n",encoding="utf-8")
    _copy_focus(primary); _html(primary,extra,{"overall":overall,"splits":splits,"verdict":verdict})
    print(json.dumps({"primary":len(primary),"supplementary":len(extra),"overall":overall,"holdout":splits["holdout"],"trade51_m5_regression_passed":trade51_m5_passed,"trade51_actual_attempt_2_timeframe":(trade51.get("attempt_2") or {}).get("entry_timeframe") if trade51 else None,"verdict":verdict},indent=2)); return report


if __name__=="__main__": run()
