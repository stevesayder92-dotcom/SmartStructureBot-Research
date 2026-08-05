from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from simulator.execution.contract_specification import ContractSpecificationService
from simulator.execution.currency_conversion import CurrencyConversionEngine
from simulator.execution.execution_ledger import ExecutionLedger
from simulator.execution.fill_engine import FillEngine
from simulator.execution.margin_engine import MarginEngine
from simulator.execution.paper_account import PaperAccount
from simulator.execution.position_sizer import PositionSizer
from simulator.execution.spread_engine import SpreadEngine
from simulator.execution.swap_engine import SwapEngine
from simulator.models.financial import (
    AccountConfig,
    ExecutionConfig,
    PaperOrderRequest,
    PositionState,
)
from simulator.models.schema import json_safe, stable_hash


ENTRY_ACTIONS = {"ENTER_M1", "ENTER_M5", "ENTER_REENTRY_M1", "ENTER_REENTRY_M5"}


class PaperBroker:
    """Deterministic historical broker consuming Director actions only."""

    def __init__(
        self,
        *,
        account_id: str = "PAPER-ZAR-001",
        account_config: AccountConfig | None = None,
        execution_config: ExecutionConfig | None = None,
        contract_service: ContractSpecificationService | None = None,
    ) -> None:
        self.account_config = account_config or AccountConfig()
        self.execution_config = execution_config or ExecutionConfig()
        self.account = PaperAccount(account_id, self.account_config)
        self.contracts = contract_service or ContractSpecificationService()
        self.conversion = CurrencyConversionEngine()
        self.margin = MarginEngine(self.conversion)
        self.sizer = PositionSizer(self.conversion, self.margin)
        self.fill_engine = FillEngine(self.conversion)
        self.spread_engine = SpreadEngine()
        self.swap_engine = SwapEngine(self.conversion)
        self.ledger = ExecutionLedger()
        self.position: PositionState | None = None
        self.pending_order: dict[str, Any] | None = None
        self.equity_history: list[dict[str, Any]] = []
        self.money_story: list[dict[str, Any]] = []
        self.attempt_reports: list[dict[str, Any]] = []
        self.last_ticket: dict[str, Any] | None = None
        self.last_close_ticket: dict[str, Any] | None = None
        self.last_market: dict[str, Any] = {}
        self.last_margin_status = "HEALTHY"
        self.last_rollover_date: str | None = None
        self._event_sequence = 0
        self._last_replay_event = ""

    def _account_state(self) -> dict[str, Any]:
        floating = self._floating_from_last_market()
        used = self.position.margin_used_zar if self.position and self.position.status == "OPEN" else 0.0
        return self.account.update(floating_pl=floating, used_margin=used, open_positions=1 if self.position and self.position.status == "OPEN" else 0).payload()

    def _emit(
        self,
        *,
        replay_event_id: str,
        timestamp: float,
        action: str,
        symbol: str,
        volume: float = 0.0,
        requested_price: float | None = None,
        fill_price: float | None = None,
        costs: dict[str, float] | None = None,
        gross_pl: float = 0.0,
        net_pl: float = 0.0,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._event_sequence += 1
        state = self._account_state()
        position = self.position
        event = self.ledger.append(
            execution_event_id=f"{self.account.account_id}|EXEC|{self._event_sequence:06d}",
            replay_event_id=replay_event_id,
            timestamp=float(timestamp),
            account_id=self.account.account_id,
            setup_id=position.setup_id if position else (details or {}).get("setup_id"),
            sequence_id=position.sequence_id if position else (details or {}).get("sequence_id"),
            attempt_id=position.attempt_id if position else (details or {}).get("attempt_id"),
            symbol=symbol,
            action=action,
            volume=float(volume),
            requested_price=requested_price,
            fill_price=fill_price,
            costs=costs or {},
            gross_pl=float(gross_pl),
            net_pl=float(net_pl),
            balance_after=float(state["current_balance"]),
            equity_after=float(state["current_equity"]),
            margin_after=float(state["used_margin"]),
            causal_valid=True,
            details=json_safe(details or {}),
        )
        return event.payload()

    @staticmethod
    def _attempt(snapshot: dict[str, Any]) -> dict[str, Any]:
        management = snapshot.get("management") or {}
        return dict(management.get("active_attempt") or management.get("latest_attempt") or snapshot.get("entry") or {})

    def _spec(self, symbol: str):
        return self.contracts.get(symbol, leverage=self.account_config.leverage)

    def _price_value_zar(self, symbol: str, price_distance: float, volume: float, timestamp: float) -> float:
        spec = self._spec(symbol)
        converted = self.conversion.convert(abs(price_distance) / spec.tick_size * spec.tick_value * volume, spec.quote_currency, timestamp)
        if converted.account_currency_amount is None:
            raise ValueError(f"Missing conversion rate for {spec.quote_currency}")
        return converted.account_currency_amount

    def _directional_pl(self, position: PositionState, start: float, end: float, volume: float, timestamp: float) -> float:
        sign = 1.0 if position.direction == "BULLISH" else -1.0
        value = self._price_value_zar(position.symbol, end - start, volume, timestamp)
        return value * (1.0 if sign * (end - start) >= 0 else -1.0)

    def _market_prices(self, symbol: str, timestamp: float, candle: dict[str, Any], volatility_ratio: float) -> dict[str, Any]:
        spec = self._spec(symbol)
        spread = self.spread_engine.calculate(spec=spec, config=self.execution_config, timestamp=timestamp, candle=candle, volatility_ratio=volatility_ratio)
        chart = float(candle.get("close", 0.0))
        bid = float(candle.get("bid_close", chart))
        ask = float(candle.get("ask_close", bid + spread["spread_price"]))
        return {"chart_price": chart, "bid_price": bid, "ask_price": ask, **spread, "timestamp": timestamp}

    def _floating_from_last_market(self) -> float:
        p = self.position
        if not p or p.status != "OPEN" or not self.last_market:
            return 0.0
        mark = float(self.last_market["bid_price"] if p.direction == "BULLISH" else self.last_market["ask_price"])
        raw = self._directional_pl(p, p.entry_fill_price, mark, p.volume, float(self.last_market["timestamp"]))
        try:
            closing_commission = self.fill_engine.commission.charge(
                spec=self._spec(p.symbol), config=self.execution_config, volume=p.volume, price=mark,
                timestamp=float(self.last_market["timestamp"]), side="CLOSE",
            )
        except ValueError:
            closing_commission = 0.0
        return raw - closing_commission

    def _money_story(self, timestamp: float, title: str, description: str, amount: float | None = None) -> None:
        self.money_story.append({"timestamp": float(timestamp), "title": title, "description": description, "amount_zar": amount})

    def _entry_payload(self, snapshot: dict[str, Any], direction_hint: str | None = None) -> dict[str, Any]:
        attempt = self._attempt(snapshot)
        entry = snapshot.get("entry") or {}
        setup = snapshot.get("setup") or {}
        direction = str(attempt.get("direction") or entry.get("direction") or entry.get("parent_direction") or direction_hint or "BULLISH")
        price = attempt.get("entry_price") or entry.get("price") or (snapshot.get("market") or {}).get("current_close")
        logical = attempt.get("logical_stop") or entry.get("logical_stop") or entry.get("stop_level")
        emergency = attempt.get("emergency_broker_stop") or entry.get("emergency_broker_stop")
        if emergency is None and price is not None and logical is not None:
            distance = abs(float(price) - float(logical))
            emergency = float(price) - distance * 1.35 if direction == "BULLISH" else float(price) + distance * 1.35
        return {
            "direction": direction,
            "price": float(price),
            "logical_stop": float(logical),
            "emergency_stop": float(emergency),
            "target_1": attempt.get("position_1_target") or entry.get("position_1_target") or entry.get("target"),
            "target_2": attempt.get("position_2_target"),
            "entry_timeframe": str(attempt.get("timeframe") or attempt.get("entry_timeframe") or (snapshot.get("identity") or {}).get("entry_owner") or "M5"),
            "attempt_number": int(attempt.get("attempt_number") or 1),
            "attempt_id": str(attempt.get("event_id") or f"ATTEMPT-{int(attempt.get('attempt_number') or 1)}"),
            "setup_id": setup.get("setup_id") or entry.get("setup_id"),
            "sequence_id": (snapshot.get("management") or {}).get("sequence_id") or setup.get("setup_id"),
            "grade": setup.get("grade") or setup.get("setup_grade") or "A",
        }

    def _open(
        self,
        *,
        replay_event_id: str,
        timestamp: float,
        symbol: str,
        candle: dict[str, Any],
        snapshot: dict[str, Any],
        strategy_action: str,
        volatility_ratio: float,
    ) -> list[dict[str, Any]]:
        created: list[dict[str, Any]] = []
        details = self._entry_payload(snapshot)
        order_id = f"{self.account.account_id}|ORDER|{replay_event_id}"
        request = PaperOrderRequest(
            order_id=order_id,
            replay_event_id=replay_event_id,
            timestamp=timestamp,
            account_id=self.account.account_id,
            setup_id=details["setup_id"],
            sequence_id=details["sequence_id"],
            attempt_id=details["attempt_id"],
            symbol=symbol,
            direction=details["direction"],
            action="MARKET_ENTRY_ON_BOS_CLOSE",
            requested_volume=0.0,
            requested_price=details["price"],
            logical_stop=details["logical_stop"],
            emergency_stop=details["emergency_stop"],
            target_1=details["target_1"],
            target_2=details["target_2"],
            entry_timeframe=details["entry_timeframe"],
            strategy_signal=strategy_action,
        )
        created.append(self._emit(replay_event_id=replay_event_id, timestamp=timestamp, action="PAPER_ORDER_REQUESTED", symbol=symbol, requested_price=request.requested_price, details={**request.payload(), **details}))
        if self.position and self.position.status == "OPEN":
            created.append(self._emit(replay_event_id=replay_event_id, timestamp=timestamp, action="PAPER_ORDER_REJECTED", symbol=symbol, requested_price=request.requested_price, details={"reason": "MAXIMUM_CONCURRENT_POSITIONS", **details}))
            return created
        if self.account.status in {"STOP_OUT", "ACCOUNT_DEPLETED"}:
            created.append(self._emit(replay_event_id=replay_event_id, timestamp=timestamp, action="PAPER_ORDER_REJECTED", symbol=symbol, requested_price=request.requested_price, details={"reason": self.account.status, **details}))
            return created
        spec = self._spec(symbol)
        trial = self.fill_engine.fill(spec=spec, config=self.execution_config, replay_event_id=replay_event_id, order_id=order_id, timestamp=timestamp, candle=candle, direction=details["direction"], order_kind="ENTRY", volume=1.0, requested_price=request.requested_price, volatility_ratio=volatility_ratio)
        account_state = self._account_state()
        from simulator.models.financial import AccountState
        sizing = self.sizer.size(
            config=self.account_config,
            account=AccountState(**account_state),
            spec=spec,
            entry_fill=trial.final_fill_price,
            logical_stop=request.logical_stop,
            emergency_stop=request.emergency_stop,
            timestamp=timestamp,
            spread_points=trial.spread_points,
            emergency_slippage_points=self.fill_engine.slippage.calculate(spec=spec, config=self.execution_config, replay_event_id=replay_event_id, order_id=order_id, order_kind="EMERGENCY_STOP")["slippage_points"],
            setup_grade=details["grade"],
        )
        if not sizing.allowed:
            if sizing.status == "MINIMUM_VOLUME_OVER_RISK":
                self.account.minimum_volume_blocks += 1
            ticket = {"status": "ORDER_BLOCKED", "reason": sizing.status, "request": request.payload(), "sizing": sizing.payload(), "contract": spec.payload(), "paper_only": True}
            self.last_ticket = ticket
            created.append(self._emit(replay_event_id=replay_event_id, timestamp=timestamp, action="PAPER_ORDER_REJECTED", symbol=symbol, requested_price=request.requested_price, details=ticket))
            self._money_story(timestamp, "ORDER BLOCKED", sizing.sizing_reason)
            return created
        fill = self.fill_engine.fill(spec=spec, config=self.execution_config, replay_event_id=replay_event_id, order_id=order_id, timestamp=timestamp, candle=candle, direction=details["direction"], order_kind="ENTRY", volume=sizing.final_lots, requested_price=request.requested_price, volatility_ratio=volatility_ratio)
        spread_cost = self._price_value_zar(symbol, fill.ask_price - fill.bid_price, sizing.final_lots, timestamp)
        self.account.apply_balance_change(-fill.commission_zar)
        self.account.add_cost(spread_cost + fill.slippage_money_zar + fill.commission_zar)
        self.position = PositionState(
            position_id=f"{self.account.account_id}|POSITION|{replay_event_id}",
            account_id=self.account.account_id,
            setup_id=details["setup_id"],
            sequence_id=details["sequence_id"],
            attempt_id=details["attempt_id"],
            attempt_number=details["attempt_number"],
            symbol=symbol,
            direction=details["direction"],
            entry_timeframe=details["entry_timeframe"],
            opened_at=timestamp,
            requested_volume=sizing.ideal_lots,
            volume=sizing.final_lots,
            initial_volume=sizing.final_lots,
            entry_reference_price=request.requested_price,
            entry_fill_price=fill.final_fill_price,
            logical_stop=request.logical_stop,
            emergency_stop=request.emergency_stop,
            current_protection=request.logical_stop,
            target_1=request.target_1,
            target_2=request.target_2,
            opening_commission_zar=fill.commission_zar,
            opening_spread_cost_zar=spread_cost,
            opening_slippage_cost_zar=fill.slippage_money_zar,
            margin_used_zar=sizing.margin_required_zar,
            planned_risk_zar=sizing.ideal_risk_money_zar,
            actual_logical_risk_zar=sizing.actual_logical_risk_zar,
            actual_emergency_risk_zar=sizing.actual_emergency_risk_zar,
            commission_zar=fill.commission_zar,
        )
        ticket = {
            "status": "FILLED — PAPER ONLY",
            "strategy_signal": strategy_action,
            "request": request.payload(),
            "fill": fill.payload(),
            "sizing": sizing.payload(),
            "contract": spec.payload(),
            "account_balance": self.account.balance,
            "paper_only": True,
        }
        self.last_ticket = ticket
        created.append(self._emit(replay_event_id=replay_event_id, timestamp=timestamp, action="PAPER_ORDER_FILLED", symbol=symbol, volume=sizing.final_lots, requested_price=request.requested_price, fill_price=fill.final_fill_price, costs={"spread": spread_cost, "slippage": fill.slippage_money_zar, "commission": fill.commission_zar}, details=ticket))
        created.append(self._emit(replay_event_id=replay_event_id, timestamp=timestamp, action="POSITION_OPENED", symbol=symbol, volume=sizing.final_lots, requested_price=request.requested_price, fill_price=fill.final_fill_price, details={"position": self.position.payload()}))
        if fill.commission_zar:
            created.append(self._emit(replay_event_id=replay_event_id, timestamp=timestamp, action="COMMISSION_CHARGED", symbol=symbol, volume=sizing.final_lots, fill_price=fill.final_fill_price, costs={"commission": fill.commission_zar}, net_pl=-fill.commission_zar))
        self._money_story(timestamp, "PAPER POSITION OPENED", f"{details['direction']} {sizing.final_lots:.2f} lot filled at {fill.final_fill_price:.5f}; planned risk R{sizing.ideal_risk_money_zar:.2f}.")
        return created

    def _close(
        self,
        *,
        replay_event_id: str,
        timestamp: float,
        candle: dict[str, Any],
        reason: str,
        requested_price: float,
        order_kind: str = "EXIT",
        fraction: float = 1.0,
        volatility_ratio: float = 1.0,
    ) -> list[dict[str, Any]]:
        p = self.position
        if not p or p.status != "OPEN":
            return []
        spec = self._spec(p.symbol)
        close_volume = min(p.volume, p.volume * fraction)
        if fraction < 1.0:
            close_volume = int((close_volume + 1e-12) / spec.volume_step) * spec.volume_step
            remaining = p.volume - close_volume
            if close_volume < spec.volume_minimum or (remaining > 1e-12 and remaining < spec.volume_minimum):
                event = self._emit(replay_event_id=replay_event_id, timestamp=timestamp, action="PARTIAL_REJECTED", symbol=p.symbol, volume=close_volume, requested_price=requested_price, details={"reason": "PARTIAL_NOT_EXECUTABLE_MINIMUM_VOLUME", "requested_fraction": fraction, "remaining_volume": remaining})
                self._money_story(timestamp, "PARTIAL REJECTED", "The broker volume step would leave a position below minimum volume.")
                return [event]
        order_id = f"{self.account.account_id}|CLOSE|{replay_event_id}|{len(p.partials)}"
        fill = self.fill_engine.fill(spec=spec, config=self.execution_config, replay_event_id=replay_event_id, order_id=order_id, timestamp=timestamp, candle={**candle, "close": requested_price}, direction=p.direction, order_kind=order_kind, volume=close_volume, requested_price=requested_price, volatility_ratio=volatility_ratio)
        actual_pl = self._directional_pl(p, p.entry_fill_price, fill.final_fill_price, close_volume, timestamp)
        reference_pl = self._directional_pl(p, p.entry_reference_price, requested_price, close_volume, timestamp)
        allocated_open_commission = p.opening_commission_zar * close_volume / p.initial_volume
        allocated_open_spread = p.opening_spread_cost_zar * close_volume / p.initial_volume
        allocated_open_slippage = p.opening_slippage_cost_zar * close_volume / p.initial_volume
        exit_spread = self._price_value_zar(p.symbol, abs(fill.market_reference_price - fill.spread_adjusted_price), close_volume, timestamp)
        costs = {
            "spread": allocated_open_spread + exit_spread,
            "slippage": allocated_open_slippage + fill.slippage_money_zar,
            "commission": allocated_open_commission + fill.commission_zar,
            "swap": p.swap_zar * close_volume / p.initial_volume,
        }
        total_cost = sum(costs.values())
        net_attempt = reference_pl - total_cost
        balance_change = actual_pl - fill.commission_zar
        self.account.apply_balance_change(balance_change)
        self.account.add_cost(exit_spread + fill.slippage_money_zar + fill.commission_zar)
        p.realized_zar += balance_change
        p.commission_zar += fill.commission_zar
        p.volume -= close_volume
        p.margin_used_zar *= max(0.0, p.volume / max(1e-12, p.volume + close_volume))
        partial = {
            "requested_fraction": fraction,
            "executable_fraction": close_volume / max(1e-12, close_volume + p.volume),
            "closed_volume": close_volume,
            "remaining_volume": p.volume,
            "fill_price": fill.final_fill_price,
            "gross_PL": reference_pl,
            "costs": costs,
            "net_PL": net_attempt,
            "reason": reason,
        }
        p.partials.append(partial)
        action = "PARTIAL_FILLED" if p.volume > 1e-12 else "POSITION_CLOSED"
        if p.volume <= 1e-12:
            p.volume = 0.0
            p.status = "CLOSED"
            p.closed_at = timestamp
            p.exit_reason = reason
            p.exit_fill_price = fill.final_fill_price
            self.attempt_reports.append({"position": p.payload(), "gross_pl_zar": reference_pl, "costs_zar": costs, "net_pl_zar": net_attempt})
        ticket = {
            "status": action,
            "reason": reason,
            "requested_exit_price": requested_price,
            "fill": fill.payload(),
            "closed_volume": close_volume,
            "remaining_volume": p.volume,
            "gross_pl_zar": reference_pl,
            "costs_zar": costs,
            "net_pl_zar": net_attempt,
            "balance_after": self.account.balance,
            "paper_only": True,
        }
        self.last_close_ticket = ticket
        event = self._emit(replay_event_id=replay_event_id, timestamp=timestamp, action=action, symbol=p.symbol, volume=close_volume, requested_price=requested_price, fill_price=fill.final_fill_price, costs=costs, gross_pl=reference_pl, net_pl=net_attempt, details=ticket)
        self._money_story(timestamp, action.replace("_", " "), f"{reason.replace('_', ' ').title()}: net result R{net_attempt:.2f} after R{total_cost:.2f} attributed costs.", net_attempt)
        return [event]

    def _maybe_swap(self, replay_event_id: str, timestamp: float) -> list[dict[str, Any]]:
        p = self.position
        if not p or p.status != "OPEN" or self.execution_config.swap_model == "DISABLED":
            return []
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        date_key = dt.date().isoformat()
        if dt.hour < 21 or self.last_rollover_date == date_key:
            return []
        self.last_rollover_date = date_key
        result = self.swap_engine.charge(
            spec=self._spec(p.symbol), config=self.execution_config,
            timestamp=timestamp, volume=p.volume,
        )
        if result["status"] == "MISSING_CONVERSION_RATE":
            return []
        charge = float(result["charge_zar"])
        self.account.apply_balance_change(-charge)
        self.account.add_cost(charge)
        p.swap_zar += charge
        return [self._emit(replay_event_id=replay_event_id, timestamp=timestamp, action="SWAP_CHARGED", symbol=p.symbol, volume=p.volume, costs={"swap": charge}, net_pl=-charge, details={"model": self.execution_config.swap_model, "triple_swap": bool(result["triple_swap"])})]

    def process_event(
        self,
        *,
        replay_event_id: str,
        timestamp: float,
        symbol: str,
        candle: dict[str, Any],
        snapshot: dict[str, Any],
        director_decision: dict[str, Any],
        volatility_ratio: float = 1.0,
    ) -> dict[str, Any]:
        self._last_replay_event = replay_event_id
        start_ledger = len(self.ledger.events)
        primary_action = "NO_EXECUTION_ACTION"
        action = str(director_decision.get("committed_action") or "NO_ACTION")
        self.last_market = self._market_prices(symbol, timestamp, candle, volatility_ratio)

        if self.pending_order and not self.position:
            pending = self.pending_order
            self.pending_order = None
            self._open(replay_event_id=replay_event_id, timestamp=timestamp, symbol=symbol, candle={**candle, "close": float(candle.get("open", candle.get("close")))}, snapshot=pending["snapshot"], strategy_action=pending["action"], volatility_ratio=volatility_ratio)
            primary_action = "PAPER_ENTRY_FILLED_NEXT_OPEN"

        p = self.position
        if p and p.status == "OPEN":
            spread_price = float(self.last_market["spread_price"])
            low = float(candle.get("low", self.last_market["chart_price"]))
            high = float(candle.get("high", self.last_market["chart_price"]))
            emergency_touched = low <= p.emergency_stop if p.direction == "BULLISH" else high + spread_price >= p.emergency_stop
            if emergency_touched:
                self._close(replay_event_id=replay_event_id, timestamp=timestamp, candle=candle, reason="EMERGENCY_STOP", requested_price=p.emergency_stop, order_kind="EMERGENCY_STOP", volatility_ratio=volatility_ratio)
                primary_action = "EMERGENCY_STOP_EXIT"

        p = self.position
        if p and p.status == "OPEN" and primary_action == "NO_EXECUTION_ACTION":
            if action.startswith("MOVE_TO") and director_decision.get("new_protection") is not None:
                proposed = float(director_decision["new_protection"])
                improves = proposed > p.current_protection if p.direction == "BULLISH" else proposed < p.current_protection
                if improves:
                    p.current_protection = proposed
                    p.logical_stop = proposed
                    self._emit(replay_event_id=replay_event_id, timestamp=timestamp, action="LOGICAL_STOP_UPDATED", symbol=symbol, volume=p.volume, requested_price=proposed, details={"owner": "SystemStateDirector", "new_logical_stop": proposed})
                    primary_action = "LOGICAL_STOP_UPDATED"
            elif action == "TAKE_PARTIAL":
                self._emit(replay_event_id=replay_event_id, timestamp=timestamp, action="PARTIAL_REQUESTED", symbol=symbol, volume=p.volume, requested_price=float(director_decision.get("price") or candle.get("close")), details={"fraction": self.execution_config.partial_fraction})
                self._close(replay_event_id=replay_event_id, timestamp=timestamp, candle=candle, reason="TP1_PARTIAL", requested_price=float(director_decision.get("price") or candle.get("close")), order_kind="PARTIAL", fraction=self.execution_config.partial_fraction, volatility_ratio=volatility_ratio)
                primary_action = "PARTIAL_CLOSE"
            elif action.startswith("EXIT"):
                self._close(replay_event_id=replay_event_id, timestamp=timestamp, candle=candle, reason=str(director_decision.get("exit_reason") or action), requested_price=float(director_decision.get("price") or candle.get("close")), order_kind="EXIT", volatility_ratio=volatility_ratio)
                primary_action = "FULL_CLOSE"

        if action in ENTRY_ACTIONS and (not self.position or self.position.status != "OPEN"):
            if self.execution_config.execution_timing_model == "NEXT_CANDLE_OPEN_PLUS_COSTS":
                self.pending_order = {"snapshot": json_safe(snapshot), "action": action}
                primary_action = "PAPER_ENTRY_QUEUED_NEXT_OPEN"
            else:
                self._open(replay_event_id=replay_event_id, timestamp=timestamp, symbol=symbol, candle=candle, snapshot=snapshot, strategy_action=action, volatility_ratio=volatility_ratio)
                primary_action = "PAPER_ENTRY_REQUEST"

        self._maybe_swap(replay_event_id, timestamp)
        state = self._account_state()
        p = self.position
        if p and p.status == "OPEN":
            risk = max(1e-12, p.actual_logical_risk_zar)
            current_r = float(state["floating_pl"]) / risk
            p.peak_unrealized_zar = max(p.peak_unrealized_zar, float(state["floating_pl"]))
            p.peak_r = max(p.peak_r, current_r)
        margin_status = str(state["account_status"])
        if margin_status in {"LOW_MARGIN_WARNING", "MARGIN_CALL"} and margin_status != self.last_margin_status:
            self.account.margin_warnings += 1
            self._emit(replay_event_id=replay_event_id, timestamp=timestamp, action="MARGIN_WARNING" if margin_status == "LOW_MARGIN_WARNING" else "MARGIN_CALL", symbol=symbol, details={"margin_level": state["margin_level"]})
        if margin_status == "STOP_OUT" and p and p.status == "OPEN":
            self.account.stop_outs += 1
            self._close(replay_event_id=replay_event_id, timestamp=timestamp, candle=candle, reason="MARGIN_STOP_OUT", requested_price=float(candle.get("close")), order_kind="EMERGENCY_STOP", volatility_ratio=volatility_ratio)
            self._emit(replay_event_id=replay_event_id, timestamp=timestamp, action="STOP_OUT", symbol=symbol, details={"margin_level": state["margin_level"]})
            primary_action = "MARGIN_STOP_OUT"
            state = self._account_state()
        self.last_margin_status = margin_status
        equity_point = {
            "replay_event_id": replay_event_id,
            "event_number": int(replay_event_id.rsplit("|", 1)[-1]) if replay_event_id.rsplit("|", 1)[-1].isdigit() else len(self.equity_history),
            "timestamp": timestamp,
            "balance": state["current_balance"],
            "equity": state["current_equity"],
            "peak_equity": state["peak_equity"],
            "drawdown_money": state["drawdown_money"],
            "drawdown_percent": state["drawdown_percent"],
        }
        self.equity_history.append(equity_point)
        new_events = [event.payload() for event in self.ledger.events[start_ledger:]]
        current_position = self.position.payload() if self.position and self.position.status == "OPEN" else None
        payload = {
            "paper_only": True,
            "orders_enabled": False,
            "account": state,
            "active_position": current_position,
            "last_ticket": self.last_ticket,
            "last_close_ticket": self.last_close_ticket,
            "market_price": self.last_market,
            "primary_execution_action": primary_action,
            "execution_events": new_events,
            "execution_event_count": len(self.ledger.events),
            "execution_ledger_hash": self.ledger.last_hash,
            "equity_point": equity_point,
            "money_story_events": list(self.money_story[-40:]),
            "cost_attribution": self.cost_attribution(),
            "execution_config": self.execution_config.payload(),
            "account_config": self.account_config.payload(),
            "contract_specification": self._spec(symbol).payload(),
            "swap_status": "SWAP NOT MODELLED" if self.execution_config.swap_model == "DISABLED" else self.execution_config.swap_model,
            "causal_valid": True,
        }
        payload["state_hash"] = stable_hash(payload)
        return json_safe(payload)

    def cost_attribution(self) -> dict[str, Any]:
        events = self.ledger.payload()
        spread = sum(float(e.get("costs", {}).get("spread", 0.0)) for e in events if e["action"] in {"PAPER_ORDER_FILLED", "POSITION_CLOSED", "PARTIAL_FILLED"})
        slippage = sum(float(e.get("costs", {}).get("slippage", 0.0)) for e in events if e["action"] in {"PAPER_ORDER_FILLED", "POSITION_CLOSED", "PARTIAL_FILLED"})
        commission = sum(float(e.get("costs", {}).get("commission", 0.0)) for e in events if e["action"] == "COMMISSION_CHARGED")
        swap = sum(float(e.get("costs", {}).get("swap", 0.0)) for e in events if e["action"] == "SWAP_CHARGED")
        return {"spread_zar": spread, "slippage_zar": slippage, "commission_zar": commission, "swap_zar": swap, "total_costs_zar": self.account.total_costs}

    def final_payload(self) -> dict[str, Any]:
        return {
            "account": self._account_state(),
            "execution_ledger": self.ledger.payload(),
            "equity_history": json_safe(self.equity_history),
            "attempt_reports": json_safe(self.attempt_reports),
            "cost_attribution": self.cost_attribution(),
            "money_story": json_safe(self.money_story),
            "orders_called": 0,
        }
