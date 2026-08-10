from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import argparse
import csv
import hashlib
import html
import json
import platform
import statistics
import subprocess
import sys

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.expert_strategy import build_expert_htf_context, confirmed_swings, scan_expert_m5_candidates
from core.steve_trade_management import SteveTradeManagementEngine
from core.synchronized_m1_replay import (
    COUNTER_CONFIRMED_ACTIVE,
    EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE,
    arbitrate_first_valid_entry,
    build_parent_contract,
    evaluate_armed_to_active_shadow,
    find_m1_child_entry,
)
from simulator.adapters.pipeline_adapter import CanonicalPipelineAdapter
from simulator.config import load_config


OUT = ROOT / "research_runs" / "s2b"
VISUALS = OUT / "visuals"
AVAILABLE_SYMBOLS = ("AUDUSD#", "EURUSD#", "GBPUSD#", "GER40Cash#", "GOLD#", "US100Cash#", "USDJPY#")
MISSING_SYMBOLS = ("US30Cash#", "OILCash#")
FOREX = {"AUDUSD#", "EURUSD#", "GBPUSD#", "USDJPY#"}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _iso(value: Any) -> str:
    return "" if value in (None, "") else datetime.fromtimestamp(float(value), timezone.utc).isoformat()


def _csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or ["state"])
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, sort_keys=True, default=str) if isinstance(value, (dict, list, tuple)) else value for key, value in row.items()})


def _remap(value: Any, offset: int) -> Any:
    if isinstance(value, list):
        return [_remap(item, offset) for item in value]
    if not isinstance(value, dict):
        return value
    result: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, int) and not isinstance(item, bool) and (key == "index" or key.endswith("_index") or key.endswith("_at_index")):
            result[key] = item - offset
        else:
            result[key] = _remap(item, offset)
    return result


def _entry_model(entry: dict[str, Any], parent: dict[str, Any], candidate: dict[str, Any], timeframe: str) -> dict[str, Any]:
    if timeframe == "M5":
        model = deepcopy(candidate)
        model["entry_price"] = float(entry.get("entry_price", entry.get("price")))
        model["stop_level"] = float(entry["logical_stop"])
        return model
    direction = str(entry["parent_direction"])
    counter_side = "LOW" if direction == "BULLISH" else "HIGH"
    trigger_side = "HIGH" if direction == "BULLISH" else "LOW"
    counter_index = int(entry["counter_structure_index"])
    trigger_index = int(entry["failure_trigger_index"])
    logical_index = int(entry["logical_stop_owner_index"])
    return {
        "setup_id": entry["parent_m5_setup_id"],
        "direction": direction,
        "entry_index": int(entry["entry_index"]),
        "entry_price": float(entry["entry_price"]),
        "anchor": {"index": counter_index, "level": float(entry["counter_structure_price"]), "side": counter_side, "confirmed_at_index": min(counter_index + 2, int(entry["entry_index"]))},
        "counter": {"index": counter_index, "level": float(entry["counter_structure_price"]), "side": counter_side, "confirmed_at_index": min(counter_index + 2, int(entry["entry_index"]))},
        "trigger": {"index": trigger_index, "level": float(entry["failure_trigger_price"]), "side": trigger_side, "confirmed_at_index": int(entry["failure_trigger_available_at_index"])},
        "logical_stop_structure": {"index": logical_index, "level": float(entry["logical_stop"]), "side": counter_side, "confirmed_at_index": min(logical_index + 2, int(entry["entry_index"]))},
        "stop_level": float(entry["logical_stop"]),
        "fibonacci": deepcopy((parent.get("retrospective_m5_outcome") or {}).get("candidate", {}).get("fibonacci") or candidate.get("fibonacci") or {}),
    }


