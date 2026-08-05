from __future__ import annotations

from copy import deepcopy
from typing import Any

from simulator.execution.paper_broker import PaperBroker
from simulator.models.financial import AccountConfig, ExecutionConfig
from simulator.models.schema import json_safe, stable_hash


SHADOW_PROFILES = (
    "PURE_STRUCTURE_RUNNER",
    "TP1_PARTIAL_PLUS_RUNNER",
    "EARNED_OPPORTUNITY_MANAGER",
    "M5_CONFIRMATION_REENTRY",
    "M1_RESET_REENTRY",
    "PROTECT_WINNER_FROM_LOSS",
)


class PaperExecutionReplayService:
    """Runs canonical and isolated shadow money accounts over one event clock."""

    def __init__(
        self,
        *,
        account_config: AccountConfig | None = None,
        execution_config: ExecutionConfig | None = None,
        shadow_profiles: tuple[str, ...] = SHADOW_PROFILES,
    ) -> None:
        self.account_config = account_config or AccountConfig()
        self.execution_config = execution_config or ExecutionConfig()
        self.canonical = PaperBroker(account_id="CANONICAL-PAPER-ZAR", account_config=self.account_config, execution_config=self.execution_config)
        self.shadows = {
            name: PaperBroker(account_id=f"SHADOW-{name}", account_config=self.account_config, execution_config=self.execution_config)
            for name in shadow_profiles
        }

    @staticmethod
    def _shadow_decision(
        profile: str,
        canonical: dict[str, Any],
        broker: PaperBroker,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        decision = deepcopy(canonical)
        action = str(decision.get("committed_action") or "NO_ACTION")
        diagnostics = snapshot.get("management_diagnostics") or {}
        position = broker.position
        if profile == "PURE_STRUCTURE_RUNNER" and action == "EXIT_LOGICAL":
            decision["committed_action"] = "NO_ACTION"
        elif profile == "TP1_PARTIAL_PLUS_RUNNER" and position and position.status == "OPEN":
            latest = (snapshot.get("management") or {}).get("latest_attempt") or {}
            if latest.get("tp1_triggered") and not position.partials:
                decision["committed_action"] = "TAKE_PARTIAL"
                decision["price"] = latest.get("position_1_target") or (snapshot.get("market") or {}).get("current_close")
        elif profile == "EARNED_OPPORTUNITY_MANAGER" and position and position.status == "OPEN":
            if diagnostics.get("earned_opportunity") in {"EARNED", "SIGNIFICANT"} and position.peak_r >= 1.0:
                decision["committed_action"] = "MOVE_TO_SHADOW_EARNED_PROTECTION"
                decision["new_protection"] = position.entry_fill_price
        elif profile == "PROTECT_WINNER_FROM_LOSS" and position and position.status == "OPEN":
            current_r = broker.account.floating_pl / max(1e-12, position.actual_logical_risk_zar)
            if position.peak_r >= 0.5 and current_r <= 0.05:
                decision["committed_action"] = "EXIT_SHADOW_PROTECT_WINNER"
                decision["exit_reason"] = "SHADOW_PROTECT_WINNER_FROM_LOSS"
                decision["price"] = (snapshot.get("market") or {}).get("current_close")
        return decision

    def process(
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
        canonical = self.canonical.process_event(
            replay_event_id=replay_event_id,
            timestamp=timestamp,
            symbol=symbol,
            candle=candle,
            snapshot=snapshot,
            director_decision=director_decision,
            volatility_ratio=volatility_ratio,
        )
        shadows = []
        for name, broker in self.shadows.items():
            shadow_decision = self._shadow_decision(name, director_decision, broker, snapshot)
            paper = broker.process_event(
                replay_event_id=replay_event_id,
                timestamp=timestamp,
                symbol=symbol,
                candle=candle,
                snapshot=snapshot,
                director_decision=shadow_decision,
                volatility_ratio=volatility_ratio,
            )
            shadows.append({
                "profile": name,
                "account": paper["account"],
                "active_position": paper["active_position"],
                "primary_execution_action": paper["primary_execution_action"],
                "difference_from_canonical_zar": paper["account"]["current_equity"] - canonical["account"]["current_equity"],
                "causal_valid": True,
                "isolated_state_hash": paper["state_hash"],
            })
        result = {"canonical": canonical, "shadow_accounts": shadows, "shadow_isolation_valid": True}
        result["state_hash"] = stable_hash(result)
        return json_safe(result)

    def final_payload(self) -> dict[str, Any]:
        canonical = self.canonical.final_payload()
        return {
            "canonical": canonical,
            "shadows": {name: broker.final_payload() for name, broker in self.shadows.items()},
            "shadow_isolation_valid": True,
            "orders_called": 0,
        }

    @classmethod
    def reprice_browser_payload(
        cls,
        payload: dict[str, Any],
        *,
        account_config: AccountConfig,
        execution_config: ExecutionConfig,
        include_shadows: bool = True,
    ) -> dict[str, Any]:
        service = cls(account_config=account_config, execution_config=execution_config, shadow_profiles=SHADOW_PROFILES if include_shadows else ())
        m1 = {int(row["index"]): row for row in payload["candles"]["M1"]}
        m5 = {int(row["index"]): row for row in payload["candles"]["M5"]}
        paper_events = []
        recent_ranges: list[float] = []
        for event in payload["events"]:
            indices = list(event.get("newly_closed_m1_indices") or [])
            candle = m1.get(int(indices[-1])) if indices else None
            if candle is None:
                indices = list(event.get("newly_closed_m5_indices") or [])
                candle = m5.get(int(indices[-1])) if indices else None
            if candle is None:
                visible = int(event.get("visible_m1_rows", 0)) - 1
                candle = m1.get(visible) or m5.get(int(event.get("visible_m5_rows", 0)) - 1)
            if candle is None:
                continue
            candle_range = abs(float(candle["high"]) - float(candle["low"]))
            baseline = sum(recent_ranges[-14:]) / len(recent_ranges[-14:]) if recent_ranges[-14:] else candle_range or 1.0
            volatility = candle_range / baseline if baseline > 0 else 1.0
            recent_ranges.append(candle_range)
            paper = service.process(
                replay_event_id=event["replay_event_id"],
                timestamp=float(event["event_time"]),
                symbol=payload["manifest"]["symbol"],
                candle=candle,
                snapshot=event["snapshot"],
                director_decision=event["director_decision"],
                volatility_ratio=volatility,
            )
            paper_events.append({"event_number": event["event_number"], **paper})
        return {
            "account_config": account_config.payload(),
            "execution_config": execution_config.payload(),
            "paper_events": paper_events,
            "final": service.final_payload(),
            "strategy_event_hash": stable_hash([event["director_decision"] for event in payload["events"]]),
            "orders_called": 0,
        }
