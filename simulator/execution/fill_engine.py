from __future__ import annotations

from typing import Any

from simulator.execution.commission_engine import CommissionEngine
from simulator.execution.currency_conversion import CurrencyConversionEngine
from simulator.execution.slippage_engine import SlippageEngine
from simulator.execution.spread_engine import SpreadEngine
from simulator.models.financial import ContractSpecification, ExecutionConfig, FillResult


class FillEngine:
    def __init__(self, conversion: CurrencyConversionEngine):
        self.conversion = conversion
        self.spread = SpreadEngine()
        self.slippage = SlippageEngine()
        self.commission = CommissionEngine(conversion)

    def fill(
        self,
        *,
        spec: ContractSpecification,
        config: ExecutionConfig,
        replay_event_id: str,
        order_id: str,
        timestamp: float,
        candle: dict[str, Any],
        direction: str,
        order_kind: str,
        volume: float,
        requested_price: float,
        volatility_ratio: float = 1.0,
    ) -> FillResult:
        chart_price = float(candle.get("close", requested_price))
        spread = self.spread.calculate(spec=spec, config=config, timestamp=timestamp, candle=candle, volatility_ratio=volatility_ratio)
        bid = float(candle.get("bid_close", chart_price))
        ask = float(candle.get("ask_close", bid + spread["spread_price"]))
        is_entry = order_kind == "ENTRY"
        fill_side = "ASK" if (direction == "BULLISH" and is_entry) or (direction == "BEARISH" and not is_entry) else "BID"
        spread_adjusted = ask if fill_side == "ASK" else bid
        slip = self.slippage.calculate(spec=spec, config=config, replay_event_id=replay_event_id, order_id=order_id, order_kind=order_kind, volatility_ratio=volatility_ratio)
        slip_price = float(slip["slippage_points"]) * spec.point_size
        adverse_sign = 1.0 if fill_side == "ASK" else -1.0
        final = spread_adjusted + adverse_sign * slip_price
        rate, source, _ = self.conversion.rate(spec.quote_currency, timestamp)
        if rate is None:
            raise ValueError(f"Missing currency conversion for {spec.quote_currency}")
        slippage_native = abs(slip_price) / spec.tick_size * spec.tick_value * volume
        slippage_zar = slippage_native * rate
        commission = self.commission.charge(spec=spec, config=config, volume=volume, price=final, timestamp=timestamp, side="OPEN" if is_entry else "CLOSE")
        return FillResult(
            status="FILLED_PAPER_ONLY",
            requested_price=float(requested_price),
            market_reference_price=chart_price,
            chart_price=chart_price,
            bid_price=bid,
            ask_price=ask,
            spread_adjusted_price=spread_adjusted,
            spread_points=float(spread["spread_points"]),
            spread_state=str(spread["spread_state"]),
            spread_source=str(spread["spread_source"]),
            slippage_points=float(slip["slippage_points"]),
            slippage_money_zar=slippage_zar,
            final_fill_price=final,
            fill_side=fill_side,
            slippage_model=str(slip["slippage_model"]),
            random_seed=slip["random_seed"],
            commission_zar=commission,
            conversion_rate=rate,
            conversion_source=source,
        )