def _managed_outcome(
    *, symbol: str, entry: dict[str, Any], owner: str, parent: dict[str, Any],
    candidate: dict[str, Any], context: dict[str, Any], m1: pd.DataFrame,
    m5: pd.DataFrame, review_end_time: float,
) -> dict[str, Any]:
    timeframe = str(owner)
    seconds = 60 if timeframe == "M1" else 300
    data = m1 if timeframe == "M1" else m5
    entry_index = int(entry.get("entry_index", entry.get("index")))
    end_index = min(len(data) - 1, int((data["time"].astype(float) + seconds).searchsorted(review_end_time, side="right") - 1))
    offset = max(0, entry_index - (160 if timeframe == "M1" else 100))
    local = data.iloc[offset : end_index + 1].reset_index(drop=True)
    model = _remap(_entry_model(entry, parent, candidate, timeframe), offset)
    local_entry = int(model["entry_index"])
    swings = confirmed_swings(local, as_of_index=len(local) - 1, sensitivity=2 if timeframe == "M1" else 3)
    management = SteveTradeManagementEngine().evaluate(
        data=local,
        symbol=symbol,
        timeframe=timeframe,
        as_of_index=len(local) - 1,
        direction=str(parent["parent_direction"]),
        context=context,
        confirmed_swings=swings,
        canonical_entry=model,
    )
    attempts = list(management.get("attempts") or [])
    attempt_metrics: list[dict[str, Any]] = []
    for attempt in attempts:
        start = int(attempt["entry_index"])
        finish = int(attempt.get("exit_index")) if attempt.get("exit_index") is not None else len(local) - 1
        candles = local.iloc[start : finish + 1]
        price = float(attempt.get("exit_price")) if attempt.get("exit_price") is not None else float(local.iloc[-1]["close"])
        entry_price = float(attempt["entry_price"])
        stop = float(attempt["logical_stop"])
        risk = max(abs(entry_price - stop), 1e-12)
        direction = str(attempt["direction"])
        final_r = (price - entry_price) / risk if direction == "BULLISH" else (entry_price - price) / risk
        mfe = ((float(candles["high"].max()) - entry_price) / risk if direction == "BULLISH" else (entry_price - float(candles["low"].min())) / risk)
        mae = ((float(candles["low"].min()) - entry_price) / risk if direction == "BULLISH" else (entry_price - float(candles["high"].max())) / risk)
        attempt_metrics.append({"attempt_number": int(attempt["attempt_number"]), "final_r": round(final_r, 6), "mfe_r": round(mfe, 6), "mae_r": round(mae, 6), "exit_reason": attempt.get("exit_reason") or "OPEN_AT_REVIEW_END", "tp1_hit": bool(attempt.get("tp1_triggered")), "status": attempt.get("status")})
    if not attempt_metrics:
        return {"attempt_count": 0, "sequence_final_r": 0.0, "causal_valid": False}
    sequence_r = sum(float(row["final_r"]) for row in attempt_metrics)
    peak_r = max(float(row["mfe_r"]) for row in attempt_metrics)
    mae_r = min(float(row["mae_r"]) for row in attempt_metrics)
    return {
        "attempt_count": len(attempt_metrics),
        "attempt1_exit_reason": attempt_metrics[0]["exit_reason"],
        "attempt1_final_r": attempt_metrics[0]["final_r"],
        "sequence_final_r": round(sequence_r, 6),
        "mfe_r": round(peak_r, 6),
        "mae_r": round(mae_r, 6),
        "peak_r": round(peak_r, 6),
        "giveback_r": round(max(0.0, peak_r - sequence_r), 6),
        "tp1_hit": any(row["tp1_hit"] for row in attempt_metrics),
        "reentry_used": len(attempt_metrics) > 1,
        "sequence_win_loss": "WIN" if sequence_r > 1e-9 else "LOSS" if sequence_r < -1e-9 else "FLAT",
        "attempts": attempt_metrics,
        "management_state": management.get("state"),
        "order_api_called": False,
        "causal_valid": bool(management.get("causal_valid", True)),
    }


def _funnel_state(value: str) -> str:
    mapping = {
        "SHADOW_VALID_EARLY_M1": "EARLY_VALID",
        "SHADOW_NO_COUNTER_STRUCTURE": "NO_COUNTER_STRUCTURE",
        "SHADOW_INCOMPLETE_SEQUENCE": "INCOMPLETE_SEQUENCE",
        "SHADOW_MICRO_NOISE": "MICRO_NOISE",
        "SHADOW_NO_BODY_CLOSE_BOS": "NO_BODY_CLOSE_BOS",
        "SHADOW_WICK_ONLY": "WICK_ONLY",
        "SHADOW_WRONG_BODY_DIRECTION": "WRONG_BODY_DIRECTION",
        "SHADOW_STALE": "STALE",
        "SHADOW_OUTSIDE_PARENT": "OUTSIDE_PARENT",
        "SHADOW_PROTECTION_BROKEN": "PROTECTION_BROKEN",
        "SHADOW_LOW_CAUSAL_QUALITY": "LOW_CAUSAL_QUALITY",
    }
    return mapping.get(value, "OTHER")


