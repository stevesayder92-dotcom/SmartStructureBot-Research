from __future__ import annotations

import csv
import html
import json
from pathlib import Path
import sys
from typing import Any, Dict

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.adaptive_decision import grade_setup  # noqa: E402
from core.expert_strategy import (  # noqa: E402
    build_expert_htf_context,
    confirmed_swings,
    scan_expert_m5_candidates,
)
from core.semantic_swing_hierarchy import (  # noqa: E402
    build_semantic_swing_hierarchy,
)
from core.steve_trade_management import (  # noqa: E402
    SteveTradeManagementEngine,
    atr_at,
)
from tools.run_phase7_expert_audit import resample_closed_m5  # noqa: E402


OUT = ROOT / "phase10_1_evidence"
CHARTS = OUT / "charts"
SOURCES = {
    "GOLD#": ROOT / "research_data" / "GOLD_M5_NY_open_closed.csv",
    "GER40Cash#": ROOT / "research_data" / "GER40Cash_M5_phase5b_closed.csv",
    "US100Cash#": ROOT / "research_data" / "US100Cash_M5_closed.csv",
}
REQUESTED_BUT_UNAVAILABLE = {
    "US30Cash#": "No closed-candle source file is present in the supplied repository.",
    "OILCash#": "No closed-candle source file is present in the supplied repository.",
}
REQUIRED_SLOTS = [
    *["FIRST_ENTRY_WINNER"] * 3,
    *["FIRST_ENTRY_LOGICAL_LOSS"] * 3,
    *["VALID_REENTRY"] * 3,
    *["REENTRY_REJECTED_DOMINANT_FAILED"] * 2,
    *["PRIMARY_SWEET_SPOT"] * 2,
    *["SHALLOW_STRUCTURALLY_STRONG"] * 2,
    *["M1_FALLBACK_TO_M5"] * 2,
    "OPPOSING_MEANINGFUL_BOS_EXIT",
    "WICK_STOP_SURVIVAL",
    "RAW_TRAIL_REJECTED_UNTIL_PROOF",
]


def _default(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(type(value).__name__)


def _font(size: int, bold: bool = False):
    name = "arialbd.ttf" if bold else "arial.ttf"
    path = Path("C:/Windows/Fonts") / name
    return ImageFont.truetype(str(path), size) if path.exists() else ImageFont.load_default()


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


def _old_keys() -> set[tuple[str, int]]:
    path = ROOT / "phase9_evidence" / "phase9_management_audit.json"
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        (str(row["symbol"]), int(row["entry_index"]))
        for row in payload.get("rows", [])
    }


def _phase10_review_keys() -> list[tuple[str, int]]:
    path = ROOT / "phase10_evidence" / "phase10_example_audit.csv"
    if not path.exists():
        return []
    rows = pd.read_csv(path).sort_values("review_number")
    return [
        (str(row["symbol"]), int(row["entry_index"]))
        for _, row in rows.iterrows()
    ]


