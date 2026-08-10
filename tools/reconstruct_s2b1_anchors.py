from __future__ import annotations

from pathlib import Path
from typing import Any
import html
import json
import sys

import pandas as pd
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.expert_strategy import scan_expert_m5_candidates
from core.synchronized_m1_replay import (
    COUNTER_CONFIRMED_ACTIVE,
    EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE,
    arbitrate_first_valid_entry,
    build_parent_contract,
    find_m1_child_entry,
)
from simulator.config import load_config
from tools.run_s2b_research import _csv, _font, _panel
from tools.run_s2b1_research import ANCHORS, DEFAULT_ACCEPTED_CONTROL, OUT


ANCHOR_VISUALS = OUT / "manual_anchors"


def _result(
    *, parent: dict[str, Any], m1: pd.DataFrame, decision_time: float, policy: str
) -> dict[str, Any]:
    report = find_m1_child_entry(
        parent=parent,
        m1_data=m1,
        sensitivity=2,
        decision_time=decision_time,
        permission_policy=policy,
        second_touch_enabled=True,
    )
    arbitration = arbitrate_first_valid_entry(
        parent=parent,
        m1_result=report,
        decision_time=decision_time,
    )
    return {"report": report, "arbitration": arbitration, "entry": arbitration.get("entry") or {}}


def _entry_summary(result: dict[str, Any]) -> dict[str, Any]:
    entry = result["entry"]
    return {
        "owner": result["arbitration"].get("entry_owner"),
        "state": entry.get("state"),
        "entry_time": entry.get("entry_time"),
        "entry_price": entry.get("entry_price"),
        "logical_stop": entry.get("logical_stop"),
        "logical_stop_owner_index": entry.get("logical_stop_owner_index"),
        "trigger_index": entry.get("failure_trigger_index"),
        "trigger_available_index": entry.get("failure_trigger_available_at_index"),
        "trigger_price": entry.get("failure_trigger_price"),
        "second_touch_entry": bool(entry.get("second_touch_entry")),
        "second_touch": entry.get("second_touch") or {},
        "causal_valid": entry.get("causal_valid"),
        "order_api_called": entry.get("order_api_called", False),
    }


def _event_time(data: pd.DataFrame, event: dict[str, Any] | None) -> float | None:
    if not event or event.get("swing_index") is None:
        return None
    index = int(event["swing_index"])
    return float(data.iloc[index]["time"]) + 60.0 if 0 <= index < len(data) else None


