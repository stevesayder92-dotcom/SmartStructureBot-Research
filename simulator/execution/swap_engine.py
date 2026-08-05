from __future__ import annotations

from datetime import datetime, timezone

from simulator.execution.currency_conversion import CurrencyConversionEngine
from simulator.models.financial import ContractSpecification, ExecutionConfig


class SwapEngine:
    """Configurable research holding-cost calculator; disabled by default."""

    def __init__(self, conversion: CurrencyConversionEngine):
        self.conversion = conversion

    def charge(self, *, spec: ContractSpecification, config: ExecutionConfig, timestamp: float, volume: float) -> dict[str, float | bool | str]:
        if config.swap_model == "DISABLED":
            return {"charge_zar": 0.0, "triple_swap": False, "status": "SWAP_NOT_MODELLED"}
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        multiplier = 3.0 if dt.weekday() == config.triple_swap_weekday else 1.0
        result = self.conversion.convert(-0.50 * float(volume) * multiplier, spec.quote_currency, timestamp)
        if result.account_currency_amount is None:
            return {"charge_zar": 0.0, "triple_swap": multiplier == 3.0, "status": "MISSING_CONVERSION_RATE"}
        return {"charge_zar": abs(float(result.account_currency_amount)), "triple_swap": multiplier == 3.0, "status": config.swap_model}