def _symbol_job(symbol_dir: str, second_touch_enabled: bool = False) -> dict[str, Any]:
    base = ROOT / "simulator_data" / "library" / symbol_dir
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    symbol = str(manifest["symbol"])
    m1 = pd.read_csv(base / "M1.csv")
    m5 = pd.read_csv(base / "M5.csv")
    config = load_config()
    candidates: list[dict[str, Any]] = []
    for direction in ("BULLISH", "BEARISH"):
        candidates.extend(scan_expert_m5_candidates(m5, direction=direction, symbol=symbol, timeframe="M5", sensitivity=config.engine_sensitivity, second_touch_enabled=second_touch_enabled))
    candidates.sort(key=lambda row: (int(row["entry_index"]), str(row["direction"])))
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in candidates:
        if str(row["setup_id"]) not in seen:
            unique.append(row); seen.add(str(row["setup_id"]))
    pairs: list[dict[str, Any]] = []
    funnel_events: list[dict[str, Any]] = []
    for candidate in unique:
        terminal_index = int(candidate["entry_index"])
        terminal_time = float(m5.iloc[terminal_index]["time"]) + 300.0
        prefix = m5.iloc[: terminal_index + 1]
        context = build_expert_htf_context(
            decision_candle_open_time=float(m5.iloc[terminal_index]["time"]),
            decision_timeframe_seconds=300,
            frame_data=CanonicalPipelineAdapter._resample_htf(prefix),
            sensitivity=config.engine_sensitivity,
            policy=config.htf_policy,
            allow_single_strong=config.allow_single_strong_htf,
        )
        if not context.get("available") or context.get("approved_direction") != candidate["direction"]:
            continue
        try:
            parent = build_parent_contract(candidate=candidate, m5_data=prefix, symbol=symbol)
        except (KeyError, ValueError, IndexError):
            continue
        visible_m1 = m1[m1["time"].astype(float) + 60.0 <= terminal_time].reset_index(drop=True)
        baseline_report = find_m1_child_entry(parent=parent, m1_data=visible_m1, sensitivity=2, decision_time=terminal_time, permission_policy=COUNTER_CONFIRMED_ACTIVE, second_touch_enabled=second_touch_enabled)
        variant_report = find_m1_child_entry(parent=parent, m1_data=visible_m1, sensitivity=2, decision_time=terminal_time, permission_policy=EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE, second_touch_enabled=second_touch_enabled)
        baseline = arbitrate_first_valid_entry(parent=parent, m1_result=baseline_report, decision_time=terminal_time)
        variant = arbitrate_first_valid_entry(parent=parent, m1_result=variant_report, decision_time=terminal_time)
        b_entry = dict(baseline.get("entry") or {})
        s_entry = dict(variant.get("entry") or {})
        if not b_entry or not s_entry:
            continue
        review_end_time = min(float(m5.iloc[-1]["time"]) + 300.0, terminal_time + 80 * 300.0)
        b_out = _managed_outcome(symbol=symbol, entry=b_entry, owner=str(baseline["entry_owner"]), parent=parent, candidate=candidate, context=context, m1=m1, m5=m5, review_end_time=review_end_time)
        s_out = _managed_outcome(symbol=symbol, entry=s_entry, owner=str(variant["entry_owner"]), parent=parent, candidate=candidate, context=context, m1=m1, m5=m5, review_end_time=review_end_time)
        b_price = float(b_entry.get("entry_price", b_entry.get("price")))
        s_price = float(s_entry.get("entry_price", s_entry.get("price")))
        b_stop = float(b_entry["logical_stop"]); s_stop = float(s_entry["logical_stop"])
        b_distance = abs(b_price - b_stop); s_distance = abs(s_price - s_stop)
        b_time = float(b_entry["entry_time"]); s_time = float(s_entry["entry_time"])
        b_second_touch = deepcopy(
            b_entry.get("second_touch")
            or (candidate.get("second_touch") if baseline.get("entry_owner") == "M5" else None)
            or {}
        )
        s_second_touch = deepcopy(
            s_entry.get("second_touch")
            or (candidate.get("second_touch") if variant.get("entry_owner") == "M5" else None)
            or {}
        )
        same_parent = str(b_entry.get("parent_m5_setup_id", b_entry.get("parent_setup_id", candidate["setup_id"]))) == str(candidate["setup_id"])
        early_earned = bool(s_entry.get("early_permission_earned"))
        row = {
            "symbol": symbol, "setup_id": candidate["setup_id"], "sequence_id": candidate["setup_id"], "direction": candidate["direction"],
            "baseline_entry_exists": True, "baseline_entry_timeframe": baseline["entry_owner"], "baseline_entry_time": _iso(b_time), "baseline_entry_epoch": b_time, "baseline_entry_price": b_price, "baseline_logical_stop": b_stop, "baseline_stop_distance": b_distance,
            "s2b_entry_exists": True, "s2b_entry_timeframe": variant["entry_owner"], "s2b_entry_time": _iso(s_time), "s2b_entry_epoch": s_time, "s2b_entry_price": s_price, "s2b_logical_stop": s_stop, "s2b_stop_distance": s_distance,
            "minutes_entry_difference": round((b_time - s_time) / 60.0, 6), "price_entry_difference": round(s_price - b_price, 10), "stop_distance_difference": round(s_distance - b_distance, 10), "stop_distance_improvement_percent": round((b_distance - s_distance) / b_distance * 100.0, 6) if b_distance else 0.0,
            "same_parent_identity": same_parent, "same_direction": candidate["direction"] == parent["parent_direction"], "duplicate_first_entry_detected": False,
            "baseline_attempt1_exit_reason": b_out["attempt1_exit_reason"], "s2b_attempt1_exit_reason": s_out["attempt1_exit_reason"], "baseline_attempt1_final_r": b_out["attempt1_final_r"], "s2b_attempt1_final_r": s_out["attempt1_final_r"],
            "baseline_sequence_final_r": b_out["sequence_final_r"], "s2b_sequence_final_r": s_out["sequence_final_r"], "baseline_mfe_r": b_out["mfe_r"], "s2b_mfe_r": s_out["mfe_r"], "baseline_mae_r": b_out["mae_r"], "s2b_mae_r": s_out["mae_r"], "baseline_peak_r": b_out["peak_r"], "s2b_peak_r": s_out["peak_r"], "baseline_giveback_r": b_out["giveback_r"], "s2b_giveback_r": s_out["giveback_r"],
            "baseline_tp1_hit": b_out["tp1_hit"], "s2b_tp1_hit": s_out["tp1_hit"], "baseline_reentry_used": b_out["reentry_used"], "s2b_reentry_used": s_out["reentry_used"], "baseline_sequence_win_loss": b_out["sequence_win_loss"], "s2b_sequence_win_loss": s_out["sequence_win_loss"],
            "early_permission_earned": early_earned, "parent_armed_time": _iso(parent["armed_time"]), "parent_armed_epoch": parent["armed_time"], "parent_active_time": _iso(parent["active_time"]), "parent_active_epoch": parent["active_time"], "dominant_protection_level": parent["dominant_protection_level"],
            "fib_zero_index": parent["fib_zero_index"], "fib_zero_price": parent["fib_zero_price"], "fib_hundred_index": parent["fib_hundred_index"], "fib_hundred_price": parent["fib_hundred_price"], "fibonacci_zone": parent["fibonacci_zone"],
            "s2b_counter_index": s_entry.get("counter_structure_index"), "s2b_counter_price": s_entry.get("counter_structure_price"), "s2b_trigger_index": s_entry.get("failure_trigger_index"), "s2b_trigger_available_index": s_entry.get("failure_trigger_available_at_index"), "s2b_trigger_price": s_entry.get("failure_trigger_price"), "s2b_entry_index": s_entry.get("entry_index"), "s2b_quality_score": s_entry.get("m1_quality_score"), "s2b_grade": s_entry.get("grade"),
            "review_end_time": _iso(review_end_time), "review_end_epoch": review_end_time, "baseline_management": b_out, "s2b_management": s_out, "causal_valid": bool(b_out["causal_valid"] and s_out["causal_valid"] and same_parent), "order_api_called": False,
            "second_touch_enabled": second_touch_enabled,
            "baseline_second_touch": b_second_touch,
            "s2b_second_touch": s_second_touch,
            "baseline_second_touch_entry": bool(b_entry.get("second_touch_entry") or (baseline.get("entry_owner") == "M5" and candidate.get("second_touch_entry"))),
            "s2b_second_touch_entry": bool(s_entry.get("second_touch_entry") or (variant.get("entry_owner") == "M5" and candidate.get("second_touch_entry"))),
        }
        categories: list[str] = []
        if row["minutes_entry_difference"] > 0: categories += ["EARLY_BETTER", "EARLY_SAVED_LATE_ENTRY"]
        elif row["minutes_entry_difference"] == 0: categories.append("EARLY_SAME")
        if row["s2b_sequence_final_r"] < row["baseline_sequence_final_r"] - 0.05: categories.append("EARLY_WORSE")
        if row["s2b_sequence_win_loss"] == "WIN" and row["baseline_sequence_win_loss"] != "WIN": categories.append("EARLY_WON_BASELINE_LOST")
        if row["s2b_sequence_win_loss"] != "WIN" and row["baseline_sequence_win_loss"] == "WIN": categories += ["EARLY_LOST_BASELINE_WON", "EARLY_CREATED_EXTRA_STOP_OUT"]
        if row["s2b_sequence_win_loss"] == row["baseline_sequence_win_loss"] == "WIN": categories.append("BOTH_WON")
        if row["s2b_sequence_win_loss"] == row["baseline_sequence_win_loss"] == "LOSS": categories.append("BOTH_LOST")
        categories.append("EARLY_STOP_WIDER" if s_distance > b_distance else "EARLY_STOP_TIGHTER" if s_distance < b_distance else "EARLY_STOP_SAME")
        if row["baseline_reentry_used"] != row["s2b_reentry_used"]: categories.append("EARLY_CHANGED_REENTRY_SEQUENCE")
        row["comparison_buckets"] = sorted(set(categories))
        pairs.append(row)
        shadow = evaluate_armed_to_active_shadow(parent=parent, m1_data=visible_m1, sensitivity=2)
        for event in shadow.get("events", []):
            funnel_events.append({"symbol": symbol, "setup_id": candidate["setup_id"], "direction": candidate["direction"], "state": _funnel_state(str(event["state"])), "raw_state": event["state"], "event_index": event.get("trigger_available_at_index"), "event_time": _iso(event.get("trigger_available_time")), "event_epoch": event.get("trigger_available_time"), "armed_time": _iso(parent["armed_time"]), "active_time": _iso(parent["active_time"]), "reason": [r.get("state") for r in event.get("rejections", [])], "order_api_called": False})
    return {"symbol": symbol, "candidate_count": len(unique), "pairs": pairs, "funnel_events": funnel_events, "second_touch_enabled": second_touch_enabled}


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _panel(draw: ImageDraw.ImageDraw, frame: pd.DataFrame, box: tuple[int, int, int, int], *, seconds: int, markers: list[tuple[float, str, str]], levels: list[tuple[float, str, str]], decision_time: float) -> None:
    left, top, right, bottom = box
    draw.rectangle(box, fill="#edf4fb", outline="#9db6d1", width=2)
    if frame.empty:
        draw.text((left + 20, top + 20), "NO SYNCHRONIZED DATA", fill="#8b1e3f", font=_font(22, True)); return
    low = min(float(frame["low"].min()), *(value for value, _, _ in levels)) if levels else float(frame["low"].min())
    high = max(float(frame["high"].max()), *(value for value, _, _ in levels)) if levels else float(frame["high"].max())
    pad = max((high - low) * 0.08, 1e-9); low -= pad; high += pad
    plot_left, plot_right, plot_top, plot_bottom = left + 72, right - 20, top + 26, bottom - 38
    def y(value: float) -> int: return int(plot_bottom - (float(value) - low) / max(high - low, 1e-12) * (plot_bottom - plot_top))
    def x(index: int) -> int: return int(plot_left + (index + 0.5) / max(len(frame), 1) * (plot_right - plot_left))
    for grid in range(5):
        yy = int(plot_top + grid * (plot_bottom - plot_top) / 4); draw.line((plot_left, yy, plot_right, yy), fill="#d4e1ee", width=1)
        value = high - grid * (high - low) / 4; draw.text((left + 4, yy - 8), f"{value:.5f}", fill="#52677e", font=_font(12))
    close_times = frame["time"].astype(float) + seconds
    decision_index = int(close_times.searchsorted(decision_time, side="left"))
    if 0 <= decision_index < len(frame): draw.rectangle((x(decision_index), plot_top, plot_right, plot_bottom), fill="#e5e9ee"); draw.text((x(decision_index) + 5, plot_bottom - 22), "POST-DECISION REVIEW ONLY", fill="#6b7280", font=_font(12, True))
    candle_width = max(3, int((plot_right - plot_left) / max(len(frame), 1) * 0.62))
    for index, candle in enumerate(frame.itertuples(index=False)):
        xx = x(index); color = "#0f9d8b" if float(candle.close) >= float(candle.open) else "#c84f72"
        draw.line((xx, y(candle.low), xx, y(candle.high)), fill=color, width=2)
        y1, y2 = sorted((y(candle.open), y(candle.close))); draw.rectangle((xx - candle_width // 2, y1, xx + candle_width // 2, max(y1 + 2, y2)), fill=color)
    for value, label, color in levels:
        yy = y(value); draw.line((plot_left, yy, plot_right, yy), fill=color, width=2); draw.text((plot_left + 5, yy - 17), f"{label} {value:.5f}", fill=color, font=_font(13, True))
    used_y: list[int] = []
    for epoch, label, color in markers:
        index = int(close_times.searchsorted(float(epoch), side="left"))
        if 0 <= index < len(frame):
            xx = x(index); draw.line((xx, plot_top, xx, plot_bottom), fill=color, width=3)
            label_y = plot_top + 4 + 20 * sum(abs(xx - prior) < 110 for prior in used_y); draw.text((min(xx + 4, plot_right - 170), label_y), label, fill=color, font=_font(13, True)); used_y.append(xx)


def _chart(number: int, row: dict[str, Any], data_dir: Path) -> str:
    m5 = pd.read_csv(data_dir / "M5.csv"); m1 = pd.read_csv(data_dir / "M1.csv")
    armed = float(row["parent_armed_epoch"]); active = float(row["parent_active_epoch"]); btime = float(row.get("baseline_entry_epoch") or active); stime = float(row.get("s2b_entry_epoch") or armed); end = float(row.get("review_end_epoch") or max(btime, stime) + 3600)
    m5_frame = m5[(m5["time"] + 300 >= armed - 35 * 300) & (m5["time"] + 300 <= min(end, max(btime, stime) + 25 * 300))].reset_index(drop=True)
    m1_frame = m1[(m1["time"] + 60 >= armed - 35 * 60) & (m1["time"] + 60 <= min(end, max(btime, stime) + 30 * 60))].reset_index(drop=True)
    rejected = str(row.get("visual_group", "")).startswith("L_REJECTED_")
    decision_time = float(row.get("rejected_event_epoch") or stime) if rejected else stime
    image = Image.new("RGB", (1800, 1120), "#f3f7fb"); draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1800, 112), fill="#12345b")
    draw.text((28, 18), f"S2B #{number:02d} · {row.get('visual_group')} · {row['symbol']} · {row['direction']}", fill="white", font=_font(28, True))
    result_line = (f"EARLY PERMISSION NOT EARNED · {row.get('rejected_state')} · later candles are review-only" if rejected else f"Baseline {row.get('baseline_sequence_win_loss')} {row.get('baseline_sequence_final_r')}R  |  S2B {row.get('s2b_sequence_win_loss')} {row.get('s2b_sequence_final_r')}R")
    draw.text((28, 60), f"{result_line}  |  Research only · zero orders", fill="#d8e8f8", font=_font(18))
    draw.text((28, 126), f"SETUP {row['setup_id']}  ·  ARMED ≠ ACTIVE  ·  entry difference {row['minutes_entry_difference']:.1f} min  ·  stop difference {row['stop_distance_difference']:.5f}", fill="#12345b", font=_font(17, True))
    markers = [(armed, "PARENT ARMED", "#7b61ff"), (active, "NORMAL ACTIVE", "#ef8f00"), (btime, "BASELINE ENTRY", "#2563eb")]
    markers.append((decision_time, f"REJECTED: {row.get('rejected_state')}" if rejected else "EARLY PERMISSION + S2B ENTRY", "#b4234d" if rejected else "#008b75"))
    _panel(draw, m5_frame, (24, 168, 1776, 600), seconds=300, markers=markers, levels=[(float(row["dominant_protection_level"]), "DOMINANT PROTECTION", "#008b75"), (float(row["fib_zero_price"]), "FIB 0%", "#9a6b00"), (float(row["fib_hundred_price"]), "FIB 100%", "#9a6b00")], decision_time=decision_time)
    draw.text((42, 176), "UPPER · M5 PARENT / HTF STORY", fill="#12345b", font=_font(16, True))
    m1_levels = [(float(row["baseline_logical_stop"]), "BASELINE STOP", "#2563eb")]
    if not rejected:
        m1_levels.insert(0, (float(row["s2b_logical_stop"]), "S2B LOGICAL STOP", "#b4234d"))
        if row.get("s2b_trigger_price") not in (None, ""): m1_levels.append((float(row["s2b_trigger_price"]), "M1 TRIGGER / BODY-CLOSE BOS", "#7b61ff"))
    _panel(draw, m1_frame, (24, 632, 1776, 1068), seconds=60, markers=markers, levels=m1_levels, decision_time=decision_time)
    draw.text((42, 640), "LOWER · M1 COUNTER → TRIGGER AVAILABLE → BODY-CLOSE BOS → EARNED PERMISSION", fill="#12345b", font=_font(16, True))
    draw.text((28, 1084), "All decision labels use candles closed by the green S2B line. Grey region is displayed only for outcome review.", fill="#52677e", font=_font(15, True))
    name = f"{number:02d}_{row['symbol'].replace('#','')}_{str(row['setup_id']).split('|')[-1]}_{row.get('visual_group','REVIEW')}.png".replace("/", "_")
    image.save(VISUALS / name, optimize=True)
    return name


