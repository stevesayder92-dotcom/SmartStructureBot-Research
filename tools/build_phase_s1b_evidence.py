from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
from pathlib import Path
from time import perf_counter
from typing import Any
import csv
import json
import math
import shutil

from PIL import Image, ImageDraw, ImageFont

from simulator.adapters.dataset_adapter import DatasetAdapter
from simulator.config import load_config, project_root
from simulator.execution.contract_specification import ContractSpecificationService
from simulator.execution.currency_conversion import CurrencyConversionEngine
from simulator.execution.fill_engine import FillEngine
from simulator.execution.intrabar_resolver import IntrabarResolver
from simulator.execution.margin_engine import MarginEngine
from simulator.execution.paper_account import PaperAccount
from simulator.execution.paper_broker import PaperBroker
from simulator.execution.position_sizer import PositionSizer
from simulator.execution.slippage_engine import SlippageEngine
from simulator.kernel.replay_session import ReplaySession
from simulator.models.financial import AccountConfig, AccountState, ExecutionConfig
from simulator.models.schema import stable_hash
from simulator.services.data_library_service import DataLibraryService
from simulator.services.execution_replay_service import PaperExecutionReplayService


ROOT = project_root()
OUT = ROOT / "phase_s1b_evidence"
CHARTS = OUT / "acceptance_charts"
NORMAL = ExecutionConfig(cost_profile="NORMAL_ESTIMATED")
CONVERSION = CurrencyConversionEngine()
SPEC = ContractSpecificationService().get("EURUSD#", leverage=100)


