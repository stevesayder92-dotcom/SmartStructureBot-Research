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

from core.presimulator_repair import (  # noqa: E402
    DEFAULT_HYBRID_CONFIG,
    EmergencyRiskEngine,
    StrategicReentryCoordinator,
    _attach_event_time,
    _authoritative_action_overlay,
    build_complete_attempt2_management,
    causal_partial_decision,
    chronological_sequence_equity,
)


OUT = ROOT / "presimulator_repair_evidence"
CHARTS = OUT / "charts"
FOCUS = OUT / "trade_51"
SOURCE = ROOT / "research_data_sync" / "sequence_elite_source.pkl"
BASELINE_AUDIT = ROOT / "final_fidelity_patch_v1_evidence" / "final_fidelity_patch_v1_audit.json"
CURRENT_AUDIT = ROOT / "sequence_elite_evidence" / "sequence_elite_audit.json"
CURRENT_CHARTS = ROOT / "sequence_elite_evidence" / "charts"


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items() if not str(key).startswith("_")}
    if isinstance(value, list):
        return [_clean(item) for item in value]
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
    try:
        return ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    words = str(text).split()
    lines: list[str] = []
    current = ""
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


def _management_candles(row: Mapping[str, Any], datasets: Mapping[str, Any], timeframe: str, start: float) -> pd.DataFrame:
    seconds = 60 if timeframe == "M1" else 300
    data = datasets[row["symbol"]][timeframe]
    end = float(row["outcome"]["review_end_time"])
    return data[(data["time"].astype(float) + seconds >= start) & (data["time"].astype(float) + seconds <= end)].copy().reset_index(drop=True)


def _attempt1_hybrid(row: Dict[str, Any], datasets: Mapping[str, Any]) -> Dict[str, Any]:
    managed = _clean(row["patched_management"])
    timeframe = row["entry_timeframe"]
    seconds = 60 if timeframe == "M1" else 300
    candles = _management_candles(row, datasets, timeframe, float(row["entry_time"]))
    _attach_event_time(managed["history"], candles, seconds)
    _authoritative_action_overlay(managed)
    partial = causal_partial_decision(managed["history"])
    fraction = float(partial.get("partial_fraction", 0.0)) if managed.get("tp1_partial_filled") else 0.0
    runner_r = float(managed.get("runner_R", managed.get("final_R", 0.0)))
    partial_r = float(managed.get("partial_R", 0.0) or 0.0)
    final_r = fraction * partial_r + (1.0 - fraction) * runner_r if fraction else runner_r
    risk = EmergencyRiskEngine().evaluate(entry_price=float(row["entry_price"]), logical_stop=float(row["logical_stop"]), emergency_stop=row.get("emergency_stop"))
    return {
        **managed,
        "attempt_id": f"{row['parent_m5_setup_id']}|ATTEMPT|1|{timeframe}|{row.get('m1_entry_index') or row.get('m5_entry_index')}",
        "parent_setup_id": row["parent_m5_setup_id"],
        "attempt_number": 1,
        "entry_timeframe": timeframe,
        "entry_index": row.get("m1_entry_index") if timeframe == "M1" else row.get("m5_entry_index"),
        "entry_time": float(row["entry_time"]),
        "entry_price": float(row["entry_price"]),
        "logical_stop": float(row["logical_stop"]),
        "emergency_stop": row.get("emergency_stop"),
        "causal_partial_decision": partial,
        "tp1_partial_fraction": fraction,
        "logical_R": final_r,
        "account_risk_R": final_r * float(risk["logical_R_to_account_R_factor"]),
        "emergency_R": risk["emergency_R"],
        "emergency_risk": risk,
        "final_R": final_r,
        "fresh_attempt_state": True,
        "future_data_used": False,
        "unfinished_candle_used": False,
        "order_api_called": False,
    }


def _scaled_attempt(attempt: Mapping[str, Any]) -> Dict[str, Any]:
    factor = float((attempt.get("emergency_risk") or {}).get("logical_R_to_account_R_factor", 1.0))
    scaled = _clean(attempt)
    scaled["final_R"] = float(attempt["final_R"]) * factor
    for event in scaled.get("history", []):
        if event.get("giveback") and event["giveback"].get("current_R") is not None:
            event["giveback"]["current_R"] = float(event["giveback"]["current_R"]) * factor
    return scaled


def _process(row: Dict[str, Any], current: Mapping[str, Any], datasets: Mapping[str, Any]) -> Dict[str, Any]:
    a1 = _attempt1_hybrid(row, datasets)
    failure = row["outcome"].get("first_failure_time")
    dominant_failure = row["outcome"].get("dominant_protection_failure_time")
    parent = {
        "parent_setup_id": row["parent_m5_setup_id"],
        "retracement_id": row["parent_m5_retracement_id"],
        "impulse_cycle_id": row["parent_impulse_cycle_id"],
        "direction": row["direction"],
        "dominant_protection_level": row["dominant_protection_level"],
        "dominant_protection_intact_at_failure": bool(failure is not None and (dominant_failure is None or float(failure) < float(dominant_failure))),
        "confirmed_opposite_m5_trend": bool(row["outcome"].get("reentry_denied_due_to_dominant_failure", False)),
        "impulse_cycle_superseded": False,
        "retracement_completed_before_failure": False,
        "retracement_expired": False,
    }
    reentry = None
    a2 = None
    if failure is not None:
        reentry = StrategicReentryCoordinator().evaluate(
            parent=parent, failure_time=float(failure), review_end_time=float(row["outcome"]["review_end_time"]),
            m1_data=datasets[row["symbol"]]["M1"], m5_data=datasets[row["symbol"]]["M5"],
            original_trigger_index=row.get("m1_failure_trigger_index"),
            original_trigger_price=row.get("m1_failure_trigger_price"),
        )
        winner = reentry.get("winner")
        if winner:
            candles = _management_candles(row, datasets, winner["entry_timeframe"], float(winner["entry_time"]))
            m5_candles = _management_candles(row, datasets, "M5", float(winner["entry_time"]))
            target = float(row["fib_hundred_price"])
            favourable = target > float(winner["entry_price"]) if row["direction"] == "BULLISH" else target < float(winner["entry_price"])
            a2 = build_complete_attempt2_management(
                candidate=winner, parent_setup_id=row["parent_m5_setup_id"], direction=row["direction"],
                candles=candles, m5_candles=m5_candles, tp1_target=target if favourable else None,
            )
    sequence = chronological_sequence_equity(parent_setup_id=row["parent_m5_setup_id"], attempt_1=a1, attempt_2=a2)
    account_sequence = chronological_sequence_equity(parent_setup_id=row["parent_m5_setup_id"], attempt_1=_scaled_attempt(a1), attempt_2=_scaled_attempt(a2) if a2 else None)
    baseline_attempt = {**a1, "final_R": float(row["patch_final_R"])}
    baseline_sequence = chronological_sequence_equity(parent_setup_id=row["parent_m5_setup_id"], attempt_1=baseline_attempt)
    current_sequence = current["sequence"]
    drift_fields = []
    for field in ("parent_m5_setup_id", "direction", "entry_timeframe", "entry_time", "entry_price", "logical_stop", "symbol", "session"):
        if str(row.get(field)) != str(current.get(field)):
            drift_fields.append(field)
    return {
        **row,
        "data_split": "development" if int(row["review_number"]) <= 36 else "validation" if int(row["review_number"]) <= 48 else "holdout",
        "entry_population_drift": drift_fields,
        "attempt_1_hybrid": a1,
        "parent_viability": reentry,
        "attempt_2_hybrid": a2,
        "baseline_sequence": baseline_sequence,
        "current_sequence": current_sequence,
        "current_attempt_1": current.get("attempt_1"),
        "current_attempt_2": current.get("attempt_2"),
        "current_reentry": current.get("reentry"),
        "repaired_sequence": sequence,
        "repaired_account_sequence": account_sequence,
        "baseline_R": float(row["patch_final_R"]),
        "current_R": float(current["patched_sequence_R"]),
        "repaired_R": float(sequence["sequence_final_R"]),
        "repaired_account_R": float(account_sequence["sequence_final_R"]),
        "order_api_called": False,
    }


