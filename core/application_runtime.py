from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import pandas as pd

from core.htf_context import (
    HTFContextPolicy,
    HigherTimeframeContextEngine,
)
from core.expert_strategy import build_expert_htf_context
from core.mt5_connector import (
    CandleDataAudit,
    connect_mt5,
    get_market_data,
    shutdown_mt5,
    timeframe_seconds,
)
from core.pipeline_runner import (
    PipelineOptions,
    PipelineResult,
    run_pipeline,
)
from core.replay_runner import (
    ReplayOptions,
    ReplayResult,
    run_replay,
)
from core.runtime_config import (
    RuntimeConfig,
    load_runtime_config,
)
from core.setup_lifecycle import PipelineRuntimeState
from core.steve_trade_management import (
    SteveManagementConfig,
    SteveTradeManagementEngine,
)


CANONICAL_OUTPUT_SECTIONS = (
    "meta",
    "market",
    "structure",
    "control",
    "context",
    "transition",
    "validation",
    "protection",
    "retracement",
    "setup",
    "entry",
    "contract_health",
)


@dataclass
class ApplicationResult:
    config: RuntimeConfig
    resolved_symbol: str
    snapshot: Dict[str, Any]
    canonical_outputs: Dict[str, Dict[str, Any]]
    replay: ReplayResult
    data_audit: Optional[CandleDataAudit]
    action: str


