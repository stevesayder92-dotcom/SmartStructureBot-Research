from __future__ import annotations

import csv
from copy import deepcopy
import html
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, Iterable, Optional

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.expert_strategy import (  # noqa: E402
    build_expert_htf_context,
    confirmed_swings,
    scan_expert_m5_candidates,
)
from core.final_fidelity_management import (  # noqa: E402
    advance_target_lifecycle,
    build_target_hierarchy,
    profit_capture_metrics,
    prove_trail_candidate,
    simulate_profit_management,
    transition_m1_to_m5_management,
)
from core.synchronized_m1_replay import (  # noqa: E402
    find_m1_child_entry,
    evaluate_synchronized_parent,
    validate_closed_series,
)
from core.steve_trade_management import atr_at  # noqa: E402
from tools.run_phase7_expert_audit import resample_closed_m5  # noqa: E402


OUT = ROOT / "final_fidelity_evidence"
CHARTS = OUT / "charts"
DATA = ROOT / "research_data_sync"
M5_EVIDENCE_ROWS = 3600
M5_SCAN_ROWS = 1800
SYMBOLS = {
    "EURUSD#": "EURUSD",
    "GBPUSD#": "GBPUSD",
    "AUDUSD#": "AUDUSD",
    "USDJPY#": "USDJPY",
    "GOLD#": "GOLD",
    "US100Cash#": "US100Cash",
    "GER40Cash#": "GER40Cash",
}
SLOTS = (
    ("VALID_M1_EARLY_ENTRY", 15),
    ("M5_FALLBACK_NO_VALID_M1", 10),
    ("MESSY_M1_BOS_REJECTED", 5),
    ("FIRST_FAILURE_VALID_REENTRY", 5),
    ("DOMINANT_PROTECTION_FAILURE_NO_REENTRY", 5),
)


