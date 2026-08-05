from __future__ import annotations

from typing import Any

from simulator.analytics.cost_attribution import aggregate_costs
from simulator.analytics.drawdown import drawdown_series
from simulator.analytics.risk_metrics import risk_summary
from simulator.analytics.sequence_money_metrics import sequence_totals
from simulator.analytics.session_performance import by_session
from simulator.analytics.symbol_performance import by_symbol


class AccountMetrics:
    @staticmethod
    def calculate(final_payload: dict[str, Any]) -> dict[str, Any]:
        account = final_payload.get("account") or {}
        attempts = list(final_payload.get("attempt_reports") or [])
        ledger = list(final_payload.get("execution_ledger") or [])
        nets = [float(row.get("net_pl_zar", 0.0)) for row in attempts]
        wins = [value for value in nets if value > 0]
        losses = [value for value in nets if value < 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        drawdowns = drawdown_series(list(final_payload.get("equity_history") or []))
        return {
            "starting_capital_zar": account.get("initial_balance", 0.0),
            "ending_balance_zar": account.get("current_balance", 0.0),
            "ending_equity_zar": account.get("current_equity", 0.0),
            "total_net_profit_zar": account.get("realized_pl", 0.0),
            "return_percent": account.get("return_percent", 0.0),
            "maximum_drawdown_zar": max((row["drawdown_money"] for row in drawdowns), default=0.0),
            "maximum_drawdown_percent": max((row["drawdown_percent"] for row in drawdowns), default=0.0),
            "largest_win_zar": max(wins, default=0.0),
            "largest_loss_zar": min(losses, default=0.0),
            "average_win_zar": sum(wins) / len(wins) if wins else 0.0,
            "average_loss_zar": sum(losses) / len(losses) if losses else 0.0,
            "expectancy_zar": sum(nets) / len(nets) if nets else 0.0,
            "profit_factor": gross_profit / gross_loss if gross_loss > 0 else None,
            "execution_attempt_win_rate": len(wins) / len(nets) * 100.0 if nets else 0.0,
            "sample_size": len(nets),
            "costs": aggregate_costs(ledger),
            "risk": risk_summary(attempts),
            "sequences": sequence_totals(attempts),
            "by_symbol": by_symbol(attempts),
            "by_session": by_session(attempts),
            "margin_call_count": sum(1 for event in ledger if event.get("action") == "MARGIN_CALL"),
            "stop_out_count": sum(1 for event in ledger if event.get("action") == "STOP_OUT"),
            "minimum_volume_blocks": account.get("minimum_volume_blocks", 0),
            "performance_is_not_guaranteed": True,
        }
