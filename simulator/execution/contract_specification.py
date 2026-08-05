from __future__ import annotations

from dataclasses import replace
from typing import Any

from simulator.models.financial import ContractSpecification


def _spec(
    symbol: str,
    *,
    asset: str,
    base: str,
    quote: str,
    contract: float,
    tick: float,
    tick_value: float,
    point: float,
    minimum: float,
    step: float,
    spread: float,
    commission_type: str = "NO_COMMISSION",
    commission_amount: float = 0.0,
) -> ContractSpecification:
    return ContractSpecification(
        canonical_symbol=symbol,
        broker_symbol=symbol,
        asset_class=asset,
        base_currency=base,
        quote_currency=quote,
        account_currency="ZAR",
        contract_size=contract,
        tick_size=tick,
        tick_value=tick_value,
        point_size=point,
        volume_minimum=minimum,
        volume_maximum=100.0,
        volume_step=step,
        margin_rate=0.0,
        leverage=100.0,
        stop_level_points=0.0,
        freeze_level_points=0.0,
        commission_type=commission_type,
        commission_amount=commission_amount,
        swap_model="DISABLED",
        trading_sessions=("ASIA", "LONDON", "OVERLAP", "NEW_YORK"),
        base_spread_points=spread,
    )


ESTIMATED_CONTRACTS: dict[str, ContractSpecification] = {
    "EURUSD": _spec("EURUSD", asset="FOREX", base="EUR", quote="USD", contract=100_000, tick=0.00001, tick_value=1.0, point=0.00001, minimum=0.01, step=0.01, spread=12, commission_type="PER_LOT_PER_SIDE", commission_amount=3.5),
    "GBPUSD": _spec("GBPUSD", asset="FOREX", base="GBP", quote="USD", contract=100_000, tick=0.00001, tick_value=1.0, point=0.00001, minimum=0.01, step=0.01, spread=15, commission_type="PER_LOT_PER_SIDE", commission_amount=3.5),
    "AUDUSD": _spec("AUDUSD", asset="FOREX", base="AUD", quote="USD", contract=100_000, tick=0.00001, tick_value=1.0, point=0.00001, minimum=0.01, step=0.01, spread=14, commission_type="PER_LOT_PER_SIDE", commission_amount=3.5),
    "USDJPY": _spec("USDJPY", asset="FOREX", base="USD", quote="JPY", contract=100_000, tick=0.001, tick_value=100.0, point=0.001, minimum=0.01, step=0.01, spread=13, commission_type="PER_LOT_PER_SIDE", commission_amount=3.5),
    "GOLD": _spec("GOLD", asset="METAL_CFD", base="XAU", quote="USD", contract=100, tick=0.01, tick_value=1.0, point=0.01, minimum=0.01, step=0.01, spread=25),
    "GER40CASH": _spec("GER40Cash", asset="INDEX_CFD", base="GER40", quote="EUR", contract=1, tick=0.01, tick_value=0.01, point=0.01, minimum=0.01, step=0.01, spread=120),
    "US100CASH": _spec("US100Cash", asset="INDEX_CFD", base="US100", quote="USD", contract=1, tick=0.01, tick_value=0.01, point=0.01, minimum=0.01, step=0.01, spread=180),
    "US30CASH": _spec("US30Cash", asset="INDEX_CFD", base="US30", quote="USD", contract=1, tick=0.01, tick_value=0.01, point=0.01, minimum=0.01, step=0.01, spread=250),
    "OILCASH": _spec("OILCash", asset="ENERGY_CFD", base="OIL", quote="USD", contract=100, tick=0.01, tick_value=1.0, point=0.01, minimum=0.01, step=0.01, spread=5),
}


def normalize_symbol(symbol: str) -> str:
    return str(symbol).replace("#", "").replace(".", "").upper()


class ContractSpecificationService:
    """Publishes symbol-specific, explicitly sourced contract profiles."""

    def __init__(self, overrides: dict[str, dict[str, Any]] | None = None):
        self.overrides = overrides or {}

    def get(self, symbol: str, *, leverage: float | None = None) -> ContractSpecification:
        key = normalize_symbol(symbol)
        if key not in ESTIMATED_CONTRACTS:
            raise KeyError(f"No contract specification is configured for {symbol}")
        spec = ESTIMATED_CONTRACTS[key]
        if key in self.overrides:
            allowed = set(ContractSpecification.__dataclass_fields__)
            patch = {k: v for k, v in self.overrides[key].items() if k in allowed}
            spec = replace(spec, **patch)
        return replace(
            spec,
            canonical_symbol=str(symbol),
            broker_symbol=str(symbol),
            leverage=float(leverage or spec.leverage),
        )

    def list_profiles(self) -> list[dict[str, Any]]:
        return [spec.payload() for _, spec in sorted(ESTIMATED_CONTRACTS.items())]
