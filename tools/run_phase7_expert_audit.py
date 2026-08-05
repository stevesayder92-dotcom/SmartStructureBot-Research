from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.expert_strategy import (  # noqa: E402
    EXPERT_HTF_TIMEFRAMES,
    build_expert_htf_context,
)
from core.pipeline_runner import PipelineOptions, run_pipeline  # noqa: E402
from core.replay_runner import _integrity_failures  # noqa: E402
from core.signal_ledger import SignalLedger  # noqa: E402


def resample_closed_m5(
    data: pd.DataFrame,
    *,
    timeframe: str,
) -> pd.DataFrame:
    minutes = {"M15": 15, "M30": 30, "H1": 60}[timeframe]
    expected = minutes // 5
    source = data.copy()
    source["_utc"] = pd.to_datetime(
        source["time"].astype(float),
        unit="s",
        utc=True,
    )
    source["_bucket"] = source["_utc"].dt.floor(f"{minutes}min")
    grouped = source.groupby("_bucket", sort=True)
    rows: list[Dict[str, Any]] = []
    for bucket, frame in grouped:
        if len(frame) != expected:
            continue
        ordered = frame.sort_values("time")
        rows.append(
            {
                "time": float(bucket.timestamp()),
                "open": float(ordered.iloc[0]["open"]),
                "high": float(ordered["high"].astype(float).max()),
                "low": float(ordered["low"].astype(float).min()),
                "close": float(ordered.iloc[-1]["close"]),
                "tick_volume": float(
                    ordered.get(
                        "tick_volume",
                        pd.Series([0] * len(ordered)),
                    ).astype(float).sum()
                ),
            }
        )
    return pd.DataFrame(rows)


def run_audit(
    *,
    source_path: Path,
    symbol: str,
    start_index: int,
    end_index: int | None,
    output_dir: Path,
) -> Dict[str, Any]:
    data = pd.read_csv(source_path)
    final = len(data) - 1 if end_index is None else min(
        int(end_index), len(data) - 1
    )
    start = max(int(start_index), 0)
    if start > final:
        raise ValueError("start_index is after end_index")

    htf_frames = {
        timeframe: resample_closed_m5(data, timeframe=timeframe)
        for timeframe in EXPERT_HTF_TIMEFRAMES
    }
    ledger = SignalLedger()
    integrity_failures: list[Dict[str, Any]] = []
    entries: list[Dict[str, Any]] = []
    context_counts = {
        "BULLISH": 0,
        "BEARISH": 0,
        "NEUTRAL": 0,
    }
    active_count = 0
    wick_only_count = 0

    for index in range(start, final + 1):
        context = build_expert_htf_context(
            decision_candle_open_time=data.iloc[index]["time"],
            decision_timeframe_seconds=300,
            frame_data=htf_frames,
            sensitivity=3,
        )
        direction = str(context["approved_direction"])
        context_counts[direction] += 1
        result = run_pipeline(
            data=data,
            symbol=symbol,
            timeframe="M5",
            as_of_index=index,
            options=PipelineOptions(
                strategy_model="EXPERT_SPEC_V1",
                engine_sensitivity=3,
            ),
            higher_timeframe_context=context,
        )
        failures = _integrity_failures(result)
        if failures:
            integrity_failures.append(
                {"as_of_index": index, "failures": failures}
            )
        snapshot = result.snapshot
        event = ledger.record_snapshot(
            snapshot=snapshot,
            candle=data.iloc[index].to_dict(),
        )
        if snapshot["retracement"].get("qualified"):
            active_count += 1
        if snapshot["retracement"].get("wick_only_trigger_sweep"):
            wick_only_count += 1
        if snapshot["entry"].get("ready"):
            epoch = float(data.iloc[index].get("time"))
            readable_utc = pd.to_datetime(
                epoch,
                unit="s",
                utc=True,
            ).isoformat()
            row = {
                "symbol": symbol,
                "timeframe": "M5",
                "setup_id": snapshot["entry"].get("setup_id"),
                "entry_index": index,
                "time": data.iloc[index].get("time"),
                "time_utc": (
                    data.iloc[index].get("time_utc")
                    if pd.notna(data.iloc[index].get("time_utc"))
                    else readable_utc
                ),
                "time_broker": data.iloc[index].get("time_broker"),
                "direction": snapshot["entry"].get("direction"),
                "entry_price": snapshot["entry"].get("price"),
                "stop_loss": snapshot["entry"].get("stop_loss"),
                "trigger_index": snapshot["entry"].get("trigger_index"),
                "trigger_level": snapshot["entry"].get("trigger_level"),
                "pullback_start": snapshot["retracement"].get(
                    "initial_pullback_start"
                ),
                "qualification_index": snapshot["retracement"].get(
                    "first_qualification_index"
                ),
                "qualification_available_at_index": snapshot[
                    "retracement"
                ].get("qualification_available_at_index"),
                "htf_votes": json.dumps(context.get("votes", {})),
                "ledger_event_created": bool(event is not None),
                "causal": snapshot["entry"].get("causal"),
                "close_only": snapshot["entry"].get("close_only"),
                "entry_matches_close": (
                    float(snapshot["entry"]["price"])
                    == float(data.iloc[index]["close"])
                ),
                "order_api_called": snapshot["execution"].get(
                    "order_api_called"
                ),
                "manual_review": "",
                "review_reason": "",
            }
            entries.append(row)

    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(entries).to_csv(
        output_dir / "phase7_expert_entries.csv",
        index=False,
    )
    summary = {
        "strategy_model": "EXPERT_SPEC_V1",
        "engine_sensitivity": 3,
        "source": str(source_path),
        "symbol": symbol,
        "rows_in_source": len(data),
        "start_index": start,
        "end_index": final,
        "candles_audited": final - start + 1,
        "htf_rows": {
            key: len(value) for key, value in htf_frames.items()
        },
        "context_counts": context_counts,
        "qualified_retracement_candles": active_count,
        "wick_only_no_entry_candles": wick_only_count,
        "canonical_entries": len(entries),
        "ledger_entry_signals": len(ledger.entry_events()),
        "integrity_failure_count": len(integrity_failures),
        "integrity_failures": integrity_failures,
        "all_entries_current_close_only": all(
            bool(row["causal"])
            and bool(row["close_only"])
            and bool(row["entry_matches_close"])
            for row in entries
        ),
        "order_api_calls": sum(
            1 for row in entries if row["order_api_called"]
        ),
    }
    (output_dir / "phase7_expert_audit.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("--symbol", default="GER40Cash#")
    parser.add_argument("--start-index", type=int, default=100)
    parser.add_argument("--end-index", type=int)
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "phase7_evidence"),
    )
    arguments = parser.parse_args()
    summary = run_audit(
        source_path=Path(arguments.source).resolve(),
        symbol=arguments.symbol,
        start_index=arguments.start_index,
        end_index=arguments.end_index,
        output_dir=Path(arguments.output_dir).resolve(),
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
