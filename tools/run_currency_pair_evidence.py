from __future__ import annotations

import csv
import html
import json
from pathlib import Path
import sys
from typing import Any, Dict

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.run_phase10_full_contract_evidence as visual
from core.expert_strategy import confirmed_swings, scan_expert_m5_candidates


OUT = ROOT / "currency_pair_evidence"
CHARTS = OUT / "charts"
SOURCES = {
    "EURUSD#": ROOT / "research_data_fx" / "EURUSD_M5_closed.csv",
    "GBPUSD#": ROOT / "research_data_fx" / "GBPUSD_M5_closed.csv",
    "USDJPY#": ROOT / "research_data_fx" / "USDJPY_M5_closed.csv",
    "AUDUSD#": ROOT / "research_data_fx" / "AUDUSD_M5_closed.csv",
}
MAX_ROWS = 5000
EXAMPLE_COUNT = 20


def _write_html(rows: list[Dict[str, Any]]) -> None:
    cards = []
    for number, row in enumerate(rows, 1):
        cards.append(
            f"""<article>
<h2>{number:02d} - {html.escape(row['symbol'])} - {html.escape(row['direction'])}</h2>
<p>{html.escape(row['time_utc'])} - {html.escape(row['session'])} -
grade {row['setup_grade']} - Fib {row['fibonacci_zone']}</p>
<img src="charts/{html.escape(row['chart_file'])}"
alt="Causal currency-pair chart {number}">
<label>Steve verdict
<select><option></option><option>ACCEPT</option><option>REJECT</option>
<option>UNCERTAIN</option></select></label>
<label>Reason<textarea></textarea></label>
</article>"""
        )
    document = f"""<!doctype html><html><head><meta charset="utf-8">
<title>SmartStructureBot Currency Pair Review</title><style>
body{{margin:0;background:#e8eef5;color:#152235;font:15px Arial,sans-serif}}
header{{padding:24px 4vw;background:#112a46;color:white;position:sticky;top:0;z-index:2}}
main{{width:min(1600px,96vw);margin:24px auto}}
article{{background:white;padding:18px;margin:0 0 28px;border-radius:12px}}
img{{width:100%;border:1px solid #a8b5c5}}
label{{display:block;margin-top:10px;font-weight:bold}}
select,textarea{{display:block;width:100%;box-sizing:border-box;padding:8px;margin-top:4px}}
textarea{{height:64px}}</style></head><body>
<header><h1>20 new currency-pair causal examples</h1>
<div>Real MT5 closed M5 data - Phase 10.1 strategy - research only - no orders</div>
</header><main>{''.join(cards)}</main></body></html>"""
    (OUT / "currency_pair_review.html").write_text(
        document,
        encoding="utf-8",
    )


