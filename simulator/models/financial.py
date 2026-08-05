from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from simulator.models.schema import json_safe, stable_hash


@dataclass(frozen=True)
class AccountConfig:
    account_currency: str = "ZAR"
    starting_balance: float = 1000.0
    risk_model: str = "FIXED_PERCENTAGE_OF_CURRENT_BALANCE"
    risk_percent: float = 1.0
    fixed_risk_money: float = 10.0
    maximum_account_risk_percent: float = 2.0
    maximum_emergency_risk_percent: float = 2.5
    leverage: float = 100.0
    margin_warning_level: float = 150.0
    margin_call_level: float = 100.0
    stop_out_level: float = 50.0
    maximum_concurrent_positions: int = 1
    compounding: bool = True
    unsafe_minimum_volume_override: bool = False
    grade_risk_multipliers: dict[str, float] = field(
        default_factory=lambda: {"A+": 1.0, "A": 1.0, "B": 0.5, "C": 0.25}
    )

    def __post_init__(self) -> None:
        if self.account_currency != "ZAR":
            raise ValueError("Phase S1B currently supports ZAR paper accounts only")
        if self.starting_balance <= 0:
            raise ValueError("Starting balance must be positive")
        if not 0 < self.risk_percent <= 100:
            raise ValueError("Risk percent must be between 0 and 100")
        if self.fixed_risk_money <= 0:
            raise ValueError("Fixed risk money must be positive")
        if self.maximum_account_risk_percent <= 0:
            raise ValueError("Maximum account risk must be positive")
        if self.maximum_emergency_risk_percent <= 0:
            raise ValueError("Maximum emergency risk must be positive")
        if self.leverage <= 0:
            raise ValueError("Leverage must be positive")
        if self.maximum_concurrent_positions < 1:
            raise ValueError("At least one concurrent paper position must be allowed")

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "AccountConfig":
        if not raw:
            return cls()
        allowed = set(cls.__dataclass_fields__)
        return cls(**{key: raw[key] for key in raw if key in allowed})

    def payload(self) -> dict[str, Any]:
        return json_safe(asdict(self))

    def hash(self) -> str:
        return stable_hash(self.payload())


@dataclass(frozen=True)
class ExecutionConfig:
    broker_profile: str = "XM_ESTIMATED_RESEARCH"
    cost_profile: str = "NORMAL_ESTIMATED"
    spread_model: str = "AUTO_NATIVE_SESSION_FALLBACK"
    fixed_spread_points: float | None = None
    slippage_model: str = "DETERMINISTIC_SEEDED"
    fixed_slippage_points: float = 0.0
    commission_model: str = "CONTRACT_SPECIFICATION"
    swap_model: str = "DISABLED"
    execution_timing_model: str = "BOS_CLOSE_PLUS_COSTS"
    intrabar_policy: str = "LOWER_TIMEFRAME_THEN_CONSERVATIVE_STOP_FIRST"
    session_seed: str = "SMARTSTRUCTUREBOT_S1B_SEED_20260803"
    partial_fraction: float = 0.5
    triple_swap_weekday: int = 2

    def __post_init__(self) -> None:
        if self.cost_profile not in {"IDEALIZED_CONTROL", "NORMAL_ESTIMATED", "STRESSED_COSTS"}:
            raise ValueError("Unknown cost sensitivity profile")
        if not 0 < self.partial_fraction < 1:
            raise ValueError("Partial fraction must be between zero and one")

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "ExecutionConfig":
        if not raw:
            return cls()
        allowed = set(cls.__dataclass_fields__)
        return cls(**{key: raw[key] for key in raw if key in allowed})

    def payload(self) -> dict[str, Any]:
        return json_safe(asdict(self))

    def hash(self) -> str:
        return stable_hash(self.payload())


@dataclass(frozen=True)
class ContractSpecification:
    canonical_symbol: str
    broker_symbol: str
    asset_class: str
    base_currency: str
    quote_currency: str
    account_currency: str
    contract_size: float
    tick_size: float
    tick_value: float
    point_size: float
    volume_minimum: float
    volume_maximum: float
    volume_step: float
    margin_rate: float
    leverage: float
    stop_level_points: float
    freeze_level_points: float
    commission_type: str
    commission_amount: float
    swap_model: str
    trading_sessions: tuple[str, ...]
    base_spread_points: float
    source_status: str = "ESTIMATED_RESEARCH_PROFILE"
    source_note: str = "Manual research estimate; verify against broker metadata before forward use."

    def payload(self) -> dict[str, Any]:
        return json_safe(asdict(self))