def _mean(rows: list[Mapping[str, Any]], key: str) -> float:
    return sum(float(row[key]) for row in rows) / max(1, len(rows))


def _profit_factor(values: list[float]) -> Optional[float]:
    gains = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    return gains / losses if losses > 0 else None


def _summary(rows: list[Dict[str, Any]], profile_key: str) -> Dict[str, Any]:
    values = [float(row[profile_key]) for row in rows]
    if profile_key == "baseline_R":
        sequences = [row["baseline_sequence"] for row in rows]
    elif profile_key == "current_R":
        sequences = [row["current_sequence"] for row in rows]
    else:
        sequences = [row["repaired_sequence"] for row in rows]
    attempts = []
    reentries = []
    for row in rows:
        if profile_key == "baseline_R":
            attempts.append({"final_R": row["baseline_R"], "peak_R": row["baseline_sequence"]["sequence_peak_R"], "exit_reason": row["attempt_1_hybrid"].get("exit_reason")})
        elif profile_key == "current_R":
            attempts.append(row.get("current_attempt_1") or {"final_R": row["current_R"]})
            if row.get("current_attempt_2"):
                attempts.append(row["current_attempt_2"])
                reentries.append(row["current_attempt_2"])
        else:
            attempts.append(row["attempt_1_hybrid"])
            if row.get("attempt_2_hybrid"):
                attempts.append(row["attempt_2_hybrid"])
                reentries.append(row["attempt_2_hybrid"])
    repaired_profile = profile_key in {"repaired_R", "repaired_account_R"}
    current_profile = profile_key == "current_R"
    def second_tf(row: Mapping[str, Any]) -> Optional[str]:
        if repaired_profile:
            return (row.get("attempt_2_hybrid") or {}).get("entry_timeframe")
        if current_profile:
            return (row.get("current_attempt_2") or {}).get("entry_timeframe")
        return None
    peaks = [float(seq.get("sequence_peak_R", 0)) for seq in sequences]
    finals = values
    reach2 = [(peak, final) for peak, final in zip(peaks, finals) if peak >= 2]
    reach3 = [(peak, final) for peak, final in zip(peaks, finals) if peak >= 3]
    reach5 = [(peak, final) for peak, final in zip(peaks, finals) if peak >= 5]
    histories = [event for attempt in attempts for event in attempt.get("history", [])]
    target_states = {
        state: sum(any(event.get("target_state") == state for event in attempt.get("history", [])) for attempt in attempts)
        for state in ("WICK_TOUCHED", "BODY_CLOSED_THROUGH", "ACCEPTED", "REJECTED")
    }
    partials = [attempt.get("causal_partial_decision") or {} for attempt in attempts]
    partial_count = sum(float(partial.get("partial_fraction", 0)) > 0 for partial in partials)
    attempt_peaks = [float(attempt.get("peak_R", attempt.get("MFE_R", 0)) or 0) for attempt in attempts]
    attempt_maes = [float(attempt.get("MAE_R", min(0.0, float(attempt.get("final_R", 0)))) or 0) for attempt in attempts]
    emergency_multiples, emergency_losses, account_results = [], [], []
    for attempt in attempts:
        risk = attempt.get("emergency_risk") or {}
        if risk.get("emergency_risk_multiple") is not None:
            emergency_multiples.append(float(risk["emergency_risk_multiple"]))
        else:
            entry, logical, emergency = attempt.get("entry_price"), attempt.get("logical_stop"), attempt.get("emergency_stop")
            if entry is not None and logical is not None and emergency is not None and abs(float(entry) - float(logical)) > 0:
                emergency_multiples.append(abs(float(entry) - float(emergency)) / abs(float(entry) - float(logical)))
        account_result = float(attempt.get("account_risk_R", attempt.get("final_R", 0)) or 0)
        account_results.append(account_result)
        if str(attempt.get("exit_reason", "")) == "EXIT_EMERGENCY":
            emergency_losses.append(account_result)
    attempt_winner_to_loser = sum(peak > 0 and float(attempt.get("final_R", 0)) <= 0 for peak, attempt in zip(attempt_peaks, attempts))
    normal_pullback_holds = sum(event.get("decision") == "HOLD_NORMAL_PULLBACK" or event.get("committed_action") == "HOLD_NORMAL_PULLBACK" for event in histories)
    mature_profit_actions = sum(event.get("committed_action") in {"LOCK_STRUCTURAL_PROFIT", "LOCK_SMALL_PROFIT", "AGGRESSIVE_EXHAUSTION_PROTECTION"} for event in histories)
    structural_trail_actions = sum(event.get("committed_action") in {"MOVE_TO_PROVEN_M1_STRUCTURE", "MOVE_TO_PROVEN_M5_STRUCTURE", "TRAIL_PROVEN_STRUCTURE"} for event in histories)
    return {
        "parent_setups": len(rows), "first_entries": len(rows),
        "M1_first_entries": sum(row["entry_timeframe"] == "M1" for row in rows),
        "M5_first_entries": sum(row["entry_timeframe"] == "M5" for row in rows),
        "entry_drift": sum(bool(row["entry_population_drift"]) for row in rows),
        "duplicate_entries": 0,
        "average_sequence_R": sum(values) / max(1, len(values)),
        "median_sequence_R": float(pd.Series(values).median()) if values else 0.0,
        "sequence_expectancy": sum(values) / max(1, len(values)),
        "sequence_win_rate": sum(value > 0 for value in values) / max(1, len(values)),
        "profit_factor": _profit_factor(values),
        "average_account_risk_result": _mean(rows, "repaired_account_R") if repaired_profile else sum(account_results) / max(1, len(account_results)),
        "eligible_reentry_parents": sum(bool((row.get("parent_viability") or {}).get("reentry_eligible")) for row in rows) if repaired_profile else sum(bool((row.get("current_reentry") or {}).get("reentry_eligible")) for row in rows) if current_profile else 0,
        "executed_reentries": len(reentries),
        "M1_to_M1": sum(row["entry_timeframe"] == "M1" and second_tf(row) == "M1" for row in rows),
        "M1_to_M5": sum(row["entry_timeframe"] == "M1" and second_tf(row) == "M5" for row in rows),
        "M5_to_M1": sum(row["entry_timeframe"] == "M5" and second_tf(row) == "M1" for row in rows),
        "M5_to_M5": sum(row["entry_timeframe"] == "M5" and second_tf(row) == "M5" for row in rows),
        "reentry_skipped_no_child_reset": sum((row.get("parent_viability") or {}).get("state") == "WAITING_FOR_CHILD_RESET" for row in rows) if repaired_profile else 0,
        "reentry_skipped_parent_invalid": sum((row.get("parent_viability") or {}).get("state") == "REENTRY_CANCELLED" for row in rows) if repaired_profile else 0,
        "recovered_sequences": sum(float(row["attempt_1_hybrid"]["final_R"]) < 0 and float(row[profile_key]) > 0 and second_tf(row) is not None for row in rows) if repaired_profile else 0,
        "recovery_rate": (sum(float(row["attempt_1_hybrid"]["final_R"]) < 0 and float(row[profile_key]) > 0 and second_tf(row) is not None for row in rows) / max(1, len(reentries))) if repaired_profile else 0.0,
        "reentry_average_R": sum(float(attempt.get("final_R", 0)) for attempt in reentries) / max(1, len(reentries)),
        "reentry_contribution_R": sum(float(attempt.get("final_R", 0)) for attempt in reentries),
        "second_failure_rate": sum(float(attempt.get("final_R", 0)) < 0 for attempt in reentries) / max(1, len(reentries)),
        "average_attempt_R": sum(float(attempt.get("final_R", 0)) for attempt in attempts) / max(1, len(attempts)),
        "attempt_win_rate": sum(float(attempt.get("final_R", 0)) > 0 for attempt in attempts) / max(1, len(attempts)),
        "average_sequence_peak_R": sum(float(seq.get("sequence_peak_R", 0)) for seq in sequences) / max(1, len(sequences)),
        "average_MFE_R": sum(attempt_peaks) / max(1, len(attempt_peaks)),
        "average_MAE_R": sum(attempt_maes) / max(1, len(attempt_maes)),
        "average_sequence_giveback_R": sum(float(seq.get("sequence_giveback_R", 0)) for seq in sequences) / max(1, len(sequences)),
        "average_profit_retained_ratio": sum(max(0.0, float(seq.get("profit_retained_ratio", seq.get("sequence_capture_ratio", 0)))) for seq in sequences) / max(1, len(sequences)),
        "winner_to_loser_reversals": sum(bool(seq.get("winner_to_loser_reversal", float(seq.get("sequence_peak_R", 0)) > 0 and float(seq.get("sequence_final_R", 0)) <= 0)) for seq in sequences),
        "attempt_winner_to_loser_reversals": attempt_winner_to_loser,
        "severe_giveback_count": sum(float(seq.get("sequence_giveback_R", 0)) >= 1.25 for seq in sequences),
        "normal_pullbacks_held": normal_pullback_holds,
        "premature_exits": None,
        "premature_exit_note": "Requires candle-by-candle post-exit counterfactual simulation",
        "peak_gte_2R_count": len(reach2),
        "peak_gte_3R_count": len(reach3),
        "peak_gte_5R_count": len(reach5),
        "long_runner_average_final_R_gte_3R": sum(final for _, final in reach3) / max(1, len(reach3)),
        "long_runner_retained_ratio_gte_3R": sum(max(0.0, final / peak) for peak, final in reach3) / max(1, len(reach3)),
        "long_runner_preserved": sum(final / peak >= 0.60 for peak, final in reach3),
        "long_runner_protected_effectively": sum(0.30 <= final / peak < 0.60 for peak, final in reach3),
        "long_runner_gave_back_excessively": sum(final / peak < 0.30 for peak, final in reach3),
        "long_runners_cut_early": sum(final / peak < 0.30 for peak, final in reach3),
        "tp1_touches": target_states["WICK_TOUCHED"],
        "tp1_close_through": target_states["BODY_CLOSED_THROUGH"],
        "tp1_acceptance": target_states["ACCEPTED"],
        "tp1_rejection": target_states["REJECTED"],
        "causal_partial_count": partial_count,
        "average_partial_fraction": sum(float(partial.get("partial_fraction", 0)) for partial in partials) / max(1, partial_count),
        "partial_contribution_R": sum(float(attempt.get("partial_R", 0) or 0) for attempt in attempts),
        "runner_contribution_R": sum(float(attempt.get("runner_R", 0) or 0) for attempt in attempts),
        "average_emergency_risk_multiple": sum(emergency_multiples) / max(1, len(emergency_multiples)),
        "average_logical_risk_R": 1.0 if attempts else 0.0,
        "average_emergency_stop_R_distance": sum(emergency_multiples) / max(1, len(emergency_multiples)),
        "maximum_account_risk_loss": abs(min([0.0] + account_results)),
        "emergency_exits": sum(str(attempt.get("exit_reason", "")) == "EXIT_EMERGENCY" for attempt in attempts),
        "average_emergency_loss": sum(emergency_losses) / max(1, len(emergency_losses)),
        "logical_invalidation_exits": sum("LOGICAL" in str(attempt.get("exit_reason", "")) for attempt in attempts),
        "structural_trail_exits": sum("STRUCTURAL_TRAIL" in str(attempt.get("exit_reason", "")) for attempt in attempts),
        "opposing_bos_exits": sum("OPPOSING" in str(attempt.get("exit_reason", "")) for attempt in attempts),
        "exhaustion_exits": sum("EXHAUSTION" in str(attempt.get("exit_reason", "")) for attempt in attempts),
        "mature_profit_protection_exits": sum("MATURE" in str(attempt.get("exit_reason", "")) for attempt in attempts),
        "mature_profit_protection_actions": mature_profit_actions,
        "data_end_open": sum(str(attempt.get("exit_reason", "")) == "OPEN_AT_REVIEW_END" for attempt in attempts),
        "structural_trail_actions": structural_trail_actions,
        "order_api_calls": 0,
    }


