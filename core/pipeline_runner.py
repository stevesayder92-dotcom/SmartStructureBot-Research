from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd

from core.market_structure import MarketStructureDetector
from core.structure_hierarchy import StructureHierarchyEngine
from core.structure_strength import StructureStrengthEngine
from core.bos_detector import BOSDetector
from core.market_state import MarketStateEngine
from core.bos_importance import BOSImportanceEngine
from core.phase_engine import PhaseEngine
from core.master_structure_state import MasterStructureState
from core.market_control_engine import MarketControlEngine
from core.transition_engine import TransitionEngine
from core.protected_structure import ProtectedStructureEngine
from core.structure_validator import StructureValidator
from core.qualified_retracement import (
    QualifiedRetracementEngine,
    QualifiedRetracementPolicy,
)
from core.continuation_engine import ContinuationEngine
from core.entry_validator import EntryValidator
from core.htf_context import (
    attach_local_alignment,
    compare_htf_advisory_policies,
)
from core.entry_freshness import EntryFreshnessEngine
from core.setup_lifecycle import PipelineRuntimeState

from core.system_director import (
    DataContractError,
    SystemStateDirector,
)


@dataclass
class PipelineOptions:
    """
    Controls optional side effects.

    Candle replay must run silently and must not:
    - open charts on every candle;
    - write hundreds of memory files;
    - simulate future trade outcomes;
    - print the full health report repeatedly.
    """

    enable_debug: bool = False
    enable_health_report: bool = False
    enable_visualizer: bool = False
    enable_trade_memory: bool = False
    enable_trade_lifecycle: bool = False
    # Retained for backward-compatible construction only. Phase 4 always
    # enforces retracement chronology; False can no longer bypass it.
    enforce_retracement_origin: bool = True
    retracement_qualification_model: str = "HYBRID"
    # Research comparison switch only. Phase 5B does not declare a
    # production winner and never uses this field as a live-order gate.
    decision_protection_policy: str = "ORIGIN_DEFENDING_SWING"
    # The accepted Phase 6 model remains available for controlled
    # comparison. Application execution selects EXPERT_SPEC_V1 through
    # RuntimeConfig; legacy unit contracts can still name LEGACY_PHASE6.
    strategy_model: str = "LEGACY_PHASE6"
    engine_sensitivity: int = 3
    fibonacci_minimum_depth: float = 0.236
    fibonacci_primary_minimum: float = 0.382
    fibonacci_primary_maximum: float = 0.618
    fibonacci_deep_maximum: float = 0.786


def _build_retracement_origin_contract(
    *,
    origin_trend_bos_index: Optional[int],
    initial_pullback_start: Optional[int],
    current_pullback_end: Optional[int],
    as_of_index: int,
) -> Dict[str, Any]:
    """
    Validate the causal chronology required by Steve's strategy.

    The trend-confirming BOS is the origin of the continuation cycle.
    Therefore it must be known no later than the first candle assigned
    to that pullback.  A broad compression that began before the BOS is
    useful descriptive context, but it is not a valid pullback origin
    for an executable continuation setup.
    """

    origin = (
        int(origin_trend_bos_index)
        if origin_trend_bos_index is not None
        else None
    )
    start = (
        int(initial_pullback_start)
        if initial_pullback_start is not None
        else None
    )
    end = (
        int(current_pullback_end)
        if current_pullback_end is not None
        else None
    )
    current = int(as_of_index)
    reasons: list[str] = []

    if origin is None:
        reasons.append(
            "No causal trend-confirming BOS owns the pullback"
        )
    if start is None:
        reasons.append(
            "No initial pullback start is available"
        )
    if end is None:
        reasons.append(
            "No current pullback boundary is available"
        )
    if (
        origin is not None
        and start is not None
        and origin > start
    ):
        reasons.append(
            "The reported pullback begins before its "
            "trend-confirming origin BOS"
        )
    if (
        start is not None
        and end is not None
        and start > end
    ):
        reasons.append(
            "The current pullback boundary precedes its start"
        )
    if end is not None and end > current:
        reasons.append(
            "The current pullback boundary is in the future"
        )

    coherent = not reasons
    if coherent:
        reasons.append(
            "Chronology satisfies origin BOS <= pullback start "
            "<= current boundary <= decision candle"
        )

    return {
        "availability": (
            "AVAILABLE" if coherent else "UNAVAILABLE"
        ),
        "state": (
            "CHRONOLOGY_COHERENT"
            if coherent
            else "CHRONOLOGY_INCOHERENT"
        ),
        "owner": "RetracementOriginAudit",
        "as_of_index": current,
        # The audit itself is causal even when the chronology fails.
        # chronology_valid expresses strategy coherence; causal_valid
        # expresses absence of future-data leakage.
        "causal_valid": True,
        "chronology_valid": coherent,
        "origin_trend_bos": origin,
        "initial_pullback_start": start,
        "current_pullback_end": end,
        "entry_index": current,
        "required_order": (
            "origin_trend_bos <= initial_pullback_start "
            "<= current_pullback_end <= entry_index"
        ),
        "reasons": reasons,
    }


@dataclass
class PipelineResult:
    """
    Result of analysing exactly one decision candle.
    """

    symbol: str
    timeframe: Any
    requested_as_of_index: int
    visible_rows: int
    snapshot: Dict[str, Any]
    diagnostics: Dict[str, Any]


def _validate_pipeline_inputs(
    data: pd.DataFrame,
    symbol: str,
    as_of_index: int,
) -> None:
    if not isinstance(data, pd.DataFrame):
        raise TypeError(
            "run_pipeline data must be a pandas DataFrame"
        )

    if data.empty:
        raise ValueError(
            "run_pipeline cannot analyse an empty DataFrame"
        )

    required_columns = {
        "open",
        "high",
        "low",
        "close",
    }

    missing_columns = required_columns.difference(data.columns)

    if missing_columns:
        raise ValueError(
            "Market data is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError(
            "run_pipeline requires a non-empty symbol"
        )

    if not isinstance(as_of_index, int):
        raise TypeError(
            "as_of_index must be an integer"
        )

    if as_of_index < 0:
        raise IndexError(
            "as_of_index cannot be negative"
        )

    if as_of_index >= len(data):
        raise IndexError(
            f"as_of_index {as_of_index} is outside "
            f"the available data range 0..{len(data) - 1}"
        )


def _build_causal_input(
    data: pd.DataFrame,
    as_of_index: int,
) -> pd.DataFrame:
    """
    Build the only DataFrame that engines may receive.

    Example:
        as_of_index = 340

    Engines receive:
        candles 0..340

    Engines cannot see:
        candles 341 onward
    """

    causal_data = (
        data.iloc[: as_of_index + 1]
        .copy()
        .reset_index(drop=True)
    )

    return causal_data


def _resolve_final_trend(
    atr_wave_state: Dict[str, Any],
    major_market_state: Dict[str, Any],
    phase_state: Dict[str, Any],
) -> tuple[str, str]:
    """
    Preserve the final-trend rules currently used by main.py.
    """

    wave_trend = atr_wave_state.get(
        "trend",
        "UNKNOWN",
    )
    wave_phase = atr_wave_state.get(
        "phase",
        "UNKNOWN",
    )
    major_trend = major_market_state.get(
        "trend",
        "UNKNOWN",
    )
    transition = phase_state.get(
        "transition",
        "NONE",
    )

    if transition == "BULLISH_TO_BEARISH_CONFIRMED":
        return "BEARISH", "BEARISH_EXPANSION"

    if transition == "BEARISH_TO_BULLISH_CONFIRMED":
        return "BULLISH", "BULLISH_EXPANSION"

    if wave_phase == "BEARISH_EXPANSION":
        return "BEARISH", "BEARISH_EXPANSION"

    if wave_phase == "BULLISH_EXPANSION":
        return "BULLISH", "BULLISH_EXPANSION"

    if (
        wave_trend == major_trend
        and wave_trend in {"BULLISH", "BEARISH"}
    ):
        return (
            wave_trend,
            atr_wave_state.get(
                "phase",
                f"{wave_trend}_EXPANSION",
            ),
        )

    if (
        wave_trend == "RANGING"
        and major_trend in {"BULLISH", "BEARISH"}
    ):
        return (
            major_trend,
            f"{major_trend}_COMPRESSION",
        )

    return "RANGING", "CONSOLIDATION"