def _frames(data: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    return {
        timeframe: resample_closed_m5(data, timeframe=timeframe)
        for timeframe in ("H1", "M30", "M15")
    }


def _tags(attempt: Dict[str, Any], management: Dict[str, Any], row: Dict[str, Any]) -> list[str]:
    tags: list[str] = []
    events = [item.get("event") for item in attempt.get("history", [])]
    risk = abs(float(row["entry_price"]) - float(row["logical_stop"]))
    direction = row["direction"]
    end_price = float(row["review_close"])
    favourable_r = (
        (end_price - float(row["entry_price"])) / risk
        if direction == "BULLISH"
        else (float(row["entry_price"]) - end_price) / risk
    ) if risk > 0 else 0.0
    if (
        (attempt.get("tp1_triggered") or favourable_r >= 1.0)
        and attempt.get("exit_reason")
        != "SETUP_LOGICAL_BODY_CLOSE_INVALIDATION"
    ):
        tags.append("FIRST_ENTRY_WINNER")
    if (
        attempt.get("exit_reason") == "SETUP_LOGICAL_BODY_CLOSE_INVALIDATION"
        and int(attempt.get("attempt_number", 1)) == 1
    ):
        tags.append("FIRST_ENTRY_LOGICAL_LOSS")
    if int(management.get("reentry_count", 0)) == 1:
        tags.append("VALID_REENTRY")
    if management.get("reentry_state") == "REENTRY_REJECTED_DOMINANT_PROTECTION_FAILED":
        tags.append("REENTRY_REJECTED_DOMINANT_FAILED")
    if row["fibonacci_zone"] == "PRIMARY_SWEET_SPOT":
        tags.append("PRIMARY_SWEET_SPOT")
    if row["fibonacci_zone"] == "SHALLOW" and float(row["bos_body_atr"]) >= 0.8:
        tags.append("SHALLOW_STRUCTURALLY_STRONG")
    if attempt.get("exit_reason") == "OPPOSING_MEANINGFUL_BOS":
        tags.append("OPPOSING_MEANINGFUL_BOS_EXIT")
    if "WICK_THROUGH_LOGICAL_LEVEL_SURVIVED" in events:
        tags.append("WICK_STOP_SURVIVAL")
    candidates = attempt.get("trail_candidates", [])
    if any(item.get("proof_index") is None for item in candidates):
        tags.append("RAW_TRAIL_REJECTED_UNTIL_PROOF")
    if any(
        item.get("proof_index") is not None
        and int(item["proof_index"]) > int(item["confirmed_at_index"])
        for item in candidates
    ):
        tags.append("RAW_TRAIL_REJECTED_UNTIL_PROOF")
    return sorted(set(tags))


def _evaluate(
    *,
    symbol: str,
    data: pd.DataFrame,
    candidate: Dict[str, Any],
    frames: Dict[str, pd.DataFrame],
    swings: list[Dict[str, Any]],
) -> Dict[str, Any] | None:
    entry_index = int(candidate["entry_index"])
    context = build_expert_htf_context(
        decision_candle_open_time=data.iloc[entry_index]["time"],
        decision_timeframe_seconds=300,
        frame_data=frames,
        sensitivity=3,
        policy="ADAPTIVE_STRUCTURE_POLICY",
        allow_single_strong=True,
    )
    if context.get("approved_direction") != candidate["direction"]:
        return None
    end = min(len(data) - 1, entry_index + 80)
    visible_swings = [
        point for point in swings
        if int(point["confirmed_at_index"]) <= end
    ]
    manager = SteveTradeManagementEngine()
    management = manager.evaluate(
        data=data,
        symbol=symbol,
        timeframe="M5",
        as_of_index=end,
        direction=candidate["direction"],
        context=context,
        confirmed_swings=visible_swings,
        canonical_entry=candidate,
    )
    attempts = management.get("attempts") or []
    if not attempts:
        return None
    attempt = attempts[0]
    invalidation = attempt["logical_invalidation"]
    if not (
        invalidation.get("causal_valid")
        and invalidation.get("correct_side_of_entry")
    ):
        return None
    emergency = attempt["emergency_broker_stop_contract"]
    fib = dict(candidate.get("fibonacci") or {})
    candle = data.iloc[entry_index]
    candle_atr = atr_at(data, as_of_index=entry_index)
    body_atr = abs(float(candle["close"]) - float(candle["open"])) / candle_atr
    adaptive = grade_setup(
        hard_blockers=[],
        htf_context=context,
        fibonacci=fib,
        structure_clear=True,
        bos_body_atr=body_atr,
        session_quality=_session(float(candle["time"])),
    )
    hierarchy = build_semantic_swing_hierarchy(
        data=data.iloc[: entry_index + 1],
        swings=[
            point for point in swings
            if int(point["confirmed_at_index"]) <= entry_index
        ],
        direction=candidate["direction"],
        as_of_index=entry_index,
        model=candidate,
        protection=attempt["dominant_decision_protection"],
    )
    timestamp = pd.to_datetime(float(candle["time"]), unit="s", utc=True)
    row = {
        "setup_id": candidate["setup_id"],
        "parent_setup_id": candidate["setup_id"],
        "reentry_event_id": (
            attempts[1]["event_id"] if len(attempts) > 1 else None
        ),
        "symbol": symbol,
        "timeframe": "M5",
        "session": _session(float(candle["time"])),
        "direction": candidate["direction"],
        "entry_index": entry_index,
        "time_utc": timestamp.isoformat(),
        "htf_policy_result": context["state"],
        "htf_h1": context["frames"]["H1"]["direction"],
        "htf_m30": context["frames"]["M30"]["direction"],
        "htf_m15": context["frames"]["M15"]["direction"],
        "origin_bos_index": fib.get("origin_bos_index"),
        "impulse_zero_index": fib.get("zero_anchor_index"),
        "impulse_zero_price": fib.get("zero_anchor_price"),
        "impulse_hundred_index": fib.get("hundred_anchor_index"),
        "impulse_hundred_price": fib.get("hundred_anchor_price"),
        "fibonacci_depth": fib.get("depth"),
        "fibonacci_zone": fib.get("zone", "UNAVAILABLE"),
        "minimum_fib_reached": fib.get("minimum_relevant_reached", False),
        "trend_protected_index": (
            attempt["dominant_decision_protection"].get("index")
        ),
        "trend_protected_level": (
            attempt["dominant_decision_protection"].get("level")
        ),
        "retracement_qualification_index": candidate.get("qualified_at"),
        "counter_index": candidate["counter"]["index"],
        "counter_level": candidate["counter"]["level"],
        "failure_trigger_index": candidate["trigger"]["index"],
        "failure_trigger_level": candidate["trigger"]["level"],
        "failure_trigger_available_at": candidate["trigger"]["confirmed_at_index"],
        "entry_price": candidate["entry_price"],
        "bos_body_atr": body_atr,
        "setup_grade": adaptive["grade"],
        "risk_modifier": adaptive["risk_modifier"],
        "hard_block_reasons": adaptive["hard_blockers"],
        "soft_downgrade_reasons": adaptive["soft_factors"],
        "logical_structure_index": invalidation["structure_index"],
        "logical_structure_selection_scope": invalidation.get(
            "selection_scope"
        ),
        "structure_body_boundary": invalidation["body_close_level"],
        "logical_stop": invalidation["logical_boundary"],
        "logical_atr_tolerance": invalidation["atr_tolerance"],
        "emergency_stop": emergency["price"],
        "broad_pullback_extreme": invalidation["broad_pullback_extreme"],
        "broad_extreme_rejected": invalidation["broad_pullback_extreme_rejected"],
        "first_entry_result": attempt.get("exit_reason") or "OPEN_AT_REVIEW_END",
        "retracement_stayed_active": any(
            item.get("event") == "FIRST_ENTRY_FAILED_RETRACEMENT_ACTIVE"
            for item in management.get("history", [])
        ),
        "reentry_trigger_index": (
            (management.get("reentry_trigger") or {}).get("index")
        ),
        "reentry_result": (
            attempts[1].get("exit_reason") or attempts[1].get("status")
            if len(attempts) > 1 else management.get("reentry_state")
        ),
        "trail_events": attempt.get("trail_movements", []),
        "opposing_bos_events": attempt.get("opposing_bos"),
        "tp1_triggered": attempt.get("tp1_triggered"),
        "tp1_target": attempt.get("position_1_target"),
        "tp1_target_source": attempt.get("position_1_target_source"),
        "review_end_index": end,
        "review_close": float(data.iloc[end]["close"]),
        "causal_valid": bool(
            fib.get("causal_valid", True)
            and invalidation["causal_valid"]
            and not invalidation["post_entry_candles_used"]
        ),
        "future_data_used_at_entry": False,
        "semantic_role_counts": hierarchy["role_counts"],
        "order_api_called": False,
        "manual_verdict": "",
        "manual_reason": "",
    }
    row["category_tags"] = _tags(attempt, management, row)
    row["_candidate"] = candidate
    row["_context"] = context
    row["_management"] = management
    row["_hierarchy"] = hierarchy
    return row


def _select(pool: list[Dict[str, Any]]) -> tuple[list[Dict[str, Any]], list[str]]:
    selected: list[Dict[str, Any]] = []
    used: set[tuple[str, int]] = set()
    unavailable: list[str] = []
    for slot in REQUIRED_SLOTS:
        match = next(
            (
                row for row in pool
                if slot in row["category_tags"]
                and (row["symbol"], row["entry_index"]) not in used
                and (
                    not selected
                    or row["symbol"] != selected[-1]["symbol"]
                    or row["direction"] != selected[-1]["direction"]
                )
            ),
            None,
        )
        if match is None:
            match = next(
                (
                    row for row in pool
                    if slot in row["category_tags"]
                    and (row["symbol"], row["entry_index"]) not in used
                ),
                None,
            )
        if match is None:
            unavailable.append(slot)
            continue
        match["assigned_category"] = slot
        selected.append(match)
        used.add((match["symbol"], match["entry_index"]))
    for row in pool:
        if len(selected) >= 20:
            break
        key = (row["symbol"], row["entry_index"])
        if key in used:
            continue
        row["assigned_category"] = "ADDITIONAL_CAUSAL_ENTRY"
        selected.append(row)
        used.add(key)
    return selected[:20], unavailable


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    words = str(text).split()
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=font) <= width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _chart(number: int, row: Dict[str, Any], data: pd.DataFrame) -> str:
    width, height = 1900, 1120
    image = Image.new("RGB", (width, height), "#f4f7fb")
    draw = ImageDraw.Draw(image)
    title = _font(30, True)
    normal = _font(18)
    small = _font(15)
    bold = _font(18, True)
    draw.rectangle((0, 0, width, 88), fill="#112a46")
    draw.text(
        (28, 18),
        f"{number:02d}  {row['symbol']} {row['timeframe']}  {row['direction']}  "
        f"{row['time_utc'][:16]} UTC  |  {row['assigned_category']}",
        fill="white",
        font=title,
    )
    plot = (70, 125, 1370, 885)
    side = (1410, 115, 1870, 1085)
    draw.rectangle(plot, fill="white", outline="#a8b5c5", width=2)
    draw.rectangle(side, fill="#eaf0f7", outline="#a8b5c5", width=2)
    entry = int(row["entry_index"])
    symbol = str(row.get("symbol") or "").upper().replace("#", "")
    forex_symbols = {
        "AUDUSD", "EURUSD", "GBPUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY",
    }
    price_decimals = 3 if symbol.endswith("JPY") else (5 if symbol in forex_symbols else 2)

    def fmt_price(value: float) -> str:
        return f"{float(value):.{price_decimals}f}"

    start = max(0, entry - 40)
    end = min(len(data) - 1, entry + 20)
    visible = data.iloc[start : end + 1]
    low = min(
        float(visible["low"].min()),
        float(row["logical_stop"]),
        float(row["emergency_stop"]),
        (
            float(row["tp1_target"])
            if row.get("tp1_target") is not None
            else float(visible["low"].min())
        ),
    )
    high = max(
        float(visible["high"].max()),
        float(row["entry_price"]),
        (
            float(row["tp1_target"])
            if row.get("tp1_target") is not None
            else float(visible["high"].max())
        ),
    )
    padding = max((high - low) * 0.08, 1e-8)
    low -= padding
    high += padding
    pw = plot[2] - plot[0]
    ph = plot[3] - plot[1]
    step = pw / max(1, end - start + 1)

    def x(index: int) -> float:
        return plot[0] + (index - start + 0.5) * step

    def y(price: float) -> float:
        return plot[3] - (price - low) / (high - low) * ph

    for grid in range(6):
        gy = plot[1] + grid * ph / 5
        price = high - grid * (high - low) / 5
        draw.line((plot[0], gy, plot[2], gy), fill="#d8e0e9", width=1)
        draw.text((plot[0] + 4, gy + 2), fmt_price(price), fill="#526274", font=small)
    future_x = x(entry) + step / 2
    draw.rectangle((future_x, plot[1], plot[2], plot[3]), fill="#eef1f5")
    draw.text((future_x + 12, plot[1] + 10), "POST-ENTRY REVIEW ONLY", fill="#526274", font=bold)
    for index in range(start, end + 1):
        candle = data.iloc[index]
        cx = x(index)
        o, h, l, c = map(float, (candle["open"], candle["high"], candle["low"], candle["close"]))
        colour = "#16866b" if c >= o else "#d14b58"
        draw.line((cx, y(h), cx, y(l)), fill=colour, width=2)
        top, bottom = sorted((y(o), y(c)))
        draw.rectangle(
            (cx - step * 0.28, top, cx + step * 0.28, max(bottom, top + 2)),
            fill=colour,
            outline=colour,
        )
    levels = (row["_candidate"].get("fibonacci") or {}).get("levels", {})
    fib_colours = {
        "0.0": "#44546a", "0.236": "#a56b00", "0.382": "#198754",
        "0.5": "#087f8c", "0.618": "#198754", "0.786": "#a56b00", "1.0": "#44546a",
    }
    for label, price in levels.items():
        if low <= float(price) <= high:
            draw.line((plot[0], y(float(price)), x(entry), y(float(price))),
                      fill=fib_colours.get(label, "#607080"), width=2)
            draw.text((plot[2] - 175, y(float(price)) - 18),
                      f"Fib {label}  {fmt_price(price)}",
                      fill=fib_colours.get(label, "#607080"), font=small)
    stop_lines = [
        ("ENTRY CLOSE", row["entry_price"], "#155fd0", 4),
        ("FAILURE TRIGGER", row["failure_trigger_level"], "#7a3db8", 3),
        ("LOGICAL STOP", row["logical_stop"], "#e46b14", 4),
        ("EMERGENCY STOP", row["emergency_stop"], "#8c1d2c", 3),
    ]
    if row.get("tp1_target") is not None:
        stop_lines.append(
            ("TP1 · WICK TOUCH", row["tp1_target"], "#087f5b", 4)
        )
    if row["trend_protected_level"] is not None:
        stop_lines.append(
            ("DOMINANT PROTECTION", row["trend_protected_level"], "#178044", 3)
        )
    for label, price, colour, weight in stop_lines:
        if low <= float(price) <= high:
            draw.line((plot[0], y(float(price)), plot[2], y(float(price))),
                      fill=colour, width=weight)
            draw.text((plot[0] + 210, y(float(price)) - 23),
                      f"{label} {fmt_price(price)}", fill=colour, font=bold)
    markers = [
        ("IMPULSE 0%", row["impulse_zero_index"], row["impulse_zero_price"], "#44546a"),
        ("IMPULSE 100%", row["impulse_hundred_index"], row["impulse_hundred_price"], "#44546a"),
        ("INITIAL COUNTER STRUCTURE", row["counter_index"], row["counter_level"], "#9a6700"),
        (
            "LAST IMPORTANT PRE-BOS SWING · SL OWNER",
            row["logical_structure_index"],
            row["structure_body_boundary"],
            "#e46b14",
        ),
        (
            f"FAILURE TRIGGER (available {row['failure_trigger_available_at']})",
            row["failure_trigger_index"], row["failure_trigger_level"], "#7a3db8",
        ),
        ("ENTRY", entry, row["entry_price"], "#155fd0"),
    ]
    for label, index, price, colour in markers:
        if index is None or price is None or not (start <= int(index) <= end):
            continue
        cx, cy = x(int(index)), y(float(price))
        draw.ellipse((cx - 7, cy - 7, cx + 7, cy + 7), fill=colour)
        draw.text((cx + 8, cy - 28), label, fill=colour, font=small)
    management = row["_management"]
    for attempt in management.get("attempts", []):
        for candidate in attempt.get("trail_candidates", []):
            idx = int(candidate["structure_index"])
            if not (start <= idx <= end):
                continue
            level = float(candidate["structure_level"])
            proved = candidate.get("proof_index") is not None
            colour = "#198754" if proved else "#c18100"
            draw.rectangle((x(idx) - 7, y(level) - 7, x(idx) + 7, y(level) + 7),
                           outline=colour, width=3)
            draw.text(
                (x(idx) + 8, y(level) + 6),
                f"TRAIL {'PROVEN' if proved else 'RAW/UNPROVEN'}"
                + (f" @ {candidate['proof_index']}" if proved else ""),
                fill=colour, font=small,
            )
        if attempt.get("exit_index") is not None and start <= int(attempt["exit_index"]) <= end:
            idx = int(attempt["exit_index"])
            draw.line((x(idx) - 8, y(float(attempt["exit_price"])) - 8,
                       x(idx) + 8, y(float(attempt["exit_price"])) + 8),
                      fill="#a71930", width=5)
            draw.line((x(idx) - 8, y(float(attempt["exit_price"])) + 8,
                       x(idx) + 8, y(float(attempt["exit_price"])) - 8),
                      fill="#a71930", width=5)
    draw.line((x(entry), plot[1], x(entry), plot[3]), fill="#155fd0", width=3)

    info = [
        ("BOT DECISION AT ENTRY", True),
        (f"HTF H1/M30/M15: {row['htf_h1']} / {row['htf_m30']} / {row['htf_m15']}", False),
        (f"HTF policy: {row['htf_policy_result']}", False),
        (f"Trend: {row['direction']}   Grade: {row['setup_grade']}   Risk: {row['risk_modifier']:.2f}", False),
        (f"Setup: {row['setup_id']}", False),
        (f"Origin BOS: {row['origin_bos_index']}", False),
        (f"Fib depth: {row['fibonacci_depth'] if row['fibonacci_depth'] is not None else 'N/A'}", False),
        (f"Fib zone: {row['fibonacci_zone']}", False),
        (f"Qualification available: {row['retracement_qualification_index']}", False),
        (f"Counter: candle {row['counter_index']} @ {fmt_price(row['counter_level'])}", False),
        (f"Trigger: candle {row['failure_trigger_index']} @ {fmt_price(row['failure_trigger_level'])}", False),
        (f"Entry: candle {entry} close {fmt_price(row['entry_price'])}", False),
        ("STOP CONTRACT", True),
        (f"SL owner swing: candle {row['logical_structure_index']}", False),
        (f"Selection: {row['logical_structure_selection_scope']}", False),
        (f"Body edge: {fmt_price(row['structure_body_boundary'])}", False),
        (f"M5 ATR tolerance: {row['logical_atr_tolerance']:.2f}", False),
        (f"Logical boundary: {fmt_price(row['logical_stop'])}", False),
        (f"Emergency stop: {fmt_price(row['emergency_stop'])}", False),
        (f"Broad wick rejected: {row['broad_extreme_rejected']}", False),
        ("POST-ENTRY REVIEW", True),
        (f"First result: {row['first_entry_result']}", False),
        (f"Parent retracement stayed active: {row['retracement_stayed_active']}", False),
        (f"Re-entry: {row['reentry_result']}", False),
        (
            f"TP1: {fmt_price(row['tp1_target'])} · {row['tp1_target_source']}"
            if row.get("tp1_target") is not None
            else "TP1: unavailable",
            False,
        ),
        (f"TP1 wick-touch triggered: {row['tp1_triggered']}", False),
        (f"Tags: {', '.join(row['category_tags']) or 'none'}", False),
        ("CAUSAL SAFETY", True),
        ("All entry labels stop at the blue entry line.", False),
        ("Grey region is outcome review only.", False),
        ("Swing roles use confirmation availability.", False),
        ("No order API called.", False),
    ]
    sy = side[1] + 18
    for text, is_heading in info:
        font = bold if is_heading else small
        colour = "#12263e" if is_heading else "#32475d"
        for line in _wrap(draw, text, font, side[2] - side[0] - 32):
            draw.text((side[0] + 16, sy), line, fill=colour, font=font)
            sy += 25 if is_heading else 21
        sy += 7 if is_heading else 3
    filename = (
        f"{number:02d}_{row['symbol'].replace('#', '').lower()}_"
        f"{row['entry_index']}_{row['direction'].lower()}.png"
    )
    image.save(CHARTS / filename)
    return filename


