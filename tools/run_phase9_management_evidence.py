from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
from typing import Any, Dict

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.expert_strategy import (  # noqa: E402
    build_expert_htf_context,
    confirmed_swings,
    scan_expert_m5_candidates,
)
from core.pipeline_runner import PipelineOptions, run_pipeline  # noqa: E402
from core.setup_lifecycle import PipelineRuntimeState  # noqa: E402
from tools.run_phase7_expert_audit import resample_closed_m5  # noqa: E402


OUTPUT_DIR = PROJECT_ROOT / "phase9_evidence"
CHART_DIR = OUTPUT_DIR / "charts"
OLD_MANIFEST = (
    PROJECT_ROOT
    / "phase7_evidence"
    / "NY_OPEN_10"
    / "ny_open_10_manifest.json"
)
SOURCES = {
    "GOLD#": (
        PROJECT_ROOT
        / "research_data"
        / "GOLD_M5_NY_open_closed.csv"
    ),
    "GER40Cash#": (
        PROJECT_ROOT
        / "research_data"
        / "GER40Cash_M5_phase5b_closed.csv"
    ),
    "US100Cash#": (
        PROJECT_ROOT
        / "research_data"
        / "US100Cash_M5_closed.csv"
    ),
}
SESSION_CONFIG = {
    "timezone": "UTC",
    "allowed_sessions": {
        "LONDON": ["07:00", "11:00"],
        "NEW_YORK": ["13:00", "17:00"],
        "OVERLAP": ["13:00", "16:00"],
    },
    "note": (
        "Research labels are configurable UTC windows; they do not "
        "hard-block the canonical strategy."
    ),
}


