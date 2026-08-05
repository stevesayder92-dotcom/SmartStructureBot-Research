from __future__ import annotations

from simulator.execution.currency_conversion import CurrencyConversionEngine
from simulator.models.financial import ContractSpecification


class MarginEngine:
    def __init__(self, conversion: CurrencyConversionEngine):
        self.conversion = conversion

    def required_margin(
        self,
        *,
        spec: ContractSpecification,
        price: float,
        volume: float,
        timestamp: float,
        leverage: float,
    ) -> float:
        notional_native = abs(float(price) * spec.contract_size * float(volume))
        native_margin = notional_native * spec.margin_rate if spec.margin_rate > 0 else notional_native / max(1.0, leverage)
        converted = self.conversion.convert(native_margin, spec.quote_currency, timestamp)
        if converted.account_currency_amount is None:
            raise ValueError(f"Missing conversion rate for margin currency {spec.quote_currency}")
        return round(converted.account_currency_amount, 6)

    @staticmethod
    def status(equity: float, used_margin: float, warning: float, call: float, stop_out: float) -> tuple[float | None, str]:
        if used_margin <= 0:
            return None, "HEALTHY"
        level = equity / used_margin * 100.0
        if level <= stop_out:
            return level, "STOP_OUT"
        if level <= call:
            return level, "MARGIN_CALL"
        if level <= warning:
            return level, "LOW_MARGIN_WARNING"
        return level, "HEALTHY"