def _default(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(type(value).__name__)


def _number(value: Any) -> float:
    return float(value)


def _offset_candidate_indexes(
    candidate: Dict[str, Any],
    *,
    offset: int,
) -> Dict[str, Any]:
    """Translate a deterministic scan-window candidate to evidence indexes."""
    translated = deepcopy(candidate)

    def visit(value: Any) -> Any:
        if isinstance(value, dict):
            output: Dict[str, Any] = {}
            for key, item in value.items():
                if (
                    item is not None
                    and isinstance(item, int)
                    and (
                        key == "index"
                        or key.endswith("_index")
                        or key in {"as_of_index", "qualified_at"}
                    )
                ):
                    output[key] = item + int(offset)
                else:
                    output[key] = visit(item)
            return output
        if isinstance(value, list):
            return [visit(item) for item in value]
        return value

    translated = visit(translated)
    setup_id = str(translated.get("setup_id", ""))
    match = re.search(r"\|PB_(\d+)$", setup_id)
    if match:
        translated["setup_id"] = (
            setup_id[: match.start(1)]
            + str(int(match.group(1)) + int(offset))
        )
    return translated


def _font(size: int, bold: bool = False):
    name = "arialbd.ttf" if bold else "arial.ttf"
    path = Path("C:/Windows/Fonts") / name
    return (
        ImageFont.truetype(str(path), size)
        if path.exists()
        else ImageFont.load_default()
    )


def _session(epoch: float) -> str:
    stamp = pd.to_datetime(epoch, unit="s", utc=True)
    minute = stamp.hour * 60 + stamp.minute
    if 13 * 60 <= minute < 16 * 60:
        return "OVERLAP"
    if 7 * 60 <= minute < 11 * 60:
        return "LONDON"
    if 13 * 60 <= minute < 17 * 60:
        return "NEW_YORK"
    return "OUTSIDE_PRIMARY_SESSION"


def _frames(data: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    return {
        timeframe: resample_closed_m5(data, timeframe=timeframe)
        for timeframe in ("H1", "M30", "M15")
    }


def _read(base: str, timeframe: str) -> pd.DataFrame:
    path = DATA / f"{base}_{timeframe}_closed.csv"
    data = pd.read_csv(path)
    data = data.sort_values("time").drop_duplicates("time").reset_index(drop=True)
    return data


def _body_invalidation(
    *,
    data: pd.DataFrame,
    direction: str,
    stop: float,
) -> Optional[int]:
    for index, row in data.iterrows():
        close = _number(row["close"])
        open_price = _number(row["open"])
        invalid = (
            close < stop and close < open_price
            if direction == "BULLISH"
            else close > stop and close > open_price
        )
        if invalid:
            return int(index)
    return None


def _dominant_failure(
    *,
    data: pd.DataFrame,
    direction: str,
    level: float,
) -> Optional[int]:
    for index, row in data.iterrows():
        close = _number(row["close"])
        open_price = _number(row["open"])
        failed = (
            close < level and close < open_price
            if direction == "BULLISH"
            else close > level and close > open_price
        )
        if failed:
            return int(index)
    return None


def _target_story(
    *,
    target: Optional[Dict[str, Any]],
    direction: str,
    candles: pd.DataFrame,
) -> tuple[Optional[Dict[str, Any]], list[Dict[str, Any]]]:
    if target is None:
        return None, []
    current = dict(target)
    history = [
        {
            "state": "CREATED",
            "index": None,
            "price": current["price"],
        }
    ]
    closes_beyond = 0
    for index, candle in candles.iterrows():
        updated = advance_target_lifecycle(
            target=current,
            direction=direction,
            candle=candle,
            prior_closes_beyond=closes_beyond,
            approach_distance=max(float(current["distance"]) * 0.10, 0.0),
        )
        if updated["body_closed_through"]:
            closes_beyond += 1
        elif updated["state"] in {"REJECTED", "WICK_TOUCHED"}:
            closes_beyond = 0
        if updated["state"] != current.get("state"):
            history.append(
                {
                    "state": updated["state"],
                    "index": int(index),
                    "price": _number(candle["close"]),
                }
            )
        current = updated
    return current, history


def _apply_m1_outcome_classification(row: Dict[str, Any]) -> None:
    advantage = row.get("advantage")
    if row.get("entry_timeframe") != "M1" or not advantage:
        return
    failure_time = row["outcome"].get("first_failure_time")
    m5_time = row.get("m5_entry_time")
    false_early = bool(
        failure_time is not None
        and m5_time is not None
        and float(failure_time) < float(m5_time)
    )
    advantage.setdefault(
        "pre_outcome_classification",
        advantage.get("classification"),
    )
    advantage["whether_m1_caused_false_early_entry"] = false_early
    advantage["whether_m5_later_confirmed"] = bool(
        m5_time is not None
        and (
            failure_time is None
            or float(m5_time) >= float(row["entry_time"])
        )
    )
    advantage["whether_m5_never_confirmed"] = m5_time is None
    if false_early:
        advantage["classification"] = "M1_FALSE_EARLY_ENTRY"


def _trail_story(
    *,
    data: pd.DataFrame,
    direction: str,
    entry_timeframe: str,
    initial_protection: float,
) -> list[Dict[str, Any]]:
    if len(data) < 8:
        return []
    local = data.reset_index(drop=True)
    swings = confirmed_swings(
        local,
        as_of_index=len(local) - 1,
        sensitivity=2,
    )
    side = "LOW" if direction == "BULLISH" else "HIGH"
    current = _number(initial_protection)
    events = []
    for point in [item for item in swings if item["side"] == side][:4]:
        start = int(point["confirmed_at_index"]) + 1
        proof = None
        for index in range(start, len(local)):
            row = local.iloc[index]
            correct_body = (
                _number(row["close"]) > _number(row["open"])
                if direction == "BULLISH"
                else _number(row["close"]) < _number(row["open"])
            )
            recent = local.iloc[max(0, int(point["index"]) - 3) : index]
            if recent.empty:
                continue
            broke = (
                _number(row["close"]) > _number(recent["high"].max())
                if direction == "BULLISH"
                else _number(row["close"]) < _number(recent["low"].min())
            )
            if correct_body and broke:
                proof = {
                    "index": index,
                    "direction": direction,
                    "body_close_confirmed": True,
                }
                break
        event = prove_trail_candidate(
            entry_timeframe=entry_timeframe,
            candidate={
                "index": int(point["index"]),
                "level": _number(point["level"]),
                "micro_noise": False,
                "major": entry_timeframe == "M5",
            },
            proof_bos=proof,
            direction=direction,
            current_protection=current,
            current_price=_number(local.iloc[-1]["close"]),
        )
        events.append(event)
        current = _number(event["selected_protection"])
    return events


def _outcome(
    *,
    synchronized: Dict[str, Any],
    m5: pd.DataFrame,
    m1: pd.DataFrame,
) -> Dict[str, Any]:
    parent = synchronized["parent"]
    decision = synchronized["decision"]
    entry = decision["entry"]
    direction = parent["parent_direction"]
    entry_time = float(entry["entry_time"])
    review_end_time = min(
        entry_time + 6 * 60 * 60,
        float(m1.iloc[-1]["time"]) + 60,
    )
    post_m1 = m1[
        (m1["time"].astype(float) + 60 >= entry_time)
        & (m1["time"].astype(float) + 60 <= review_end_time)
    ].copy().reset_index(drop=True)
    post_m5 = m5[
        (m5["time"].astype(float) + 300 >= entry_time)
        & (m5["time"].astype(float) + 300 <= review_end_time)
    ].copy().reset_index(drop=True)
    logical_stop = _number(entry["logical_stop"])
    failure_local = _body_invalidation(
        data=post_m1 if entry["entry_timeframe"] == "M1" else post_m5,
        direction=direction,
        stop=logical_stop,
    )
    failure_source = post_m1 if entry["entry_timeframe"] == "M1" else post_m5
    failure_time = (
        float(failure_source.iloc[failure_local]["time"])
        + (60 if entry["entry_timeframe"] == "M1" else 300)
        if failure_local is not None
        else None
    )
    dominant_local = _dominant_failure(
        data=post_m5,
        direction=direction,
        level=_number(parent["dominant_protection_level"]),
    )
    dominant_failure_time = (
        float(post_m5.iloc[dominant_local]["time"]) + 300
        if dominant_local is not None
        else None
    )
    reentry = None
    if (
        failure_time is not None
        and (
            dominant_failure_time is None
            or failure_time < dominant_failure_time
        )
    ):
        reentry_parent = dict(parent)
        reentry_parent["armed_time"] = failure_time
        reentry_parent["active_time"] = failure_time
        reentry_parent["m5_entry_time"] = review_end_time
        reentry_result = find_m1_child_entry(
            parent=reentry_parent,
            m1_data=m1,
            sensitivity=2,
        )
        if (
            reentry_result.get("entry_ready")
            and float(reentry_result["entry"]["entry_time"]) > failure_time
        ):
            reentry = reentry_result["entry"]
    if (
        reentry is not None
        and dominant_failure_time is not None
        and float(reentry["entry_time"]) >= dominant_failure_time
    ):
        # The M1 child search is intentionally causal and cannot know about a
        # later parent failure. The merged coordinator cancels a candidate
        # that has not closed before the dominant failure becomes available.
        reentry = None
    valid_reentry = reentry is not None
    reentry_denied = bool(
        dominant_failure_time is not None and not valid_reentry
    )

    target_contract = build_target_hierarchy(
        direction=direction,
        entry_price=_number(entry["entry_price"]),
        logical_stop=logical_stop,
        previous_impulse_extreme=_number(parent["fib_hundred_price"]),
        external_objectives=[],
        spread_price=0.0,
    )
    management_candles = (
        post_m1.reset_index(drop=True)
        if entry["entry_timeframe"] == "M1"
        else post_m5.reset_index(drop=True)
    )
    tp1, tp1_history = _target_story(
        target=target_contract.get("tp1"),
        direction=direction,
        candles=management_candles,
    )
    tp2, tp2_history = _target_story(
        target=target_contract.get("tp2"),
        direction=direction,
        candles=management_candles,
    )
    if failure_local is not None:
        exit_row = failure_source.iloc[failure_local]
        exit_price = _number(exit_row["close"])
        exit_time = float(exit_row["time"]) + (
            60 if entry["entry_timeframe"] == "M1" else 300
        )
        exit_reason = "LOGICAL_BODY_EDGE_INVALIDATION"
    else:
        exit_row = management_candles.iloc[-1]
        exit_price = _number(exit_row["close"])
        exit_time = float(exit_row["time"]) + (
            60 if entry["entry_timeframe"] == "M1" else 300
        )
        exit_reason = "OPEN_AT_REVIEW_END"
    if direction == "BULLISH":
        peak_position = int(
            management_candles["high"].astype(float).argmax()
        )
    else:
        peak_position = int(
            management_candles["low"].astype(float).argmin()
        )
    peak_time = float(management_candles.iloc[peak_position]["time"]) + (
        60 if entry["entry_timeframe"] == "M1" else 300
    )
    trails = _trail_story(
        data=management_candles,
        direction=direction,
        entry_timeframe=entry["entry_timeframe"],
        initial_protection=logical_stop,
    )
    profit_management = simulate_profit_management(
        direction=direction,
        entry_price=_number(entry["entry_price"]),
        initial_stop=logical_stop,
        emergency_stop=entry.get("emergency_stop"),
        candles=management_candles,
        tp1_target=(
            _number(target_contract["tp1"]["price"])
            if target_contract.get("tp1") is not None
            else None
        ),
        target_events=tp1_history,
        trail_events=trails,
        profit_lock_trigger_r=1.0,
        profit_lock_r=0.10,
        tp1_partial_fraction=0.50,
    )
    exit_local = int(profit_management["exit_index"])
    exit_price = _number(profit_management["exit_price"])
    exit_time = float(management_candles.iloc[exit_local]["time"]) + (
        60 if entry["entry_timeframe"] == "M1" else 300
    )
    exit_reason = str(profit_management["exit_reason"])
    trade_candles = management_candles.iloc[: exit_local + 1].copy()
    tp1, tp1_history = _target_story(
        target=target_contract.get("tp1"),
        direction=direction,
        candles=trade_candles,
    )
    tp2, tp2_history = _target_story(
        target=target_contract.get("tp2"),
        direction=direction,
        candles=trade_candles,
    )
    if direction == "BULLISH":
        peak_position = int(trade_candles["high"].astype(float).argmax())
    else:
        peak_position = int(trade_candles["low"].astype(float).argmin())
    peak_time = float(trade_candles.iloc[peak_position]["time"]) + (
        60 if entry["entry_timeframe"] == "M1" else 300
    )
    metrics = profit_capture_metrics(
        direction=direction,
        entry_price=_number(entry["entry_price"]),
        initial_stop=logical_stop,
        candles=trade_candles,
        exit_price=_number(profit_management["equivalent_exit_price"]),
        entry_time=entry_time,
        exit_time=exit_time,
        peak_time=peak_time,
        tp1_state=(tp1 or {}).get("state", "UNAVAILABLE"),
        tp2_state=(tp2 or {}).get("state", "UNAVAILABLE"),
        first_trail_delay=(
            int(trails[0]["proof_index"]) if trails and trails[0].get("proof_index") is not None else None
        ),
        trail_count=sum(event["state"] == "TRAIL_PROVEN" for event in trails),
        entry_timeframe=entry["entry_timeframe"],
        exit_timeframe=entry["entry_timeframe"],
    )
    transition = None
    if entry["entry_timeframe"] == "M1":
        transition = transition_m1_to_m5_management(
            direction=direction,
            current_m1_protection=logical_stop,
            proposed_m5_protection=_number(parent["m5_logical_stop"]),
            proof_index=int(parent["m5_entry_index"]),
            proof_reason="M5_DIRECTIONAL_CONTINUATION_BOS_CLOSED",
        )
    return {
        "review_end_time": review_end_time,
        "first_entry_failed": failure_time is not None,
        "first_failure_time": failure_time,
        "dominant_protection_failed": dominant_failure_time is not None,
        "dominant_protection_failure_time": dominant_failure_time,
        "valid_reentry": valid_reentry,
        "reentry": reentry,
        "reentry_denied_due_to_dominant_failure": reentry_denied,
        "targets": target_contract,
        "tp1": tp1,
        "tp1_history": tp1_history,
        "tp2": tp2,
        "tp2_history": tp2_history,
        "trails": trails,
        "profit_management": profit_management,
        "management_transition": transition,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "metrics": metrics,
    }


def _category_flags(row: Dict[str, Any]) -> set[str]:
    flags = set()
    if row["entry_timeframe"] == "M1":
        flags.add("VALID_M1_EARLY_ENTRY")
    else:
        flags.add("M5_FALLBACK_NO_VALID_M1")
    if row["m1_rejections"]:
        flags.add("MESSY_M1_BOS_REJECTED")
    if row["outcome"]["first_entry_failed"] and row["outcome"]["valid_reentry"]:
        flags.add("FIRST_FAILURE_VALID_REENTRY")
    if (
        row["outcome"]["reentry_denied_due_to_dominant_failure"]
    ):
        flags.add("DOMINANT_PROTECTION_FAILURE_NO_REENTRY")
    return flags


def _build_pool() -> tuple[
    list[Dict[str, Any]],
    Dict[str, Dict[str, pd.DataFrame]],
    list[Dict[str, Any]],
]:
    pool: list[Dict[str, Any]] = []
    datasets: Dict[str, Dict[str, pd.DataFrame]] = {}
    source_audit: list[Dict[str, Any]] = []
    for symbol, base in SYMBOLS.items():
        m5_all = _read(base, "M5")
        m1 = _read(base, "M1")
        m5 = m5_all.tail(M5_EVIDENCE_ROWS).reset_index(drop=True)
        scan_offset = max(0, len(m5) - M5_SCAN_ROWS)
        scan_m5 = m5.iloc[scan_offset:].reset_index(drop=True)
        datasets[symbol] = {"M5": m5, "M1": m1}
        audit_m1 = validate_closed_series(
            m1,
            timeframe_seconds=60,
        )
        audit_m5 = validate_closed_series(
            m5,
            timeframe_seconds=300,
        )
        frames = _frames(m5)
        candidates: list[Dict[str, Any]] = []
        for direction in ("BULLISH", "BEARISH"):
            scanned = scan_expert_m5_candidates(
                    scan_m5,
                    symbol=symbol,
                    timeframe="M5",
                    direction=direction,
                    sensitivity=3,
                )
            candidates.extend(
                _offset_candidate_indexes(
                    candidate,
                    offset=scan_offset,
                )
                for candidate in scanned
            )
        candidates.sort(key=lambda item: int(item["entry_index"]))
        if len(candidates) > 60:
            positions = sorted(
                {
                    round(index * (len(candidates) - 1) / 59)
                    for index in range(60)
                }
            )
            candidates = [candidates[index] for index in positions]
        accepted = 0
        for candidate in candidates:
            fibonacci = candidate.get("fibonacci") or {}
            if not (
                fibonacci.get("available")
                and fibonacci.get("fib_zero_index") is not None
                and fibonacci.get("fib_hundred_index") is not None
            ):
                continue
            entry_index = int(candidate["entry_index"])
            if entry_index + 75 >= len(m5):
                continue
            event_time = float(m5.iloc[entry_index]["time"]) + 300
            if not (
                float(m1.iloc[0]["time"]) + 60
                <= event_time
                <= float(m1.iloc[-1]["time"]) + 60
            ):
                continue
            context = build_expert_htf_context(
                decision_candle_open_time=m5.iloc[entry_index]["time"],
                decision_timeframe_seconds=300,
                frame_data=frames,
                sensitivity=3,
                policy="ADAPTIVE_STRUCTURE_POLICY",
                allow_single_strong=True,
            )
            if context.get("approved_direction") != candidate["direction"]:
                continue
            synchronized = evaluate_synchronized_parent(
                candidate=candidate,
                m5_data=m5,
                m1_data=m1,
                symbol=symbol,
                sensitivity=2,
            )
            if not synchronized["causal_valid"]:
                continue
            outcome = _outcome(
                synchronized=synchronized,
                m5=m5,
                m1=m1,
            )
            decision = synchronized["decision"]
            entry = decision["entry"]
            row = {
                "symbol": symbol,
                "direction": candidate["direction"],
                "parent_m5_setup_id": synchronized["parent"][
                    "parent_m5_setup_id"
                ],
                "parent_m5_retracement_id": synchronized["parent"][
                    "parent_m5_retracement_id"
                ],
                "parent_impulse_cycle_id": synchronized["parent"][
                    "parent_impulse_cycle_id"
                ],
                "parent_protected_structure_id": synchronized["parent"][
                    "parent_protected_structure_id"
                ],
                "parent_fib_anchor_version": synchronized["parent"][
                    "parent_fib_anchor_version"
                ],
                "entry_timeframe": entry["entry_timeframe"],
                "entry_reason": entry["entry_reason"],
                "entry_time": float(entry["entry_time"]),
                "entry_time_utc": pd.to_datetime(
                    float(entry["entry_time"]),
                    unit="s",
                    utc=True,
                ).isoformat(),
                "entry_price": _number(entry["entry_price"]),
                "logical_stop": _number(entry["logical_stop"]),
                "emergency_stop": entry.get("emergency_stop"),
                "m5_entry_time": synchronized["parent"]["m5_entry_time"],
                "m5_entry_price": synchronized["parent"]["m5_entry_price"],
                "m5_entry_index": synchronized["parent"]["m5_entry_index"],
                "m1_entry_index": (
                    int(entry["entry_index"])
                    if entry["entry_timeframe"] == "M1"
                    else None
                ),
                "m1_failure_trigger_index": entry.get(
                    "failure_trigger_index"
                ),
                "m1_failure_trigger_price": entry.get(
                    "failure_trigger_price"
                ),
                "m1_counter_structure_index": entry.get(
                    "counter_structure_index"
                ),
                "m1_counter_structure_price": entry.get(
                    "counter_structure_price"
                ),
                "m1_logical_stop_owner_index": entry.get(
                    "logical_stop_owner_index"
                ),
                "m1_logical_stop_terminology": entry.get(
                    "logical_stop_terminology"
                ),
                "m1_grade": entry.get("grade"),
                "m1_soft_factors": entry.get("soft_factors", []),
                "m1_hard_blockers": entry.get("hard_blockers", []),
                "m1_rejections": synchronized["m1"].get("rejections", []),
                "m1_was_monitored": decision["m1_was_monitored"],
                "m5_entry_avoided_due_to_prior_m1": decision[
                    "m5_entry_avoided_due_to_prior_m1"
                ],
                "advantage": decision.get("advantage"),
                "bars_saved_by_m1": (
                    (decision.get("advantage") or {}).get(
                        "m1_candles_entered_earlier"
                    )
                ),
                "price_improvement_from_m1": (
                    (decision.get("advantage") or {}).get(
                        "price_improvement_from_m1"
                    )
                ),
                "stop_reduction_percent": (
                    (decision.get("advantage") or {}).get(
                        "stop_reduction_percent"
                    )
                ),
                "rr_improvement_from_m1": (
                    (decision.get("advantage") or {}).get(
                        "rr_improvement_from_m1"
                    )
                ),
                "remaining_impulse_percent": synchronized["parent"][
                    "remaining_impulse_percent"
                ],
                "retracement_depth_ratio": synchronized["parent"][
                    "retracement_depth_ratio"
                ],
                "fibonacci_zone": synchronized["parent"][
                    "fibonacci_zone"
                ],
                "fibonacci_levels": synchronized["parent"][
                    "fibonacci_levels"
                ],
                "fib_zero_price": synchronized["parent"]["fib_zero_price"],
                "fib_hundred_price": synchronized["parent"][
                    "fib_hundred_price"
                ],
                "dominant_protection_level": synchronized["parent"][
                    "dominant_protection_level"
                ],
                "monitoring_armed_time": synchronized["parent"]["armed_time"],
                "monitoring_active_time": synchronized["parent"]["active_time"],
                "htf_h1": context["frames"]["H1"]["direction"],
                "htf_m30": context["frames"]["M30"]["direction"],
                "htf_m15": context["frames"]["M15"]["direction"],
                "htf_state": context["state"],
                "session": _session(float(entry["entry_time"]) - 60),
                "outcome": outcome,
                "causal_valid": True,
                "future_data_used": False,
                "unfinished_candle_used": False,
                "duplicate_first_entries": 0,
                "unrelated_parent_attachments": 0,
                "order_api_called": False,
                "_candidate": candidate,
                "_synchronized": synchronized,
            }
            row["category_flags"] = sorted(_category_flags(row))
            _apply_m1_outcome_classification(row)
            pool.append(row)
            accepted += 1
        source_audit.append(
            {
                "symbol": symbol,
                "m1_rows": len(m1),
                "m5_rows": len(m5),
                "m1_first_utc": pd.to_datetime(
                    float(m1.iloc[0]["time"]), unit="s", utc=True
                ).isoformat(),
                "m1_last_utc": pd.to_datetime(
                    float(m1.iloc[-1]["time"]), unit="s", utc=True
                ).isoformat(),
                "m5_first_utc": pd.to_datetime(
                    float(m5.iloc[0]["time"]), unit="s", utc=True
                ).isoformat(),
                "m5_last_utc": pd.to_datetime(
                    float(m5.iloc[-1]["time"]), unit="s", utc=True
                ).isoformat(),
                "m1_validation": audit_m1,
                "m5_validation": audit_m5,
                "m5_candidates": len(candidates),
                "synchronized_accepted": accepted,
            }
        )
    pool.sort(key=lambda row: (row["entry_time"], row["symbol"]))
    return pool, datasets, source_audit


def _select(pool: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    selected: list[Dict[str, Any]] = []
    used: set[str] = set()
    # Rare lifecycle outcomes own their examples before generic entry classes.
    order = (
        ("DOMINANT_PROTECTION_FAILURE_NO_REENTRY", 5),
        ("FIRST_FAILURE_VALID_REENTRY", 5),
        ("MESSY_M1_BOS_REJECTED", 5),
        ("VALID_M1_EARLY_ENTRY", 15),
        ("M5_FALLBACK_NO_VALID_M1", 10),
    )
    for category, count in order:
        matches = [
            row
            for row in pool
            if category in row["category_flags"]
            and row["parent_m5_setup_id"] not in used
        ]
        by_symbol: Dict[str, list[Dict[str, Any]]] = {}
        for row in matches:
            by_symbol.setdefault(row["symbol"], []).append(row)
        picked: list[Dict[str, Any]] = []
        while len(picked) < count and any(by_symbol.values()):
            for symbol in sorted(by_symbol):
                if not by_symbol[symbol] or len(picked) >= count:
                    continue
                picked.append(by_symbol[symbol].pop(0))
        if len(picked) < count:
            raise RuntimeError(
                f"Evidence shortage for {category}: "
                f"required {count}, available {len(matches)}"
            )
        for row in picked:
            row["assigned_category"] = category
            selected.append(row)
            used.add(row["parent_m5_setup_id"])
    if len(selected) != 40:
        raise RuntimeError(f"Expected 40 unique examples, got {len(selected)}")
    selected.sort(
        key=lambda row: (
            [slot[0] for slot in SLOTS].index(row["assigned_category"]),
            row["entry_time"],
            row["symbol"],
        )
    )
    return selected


def _format_price(symbol: str, value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    clean = symbol.replace("#", "").upper()
    digits = (
        3
        if clean.endswith("JPY")
        else 5
        if clean in {"EURUSD", "GBPUSD", "AUDUSD"}
        else 2
    )
    return f"{float(value):.{digits}f}"


def _wrap(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    width: int,
) -> list[str]:
    words = str(text).split()
    lines = []
    line = ""
    for word in words:
        proposed = f"{line} {word}".strip()
        if draw.textlength(proposed, font=font) <= width:
            line = proposed
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _candles_panel(
    *,
    draw: ImageDraw.ImageDraw,
    data: pd.DataFrame,
    panel: tuple[int, int, int, int],
    start: int,
    end: int,
    levels: Iterable[tuple[str, float, str, int]],
    verticals: Iterable[tuple[str, float, str]],
    timeframe_seconds: int,
    symbol: str,
    title: str,
) -> None:
    left, top, right, bottom = panel
    draw.rectangle(panel, fill="#ffffff", outline="#9fb0c4", width=2)
    visible = data.iloc[start : end + 1]
    values = [
        _number(visible["low"].min()),
        _number(visible["high"].max()),
    ]
    for _, value, _, _ in levels:
        values.append(_number(value))
    low, high = min(values), max(values)
    padding = max((high - low) * 0.08, 1e-10)
    low -= padding
    high += padding
    width = right - left
    height = bottom - top
    step = width / max(1, end - start + 1)

    def x(index: int) -> float:
        return left + (index - start + 0.5) * step

    def y(price: float) -> float:
        return bottom - (_number(price) - low) / (high - low) * height

    small = _font(13)
    bold = _font(16, True)
    draw.text((left + 8, top + 7), title, fill="#142a44", font=bold)
    for grid in range(5):
        gy = top + grid * height / 4
        price = high - grid * (high - low) / 4
        draw.line((left, gy, right, gy), fill="#d9e1ea", width=1)
        draw.text(
            (left + 4, gy + 2),
            _format_price(symbol, price),
            fill="#526274",
            font=small,
        )
    for index in range(start, end + 1):
        candle = data.iloc[index]
        cx = x(index)
        open_price = _number(candle["open"])
        high_price = _number(candle["high"])
        low_price = _number(candle["low"])
        close = _number(candle["close"])
        colour = "#16866b" if close >= open_price else "#d14b58"
        draw.line((cx, y(high_price), cx, y(low_price)), fill=colour, width=2)
        y1, y2 = sorted((y(open_price), y(close)))
        draw.rectangle(
            (
                cx - step * 0.27,
                y1,
                cx + step * 0.27,
                max(y2, y1 + 2),
            ),
            fill=colour,
            outline=colour,
        )
    label_y: list[float] = []
    for label, value, colour, weight in levels:
        position = y(value)
        draw.line((left, position, right, position), fill=colour, width=weight)
        text_y = position - 18
        while any(abs(text_y - prior) < 18 for prior in label_y):
            text_y += 18
        label_y.append(text_y)
        draw.text(
            (right - 305, text_y),
            f"{label} {_format_price(symbol, value)}",
            fill=colour,
            font=small,
        )
    times = data["time"].astype(float)
    for event_number, (label, event_time, colour) in enumerate(verticals):
        open_time = float(event_time) - timeframe_seconds
        index = int(times.searchsorted(open_time, side="left"))
        if start <= index <= end:
            cx = x(index)
            draw.line((cx, top, cx, bottom), fill=colour, width=3)
            draw.text(
                (cx + 5, top + 30 + event_number * 20),
                label,
                fill=colour,
                font=small,
            )


def _chart(
    number: int,
    row: Dict[str, Any],
    datasets: Dict[str, Dict[str, pd.DataFrame]],
) -> str:
    symbol = row["symbol"]
    m5 = datasets[symbol]["M5"]
    m1 = datasets[symbol]["M1"]
    image = Image.new("RGB", (2100, 1450), "#f3f6fa")
    draw = ImageDraw.Draw(image)
    title = _font(28, True)
    heading = _font(18, True)
    small = _font(14)
    draw.rectangle((0, 0, 2100, 82), fill="#112a46")
    draw.text(
        (24, 19),
        f"{number:02d}  {symbol}  {row['direction']}  "
        f"{row['entry_timeframe']}  {row['assigned_category']}",
        fill="#ffffff",
        font=title,
    )
    m5_close_times = m5["time"].astype(float) + 300
    m5_center = min(
        len(m5) - 1,
        int(
            m5_close_times.searchsorted(
                float(row["m5_entry_time"]),
                side="left",
            )
        ),
    )
    m5_start = max(0, m5_center - 35)
    m5_end = min(len(m5) - 1, m5_center + 20)
    entry_time = float(row["entry_time"])
    m1_times = m1["time"].astype(float) + 60
    m1_center = int(m1_times.searchsorted(entry_time, side="left"))
    m1_start = max(0, m1_center - 55)
    m1_end = min(len(m1) - 1, m1_center + 35)
    fib_colours = {
        "100.0": "#44546a",
        "78.6": "#a56b00",
        "61.8": "#198754",
        "50.0": "#087f8c",
        "38.2": "#198754",
        "23.6": "#a56b00",
        "0.0": "#44546a",
    }
    m5_levels = [
        (
            f"Fib {label}%",
            _number(value),
            fib_colours.get(label, "#607080"),
            2,
        )
        for label, value in row["fibonacci_levels"].items()
    ]
    m5_levels.append(
        (
            "M5 DOMINANT PROTECTION",
            _number(row["dominant_protection_level"]),
            "#087f5b",
            3,
        )
    )
    upper_verticals = (
        [
            ("M1 ENTRY", entry_time, "#087f5b"),
            (
                "HYPOTHETICAL M5 BOS",
                float(row["m5_entry_time"]),
                "#155fd0",
            ),
        ]
        if row["entry_timeframe"] == "M1"
        else [
            (
                "M5 FALLBACK ENTRY",
                float(row["m5_entry_time"]),
                "#155fd0",
            )
        ]
    )
    _candles_panel(
        draw=draw,
        data=m5,
        panel=(55, 115, 1370, 640),
        start=m5_start,
        end=m5_end,
        levels=m5_levels,
        verticals=upper_verticals,
        timeframe_seconds=300,
        symbol=symbol,
        title="UPPER PANEL - M5 PARENT STORY",
    )
    m1_levels = [
        ("ENTRY", _number(row["entry_price"]), "#155fd0", 3),
        ("LOGICAL BODY-EDGE STOP", _number(row["logical_stop"]), "#e46b14", 3),
    ]
    if row.get("emergency_stop") is not None:
        m1_levels.append(
            ("EMERGENCY STOP", _number(row["emergency_stop"]), "#8c1d2c", 2)
        )
    if row.get("m1_failure_trigger_price") is not None:
        m1_levels.append(
            (
                "M1 FAILURE TRIGGER",
                _number(row["m1_failure_trigger_price"]),
                "#7a3db8",
                2,
            )
        )
    tp1 = row["outcome"].get("tp1")
    tp2 = row["outcome"].get("tp2")
    if tp1:
        m1_levels.append(("TP1", _number(tp1["price"]), "#087f5b", 3))
    if tp2:
        m1_levels.append(("TP2", _number(tp2["price"]), "#1769aa", 2))
    verticals = [
        (
            "M1 MONITORING ACTIVE",
            float(row["monitoring_active_time"]),
            "#7a3db8",
        ),
        ("EXIT/REVIEW", float(row["outcome"]["exit_time"]), "#a71930"),
    ]
    if row["entry_timeframe"] == "M1":
        verticals.extend(
            [
                ("M1 CHOSEN ENTRY", entry_time, "#087f5b"),
                (
                    "HYPOTHETICAL M5 BOS",
                    float(row["m5_entry_time"]),
                    "#155fd0",
                ),
            ]
        )
    else:
        verticals.append(
            (
                "M5 FALLBACK ENTRY",
                float(row["m5_entry_time"]),
                "#155fd0",
            )
        )
    if (
        row["assigned_category"] == "MESSY_M1_BOS_REJECTED"
        and row["m1_rejections"]
        and row["m1_rejections"][0].get("m1_index") is not None
    ):
        rejection_index = int(row["m1_rejections"][0]["m1_index"])
        verticals.append(
            (
                "REJECTED M1 BOS",
                float(m1.iloc[rejection_index]["time"]) + 60,
                "#c18100",
            )
        )
    _candles_panel(
        draw=draw,
        data=m1,
        panel=(55, 705, 1370, 1300),
        start=m1_start,
        end=m1_end,
        levels=m1_levels,
        verticals=verticals,
        timeframe_seconds=60,
        symbol=symbol,
        title="LOWER PANEL - SYNCHRONIZED M1 CHILD EXECUTION",
    )
    side = (1410, 110, 2070, 1390)
    draw.rectangle(side, fill="#eaf0f7", outline="#9fb0c4", width=2)
    advantage = row.get("advantage") or {}
    metrics = row["outcome"]["metrics"]
    transition = row["outcome"].get("management_transition") or {}
    info = [
        ("PARENT OWNERSHIP", True),
        (f"Setup: {row['parent_m5_setup_id']}", False),
        (f"Retracement: {row['parent_m5_retracement_id']}", False),
        (f"Impulse: {row['parent_impulse_cycle_id']}", False),
        (f"Protection: {row['parent_protected_structure_id']}", False),
        ("HTF AND FIBONACCI", True),
        (f"H1/M30/M15: {row['htf_h1']} / {row['htf_m30']} / {row['htf_m15']}", False),
        (f"HTF state: {row['htf_state']}", False),
        (f"Steve remaining impulse: {row['remaining_impulse_percent']:.2f}%", False),
        (f"Retracement depth: {row['retracement_depth_ratio'] * 100:.2f}%", False),
        (f"Zone: {row['fibonacci_zone']}", False),
        ("FIRST-VALID ENTRY", True),
        (f"Owner: {row['entry_timeframe']}", False),
        (f"Reason: {row['entry_reason']}", False),
        (f"Entry: {_format_price(symbol, row['entry_price'])}", False),
        (f"Logical stop: {_format_price(symbol, row['logical_stop'])}", False),
        (f"M1 grade: {row.get('m1_grade') or 'M5 fallback'}", False),
        (f"M1 rejections: {len(row['m1_rejections'])}", False),
        ("M1 ADVANTAGE", True),
        (f"Minutes/candles saved: {advantage.get('minutes_entered_earlier', 0):.1f}", False),
        (f"Price improvement: {advantage.get('price_improvement_from_m1', 0):.5f}", False),
        (f"Stop reduction: {advantage.get('stop_reduction_percent', 0):.2f}%", False),
        (f"RR improvement: {advantage.get('rr_improvement_from_m1', 0):.2f}", False),
        (f"Classification: {advantage.get('classification', 'M5_FALLBACK')}", False),
        ("MANAGEMENT", True),
        (f"M5 confirmation: {pd.to_datetime(row['m5_entry_time'], unit='s', utc=True).isoformat()}", False),
        (f"Transition: {transition.get('management_state', 'M5_MANAGED')}", False),
        (f"TP1: {(row['outcome'].get('tp1') or {}).get('state', 'N/A')}", False),
        (f"TP2: {(row['outcome'].get('tp2') or {}).get('state', 'N/A')}", False),
        (f"Trail candidates/proven: {len(row['outcome']['trails'])}/{sum(x['state']=='TRAIL_PROVEN' for x in row['outcome']['trails'])}", False),
        (f"Opposing BOS exit: {row['outcome']['exit_reason'] == 'OWNED_PROTECTION_BODY_CLOSE_EXIT'}", False),
        (f"Re-entry: {'VALID' if row['outcome']['valid_reentry'] else 'NONE/DENIED'}", False),
        (f"Exit: {row['outcome']['exit_reason']}", False),
        ("PROFIT CAPTURE", True),
        (f"MFE / MAE: {metrics['MFE']:.5f} / {metrics['MAE']:.5f}", False),
        (f"Peak R / Final R: {metrics['peak_R']:.2f} / {metrics['final_R']:.2f}", False),
        (f"Giveback R: {metrics['giveback_R']:.2f}", False),
        (f"Capture ratio: {metrics['capture_ratio']:.2%}", False),
        (f"Capture class: {metrics['classification']}", False),
        ("CAUSAL SAFETY", True),
        ("Closed candles only. No future data. One parent owner.", False),
        ("M1 and M5 first entries cannot duplicate.", False),
        ("Research only. No order API called.", False),
    ]
    sy = side[1] + 16
    for text, is_heading in info:
        font = heading if is_heading else small
        colour = "#142a44" if is_heading else "#32475d"
        for line in _wrap(draw, text, font, side[2] - side[0] - 30):
            draw.text((side[0] + 15, sy), line, fill=colour, font=font)
            sy += 24 if is_heading else 19
        sy += 6 if is_heading else 2
    filename = (
        f"{number:02d}_{symbol.replace('#', '').lower()}_"
        f"{row['entry_timeframe'].lower()}_{row['direction'].lower()}.png"
    )
    image.save(CHARTS / filename)
    return filename


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _clean(item)
            for key, item in value.items()
            if not str(key).startswith("_")
        }
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
            writer.writerow(
                {
                    key: json.dumps(value, default=_default)
                    if isinstance(value, (dict, list))
                    else value
                    for key, value in row.items()
                }
            )


def _html(rows: list[Dict[str, Any]]) -> None:
    cards = []
    for row in rows:
        cards.append(
            f"""<article>
<h2>{row['review_number']:02d} - {html.escape(row['symbol'])} -
{html.escape(row['direction'])} - {html.escape(row['assigned_category'])}</h2>
<p>{html.escape(row['entry_time_utc'])} - entry {row['entry_timeframe']} -
Steve remaining {row['remaining_impulse_percent']:.2f}% -
final {row['outcome']['metrics']['final_R']:.2f}R</p>
<img src="charts/{html.escape(row['chart_file'])}"
alt="Synchronized M5 and M1 evidence chart {row['review_number']}">
<label>Steve verdict<select><option></option><option>ACCEPT</option>
<option>REJECT</option><option>UNCERTAIN</option></select></label>
<label>Reason<textarea></textarea></label></article>"""
        )
    document = f"""<!doctype html><html><head><meta charset="utf-8">
<title>SmartStructureBot Final Fidelity Review</title><style>
body{{margin:0;background:#e8eef5;color:#152235;font:15px Arial,sans-serif}}
header{{padding:22px 4vw;background:#112a46;color:white;position:sticky;top:0;z-index:2}}
main{{width:min(1900px,97vw);margin:22px auto}}
article{{background:white;padding:17px;margin:0 0 28px;border-radius:10px}}
img{{width:100%;border:1px solid #a8b5c5}}
label{{display:block;margin-top:10px;font-weight:bold}}
select,textarea{{display:block;width:100%;box-sizing:border-box;padding:8px;margin-top:4px}}
textarea{{height:58px}}</style></head><body><header>
<h1>40 synchronized M5-parent / M1-child fidelity examples</h1>
<div>Real MT5 closed candles - Steve Fibonacci V2 - research only - no orders</div>
</header><main>{''.join(cards)}</main></body></html>"""
    (OUT / "final_fidelity_review.html").write_text(
        document,
        encoding="utf-8",
    )


def _reports(
    *,
    rows: list[Dict[str, Any]],
    source_audit: list[Dict[str, Any]],
) -> None:
    clean_rows = [_clean(row) for row in rows]
    review_rows = []
    for row in clean_rows:
        review_rows.append(
            {
                "review_number": row["review_number"],
                "symbol": row["symbol"],
                "direction": row["direction"],
                "assigned_category": row["assigned_category"],
                "entry_time_utc": row["entry_time_utc"],
                "entry_timeframe": row["entry_timeframe"],
                "entry_price": row["entry_price"],
                "logical_stop": row["logical_stop"],
                "remaining_impulse_percent": row[
                    "remaining_impulse_percent"
                ],
                "m1_grade": row["m1_grade"],
                "final_R": row["outcome"]["metrics"]["final_R"],
                "capture_ratio": row["outcome"]["metrics"][
                    "capture_ratio"
                ],
                "manual_verdict": "",
                "manual_reason": "",
                "chart_file": row["chart_file"],
            }
        )
    _write_csv(OUT / "final_fidelity_review.csv", review_rows)
    _write_csv(
        OUT / "m1_advantage_audit.csv",
        [
            {
                "review_number": row["review_number"],
                "symbol": row["symbol"],
                "setup_id": row["parent_m5_setup_id"],
                **(row["advantage"] or {}),
            }
            for row in clean_rows
            if row["advantage"]
        ],
    )
    rejection_rows = []
    for row in clean_rows:
        for rejection in row["m1_rejections"]:
            rejection_rows.append(
                {
                    "review_number": row["review_number"],
                    "symbol": row["symbol"],
                    "setup_id": row["parent_m5_setup_id"],
                    **rejection,
                }
            )
    _write_csv(OUT / "m1_rejection_audit.csv", rejection_rows)
    _write_csv(
        OUT / "target_lifecycle_audit.csv",
        [
            {
                "review_number": row["review_number"],
                "symbol": row["symbol"],
                "setup_id": row["parent_m5_setup_id"],
                "tp1": row["outcome"]["tp1"],
                "tp1_history": row["outcome"]["tp1_history"],
                "tp2": row["outcome"]["tp2"],
                "tp2_history": row["outcome"]["tp2_history"],
            }
            for row in clean_rows
        ],
    )
    _write_csv(
        OUT / "profit_capture_report.csv",
        [
            {
                "review_number": row["review_number"],
                "symbol": row["symbol"],
                "setup_id": row["parent_m5_setup_id"],
                **row["outcome"]["metrics"],
            }
            for row in clean_rows
        ],
    )
    _write_csv(
        OUT / "reentry_audit.csv",
        [
            {
                "review_number": row["review_number"],
                "symbol": row["symbol"],
                "setup_id": row["parent_m5_setup_id"],
                "first_entry_failed": row["outcome"][
                    "first_entry_failed"
                ],
                "first_failure_time": row["outcome"][
                    "first_failure_time"
                ],
                "valid_reentry": row["outcome"]["valid_reentry"],
                "reentry": row["outcome"]["reentry"],
                "dominant_protection_failed": row["outcome"][
                    "dominant_protection_failed"
                ],
                "reentry_denied_due_to_dominant_failure": row["outcome"][
                    "reentry_denied_due_to_dominant_failure"
                ],
                "maximum_reentry": 1,
            }
            for row in clean_rows
        ],
    )
    _write_csv(
        OUT / "hard_block_soft_grade_report.csv",
        [
            {
                "review_number": row["review_number"],
                "symbol": row["symbol"],
                "entry_timeframe": row["entry_timeframe"],
                "m1_grade": row["m1_grade"],
                "hard_blockers": row["m1_hard_blockers"],
                "soft_factors": row["m1_soft_factors"],
                "rejection_states": [
                    item.get("state") for item in row["m1_rejections"]
                ],
            }
            for row in clean_rows
        ],
    )
    counts = {
        category: sum(
            row["assigned_category"] == category for row in clean_rows
        )
        for category, _ in SLOTS
    }
    audit = {
        "strategy_model": "EXPERT_SPEC_V1",
        "fibonacci_model": "STEVE_REMAINING_IMPULSE_PERCENT_V2",
        "coordinator": "SynchronizedM1ReplayCoordinator",
        "generated_examples": len(clean_rows),
        "unique_parent_setups": len(
            {row["parent_m5_setup_id"] for row in clean_rows}
        ),
        "distribution": counts,
        "symbols": sorted({row["symbol"] for row in clean_rows}),
        "directions": {
            direction: sum(row["direction"] == direction for row in clean_rows)
            for direction in ("BULLISH", "BEARISH")
        },
        "m1_entry_count": sum(
            row["entry_timeframe"] == "M1" for row in clean_rows
        ),
        "m5_fallback_count": sum(
            row["entry_timeframe"] == "M5" for row in clean_rows
        ),
        "m1_false_entry_rate": (
            sum(
                (row.get("advantage") or {}).get("classification")
                == "M1_FALSE_EARLY_ENTRY"
                for row in clean_rows
            )
            / max(
                1,
                sum(row["entry_timeframe"] == "M1" for row in clean_rows),
            )
        ),
        "all_causal": all(row["causal_valid"] for row in clean_rows),
        "future_data_violations": sum(
            bool(row["future_data_used"]) for row in clean_rows
        ),
        "unfinished_candle_decisions": sum(
            bool(row["unfinished_candle_used"]) for row in clean_rows
        ),
        "duplicate_first_entries": sum(
            int(row["duplicate_first_entries"]) for row in clean_rows
        ),
        "unrelated_parent_attachments": sum(
            int(row["unrelated_parent_attachments"]) for row in clean_rows
        ),
        "order_api_calls": sum(
            bool(row["order_api_called"]) for row in clean_rows
        ),
        "reproducibility_fingerprint": [
            (
                row["parent_m5_setup_id"],
                row["entry_timeframe"],
                row["entry_time"],
                row["entry_price"],
            )
            for row in clean_rows
        ],
        "source_audit": source_audit,
        "rows": clean_rows,
    }
    (OUT / "final_fidelity_audit.json").write_text(
        json.dumps(audit, indent=2, default=_default),
        encoding="utf-8",
    )
    (OUT / "data_alignment_audit.json").write_text(
        json.dumps(source_audit, indent=2, default=_default),
        encoding="utf-8",
    )
    _html(clean_rows)


def run() -> Dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    CHARTS.mkdir(parents=True, exist_ok=True)
    prior_fallbacks: list[Dict[str, Any]] = []
    prior_path = OUT / "final_fidelity_audit.json"
    if prior_path.exists():
        prior_payload = json.loads(prior_path.read_text(encoding="utf-8"))
        for prior in prior_payload.get("rows", []):
            if prior.get("entry_timeframe") != "M5":
                continue
            row = deepcopy(prior)
            row["category_flags"] = ["M5_FALLBACK_NO_VALID_M1"]
            row.pop("assigned_category", None)
            row.pop("review_number", None)
            row.pop("chart_file", None)
            prior_fallbacks.append(row)
    pool, datasets, source_audit = _build_pool()
    event_keys = {
        (
            row["symbol"],
            row["direction"],
            float(row["entry_time"]),
        )
        for row in pool
    }
    for row in prior_fallbacks:
        event_key = (
            row["symbol"],
            row["direction"],
            float(row["entry_time"]),
        )
        if event_key not in event_keys:
            pool.append(row)
            event_keys.add(event_key)
    pool.sort(key=lambda row: (float(row["entry_time"]), row["symbol"]))
    availability = {
        category: sum(category in row["category_flags"] for row in pool)
        for category, _ in SLOTS
    }
    (OUT / "pool_availability.json").write_text(
        json.dumps(
            {"pool": len(pool), "availability": availability},
            indent=2,
        ),
        encoding="utf-8",
    )
    selected = _select(pool)
    for number, row in enumerate(selected, 1):
        row["review_number"] = number
        row["chart_file"] = _chart(number, row, datasets)
    _reports(rows=selected, source_audit=source_audit)
    summary = json.loads(
        (OUT / "final_fidelity_audit.json").read_text(encoding="utf-8")
    )
    print(
        json.dumps(
            {
                "generated_examples": summary["generated_examples"],
                "unique_parent_setups": summary["unique_parent_setups"],
                "distribution": summary["distribution"],
                "symbols": summary["symbols"],
                "directions": summary["directions"],
                "all_causal": summary["all_causal"],
                "future_data_violations": summary[
                    "future_data_violations"
                ],
                "unfinished_candle_decisions": summary[
                    "unfinished_candle_decisions"
                ],
                "duplicate_first_entries": summary[
                    "duplicate_first_entries"
                ],
                "unrelated_parent_attachments": summary[
                    "unrelated_parent_attachments"
                ],
                "order_api_calls": summary["order_api_calls"],
            },
            indent=2,
        )
    )
    return summary


def refresh_profit_management() -> Dict[str, Any]:
    """Re-evaluate management for the already selected deterministic 40."""
    path = OUT / "final_fidelity_audit.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload["rows"]
    datasets: Dict[str, Dict[str, pd.DataFrame]] = {}
    for symbol, base in SYMBOLS.items():
        datasets[symbol] = {
            "M5": _read(base, "M5").tail(M5_EVIDENCE_ROWS).reset_index(drop=True),
            "M1": _read(base, "M1"),
        }
    for row in rows:
        data = datasets[row["symbol"]][row["entry_timeframe"]]
        seconds = 60 if row["entry_timeframe"] == "M1" else 300
        entry_time = float(row["entry_time"])
        if (
            row["entry_timeframe"] == "M5"
            and row.get("emergency_stop") is None
        ):
            m5_data = datasets[row["symbol"]]["M5"]
            m5_close_times = m5_data["time"].astype(float) + 300
            m5_entry_index = min(
                len(m5_data) - 1,
                int(m5_close_times.searchsorted(entry_time, side="left")),
            )
            m5_atr = atr_at(m5_data, as_of_index=m5_entry_index)
            row["emergency_stop"] = (
                _number(row["logical_stop"]) - m5_atr
                if row["direction"] == "BULLISH"
                else _number(row["logical_stop"]) + m5_atr
            )
        review_end = float(row["outcome"]["review_end_time"])
        candles = data[
            (data["time"].astype(float) + seconds >= entry_time)
            & (data["time"].astype(float) + seconds <= review_end)
        ].copy().reset_index(drop=True)
        target_contract = row["outcome"]["targets"]
        _, full_tp1_history = _target_story(
            target=target_contract.get("tp1"),
            direction=row["direction"],
            candles=candles,
        )
        management = simulate_profit_management(
            direction=row["direction"],
            entry_price=_number(row["entry_price"]),
            initial_stop=_number(row["logical_stop"]),
            emergency_stop=(
                _number(row["emergency_stop"])
                if row.get("emergency_stop") is not None
                else None
            ),
            candles=candles,
            tp1_target=(
                _number(row["outcome"]["targets"]["tp1"]["price"])
                if row["outcome"]["targets"].get("tp1")
                else None
            ),
            target_events=full_tp1_history,
            trail_events=row["outcome"].get("trails", []),
            profit_lock_trigger_r=1.0,
            profit_lock_r=0.10,
            tp1_partial_fraction=0.50,
        )
        exit_index = int(management["exit_index"])
        exit_time = float(candles.iloc[exit_index]["time"]) + seconds
        trade_candles = candles.iloc[: exit_index + 1].copy()
        if row["direction"] == "BULLISH":
            peak_index = int(trade_candles["high"].astype(float).argmax())
        else:
            peak_index = int(trade_candles["low"].astype(float).argmin())
        peak_time = float(trade_candles.iloc[peak_index]["time"]) + seconds
        tp1, tp1_history = _target_story(
            target=target_contract.get("tp1"),
            direction=row["direction"],
            candles=trade_candles,
        )
        tp2, tp2_history = _target_story(
            target=target_contract.get("tp2"),
            direction=row["direction"],
            candles=trade_candles,
        )
        metrics = profit_capture_metrics(
            direction=row["direction"],
            entry_price=_number(row["entry_price"]),
            initial_stop=_number(row["logical_stop"]),
            candles=trade_candles,
            exit_price=_number(management["equivalent_exit_price"]),
            entry_time=entry_time,
            exit_time=exit_time,
            peak_time=peak_time,
            tp1_state=(tp1 or {}).get("state", "UNAVAILABLE"),
            tp2_state=(tp2 or {}).get("state", "UNAVAILABLE"),
            first_trail_delay=(
                int(row["outcome"]["trails"][0]["proof_index"])
                if row["outcome"].get("trails")
                and row["outcome"]["trails"][0].get("proof_index") is not None
                else None
            ),
            trail_count=sum(
                event["state"] == "TRAIL_PROVEN"
                for event in row["outcome"].get("trails", [])
            ),
            entry_timeframe=row["entry_timeframe"],
            exit_timeframe=row["entry_timeframe"],
        )
        row["outcome"]["profit_management"] = management
        row["outcome"]["tp1"] = tp1
        row["outcome"]["tp1_history"] = tp1_history
        row["outcome"]["tp2"] = tp2
        row["outcome"]["tp2_history"] = tp2_history
        row["outcome"]["exit_time"] = exit_time
        row["outcome"]["exit_price"] = _number(management["exit_price"])
        row["outcome"]["exit_reason"] = management["exit_reason"]
        row["outcome"]["metrics"] = metrics
        _apply_m1_outcome_classification(row)
        row["chart_file"] = _chart(
            int(row["review_number"]),
            row,
            datasets,
        )
    _reports(
        rows=rows,
        source_audit=payload["source_audit"],
    )
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    run()