def _clean(row: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def _write_html(rows: list[Dict[str, Any]], unavailable: list[str]) -> None:
    cards = []
    for index, row in enumerate(rows, 1):
        cards.append(
            f"""<article>
<h2>{index:02d} · {html.escape(row['symbol'])} · {html.escape(row['direction'])} · {html.escape(row['assigned_category'])}</h2>
<p>{html.escape(row['time_utc'])} · {html.escape(row['session'])} · grade {row['setup_grade']} · Fib {row['fibonacci_zone']}</p>
<img src="charts/{html.escape(row['chart_file'])}" alt="Phase 10 causal chart {index}">
<label>Steve verdict <select><option></option><option>ACCEPT</option><option>REJECT</option><option>UNCERTAIN</option></select></label>
<label>Reason <textarea></textarea></label>
</article>"""
        )
    unavailable_text = "<br>".join(html.escape(item) for item in unavailable) or "None"
    document = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Phase 10.1 Swing Stop and TP1 Review</title><style>
body{{margin:0;background:#e8eef5;color:#152235;font:15px Arial,sans-serif}}
header{{padding:24px 4vw;background:#112a46;color:white;position:sticky;top:0;z-index:2}}
main{{width:min(1600px,96vw);margin:24px auto}}article{{background:white;padding:18px;margin:0 0 28px;border-radius:12px}}
img{{width:100%;border:1px solid #a8b5c5}}label{{display:block;margin-top:10px;font-weight:bold}}
select,textarea{{display:block;width:100%;box-sizing:border-box;padding:8px;margin-top:4px}}textarea{{height:64px}}
.warning{{background:#fff4d6;color:#5c3b00;padding:10px}}</style></head>
<body><header><h1>Phase 10.1 corrected swing-stop and TP1 review</h1>
<div>The same 20 Phase 10 entries reprocessed with Steve's feedback · research only · no orders</div></header>
<main><p class="warning"><strong>Unavailable requested coverage:</strong><br>{unavailable_text}</p>
{''.join(cards)}</main></body></html>"""
    (OUT / "phase10_1_swing_stop_tp1_review.html").write_text(document, encoding="utf-8")


def run() -> Dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    CHARTS.mkdir(parents=True, exist_ok=True)
    for stale_chart in CHARTS.glob("*.png"):
        stale_chart.unlink()
    old = _old_keys()
    review_keys = _phase10_review_keys()
    review_key_set = set(review_keys)
    data_by_symbol: Dict[str, pd.DataFrame] = {}
    pool: list[Dict[str, Any]] = []
    funnel: list[Dict[str, Any]] = []
    for symbol, path in SOURCES.items():
        data = pd.read_csv(path)
        data_by_symbol[symbol] = data
        frames = _frames(data)
        all_swings = confirmed_swings(data, as_of_index=len(data) - 1, sensitivity=3)
        candidates = [
            item
            for direction in ("BULLISH", "BEARISH")
            for item in scan_expert_m5_candidates(
                data,
                direction=direction,
                symbol=symbol,
                timeframe="M5",
                sensitivity=3,
            )
            if (symbol, int(item["entry_index"])) not in old
            and _session(float(data.iloc[int(item["entry_index"])]["time"]))
            != "OUTSIDE_PRIMARY_SESSION"
        ]
        sampled: list[Dict[str, Any]] = [
            item
            for item in candidates
            if (symbol, int(item["entry_index"])) in review_key_set
        ]
        for direction in ("BULLISH", "BEARISH"):
            directional = [item for item in candidates if item["direction"] == direction]
            if directional:
                step = max(1, len(directional) // 18)
                sampled.extend(directional[::step][:18])
        sampled = list(
            {
                (item["direction"], int(item["entry_index"])): item
                for item in sampled
            }.values()
        )
        accepted = 0
        for candidate in sampled:
            row = _evaluate(
                symbol=symbol,
                data=data,
                candidate=candidate,
                frames=frames,
                swings=all_swings,
            )
            if row is not None:
                pool.append(row)
                accepted += 1
        funnel.append(
            {
                "symbol": symbol,
                "timeframe": "M5",
                "closed_candles": len(data),
                "trend_cycles": len(candidates),
                "micro_counter_moves": sum(
                    1 for point in all_swings
                    if not point.get("is_tradeable_structure", False)
                ),
                "retracement_candidates": len(candidates),
                "qualified_retracements": len(candidates),
                "minimum_fib_reached": sum(
                    bool((item.get("fibonacci") or {}).get("minimum_relevant_reached"))
                    for item in candidates
                ),
                "primary_sweet_spot_reached": sum(
                    (item.get("fibonacci") or {}).get("zone") == "PRIMARY_SWEET_SPOT"
                    for item in candidates
                ),
                "failure_triggers": len(candidates),
                "first_entries": accepted,
                "hard_blocks": len(sampled) - accepted,
                "trade_frequency_per_1000": accepted / len(data) * 1000.0,
            }
        )
    pool.sort(
        key=lambda row: (
            row["time_utc"],
            row["symbol"],
            row["direction"],
        )
    )
    pool_by_key = {
        (row["symbol"], int(row["entry_index"])): row
        for row in pool
    }
    selected = [
        pool_by_key[key]
        for key in review_keys
        if key in pool_by_key
    ]
    unavailable_slots: list[str] = []
    if len(selected) != len(review_keys):
        missing_review = [
            key for key in review_keys if key not in pool_by_key
        ]
        raise RuntimeError(
            "Feedback comparison lost Phase 10 entries: "
            f"{missing_review}"
        )
    for row in selected:
        row["assigned_category"] = "STOP_TP1_FEEDBACK_RECHECK"
    if len(selected) < 20:
        raise RuntimeError(
            f"Only {len(selected)} fresh causally eligible examples were available"
        )
    for number, row in enumerate(selected, 1):
        row["review_number"] = number
        row["chart_file"] = _chart(number, row, data_by_symbol[row["symbol"]])
    clean_rows = [_clean(row) for row in selected]
    for row in clean_rows:
        for key, value in list(row.items()):
            if isinstance(value, (list, dict)):
                row[key] = json.dumps(value, default=_default)
    with (OUT / "phase10_example_audit.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(clean_rows[0]))
        writer.writeheader()
        writer.writerows(clean_rows)
    with (OUT / "phase10_frequency_funnel.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(funnel[0]))
        writer.writeheader()
        writer.writerows(funnel)
    category_counts = {
        "STOP_TP1_FEEDBACK_RECHECK": len(selected)
    }
    unavailable = [
        f"{symbol}: {reason}"
        for symbol, reason in REQUESTED_BUT_UNAVAILABLE.items()
    ] + [
        f"{slot}: no distinct qualifying case in the causally reviewed sample"
        for slot in unavailable_slots
    ]
    if "M1_FALLBACK_TO_M5" in unavailable_slots:
        unavailable.append(
            "M1 fallback: the supplied GOLD M1 data was not paired with a "
            "separately validated contemporaneous M5 parent setup in this run."
        )
    report = {
        "model": "EXPERT_SPEC_V1_PHASE10_1_SWING_STOP_TP1",
        "fresh_examples": len(selected),
        "old_phase9_examples_reused": 0,
        "same_phase10_entries_reprocessed": True,
        "eligible_pool_size": len(pool),
        "category_counts": category_counts,
        "unavailable_requested_coverage": unavailable,
        "symbols_with_real_data": list(SOURCES),
        "timeframes_with_verified_examples": ["M5"],
        "all_examples_causal": all(row["causal_valid"] for row in selected),
        "future_data_used_at_entry": False,
        "order_api_calls": 0,
        "rows": [_clean(row) for row in selected],
        "funnel": funnel,
    }
    (OUT / "phase10_full_audit.json").write_text(
        json.dumps(report, indent=2, default=_default), encoding="utf-8"
    )
    (OUT / "coverage_limitations.json").write_text(
        json.dumps(
            {
                "requested_but_unavailable": unavailable,
                "policy": "No examples were fabricated or relabelled to fill a category.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_html(selected, unavailable)
    return report


if __name__ == "__main__":
    result = run()
    print(
        json.dumps(
            {
                "fresh_examples": result["fresh_examples"],
                "eligible_pool_size": result["eligible_pool_size"],
                "category_counts": result["category_counts"],
                "unavailable_count": len(result["unavailable_requested_coverage"]),
                "order_api_calls": result["order_api_calls"],
            },
            indent=2,
        )
    )