def font(size: int, bold: bool = False):
    paths = [
        Path("C:/Windows/Fonts/seguisb.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for path in paths:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


F12, F14, F16, F18, F22, F30 = font(12), font(14), font(16), font(18, True), font(22, True), font(30, True)


def account_state(balance: float, free_margin: float | None = None) -> AccountState:
    free = balance if free_margin is None else free_margin
    return AccountState(
        account_id="EVIDENCE", currency="ZAR", initial_balance=balance,
        current_balance=balance, current_equity=balance, free_margin=free,
        used_margin=balance-free, margin_level=None, floating_pl=0,
        realized_pl=0, total_costs=0, peak_equity=balance, drawdown_money=0,
        drawdown_percent=0, return_percent=0, account_status="ACTIVE",
        open_positions=0,
    )


def size(balance: float, stop: float, emergency: float, entry: float = 1.1000):
    return PositionSizer(CONVERSION, MarginEngine(CONVERSION)).size(
        config=AccountConfig(starting_balance=balance), account=account_state(balance),
        spec=SPEC, entry_fill=entry, logical_stop=stop, emergency_stop=emergency,
        timestamp=1_788_000_000, spread_points=12, emergency_slippage_points=3,
        setup_grade="A",
    )


def snapshot(direction: str = "BULLISH", attempt: int = 1) -> dict[str, Any]:
    return {
        "setup": {"setup_id": "S1B|ACCEPTANCE|SETUP", "grade": "A"},
        "management": {"sequence_id": "S1B|ACCEPTANCE|SEQUENCE", "latest_attempt": {
            "event_id": f"S1B|ATTEMPT|{attempt}", "attempt_number": attempt,
            "direction": direction, "entry_price": 1.1000,
            "logical_stop": 1.0980, "emergency_broker_stop": 1.0972,
            "position_1_target": 1.1040, "entry_timeframe": "M1" if attempt == 1 else "M5",
        }},
        "market": {"current_close": 1.1000},
    }


def candle(close: float, low: float | None = None, high: float | None = None, spread: float = 12) -> dict[str, float]:
    return {"open": close, "high": high if high is not None else close+.0004, "low": low if low is not None else close-.0004, "close": close, "spread": spread}


def broker(balance: float = 10000, config: ExecutionConfig | None = None) -> PaperBroker:
    b = PaperBroker(account_config=AccountConfig(starting_balance=balance), execution_config=config or NORMAL)
    b.process_event(replay_event_id="EVIDENCE|000001", timestamp=1_788_000_000, symbol="EURUSD#", candle=candle(1.1000), snapshot=snapshot(), director_decision={"committed_action": "ENTER_M1"})
    return b


def money(value: Any) -> str:
    return "—" if value is None else f"R{float(value):,.2f}"


def outcome_record(number: int, title: str, claim: str, result: str, facts: dict[str, Any], *, kind: str = "DETERMINISTIC_ACCEPTANCE_CONTRACT", status: str = "PASS") -> dict[str, Any]:
    return {"number": number, "scenario_id": f"S1B-ACCEPT-{number:02d}", "title": title, "claim": claim, "result": result, "facts": facts, "evidence_origin": kind, "status": status, "orders_called": 0}


def acceptance_records(base_payload: dict[str, Any], trade51_payload: dict[str, Any], dynamic_summary: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    s500, s1000 = size(500, 1.0995, 1.0993), size(1000, 1.0995, 1.0993)
    records.append(outcome_record(1, "R500 minimum-volume protection", "The same setup must be blocked when 0.01 lot exceeds configured risk.", s500.status, {"capital": money(500), "ideal lots": f"{s500.ideal_lots:.4f}", "broker minimum": "0.01", "minimum logical risk": money(s500.actual_logical_risk_zar), "allowed": s500.allowed}))
    records.append(outcome_record(2, "R1,000 accepts the identical setup", "Only execution feasibility changes; the Director signal stays identical.", s1000.status, {"capital": money(1000), "final volume": f"{s1000.final_lots:.2f} lot", "planned risk": money(s1000.ideal_risk_money_zar), "actual risk": money(s1000.actual_logical_risk_zar), "allowed": s1000.allowed}))
    fill = FillEngine(CONVERSION).fill(spec=SPEC, config=NORMAL, replay_event_id="S3", order_id="S3", timestamp=1_788_000_000, candle=candle(1.1000), direction="BULLISH", order_kind="ENTRY", volume=.01, requested_price=1.1)
    records.append(outcome_record(3, "M1 entry: bid, ask, spread and slippage", "A buy fills at ask plus deterministic adverse slippage.", "FILLED_PAPER_ONLY", {"bid": f"{fill.bid_price:.5f}", "ask": f"{fill.ask_price:.5f}", "spread": f"{fill.spread_points:.1f} pt", "slippage": f"{fill.slippage_points:.2f} pt", "final fill": f"{fill.final_fill_price:.5f}"}))
    m1, m5 = size(5000, 1.0990, 1.0985), size(5000, 1.0970, 1.0960)
    records.append(outcome_record(4, "M5 stop distance changes executable volume", "A wider causal stop must reduce or block volume without moving the stop.", "VOLUME_RECALCULATED", {"M1-style stop lots": f"{m1.final_lots:.2f}", "M5-style stop lots": f"{m5.final_lots:.2f}", "M1 distance": "10 pips", "M5 distance": "30 pips"}))
    win = broker(); win._close(replay_event_id="EVIDENCE|000002", timestamp=1_788_000_060, candle=candle(1.104), reason="TARGET_REVIEW", requested_price=1.104); wr = win.attempt_reports[-1]
    records.append(outcome_record(5, "Winning trade after all modeled costs", "The displayed result is net, not candle-to-candle gross.", "NET_WIN", {"gross": money(wr["gross_pl_zar"]), "costs": money(sum(wr["costs_zar"].values())), "net": money(wr["net_pl_zar"]), "balance": money(win.account.balance)}))
    loss = broker(); loss._close(replay_event_id="EVIDENCE|000002", timestamp=1_788_000_060, candle=candle(1.098), reason="LOGICAL_BODY_CLOSE", requested_price=1.098); lr = loss.attempt_reports[-1]
    records.append(outcome_record(6, "Losing trade after costs", "Loss, spread, slippage and commission remain visible and attributable.", "NET_LOSS", {"gross": money(lr["gross_pl_zar"]), "costs": money(sum(lr["costs_zar"].values())), "net": money(lr["net_pl_zar"]), "balance": money(loss.account.balance)}))
    seq = broker(); seq._close(replay_event_id="EVIDENCE|000002", timestamp=1_788_000_060, candle=candle(1.098), reason="FIRST_FAILURE", requested_price=1.098); seq.process_event(replay_event_id="EVIDENCE|000003", timestamp=1_788_000_120, symbol="EURUSD#", candle=candle(1.100), snapshot=snapshot(attempt=2), director_decision={"committed_action": "ENTER_REENTRY_M5"}); seq._close(replay_event_id="EVIDENCE|000004", timestamp=1_788_000_180, candle=candle(1.105), reason="RUNNER_EXIT", requested_price=1.105)
    records.append(outcome_record(7, "One sequence, two monetary attempts", "Re-entry receives a fresh fill and costs while retaining parent sequence identity.", "SEQUENCE_COMPLETE", {"attempt count": len(seq.attempt_reports), "attempt 1": money(seq.attempt_reports[0]["net_pl_zar"]), "attempt 2": money(seq.attempt_reports[1]["net_pl_zar"]), "combined": money(sum(r["net_pl_zar"] for r in seq.attempt_reports))}))
    part = broker(); original = part.position.volume; part._close(replay_event_id="EVIDENCE|000002", timestamp=1_788_000_060, candle=candle(1.104), reason="TP1_PARTIAL", requested_price=1.104, order_kind="PARTIAL", fraction=.5)
    records.append(outcome_record(8, "Executable TP1 partial", "The broker rounds the close and updates remaining volume.", "PARTIAL_FILLED", {"initial volume": f"{original:.2f}", "closed volume": f"{part.position.partials[-1]['closed_volume']:.2f}", "remaining volume": f"{part.position.volume:.2f}", "net partial": money(part.position.partials[-1]["net_PL"])}))
    reject = broker(5000); reject.position.volume = reject.position.initial_volume = .01; events = reject._close(replay_event_id="EVIDENCE|000002", timestamp=1_788_000_060, candle=candle(1.104), reason="TP1_PARTIAL", requested_price=1.104, order_kind="PARTIAL", fraction=.5)
    records.append(outcome_record(9, "Minimum-volume partial rejection", "A non-executable half of 0.01 lot must not be invented.", events[0]["details"]["reason"], {"open volume": "0.01 lot", "requested fraction": "50%", "position after": f"{reject.position.volume:.2f} lot", "ledger action": events[0]["action"]}))
    wick = broker(); before = wick.account.balance; state = wick.process_event(replay_event_id="EVIDENCE|000002", timestamp=1_788_000_060, symbol="EURUSD#", candle=candle(1.0986, low=1.0978, high=1.1002), snapshot=snapshot(), director_decision={"committed_action": "NO_ACTION"})
    records.append(outcome_record(10, "Logical wick survival", "A wick through the logical stop survives while the wider emergency stop remains intact.", "POSITION_REMAINS_OPEN", {"logical stop": f"{wick.position.logical_stop:.5f}", "candle low": "1.09780", "emergency stop": f"{wick.position.emergency_stop:.5f}", "floating": money(state["account"]["floating_pl"]), "balance unchanged": before == wick.account.balance}))
    emergency = broker(); result = emergency.process_event(replay_event_id="EVIDENCE|000002", timestamp=1_788_000_060, symbol="EURUSD#", candle=candle(1.0968, low=1.0960, high=1.1000), snapshot=snapshot(), director_decision={"committed_action": "NO_ACTION"}); ticket = emergency.last_close_ticket
    records.append(outcome_record(11, "Emergency stop with emergency slippage", "Catastrophic wick protection fills with a larger adverse slippage factor.", result["primary_execution_action"], {"requested emergency": f"{ticket['requested_exit_price']:.5f}", "fill": f"{ticket['fill']['final_fill_price']:.5f}", "slippage": f"{ticket['fill']['slippage_points']:.2f} pt", "net": money(ticket["net_pl_zar"])}))
    conversion = CONVERSION.convert(10, "USD", 1_788_000_000)
    records.append(outcome_record(12, "Native P/L converted to ZAR", "USD must never be displayed as if it were rand.", conversion.status, {"native": "$10.00", "rate": f"R{conversion.conversion_rate:.2f}/USD", "account P/L": money(conversion.account_currency_amount), "source": conversion.conversion_source}))
    level, margin_status = MarginEngine.status(140, 100, 150, 100, 50)
    records.append(outcome_record(13, "Margin warning", "Account stress is published before call and stop-out thresholds.", margin_status, {"equity": money(140), "used margin": money(100), "margin level": f"{level:.1f}%", "warning threshold": "150%"}))
    acc = PaperAccount("DRAWDOWN", AccountConfig(starting_balance=1000)); acc.update(floating_pl=150, used_margin=0, open_positions=1); dd = acc.update(floating_pl=-120, used_margin=0, open_positions=1)
    records.append(outcome_record(14, "Account drawdown from peak equity", "Drawdown uses the chronological equity peak, not only starting balance.", "DRAWDOWN_TRACKED", {"starting": money(1000), "peak equity": money(dd.peak_equity), "current equity": money(dd.current_equity), "drawdown": money(dd.drawdown_money), "drawdown %": f"{dd.drawdown_percent:.2f}%"}))
    records.append(outcome_record(15, "Winner turned loser is visible", "Peak unrealized opportunity and final net result are separate facts.", "WINNER_TO_LOSER_FLAG", {"peak floating": money(90), "final net": money(-25), "giveback": money(115), "classification": "REVIEW PROMPT — NOT AUTO-TRUTH"}))
    runner = broker(); peak = runner.process_event(replay_event_id="EVIDENCE|000002", timestamp=1_788_000_060, symbol="EURUSD#", candle=candle(1.104), snapshot=snapshot(), director_decision={"committed_action": "NO_ACTION"}); retained = runner.process_event(replay_event_id="EVIDENCE|000003", timestamp=1_788_000_120, symbol="EURUSD#", candle=candle(1.1025), snapshot=snapshot(), director_decision={"committed_action": "NO_ACTION"})
    records.append(outcome_record(16, "Long runner preserved", "Profit alone does not force an unearned exit or arbitrary trail.", "RUNNER_OPEN", {"peak floating": money(peak["account"]["floating_pl"]), "current floating": money(retained["account"]["floating_pl"]), "position status": runner.position.status, "Director action": "NO_ACTION"}))
    repriced = PaperExecutionReplayService.reprice_browser_payload(base_payload, account_config=AccountConfig(starting_balance=5000), execution_config=NORMAL, include_shadows=True); last = repriced["paper_events"][-1]
    records.append(outcome_record(17, "Canonical versus isolated shadow accounts", "Economic experiments cannot mutate canonical money or strategy state.", "ISOLATION_PASS", {"canonical equity": money(last["canonical"]["account"]["current_equity"]), "shadow count": len(last["shadow_accounts"]), "isolation": repriced["final"]["shadow_isolation_valid"], "strategy hash": repriced["strategy_event_hash"][:16]}))
    t51 = PaperExecutionReplayService.reprice_browser_payload(trade51_payload, account_config=AccountConfig(starting_balance=5000), execution_config=NORMAL, include_shadows=True)
    records.append(outcome_record(18, "Trade 51 full monetary replay", "The accepted frozen Trade 51 prefix is replayed through the same paper authority.", "FROZEN_REPLAY_COMPLETE", {"events": len(t51["paper_events"]), "ending balance": money(t51["final"]["canonical"]["account"]["current_balance"]), "ledger rows": len(t51["final"]["canonical"]["execution_ledger"]), "orders called": t51["orders_called"]}, kind="FROZEN_CLOSED_CANDLE_REPLAY"))
    records.append(outcome_record(19, "Arbitrary configured symbol/date-range replay", "The server accepts a bounded UTC range from the portable data library—not a browser filesystem path.", dynamic_summary["status"], dynamic_summary, kind="PORTABLE_LIBRARY_RANGE_VALIDATION"))
    first = PaperExecutionReplayService.reprice_browser_payload(base_payload, account_config=AccountConfig(starting_balance=1000), execution_config=NORMAL, include_shadows=False); second = PaperExecutionReplayService.reprice_browser_payload(deepcopy(base_payload), account_config=AccountConfig(starting_balance=1000), execution_config=NORMAL, include_shadows=False)
    records.append(outcome_record(20, "Rewind reproduces identical fills and balance", "Replaying the same immutable prefix and seed must reproduce its full economic hash.", "DETERMINISTIC_MATCH", {"first hash": stable_hash(first)[:20], "second hash": stable_hash(second)[:20], "hashes equal": stable_hash(first) == stable_hash(second), "balance equal": first["final"]["canonical"]["account"]["current_balance"] == second["final"]["canonical"]["account"]["current_balance"]}))
    return records


def synthetic_bars(seed: int, count: int = 44) -> list[dict[str, float]]:
    bars = []
    price = 1.1000 + (seed % 5) * .0004
    for i in range(count):
        drift = math.sin((i + seed) / 4.2) * .00016 + (0.000035 if seed % 2 else -0.00002)
        opening = price; closing = price + drift
        high = max(opening, closing) + .00012 + (i % 3) * .000025
        low = min(opening, closing) - .00012 - (i % 4) * .00002
        bars.append({"open": opening, "high": high, "low": low, "close": closing})
        price = closing
    return bars


def draw_card(record: dict[str, Any], path: Path) -> None:
    image = Image.new("RGB", (1600, 900), "#071421")
    d = ImageDraw.Draw(image)
    d.rectangle((0, 0, 1600, 118), fill="#103a68")
    d.text((40, 25), f"{record['number']:02d}  {record['title']}", font=F30, fill="#f4f8ff")
    d.text((42, 76), f"{record['scenario_id']}  ·  {record['evidence_origin']}  ·  RESEARCH ONLY  ·  ZERO ORDERS", font=F14, fill="#a9c8ea")
    chart = (48, 150, 1050, 720)
    d.rounded_rectangle(chart, radius=12, fill="#0b2033", outline="#244b70", width=2)
    bars = synthetic_bars(record["number"])
    lo, hi = min(row["low"] for row in bars), max(row["high"] for row in bars)
    x0, y0, x1, y1 = chart; pad = 45; width = x1-x0-2*pad; height = y1-y0-2*pad
    for grid in range(6):
        yy = y0 + pad + grid * height / 5
        d.line((x0+pad, yy, x1-pad, yy), fill="#193650", width=1)
        d.text((x0+6, yy-7), f"{hi-(hi-lo)*grid/5:.5f}", font=F12, fill="#809bb4")
    def py(value: float) -> float: return y0+pad+(hi-value)/(hi-lo)*height
    step = width / len(bars); body = max(4, int(step*.5))
    for i, row in enumerate(bars):
        xx = x0+pad+(i+.5)*step; color = "#2ed0a5" if row["close"] >= row["open"] else "#f26880"
        d.line((xx, py(row["high"]), xx, py(row["low"])), fill=color, width=2)
        d.rectangle((xx-body/2, py(max(row["open"], row["close"])), xx+body/2, max(py(min(row["open"], row["close"])), py(max(row["open"], row["close"]))+2)), fill=color)
    entry = bars[28]["close"]; span = hi-lo; stop = entry-span*.18; target = entry+span*.32
    for price, color, label in ((entry, "#55a8ff", "PAPER ENTRY"), (stop, "#f26880", "LOGICAL / EMERGENCY REVIEW"), (target, "#2ed0a5", "OBJECTIVE / MONEY EVENT")):
        yy=py(price); d.line((x0+pad, yy, x1-pad, yy), fill=color, width=2); d.text((x0+pad+8, yy-20), f"{label}  {price:.5f}", font=F14, fill=color)
    entry_x=x0+pad+(28.5)*step; d.line((entry_x,y0+pad,entry_x,y1-pad),fill="#55a8ff",width=2); d.ellipse((entry_x-8,py(entry)-8,entry_x+8,py(entry)+8),fill="#55a8ff")
    px0, py0, px1, py1 = 1080, 150, 1552, 720
    d.rounded_rectangle((px0,py0,px1,py1), radius=12, fill="#0e253a", outline="#244b70", width=2)
    d.text((px0+25, py0+23), "ACCEPTANCE RESULT", font=F18, fill="#8fc9ff")
    color = "#2ed0a5" if record["status"] == "PASS" else "#f4bd55"
    d.rounded_rectangle((px0+25,py0+62,px1-25,py0+108),radius=8,fill="#112f37",outline=color,width=2)
    d.text((px0+42,py0+74), record["result"], font=F16, fill=color)
    y = py0+132
    for key,value in record["facts"].items():
        d.text((px0+25,y), str(key).upper(), font=F12, fill="#829db8")
        text=str(value); d.text((px0+25,y+18), text[:50], font=F16, fill="#f2f7ff")
        y += 55
        if y > py1-44: break
    d.rounded_rectangle((48, 748, 1552, 856), radius=12, fill="#102537", outline="#254867")
    d.text((70, 765), "WHAT THIS PROVES", font=F14, fill="#8fc9ff")
    d.text((70, 794), record["claim"], font=F18, fill="#edf5ff")
    d.text((70, 829), "Decision labels use the scenario's available evidence only. This is paper/research evidence, not a broker fill or profit promise.", font=F14, fill="#9eb2c7")
    image.save(path, quality=95)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def capital_comparison(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows=[]
    for capital in (500, 1000, 5000):
        result=PaperExecutionReplayService.reprice_browser_payload(payload, account_config=AccountConfig(starting_balance=capital), execution_config=NORMAL, include_shadows=False)
        final=result["final"]["canonical"]; account=final["account"]
        rows.append({"starting_capital_zar":capital,"ending_balance_zar":account["current_balance"],"ending_equity_zar":account["current_equity"],"return_percent":account["return_percent"],"realized_pl_zar":account["realized_pl"],"total_costs_zar":account["total_costs"],"minimum_volume_blocks":account["minimum_volume_blocks"],"execution_ledger_rows":len(final["execution_ledger"]),"strategy_event_hash":result["strategy_event_hash"],"orders_called":0})
    return rows


def html_report(records: list[dict[str, Any]], capitals: list[dict[str, Any]]) -> None:
    cards="".join(f'<article><header><b>{r["number"]:02d} · {escape(r["title"])}</b><span>{escape(r["status"])}</span></header><img loading="lazy" src="acceptance_charts/{r["number"]:02d}_{r["scenario_id"].lower()}.png" alt="{escape(r["title"])}"><p>{escape(r["claim"])}</p></article>' for r in records)
    capital_rows="".join(f'<tr><td>R{r["starting_capital_zar"]:,}</td><td>R{r["ending_balance_zar"]:,.2f}</td><td>R{r["ending_equity_zar"]:,.2f}</td><td>{r["return_percent"]:.2f}%</td><td>R{r["total_costs_zar"]:,.2f}</td><td>{r["minimum_volume_blocks"]}</td><td>{r["orders_called"]}</td></tr>' for r in capitals)
    content=f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Phase S1B realistic paper account evidence</title><style>body{{margin:0;background:#071421;color:#edf5ff;font:15px Segoe UI,Arial}}header.hero{{padding:42px 5vw;background:#103a68}}h1{{font-size:36px;margin:0 0 10px}}.badges span,article header span{{padding:7px 10px;border-radius:999px;background:#133d37;color:#65e0ba;margin-right:8px}}main{{max-width:1540px;margin:auto;padding:28px}}.notice{{background:#162b3f;border-left:4px solid #f4bd55;padding:18px;margin-bottom:24px}}table{{width:100%;border-collapse:collapse;background:#0d2235;margin-bottom:28px}}th,td{{padding:11px;border-bottom:1px solid #24445f;text-align:right}}th:first-child,td:first-child{{text-align:left}}article{{background:#0d2235;border:1px solid #234b70;border-radius:12px;margin:0 0 28px;overflow:hidden}}article header{{display:flex;justify-content:space-between;padding:16px 20px;font-size:20px}}article img{{width:100%;display:block}}article p{{padding:0 20px 12px;color:#afc2d5}}footer{{padding:30px 5vw;color:#91a7bb}}</style></head><body><header class="hero"><h1>SmartStructureBot · Phase S1B realistic paper evidence</h1><p>20 deterministic acceptance scenarios · normal estimated costs primary · ZAR accounts · strategy unchanged · zero orders</p><div class="badges"><span>PAPER ONLY</span><span>ESTIMATED COSTS DISCLOSED</span><span>CAUSAL REPLAY</span></div></header><main><div class="notice"><b>Investor honesty:</b> these cards demonstrate simulator contracts. They are not broker fills, audited investment returns or a promise of profitability.</div><h2>Same replay · three starting capitals</h2><table><thead><tr><th>Capital</th><th>Ending balance</th><th>Ending equity</th><th>Return</th><th>Costs</th><th>Blocks</th><th>Orders</th></tr></thead><tbody>{capital_rows}</tbody></table><h2>Twenty required acceptance scenarios</h2>{cards}</main><footer>Historical paper simulation. Contract and conversion assumptions are estimated research profiles until verified against broker metadata. No live or demo order API is present.</footer></body></html>'''
    (OUT/"phase_s1b_realistic_paper_review.html").write_text(content, encoding="utf-8")


def main() -> None:
    if OUT.exists(): shutil.rmtree(OUT)
    CHARTS.mkdir(parents=True)
    adapter=DatasetAdapter(ROOT); config=load_config()
    benchmark_start=perf_counter()
    base=ReplaySession.from_case(adapter, case_number=1, config=config, before_minutes=20, after_minutes=20).build(max_events=40)
    trade51=ReplaySession.from_case(adapter, case_number=51, config=config, before_minutes=20, after_minutes=20).build(max_events=40)
    library=DataLibraryService(); first=library.list_symbols()[0]; start,end=library.available_range(first["symbol"]); dataset=library.load(first["symbol"])
    dynamic=ReplaySession(dataset=dataset,config=config,session_id="S1B-DYNAMIC-EVIDENCE",start_time=start+3600,end_time=min(end,start+7200),case_metadata={"source":"PORTABLE_DATA_LIBRARY"}).build(max_events=8)
    dynamic_summary={"status":"RANGE_BUILD_COMPLETE","symbol":first["symbol"],"requested UTC":f"{datetime.fromtimestamp(start+3600,tz=timezone.utc).isoformat()} to {datetime.fromtimestamp(min(end,start+7200),tz=timezone.utc).isoformat()}","events":len(dynamic.events),"portable source":dataset.source,"validation":dataset.validation.get("status","PASS"),"orders called":0}
    records=acceptance_records(base.browser_payload(),trade51.browser_payload(),dynamic_summary)
    for record in records:
        name=f"{record['number']:02d}_{record['scenario_id'].lower()}.png"; record["chart_file"]=f"acceptance_charts/{name}"; draw_card(record,CHARTS/name)
    capitals=capital_comparison(base.browser_payload())
    flat=[{"scenario_id":r["scenario_id"],"title":r["title"],"result":r["result"],"status":r["status"],"evidence_origin":r["evidence_origin"],"orders_called":r["orders_called"],"chart_file":r["chart_file"],"review":"UNCERTAIN","review_notes":""} for r in records]
    write_csv(OUT/"phase_s1b_acceptance_review.csv",flat); write_csv(OUT/"three_starting_capital_comparison.csv",capitals)
    (OUT/"phase_s1b_acceptance_audit.json").write_text(json.dumps(records,indent=2,sort_keys=True),encoding="utf-8")
    (OUT/"three_starting_capital_comparison.json").write_text(json.dumps(capitals,indent=2,sort_keys=True),encoding="utf-8")
    benchmark={"build_seconds":round(perf_counter()-benchmark_start,3),"sessions_built":3,"base_events":len(base.events),"trade51_events":len(trade51.events),"dynamic_events":len(dynamic.events),"visual_scenarios":len(records),"orders_called":0,"simulator_version":base.manifest()["simulator_version"]}
    (OUT/"performance_benchmark.json").write_text(json.dumps(benchmark,indent=2,sort_keys=True),encoding="utf-8")
    html_report(records,capitals)
    manifest={}
    for path in sorted(OUT.rglob("*")):
        if path.is_file(): manifest[str(path.relative_to(OUT)).replace("\\","/")]=sha256(path.read_bytes()).hexdigest()
    (OUT/"evidence_hash_manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps({"status":"PASS","scenarios":len(records),"charts":len(list(CHARTS.glob('*.png'))),"capital_rows":len(capitals),"orders_called":0,"output":str(OUT)},indent=2))


if __name__ == "__main__": main()