def _canonical_outputs(
    snapshot: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    return {
        section: dict(snapshot.get(section, {}) or {})
        for section in CANONICAL_OUTPUT_SECTIONS
    }


def _configured_runtime_state(
    config: RuntimeConfig,
) -> PipelineRuntimeState:
    management = SteveManagementConfig(
        m5_atr_tolerance=float(config.m5_logical_atr_tolerance),
        m5_min_body_atr=float(config.m5_min_body_atr),
        m5_min_close_distance_atr=float(
            config.m5_min_close_distance_atr
        ),
        emergency_atr_buffer=float(
            config.emergency_stop_atr_buffer
        ),
        trail_atr_tolerance=float(config.trail_atr_tolerance),
        trail_min_body_atr=float(config.trail_min_body_atr),
        management_profile=str(config.management_profile),
        tp1_model=str(config.tp1_model),
        configurable_r_target=float(config.configurable_r_target),
    )
    return PipelineRuntimeState(
        expert_trade_manager=SteveTradeManagementEngine(
            config=management
        )
    )


def analyze_closed_data(
    *,
    data: pd.DataFrame,
    config: RuntimeConfig,
    data_audit: Optional[CandleDataAudit] = None,
    pipeline_callable: Callable[
        ...,
        PipelineResult,
    ] = run_pipeline,
    higher_timeframe_context: Optional[
        Dict[str, Any]
    ] = None,
    higher_timeframe_context_provider: Optional[
        Callable[[int], Dict[str, Any]]
    ] = None,
) -> ApplicationResult:
    if data.empty:
        raise ValueError(
            "Application runtime requires closed candle data"
        )

    end_index = len(data) - 1
    start_index = min(
        config.replay_start_index,
        end_index,
    )
    replay = run_replay(
        data=data,
        symbol=config.symbol,
        timeframe=config.timeframe,
        options=ReplayOptions(
            start_index=start_index,
            end_index=end_index,
            continue_on_error=False,
            enable_progress=False,
        ),
        pipeline_options=PipelineOptions(
            strategy_model=config.strategy_model,
            engine_sensitivity=config.engine_sensitivity,
            fibonacci_minimum_depth=config.fibonacci_minimum_depth,
            fibonacci_primary_minimum=config.fibonacci_primary_minimum,
            fibonacci_primary_maximum=config.fibonacci_primary_maximum,
            fibonacci_deep_maximum=config.fibonacci_deep_maximum,
        ),
        pipeline_callable=pipeline_callable,
        higher_timeframe_context_provider=(
            higher_timeframe_context_provider
            if higher_timeframe_context_provider is not None
            else
            (
                lambda index: (
                    higher_timeframe_context
                    if index == end_index
                    else {}
                )
            )
            if higher_timeframe_context is not None
            else None
        ),
        runtime_state=_configured_runtime_state(config),
    )

    if not replay.pipeline_results:
        raise RuntimeError(
            "Canonical runtime produced no pipeline result"
        )

    snapshot = replay.pipeline_results[-1].snapshot
    canonical = _canonical_outputs(snapshot)

    if config.mode == "PAPER_SIGNAL":
        action = (
            "PAPER_SIGNAL_READY"
            if canonical["entry"].get("ready") is True
            else "NO_PAPER_SIGNAL"
        )
    elif config.mode == "REPORT":
        action = "REPORT_ONLY"
    else:
        action = "RESEARCH_ONLY"

    return ApplicationResult(
        config=config,
        resolved_symbol=config.symbol,
        snapshot=snapshot,
        canonical_outputs=canonical,
        replay=replay,
        data_audit=data_audit,
        action=action,
    )


def run_mt5_application(
    config: RuntimeConfig,
    *,
    mt5_api: Any = None,
    pipeline_callable: Callable[
        ...,
        PipelineResult,
    ] = run_pipeline,
) -> ApplicationResult:
    api = connect_mt5(mt5_api)

    try:
        data, audit = get_market_data(
            symbol=config.symbol,
            timeframe=config.timeframe,
            candles=config.candles,
            mt5_api=api,
            minimum_history=config.minimum_history,
            source_timezone=(
                config.source_timezone
            ),
            broker_timezone=(
                config.broker_timezone
            ),
            stale_after_intervals=(
                config.stale_after_intervals
            ),
            strict_missing_candles=(
                config.strict_missing_candles
            ),
            preferred_suffix=(
                config.preferred_symbol_suffix
            ),
        )
        export_path_value = config.raw.get(
            "closed_data_export_path"
        )
        if export_path_value:
            export_path = Path(
                str(export_path_value)
            ).expanduser().resolve()
            export_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            data.to_csv(export_path, index=False)
        frame_histories = {}
        raw_htf_frames: Dict[str, pd.DataFrame] = {}

        for htf_timeframe in (
            config.htf_timeframes
        ):
            htf_data, _ = get_market_data(
                symbol=config.symbol,
                timeframe=htf_timeframe,
                candles=config.htf_candles,
                mt5_api=api,
                minimum_history=min(
                    config.minimum_history,
                    config.htf_candles,
                ),
                source_timezone=(
                    config.source_timezone
                ),
                broker_timezone=(
                    config.broker_timezone
                ),
                stale_after_intervals=(
                    config.stale_after_intervals
                ),
                strict_missing_candles=(
                    config.strict_missing_candles
                ),
                preferred_suffix=(
                    config.preferred_symbol_suffix
                ),
            )
            raw_htf_frames[htf_timeframe] = htf_data
            if config.strategy_model == "EXPERT_SPEC_V1":
                continue
            htf_result = pipeline_callable(
                data=htf_data,
                symbol=audit.symbol,
                timeframe=htf_timeframe,
                as_of_index=len(htf_data) - 1,
                options=PipelineOptions(
                    strategy_model="LEGACY_PHASE6",
                ),
                runtime_state=PipelineRuntimeState(),
            )
            htf_open_time = float(
                htf_data.iloc[-1]["time"]
            )
            frame_histories[
                htf_timeframe
            ] = [
                {
                    "bar_open_time": (
                        htf_open_time
                    ),
                    "bar_close_time": (
                        htf_open_time
                        + timeframe_seconds(
                            htf_timeframe
                        )
                    ),
                    "snapshot": (
                        htf_result.snapshot
                    ),
                    "causal": True,
                }
            ]

        if config.strategy_model == "EXPERT_SPEC_V1":
            context_provider = lambda index: build_expert_htf_context(
                decision_candle_open_time=data.iloc[index]["time"],
                decision_timeframe_seconds=timeframe_seconds(
                    config.timeframe
                ),
                frame_data=raw_htf_frames,
                sensitivity=config.engine_sensitivity,
                policy=config.htf_policy,
                allow_single_strong=config.htf_allow_single_strong,
            )
            htf_context = context_provider(len(data) - 1)
        else:
            context_provider = None
            htf_context = (
                HigherTimeframeContextEngine(
                    HTFContextPolicy(
                        name=config.htf_policy,
                        allow_single_strong=(
                            config.htf_allow_single_strong
                        ),
                    )
                ).build(
                    decision_candle_open_time=float(
                        data.iloc[-1]["time"]
                    ),
                    decision_timeframe_seconds=(
                        timeframe_seconds(
                            config.timeframe
                        )
                    ),
                    frame_histories=frame_histories,
                )
            )
        result = analyze_closed_data(
            data=data,
            config=config,
            data_audit=audit,
            pipeline_callable=pipeline_callable,
            higher_timeframe_context=htf_context,
            higher_timeframe_context_provider=context_provider,
        )
        result.resolved_symbol = audit.symbol
        return result
    finally:
        shutdown_mt5(api)


def format_application_report(
    result: ApplicationResult,
) -> str:
    meta = result.canonical_outputs["meta"]
    market = result.canonical_outputs["market"]
    setup = result.canonical_outputs["setup"]
    entry = result.canonical_outputs["entry"]
    context = result.canonical_outputs["context"]
    health = result.canonical_outputs[
        "contract_health"
    ]

    lines = [
        "=" * 72,
        "SMARTSTRUCTUREBOT CANONICAL RESEARCH RUNTIME",
        "=" * 72,
        f"Mode               : {result.config.mode}",
        f"Action             : {result.action}",
        f"Symbol             : {result.resolved_symbol}",
        f"Timeframe          : {result.config.timeframe}",
        f"As-of index        : {meta.get('as_of_index')}",
        f"Trend              : {market.get('trend')}",
        f"Phase              : {market.get('phase')}",
        f"Setup ID           : {setup.get('setup_id')}",
        f"Setup status       : {setup.get('status')}",
        f"Entry state        : {entry.get('state')}",
        f"Entry ready        : {entry.get('ready')}",
        f"Entry index        : {entry.get('index')}",
        f"Entry price        : {entry.get('price')}",
        f"HTF state          : {context.get('state')}",
        f"HTF direction      : "
        f"{context.get('approved_direction')}",
        f"HTF alignment      : "
        f"{context.get('entry_alignment')}",
        f"Contract valid     : {health.get('valid')}",
        f"Replay passed      : "
        f"{result.replay.diagnostics.get('replay_passed')}",
        "Orders called      : NO",
        "=" * 72,
    ]

    if result.data_audit is not None:
        lines.insert(
            -1,
            "Closed candles     : "
            f"{result.data_audit.received_candles}",
        )
        lines.insert(
            -1,
            "Broker timezone    : "
            f"{result.data_audit.broker_timezone}",
        )

    return "\n".join(lines)


def run_from_config_file(
    path: str | Path,
    *,
    mt5_api: Any = None,
) -> ApplicationResult:
    config = load_runtime_config(path)
    return run_mt5_application(
        config,
        mt5_api=mt5_api,
    )
