from __future__ import annotations

import math

from simulator.execution.currency_conversion import CurrencyConversionEngine
from simulator.execution.margin_engine import MarginEngine
from simulator.models.financial import AccountConfig, AccountState, ContractSpecification, SizingResult


def _round_down(value: float, step: float) -> float:
    if step <= 0:
        return value
    return math.floor((value + 1e-12) / step) * step


class PositionSizer:
    def __init__(self, conversion: CurrencyConversionEngine, margin: MarginEngine):
        self.conversion = conversion
        self.margin = margin

    @staticmethod
    def planned_risk(config: AccountConfig, account: AccountState, setup_grade: str | None = None) -> float:
        original = account.initial_balance
        balance = account.current_balance if config.compounding else original
        equity = account.current_equity if config.compounding else original
        if config.risk_model == "FIXED_PERCENTAGE_OF_CURRENT_EQUITY":
            value = equity * config.risk_percent / 100.0
        elif config.risk_model == "FIXED_RAND_AMOUNT":
            value = config.fixed_risk_money
        elif config.risk_model == "FIXED_MINIMUM_BROKER_VOLUME":
            value = balance * config.maximum_account_risk_percent / 100.0
        else:
            value = balance * config.risk_percent / 100.0
        if config.risk_model == "GRADE_ADJUSTED_RESEARCH_RISK":
            value *= config.grade_risk_multipliers.get(str(setup_grade or "A"), 1.0)
        return max(0.0, value)

    def size(
        self,
        *,
        config: AccountConfig,
        account: AccountState,
        spec: ContractSpecification,
        entry_fill: float,
        logical_stop: float,
        emergency_stop: float,
        timestamp: float,
        spread_points: float,
        emergency_slippage_points: float,
        setup_grade: str | None = None,
    ) -> SizingResult:
        planned = self.planned_risk(config, account, setup_grade)
        rate, _, status = self.conversion.rate(spec.quote_currency, timestamp)
        if rate is None or status == "MISSING_RATE":
            return SizingResult("MISSING_CONVERSION_RATE", False, 0, 0, 0, 0, planned, 0, 0, 0, 0, 0, "Currency conversion unavailable")
        logical_ticks = abs(entry_fill - logical_stop) / spec.tick_size
        emergency_ticks = abs(entry_fill - emergency_stop) / spec.tick_size + spread_points * spec.point_size / spec.tick_size + emergency_slippage_points * spec.point_size / spec.tick_size
        if logical_ticks <= 0 or emergency_ticks <= 0:
            return SizingResult("INVALID_STOP_DISTANCE", False, 0, 0, 0, 0, planned, 0, 0, 0, 0, 0, "Stop distance is not economically valid")
        logical_per_lot = logical_ticks * spec.tick_value * rate
        emergency_per_lot = emergency_ticks * spec.tick_value * rate
        ideal = spec.volume_minimum if config.risk_model == "FIXED_MINIMUM_BROKER_VOLUME" else planned / logical_per_lot
        risk_cap_money = account.current_balance * config.maximum_account_risk_percent / 100.0
        emergency_cap_money = account.current_balance * config.maximum_emergency_risk_percent / 100.0
        risk_cap_lots = min(ideal, risk_cap_money / logical_per_lot, emergency_cap_money / emergency_per_lot, spec.volume_maximum)
        margin_per_lot = self.margin.required_margin(spec=spec, price=entry_fill, volume=1.0, timestamp=timestamp, leverage=config.leverage)
        margin_cap_lots = min(risk_cap_lots, account.free_margin / margin_per_lot if margin_per_lot > 0 else risk_cap_lots)
        final = _round_down(margin_cap_lots, spec.volume_step)
        unsafe = False
        status_name = "EXACT_RISK_ACHIEVED"
        reason = "Volume rounded down to the broker step without exceeding risk or margin caps."
        if final < spec.volume_minimum:
            candidate = spec.volume_minimum
            logical_min = logical_per_lot * candidate
            emergency_min = emergency_per_lot * candidate
            margin_min = margin_per_lot * candidate
            safe = logical_min <= risk_cap_money + 1e-9 and emergency_min <= emergency_cap_money + 1e-9 and margin_min <= account.free_margin + 1e-9
            within_tolerance = logical_min <= planned * 1.20 + 1e-9
            if safe and (within_tolerance or config.risk_model == "FIXED_MINIMUM_BROKER_VOLUME"):
                final = candidate
                status_name = "ROUNDED_WITHIN_TOLERANCE"
                reason = "Broker minimum volume is within the configured risk and margin tolerance."
            elif config.unsafe_minimum_volume_override and margin_min <= account.free_margin + 1e-9:
                final = candidate
                status_name = "UNSAFE_MINIMUM_VOLUME_OVERRIDE"
                reason = "Explicit research override accepted minimum volume above the safe risk cap."
                unsafe = True
            else:
                block = "INSUFFICIENT_MARGIN" if margin_min > account.free_margin else "MINIMUM_VOLUME_OVER_RISK"
                return SizingResult(block, False, ideal, risk_cap_lots, margin_cap_lots, 0.0, planned, logical_min, emergency_min, logical_min / account.current_balance * 100, emergency_min / account.current_balance * 100, margin_min, "ORDER BLOCKED — minimum volume exceeds margin or configured risk limits.")
        actual_logical = logical_per_lot * final
        actual_emergency = emergency_per_lot * final
        margin_required = margin_per_lot * final
        if margin_required > account.free_margin + 1e-9:
            return SizingResult("INSUFFICIENT_MARGIN", False, ideal, risk_cap_lots, margin_cap_lots, 0, planned, actual_logical, actual_emergency, actual_logical / account.current_balance * 100, actual_emergency / account.current_balance * 100, margin_required, "Required margin exceeds free margin")
        if abs(actual_logical - planned) > max(spec.tick_value * rate * spec.volume_step, planned * 0.02):
            status_name = "ROUNDED_WITHIN_TOLERANCE"
        return SizingResult(
            status_name,
            True,
            ideal,
            risk_cap_lots,
            margin_cap_lots,
            final,
            planned,
            actual_logical,
            actual_emergency,
            actual_logical / account.current_balance * 100.0,
            actual_emergency / account.current_balance * 100.0,
            margin_required,
            reason,
            unsafe,
        )
