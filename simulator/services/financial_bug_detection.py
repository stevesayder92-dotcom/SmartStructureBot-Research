from __future__ import annotations

from typing import Any

from simulator.models.schema import BugFlag


FINANCIAL_BUG_CATALOG = (
    "RISK_EXCEEDS_CONFIG",
    "EMERGENCY_RISK_EXCEEDS_CAP",
    "INSUFFICIENT_MARGIN",
    "MINIMUM_VOLUME_TOO_LARGE",
    "SPREAD_ABNORMALLY_HIGH",
    "SLIPPAGE_ABNORMALLY_HIGH",
    "PARTIAL_NOT_EXECUTABLE",
    "COSTS_ERASED_EDGE",
    "ACCOUNT_STOP_OUT",
    "CURRENCY_CONVERSION_MISSING",
    "REENTRY_COST_EXCEEDS_EDGE",
    "SECOND_ATTEMPT_OVER_RISK",
)


def financial_bug_flags(event_id: str, paper: dict[str, Any]) -> list[BugFlag]:
    canonical = paper.get("canonical") or {}
    account = canonical.get("account") or {}
    position = canonical.get("active_position") or {}
    config = canonical.get("account_config") or {}
    market = canonical.get("market_price") or {}
    ticket = canonical.get("last_ticket") or {}
    close = canonical.get("last_close_ticket") or {}
    events = canonical.get("execution_events") or []
    flags: list[BugFlag] = []

    def add(title: str, evidence: dict[str, Any], *, severity: str = "REVIEW", engine: str = "PaperExecutionEngine") -> None:
        flags.append(BugFlag(
            bug_flag_id=f"{event_id}|{title}",
            event_id=event_id,
            severity=severity,
            category="FINANCIAL",
            title=title,
            evidence=evidence,
            affected_engine=engine,
            director_action="UNCHANGED_STRATEGY_ACTION",
            suggested_review_question="Is this economic constraint or cost assumption acceptable for the research profile?",
        ))

    if position:
        balance = max(1e-12, float(account.get("current_balance", 0.0)))
        logical_pct = float(position.get("actual_logical_risk_zar", 0.0)) / balance * 100.0
        emergency_pct = float(position.get("actual_emergency_risk_zar", 0.0)) / balance * 100.0
        if logical_pct > float(config.get("maximum_account_risk_percent", 100.0)) + 1e-9:
            add("RISK_EXCEEDS_CONFIG", {"actual_percent": logical_pct, "cap_percent": config.get("maximum_account_risk_percent")}, severity="WARNING", engine="PositionSizer")
        if emergency_pct > float(config.get("maximum_emergency_risk_percent", 100.0)) + 1e-9:
            add("EMERGENCY_RISK_EXCEEDS_CAP", {"actual_percent": emergency_pct, "cap_percent": config.get("maximum_emergency_risk_percent")}, severity="WARNING", engine="PositionSizer")
        if int(position.get("attempt_number", 1)) == 2 and logical_pct > float(config.get("maximum_account_risk_percent", 100.0)) + 1e-9:
            add("SECOND_ATTEMPT_OVER_RISK", {"actual_percent": logical_pct}, severity="WARNING", engine="PositionSizer")
    reasons = [str((event.get("details") or {}).get("reason")) for event in events if event.get("action") == "PAPER_ORDER_REJECTED"]
    if "INSUFFICIENT_MARGIN" in reasons:
        add("INSUFFICIENT_MARGIN", {"rejection_reasons": reasons}, engine="MarginEngine")
    if "MINIMUM_VOLUME_OVER_RISK" in reasons:
        add("MINIMUM_VOLUME_TOO_LARGE", {"rejection_reasons": reasons}, engine="PositionSizer")
    if str(market.get("spread_state")) in {"HIGH", "ROLLOVER_EXTREME"}:
        add("SPREAD_ABNORMALLY_HIGH", {"spread_points": market.get("spread_points"), "state": market.get("spread_state"), "source": market.get("spread_source")}, engine="SpreadEngine")
    fill = ticket.get("fill") or {}
    contract = ticket.get("contract") or {}
    if float(fill.get("slippage_points", 0.0) or 0.0) > float(contract.get("base_spread_points", 1.0) or 1.0) * 0.5:
        add("SLIPPAGE_ABNORMALLY_HIGH", {"slippage_points": fill.get("slippage_points"), "base_spread_points": contract.get("base_spread_points")}, engine="SlippageEngine")
    if any(event.get("action") == "PARTIAL_REJECTED" for event in events):
        add("PARTIAL_NOT_EXECUTABLE", {"events": [event for event in events if event.get("action") == "PARTIAL_REJECTED"]}, engine="PaperBroker")
    if close and float(close.get("gross_pl_zar", 0.0) or 0.0) > 0 and float(close.get("net_pl_zar", 0.0) or 0.0) <= 0:
        add("COSTS_ERASED_EDGE", {"gross_zar": close.get("gross_pl_zar"), "costs": close.get("costs_zar"), "net_zar": close.get("net_pl_zar")})
    if account.get("account_status") == "STOP_OUT" or any(event.get("action") == "STOP_OUT" for event in events):
        add("ACCOUNT_STOP_OUT", {"account": account}, severity="WARNING", engine="MarginEngine")
    if (ticket.get("fill") or {}).get("conversion_source") == "MISSING_RATE":
        add("CURRENCY_CONVERSION_MISSING", {"fill": ticket.get("fill")}, severity="WARNING", engine="CurrencyConversionEngine")
    return flags