def _json_default(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(type(value).__name__)


def _session(epoch: float) -> str:
    timestamp = pd.to_datetime(epoch, unit="s", utc=True)
    minutes = timestamp.hour * 60 + timestamp.minute
    if 13 * 60 <= minutes < 16 * 60:
        return "OVERLAP"
    if 7 * 60 <= minutes < 11 * 60:
        return "LONDON"
    if 13 * 60 <= minutes < 17 * 60:
        return "NEW_YORK"
    return "OUTSIDE_CONFIGURED_REVIEW_WINDOW"


def _candles(
    axis: plt.Axes,
    data: pd.DataFrame,
    start: int,
    end: int,
) -> None:
    width = 0.62
    for index in range(start, end + 1):
        row = data.iloc[index]
        open_price = float(row["open"])
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        colour = "#168f75" if close >= open_price else "#d94b55"
        axis.vlines(index, low, high, color=colour, linewidth=0.9)
        bottom = min(open_price, close)
        height = max(abs(close - open_price), 1e-8)
        axis.add_patch(
            Rectangle(
                (index - width / 2, bottom),
                width,
                height,
                facecolor=colour,
                edgecolor=colour,
                linewidth=0.7,
            )
        )


def _candidate_map(
    data: pd.DataFrame,
    symbol: str,
) -> Dict[tuple[str, int], Dict[str, Any]]:
    result: Dict[tuple[str, int], Dict[str, Any]] = {}
    for direction in ("BULLISH", "BEARISH"):
        for item in scan_expert_m5_candidates(
            data,
            direction=direction,
            symbol=symbol,
            timeframe="M5",
            sensitivity=3,
        ):
            result[(direction, int(item["entry_index"]))] = item
    return result


def _classifications(attempt: Dict[str, Any], manager: Dict[str, Any]) -> list[str]:
    labels: list[str] = []
    direction = attempt["direction"]
    if attempt.get("trail_movements"):
        labels.append(
            "BULLISH_M5_SUCCESSFUL_HL_TRAIL"
            if direction == "BULLISH"
            else "BEARISH_M5_SUCCESSFUL_LH_TRAIL"
        )
    if attempt.get("trail_candidates") and not attempt.get(
        "trail_movements"
    ):
        labels.append("RAW_SWING_REJECTED_UNPROVEN")
    if attempt.get("exit_reason") == "OPPOSING_MEANINGFUL_BOS":
        labels.append("OPPOSING_BOS_MANAGEMENT_EXIT")
    events = [
        item.get("event")
        for item in attempt.get("history", [])
    ]
    if (
        "WICK_THROUGH_LOGICAL_LEVEL_SURVIVED" in events
        and attempt.get("exit_reason")
        == "SETUP_LOGICAL_BODY_CLOSE_INVALIDATION"
    ):
        labels.append("LOGICAL_BODY_CLOSE_AFTER_WICK_SURVIVAL")
    if int(manager.get("reentry_count", 0)) == 1:
        labels.append("VALID_ONE_TIME_REENTRY")
    if manager.get("reentry_state") == (
        "REENTRY_REJECTED_DOMINANT_PROTECTION_FAILED"
    ):
        labels.append("REENTRY_REJECTED_DOMINANT_PROTECTION_FAILED")
    if not labels:
        labels.append("NO_PROVEN_TRAIL_WITHIN_REVIEW_WINDOW")
    return labels


def _replay(
    *,
    data: pd.DataFrame,
    symbol: str,
    candidate: Dict[str, Any],
    htf_frames: Dict[str, pd.DataFrame],
    review_after: int = 60,
    all_swings: list[Dict[str, Any]] | None = None,
    canonical_validate: bool = True,
) -> Dict[str, Any]:
    entry_index = int(candidate["entry_index"])
    end = min(len(data) - 1, entry_index + review_after)
    context = build_expert_htf_context(
        decision_candle_open_time=data.iloc[entry_index]["time"],
        decision_timeframe_seconds=300,
        frame_data=htf_frames,
        sensitivity=3,
    )
    if context.get("approved_direction") != candidate.get("direction"):
        return {"eligible": False, "reason": "HTF_DIRECTION_NOT_APPROVED"}
    runtime = PipelineRuntimeState()
    if canonical_validate:
        pipeline = run_pipeline(
            data=data,
            symbol=symbol,
            timeframe="M5",
            as_of_index=entry_index,
            options=PipelineOptions(
                strategy_model="EXPERT_SPEC_V1",
                engine_sensitivity=3,
            ),
            runtime_state=runtime,
            higher_timeframe_context=context,
        )
        entry = pipeline.snapshot["entry"]
        if not entry.get("ready"):
            return {
                "eligible": False,
                "reason": entry.get(
                    "state", "CANONICAL_ENTRY_NOT_READY"
                ),
            }
    else:
        entry = {}
        pipeline = None
    swings = [
        point
        for point in (
            all_swings
            if all_swings is not None
            else confirmed_swings(
                data,
                as_of_index=end,
                sensitivity=3,
            )
        )
        if int(point["confirmed_at_index"]) <= end
    ]
    if not canonical_validate:
        management = runtime.expert_trade_manager.evaluate(
            data=data,
            symbol=symbol,
            timeframe="M5",
            as_of_index=end,
            direction=candidate["direction"],
            context=context,
            confirmed_swings=swings,
            canonical_entry=candidate,
        )
        attempt = management.get("attempts", [{}])[0]
        entry = {
            "ready": True,
            "index": entry_index,
            "entry_index": entry_index,
            "price": candidate["entry_price"],
            "direction": candidate["direction"],
            "setup_id": candidate["setup_id"],
            "trigger_index": candidate["trigger"]["index"],
            "trigger_level": candidate["trigger"]["level"],
            "setup_invalidation_contract": attempt[
                "logical_invalidation"
            ],
            "emergency_broker_stop_contract": attempt[
                "emergency_broker_stop_contract"
            ],
        }
        snapshot = {
            "entry": entry,
            "setup_invalidation": attempt["logical_invalidation"],
            "protection": attempt["dominant_decision_protection"],
            "trailing_protection": management,
        }
    else:
        snapshot = pipeline.snapshot
    management = runtime.expert_trade_manager.evaluate(
        data=data,
        symbol=symbol,
        timeframe="M5",
        as_of_index=end,
        direction=candidate["direction"],
        context=context,
        confirmed_swings=swings,
        canonical_entry=None,
    )
    attempt = (
        management.get("attempts", [{}])[0]
        if management.get("attempts")
        else {}
    )
    return {
        "eligible": True,
        "entry": entry,
        "snapshot": snapshot,
        "context": context,
        "management": management,
        "initial_attempt": attempt,
        "classifications": _classifications(attempt, management),
        "review_end_index": end,
    }


def _row(
    *,
    symbol: str,
    data: pd.DataFrame,
    candidate: Dict[str, Any],
    replay: Dict[str, Any],
    source_group: str,
) -> Dict[str, Any]:
    entry = replay["entry"]
    invalidation = entry["setup_invalidation_contract"]
    emergency = entry["emergency_broker_stop_contract"]
    management = replay["management"]
    attempt = replay["initial_attempt"]
    index = int(entry["index"])
    epoch = float(data.iloc[index]["time"])
    return {
        "source_group": source_group,
        "symbol": symbol,
        "timeframe": "M5",
        "entry_index": index,
        "time_utc": pd.to_datetime(
            epoch, unit="s", utc=True
        ).isoformat(),
        "session": _session(epoch),
        "direction": entry["direction"],
        "setup_id": entry["setup_id"],
        "trigger_index": entry["trigger_index"],
        "trigger_level": entry["trigger_level"],
        "entry_price": entry["price"],
        "dominant_role": (
            replay["snapshot"]["protection"].get("protection_role")
        ),
        "dominant_index": replay["snapshot"]["protection"].get("index"),
        "dominant_level": replay["snapshot"]["protection"].get("level"),
        "dominant_timeframe": (
            replay["snapshot"]["protection"].get("timeframe")
        ),
        "logical_structure_index": invalidation["structure_index"],
        "logical_structure_type": invalidation["structure_type"],
        "logical_wick_price": invalidation["wick_price"],
        "logical_body_close": invalidation["body_close_level"],
        "logical_boundary": invalidation["logical_boundary"],
        "atr_at_entry": invalidation["atr_at_entry"],
        "atr_tolerance": invalidation["atr_tolerance"],
        "emergency_broker_stop": emergency["price"],
        "broad_pullback_extreme": invalidation[
            "broad_pullback_extreme"
        ],
        "broad_extreme_rejected": invalidation[
            "broad_pullback_extreme_rejected"
        ],
        "trail_candidate_count": len(
            attempt.get("trail_candidates", [])
        ),
        "proven_trail_count": len(
            attempt.get("proven_trails", [])
        ),
        "trail_movement_count": len(
            attempt.get("trail_movements", [])
        ),
        "exit_index": attempt.get("exit_index"),
        "exit_reason": attempt.get("exit_reason"),
        "reentry_count": management.get("reentry_count"),
        "reentry_state": management.get("reentry_state"),
        "classifications": replay["classifications"],
        "review_end_index": replay["review_end_index"],
        "causal_valid": (
            invalidation["causal_valid"]
            and not invalidation["post_entry_candles_used"]
        ),
        "order_api_called": False,
        "manual_review": "",
        "manual_reason": "",
    }


def _render_chart(
    *,
    number: int,
    row: Dict[str, Any],
    data: pd.DataFrame,
    replay: Dict[str, Any],
) -> str:
    entry_index = int(row["entry_index"])
    end = int(row["review_end_index"])
    start = max(0, entry_index - 40)
    attempt = replay["initial_attempt"]
    snapshot = replay["snapshot"]
    invalidation = snapshot["setup_invalidation"]
    dominant = snapshot["protection"]
    emergency = row["emergency_broker_stop"]
    direction = row["direction"]
    figure = plt.figure(figsize=(21, 12), facecolor="#f6f8fb")
    grid = figure.add_gridspec(
        2, 1, height_ratios=[5.7, 2.0], hspace=0.10
    )
    chart = figure.add_subplot(grid[0])
    notes = figure.add_subplot(grid[1])
    chart.set_facecolor("white")
    notes.set_facecolor("#edf2f7")
    _candles(chart, data, start, end)
    chart.axvspan(
        entry_index + 0.5,
        end + 0.5,
        color="#64748b",
        alpha=0.08,
        label="Post-entry management evidence",
    )
    chart.axvline(
        entry_index,
        color="#1d4ed8",
        linewidth=2.3,
        label=f"ENTRY close {row['entry_price']:.2f}",
    )
    chart.hlines(
        float(row["trigger_level"]),
        int(row["trigger_index"]),
        entry_index,
        color="#7c3aed",
        linewidth=2.2,
        label=f"Entry trigger {row['trigger_level']:.2f}",
    )
    if dominant.get("level") is not None:
        chart.axhline(
            float(dominant["level"]),
            color="#15803d",
            linestyle="-.",
            linewidth=1.8,
            label=(
                "A Dominant decision protection "
                f"{dominant.get('timeframe')} {dominant['level']:.2f}"
            ),
        )
    chart.axhline(
        float(invalidation["logical_boundary"]),
        color="#ea580c",
        linestyle="--",
        linewidth=2.0,
        label=(
            "B Setup logical invalidation "
            f"{invalidation['logical_boundary']:.2f}"
        ),
    )
    chart.scatter(
        [int(invalidation["structure_index"])],
        [float(invalidation["wick_price"])],
        marker="D",
        s=115,
        color="#ea580c",
        zorder=8,
    )
    chart.annotate(
        (
            f"RELEVANT PRE-BOS {invalidation['structure_type']}\n"
            f"candle {invalidation['structure_index']} · "
            f"wick {invalidation['wick_price']:.2f}\n"
            f"body close {invalidation['body_close_level']:.2f}"
        ),
        xy=(
            int(invalidation["structure_index"]),
            float(invalidation["wick_price"]),
        ),
        xytext=(
            int(invalidation["structure_index"]) - 7,
            float(invalidation["wick_price"]),
        ),
        fontsize=8.5,
        fontweight="bold",
        ha="right",
        arrowprops={"arrowstyle": "->", "color": "#ea580c"},
    )
    chart.axhline(
        float(emergency),
        color="#7f1d1d",
        linestyle=":",
        linewidth=2.2,
        label=f"C Emergency broker stop {emergency:.2f}",
    )
    for candidate in attempt.get("trail_candidates", []):
        x = int(candidate["structure_index"])
        level = float(candidate["structure_level"])
        proved = candidate.get("proof_index") is not None
        chart.scatter(
            [x],
            [level],
            s=105,
            facecolors="#dcfce7" if proved else "#fef3c7",
            edgecolors="#15803d" if proved else "#d97706",
            linewidths=2.0,
            zorder=8,
        )
        label = (
            f"PROVEN {candidate['structure_type']}\n"
            f"formed {x}, proved {candidate['proof_index']}"
            if proved
            else (
                f"TRAIL CANDIDATE — UNPROVEN\n"
                f"formed {x}, visible {candidate['confirmed_at_index']}"
            )
        )
        chart.annotate(
            label,
            xy=(x, level),
            xytext=(
                x + 3,
                level,
            ),
            fontsize=7.8,
            color="#166534" if proved else "#92400e",
            arrowprops={
                "arrowstyle": "->",
                "color": "#15803d" if proved else "#d97706",
            },
        )
    for movement in attempt.get("trail_movements", []):
        chart.hlines(
            float(movement["new_level"]),
            int(movement["as_of_index"]),
            end,
            color="#16a34a",
            linewidth=1.8,
            label=(
                "D Proven trailing protection"
                if movement
                == attempt.get("trail_movements", [None])[0]
                else None
            ),
        )
        chart.axvline(
            int(movement["as_of_index"]),
            color="#16a34a",
            alpha=0.45,
            linewidth=1.0,
        )
    tp1 = attempt.get("position_1_target")
    if (
        tp1 is not None
        and attempt.get("management_profile")
        in {"TWIN_POSITION_50_50", "PARTIAL_PLUS_RUNNER"}
    ):
        chart.axhline(
            float(tp1),
            color="#0e7490",
            linestyle="--",
            linewidth=1.5,
            alpha=0.8,
            label=(
                f"TP1 {attempt.get('tp1_model')} {float(tp1):.2f}"
            ),
        )
    opposing = attempt.get("opposing_bos") or {}
    if opposing:
        chart.scatter(
            [int(opposing["index"])],
            [float(opposing["close"])],
            marker="X",
            s=155,
            color="#b91c1c",
            zorder=9,
            label="Opposing meaningful body-close BOS exit",
        )
    reentry_counter = replay["management"].get("reentry_counter") or {}
    reentry_trigger = replay["management"].get("reentry_trigger") or {}
    if reentry_counter:
        chart.scatter(
            [int(reentry_counter["index"])],
            [float(reentry_counter["level"])],
            marker="o",
            s=100,
            facecolor="#cffafe",
            edgecolor="#0891b2",
            linewidth=2.0,
            zorder=9,
        )
        chart.annotate(
            (
                "FRESH RE-ENTRY COUNTER-STRUCTURE\n"
                f"formed {reentry_counter['index']}, "
                f"confirmed {reentry_counter['confirmed_at_index']}"
            ),
            xy=(
                int(reentry_counter["index"]),
                float(reentry_counter["level"]),
            ),
            xytext=(
                int(reentry_counter["index"]) - 8,
                float(reentry_counter["level"]),
            ),
            ha="right",
            fontsize=7.6,
            color="#0e7490",
            arrowprops={"arrowstyle": "->", "color": "#0891b2"},
        )
    if reentry_trigger:
        chart.scatter(
            [int(reentry_trigger["index"])],
            [float(reentry_trigger["level"])],
            marker="s",
            s=95,
            facecolor="#cffafe",
            edgecolor="#0891b2",
            linewidth=2.0,
            zorder=9,
        )
        chart.annotate(
            (
                "FRESH RE-ENTRY BOS TRIGGER\n"
                f"formed {reentry_trigger['index']}, "
                f"confirmed {reentry_trigger['confirmed_at_index']}"
            ),
            xy=(
                int(reentry_trigger["index"]),
                float(reentry_trigger["level"]),
            ),
            xytext=(
                int(reentry_trigger["index"]) - 7,
                float(reentry_trigger["level"]),
            ),
            ha="right",
            fontsize=7.6,
            color="#0e7490",
            arrowprops={"arrowstyle": "->", "color": "#0891b2"},
        )
    for reentry in replay["management"].get("attempts", [])[1:]:
        chart.scatter(
            [int(reentry["entry_index"])],
            [float(reentry["entry_price"])],
            marker="*",
            s=220,
            color="#0891b2",
            zorder=9,
            label="One allowed fresh-structure re-entry",
        )
    timestamp = pd.to_datetime(
        float(data.iloc[entry_index]["time"]),
        unit="s",
        utc=True,
    )
    chart.set_title(
        (
            f"{number:02d} · {row['source_group']} · {row['symbol']} M5 · "
            f"{direction} · {timestamp:%Y-%m-%d %H:%M UTC} · "
            f"{row['session']}\n"
            "Steve V2: entry preserved; four protection roles remain separate"
        ),
        loc="left",
        fontsize=14,
        fontweight="bold",
    )
    chart.set_xlim(start - 1, end + 1)
    chart.grid(axis="y", color="#d8e0e8", alpha=0.75)
    chart.set_ylabel("Price")
    chart.set_xlabel("M5 source candle index")
    handles, labels = chart.get_legend_handles_labels()
    unique = dict(zip(labels, handles))
    chart.legend(
        unique.values(),
        unique.keys(),
        loc="upper left",
        fontsize=8.2,
        ncol=2,
    )

    notes.set_xticks([])
    notes.set_yticks([])
    for spine in notes.spines.values():
        spine.set_visible(False)
    trail_summary = (
        f"{len(attempt.get('trail_candidates', []))} candidate(s), "
        f"{len(attempt.get('proven_trails', []))} proven, "
        f"{len(attempt.get('trail_movements', []))} movement(s)"
    )
    lines = [
        "HOW TO READ THIS DECISION",
        (
            f"1 ENTRY (unchanged) — candle {entry_index} closed beyond "
            f"trigger {row['trigger_index']} at {row['trigger_level']:.2f}; "
            f"entry is its close {row['entry_price']:.2f}."
        ),
        (
            "2 INITIAL LOGICAL STOP — selected only from the relevant "
            f"pre-BOS {invalidation['structure_type']} at candle "
            f"{invalidation['structure_index']}; boundary "
            f"{invalidation['logical_boundary']:.2f} uses "
            f"{invalidation['atr_tolerance']:.2f} ATR tolerance."
        ),
        (
            "3 EMERGENCY STOP — "
            f"{emergency:.2f}; wider software/broker catastrophe protection, "
            "not the strategy's normal logical loss level."
        ),
        (
            "4 POST-ENTRY MANAGEMENT — "
            f"{trail_summary}. A raw swing never moves protection; the "
            "later same-direction body-close proof candle is shown."
        ),
        (
            "5 RESULT IN DISPLAY WINDOW — "
            f"exit={attempt.get('exit_reason') or 'NONE'}; "
            f"re-entry={replay['management'].get('reentry_state')}; "
            f"tags={', '.join(replay['classifications'])}."
        ),
        (
            "CAUSALITY — the initial stop used zero post-entry candles. "
            "Future candles are visible only to review management after "
            "their close/confirmation availability."
        ),
    ]
    notes.text(
        0.018,
        0.94,
        "\n".join(lines),
        transform=notes.transAxes,
        va="top",
        fontsize=9.7,
        linespacing=1.45,
    )
    filename = (
        f"{number:02d}_{row['source_group'].lower()}_"
        f"{row['symbol'].replace('#', '')}_{entry_index}_"
        f"{direction.lower()}_steve_v2.png"
    )
    path = CHART_DIR / filename
    figure.savefig(path, dpi=145, bbox_inches="tight")
    plt.close(figure)
    return filename


def _html(rows: list[Dict[str, Any]]) -> None:
    cards = []
    for number, row in enumerate(rows, start=1):
        tags = "".join(
            f"<span>{tag}</span>" for tag in row["classifications"]
        )
        cards.append(
            f"""
            <article>
              <div class="head">
                <h2>{number:02d} · {row['symbol']} · {row['direction']}</h2>
                <p>{row['time_utc']} · {row['session']} · {row['source_group']}</p>
                <div class="tags">{tags}</div>
              </div>
              <img src="charts/{row['chart_file']}" alt="Management chart {number}">
              <dl>
                <dt>Entry trigger / close</dt><dd>{row['trigger_level']:.2f} / {row['entry_price']:.2f}</dd>
                <dt>Setup logical boundary</dt><dd>{row['logical_boundary']:.2f}</dd>
                <dt>Emergency broker stop</dt><dd>{row['emergency_broker_stop']:.2f}</dd>
                <dt>Trail candidates / proven / moved</dt>
                <dd>{row['trail_candidate_count']} / {row['proven_trail_count']} / {row['trail_movement_count']}</dd>
                <dt>Exit / re-entry</dt><dd>{row['exit_reason'] or 'None'} / {row['reentry_state']}</dd>
              </dl>
              <label>Your review
                <select data-key="{number}">
                  <option value=""></option><option>ACCEPT</option>
                  <option>REJECT</option><option>UNCERTAIN</option>
                </select>
              </label>
              <label>Reason<textarea data-reason="{number}"></textarea></label>
            </article>
            """
        )
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Phase 9 Steve Management Review</title>
<style>
body{{margin:0;background:#e8eef5;color:#152235;font:15px Arial,sans-serif}}
header{{padding:28px 5vw;background:#10253f;color:white;position:sticky;top:0;z-index:3}}
header h1{{margin:0 0 8px}} main{{width:min(1500px,94vw);margin:28px auto}}
article{{background:white;margin:0 0 32px;border-radius:14px;box-shadow:0 8px 28px #2343;padding:20px}}
.head h2{{margin:0}} .head p{{color:#53657a}} img{{width:100%;border:1px solid #cad5e1;border-radius:8px}}
.tags span{{display:inline-block;background:#e0edff;color:#143e76;padding:5px 9px;border-radius:99px;margin:0 7px 7px 0;font-size:12px;font-weight:bold}}
dl{{display:grid;grid-template-columns:240px 1fr;gap:7px 14px;background:#f2f6fa;padding:14px}}dt{{font-weight:bold}}
label{{display:block;margin-top:12px;font-weight:bold}}select,textarea{{display:block;width:100%;margin-top:5px;padding:9px;box-sizing:border-box}}textarea{{height:72px}}
button{{margin-top:12px;padding:9px 14px;border:0;border-radius:7px;background:#38bdf8;color:#082f49;font-weight:bold;cursor:pointer}}
</style></head>
<body><header><h1>Phase 9 · Steve stop and management evidence</h1>
<div>20 real closed-data entries · first 10 preserved · next 10 independently selected · no orders</div>
<button id="export">Export my review CSV</button></header>
<main>{''.join(cards)}</main>
<script>
const key='phase9-steve-management-review-v1';
const state=JSON.parse(localStorage.getItem(key)||'{{}}');
document.querySelectorAll('select[data-key]').forEach(el=>{{
  const id=el.dataset.key; el.value=(state[id]||{{}}).verdict||'';
  el.addEventListener('change',()=>save(id));
}});
document.querySelectorAll('textarea[data-reason]').forEach(el=>{{
  const id=el.dataset.reason; el.value=(state[id]||{{}}).reason||'';
  el.addEventListener('input',()=>save(id));
}});
function save(id){{
  const verdict=document.querySelector(`select[data-key="${{id}}"]`).value;
  const reason=document.querySelector(`textarea[data-reason="${{id}}"]`).value;
  state[id]={{verdict,reason}}; localStorage.setItem(key,JSON.stringify(state));
}}
document.getElementById('export').onclick=()=>{{
  const rows=['review_number,verdict,reason'];
  for(let i=1;i<=20;i++){{
    const s=state[String(i)]||{{}};
    const q=v=>`"${{String(v||'').replaceAll('"','""')}}"`;
    rows.push([i,q(s.verdict),q(s.reason)].join(','));
  }}
  const blob=new Blob([rows.join('\\n')],{{type:'text/csv'}});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='phase9_steve_manual_review.csv'; a.click();
}};
</script></body></html>"""
    (OUTPUT_DIR / "phase9_management_review.html").write_text(
        html, encoding="utf-8"
    )


def run() -> Dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    data_by_symbol = {
        symbol: pd.read_csv(path)
        for symbol, path in SOURCES.items()
    }
    maps = {
        symbol: _candidate_map(data, symbol)
        for symbol, data in data_by_symbol.items()
    }
    htf = {
        symbol: {
            timeframe: resample_closed_m5(data, timeframe=timeframe)
            for timeframe in ("H1", "M30", "M15")
        }
        for symbol, data in data_by_symbol.items()
    }
    swings_by_symbol = {
        symbol: confirmed_swings(
            data,
            as_of_index=len(data) - 1,
            sensitivity=3,
        )
        for symbol, data in data_by_symbol.items()
    }
    old = json.loads(OLD_MANIFEST.read_text(encoding="utf-8"))
    rows: list[Dict[str, Any]] = []
    replay_records: Dict[tuple[str, int], Dict[str, Any]] = {}
    used: set[tuple[str, int]] = set()

    for old_item in old["entries"]:
        symbol = old_item["symbol"]
        index = int(old_item["entry_index"])
        key = (str(old_item["direction"]), index)
        candidate = maps[symbol].get(key)
        if candidate is None:
            raise RuntimeError(f"Accepted entry missing from replay: {symbol} {key}")
        replay = _replay(
            data=data_by_symbol[symbol],
            symbol=symbol,
            candidate=candidate,
            htf_frames=htf[symbol],
            all_swings=swings_by_symbol[symbol],
        )
        if not replay["eligible"]:
            raise RuntimeError(
                f"Accepted entry no longer canonical: {symbol} {index} "
                f"{replay['reason']}"
            )
        rows.append(
            _row(
                symbol=symbol,
                data=data_by_symbol[symbol],
                candidate=candidate,
                replay=replay,
                source_group="PRESERVED_10",
            )
        )
        replay_records[(symbol, index)] = replay
        used.add((symbol, index))

    pool: list[tuple[Dict[str, Any], Dict[str, Any]]] = []
    for symbol, candidate_map in maps.items():
        data = data_by_symbol[symbol]
        for candidate in candidate_map.values():
            index = int(candidate["entry_index"])
            if (symbol, index) in used:
                continue
            if _session(float(data.iloc[index]["time"])) == (
                "OUTSIDE_CONFIGURED_REVIEW_WINDOW"
            ):
                continue
            replay = _replay(
                data=data,
                symbol=symbol,
                candidate=candidate,
                htf_frames=htf[symbol],
                all_swings=swings_by_symbol[symbol],
                canonical_validate=False,
            )
            if not replay["eligible"]:
                continue
            row = _row(
                symbol=symbol,
                data=data,
                candidate=candidate,
                replay=replay,
                source_group="NEW_10",
            )
            pool.append((row, replay))

    targets = [
        ("BULLISH_M5_SUCCESSFUL_HL_TRAIL", "GOLD#"),
        ("BULLISH_M5_SUCCESSFUL_HL_TRAIL", "US100Cash#"),
        ("BEARISH_M5_SUCCESSFUL_LH_TRAIL", "GER40Cash#"),
        ("BEARISH_M5_SUCCESSFUL_LH_TRAIL", "US100Cash#"),
        ("RAW_SWING_REJECTED_UNPROVEN", "GER40Cash#"),
        ("RAW_SWING_REJECTED_UNPROVEN", "GOLD#"),
        ("OPPOSING_BOS_MANAGEMENT_EXIT", "US100Cash#"),
        ("LOGICAL_BODY_CLOSE_AFTER_WICK_SURVIVAL", "GER40Cash#"),
        ("VALID_ONE_TIME_REENTRY", "GOLD#"),
        (
            "REENTRY_REJECTED_DOMINANT_PROTECTION_FAILED",
            "US100Cash#",
        ),
    ]
    selected_new: list[tuple[Dict[str, Any], Dict[str, Any]]] = []
    selected_keys: set[tuple[str, int]] = set()
    unavailable: list[str] = []
    for target, preferred_symbol in targets:
        match = next(
            (
                item
                for item in pool
                if target in item[0]["classifications"]
                and item[0]["symbol"] == preferred_symbol
                and (item[0]["symbol"], item[0]["entry_index"])
                not in selected_keys
            ),
            None,
        )
        if match is None:
            match = next(
                (
                    item
                    for item in pool
                    if target in item[0]["classifications"]
                    and (item[0]["symbol"], item[0]["entry_index"])
                    not in selected_keys
                ),
                None,
            )
        if match is None:
            unavailable.append(target)
            continue
        selected_new.append(match)
        selected_keys.add((match[0]["symbol"], match[0]["entry_index"]))
    if len(selected_new) < 10:
        for item in pool:
            key = (item[0]["symbol"], item[0]["entry_index"])
            if key in selected_keys:
                continue
            selected_new.append(item)
            selected_keys.add(key)
            if len(selected_new) == 10:
                break
    for preliminary_row, _ in selected_new:
        symbol = preliminary_row["symbol"]
        index = preliminary_row["entry_index"]
        direction = preliminary_row["direction"]
        candidate = maps[symbol][(direction, index)]
        replay = _replay(
            data=data_by_symbol[symbol],
            symbol=symbol,
            candidate=candidate,
            htf_frames=htf[symbol],
            all_swings=swings_by_symbol[symbol],
            canonical_validate=True,
        )
        if not replay["eligible"]:
            raise RuntimeError(
                f"Selected new evidence failed canonical replay: "
                f"{symbol} {index} {replay['reason']}"
            )
        row = _row(
            symbol=symbol,
            data=data_by_symbol[symbol],
            candidate=candidate,
            replay=replay,
            source_group="NEW_10",
        )
        rows.append(row)
        replay_records[(symbol, index)] = replay

    for number, row in enumerate(rows, start=1):
        replay = replay_records[(row["symbol"], row["entry_index"])]
        row["review_number"] = number
        row["chart_file"] = _render_chart(
            number=number,
            row=row,
            data=data_by_symbol[row["symbol"]],
            replay=replay,
        )
    csv_rows = []
    for row in rows:
        clean = dict(row)
        clean["classifications"] = "|".join(row["classifications"])
        csv_rows.append(clean)
    with (OUTPUT_DIR / "phase9_management_review.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    report = {
        "model": "STEVE_STOP_MANAGEMENT_V2",
        "session_config": SESSION_CONFIG,
        "preserved_entry_count": 10,
        "new_real_example_count": len(selected_new),
        "total_chart_count": len(rows),
        "requested_categories_unavailable": unavailable,
        "pool_eligible_count": len(pool),
        "all_initial_stops_causal": all(
            row["causal_valid"] for row in rows
        ),
        "order_api_calls": 0,
        "rows": rows,
    }
    (OUTPUT_DIR / "phase9_management_audit.json").write_text(
        json.dumps(report, indent=2, default=_json_default),
        encoding="utf-8",
    )
    _html(rows)
    return report


if __name__ == "__main__":
    result = run()
    print(
        json.dumps(
            {
                "total_chart_count": result["total_chart_count"],
                "new_real_example_count": result[
                    "new_real_example_count"
                ],
                "pool_eligible_count": result["pool_eligible_count"],
                "requested_categories_unavailable": result[
                    "requested_categories_unavailable"
                ],
                "order_api_calls": result["order_api_calls"],
            },
            indent=2,
        )
    )
