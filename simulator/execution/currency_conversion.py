from __future__ import annotations

from dataclasses import dataclass
from typing import Any


STATIC_ZAR_RATES = {
    "ZAR": 1.0,
    "USD": 18.30,
    "EUR": 21.00,
    "GBP": 24.20,
    "JPY": 0.125,
    "AUD": 12.00,
}


@dataclass(frozen=True)
class ConversionResult:
    native_amount: float
    native_currency: str
    conversion_rate: float | None
    account_currency_amount: float | None
    conversion_source: str
    conversion_timestamp: float
    status: str

    def payload(self) -> dict[str, Any]:
        return {
            "native_PL": self.native_amount,
            "native_currency": self.native_currency,
            "conversion_rate": self.conversion_rate,
            "account_currency_PL": self.account_currency_amount,
            "conversion_source": self.conversion_source,
            "conversion_timestamp": self.conversion_timestamp,
            "status": self.status,
        }


class CurrencyConversionEngine:
    def __init__(self, static_rates: dict[str, float] | None = None):
        self.static_rates = {**STATIC_ZAR_RATES, **(static_rates or {})}

    def rate(
        self,
        currency: str,
        timestamp: float,
        historical_rates: dict[str, float] | None = None,
    ) -> tuple[float | None, str, str]:
        code = str(currency).upper()
        if historical_rates and code in historical_rates:
            return float(historical_rates[code]), "HISTORICAL_RATE", "HISTORICAL_RATE"
        if code in self.static_rates:
            return float(self.static_rates[code]), "STATIC_RESEARCH_RATE", "STATIC_RESEARCH_RATE"
        return None, "MISSING_RATE", "MISSING_RATE"

    def convert(
        self,
        amount: float,
        currency: str,
        timestamp: float,
        historical_rates: dict[str, float] | None = None,
    ) -> ConversionResult:
        rate, source, status = self.rate(currency, timestamp, historical_rates)
        converted = None if rate is None else float(amount) * rate
        return ConversionResult(
            native_amount=float(amount),
            native_currency=str(currency).upper(),
            conversion_rate=rate,
            account_currency_amount=converted,
            conversion_source=source,
            conversion_timestamp=float(timestamp),
            status=status,
        )
