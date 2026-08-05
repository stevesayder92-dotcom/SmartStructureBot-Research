from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from core.pipeline_runner import PipelineOptions, run_pipeline
from core.setup_lifecycle import PipelineRuntimeState


def evaluate_m1_fallback(
    *,
    m5_snapshot: Dict[str, Any],
    m1_data: pd.DataFrame,
    symbol: str,
    m1_as_of_index: int,
    higher_timeframe_context: Dict[str, Any],
    runtime_state: Optional[PipelineRuntimeState] = None,
    sensitivity: int = 3,
) -> Dict[str, Any]:
    """
    Evaluate M1 only while a qualified M5 pullback awaits its clean BOS.

    This is a research coordinator, not an independent strategy. The M1
    candidate still runs through the same canonical Director pipeline and
    must belong temporally to the active M5 pullback.
    """
    m5_retracement = m5_snapshot.get("retracement") or {}
    m5_entry = m5_snapshot.get("entry") or {}
    direction = str(
        (m5_snapshot.get("context") or {}).get(
            "approved_direction",
            (m5_snapshot.get("market") or {}).get("trend", "NEUTRAL"),
        )
    ).upper()
    gate_open = bool(
        m5_retracement.get("qualified")
        and not m5_entry.get("ready")
        and direction in {"BULLISH", "BEARISH"}
    )
    base = {
        "availability": "AVAILABLE",
        "available": True,
        "owner": "M1FallbackCoordinator",
        "source_timeframe": "M1",
        "parent_timeframe": "M5",
        "as_of_index": int(m1_as_of_index),
        "causal_valid": True,
        "research_only": True,
        "order_api_called": False,
    }
    if not gate_open:
        return {
            **base,
            "state": "M1_FALLBACK_GATE_CLOSED",
            "entry_ready": False,
            "entry": {},
            "reasons": [
                "M1 is inspected only when a qualified active M5 "
                "pullback has no current clean M5 entry"
            ],
        }
    if runtime_state is None:
        runtime_state = PipelineRuntimeState()
    result = run_pipeline(
        data=m1_data,
        symbol=symbol,
        timeframe="M1",
        as_of_index=int(m1_as_of_index),
        options=PipelineOptions(
            strategy_model="EXPERT_SPEC_V1",
            engine_sensitivity=int(sensitivity),
        ),
        runtime_state=runtime_state,
        higher_timeframe_context=higher_timeframe_context,
    )
    snapshot = result.snapshot
    entry = snapshot["entry"]
    m5_origin = m5_retracement.get("origin_swing") or {}
    m1_origin = snapshot["retracement"].get("origin_swing") or {}
    m5_origin_time = m5_origin.get("time")
    m1_origin_time = m1_origin.get("time")
    belongs_to_parent = bool(
        m5_origin_time is None
        or m1_origin_time is None
        or float(m1_origin_time) >= float(m5_origin_time)
    )
    ready = bool(entry.get("ready") and belongs_to_parent)
    if ready:
        state = "M1_FALLBACK_ENTRY_VALIDATED"
        reasons = [
            "The active qualified M5 pullback had no current M5 entry",
            "The current closed M1 candle completed a canonical "
            "same-direction failed-retracement BOS",
            "Initial logical invalidation uses "
            "M1_RELEVANT_SWING_BODY_EDGE",
        ]
    elif entry.get("ready"):
        state = "M1_ENTRY_REJECTED_OUTSIDE_PARENT_M5_PULLBACK"
        reasons = [
            "The M1 setup began before the active M5 pullback and cannot "
            "be borrowed as a fallback trigger"
        ]
    else:
        state = "M1_FALLBACK_WAITING_FOR_CLEAN_BOS"
        reasons = list(entry.get("reason", []))
    return {
        **base,
        "state": state,
        "entry_ready": ready,
        "entry": entry if ready else {**entry, "ready": False},
        "m5_setup_id": (m5_snapshot.get("setup") or {}).get("setup_id"),
        "m5_pullback_origin_time": m5_origin_time,
        "m1_pullback_origin_time": m1_origin_time,
        "belongs_to_parent_m5_pullback": belongs_to_parent,
        "logical_stop_source": (
            "M1_RELEVANT_SWING_BODY_EDGE"
            if ready
            else None
        ),
        "reasons": reasons,
        "snapshot": snapshot,
    }
