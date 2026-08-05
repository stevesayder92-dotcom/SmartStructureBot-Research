from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict


SAFE_RUNTIME_MODES = {
    "RESEARCH",
    "REPORT",
    "PAPER_SIGNAL",
}


@dataclass(frozen=True)
class RuntimeConfig:
    mode: str = "RESEARCH"
    symbol: str = "GER40Cash#"
    timeframe: str = "M5"
    candles: int = 400
    replay_start_index: int = 100
    broker_timezone: str = "UTC"
    source_timezone: str = "UTC"
    minimum_history: int = 100
    stale_after_intervals: int = 3
    strict_missing_candles: bool = False
    preferred_symbol_suffix: str = "#"
    approved_symbols: tuple[str, ...] = (
        "EURUSD#",
        "GBPUSD#",
        "AUDUSD#",
        "USDJPY#",
        "GOLD#",
        "GER40Cash#",
        "US100Cash#",
        "US30Cash#",
        "OILCash#",
    )
    htf_timeframes: tuple[str, ...] = (
        "H1",
        "M30",
        "M15",
    )
    strategy_model: str = "EXPERT_SPEC_V1"
    engine_sensitivity: int = 3
    fibonacci_minimum_depth: float = 0.236
    fibonacci_primary_minimum: float = 0.382
    fibonacci_primary_maximum: float = 0.618
    fibonacci_deep_maximum: float = 0.786
    htf_policy: str = "STRICT_2_OF_3_H1_M30_M15"
    htf_allow_single_strong: bool = False
    htf_candles: int = 300
    entry_timeframes: tuple[str, ...] = ("M5", "M1_FALLBACK")
    allowed_sessions: tuple[str, ...] = (
        "LONDON",
        "NEW_YORK",
        "OVERLAP",
    )
    session_filter_mode: str = "RESEARCH_COMPARISON"
    management_profile: str = "TWIN_POSITION_50_50"
    tp1_model: str = "PREVIOUS_IMPULSE_EXTREME"
    configurable_r_target: float = 1.0
    m5_logical_atr_tolerance: float = 0.15
    m5_min_body_atr: float = 0.35
    m5_min_close_distance_atr: float = 0.10
    emergency_stop_atr_buffer: float = 1.0
    trail_atr_tolerance: float = 0.10
    trail_min_body_atr: float = 0.25
    m1_minimum_counter_bars: int = 3
    m1_max_trigger_age: int = 30
    target_approach_fraction: float = 0.10
    profit_lock_trigger_r: float = 1.0
    profit_lock_r: float = 0.10
    tp1_partial_fraction: float = 0.50
    htf_research_policies: tuple[str, ...] = (
        "STRICT_2_OF_3",
        "PREFERRED_M30_M15",
        "ONE_EXCEPTIONALLY_CLEAN_HTF",
        "CONFLICT_RISK_REDUCTION",
    )
    raw: Dict[str, Any] = field(
        default_factory=dict,
        compare=False,
    )

    def __post_init__(self) -> None:
        normalized_mode = str(self.mode).upper()
        object.__setattr__(self, "mode", normalized_mode)

        if normalized_mode not in SAFE_RUNTIME_MODES:
            raise ValueError(
                f"Unsafe or unsupported runtime mode {self.mode!r}. "
                f"Allowed modes: {sorted(SAFE_RUNTIME_MODES)}"
            )

        if not self.symbol:
            raise ValueError("Runtime symbol cannot be empty")

        if self.approved_symbols and (
            self.symbol not in self.approved_symbols
        ):
            raise ValueError(
                f"Symbol {self.symbol!r} is not in approved_symbols"
            )

        for name, value in {
            "candles": self.candles,
            "minimum_history": self.minimum_history,
            "stale_after_intervals": (
                self.stale_after_intervals
            ),
            "htf_candles": self.htf_candles,
            "m1_minimum_counter_bars": self.m1_minimum_counter_bars,
            "m1_max_trigger_age": self.m1_max_trigger_age,
        }.items():
            if int(value) <= 0:
                raise ValueError(
                    f"{name} must be greater than zero"
                )

        if self.replay_start_index < 0:
            raise ValueError(
                "replay_start_index cannot be negative"
            )
        if int(self.engine_sensitivity) <= 0:
            raise ValueError(
                "engine_sensitivity must be greater than zero"
            )
        if not (
            0 < float(self.fibonacci_minimum_depth)
            <= float(self.fibonacci_primary_minimum)
            <= float(self.fibonacci_primary_maximum)
            <= float(self.fibonacci_deep_maximum)
            <= 1
        ):
            raise ValueError("Fibonacci thresholds are not ordered")
        if self.management_profile not in {
            "STRUCTURE_RUNNER_ONLY",
            "TWIN_POSITION_50_50",
            "PARTIAL_PLUS_RUNNER",
        }:
            raise ValueError("Unsupported management_profile")
        if self.tp1_model not in {
            "PREVIOUS_HTF_EXTREME",
            "PREVIOUS_IMPULSE_EXTREME",
            "CONFIGURABLE_R",
            "NEAREST_MEANINGFUL_LIQUIDITY",
        }:
            raise ValueError("Unsupported tp1_model")
        if self.emergency_stop_atr_buffer <= 0:
            raise ValueError(
                "emergency_stop_atr_buffer must be positive"
            )
        for value_name in (
            "m5_logical_atr_tolerance",
            "m5_min_body_atr",
            "m5_min_close_distance_atr",
            "trail_atr_tolerance",
            "trail_min_body_atr",
            "target_approach_fraction",
            "profit_lock_trigger_r",
            "profit_lock_r",
        ):
            if float(getattr(self, value_name)) < 0:
                raise ValueError(f"{value_name} cannot be negative")
        if not 0 <= float(self.tp1_partial_fraction) <= 1:
            raise ValueError("tp1_partial_fraction must be in [0, 1]")
        if self.strategy_model not in {
            "EXPERT_SPEC_V1",
            "LEGACY_PHASE6",
        }:
            raise ValueError(
                f"Unsupported strategy_model {self.strategy_model!r}"
            )
        if (
            self.strategy_model == "EXPERT_SPEC_V1"
            and tuple(self.htf_timeframes)
            != ("H1", "M30", "M15")
        ):
            raise ValueError(
                "EXPERT_SPEC_V1 requires H1, M30 and M15 HTF frames"
            )


def load_runtime_config(
    path: str | Path,
) -> RuntimeConfig:
    config_path = Path(path).expanduser().resolve()

    with config_path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError(
            "Runtime configuration must be a JSON object"
        )

    values = dict(payload)
    # Research-only output directive consumed by application_runtime.
    # It is deliberately not a strategy or execution parameter.
    values.pop("closed_data_export_path", None)

    if "approved_symbols" in values:
        values["approved_symbols"] = tuple(
            values["approved_symbols"]
        )

    if "htf_timeframes" in values:
        values["htf_timeframes"] = tuple(
            values["htf_timeframes"]
        )
    if "entry_timeframes" in values:
        values["entry_timeframes"] = tuple(
            values["entry_timeframes"]
        )
    if "allowed_sessions" in values:
        values["allowed_sessions"] = tuple(
            values["allowed_sessions"]
        )
    if "htf_research_policies" in values:
        values["htf_research_policies"] = tuple(
            values["htf_research_policies"]
        )

    values["raw"] = payload
    return RuntimeConfig(**values)