def _select_balanced(pool: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    groups: Dict[tuple[str, str], list[Dict[str, Any]]] = {}
    for row in pool:
        groups.setdefault(
            (row["symbol"], row["direction"]),
            [],
        ).append(row)
    for rows in groups.values():
        rows.sort(key=lambda row: row["time_utc"])

    selected: list[Dict[str, Any]] = []
    used: set[tuple[str, int]] = set()
    keys = sorted(groups)
    while len(selected) < EXAMPLE_COUNT:
        progressed = False
        for key in keys:
            rows = groups[key]
            while rows:
                row = rows.pop(0)
                identity = (row["symbol"], int(row["entry_index"]))
                if identity in used:
                    continue
                selected.append(row)
                used.add(identity)
                progressed = True
                break
            if len(selected) >= EXAMPLE_COUNT:
                break
        if not progressed:
            break
    return sorted(
        selected,
        key=lambda row: (row["time_utc"], row["symbol"]),
    )


def run() -> Dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    CHARTS.mkdir(parents=True, exist_ok=True)
    visual.OUT = OUT
    visual.CHARTS = CHARTS

    pool: list[Dict[str, Any]] = []
    source_audit: list[Dict[str, Any]] = []
    data_by_symbol: Dict[str, pd.DataFrame] = {}
    for symbol, path in SOURCES.items():
        if not path.exists():
            source_audit.append(
                {"symbol": symbol, "available": False, "reason": "missing file"}
            )
            continue
        full = pd.read_csv(path)
        data = full.iloc[-MAX_ROWS:].copy().reset_index(drop=True)
        data_by_symbol[symbol] = data
        duplicate_count = int(data["time"].duplicated().sum())
        monotonic = bool(data["time"].is_monotonic_increasing)
        frames = visual._frames(data)
        swings = confirmed_swings(
            data,
            as_of_index=len(data) - 1,
            sensitivity=3,
        )
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
            if visual._session(
                float(data.iloc[int(item["entry_index"])]["time"])
            )
            != "OUTSIDE_PRIMARY_SESSION"
        ]
        sampled: list[Dict[str, Any]] = []
        for direction in ("BULLISH", "BEARISH"):
            directional = [
                item for item in candidates
                if item["direction"] == direction
            ]
            if directional:
                step = max(1, len(directional) // 14)
                sampled.extend(directional[::step][:14])
        accepted = 0
        for candidate in sampled:
            row = visual._evaluate(
                symbol=symbol,
                data=data,
                candidate=candidate,
                frames=frames,
                swings=swings,
            )
            if row is None:
                continue
            row["assigned_category"] = "CURRENCY_PAIR_CAUSAL_ENTRY"
            pool.append(row)
            accepted += 1
        source_audit.append(
            {
                "symbol": symbol,
                "available": True,
                "closed_rows_used": len(data),
                "first_time_utc": pd.to_datetime(
                    float(data.iloc[0]["time"]), unit="s", utc=True
                ).isoformat(),
                "last_time_utc": pd.to_datetime(
                    float(data.iloc[-1]["time"]), unit="s", utc=True
                ).isoformat(),
                "monotonic": monotonic,
                "duplicate_count": duplicate_count,
                "candidates": len(candidates),
                "sampled": len(sampled),
                "accepted": accepted,
            }
        )

    selected = _select_balanced(pool)
    if len(selected) < EXAMPLE_COUNT:
        raise RuntimeError(
            f"Only {len(selected)} causal FX examples were available"
        )
    for number, row in enumerate(selected, 1):
        row["review_number"] = number
        row["chart_file"] = visual._chart(
            number,
            row,
            data_by_symbol[row["symbol"]],
        )

    clean_rows = [visual._clean(row) for row in selected]
    csv_rows = []
    for row in clean_rows:
        exported = dict(row)
        for key, value in list(exported.items()):
            if isinstance(value, (list, dict)):
                exported[key] = json.dumps(value, default=visual._default)
        csv_rows.append(exported)
    with (OUT / "currency_pair_audit.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)

    unique_keys = {
        (row["symbol"], int(row["entry_index"]))
        for row in selected
    }
    report = {
        "strategy_model": "EXPERT_SPEC_V1",
        "management_model": "STEVE_STOP_MANAGEMENT_V3",
        "requested_examples": EXAMPLE_COUNT,
        "generated_examples": len(selected),
        "unique_entry_keys": len(unique_keys),
        "symbols": sorted({row["symbol"] for row in selected}),
        "direction_counts": {
            direction: sum(
                row["direction"] == direction for row in selected
            )
            for direction in ("BULLISH", "BEARISH")
        },
        "all_causal": all(row["causal_valid"] for row in selected),
        "future_data_used_at_entry": any(
            row["future_data_used_at_entry"] for row in selected
        ),
        "order_api_calls": 0,
        "source_audit": source_audit,
        "rows": clean_rows,
    }
    (OUT / "currency_pair_audit.json").write_text(
        json.dumps(report, indent=2, default=visual._default),
        encoding="utf-8",
    )
    _write_html(selected)
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "generated_examples",
                    "unique_entry_keys",
                    "symbols",
                    "direction_counts",
                    "all_causal",
                    "future_data_used_at_entry",
                    "order_api_calls",
                )
            },
            indent=2,
        )
    )
    return report


if __name__ == "__main__":
    run()