def _chart(number: int, row: dict[str, Any], m1: pd.DataFrame, m5: pd.DataFrame) -> str:
    b = row["B"]
    c = row["C"]
    decision = float(b["entry_time"] or c["entry_time"])
    upper = m5.iloc[
        max(0, int((m5.time.astype(float) + 300).searchsorted(decision - 70 * 300, side="left"))) :
        min(len(m5), int((m5.time.astype(float) + 300).searchsorted(decision + 20 * 300, side="right")))
    ].reset_index(drop=True)
    lower = m1.iloc[
        max(0, int((m1.time.astype(float) + 60).searchsorted(decision - 135 * 60, side="left"))) :
        min(len(m1), int((m1.time.astype(float) + 60).searchsorted(decision + 45 * 60, side="right")))
    ].reset_index(drop=True)
    image = Image.new("RGB", (1700, 1120), "#edf4fb")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1700, 112), fill="#123b66")
    draw.text((28, 17), f"Manual anchor {number} · {row['symbol']} · {row['direction']} · {row['setup_suffix']}", fill="white", font=_font(29, True))
    draw.text((28, 64), "Hand-mark reconstruction: touch wicks → migrated trigger → body-close BOS → touch-2 wick stop", fill="white", font=_font(18))
    upper_markers = [(float(row["parent_armed_time"]), "PARENT ARMED", "#7849ff"), (float(row["parent_active_time"]), "PARENT ACTIVE", "#e07a00")]
    lower_markers: list[tuple[float, str, str]] = []
    touch = b.get("second_touch") or {}
    for event, label, color in (
        (touch.get("touch_1"), "1 · T1", "#7849ff"),
        (touch.get("separating_reaction"), "R · REACTION", "#4c75a3"),
        (touch.get("touch_2"), "2 · T2", "#b4234d"),
        (touch.get("active_trigger"), "3 · NEW TRIGGER", "#9a62ff"),
    ):
        stamp = _event_time(m1, event)
        if stamp is not None:
            lower_markers.append((stamp, label, color))
    if b.get("entry_time") is not None:
        lower_markers.append((float(b["entry_time"]), "4 · B ENTRY", "#e07a00"))
    if c.get("entry_time") is not None:
        lower_markers.append((float(c["entry_time"]), "C · EARLY", "#008b75"))
    lower_levels = []
    if b.get("logical_stop") is not None:
        lower_levels.append((float(b["logical_stop"]), "B STOP", "#b4234d"))
    if b.get("trigger_price") is not None:
        lower_levels.append((float(b["trigger_price"]), "NEW TRIGGER", "#9a62ff"))
    if b.get("entry_price") is not None:
        lower_levels.append((float(b["entry_price"]), "BOS CLOSE", "#e07a00"))
    _panel(draw, upper, (30, 130, 1260, 565), seconds=300, markers=upper_markers, levels=[], decision_time=decision)
    _panel(draw, lower, (30, 605, 1260, 1045), seconds=60, markers=lower_markers, levels=lower_levels, decision_time=decision)
    draw.rounded_rectangle((1280, 130, 1670, 1045), radius=12, fill="#ffffff", outline="#9ab0c8", width=2)
    touch_1 = touch.get("touch_1") or {}
    reaction = touch.get("separating_reaction") or {}
    touch_2 = touch.get("touch_2") or {}
    trigger = touch.get("active_trigger") or {}
    details = (
        "BOT DECISION AT ENTRY\n\n"
        f"Parent: {row['setup_suffix']}\n"
        f"Direction: {row['direction']}\n"
        f"State: {touch.get('state', 'NO_SECOND_TOUCH')}\n\n"
        f"1  Touch 1 wick\n   {touch_1.get('price', 'N/A')}\n\n"
        f"R  Separating reaction\n   {reaction.get('price', 'N/A')}\n\n"
        f"2  Touch 2 wick\n   {touch_2.get('price', 'N/A')}\n\n"
        f"3  New trigger\n   {trigger.get('price', 'N/A')}\n\n"
        f"4  BOS close / entry\n   {b.get('entry_price', 'N/A')}\n\n"
        f"STOP OWNER\n   {b.get('logical_stop', 'N/A')}\n\n"
        f"Trigger superseded: {touch.get('old_trigger_superseded', False)}\n"
        f"B owner: {b.get('owner')}\n"
        f"C owner: {c.get('owner')}\n\n"
        "CAUSAL SAFETY\n"
        "Closed candles only\n"
        "Grey = future review\n"
        "No order API called"
    )
    draw.multiline_text((1305, 155), details, fill="#193a5b", font=_font(17), spacing=7)
    draw.text((32, 1070), f"B state={touch.get('state', 'NO_SECOND_TOUCH')} · superseded={touch.get('old_trigger_superseded', False)} · future candles grey/review-only · zero orders", fill="#263f5c", font=_font(16, True))
    filename = f"anchor_{number}_{row['symbol'].replace('#','')}_{row['setup_suffix']}.png"
    image.save(ANCHOR_VISUALS / filename)
    return filename


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ANCHOR_VISUALS.mkdir(parents=True, exist_ok=True)
    control = pd.read_csv(DEFAULT_ACCEPTED_CONTROL, keep_default_na=False).to_dict("records")
    config = load_config()
    cache: dict[str, tuple[pd.DataFrame, pd.DataFrame, dict[str, dict[str, Any]]]] = {}
    rows: list[dict[str, Any]] = []
    causal_rows: list[dict[str, Any]] = []
    for symbol, direction, suffix, screenshot in ANCHORS:
        if symbol not in cache:
            directory = next(
                path
                for path in (ROOT / "simulator_data/library").iterdir()
                if path.is_dir()
                and json.loads((path / "manifest.json").read_text(encoding="utf-8"))["symbol"] == symbol
            )
            m1 = pd.read_csv(directory / "M1.csv")
            m5 = pd.read_csv(directory / "M5.csv")
            candidates: dict[str, dict[str, Any]] = {}
            for side in ("BULLISH", "BEARISH"):
                for candidate in scan_expert_m5_candidates(
                    m5,
                    direction=side,
                    symbol=symbol,
                    sensitivity=config.engine_sensitivity,
                ):
                    candidates.setdefault(candidate["setup_id"], candidate)
            cache[symbol] = (m1, m5, candidates)
        m1, m5, candidates = cache[symbol]
        setup_id = f"{symbol}|M5|EXPERT_SPEC_V1|{direction}|{suffix}"
        candidate = candidates[setup_id]
        terminal = int(candidate["entry_index"])
        decision_time = float(m5.iloc[terminal]["time"]) + 300.0
        parent = build_parent_contract(
            candidate=candidate,
            m5_data=m5.iloc[: terminal + 1],
            symbol=symbol,
        )
        visible = m1[m1.time.astype(float) + 60 <= decision_time].reset_index(drop=True)
        b_result = _result(parent=parent, m1=visible, decision_time=decision_time, policy=COUNTER_CONFIRMED_ACTIVE)
        c_result = _result(parent=parent, m1=visible, decision_time=decision_time, policy=EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE)
        accepted = next(row for row in control if row["setup_id"] == setup_id)
        row = {
            "screenshot": screenshot,
            "symbol": symbol,
            "direction": direction,
            "setup_suffix": suffix,
            "setup_id": setup_id,
            "state": "RECONSTRUCTED",
            "A": {
                "entry_time": float(accepted["baseline_entry_epoch"]),
                "entry_price": float(accepted["baseline_entry_price"]),
                "logical_stop": float(accepted["baseline_logical_stop"]),
                "owner": accepted["baseline_entry_timeframe"],
            },
            "B": _entry_summary(b_result),
            "C": _entry_summary(c_result),
            "parent_armed_time": parent["armed_time"],
            "parent_active_time": parent["active_time"],
            "same_parent_identity": True,
            "research_only": True,
            "order_api_called": False,
            "manual_verdict": "",
            "manual_reason": "",
        }
        rows.append(row)
        frozen_time = float(row["B"]["entry_time"])
        frozen_index = int(row["B"]["logical_stop_owner_index"] or 0)
        variants: dict[str, pd.DataFrame] = {
            "PREFIX_ONLY": visible[visible.time.astype(float) + 60 <= frozen_time].copy(),
            "ACTUAL_SUFFIX": visible.copy(),
            "MODIFIED_SUFFIX": visible.copy(),
            "REVERSAL_SUFFIX": visible.copy(),
        }
        cutoff = variants["ACTUAL_SUFFIX"].time.astype(float) + 60 > frozen_time
        variants["MODIFIED_SUFFIX"].loc[cutoff, ["open", "high", "low", "close"]] *= 1.01
        variants["REVERSAL_SUFFIX"].loc[cutoff, ["open", "high", "low", "close"]] *= 0.99
        reference = None
        for variant_name, variant_data in variants.items():
            replay = _result(parent=parent, m1=variant_data.reset_index(drop=True), decision_time=frozen_time, policy=COUNTER_CONFIRMED_ACTIVE)
            summary = _entry_summary(replay)
            frozen = (summary["entry_time"], summary["entry_price"], summary["logical_stop"], summary["trigger_index"], frozen_index)
            reference = frozen if reference is None else reference
            causal_rows.append(
                {
                    "symbol": symbol,
                    "setup_id": setup_id,
                    "suffix_variant": variant_name,
                    "entry_time": summary["entry_time"],
                    "entry_price": summary["entry_price"],
                    "logical_stop": summary["logical_stop"],
                    "trigger_index": summary["trigger_index"],
                    "decision_identical_at_frozen_boundary": frozen == reference,
                    "order_api_called": False,
                }
            )
    manifest = []
    for number, row in enumerate(rows, 1):
        filename = _chart(number, row, cache[row["symbol"]][0], cache[row["symbol"]][1])
        manifest.append({"review_number": number, "symbol": row["symbol"], "setup_id": row["setup_id"], "chart_file": f"manual_anchors/{filename}", "manual_verdict": "", "manual_reason": ""})
    _csv(OUT / "s2b1_manual_anchor_reconstruction.csv", rows)
    _csv(OUT / "s2b1_manual_anchor_visual_manifest.csv", manifest)
    _csv(OUT / "s2b1_actual_suffix_causality_matrix.csv", causal_rows)
    articles = "\n".join(
        f"<article><h2>{row['review_number']} · {html.escape(row['symbol'])}</h2><p>{html.escape(row['setup_id'])}</p><img src='{html.escape(row['chart_file'])}'></article>"
        for row in manifest
    )
    (OUT / "s2b1_manual_anchor_review.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>S2B.1 manual anchors</title><style>body{font-family:Arial;background:#edf4fb;color:#12345b;margin:0}header{background:#123b66;color:#fff;padding:24px;position:sticky;top:0}main{max-width:1720px;margin:auto}article{background:#fff;margin:24px;padding:18px;border-radius:12px}img{width:100%;border:1px solid #9ab0c8}</style>"
        f"<header><h1>S2B.1 · four hand-marked anchor reconstructions</h1><p>Same accepted parents · closed candles · causal suffix matrix · research only · zero orders</p></header><main>{articles}</main>",
        encoding="utf-8",
    )
    summary = {
        "anchors_reconstructed": len(rows),
        "second_touch_canonical_entries": sum(row["B"]["second_touch_entry"] for row in rows),
        "causality_rows": len(causal_rows),
        "causality_all_identical": all(row["decision_identical_at_frozen_boundary"] for row in causal_rows),
        "order_api_called": False,
    }
    (OUT / "s2b1_manual_anchor_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["causality_all_identical"] and not summary["order_api_called"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