def _choose_visuals(pairs: list[dict[str, Any]], funnel_events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    changed = [row for row in pairs if row["early_permission_earned"] and row["minutes_entry_difference"] > 0]
    criteria = {
        "A_TIMING_IMPROVED": lambda r: r["minutes_entry_difference"] > 0,
        "B_EARLY_WIN": lambda r: r["s2b_sequence_win_loss"] == "WIN",
        "C_EARLY_LOSS": lambda r: r["s2b_sequence_win_loss"] == "LOSS",
        "D_BASELINE_WIN_EARLY_LOSS": lambda r: r["baseline_sequence_win_loss"] == "WIN" and r["s2b_sequence_win_loss"] != "WIN",
        "E_EARLY_WIN_BASELINE_LOSS": lambda r: r["baseline_sequence_win_loss"] != "WIN" and r["s2b_sequence_win_loss"] == "WIN",
        "F_EARLY_STOP_WIDER": lambda r: r["s2b_stop_distance"] > r["baseline_stop_distance"],
        "G_EARLY_STOP_TIGHTER": lambda r: r["s2b_stop_distance"] < r["baseline_stop_distance"],
        "H_GER40": lambda r: r["symbol"] == "GER40Cash#",
        "I_US100": lambda r: r["symbol"] == "US100Cash#",
        "J_GOLD": lambda r: r["symbol"] == "GOLD#",
        "K_FOREX": lambda r: r["symbol"] in FOREX,
    }
    chosen: list[dict[str, Any]] = []; used: set[str] = set(); coverage: dict[str, str] = {}
    for group, predicate in criteria.items():
        matches = sorted((r for r in changed if predicate(r)), key=lambda r: (r["symbol"], r["setup_id"]))
        coverage[group] = "OBSERVED" if matches else "NOT_OBSERVED_IN_AVAILABLE_DATA"
        if matches:
            row = next((r for r in matches if r["setup_id"] not in used), matches[0]); copy = deepcopy(row); copy["visual_group"] = group; copy["reason_selected"] = group.replace("_", " "); chosen.append(copy); used.add(row["setup_id"])
    for row in sorted(changed, key=lambda r: (-abs(float(r["s2b_sequence_final_r"]) - float(r["baseline_sequence_final_r"])), r["symbol"], r["setup_id"])):
        if len(chosen) >= 25: break
        if row["setup_id"] not in used:
            copy = deepcopy(row); copy["visual_group"] = "PAIRED_UNFILTERED_REVIEW"; copy["reason_selected"] = "Deterministic largest absolute paired outcome difference"; chosen.append(copy); used.add(row["setup_id"])
    rejected = sorted((r for r in funnel_events if r["state"] != "EARLY_VALID"), key=lambda r: (r["state"], r["symbol"], r["setup_id"], str(r["event_time"])))
    rejected_states: set[str] = set()
    pair_by_id = {r["setup_id"]: r for r in pairs}
    for event in rejected:
        if len(chosen) >= 30: break
        if event["state"] in rejected_states or event["setup_id"] not in pair_by_id: continue
        copy = deepcopy(pair_by_id[event["setup_id"]]); copy["visual_group"] = f"L_REJECTED_{event['state']}"; copy["reason_selected"] = f"Rejected pre-active event: {event['state']} — {event['reason']}"; copy["rejected_state"] = event["state"]; copy["rejected_event_epoch"] = event.get("event_epoch"); chosen.append(copy); rejected_states.add(event["state"])
    for row in sorted(pairs, key=lambda r: (r["symbol"], r["setup_id"])):
        if len(chosen) >= 30: break
        if row["setup_id"] not in used:
            copy = deepcopy(row); copy["visual_group"] = "L_OR_BASELINE_REVIEW"; copy["reason_selected"] = "Deterministic coverage fill without outcome selection"; chosen.append(copy); used.add(row["setup_id"])
    coverage["L_REJECTED"] = "OBSERVED" if rejected_states else "NOT_OBSERVED_IN_AVAILABLE_DATA"
    return chosen[:30], coverage


def _summary_for(rows: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
    entries = [row for row in rows if row[f"{prefix}_entry_exists"]]
    sequence = [float(row[f"{prefix}_sequence_final_r"]) for row in entries]
    attempts = [float(row[f"{prefix}_attempt1_final_r"]) for row in entries]
    wins = sum(v > 1e-9 for v in sequence); losses = sum(v < -1e-9 for v in sequence); flat = len(sequence) - wins - losses
    gross_win = sum(v for v in sequence if v > 0); gross_loss = abs(sum(v for v in sequence if v < 0))
    return {
        "unique_parent_setups": len({row["setup_id"] for row in rows}), "first_entries": len(entries), "m1_first_entries": sum(row[f"{prefix}_entry_timeframe"] == "M1" for row in entries), "m5_first_entries": sum(row[f"{prefix}_entry_timeframe"] == "M5" for row in entries), "reentries": sum(bool(row[f"{prefix}_reentry_used"]) for row in entries), "total_sequences": len(entries),
        "wins": wins, "losses": losses, "flat": flat, "win_rate": wins / len(sequence) if sequence else 0.0, "median_attempt_r": statistics.median(attempts) if attempts else None, "mean_attempt_r": statistics.mean(attempts) if attempts else None, "median_sequence_r": statistics.median(sequence) if sequence else None, "mean_sequence_r": statistics.mean(sequence) if sequence else None, "profit_factor_r": gross_win / gross_loss if gross_loss else None, "expectancy_r": statistics.mean(sequence) if sequence else None,
        "median_mfe_r": statistics.median(float(r[f"{prefix}_mfe_r"]) for r in entries) if entries else None, "median_mae_r": statistics.median(float(r[f"{prefix}_mae_r"]) for r in entries) if entries else None, "median_peak_r": statistics.median(float(r[f"{prefix}_peak_r"]) for r in entries) if entries else None, "median_giveback_r": statistics.median(float(r[f"{prefix}_giveback_r"]) for r in entries) if entries else None, "winner_to_loser_reversals": sum(float(r[f"{prefix}_peak_r"]) > 0 and float(r[f"{prefix}_sequence_final_r"]) < 0 for r in entries), "tp1_touches": sum(bool(r[f"{prefix}_tp1_hit"]) for r in entries), "median_entry_latency_minutes_from_armed": statistics.median((float(r[f"{prefix}_entry_epoch"]) - float(r["parent_armed_epoch"])) / 60 for r in entries) if entries else None, "median_stop_distance": statistics.median(float(r[f"{prefix}_stop_distance"]) for r in entries) if entries else None,
    }


def _run_tests() -> list[dict[str, Any]]:
    commands = [
        [sys.executable, "-m", "unittest", "tests.test_s2b_earned_early_permission", "-v"],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        [sys.executable, "-m", "unittest", "discover", "-s", "simulator/tests", "-v"],
    ]
    sections: list[str] = []; results: list[dict[str, Any]] = []
    for command in commands:
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        sections.append(f"$ {' '.join(command)}\n{completed.stdout}{completed.stderr}")
        results.append({"command": command, "returncode": completed.returncode, "state": "PASS" if completed.returncode == 0 else "FAIL"})
    (OUT / "full_test_results.txt").write_text("\n\n".join(sections), encoding="utf-8")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--workers", type=int, default=3); parser.add_argument("--run-tests", action="store_true"); args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True); VISUALS.mkdir(parents=True, exist_ok=True)
    directories = sorted(path.name for path in (ROOT / "simulator_data" / "library").iterdir() if path.is_dir() and (path / "manifest.json").exists())
    jobs: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as executor:
        pending = {executor.submit(_symbol_job, name): name for name in directories}
        for future in as_completed(pending):
            job = future.result(); jobs.append(job); print(f"S2B {job['symbol']}: pairs={len(job['pairs'])} funnel={len(job['funnel_events'])}", flush=True)
    jobs.sort(key=lambda r: r["symbol"])
    pairs = sorted((row for job in jobs for row in job["pairs"]), key=lambda r: (r["symbol"], r["setup_id"]))
    funnel_events = sorted((row for job in jobs for row in job["funnel_events"]), key=lambda r: (r["symbol"], r["setup_id"], str(r["event_time"])))
    event_counts = Counter(r["state"] for r in funnel_events); setup_counts: dict[str, set[str]] = defaultdict(set)
    for row in funnel_events: setup_counts[row["state"]].add(row["setup_id"])
    funnel = [{"state": state, "events": event_counts[state], "unique_setups": len(setup_counts[state])} for state in sorted(set(event_counts) | {"EARLY_VALID", "NO_COUNTER_STRUCTURE", "INCOMPLETE_SEQUENCE", "MICRO_NOISE", "NO_BODY_CLOSE_BOS", "WICK_ONLY", "WRONG_BODY_DIRECTION", "STALE", "OUTSIDE_PARENT", "PROTECTION_BROKEN", "LOW_CAUSAL_QUALITY", "PARENT_SUPERSEDED", "OTHER"})]
    per_symbol = []
    for symbol in (*AVAILABLE_SYMBOLS, *MISSING_SYMBOLS):
        subset = [r for r in pairs if r["symbol"] == symbol]
        if not subset:
            per_symbol.append({"symbol": symbol, "state": "DATA_NOT_AVAILABLE_FOR_S2B", "parent_setups": 0}); continue
        b = _summary_for(subset, "baseline"); s = _summary_for(subset, "s2b")
        per_symbol.append({"symbol": symbol, "state": "AVAILABLE", "parent_setups": len(subset), "earned_early_setups": sum(r["early_permission_earned"] for r in subset), "baseline_win_rate": b["win_rate"], "s2b_win_rate": s["win_rate"], "baseline_expectancy_r": b["expectancy_r"], "s2b_expectancy_r": s["expectancy_r"], "paired_expectancy_change_r": (s["expectancy_r"] or 0) - (b["expectancy_r"] or 0), "baseline_median_stop": b["median_stop_distance"], "s2b_median_stop": s["median_stop_distance"]})
    visuals, visual_coverage = _choose_visuals(pairs, funnel_events)
    dir_by_symbol = {json.loads((ROOT / "simulator_data" / "library" / d / "manifest.json").read_text(encoding="utf-8"))["symbol"]: ROOT / "simulator_data" / "library" / d for d in directories}
    visual_manifest: list[dict[str, Any]] = []
    for number, row in enumerate(visuals, 1):
        name = _chart(number, row, dir_by_symbol[row["symbol"]])
        payload = {key: value for key, value in row.items() if not isinstance(value, (dict, list))}
        (VISUALS / name.replace(".png", ".json")).write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        visual_manifest.append({"review_number": number, "symbol": row["symbol"], "setup_id": row["setup_id"], "baseline_outcome": row["baseline_sequence_win_loss"], "s2b_outcome": row["s2b_sequence_win_loss"], "classification": row["visual_group"], "entry_timing_difference_minutes": row["minutes_entry_difference"], "stop_difference": row["stop_distance_difference"], "reason_selected": row["reason_selected"], "chart_file": f"visuals/{name}", "manual_verdict": "", "manual_reason": ""})
    articles = "\n".join(f"<article><h2>{r['review_number']:02d} · {html.escape(r['symbol'])} · {html.escape(r['classification'])}</h2><p>{html.escape(str(r['reason_selected']))}</p><img src='{html.escape(r['chart_file'])}' loading='lazy'></article>" for r in visual_manifest)
    (OUT / "s2b_visual_review.html").write_text(f"<!doctype html><meta charset='utf-8'><title>S2B review</title><style>body{{font-family:Arial;background:#edf4fb;color:#12345b;margin:0}}header{{background:#12345b;color:white;padding:24px;position:sticky;top:0;z-index:2}}main{{max-width:1500px;margin:auto}}article{{background:white;margin:24px;padding:18px;border-radius:10px}}img{{width:100%;border:1px solid #abc}}p{{font-size:16px}}</style><header><h1>S2B Earned Early M1 Permission · 30 deterministic paired reviews</h1><p>Research only · closed candles · decision/future boundary shown · zero orders</p></header><main>{articles}</main>", encoding="utf-8")
    for event in funnel_events:
        event["state_event_count"] = event_counts[event["state"]]
        event["state_unique_setup_count"] = len(setup_counts[event["state"]])
    _csv(OUT / "baseline_vs_early_setup.csv", pairs); _csv(OUT / "early_permission_funnel.csv", funnel_events); _csv(OUT / "early_permission_funnel_summary.csv", funnel); _csv(OUT / "per_symbol_comparison.csv", per_symbol); _csv(OUT / "early_entry_trade_outcomes.csv", [r for r in pairs if r["early_permission_earned"]]); _csv(OUT / "sequence_outcomes.csv", [{"symbol": r["symbol"], "setup_id": r["setup_id"], "baseline_sequence_final_r": r["baseline_sequence_final_r"], "s2b_sequence_final_r": r["s2b_sequence_final_r"], "baseline_reentry_used": r["baseline_reentry_used"], "s2b_reentry_used": r["s2b_reentry_used"], "buckets": r["comparison_buckets"]} for r in pairs]); _csv(OUT / "visual_manifest.csv", visual_manifest)
    baseline_summary = _summary_for(pairs, "baseline"); s2b_summary = _summary_for(pairs, "s2b")
    early_rows = [r for r in pairs if r["early_permission_earned"]]
    worse = sum(float(r["s2b_sequence_final_r"]) < float(r["baseline_sequence_final_r"]) - 0.05 for r in early_rows)
    better = sum(float(r["s2b_sequence_final_r"]) > float(r["baseline_sequence_final_r"]) + 0.05 for r in early_rows)
    expectancy_change = (s2b_summary["expectancy_r"] or 0) - (baseline_summary["expectancy_r"] or 0)
    verdict = "RESEARCH_VALIDATED" if early_rows and expectancy_change >= 0.05 and better >= worse else "RESEARCH_REJECTED" if early_rows and expectancy_change <= -0.05 else "INCONCLUSIVE"
    test_results = _run_tests() if args.run_tests else []
    if not args.run_tests: (OUT / "full_test_results.txt").write_text("Tests not requested in this invocation.\n", encoding="utf-8")
    summary = {"phase": "S2B", "verdict": verdict, "maximum_readiness": "READY_FOR_STEVE_VISUAL_REVIEW", "baseline_policy": COUNTER_CONFIRMED_ACTIVE, "s2b_policy": EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE, "candidate_setups_scanned": sum(j["candidate_count"] for j in jobs), "paired_htf_aligned_setups": len(pairs), "preactive_events_evaluated": len(funnel_events), "preactive_unique_setups": len({r["setup_id"] for r in funnel_events}), "earned_early_events": event_counts.get("EARLY_VALID", 0), "earned_early_unique_setups": len({r["setup_id"] for r in funnel_events if r["state"] == "EARLY_VALID"}), "committed_earned_early_setups": len(early_rows), "baseline": baseline_summary, "s2b": s2b_summary, "paired_better": better, "paired_worse": worse, "visual_count": len(visual_manifest), "visual_group_coverage": visual_coverage, "available_symbols": list(AVAILABLE_SYMBOLS), "unavailable_symbols": {s: "DATA_NOT_AVAILABLE_FOR_S2B" for s in MISSING_SYMBOLS}, "tests": test_results, "baseline_default_unchanged": True, "thresholds_changed": False, "quality_points_redistributed": False, "live_demo_enabled": False, "order_api_called": False}
    (OUT / "s2b_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    manifest = {"phase": "S2B", "created_at": datetime.now(timezone.utc).isoformat(), "python": sys.version, "platform": platform.platform(), "command": f'"{sys.executable}" tools/run_s2b_research.py --workers {args.workers}' + (" --run-tests" if args.run_tests else ""), "input_library_hash": _sha(ROOT / "simulator_data" / "library" / "index.json"), "policies": [COUNTER_CONFIRMED_ACTIVE, EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE], "summary": summary, "outputs": {}, "research_only": True, "order_api_called": False}
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path.name != "reproducibility_manifest.json": manifest["outputs"][str(path.relative_to(OUT))] = {"bytes": path.stat().st_size, "sha256": _sha(path)}
    (OUT / "reproducibility_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if all(r["state"] == "PASS" for r in test_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