@dataclass(frozen=True)
class SizingResult:
    status: str
    allowed: bool
    ideal_lots: float
    risk_capped_lots: float
    margin_capped_lots: float
    final_lots: float
    ideal_risk_money_zar: float
    actual_logical_risk_zar: float
    actual_emergency_risk_zar: float
    actual_logical_risk_percent: float
    actual_emergency_risk_percent: float
    margin_required_zar: float
    sizing_reason: str
    unsafe_override_used: bool = False

    def payload(self) -> dict[str, Any]:
        return json_safe(asdict(self))


@dataclass(frozen=True)
class PaperOrderRequest:
    order_id: str
    replay_event_id: str
    timestamp: float
    account_id: str
    setup_id: str | None
    sequence_id: str | None
    attempt_id: str | None
    symbol: str
    direction: str
    action: str
    requested_volume: float
    requested_price: float
    logical_stop: float
    emergency_stop: float
    target_1: float | None
    target_2: float | None
    entry_timeframe: str
    strategy_signal: str
    causal_valid: bool = True

    def payload(self) -> dict[str, Any]:
        return json_safe(asdict(self))


@dataclass(frozen=True)
class FillResult:
    status: str
    requested_price: float
    market_reference_price: float
    chart_price: float
    bid_price: float
    ask_price: float
    spread_adjusted_price: float
    spread_points: float
    spread_state: str
    spread_source: str
    slippage_points: float
    slippage_money_zar: float
    final_fill_price: float
    fill_side: str
    slippage_model: str
    random_seed: str | None
    commission_zar: float
    conversion_rate: float
    conversion_source: str

    def payload(self) -> dict[str, Any]:
        return json_safe(asdict(self))


@dataclass
class PositionState:
    position_id: str
    account_id: str
    setup_id: str | None
    sequence_id: str | None
    attempt_id: str | None
    attempt_number: int
    symbol: str
    direction: str
    entry_timeframe: str
    opened_at: float
    requested_volume: float
    volume: float
    initial_volume: float
    entry_reference_price: float
    entry_fill_price: float
    logical_stop: float
    emergency_stop: float
    current_protection: float
    target_1: float | None
    target_2: float | None
    opening_commission_zar: float
    opening_spread_cost_zar: float
    opening_slippage_cost_zar: float
    margin_used_zar: float
    planned_risk_zar: float
    actual_logical_risk_zar: float
    actual_emergency_risk_zar: float
    peak_unrealized_zar: float = 0.0
    peak_r: float = 0.0
    realized_zar: float = 0.0
    commission_zar: float = 0.0
    swap_zar: float = 0.0
    partials: list[dict[str, Any]] = field(default_factory=list)
    status: str = "OPEN"
    closed_at: float | None = None
    exit_reason: str | None = None
    exit_fill_price: float | None = None

    def payload(self) -> dict[str, Any]:
        return json_safe(asdict(self))


@dataclass
class AccountState:
    account_id: str
    currency: str
    initial_balance: float
    current_balance: float
    current_equity: float
    free_margin: float
    used_margin: float
    margin_level: float | None
    floating_pl: float
    realized_pl: float
    total_costs: float
    peak_equity: float
    drawdown_money: float
    drawdown_percent: float
    return_percent: float
    account_status: str
    open_positions: int
    minimum_volume_blocks: int = 0
    margin_warnings: int = 0
    stop_outs: int = 0

    def payload(self) -> dict[str, Any]:
        return json_safe(asdict(self))


@dataclass(frozen=True)
class MonetaryEvent:
    execution_event_id: str
    replay_event_id: str
    timestamp: float
    account_id: str
    setup_id: str | None
    sequence_id: str | None
    attempt_id: str | None
    symbol: str
    action: str
    volume: float
    requested_price: float | None
    fill_price: float | None
    costs: dict[str, float]
    gross_pl: float
    net_pl: float
    balance_after: float
    equity_after: float
    margin_after: float
    causal_valid: bool
    parent_state_hash: str | None
    state_hash: str
    details: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return json_safe(asdict(self))
