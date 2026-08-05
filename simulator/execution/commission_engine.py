from __future__ import annotations

from simulator.execution.currency_conversion import CurrencyConversionEngine
from simulator.models.financial import ContractSpecification, ExecutionConfig


class CommissionEngine:
    def __init__(self, conversion: CurrencyConversionEngine):
        self.conversion = conversion

    def charge(
        self,
        *,
        spec: ContractSpecification,
        config: ExecutionConfig,
        volume: float,
        price: float,
        timestamp: float,
        side: str,
    ) -> float:
        if config.commission_model == "NO_COMMISSION" or spec.commission_type == "NO_COMMISSION":
            return 0.0
        if spec.commission_type == "PER_LOT_PER_SIDE":
            native = spec.commission_amount * volume
        elif spec.commission_type == "PER_LOT_ROUND_TURN":
            native = spec.commission_amount * volume / 2.0
        elif spec.commission_type == "FIXED_PER_ORDER":
            native = spec.commission_amount
        elif spec.commission_type == "PERCENTAGE_OF_NOTIONAL":
            native = price * spec.contract_size * volume * spec.commission_amount / 100.0
        else:
            native = 0.0
        result = self.conversion.convert(native, spec.quote_currency, timestamp)
        if result.account_currency_amount is None:
            raise ValueError(f"Missing conversion rate for commission currency {spec.quote_currency}")
        multiplier = {"IDEALIZED_CONTROL": 0.5, "NORMAL_ESTIMATED": 1.0, "STRESSED_COSTS": 1.5}[config.cost_profile]
        return round(result.account_currency_amount * multiplier, 6)