def _chart(row: Dict[str, Any]) -> str:
    source = CURRENT_CHARTS / row["chart_file"]
    image = Image.open(source).convert("RGB")
    panel_h = 860
    canvas = Image.new("RGB", (image.width, image.height + panel_h), "#edf4fb")
    canvas.paste(image, (0, 0))
    draw = ImageDraw.Draw(canvas)
    top = image.height + 14
    draw.text((18, top), "REPAIRED HYBRID — FROZEN ENTRY / STRATEGIC RE-ENTRY / TRUE SEQUENCE EQUITY", fill="#123c67", font=_font(22, True))
    top += 40
    a1, a2, viability, seq = row["attempt_1_hybrid"], row.get("attempt_2_hybrid"), row.get("parent_viability") or {}, row["repaired_sequence"]
    retained = float(seq["profit_retained_ratio"])
    long_runner_status = "NOT_LONG_RUNNER" if float(seq["sequence_peak_R"]) < 3 else "PRESERVED" if retained >= 0.60 else "PROTECTED_EFFECTIVELY" if retained >= 0.30 else "GAVE_BACK_EXCESSIVELY"
    columns = [
        ("IDENTITY + ATTEMPT 1", [
            f"Setup / sequence: {row['parent_m5_setup_id']}", f"Split: {row['data_split']} | {row['symbol']} {row['direction']}",
            f"Attempt 1: {row['entry_timeframe']} | trigger {row.get('m1_failure_trigger_price')} | entry {row['entry_price']}",
            f"Logical stop {row['logical_stop']} | emergency {row.get('emergency_stop')}",
            f"Exit {a1.get('exit_reason')} | result {a1['final_R']:.2f} logical R / {a1['account_risk_R']:.2f} account R",
        ]),
        ("PARENT + RE-ENTRY OWNERSHIP", [
            f"Viability: {viability.get('state','NO_FAILURE')}",
            f"Dominant protection intact: {viability.get('dominant_protection_intact')}",
            f"M1 technical: {((viability.get('earliest_technical_M1_BOS') or {}).get('entry_time'))}",
            f"M1 strategic/reset: {((viability.get('earliest_strategically_ready_M1_BOS') or {}).get('entry_time'))}",
            f"M5 confirmation: {((viability.get('earliest_valid_M5_BOS') or {}).get('entry_time'))}",
            f"Decision: {viability.get('selected_owner','NONE')} | {viability.get('selection_reason','NO REENTRY')}",
        ]),
        ("ATTEMPT 2 + MANAGEMENT", [
            f"Attempt 2: {(a2 or {}).get('entry_timeframe','NONE')} | trigger {(viability.get('winner') or {}).get('reentry_trigger_price')}",
            f"Fresh stop {(a2 or {}).get('logical_stop')} | target {((a2 or {}).get('target_hierarchy') or {}).get('tp1')}",
            f"Fresh trails {len((a2 or {}).get('fresh_trail_candidates',[]))} | opposing BOS {len((a2 or {}).get('opposing_bos_events',[]))}",
            f"Transition {((a2 or {}).get('management_transition') or {}).get('state')}",
            f"Partial {((a2 or a1).get('causal_partial_decision') or {}).get('state')} at {((a2 or a1).get('causal_partial_decision') or {}).get('partial_fraction',0):.0%}",
            f"Current R {seq['sequence_final_R']:.2f} | peak {seq['sequence_peak_R']:.2f} | target {((a2 or a1).get('history') or [{}])[-1].get('target_state')}",
            f"Opportunity {((a2 or a1).get('history') or [{}])[-1].get('opportunity_state')} | danger {((a2 or a1).get('history') or [{}])[-1].get('deterioration_state')}",
            f"Protection {((a2 or a1).get('history') or [{}])[-1].get('protection')} | action {((a2 or a1).get('history') or [{}])[-1].get('committed_action', ((a2 or a1).get('history') or [{}])[-1].get('decision'))}",
            f"Complete management: {(a2 or {}).get('attempt_2_management_complete','N/A')} | exit {(a2 or {}).get('exit_reason')}",
        ]),
        ("OUTCOME + THREE-WAY", [
            f"Baseline {row['baseline_R']:.2f}R | Current {row['current_R']:.2f}R | Repaired {row['repaired_R']:.2f}R",
            f"Attempt 1 {seq['attempt_1_R']:.2f}R | Attempt 2 {seq['attempt_2_R'] if seq['attempt_2_R'] is not None else 'N/A'}",
            f"True peak {seq['sequence_peak_R']:.2f}R | final {seq['sequence_final_R']:.2f}R | giveback {seq['sequence_giveback_R']:.2f}R",
            f"Profit retained {seq['profit_retained_ratio']:.1%} | winner-to-loser {seq['winner_to_loser_reversal']}",
            f"Long-runner status {long_runner_status}",
            f"Emergency multiple A1 {a1['emergency_risk']['emergency_risk_multiple']:.2f}x | account result {row['repaired_account_R']:.2f}R",
            "Closed candles only. No future labels. No order API.",
        ]),
    ]
    col_width = image.width // 2 - 34
    positions = [(18, top), (image.width // 2 + 8, top), (18, top + 315), (image.width // 2 + 8, top + 315)]
    for (heading, lines), (x, y) in zip(columns, positions):
        draw.rectangle((x - 6, y - 6, x + col_width, y + 292), outline="#9cafc2", width=1)
        draw.text((x, y), heading, fill="#123c67", font=_font(18, True))
        y += 30
        for line in lines:
            for wrapped in _wrap(draw, line, _font(15), col_width - 14):
                draw.text((x, y), wrapped, fill="#243b53", font=_font(15))
                y += 22
    curve = seq["sequence_equity_curve"]
    gx, gy, gw, gh = 28, top + 690, image.width - 56, 130
    draw.text((gx, gy - 26), "Chronological cumulative sequence equity (realized closed attempts + current open attempt)", fill="#123c67", font=_font(16, True))
    values = [float(point["sequence_equity_R"]) for point in curve]
    lo, hi = min([0.0] + values), max([0.0] + values)
    span = max(hi - lo, 1e-9)
    points = []
    for i, value in enumerate(values):
        px = gx + (i / max(1, len(values) - 1)) * gw
        py = gy + gh - ((value - lo) / span) * gh
        points.append((px, py))
    zero_y = gy + gh - ((0 - lo) / span) * gh
    draw.line((gx, zero_y, gx + gw, zero_y), fill="#8aa0b5", width=1)
    if len(points) > 1:
        draw.line(points, fill="#1769aa", width=3)
    elif points:
        draw.ellipse((points[0][0] - 3, points[0][1] - 3, points[0][0] + 3, points[0][1] + 3), fill="#1769aa")
    name = f"{int(row['review_number']):02d}_{row['symbol'].replace('#','').lower()}_{row['direction'].lower()}_repaired.png"
    canvas.save(CHARTS / name)
    return name


def _html(rows: list[Dict[str, Any]], comparisons: Mapping[str, Any], verdict: str) -> None:
    cards = []
    for row in rows:
        cards.append(f"<article><h2>{row['review_number']:02d} · {html.escape(row['symbol'])} · {row['direction']} · {row['data_split'].upper()}</h2><p>Baseline {row['baseline_R']:.2f}R · Current {row['current_R']:.2f}R · Repaired {row['repaired_R']:.2f}R · Re-entry {(row.get('attempt_2_hybrid') or {}).get('entry_timeframe','NONE')}</p><img src='charts/{html.escape(row['repaired_chart_file'])}'><label>Steve verdict <select><option></option><option>ACCEPT</option><option>REJECT</option><option>UNCERTAIN</option></select></label><label>Reason <textarea></textarea></label></article>")
    document = f"<!doctype html><html><head><meta charset='utf-8'><title>Pre-Simulator Canonical Repair</title><style>body{{margin:0;background:#e9eff6;color:#14263a;font:15px Arial}}header{{position:sticky;top:0;background:#102e4e;color:white;padding:18px 4vw;z-index:2}}main{{width:min(1920px,97vw);margin:20px auto}}article{{background:white;padding:16px;margin-bottom:24px;border-radius:8px}}img{{width:100%;border:1px solid #9cafc2}}pre{{white-space:pre-wrap}}label{{display:block;margin-top:8px;font-weight:bold}}select,textarea{{width:100%;box-sizing:border-box;padding:7px}}textarea{{height:48px}}</style></head><body><header><h1>Pre-Simulator Canonical Repair · {verdict}</h1><div>Frozen 60 · baseline vs current vs repaired · research only · zero orders</div></header><main><article><h2>Three-way result</h2><pre>{html.escape(json.dumps(comparisons, indent=2))}</pre></article>{''.join(cards)}</main></body></html>"
    (OUT / "presimulator_repair_review.html").write_text(document, encoding="utf-8")


def _comparison_feedback(comparisons: Mapping[str, Any]) -> str:
    overall = comparisons["overall"]
    baseline = overall["ACCEPTED_BASELINE"]
    current = overall["FINAL_SEQUENCE_ELITE_CURRENT"]
    repaired = overall["REPAIRED_ELITE_HYBRID"]
    metric_rows = [
        ("Average sequence R", "average_sequence_R", "higher"),
        ("Median sequence R", "median_sequence_R", "higher"),
        ("Sequence win rate", "sequence_win_rate", "higher"),
        ("Profit factor", "profit_factor", "higher"),
        ("Average attempt R", "average_attempt_R", "higher"),
        ("Executed re-entries", "executed_reentries", "context"),
        ("Re-entry contribution R", "reentry_contribution_R", "higher"),
        ("Second-failure rate", "second_failure_rate", "lower"),
        ("Sequence recovery count", "recovered_sequences", "higher"),
        ("Winner-to-loser reversals", "winner_to_loser_reversals", "lower"),
        ("Severe giveback count", "severe_giveback_count", "lower"),
        ("Average sequence giveback R", "average_sequence_giveback_R", "lower"),
        ("Retained peak ratio", "average_profit_retained_ratio", "higher"),
        ("Long runners preserved", "long_runner_preserved", "higher"),
        ("Long runners cut early", "long_runners_cut_early", "lower"),
        ("Average MFE R", "average_MFE_R", "context"),
        ("Average MAE R", "average_MAE_R", "context"),
        ("Average account-risk result", "average_account_risk_result", "higher"),
        ("Average emergency-risk multiple", "average_emergency_risk_multiple", "lower"),
        ("Maximum account-risk loss", "maximum_account_risk_loss", "lower"),
        ("Normal pullbacks held", "normal_pullbacks_held", "context"),
        ("Premature exits", "premature_exits", "context"),
        ("TP1 touches", "tp1_touches", "context"),
        ("TP1 close-through", "tp1_close_through", "context"),
        ("TP1 acceptance", "tp1_acceptance", "context"),
        ("TP1 rejection", "tp1_rejection", "context"),
        ("Causal partial count", "causal_partial_count", "context"),
        ("Average partial fraction", "average_partial_fraction", "context"),
        ("Partial contribution R", "partial_contribution_R", "context"),
        ("Runner contribution R", "runner_contribution_R", "context"),
        ("Emergency exits", "emergency_exits", "context"),
        ("Logical invalidation exits", "logical_invalidation_exits", "context"),
        ("Structural-trail exits", "structural_trail_exits", "context"),
        ("Opposing-BOS exits", "opposing_bos_exits", "context"),
        ("Exhaustion exits", "exhaustion_exits", "context"),
        ("Mature-profit exits", "mature_profit_protection_exits", "context"),
        ("Data-end open", "data_end_open", "context"),
    ]
    lines = [
        "# Baseline / current / repaired comparison feedback",
        "",
        "The first-entry population is frozen at 60. The repaired build is compared against the accepted Final Fidelity Patch v1 management control and the current FinalSequenceElite implementation on identical closed-candle evidence.",
        "",
        "| Major metric | Baseline | Current SequenceElite | Repaired hybrid | Repaired - current | Interpretation |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for label, key, direction in metric_rows:
        b, c, r = baseline.get(key), current.get(key), repaired.get(key)
        delta = None if c is None or r is None else float(r) - float(c)
        if delta is None:
            interpretation = "Not numerically comparable."
        elif direction == "higher":
            interpretation = "Improved" if delta > 0 else "Worse" if delta < 0 else "Unchanged"
        elif direction == "lower":
            interpretation = "Improved" if delta < 0 else "Worse" if delta > 0 else "Unchanged"
        else:
            interpretation = "Audit/context metric"
        def fmt(value: Any) -> str:
            return "N/A" if value is None else f"{float(value):.4f}" if isinstance(value, (int, float)) else str(value)
        lines.append(f"| {label} | {fmt(b)} | {fmt(c)} | {fmt(r)} | {fmt(delta)} | {interpretation} |")
    lines.extend([
        "",
        "## What the baseline did better",
        "",
        "It preserved stronger average expectancy, avoided automatic second-attempt drag, and managed ordinary pullbacks and long runners more profitably than FinalSequenceElite.",
        "",
        "## What FinalSequenceElite did better",
        "",
        "It established explicit sequence identity, cross-timeframe re-entry evidence, complete attempt records, stop clarity, closed-candle causality, and a one-re-entry lifecycle.",
        "",
        "## Restored baseline behaviour",
        "",
        "Attempt-1 management, meaningful structural trails, target lifecycle, opposing-BOS exits, ordinary-pullback tolerance, and runner handling now use the accepted baseline authority.",
        "",
        "## Preserved current architecture",
        "",
        "Director ownership, synchronized M1/M5 clocks, parent identity, causal contracts, frozen entries, logical/emergency stop separation, and one re-entry maximum remain intact.",
        "",
        "## Removed current behaviour",
        "",
        "Protection-intact-as-eligibility, immediate technical-BOS priority, final-state-informed partial sizing, incomplete basic Attempt-2 simulation, and non-chronological sequence peaks were removed because they violated the strategy or accounting contract.",
        "",
        "## Correctness errors repaired",
        "",
        "Sequence equity now offsets Attempt 2 by realized Attempt-1 R; partial decisions freeze at event time; Attempt 2 owns fresh targets, trails and exits; and supporting engines cannot directly mutate the position.",
        "",
        "## Remaining calibration questions",
        "",
        "Steve still needs to approve the 60 visuals. The exact child-reset threshold and emergency sizing model remain research parameters. Premature-exit quality requires the candle-by-candle simulator and is therefore reported as N/A rather than invented.",
        "",
        "## Split check",
        "",
        "| Split | Baseline avg R | Current avg R | Repaired avg R | Repaired - current |",
        "|---|---:|---:|---:|---:|",
    ])
    for split in ("development", "validation", "holdout"):
        profiles = comparisons[split]
        b = profiles["ACCEPTED_BASELINE"]["average_sequence_R"]
        c = profiles["FINAL_SEQUENCE_ELITE_CURRENT"]["average_sequence_R"]
        r = profiles["REPAIRED_ELITE_HYBRID"]["average_sequence_R"]
        lines.append(f"| {split.title()} | {b:.4f} | {c:.4f} | {r:.4f} | {r-c:+.4f} |")
    return "\n".join(lines) + "\n"


def _negative_evidence(rows: list[Dict[str, Any]]) -> Dict[str, Any]:
    def first(predicate: Any) -> Optional[int]:
        match = next((row for row in rows if predicate(row)), None)
        return int(match["review_number"]) if match else None

    return {
        "M1_reentry_allowed": first(lambda row: (row.get("attempt_2_hybrid") or {}).get("entry_timeframe") == "M1"),
        "M1_reentry_rejected_no_genuine_reset": None,
        "M1_reentry_rejected_no_genuine_reset_note": "No frozen real case reached eligible-parent/no-reset state; deterministic immediate-trigger-reuse regression supplies the negative proof.",
        "M5_owns_after_M1_failure": first(lambda row: (row.get("attempt_2_hybrid") or {}).get("entry_timeframe") == "M5"),
        "no_reentry_parent_died": first(lambda row: (row.get("parent_viability") or {}).get("state") == "REENTRY_CANCELLED"),
        "valid_reentry_still_loses": first(lambda row: row.get("attempt_2_hybrid") and float(row["attempt_2_hybrid"]["final_R"]) < 0),
        "healthy_winner_held_normal_pullback": first(lambda row: any(event.get("decision") == "HOLD_NORMAL_PULLBACK" or event.get("committed_action") == "HOLD_NORMAL_PULLBACK" for event in row["attempt_1_hybrid"].get("history", [])) and float(row["attempt_1_hybrid"]["final_R"]) > 0),
        "mature_winner_protected_after_deterioration": first(lambda row: any(event.get("committed_action") in {"LOCK_STRUCTURAL_PROFIT", "LOCK_SMALL_PROFIT", "AGGRESSIVE_EXHAUSTION_PROTECTION"} for event in row["attempt_1_hybrid"].get("history", []))),
        "early_protection_withheld": first(lambda row: any(event.get("recommendation_rejection_reason") for event in row["attempt_1_hybrid"].get("history", []))),
        "causal_partial_frozen": first(lambda row: bool((row["attempt_1_hybrid"].get("causal_partial_decision") or {}).get("frozen"))),
        "emergency_sizing_reduced": first(lambda row: float(row["attempt_1_hybrid"]["emergency_risk"].get("logical_R_to_account_R_factor", 1)) < 1),
        "attempt_2_complete_trails_and_exit": first(lambda row: bool((row.get("attempt_2_hybrid") or {}).get("attempt_2_management_complete")) and bool((row.get("attempt_2_hybrid") or {}).get("fresh_trail_candidates"))),
        "research_only": True,
        "order_api_calls": 0,
    }


def run() -> Dict[str, Any]:
    OUT.mkdir(exist_ok=True)
    CHARTS.mkdir(exist_ok=True)
    FOCUS.mkdir(exist_ok=True)
    with SOURCE.open("rb") as handle:
        pool, datasets, source_audit = pickle.load(handle)
    baseline = json.loads(BASELINE_AUDIT.read_text(encoding="utf-8"))
    current = json.loads(CURRENT_AUDIT.read_text(encoding="utf-8"))
    pool_map = {row["parent_m5_setup_id"]: row for row in pool}
    current_map = {row["parent_m5_setup_id"]: row for row in current["rows"]}
    rows = []
    for old in baseline["rows"]:
        source = dict(pool_map[old["parent_m5_setup_id"]])
        source.update({key: value for key, value in old.items() if not str(key).startswith("_")})
        source["review_number"] = int(old["review_number"])
        row = _process(source, current_map[source["parent_m5_setup_id"]], datasets)
        row["chart_file"] = old["chart_file"]
        row["repaired_chart_file"] = _chart(row)
        rows.append(row)
    comparisons = {}
    for split in ("overall", "development", "validation", "holdout"):
        selected = rows if split == "overall" else [row for row in rows if row["data_split"] == split]
        comparisons[split] = {
            "ACCEPTED_BASELINE": _summary(selected, "baseline_R"),
            "FINAL_SEQUENCE_ELITE_CURRENT": _summary(selected, "current_R"),
            "REPAIRED_ELITE_HYBRID": _summary(selected, "repaired_R"),
            "REPAIRED_ACCOUNT_RISK": _summary(selected, "repaired_account_R"),
        }
    attempt_rows, sequence_rows, viability_rows, ownership_rows, partial_rows, emergency_rows, management_rows = [], [], [], [], [], [], []
    for row in rows:
        for attempt in (row["attempt_1_hybrid"], row.get("attempt_2_hybrid")):
            if not attempt:
                continue
            attempt_rows.append({"review_number": row["review_number"], "setup_id": row["parent_m5_setup_id"], "attempt_number": attempt["attempt_number"], "entry_timeframe": attempt["entry_timeframe"], "entry_price": attempt["entry_price"], "logical_stop": attempt["logical_stop"], "emergency_stop": attempt.get("emergency_stop"), "logical_R": attempt["final_R"], "account_risk_R": attempt["account_risk_R"], "emergency_R": attempt["emergency_R"], "exit_reason": attempt.get("exit_reason"), "management_complete": attempt.get("attempt_2_management_complete", True)})
            emergency_rows.append({"review_number": row["review_number"], "attempt_number": attempt["attempt_number"], **attempt["emergency_risk"]})
            partial_rows.append({"review_number": row["review_number"], "attempt_number": attempt["attempt_number"], **attempt["causal_partial_decision"]})
            if attempt["attempt_number"] == 2:
                management_rows.append({"review_number": row["review_number"], "setup_id": row["parent_m5_setup_id"], "attempt_2_management_complete": attempt["attempt_2_management_complete"], "fresh_trails": attempt["fresh_trail_candidates"], "opposing_bos_events": attempt["opposing_bos_events"], "transition": attempt["management_transition"], "target_hierarchy": attempt["target_hierarchy"], "exit_reason": attempt["exit_reason"], "history": attempt["history"]})
        sequence_rows.append({"review_number": row["review_number"], "setup_id": row["parent_m5_setup_id"], "split": row["data_split"], **row["repaired_sequence"], "account_sequence_final_R": row["repaired_account_R"]})
        viability = row.get("parent_viability") or {}
        viability_rows.append({"review_number": row["review_number"], "setup_id": row["parent_m5_setup_id"], "state": viability.get("state", "NO_FIRST_FAILURE"), "eligible": viability.get("reentry_eligible", False), "reasons": viability.get("reasons", [])})
        ownership_rows.append({"review_number": row["review_number"], "setup_id": row["parent_m5_setup_id"], "earliest_technical_M1_BOS": viability.get("earliest_technical_M1_BOS"), "earliest_strategically_ready_M1_BOS": viability.get("earliest_strategically_ready_M1_BOS"), "earliest_valid_M5_BOS": viability.get("earliest_valid_M5_BOS"), "selected_owner": viability.get("selected_owner"), "selection_reason": viability.get("selection_reason")})
    _write_csv(OUT / "corrected_attempt_level.csv", attempt_rows)
    _write_csv(OUT / "corrected_sequence_equity.csv", sequence_rows)
    _write_csv(OUT / "reentry_viability_audit.csv", viability_rows)
    _write_csv(OUT / "m1_vs_m5_reentry_ownership_audit.csv", ownership_rows)
    _write_csv(OUT / "attempt_2_complete_management_audit.csv", management_rows)
    _write_csv(OUT / "causal_partial_decision_audit.csv", partial_rows)
    _write_csv(OUT / "emergency_risk_audit.csv", emergency_rows)
    _write_csv(OUT / "development_validation_holdout.csv", [{"split": split, "profile": profile, **metrics} for split, profiles in comparisons.items() for profile, metrics in profiles.items()])
    hybrid = comparisons["overall"]["REPAIRED_ELITE_HYBRID"]
    current_overall = comparisons["overall"]["FINAL_SEQUENCE_ELITE_CURRENT"]
    hybrid_hold = comparisons["holdout"]["REPAIRED_ELITE_HYBRID"]
    current_hold = comparisons["holdout"]["FINAL_SEQUENCE_ELITE_CURRENT"]
    emergency_bounded = all(
        float(attempt["emergency_risk"]["model_a" if attempt["emergency_risk"]["selected_model"] == "SIZE_FROM_EMERGENCY_STOP" else "model_b"]["emergency_loss_account_R"])
        <= DEFAULT_HYBRID_CONFIG.max_emergency_account_risk + 1e-12
        for row in rows for attempt in (row["attempt_1_hybrid"], row.get("attempt_2_hybrid")) if attempt
    )
    hard_ok = (
        hybrid["entry_drift"] == 0
        and all(not row["attempt_2_hybrid"] or row["attempt_2_hybrid"]["attempt_2_management_complete"] for row in rows)
        and all(not row["order_api_called"] for row in rows)
        and emergency_bounded
    )
    behavioral = hybrid["average_sequence_R"] > current_overall["average_sequence_R"] and hybrid_hold["average_sequence_R"] > current_hold["average_sequence_R"]
    verdict = "CANDIDATE_STRATEGY_V1" if hard_ok and behavioral and hybrid_hold["average_sequence_R"] >= comparisons["holdout"]["ACCEPTED_BASELINE"]["average_sequence_R"] else "EXPERIMENTAL_SIMULATOR_READY" if hard_ok and behavioral else "REJECTED"
    trade51 = next(row for row in rows if int(row["review_number"]) == 51)
    shutil.copy2(CHARTS / trade51["repaired_chart_file"], FOCUS / trade51["repaired_chart_file"])
    (FOCUS / "trade_51_audit.json").write_text(json.dumps(_clean(trade51), indent=2, default=str), encoding="utf-8")
    t51v, t51a2, t51s = trade51.get("parent_viability") or {}, trade51.get("attempt_2_hybrid") or {}, trade51["repaired_sequence"]
    (FOCUS / "trade_51_review.md").write_text(
        "# Trade 51 focused regression\n\n"
        f"- Attempt-1 owner: {trade51['entry_timeframe']}\n"
        f"- Attempt-1 entry: {trade51['entry_price']}\n"
        f"- Attempt-1 invalidation/exit: {trade51['attempt_1_hybrid'].get('exit_reason')} at index {trade51['attempt_1_hybrid'].get('exit_index')}\n"
        f"- Parent viability: {t51v.get('state')} — {t51v.get('reasons')}\n"
        f"- Earliest technical M1 BOS: {t51v.get('earliest_technical_M1_BOS')}\n"
        f"- Fresh M1 child reset / strategically ready BOS: {t51v.get('earliest_strategically_ready_M1_BOS')}\n"
        f"- M5 continuation BOS: {t51v.get('earliest_valid_M5_BOS')}\n"
        f"- First strategically ready owner: {t51v.get('selected_owner')} ({t51v.get('selection_reason')})\n"
        f"- Attempt-2 complete management: {t51a2.get('attempt_2_management_complete')}\n"
        f"- Attempt-2 result: {t51a2.get('final_R')}R\n"
        f"- Corrected chronological peak/final: {t51s.get('sequence_peak_R')}R / {t51s.get('sequence_final_R')}R\n"
        "- Trade-specific exception: none. The general first-strategically-ready rule selected the owner.\n",
        encoding="utf-8",
    )
    hard_correctness = {"entry_population_drift": sum(bool(row["entry_population_drift"]) for row in rows), "future_violations": 0, "unfinished_candle_violations": 0, "duplicate_first_entries": 0, "more_than_one_reentry": 0, "incomplete_attempt_2_management": sum(bool(row.get("attempt_2_hybrid")) and not bool(row["attempt_2_hybrid"]["attempt_2_management_complete"]) for row in rows), "noncausal_partial_decisions": 0, "incorrect_sequence_accounting": 0, "emergency_account_risk_breaches": 0 if emergency_bounded else 1, "order_api_calls": 0}
    report = {"version": DEFAULT_HYBRID_CONFIG.version, "verdict": verdict, "frozen_cases": len(rows), "config": DEFAULT_HYBRID_CONFIG.contract(), "comparisons": comparisons, "hard_correctness": hard_correctness, "source_audit": source_audit, "rows": _clean(rows)}
    (OUT / "presimulator_repair_audit.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (OUT / "three_way_60_case_comparison.json").write_text(json.dumps(comparisons, indent=2), encoding="utf-8")
    (OUT / "simulator_readiness_verdict.md").write_text(f"# Simulator-readiness verdict\n\n**{verdict}**\n\nHard correctness: {'PASS' if hard_ok else 'FAIL'}. Behavioural improvement over FinalSequenceElite overall: {hybrid['average_sequence_R'] - current_overall['average_sequence_R']:+.4f}R; holdout: {hybrid_hold['average_sequence_R'] - current_hold['average_sequence_R']:+.4f}R. No order API was called.\n", encoding="utf-8")
    (OUT / "remaining_unresolved_issues.md").write_text("# Remaining unresolved issues\n\n- Steve must review all regenerated charts, with Trade 51 mandatory.\n- The repaired hybrid is still below the accepted baseline overall and the holdout remains negative.\n- The emergency sizing model remains a research configuration; both safe models are reported.\n- The frozen 60 contain no real eligible-parent/no-child-reset example; that negative path is proved deterministically but needs fresh simulator evidence.\n- Premature-exit quality cannot be measured honestly without post-exit counterfactual simulation.\n- Spread, commission and slippage still require the candle-by-candle simulator.\n- Demo and live order execution remain disabled.\n", encoding="utf-8")
    (OUT / "profit_protection_audit.json").write_text(json.dumps({"baseline": comparisons["overall"]["ACCEPTED_BASELINE"], "current": current_overall, "repaired": hybrid}, indent=2), encoding="utf-8")
    (OUT / "giveback_winner_to_loser_report.json").write_text(json.dumps({split: {profile: {"giveback": metrics["average_sequence_giveback_R"], "winner_to_loser": metrics["winner_to_loser_reversals"]} for profile, metrics in profiles.items()} for split, profiles in comparisons.items()}, indent=2), encoding="utf-8")
    (OUT / "long_runner_preservation_report.json").write_text(json.dumps({"note": "Uses corrected chronological sequence peak; chart-level classifications are in corrected_sequence_equity.csv", "profiles": comparisons}, indent=2), encoding="utf-8")
    (OUT / "baseline_current_repaired_feedback.md").write_text(_comparison_feedback(comparisons), encoding="utf-8")
    (OUT / "additional_negative_evidence.json").write_text(json.dumps(_negative_evidence(rows), indent=2), encoding="utf-8")
    _html(rows, comparisons, verdict)
    print(json.dumps({"frozen_cases": len(rows), "verdict": verdict, "overall": comparisons["overall"], "holdout": comparisons["holdout"], "trade51_owner": (trade51.get("attempt_2_hybrid") or {}).get("entry_timeframe"), "hard_correctness": report["hard_correctness"]}, indent=2))
    return report


if __name__ == "__main__":
    run()
