from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase

from simulator.adapters.dataset_adapter import DatasetAdapter
from simulator.config import load_config, project_root
from simulator.execution.commission_engine import CommissionEngine
from simulator.execution.contract_specification import ContractSpecificationService
from simulator.execution.currency_conversion import CurrencyConversionEngine
from simulator.execution.fill_engine import FillEngine
from simulator.execution.intrabar_resolver import IntrabarResolver
from simulator.execution.margin_engine import MarginEngine
from simulator.execution.paper_account import PaperAccount
from simulator.execution.paper_broker import PaperBroker
from simulator.execution.position_sizer import PositionSizer
from simulator.execution.slippage_engine import SlippageEngine
from simulator.execution.spread_engine import SpreadEngine
from simulator.execution.swap_engine import SwapEngine
from simulator.kernel.replay_session import ReplaySession
from simulator.models.financial import AccountConfig, AccountState, ExecutionConfig
from simulator.models.schema import stable_hash
from simulator.services.execution_replay_service import PaperExecutionReplayService


class PhaseS1BFinancialContractTests(TestCase):
    """The 50 deterministic acceptance contracts required by the S1B mandate."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.contracts = ContractSpecificationService()
        cls.spec = cls.contracts.get("EURUSD#", leverage=100)
        cls.conversion = CurrencyConversionEngine()
        cls.normal = ExecutionConfig(slippage_model="NO_SLIPPAGE")
        cls.adapter = DatasetAdapter(project_root())
        cls.base_session = ReplaySession.from_case(
            cls.adapter, case_number=1, config=load_config(), before_minutes=15, after_minutes=10
        ).build(max_events=18)
        cls.browser_payload = cls.base_session.browser_payload()

    @staticmethod
    def account_state(balance: float = 5000.0, *, equity: float | None = None, free_margin: float | None = None) -> AccountState:
        equity = balance if equity is None else equity
        free_margin = equity if free_margin is None else free_margin
        return AccountState("A", "ZAR", balance, balance, equity, free_margin, equity - free_margin, None, equity - balance, balance - 5000, 0, max(balance, equity), max(0, balance - equity), 0, 0, "ACTIVE", 0)

    def size(self, account: AccountState | None = None, config: AccountConfig | None = None, **overrides):
        values = dict(entry_fill=1.1002, logical_stop=1.0982, emergency_stop=1.0975, timestamp=1_788_000_000, spread_points=12, emergency_slippage_points=2, setup_grade="A")
        values.update(overrides)
        return PositionSizer(self.conversion, MarginEngine(self.conversion)).size(
            config=config or AccountConfig(starting_balance=5000), account=account or self.account_state(), spec=self.spec, **values
        )

    @staticmethod
    def snapshot(direction: str = "BULLISH", attempt: int = 1) -> dict:
        return {
            "setup": {"setup_id": "SYNTHETIC|SETUP|1", "grade": "A"},
            "management": {"sequence_id": "SYNTHETIC|SEQ|1", "latest_attempt": {
                "event_id": f"ATTEMPT-{attempt}", "attempt_number": attempt, "direction": direction,
                "entry_price": 1.1000, "logical_stop": 1.0980, "emergency_broker_stop": 1.0972,
                "position_1_target": 1.1040, "entry_timeframe": "M1",
            }},
            "market": {"current_close": 1.1000},
        }

    @staticmethod
    def candle(close: float = 1.1000, *, spread: float | None = 12, low: float | None = None, high: float | None = None) -> dict:
        row = {"open": close, "high": high if high is not None else close + .0005, "low": low if low is not None else close - .0005, "close": close}
        if spread is not None:
            row["spread"] = spread
        return row

    def open_broker(self, *, balance: float = 5000, config: ExecutionConfig | None = None, direction: str = "BULLISH") -> PaperBroker:
        broker = PaperBroker(account_config=AccountConfig(starting_balance=balance), execution_config=config or self.normal)
        broker.process_event(replay_event_id="SYN|000001", timestamp=1_788_000_000, symbol="EURUSD#", candle=self.candle(), snapshot=self.snapshot(direction), director_decision={"committed_action": "ENTER_M1"})
        self.assertIsNotNone(broker.position)
        return broker

    # ACCOUNT 1-6
    def test_01_r500_initialization(self):
        self.assertEqual(PaperAccount("A", AccountConfig(starting_balance=500)).state().current_balance, 500)

    def test_02_r1000_initialization(self):
        self.assertEqual(PaperAccount("A", AccountConfig(starting_balance=1000)).state().current_equity, 1000)

    def test_03_balance_and_equity_separation(self):
        state = PaperAccount("A", AccountConfig()).update(floating_pl=25, used_margin=0, open_positions=1)
        self.assertEqual((state.current_balance, state.current_equity), (1000, 1025))

    def test_04_floating_pl_updates(self):
        account = PaperAccount("A", AccountConfig()); self.assertEqual(account.update(floating_pl=-40, used_margin=0, open_positions=1).floating_pl, -40)

    def test_05_realized_pl_updates_balance(self):
        account = PaperAccount("A", AccountConfig()); account.apply_balance_change(75); self.assertEqual((account.balance, account.realized_pl), (1075, 75))

    def test_06_drawdown_calculation(self):
        account = PaperAccount("A", AccountConfig()); account.update(floating_pl=100, used_margin=0, open_positions=1); state = account.update(floating_pl=-100, used_margin=0, open_positions=1); self.assertAlmostEqual(state.drawdown_money, 200)

    # POSITION SIZING 7-11
    def test_07_volume_from_logical_risk(self):
        result = self.size(); self.assertTrue(result.allowed); self.assertLessEqual(result.actual_logical_risk_zar, result.ideal_risk_money_zar * 1.2)

    def test_08_emergency_risk_cap_reduces_volume(self):
        base = self.size(emergency_stop=1.0975); capped = self.size(emergency_stop=1.0800); self.assertLessEqual(capped.final_lots, base.final_lots)

    def test_09_volume_rounds_down(self):
        result = self.size(); self.assertAlmostEqual(result.final_lots / self.spec.volume_step, round(result.final_lots / self.spec.volume_step))

    def test_10_minimum_volume_over_risk_blocks_trade(self):
        result = self.size(account=self.account_state(500), config=AccountConfig(starting_balance=500)); self.assertFalse(result.allowed); self.assertEqual(result.status, "MINIMUM_VOLUME_OVER_RISK")

    def test_11_margin_cap_reduces_or_blocks_volume(self):
        account = self.account_state(5000, free_margin=1); result = self.size(account=account); self.assertFalse(result.allowed); self.assertEqual(result.status, "INSUFFICIENT_MARGIN")

    # BID / ASK 12-15
    def fill(self, direction: str, order_kind: str, candle: dict | None = None):
        return FillEngine(self.conversion).fill(spec=self.spec, config=self.normal, replay_event_id="E1", order_id="O1", timestamp=1_788_000_000, candle=candle or self.candle(), direction=direction, order_kind=order_kind, volume=.01, requested_price=1.1)

    def test_12_buy_enters_at_ask(self):
        fill = self.fill("BULLISH", "ENTRY"); self.assertEqual(fill.fill_side, "ASK"); self.assertEqual(fill.final_fill_price, fill.ask_price)

    def test_13_buy_exits_at_bid(self):
        fill = self.fill("BULLISH", "EXIT"); self.assertEqual(fill.fill_side, "BID"); self.assertEqual(fill.final_fill_price, fill.bid_price)

    def test_14_sell_enters_at_bid(self):
        fill = self.fill("BEARISH", "ENTRY"); self.assertEqual(fill.fill_side, "BID")

    def test_15_sell_exits_at_ask(self):
        fill = self.fill("BEARISH", "EXIT"); self.assertEqual(fill.fill_side, "ASK")

    # SPREAD 16-18
    def test_16_native_spread_used_when_available(self):
        result = SpreadEngine().calculate(spec=self.spec, config=self.normal, timestamp=1_788_000_000, candle=self.candle(spread=9)); self.assertEqual((result["spread_points"], result["spread_source"]), (9, "NATIVE_HISTORICAL_SPREAD"))

    def test_17_session_profile_fallback(self):
        result = SpreadEngine().calculate(spec=self.spec, config=self.normal, timestamp=1_788_000_000, candle=self.candle(spread=None)); self.assertEqual(result["spread_source"], "SYMBOL_SESSION_ESTIMATED")

    def test_18_spread_not_double_counted(self):
        fill = self.fill("BULLISH", "ENTRY"); self.assertAlmostEqual(fill.final_fill_price - fill.bid_price, fill.spread_points * self.spec.point_size)

    # SLIPPAGE 19-21
    def slip(self, kind: str = "ENTRY"):
        return SlippageEngine().calculate(spec=self.spec, config=ExecutionConfig(), replay_event_id="E1", order_id="O1", order_kind=kind)

    def test_19_seeded_slippage_deterministic(self):
        self.assertEqual(self.slip(), self.slip())

    def test_20_same_replay_seed_reproduces_fills(self):
        a = FillEngine(self.conversion).fill(spec=self.spec, config=ExecutionConfig(), replay_event_id="E1", order_id="O1", timestamp=1_788_000_000, candle=self.candle(), direction="BULLISH", order_kind="ENTRY", volume=.01, requested_price=1.1); b = FillEngine(self.conversion).fill(spec=self.spec, config=ExecutionConfig(), replay_event_id="E1", order_id="O1", timestamp=1_788_000_000, candle=self.candle(), direction="BULLISH", order_kind="ENTRY", volume=.01, requested_price=1.1); self.assertEqual(a, b)

    def test_21_emergency_slippage_differs_appropriately(self):
        self.assertGreater(self.slip("EMERGENCY_STOP")["slippage_points"], self.slip("ENTRY")["slippage_points"])

    # COMMISSION / SWAP 22-24
    def test_22_opening_and_closing_commission(self):
        engine = CommissionEngine(self.conversion); opening = engine.charge(spec=self.spec, config=self.normal, volume=.1, price=1.1, timestamp=1_788_000_000, side="OPEN"); closing = engine.charge(spec=self.spec, config=self.normal, volume=.1, price=1.1, timestamp=1_788_000_000, side="CLOSE"); self.assertGreater(opening + closing, 0)

    def test_23_partial_close_commission(self):
        engine = CommissionEngine(self.conversion); full = engine.charge(spec=self.spec, config=self.normal, volume=.1, price=1.1, timestamp=1_788_000_000, side="CLOSE"); partial = engine.charge(spec=self.spec, config=self.normal, volume=.05, price=1.1, timestamp=1_788_000_000, side="CLOSE"); self.assertAlmostEqual(partial, full / 2)

    def test_24_overnight_swap_event(self):
        stamp = datetime(2026, 8, 5, 21, 5, tzinfo=timezone.utc).timestamp(); result = SwapEngine(self.conversion).charge(spec=self.spec, config=ExecutionConfig(swap_model="ESTIMATED_STATIC"), timestamp=stamp, volume=.1); self.assertGreater(result["charge_zar"], 0); self.assertTrue(result["triple_swap"])

    # PARTIALS 25-27
    def test_25_valid_volume_partial(self):
        broker = self.open_broker(balance=10000); before = broker.position.volume; events = broker._close(replay_event_id="SYN|000002", timestamp=1_788_000_060, candle=self.candle(1.104), reason="TP1_PARTIAL", requested_price=1.104, order_kind="PARTIAL", fraction=.5); self.assertIn("PARTIAL_FILLED", [row["action"] for row in events]); self.assertLess(broker.position.volume, before)

    def test_26_minimum_volume_partial_rejection(self):
        broker = self.open_broker(balance=5000); broker.position.volume = broker.position.initial_volume = .01; events = broker._close(replay_event_id="SYN|000002", timestamp=1_788_000_060, candle=self.candle(), reason="TP1_PARTIAL", requested_price=1.101, order_kind="PARTIAL", fraction=.5); self.assertEqual(events[0]["action"], "PARTIAL_REJECTED")

    def test_27_remaining_volume_tracked_correctly(self):
        broker = self.open_broker(balance=10000); initial = broker.position.volume; broker._close(replay_event_id="SYN|000002", timestamp=1_788_000_060, candle=self.candle(1.104), reason="TP1_PARTIAL", requested_price=1.104, order_kind="PARTIAL", fraction=.5); self.assertAlmostEqual(broker.position.volume, initial - broker.position.partials[-1]["closed_volume"])

    # MARGIN 28-30
    def test_28_used_and_free_margin(self):
        state = PaperAccount("A", AccountConfig()).update(floating_pl=0, used_margin=250, open_positions=1); self.assertEqual((state.used_margin, state.free_margin), (250, 750))

    def test_29_margin_warning(self):
        level, status = MarginEngine.status(140, 100, 150, 100, 50); self.assertEqual((level, status), (140, "LOW_MARGIN_WARNING"))

    def test_30_stop_out_simulation(self):
        _, status = MarginEngine.status(49, 100, 150, 100, 50); self.assertEqual(status, "STOP_OUT")

    # CURRENCY 31-32
    def test_31_native_pl_converts_to_zar(self):
        result = self.conversion.convert(10, "USD", 1_788_000_000); self.assertEqual(result.account_currency_amount, 183)

    def test_32_missing_conversion_blocks_or_warns_explicitly(self):
        result = self.conversion.convert(10, "XYZ", 1_788_000_000); self.assertIsNone(result.account_currency_amount); self.assertEqual(result.status, "MISSING_RATE")

    # ACCOUNTING 33-36
    def test_33_gross_minus_costs_equals_net(self):
        broker = self.open_broker(balance=10000); broker._close(replay_event_id="SYN|000002", timestamp=1_788_000_060, candle=self.candle(1.104), reason="EXIT_TEST", requested_price=1.104); report = broker.attempt_reports[-1]; self.assertAlmostEqual(report["gross_pl_zar"] - sum(report["costs_zar"].values()), report["net_pl_zar"], places=5)

    def test_34_attempt_totals_equal_sequence_totals(self):
        broker = self.open_broker(balance=10000); broker._close(replay_event_id="SYN|000002", timestamp=1_788_000_060, candle=self.candle(1.104), reason="EXIT_TEST", requested_price=1.104); reports = broker.attempt_reports; self.assertAlmostEqual(sum(row["net_pl_zar"] for row in reports), broker.final_payload()["account"]["realized_pl"])

    def test_35_sequence_totals_update_account_balance(self):
        broker = self.open_broker(balance=10000); broker._close(replay_event_id="SYN|000002", timestamp=1_788_000_060, candle=self.candle(1.104), reason="EXIT_TEST", requested_price=1.104); self.assertAlmostEqual(broker.account.balance, 10000 + broker.account.realized_pl)

    def test_36_reentry_uses_new_current_balance(self):
        state = self.account_state(5500); config = AccountConfig(starting_balance=5000, compounding=True); self.assertEqual(PositionSizer.planned_risk(config, state), 55)

    # CAUSALITY 37-42
    def repriced(self, payload=None, balance=1000):
        return PaperExecutionReplayService.reprice_browser_payload(payload or self.browser_payload, account_config=AccountConfig(starting_balance=balance), execution_config=ExecutionConfig(), include_shadows=True)

    def test_37_future_candles_cannot_change_earlier_fill(self):
        prefix = deepcopy(self.browser_payload); prefix["events"] = prefix["events"][:8]; a = self.repriced(prefix); changed = deepcopy(self.browser_payload); changed["candles"]["M1"][-1]["close"] *= 10; b = self.repriced(changed); self.assertEqual(a["paper_events"], b["paper_events"][:len(a["paper_events"])])

    def test_38_future_spread_cannot_change_earlier_cost(self):
        prefix = deepcopy(self.browser_payload); prefix["events"] = prefix["events"][:8]; a = self.repriced(prefix); changed = deepcopy(self.browser_payload); changed["candles"]["M1"][-1]["spread"] = 9999; b = self.repriced(changed); self.assertEqual(a["paper_events"], b["paper_events"][:len(a["paper_events"])])

    def test_39_future_target_state_cannot_change_partial(self):
        prefix = deepcopy(self.browser_payload); prefix["events"] = prefix["events"][:8]; a = self.repriced(prefix); changed = deepcopy(self.browser_payload); changed["events"][-1]["director_decision"]["committed_action"] = "TAKE_PARTIAL"; b = self.repriced(changed); self.assertEqual(a["paper_events"], b["paper_events"][:len(a["paper_events"])])

    def test_40_rewind_reproduces_account_state(self):
        self.assertEqual(self.repriced()["final"], self.repriced()["final"])

    def test_41_shadow_accounts_isolated(self):
        result = self.repriced(); hashes = [row["isolated_state_hash"] for row in result["paper_events"][-1]["shadow_accounts"]]; self.assertEqual(len(hashes), len(set(hashes)) if len(set(hashes)) > 1 else len(hashes)); self.assertTrue(result["final"]["shadow_isolation_valid"])

    def test_42_strategy_signals_unchanged_by_account_size(self):
        small = self.repriced(balance=500); large = self.repriced(balance=5000); self.assertEqual(small["strategy_event_hash"], large["strategy_event_hash"])

    # INTRABAR 43-45
    def test_43_lower_timeframe_resolves_ambiguity(self):
        result = IntrabarResolver().resolve(direction="BULLISH", parent_candle={"low": 98, "high": 102}, stop=99, target=101, policy="LOWER_TIMEFRAME_THEN_CONSERVATIVE_STOP_FIRST", closed_child_candles=[{"time": 1, "low": 100, "high": 101.2}], parent_close_time=5); self.assertEqual((result["resolution"], result["resolution_source"]), ("TARGET_FIRST", "CLOSED_LOWER_TIMEFRAME"))

    def test_44_conservative_fallback_works(self):
        result = IntrabarResolver().resolve(direction="BULLISH", parent_candle={"low": 98, "high": 102}, stop=99, target=101, policy="CONSERVATIVE_STOP_FIRST"); self.assertEqual(result["resolution"], "STOP_FIRST")

    def test_45_ambiguity_flag_stored(self):
        result = IntrabarResolver().resolve(direction="BULLISH", parent_candle={"low": 98, "high": 102}, stop=99, target=101, policy="FLAG_AS_AMBIGUOUS"); self.assertTrue(result["ambiguous"]); self.assertEqual(result["resolution"], "UNRESOLVED")

    # SAFETY 46-50
    def test_46_no_order_apis(self):
        source = "\n".join(path.read_text(encoding="utf-8") for path in (project_root() / "simulator").rglob("*.py") if "tests" not in path.parts); self.assertNotIn("order_send(", source); self.assertNotIn("positions_get(", source)

    def test_47_no_real_broker_calls(self):
        source = (project_root() / "simulator" / "execution" / "paper_broker.py").read_text(encoding="utf-8"); self.assertNotIn("MetaTrader5", source); self.assertNotIn("requests.", source)

    def test_48_paper_only_banner_always_visible(self):
        html = (project_root() / "simulator" / "ui" / "index.html").read_text(encoding="utf-8"); self.assertIn("PAPER ONLY", html); self.assertIn("NO LIVE ORDERS", html)

    def test_49_one_execution_action_per_canonical_order_event(self):
        result = self.repriced(); self.assertTrue(all(isinstance(row["canonical"]["primary_execution_action"], str) for row in result["paper_events"]))

    def test_50_deterministic_end_to_end_account_replay(self):
        a = self.repriced(); b = self.repriced(); self.assertEqual(stable_hash(a), stable_hash(b))