def _to_float(
    value: Any,
    field_name: str,
) -> float:
    """
    Safely normalize a Pandas scalar or Python numeric value.

    The explicit Any boundary also prevents Pandas' broad Scalar
    type annotation from creating false Pylance warnings.
    """

    try:
        return float(value)

    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(
            f"{field_name} must be numeric, "
            f"received {value!r}"
        ) from error


def _build_canonical_entry(
    *,
    trend: str,
    as_of_index: int,
    current_close: float,
    continuation_state: Dict[str, Any],
    entry_validation: Dict[str, Any],
    setup_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Assemble the single Director-owned entry contract.

    ContinuationEngine owns the structural candidate and EntryValidator
    owns executable-candle approval. This function only maps their
    results; it does not recompute either decision.
    """

    candidate = (
        continuation_state.get("continuation_bos")
        or {}
    )
    candidate_present = bool(
        continuation_state.get("entry_ready", False)
        and candidate
    )
    validation_allowed = bool(
        entry_validation.get("allowed", False)
    )
    candidate_index = candidate.get("index")
    candidate_is_current = (
        candidate_index == as_of_index
    )
    causal = bool(
        continuation_state.get("causal_valid", False)
        and entry_validation.get("causal_valid", False)
        and candidate.get("causal_valid", True)
    )
    current_candle_only = bool(
        continuation_state.get(
            "current_candle_only",
            False,
        )
        and entry_validation.get(
            "current_candle_only",
            False,
        )
        and candidate.get(
            "current_candle_only",
            True,
        )
    )
    approved = bool(
        candidate_present
        and validation_allowed
        and candidate_is_current
        and causal
        and current_candle_only
    )

    failure_trigger = (
        continuation_state.get("failure_trigger")
        or {}
    )
    trigger_index = candidate.get(
        "broken_structure_index",
        failure_trigger.get("index"),
    )
    trigger_level = candidate.get(
        "broken_structure_price",
        failure_trigger.get("level"),
    )

    if approved:
        state = "ENTRY_VALIDATED"
        reason = list(
            entry_validation.get("reason", [])
        )
    elif candidate_present:
        state = str(
            entry_validation.get(
                "state",
                "BLOCKED_ENTRY_VALIDATION",
            )
        )
        reason = list(
            entry_validation.get("reason", [])
        )
    else:
        state = str(
            continuation_state.get(
                "state",
                "NO_ENTRY_CANDIDATE",
            )
        )
        reason = list(
            continuation_state.get("reason", [])
        )

    if candidate_present and not candidate_is_current:
        state = "BLOCKED_STALE_ENTRY"
        approved = False
        causal = False
        reason.append(
            "Entry candidate index does not equal the current "
            "decision candle"
        )

    return {
        "available": approved,
        "ready": approved,
        "state": state,
        "setup_id": setup_id,
        "direction": (
            trend
            if trend in {"BULLISH", "BEARISH"}
            else None
        ),
        "index": as_of_index if approved else None,
        "price": current_close if approved else None,
        "type": candidate.get("type"),
        "quality": candidate.get("entry_quality"),
        "score": candidate.get(
            "entry_confidence_score"
        ),
        "trigger_index": trigger_index,
        "trigger_level": trigger_level,
        "validation": dict(entry_validation),
        "causal": causal,
        "current_candle_only": current_candle_only,
        "reason": reason,
        "as_of_index": as_of_index,
        "candidate_index": candidate_index,
        "setup_invalidation_type": candidate.get(
            "setup_invalidation_type"
        ),
        "setup_invalidation_index": candidate.get(
            "setup_invalidation_index"
        ),
        "setup_invalidation_level": candidate.get(
            "setup_invalidation_level"
        ),
        "setup_invalidation_intact": candidate.get(
            "setup_invalidation_intact_at_entry"
        ),
    }


def _reason_list(*values: Any) -> list[str]:
    reasons: list[str] = []

    for value in values:
        if isinstance(value, str) and value.strip():
            reasons.append(value.strip())
        elif isinstance(value, (list, tuple)):
            reasons.extend(
                str(item)
                for item in value
                if str(item).strip()
            )

    return reasons


def _build_protection_contract(
    *,
    raw: Dict[str, Any],
    setup_id: Optional[str],
    as_of_index: int,
) -> Dict[str, Any]:
    selected = (
        raw.get("protected_low")
        or raw.get("protected_high")
        or {}
    )
    level = raw.get("protection_level")
    index = selected.get("index")
    protection_type = (
        selected.get("type")
        or selected.get("raw_type")
    )
    available = bool(
        level is not None
        and index is not None
    )
    broken = bool(
        raw.get("protection_broken", False)
    )

    if not available:
        state = str(
            raw.get(
                "state",
                "WAITING_FOR_VALID_DECISION_PROTECTION",
            )
        )
    elif broken:
        state = "PROTECTION_BROKEN"
    else:
        state = "PROTECTION_AVAILABLE_INTACT"

    return {
        **raw,
        "availability": available,
        "available": available,
        "state": state,
        "owner": raw.get(
            "owner",
            "ProtectedStructureEngine",
        ),
        "setup_id": setup_id,
        "as_of_index": int(as_of_index),
        "causal_valid": bool(
            raw.get("causal_valid", False)
        ),
        "relevant_structure_index": index,
        "relevant_structure_level": level,
        "type": (
            protection_type
            if available
            else "NOT_AVAILABLE"
        ),
        "index": index,
        "level": level,
        "intact": (
            not broken
            if available
            else None
        ),
        "reasons": _reason_list(
            raw.get("reason"),
            raw.get("selected_reason"),
        ),
    }


def _build_transition_contract(
    *,
    raw: Dict[str, Any],
    setup_id: Optional[str],
    as_of_index: int,
) -> Dict[str, Any]:
    state = str(
        raw.get("state")
        or "TRANSITION_UNAVAILABLE"
    )
    relevant = (
        raw.get("recovery_bos")
        or raw.get("step_three")
        or raw.get("opposite_bos")
        or {}
    )
    available = state not in {
        "TRANSITION_UNKNOWN",
        "TRANSITION_UNAVAILABLE",
    }

    return {
        **raw,
        "availability": available,
        "available": available,
        "state": state,
        "owner": "TransitionEngine",
        "setup_id": setup_id,
        "as_of_index": int(as_of_index),
        "causal_valid": bool(
            raw.get("causal_valid", False)
        ),
        "relevant_structure_index": (
            relevant.get("index")
        ),
        "relevant_structure_level": (
            relevant.get(
                "break_price",
                relevant.get("level"),
            )
        ),
        "active": bool(
            raw.get("transition_active", False)
        ),
        "recovered": bool(
            raw.get(
                "transition_recovered",
                False,
            )
        ),
        "reasons": _reason_list(
            raw.get("reasons"),
            raw.get("reason"),
        ),
    }


def _build_validation_contract(
    *,
    raw: Dict[str, Any],
    setup_id: Optional[str],
    as_of_index: int,
    protection: Dict[str, Any],
    transition: Dict[str, Any],
) -> Dict[str, Any]:
    verdict = raw.get("verdict")
    available = verdict is not None
    relevant_index = (
        protection.get(
            "relevant_structure_index"
        )
        if protection.get("available")
        else transition.get(
            "relevant_structure_index"
        )
    )
    relevant_level = (
        protection.get(
            "relevant_structure_level"
        )
        if protection.get("available")
        else transition.get(
            "relevant_structure_level"
        )
    )

    return {
        **raw,
        "availability": available,
        "available": available,
        "state": (
            str(verdict)
            if available
            else "VALIDATION_UNAVAILABLE"
        ),
        "owner": "StructureValidator",
        "setup_id": setup_id,
        "as_of_index": int(as_of_index),
        "causal_valid": bool(
            raw.get("causal_valid", True)
        ),
        "relevant_structure_index": (
            relevant_index
        ),
        "relevant_structure_level": (
            relevant_level
        ),
        "reasons": _reason_list(
            raw.get("reasons"),
            raw.get("warnings"),
            raw.get("hard_failures"),
            raw.get("hard_block_reason"),
        ),
    }


def run_pipeline(
    *,
    data: pd.DataFrame,
    symbol: str,
    timeframe: Any,
    as_of_index: int,
    options: Optional[PipelineOptions] = None,
    runtime_state: Optional[
        PipelineRuntimeState
    ] = None,
    higher_timeframe_context: Optional[
        Dict[str, Any]
    ] = None,
) -> PipelineResult:
    """
    Analyse one candle causally.

    This function will eventually contain the verified engine chain from
    main.py. During replay, it will be called once for every candle.

    No engine inside this function may receive the full future DataFrame.
    """

    if options is None:
        options = PipelineOptions()

    if runtime_state is None:
        runtime_state = PipelineRuntimeState()

    _validate_pipeline_inputs(
        data=data,
        symbol=symbol,
        as_of_index=as_of_index,
    )

    strategy_model = str(
        options.strategy_model or "LEGACY_PHASE6"
    ).upper()
    if strategy_model == "EXPERT_SPEC_V1":
        from core.expert_strategy import run_expert_strategy
        from core.fibonacci_contract import FibonacciConfig

        expert = run_expert_strategy(
            data=data,
            symbol=symbol,
            timeframe=timeframe,
            as_of_index=as_of_index,
            higher_timeframe_context=higher_timeframe_context,
            sensitivity=int(options.engine_sensitivity),
            runtime_state=runtime_state,
            fibonacci_config=FibonacciConfig(
                minimum_relevant_depth=float(
                    options.fibonacci_minimum_depth
                ),
                primary_minimum=float(
                    options.fibonacci_primary_minimum
                ),
                primary_maximum=float(
                    options.fibonacci_primary_maximum
                ),
                deep_maximum=float(
                    options.fibonacci_deep_maximum
                ),
            ),
        )
        return PipelineResult(
            symbol=symbol,
            timeframe=timeframe,
            requested_as_of_index=as_of_index,
            visible_rows=as_of_index + 1,
            snapshot=expert.snapshot,
            diagnostics=expert.diagnostics,
        )
    if strategy_model != "LEGACY_PHASE6":
        raise ValueError(
            f"Unsupported strategy_model {options.strategy_model!r}"
        )

    causal_data = _build_causal_input(
        data=data,
        as_of_index=as_of_index,
    )

    # Because causal_data was truncated and reset, its final row is the
    # decision candle inside this isolated pipeline run.
    local_as_of_index = len(causal_data) - 1

    director = SystemStateDirector(
        symbol=symbol,
        timeframe=timeframe,
        data=causal_data,
        as_of_index=local_as_of_index,
    )

    future_access_test_passed = False
    future_access_message = "NOT_RUN"

    try:
        director.market_view.row(
            director.as_of_index + 1
        )

        future_access_message = (
            "FAILED: Director allowed future access"
        )

    except (DataContractError, IndexError) as error:
        future_access_test_passed = True
        future_access_message = str(error)

    # =========================================================
    # STRUCTURE DETECTION
    # =========================================================

    structure_detector = MarketStructureDetector(
        causal_data
    )

    major_highs, major_lows = (
        structure_detector.detect_swings(
            min_swing_distance=3,
            min_price_distance=1.5,
        )
    )

    (
        major_classified_highs,
        major_classified_lows,
    ) = structure_detector.classify_structure(
        major_highs,
        major_lows,
    )

    atr_highs, atr_lows = (
        structure_detector.detect_atr_wave_structure(
            atr_period=14,
            atr_multiplier=1.2,
        )
    )

    (
        atr_classified_highs,
        atr_classified_lows,
    ) = structure_detector.classify_structure(
        atr_highs,
        atr_lows,
    )

    hierarchy_engine = StructureHierarchyEngine(
        causal_data,
        as_of_index=local_as_of_index,
    )

    (
        atr_classified_highs,
        atr_classified_lows,
        atr_structure_points,
    ) = hierarchy_engine.build_hierarchy(
        atr_classified_highs,
        atr_classified_lows,
    )

    flow_highs, flow_lows = (
        structure_detector.detect_flow_points()
    )

    (
        flow_classified_highs,
        flow_classified_lows,
    ) = structure_detector.classify_structure(
        flow_highs,
        flow_lows,
    )

    # =========================================================
    # STRUCTURE STRENGTH
    # =========================================================

    strength_engine = StructureStrengthEngine(
        causal_data
    )

    scored_atr_highs = (
        strength_engine.score_structure_points(
            atr_classified_highs
        )
    )

    scored_atr_lows = (
        strength_engine.score_structure_points(
            atr_classified_lows
        )
    )

    scored_structure_points = (
        scored_atr_highs
        + scored_atr_lows
    )

    # =========================================================
    # BOS DETECTION
    # =========================================================

    bos_detector = BOSDetector(causal_data)

    atr_bos_events = bos_detector.detect_bos(
        atr_classified_highs,
        atr_classified_lows,
    )

    trade_eligible_bos = (
        bos_detector.get_trade_eligible_bos(
            atr_bos_events
        )
    )

    # =========================================================
    # MARKET STATE
    # =========================================================

    state_engine = MarketStateEngine()

    (
        compressed_highs,
        compressed_lows,
    ) = state_engine.compress_structure_points(
        atr_classified_highs,
        atr_classified_lows,
        min_index_gap=4,
    )

    atr_wave_state = (
        state_engine.analyze_structure_state(
            compressed_highs,
            compressed_lows,
            len(causal_data),
        )
    )

    major_market_state = (
        state_engine.analyze_structure_state(
            major_classified_highs,
            major_classified_lows,
            len(causal_data),
        )
    )

    # =========================================================
    # BOS IMPORTANCE
    # =========================================================

    bos_importance_engine = BOSImportanceEngine(
        causal_data
    )

    scored_bos = (
        bos_importance_engine.score_bos_events(
            trade_eligible_bos,
            atr_wave_state,
        )
    )

    tradable_bos = (
        bos_importance_engine.get_tradable_bos(
            scored_bos
        )
    )

    # =========================================================
    # PHASE AND FINAL TREND
    # =========================================================

    phase_engine = PhaseEngine()

    phase_state = phase_engine.determine_phase(
        atr_wave_state,
        atr_bos_events,
    )

    (
        final_trend_context,
        final_phase_context,
    ) = _resolve_final_trend(
        atr_wave_state,
        major_market_state,
        phase_state,
    )

    atr_wave_state["final_trend_context"] = (
        final_trend_context
    )
    atr_wave_state["trend"] = (
        final_trend_context
    )
    atr_wave_state["phase"] = (
        final_phase_context
    )
    
    # =========================================================
    # MASTER STRUCTURE STATE
    # =========================================================

    master_state_engine = MasterStructureState(
        causal_data
    )

    master_state = master_state_engine.build(
        atr_classified_highs,
        atr_classified_lows,
        atr_bos_events,
        atr_wave_state,
    )

    # Reinforce the final resolved context so every downstream
    # engine reads the same trend and phase.
    master_state["final_trend_context"] = (
        final_trend_context
    )
    master_state["trend"] = (
        final_trend_context
    )
    master_state["phase"] = (
        final_phase_context
    )
    master_state["as_of_index"] = (
        local_as_of_index
    )
    master_state["causal_valid"] = True
    # Phase 4 retires the broad-compression heuristic as an owner.
    # It remains inside MasterStructureState only as descriptive legacy
    # evidence and may not seed an executable setup.
    master_state["legacy_active_retracement"] = (
        master_state.get("active_retracement")
    )
    master_state["active_retracement"] = None

    # =========================================================
    # MARKET CONTROL
    # =========================================================

    market_control_engine = MarketControlEngine(
        as_of_index=local_as_of_index
    )

    market_control = market_control_engine.analyze(
        trend=final_trend_context,
        master_state=master_state,
        bos_events=atr_bos_events,
        lookback_points=18,
    )

    master_state["market_control"] = (
        market_control
    )

    # =========================================================
    # TRANSITION ENGINE
    # =========================================================

    transition_engine = TransitionEngine(
        as_of_index=local_as_of_index
    )

    transition_state = transition_engine.analyze(
        trend=final_trend_context,
        structure_points=master_state.get(
            "structure_points",
            [],
        ),
        bos_events=atr_bos_events,
        lookback=60,
    )

    master_state["transition_state"] = (
        transition_state
    )

    # =========================================================
    # DECISION PROTECTION
    # =========================================================

    protected_engine = ProtectedStructureEngine(
        as_of_index=local_as_of_index
    )

    protected_structure = (
        protected_engine.find_protected_structure(
            atr_classified_highs,
            atr_classified_lows,
            master_state,
            tradable_bos,
            anchor_bos=None,
        )
    )

    # =========================================================
    # STRUCTURE VALIDATOR
    # =========================================================

    structure_validator = StructureValidator()

    structure_validation = (
        structure_validator.validate(
            trend=final_trend_context,
            master_state=master_state,
            protected_structure=protected_structure,
        )
    )

    master_state["structure_validation"] = (
        structure_validation
    )

    # =========================================================
    # QUALIFIED RETRACEMENT GENESIS
    # One engine owns origin BOS, candidate break, qualification,
    # protection, failure trigger, and post-origin chronology.
    # =========================================================

    qualified_engine = QualifiedRetracementEngine(
        causal_data,
        as_of_index=local_as_of_index,
        policy=QualifiedRetracementPolicy(
            model=options.retracement_qualification_model,
        ),
        symbol=symbol,
        timeframe=str(timeframe),
        protection_policy=options.decision_protection_policy,
    )
    retracement_state = qualified_engine.analyze(
        trend=final_trend_context,
        structure_points=master_state.get(
            "structure_points",
            [],
        ),
        bos_events=atr_bos_events,
        protected_structure=protected_structure,
    )

    setup_start = retracement_state.get(
        "qualified_retracement_start_index"
    )
    setup_end = retracement_state.get(
        "current_pullback_end"
    )
    origin_trend_bos = (
        retracement_state.get("setup_origin_bos")
        or {}
    )
    origin_trend_bos_index = (
        origin_trend_bos.get("index")
    )
    pullback_points = [
        point
        for point in master_state.get(
            "structure_points",
            [],
        )
        if setup_start is not None
        and int(point.get("index", -1))
        >= int(setup_start)
        and int(
            point.get(
                "confirmed_at_index",
                point.get("index", -1),
            )
        )
        <= local_as_of_index
    ]
    latest_retracement_lifecycle = {
        **retracement_state,
        "trend": final_trend_context,
        "retracement_direction": (
            "BEARISH_PULLBACK"
            if final_trend_context == "BULLISH"
            else "BULLISH_PULLBACK"
            if final_trend_context == "BEARISH"
            else None
        ),
        "start_index": setup_start,
        "end_index": setup_end,
        "status": retracement_state.get("state"),
        "setup_active": bool(
            retracement_state.get("qualified")
        ),
        "quality": (
            retracement_state.get("significance")
            or {}
        ).get("classification"),
        "counter_structure_count": len(
            retracement_state.get(
                "counter_structure_points",
                [],
            )
        ),
        "pullback_structure_points": pullback_points,
        "current_candle_only": True,
        "causal_valid": bool(
            retracement_state.get("causal_valid", False)
        ),
    }
    managed_retracements = (
        [latest_retracement_lifecycle]
        if origin_trend_bos_index is not None
        else []
    )
    retracement_zones = managed_retracements
    master_state["active_retracement"] = (
        {
            "trend": final_trend_context,
            "retracement_direction": (
                latest_retracement_lifecycle.get(
                    "retracement_direction"
                )
            ),
            "start_index": setup_start,
            "end_index": setup_end,
            "counter_structure_count": (
                latest_retracement_lifecycle.get(
                    "counter_structure_count",
                    0,
                )
            ),
            "quality": (
                latest_retracement_lifecycle.get("quality")
            ),
            "qualified": True,
        }
        if retracement_state.get("qualified")
        else None
    )

    qualified_protection = (
        retracement_state.get(
            "decision_protected_swing"
        )
        or {}
    )
    if qualified_protection.get("available"):
        raw_point = {
            "type": qualified_protection.get("type"),
            "side": qualified_protection.get("side"),
            "index": qualified_protection.get("index"),
            "body_price": qualified_protection.get("level"),
            "confirmed_at_index": (
                qualified_protection.get(
                    "confirmed_at_index"
                )
            ),
            "tradeable_at_index": (
                qualified_protection.get(
                    "confirmed_at_index"
                )
            ),
            "is_tradeable_structure": True,
            "decision_weight": 10,
        }
        protected_structure = {
            "trend_context": final_trend_context,
            "protection_role": "DECISION_PROTECTION",
            "role": "DECISION_PROTECTION",
            "owner": "DecisionProtectionSelector",
            "cycle_id": qualified_protection.get("cycle_id"),
            "origin_bos_index": qualified_protection.get(
                "origin_bos_index"
            ),
            "selection_policy": qualified_protection.get(
                "selection_policy"
            ),
            "policy_activation": qualified_protection.get(
                "policy_activation"
            ),
            "relationship_to_origin_bos": qualified_protection.get(
                "relationship_to_origin_bos"
            ),
            "caused_or_defended_bos": qualified_protection.get(
                "caused_or_defended_bos"
            ),
            "confirming_bos_index": qualified_protection.get(
                "confirming_bos_index"
            ),
            "replacement_eligible": qualified_protection.get(
                "replacement_eligible",
                False,
            ),
            "selection_score": qualified_protection.get(
                "selection_score",
                0,
            ),
            "all_candidates": list(
                qualified_protection.get("all_candidates", [])
            ),
            "protected_high": (
                raw_point
                if final_trend_context == "BEARISH"
                else None
            ),
            "protected_low": (
                raw_point
                if final_trend_context == "BULLISH"
                else None
            ),
            "last_trend_bos": origin_trend_bos,
            "anchor_bos_used": origin_trend_bos,
            "anchor_source": "QUALIFIED_SETUP_ORIGIN_BOS",
            "as_of_index": local_as_of_index,
            "protection_available_at_index": (
                qualified_protection.get(
                    "confirmed_at_index"
                )
            ),
            "protection_score": 100,
            "protection_grade": "A",
            "confidence": "HIGH",
            "protection_confidence": "HIGH",
            "candidate_count": int(
                qualified_protection.get("candidate_count", 1)
            ),
            "protection_broken": not bool(
                retracement_state.get(
                    "protected_swing_intact",
                    True,
                )
            ),
            "protection_broken_at_index": (
                retracement_state.get(
                    "protected_swing_invalidated_at"
                )
            ),
            "protection_level": (
                qualified_protection.get("level")
            ),
            "causal_valid": True,
            "fallback_used": False,
            "selected_reason": list(
                qualified_protection.get("reason", [])
            ),
            "reason": list(
                qualified_protection.get("reason", [])
            ),
        }
        structure_validation = (
            structure_validator.validate(
                trend=final_trend_context,
                master_state=master_state,
                protected_structure=protected_structure,
            )
        )
        master_state["structure_validation"] = (
            structure_validation
        )
    elif retracement_state.get("impulse_cycle"):
        protected_structure = {
            "trend_context": final_trend_context,
            "protection_role": "DECISION_PROTECTION",
            "role": "DECISION_PROTECTION",
            "owner": "DecisionProtectionSelector",
            "cycle_id": (
                retracement_state["impulse_cycle"].get("cycle_id")
            ),
            "origin_bos_index": (
                retracement_state["impulse_cycle"].get(
                    "origin_bos_index"
                )
            ),
            "selection_policy": qualified_protection.get(
                "selection_policy",
                "ORIGIN_DEFENDING_SWING",
            ),
            "policy_activation": (
                "RESEARCH_COMPARISON_NOT_PERMANENT"
            ),
            "protected_high": None,
            "protected_low": None,
            "last_trend_bos": origin_trend_bos,
            "anchor_bos_used": origin_trend_bos,
            "anchor_source": "QUALIFIED_SETUP_ORIGIN_BOS",
            "as_of_index": local_as_of_index,
            "protection_available_at_index": None,
            "protection_score": 0,
            "protection_grade": "D",
            "confidence": "VERY_LOW",
            "protection_confidence": "VERY_LOW",
            "candidate_count": int(
                qualified_protection.get("candidate_count", 0)
            ),
            "all_candidates": list(
                qualified_protection.get("all_candidates", [])
            ),
            "protection_broken": False,
            "protection_broken_at_index": None,
            "protection_level": None,
            "causal_valid": bool(
                qualified_protection.get("causal_valid", True)
            ),
            "fallback_used": False,
            "state": "WAITING_FOR_VALID_DECISION_PROTECTION",
            "selected_reason": [],
            "reason": list(
                qualified_protection.get(
                    "reason",
                    ["WAITING_FOR_VALID_DECISION_PROTECTION"],
                )
            ),
        }
        structure_validation = (
            structure_validator.validate(
                trend=final_trend_context,
                master_state=master_state,
                protected_structure=protected_structure,
            )
        )
        master_state["structure_validation"] = structure_validation

    setup_contract: Dict[str, Any] = {}
    retracement_origin_audit = (
        _build_retracement_origin_contract(
            origin_trend_bos_index=(
                origin_trend_bos_index
            ),
            initial_pullback_start=setup_start,
            current_pullback_end=setup_end,
            as_of_index=local_as_of_index,
        )
    )

    if (
        final_trend_context
        in {"BULLISH", "BEARISH"}
        and retracement_state.get("qualified")
        and setup_start is not None
        and setup_end is not None
        and retracement_origin_audit[
            "chronology_valid"
        ]
    ):
        setup_contract = (
            runtime_state.setup_registry.observe(
                symbol=symbol,
                timeframe=timeframe,
                direction=final_trend_context,
                origin_trend_bos_index=(
                    origin_trend_bos_index
                ),
                initial_pullback_start=int(
                    setup_start
                ),
                current_pullback_end=int(
                    setup_end
                ),
                as_of_index=local_as_of_index,
                descriptive_status=str(
                    latest_retracement_lifecycle.get(
                        "status",
                        "DEVELOPING",
                    )
                ),
                retracement_direction=(
                    latest_retracement_lifecycle.get(
                        "retracement_direction"
                    )
                ),
                quality=(
                    latest_retracement_lifecycle.get(
                        "quality"
                    )
                ),
                causal=bool(
                    latest_retracement_lifecycle.get(
                        "causal_valid",
                        False,
                    )
                ),
            )
        )
        setup_contract["origin_audit"] = (
            retracement_origin_audit
        )
    elif (
        final_trend_context
        in {"BULLISH", "BEARISH"}
        and setup_start is not None
        and setup_end is not None
        and not retracement_origin_audit[
            "chronology_valid"
        ]
    ):
        setup_contract = {
            "available": False,
            "state": "INVALID_SETUP_CHRONOLOGY",
            "status": "INVALIDATED",
            "owner": "RetracementOriginAudit",
            "setup_id": None,
            "direction": final_trend_context,
            "trend": final_trend_context,
            "origin_trend_bos": (
                origin_trend_bos_index
            ),
            "initial_pullback_start": int(
                setup_start
            ),
            "current_pullback_end": int(
                setup_end
            ),
            "as_of_index": local_as_of_index,
            "causal": True,
            "reason": list(
                retracement_origin_audit[
                    "reasons"
                ]
            ),
            "history": [
                {
                    "event": (
                        "SETUP_REJECTED_INCOHERENT_ORIGIN"
                    ),
                    "as_of_index": (
                        local_as_of_index
                    ),
                    "status": "INVALIDATED",
                }
            ],
            "origin_audit": (
                retracement_origin_audit
            ),
        }

    # =========================================================
    # SETUP INVALIDATION
    # Separate from broad decision protection.
    # =========================================================

    setup_invalidation = (
        protected_engine.find_setup_invalidation_structure(
            data=causal_data,
            market_state=master_state,
            retracement_lifecycle=(
                latest_retracement_lifecycle
            ),
            structure_points=master_state.get(
                "structure_points",
                [],
            ),
        )
    )

    # =========================================================
    # CURRENT-CANDLE CONTINUATION ENTRY
    # =========================================================

    continuation_engine = ContinuationEngine(
        causal_data,
        as_of_index=local_as_of_index,
    )

    continuation_state = (
        continuation_engine.analyze(
            master_state=master_state,
            structure_points=master_state.get(
                "structure_points",
                [],
            ),
            bos_events=atr_bos_events,
            protected_structure=(
                protected_structure
            ),
            setup_invalidation=(
                setup_invalidation
            ),
            retracement_lifecycle=(
                latest_retracement_lifecycle
            ),
            structure_validation=(
                structure_validation
            ),
        )
    )

    # =========================================================
    # CURRENT-CANDLE ENTRY VALIDATION
    # ContinuationEngine owns structural BOS detection.
    # EntryValidator owns executable candle validation.
    # =========================================================

    entry_validator = EntryValidator(
        causal_data,
        as_of_index=local_as_of_index,
    )

    entry_validation = entry_validator.validate(
        trend=final_trend_context,
        continuation_state=continuation_state,
    )

    continuation_state["entry_validation"] = (
        entry_validation
    )

    # =========================================================
    # FINAL CAUSAL ENTRY BOS
    # Only a current, causal, validated entry may pass.
    # =========================================================

    final_entry_bos = []

    if (
        continuation_state.get(
            "entry_ready",
            False,
        )
        and continuation_state.get(
            "continuation_bos"
        )
        and entry_validation.get(
            "allowed",
            False,
        )
    ):
        candidate_entry = (
            continuation_state[
                "continuation_bos"
            ]
        )

        candidate_index = (
            candidate_entry.get("index")
        )

        if candidate_index == local_as_of_index:
            candidate_entry = candidate_entry.copy()
            candidate_entry["entry_validation"] = (
                entry_validation
            )
            final_entry_bos = [
                candidate_entry
            ]
        else:
            continuation_state[
                "stale_fallback_used"
            ] = True

    current_close = _to_float(
        causal_data.iloc[-1]["close"],
        field_name="Current candle close",
    )

    setup_id = setup_contract.get("setup_id")
    setup_was_consumed = bool(
        setup_id
        and runtime_state.setup_registry.is_consumed(
            setup_id
        )
    )
    setup_invalidation["cycle_id"] = (
        (retracement_state.get("impulse_cycle") or {}).get("cycle_id")
    )
    setup_invalidation["owner"] = "ProtectedStructureEngine"
    setup_invalidation["protection_role"] = "SETUP_INVALIDATION"
    setup_invalidation["state"] = (
        "SETUP_INVALIDATION_BROKEN"
        if setup_invalidation.get("broken")
        else "SETUP_INVALIDATION_AVAILABLE"
        if setup_invalidation.get("index") is not None
        else "WAITING_FOR_SETUP_INVALIDATION"
    )
    setup_invalidation["available"] = bool(
        setup_invalidation.get("index") is not None
        and setup_invalidation.get("price") is not None
    )

    if (
        setup_id
        and continuation_state.get(
            "entry_ready",
            False,
        )
    ):
        setup_contract = (
            runtime_state.setup_registry.mark_candidate_ready(
                setup_id,
                local_as_of_index,
            )
        )

    canonical_entry = _build_canonical_entry(
        trend=final_trend_context,
        as_of_index=local_as_of_index,
        current_close=current_close,
        continuation_state=continuation_state,
        entry_validation=entry_validation,
        setup_id=setup_id,
    )
    canonical_entry.update(
        {
            "first_candidate_index": (
                retracement_state.get(
                    "first_candidate_index"
                )
            ),
            "first_qualification_index": (
                retracement_state.get(
                    "first_qualification_index"
                )
            ),
            "qualification_available_at_index": (
                retracement_state.get(
                    "qualification_available_at_index"
                )
            ),
            "initial_failure_trigger_index": (
                retracement_state.get(
                    "initial_failure_trigger_index"
                )
            ),
            "active_failure_trigger_index": (
                retracement_state.get(
                    "active_failure_trigger_index"
                )
            ),
            "active_failure_trigger_level": (
                retracement_state.get(
                    "active_failure_trigger_level"
                )
            ),
            "trigger_updated_at_index": (
                retracement_state.get(
                    "trigger_updated_at_index"
                )
            ),
            "trigger_update_count": (
                retracement_state.get(
                    "trigger_update_count",
                    0,
                )
            ),
            "significance_score": (
                (
                    retracement_state.get(
                        "significance"
                    )
                    or {}
                ).get("significance_score")
            ),
            "raw_significance_score": (
                (
                    retracement_state.get(
                        "significance"
                    )
                    or {}
                ).get("raw_significance_score")
            ),
        }
    )

    if (
        setup_was_consumed
        and continuation_state.get(
            "entry_ready",
            False,
        )
    ):
        canonical_entry.update(
            {
                "available": False,
                "ready": False,
                "state": "BLOCKED_SETUP_CONSUMED",
                "index": None,
                "price": None,
            }
        )
        canonical_entry["reason"].append(
            "The setup already emitted its first canonical entry"
        )

    elif (
        canonical_entry["ready"]
        and not retracement_origin_audit[
            "chronology_valid"
        ]
    ):
        canonical_entry.update(
            {
                "available": False,
                "ready": False,
                "state": (
                    "BLOCKED_INCOHERENT_SETUP_CHRONOLOGY"
                ),
                "index": None,
                "price": None,
            }
        )
        canonical_entry["reason"].extend(
            retracement_origin_audit["reasons"]
        )

    elif canonical_entry["ready"] and setup_id is None:
        canonical_entry.update(
            {
                "available": False,
                "ready": False,
                "state": "BLOCKED_MISSING_SETUP_ID",
                "index": None,
                "price": None,
            }
        )
        canonical_entry["reason"].append(
            "Validator-approved entry has no authoritative setup ID"
        )

    elif canonical_entry["ready"] and setup_id:
        setup_contract = (
            runtime_state.setup_registry.consume(
                setup_id,
                local_as_of_index,
            )
        )

    elif (
        setup_id
        and canonical_entry["state"]
        in {
            "BLOCKED_SETUP_INVALIDATION_BROKEN",
            "BLOCKED_STRUCTURE_INVALID",
        }
    ):
        setup_contract = (
            runtime_state.setup_registry.invalidate(
                setup_id,
                local_as_of_index,
                canonical_entry["state"],
            )
        )

    canonical_entry["entry_index"] = (
        canonical_entry.get("index")
    )

    if not canonical_entry["ready"]:
        final_entry_bos = []
    elif final_entry_bos:
        final_entry_bos[-1]["setup_id"] = setup_id

    freshness_contract = EntryFreshnessEngine(
        causal_data,
        timeframe=str(timeframe),
    ).assess(
        retracement=retracement_state,
        entry_index=canonical_entry.get("index"),
    )
    canonical_entry["freshness_classification"] = (
        freshness_contract.get("classification")
    )
    canonical_entry["freshness_advisory_only"] = True

    if canonical_entry["ready"]:
        retracement_state["state"] = "CONSUMED"
        retracement_state["consumed_at_index"] = (
            local_as_of_index
        )
        latest_retracement_lifecycle["state"] = (
            "CONSUMED"
        )
        latest_retracement_lifecycle["status"] = (
            "CONSUMED"
        )
    elif entry_validation.get("allowed"):
        retracement_state["state"] = "ENTRY_VALIDATED"
        latest_retracement_lifecycle["state"] = (
            "ENTRY_VALIDATED"
        )

    context_contract = attach_local_alignment(
        higher_timeframe_context
        or {
            "available": False,
            "state": "HTF_CONTEXT_NOT_SUPPLIED",
            "approved_direction": None,
            "policy": None,
            "frames": {},
            "votes": {
                "BULLISH": 0,
                "BEARISH": 0,
            },
            "causal": True,
            "incomplete_htf_candles_used": False,
            "reason": [
                "No higher-timeframe context was "
                "supplied to this pipeline call"
            ],
        },
        (
            canonical_entry.get("direction")
            or final_trend_context
        ),
    )
    context_contract["advisory_comparison"] = (
        compare_htf_advisory_policies(
            context_contract,
            (
                canonical_entry.get("direction")
                or final_trend_context
            ),
        )
    )
    context_contract["advisory_only"] = True
    context_contract["hard_block_applied"] = False
    canonical_entry["htf_context_state"] = (
        context_contract.get("state")
    )
    canonical_entry["htf_direction"] = (
        context_contract.get(
            "approved_direction"
        )
    )
    canonical_entry["htf_alignment"] = (
        context_contract.get(
            "entry_alignment"
        )
    )

    impulse_cycle_contract = dict(
        retracement_state.get("impulse_cycle")
        or {
            "availability": "UNAVAILABLE",
            "available": False,
            "owner": "ImpulseCycleEngine",
            "cycle_id": None,
            "symbol": symbol,
            "timeframe": str(timeframe),
            "direction": final_trend_context,
            "origin_bos_index": None,
            "origin_bos_available_at_index": None,
            "impulse_start_index": None,
            "impulse_extreme_index": None,
            "qualified_retracement_start_index": None,
            "terminal_index": None,
            "status": "CLOSED",
            "state": "CLOSED",
            "as_of_index": local_as_of_index,
            "causal_valid": True,
            "reason": ["No causal impulse cycle is active"],
        }
    )
    if canonical_entry["ready"]:
        impulse_cycle_contract["status"] = "ENTRY_CONSUMED"
        impulse_cycle_contract["state"] = "ENTRY_CONSUMED"
        impulse_cycle_contract["terminal_index"] = local_as_of_index
    elif retracement_state.get("protected_swing_invalidated_at") is not None:
        impulse_cycle_contract["status"] = "INVALIDATED"
        impulse_cycle_contract["state"] = "INVALIDATED"
        impulse_cycle_contract["terminal_index"] = (
            retracement_state.get("protected_swing_invalidated_at")
        )
    retracement_state["impulse_cycle"] = impulse_cycle_contract

    trailing_protection_contract = {
        "availability": "UNAVAILABLE",
        "available": False,
        "state": "NOT_ACTIVE_BEFORE_OPEN_TRADE",
        "owner": "TrailingProtectionEngine",
        "role": "TRAILING_PROTECTION",
        "cycle_id": impulse_cycle_contract.get("cycle_id"),
        "setup_id": setup_id,
        "as_of_index": local_as_of_index,
        "causal_valid": True,
        "relevant_structure_index": None,
        "relevant_structure_level": None,
        "reason": [
            "Trailing protection is a post-entry role and cannot "
            "substitute for decision protection or setup invalidation"
        ],
    }

    if final_entry_bos:
        latest_entry = final_entry_bos[-1]

        master_state["last_trend_bos"] = (
            latest_entry
        )

    master_state["retracement_state"] = (
        retracement_state
    )
    master_state["retracement_zones"] = (
        retracement_zones
    )
    master_state["managed_retracements"] = (
        managed_retracements
    )
    master_state[
        "latest_retracement_lifecycle"
    ] = latest_retracement_lifecycle
    master_state["setup_invalidation"] = (
        setup_invalidation
    )
    master_state["continuation_state"] = (
        continuation_state
    )
    master_state["entry_validation"] = (
        entry_validation
    )
    master_state["final_entry_bos"] = (
        final_entry_bos
    )
    master_state["setup_lifecycle"] = (
        setup_contract
    )

    # =========================================================
    # DIRECTOR STATE WRITES
    # =========================================================

    if setup_id is not None:
        director.set_setup_id(setup_id)

    director.write(
        "retracement",
        retracement_state,
        producer="QualifiedRetracementEngine",
    )

    director.write(
        "setup",
        setup_contract,
        producer="SetupLifecycleRegistry",
    )

    director.write(
        "market",
        {
            "trend": final_trend_context,
            "phase": final_phase_context,
            "atr_wave_state": atr_wave_state,
            "major_market_state": (
                major_market_state
            ),
            "phase_state": phase_state,

            "master_state": master_state,
            "market_control": market_control,
            "transition_state": transition_state,
            "protected_structure": (
                protected_structure
            ),
            "structure_validation": (
                structure_validation
            ),

            "retracement_state": (
                retracement_state
            ),
            "retracement_zones": (
                retracement_zones
            ),
            "managed_retracements": (
                managed_retracements
            ),
            "latest_retracement_lifecycle": (
                latest_retracement_lifecycle
            ),
            "setup_lifecycle": setup_contract,
            "setup_invalidation": (
                setup_invalidation
            ),
            "continuation_state": (
                continuation_state
            ),
            "entry_validation": (
                entry_validation
            ),
            "final_entry_bos": (
                final_entry_bos
            ),

            "current_close": current_close,
            "as_of_index": local_as_of_index,
            "causal_valid": True,
        },
        producer="StructuralDecisionPipeline",
    )

    director.write(
        "structure",
        {
            "phase": final_phase_context,

            "major_highs": major_highs,
            "major_lows": major_lows,
            "major_classified_highs": (
                major_classified_highs
            ),
            "major_classified_lows": (
                major_classified_lows
            ),

            "atr_highs": atr_highs,
            "atr_lows": atr_lows,
            "atr_classified_highs": (
                atr_classified_highs
            ),
            "atr_classified_lows": (
                atr_classified_lows
            ),
            "atr_structure_points": (
                atr_structure_points
            ),

            "flow_highs": flow_highs,
            "flow_lows": flow_lows,
            "flow_classified_highs": (
                flow_classified_highs
            ),
            "flow_classified_lows": (
                flow_classified_lows
            ),

            "scored_atr_highs": (
                scored_atr_highs
            ),
            "scored_atr_lows": (
                scored_atr_lows
            ),

            "atr_bos_events": atr_bos_events,
            "trade_eligible_bos": (
                trade_eligible_bos
            ),
            "scored_bos": scored_bos,
            "tradable_bos": tradable_bos,

            "master_state": master_state,
            "market_control": market_control,
            "transition_state": transition_state,
            "protected_structure": (
                protected_structure
            ),
            "structure_validation": (
                structure_validation
            ),
            "retracement_state": (
                retracement_state
            ),
            "retracement_zones": (
                retracement_zones
            ),
            "managed_retracements": (
                managed_retracements
            ),
            "setup_lifecycle": setup_contract,
            "setup_invalidation": (
                setup_invalidation
            ),
            "continuation_state": (
                continuation_state
            ),
            "entry_validation": (
                entry_validation
            ),
            "final_entry_bos": (
                final_entry_bos
            ),
            "as_of_index": local_as_of_index,
            "causal_valid": True,
        },
        producer="StructurePipeline",
    )

    control_contract = dict(market_control)
    control_contract["setup_id"] = setup_id
    director.write(
        "control",
        control_contract,
        producer="MarketControlEngine",
    )

    director.write(
        "context",
        context_contract,
        producer="HTFContextEngine",
    )

    director.write(
        "impulse_cycle",
        impulse_cycle_contract,
        producer="ImpulseCycleEngine",
    )

    director.write(
        "setup_invalidation",
        setup_invalidation,
        producer="ProtectedStructureEngine",
    )

    director.write(
        "trailing_protection",
        trailing_protection_contract,
        producer="TrailingProtectionEngine",
    )

    director.write(
        "entry_freshness",
        freshness_contract,
        producer="EntryFreshnessEngine",
    )

    transition_contract = (
        _build_transition_contract(
            raw=transition_state,
            setup_id=setup_id,
            as_of_index=local_as_of_index,
        )
    )
    director.write(
        "transition",
        transition_contract,
        producer="TransitionEngine",
    )

    protection_contract = (
        _build_protection_contract(
            raw=protected_structure,
            setup_id=setup_id,
            as_of_index=local_as_of_index,
        )
    )
    validation_contract = (
        _build_validation_contract(
            raw=structure_validation,
            setup_id=setup_id,
            as_of_index=local_as_of_index,
            protection=protection_contract,
            transition=transition_contract,
        )
    )
    director.write(
        "protection",
        protection_contract,
        producer="ProtectedStructureEngine",
    )

    director.write(
        "validation",
        validation_contract,
        producer="StructureValidator",
    )

    director.write(
        "entry",
        canonical_entry,
        producer="ContinuationEngine",
    )

    # =========================================================
    # INTEGRITY COUNTS
    # =========================================================

    all_atr_structures = (
        atr_classified_highs
        + atr_classified_lows
    )

    future_structures_used = [
        point
        for point in all_atr_structures
        if point.get(
            "confirmed_at_index",
            point.get("index", 0),
        ) > local_as_of_index
    ]

    untimed_structures = [
        point
        for point in all_atr_structures
        if point.get(
            "confirmed_at_index"
        ) is None
    ]

    future_strength_used = [
        point
        for point in scored_structure_points
        if point.get(
            "strength_available_at_index",
            point.get("index", 0),
        ) > local_as_of_index
    ]

    future_displacement_used = [
        point
        for point in scored_structure_points
        if point.get(
            "future_displacement_used",
            False,
        )
    ]

    non_causal_bos = [
        event
        for event in atr_bos_events
        if not event.get(
            "causal_valid",
            False,
        )
    ]

    bos_before_confirmation = [
        event
        for event in atr_bos_events
        if event.get(
            "broken_structure_confirmed_at_index",
            event.get(
                "broken_structure_index",
                0,
            ),
        ) > event.get("index", 0)
    ]

    wrong_bos_break_prices = []

    for event in atr_bos_events:
        event_index = event.get("index")
        break_price = event.get("break_price")

        if (
            not isinstance(event_index, int)
            or not 0 <= event_index < len(
                causal_data
            )
            or break_price is None
        ):
            wrong_bos_break_prices.append(
                event
            )
            continue

        actual_close = _to_float(
            causal_data.at[
                event_index,
                "close",
            ],
            field_name="BOS candle close",
        )

        normalized_break_price = _to_float(
            break_price,
            field_name="BOS break price",
        )

        if (
            abs(
                normalized_break_price
                - actual_close
            )
            > 1e-9
        ):
            wrong_bos_break_prices.append(
                event
            )

    # =========================================================
    # STRUCTURAL DECISION INTEGRITY
    # =========================================================

    protection_available_at = (
        protected_structure.get(
            "protection_available_at_index"
        )
    )

    future_protection_used = bool(
        isinstance(
            protection_available_at,
            int,
        )
        and protection_available_at
        > local_as_of_index
    )

    protection_exists = bool(
        protected_structure.get(
            "protected_low"
        )
        or protected_structure.get(
            "protected_high"
        )
    )

    protection_is_causal = (
        protected_structure.get(
            "causal_valid",
            False,
        )
    )

    protection_fallback_used = (
        protected_structure.get(
            "fallback_used",
            False,
        )
    )

    market_control_is_causal = (
        market_control.get(
            "causal_valid",
            False,
        )
    )

    market_control_as_of_matches = (
        market_control.get(
            "as_of_index"
        )
        == local_as_of_index
    )

    transition_is_causal = (
        transition_state.get(
            "causal_valid",
            False,
        )
    )

    transition_as_of_matches = (
        transition_state.get(
            "as_of_index"
        )
        == local_as_of_index
    )

    unresolved_transition = bool(
        transition_state.get(
            "sequence_confirmed",
            False,
        )
        and transition_state.get(
            "transition_active",
            False,
        )
        and not transition_state.get(
            "transition_recovered",
            False,
        )
    )

    unexplained_structure_block = bool(
        structure_validation.get(
            "hard_block",
            False,
        )
        and not structure_validation.get(
            "hard_failures",
            [],
        )
    )

    recovered_transition_blocked = bool(
        transition_state.get(
            "transition_recovered",
            False,
        )
        and structure_validation.get(
            "hard_block",
            False,
        )
        and any(
            "transition" in str(reason).lower()
            for reason in structure_validation.get(
                "hard_failures",
                [],
            )
        )
    )

    # =========================================================
    # SETUP AND ENTRY INTEGRITY
    # =========================================================

    latest_managed_retracement = (
        managed_retracements[-1]
        if managed_retracements
        else {}
    )

    setup_current_only = (
        not latest_managed_retracement
        or latest_managed_retracement.get(
            "current_candle_only",
            False,
        )
    )

    stale_setup_confirmation_used = (
        latest_managed_retracement.get(
            "stale_confirmation_used",
            False,
        )
    )

    setup_lifecycle_causal = (
        not latest_managed_retracement
        or latest_managed_retracement.get(
            "causal_valid",
            False,
        )
    )

    setup_as_of_matches = (
        not latest_managed_retracement
        or latest_managed_retracement.get(
            "as_of_index"
        )
        == local_as_of_index
    )

    setup_invalidation_causal = (
        not retracement_state.get("qualified")
        or setup_invalidation.get(
            "causal_valid",
            False,
        )
    )

    setup_invalidation_available_at = (
        setup_invalidation.get(
            "available_at_index"
        )
    )

    future_setup_invalidation_used = bool(
        isinstance(
            setup_invalidation_available_at,
            int,
        )
        and setup_invalidation_available_at
        > local_as_of_index
    )

    continuation_current_only = (
        continuation_state.get(
            "current_candle_only",
            False,
        )
    )

    continuation_causal = (
        continuation_state.get(
            "causal_valid",
            False,
        )
    )

    continuation_as_of_matches = (
        continuation_state.get(
            "as_of_index"
        )
        == local_as_of_index
    )

    stale_continuation_used = (
        continuation_state.get(
            "stale_fallback_used",
            False,
        )
    )

    continuation_entry_index = (
        continuation_state.get(
            "entry_index"
        )
    )

    continuation_entry_is_current = (
        not continuation_state.get(
            "entry_ready",
            False,
        )
        or continuation_entry_index
        == local_as_of_index
    )

    final_entry = (
        final_entry_bos[-1]
        if final_entry_bos
        else {}
    )

    final_entry_is_current = (
        not final_entry
        or final_entry.get("index")
        == local_as_of_index
    )

    final_entry_is_causal = (
        not final_entry
        or final_entry.get(
            "causal_valid",
            False,
        )
    )

    final_entry_close_only = (
        not final_entry
        or final_entry.get(
            "break_semantics"
        )
        == "DIRECTIONAL_CLOSE_ONLY"
    )

    manager_continuation_conflict = bool(
        latest_managed_retracement
        and latest_managed_retracement.get(
            "status"
        ) != "CONFIRMED"
        and continuation_state.get(
            "entry_ready",
            False,
        )
    )

    director_entry = director.read("entry")
    canonical_entry_available = bool(
        canonical_entry.get("available", False)
    )
    canonical_entry_ready = bool(
        canonical_entry.get("ready", False)
    )
    canonical_entry_as_of_matches = bool(
        not canonical_entry_ready
        or canonical_entry.get("index")
        == local_as_of_index
    )
    canonical_entry_price_matches_close = bool(
        not canonical_entry_ready
        or canonical_entry.get("price")
        == current_close
    )

    director_report = director.contract_report()

    diagnostics = {
        "requested_as_of_index": (
            as_of_index
        ),
        "local_as_of_index": (
            local_as_of_index
        ),
        "source_rows": len(data),
        "visible_rows": len(causal_data),
        "future_rows_hidden": (
            len(data) - len(causal_data)
        ),

        "future_access_test_passed": (
            future_access_test_passed
        ),
        "future_access_message": (
            future_access_message
        ),

        "contract_valid": (
            director_report.get("valid")
        ),
        "contract_errors": (
            director_report.get(
                "errors",
                [],
            )
        ),
        "contract_warnings": (
            director_report.get(
                "warnings",
                [],
            )
        ),

        "pipeline_stage": (
            "CAUSAL_SETUP_ENTRY_CHAIN"
        ),

        "final_trend": (
            final_trend_context
        ),
        "final_phase": (
            final_phase_context
        ),

        "major_high_count": len(
            major_classified_highs
        ),
        "major_low_count": len(
            major_classified_lows
        ),
        "atr_high_count": len(
            atr_classified_highs
        ),
        "atr_low_count": len(
            atr_classified_lows
        ),

        "atr_bos_count": len(
            atr_bos_events
        ),
        "trade_eligible_bos_count": len(
            trade_eligible_bos
        ),
        "tradable_bos_count": len(
            tradable_bos
        ),

        "future_structures_used": len(
            future_structures_used
        ),
        "untimed_structures": len(
            untimed_structures
        ),
        "future_strength_used": len(
            future_strength_used
        ),
        "future_displacement_used": len(
            future_displacement_used
        ),
        "non_causal_bos": len(
            non_causal_bos
        ),
        "bos_before_confirmation": len(
            bos_before_confirmation
        ),
        "wrong_bos_break_prices": len(
            wrong_bos_break_prices
        ),
        "master_state_causal": (
            master_state.get(
                "causal_valid",
                False,
            )
        ),

        "market_control_state": (
            market_control.get(
                "control_state"
            )
        ),
        "market_control_side": (
            market_control.get(
                "control_side"
            )
        ),
        "market_control_causal": (
            market_control_is_causal
        ),
        "market_control_as_of_matches": (
            market_control_as_of_matches
        ),

        "transition_state": (
            transition_state.get("state")
        ),
        "transition_sequence_confirmed": (
            transition_state.get(
                "sequence_confirmed",
                False,
            )
        ),
        "transition_active": (
            transition_state.get(
                "transition_active",
                False,
            )
        ),
        "transition_recovered": (
            transition_state.get(
                "transition_recovered",
                False,
            )
        ),
        "transition_causal": (
            transition_is_causal
        ),
        "transition_as_of_matches": (
            transition_as_of_matches
        ),
        "unresolved_transition": (
            unresolved_transition
        ),

        "protection_exists": (
            protection_exists
        ),
        "protection_causal": (
            protection_is_causal
        ),
        "protection_fallback_used": (
            protection_fallback_used
        ),
        "protection_available_at": (
            protection_available_at
        ),
        "future_protection_used": (
            future_protection_used
        ),
        "protection_broken": (
            protected_structure.get(
                "protection_broken",
                False,
            )
        ),

        "structure_verdict": (
            structure_validation.get(
                "verdict"
            )
        ),
        "structure_hard_block": (
            structure_validation.get(
                "hard_block",
                False,
            )
        ),
        "structure_hard_failures": (
            structure_validation.get(
                "hard_failures",
                [],
            )
        ),
        "unexplained_structure_block": (
            unexplained_structure_block
        ),
        "recovered_transition_blocked": (
            recovered_transition_blocked
        ),
        "retracement_zone_count": len(
            retracement_zones
        ),
        "managed_retracement_count": len(
            managed_retracements
        ),
        "managed_retracement_status": (
            latest_managed_retracement.get(
                "status"
            )
        ),
        "setup_id": setup_contract.get(
            "setup_id"
        ),
        "setup_lifecycle_status": (
            setup_contract.get("status")
        ),
        "setup_consumed": (
            setup_contract.get("status")
            == "CONSUMED"
        ),
        "setup_consumed_before_candidate": (
            setup_was_consumed
        ),
        "setup_reentry_count": (
            setup_contract.get("reentry_count")
        ),
        "htf_context_state": (
            context_contract.get("state")
        ),
        "htf_approved_direction": (
            context_contract.get(
                "approved_direction"
            )
        ),
        "htf_entry_alignment": (
            context_contract.get(
                "entry_alignment"
            )
        ),
        "htf_context_causal": (
            context_contract.get(
                "causal",
                False,
            )
        ),
        "htf_incomplete_candles_used": (
            context_contract.get(
                "incomplete_htf_candles_used",
                False,
            )
        ),

        "setup_current_only": (
            setup_current_only
        ),
        "stale_setup_confirmation_used": (
            stale_setup_confirmation_used
        ),
        "setup_lifecycle_causal": (
            setup_lifecycle_causal
        ),
        "setup_as_of_matches": (
            setup_as_of_matches
        ),

        "setup_invalidation_exists": (
            setup_invalidation.get(
                "price"
            )
            is not None
        ),
        "setup_invalidation_causal": (
            setup_invalidation_causal
        ),
        "setup_invalidation_broken": (
            setup_invalidation.get(
                "broken",
                False,
            )
        ),
        "future_setup_invalidation_used": (
            future_setup_invalidation_used
        ),

        "continuation_state": (
            continuation_state.get(
                "state"
            )
        ),
        "continuation_ready": (
            continuation_state.get(
                "entry_ready",
                False,
            )
        ),
        "continuation_current_only": (
            continuation_current_only
        ),
        "continuation_causal": (
            continuation_causal
        ),
        "continuation_as_of_matches": (
            continuation_as_of_matches
        ),
        "stale_continuation_used": (
            stale_continuation_used
        ),
        "continuation_entry_is_current": (
            continuation_entry_is_current
        ),

        "entry_validation_state": (
            entry_validation.get("state")
        ),
        "entry_validation_allowed": (
            entry_validation.get("allowed", False)
        ),
        "canonical_entry_available": (
            canonical_entry_available
        ),
        "canonical_entry_state": (
            canonical_entry.get("state")
        ),
        "canonical_entry_ready": (
            canonical_entry_ready
        ),
        "canonical_entry_index": (
            canonical_entry.get("index")
        ),
        "canonical_entry_price": (
            canonical_entry.get("price")
        ),
        "canonical_entry_as_of_matches": (
            canonical_entry_as_of_matches
        ),
        "canonical_entry_price_matches_close": (
            canonical_entry_price_matches_close
        ),
        "canonical_entry_causal": (
            canonical_entry.get("causal", False)
        ),
        "director_entry_available": (
            director_entry.get("available", False)
        ),
        "ledger_entry_event_created": None,

        "final_entry_available": bool(
            final_entry
        ),
        "final_entry_type": (
            final_entry.get("type")
        ),
        "final_entry_index": (
            final_entry.get("index")
        ),
        "final_entry_price": (
            final_entry.get(
                "entry_price"
            )
        ),
        "final_entry_is_current": (
            final_entry_is_current
        ),
        "final_entry_is_causal": (
            final_entry_is_causal
        ),
        "final_entry_close_only": (
            final_entry_close_only
        ),

        "manager_continuation_conflict": (
            manager_continuation_conflict
        ),
    }

    if options.enable_debug:
        print(
            "PIPELINE",
            as_of_index,
            final_trend_context,
            final_phase_context,
            len(atr_bos_events),
        )

    return PipelineResult(
        symbol=symbol,
        timeframe=timeframe,
        requested_as_of_index=as_of_index,
        visible_rows=len(causal_data),
        snapshot=director.snapshot(),
        diagnostics=diagnostics,
    )
