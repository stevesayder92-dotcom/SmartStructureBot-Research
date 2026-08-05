from __future__ import annotations

from simulator.execution.margin_engine import MarginEngine
from simulator.models.financial import AccountConfig, AccountState


class PaperAccount:
    def __init__(self, account_id: str, config: AccountConfig):
        self.account_id = account_id
        self.config = config
        self.balance = float(config.starting_balance)
        self.equity = float(config.starting_balance)
        self.floating_pl = 0.0
        self.used_margin = 0.0
        self.realized_pl = 0.0
        self.total_costs = 0.0
        self.peak_equity = float(config.starting_balance)
        self.drawdown_money = 0.0
        self.drawdown_percent = 0.0
        self.status = "ACTIVE"
        self.minimum_volume_blocks = 0
        self.margin_warnings = 0
        self.stop_outs = 0

    def apply_balance_change(self, amount: float) -> None:
        self.balance += float(amount)
        self.realized_pl = self.balance - self.config.starting_balance

    def add_cost(self, amount: float) -> None:
        self.total_costs += max(0.0, float(amount))

    def update(self, *, floating_pl: float, used_margin: float, open_positions: int) -> AccountState:
        self.floating_pl = float(floating_pl)
        self.used_margin = max(0.0, float(used_margin))
        self.equity = self.balance + self.floating_pl
        self.peak_equity = max(self.peak_equity, self.equity)
        self.drawdown_money = max(0.0, self.peak_equity - self.equity)
        self.drawdown_percent = self.drawdown_money / self.peak_equity * 100.0 if self.peak_equity > 0 else 0.0
        margin_level, margin_status = MarginEngine.status(
            self.equity,
            self.used_margin,
            self.config.margin_warning_level,
            self.config.margin_call_level,
            self.config.stop_out_level,
        )
        if self.equity <= 0 or self.balance <= 0:
            self.status = "ACCOUNT_DEPLETED"
        elif margin_status != "HEALTHY":
            self.status = margin_status
        elif self.status not in {"SIMULATION_COMPLETE"}:
            self.status = "ACTIVE"
        free_margin = self.equity - self.used_margin
        return AccountState(
            account_id=self.account_id,
            currency=self.config.account_currency,
            initial_balance=self.config.starting_balance,
            current_balance=self.balance,
            current_equity=self.equity,
            free_margin=free_margin,
            used_margin=self.used_margin,
            margin_level=margin_level,
            floating_pl=self.floating_pl,
            realized_pl=self.realized_pl,
            total_costs=self.total_costs,
            peak_equity=self.peak_equity,
            drawdown_money=self.drawdown_money,
            drawdown_percent=self.drawdown_percent,
            return_percent=(self.equity - self.config.starting_balance) / self.config.starting_balance * 100.0,
            account_status=self.status,
            open_positions=open_positions,
            minimum_volume_blocks=self.minimum_volume_blocks,
            margin_warnings=self.margin_warnings,
            stop_outs=self.stop_outs,
        )

    def state(self, *, open_positions: int = 0) -> AccountState:
        return self.update(floating_pl=self.floating_pl, used_margin=self.used_margin, open_positions=open_positions)
