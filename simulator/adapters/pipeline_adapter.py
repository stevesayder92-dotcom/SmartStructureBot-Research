from __future__ import annotations

from copy import deepcopy
from typing import Any

import pandas as pd

from core.expert_strategy import build_expert_htf_context, confirmed_swings
from core.pipeline_runner import PipelineOptions, run_pipeline
from core.setup_lifecycle import PipelineRuntimeState
from core.steve_trade_management import SteveTradeManagementEngine
from core.synchronized_m1_replay import build_parent_contract, find_m1_child_entry
from simulator.adapters.dataset_adapter import ReplayDataset
from simulator.config import SimulatorConfig
from simulator.models.schema import json_safe, stable_hash


def _state(root: Any, fallback: str = "UNAVAILABLE") -> str:
    return str(root.get("state", fallback)) if isinstance(root, dict) else fallback


class CanonicalPipelineAdapter:
    """
    Read-only bridge into the canonical pipeline.

    Every M5 update calls run_pipeline with the visible global prefix. M1 child
    discovery calls the existing synchronized M1 engine with the visible M1
    prefix. The simulator never recreates strategy decisions in JavaScript.
    """

    def __init__(self, dataset: ReplayDataset, config: SimulatorConfig):
        self.dataset = dataset
        self.config = config
        self.runtime = PipelineRuntimeState()
        self.m1_manager = SteveTradeManagementEngine()
        self.last_full_snapshot: dict[str, Any] = {}
        self.last_m1_report: dict[str, Any] = {
            "state": "M1_PARENT_NOT_ACTIVE",
            "causal_valid": True,
            "entry_ready": False,
        }
        self.committed_entry: dict[str, Any] | None = None
        self.entry_owner: str | None = None
        self.m1_management_offset = 0
        self.last_management: dict[str, Any] = {
            "state": "NO_MANAGED_ENTRY",
            "attempt_count": 0,
            "causal_valid": True,
            "order_api_called": False,
        }

    @staticmethod
    def _remap_indices(value: Any, offset: int, *, subtract: bool = False) -> Any:
        """Translate local M1 adapter indexes without mutating engine output."""
        delta = -int(offset) if subtract else int(offset)
        if isinstance(value, list):
            return [CanonicalPipelineAdapter._remap_indices(item, offset, subtract=subtract) for item in value]
        if not isinstance(value, dict):
            return value
        mapped: dict[str, Any] = {}
        for key, item in value.items():
            if (
                isinstance(item, int)
                and not isinstance(item, bool)
                and not key.startswith("m5_")
                and (key == "index" or key.endswith("_index") or key.endswith("_at_index"))
            ):
                mapped[key] = item + delta
            else:
                mapped[key] = CanonicalPipelineAdapter._remap_indices(
                    item, offset, subtract=subtract
                )
        return mapped

    @staticmethod
    def _resample_htf(m5_prefix: pd.DataFrame) -> dict[str, pd.DataFrame]:
        source = m5_prefix.copy()
        source["_dt"] = pd.to_datetime(source["time"], unit="s", utc=True)
        source = source.set_index("_dt")
        frames: dict[str, pd.DataFrame] = {}
        for name, minutes in (("M15", 15), ("M30", 30), ("H1", 60)):
            frame = (
                source.resample(f"{minutes}min", label="left", closed="left")
                .agg(
                    {
                        "open": "first",
                        "high": "max",
                        "low": "min",
                        "close": "last",
                        "tick_volume": "sum",
                    }
                )
                .dropna()
                .reset_index()
            )
            frame["time"] = frame["_dt"].astype("int64") / 1_000_000_000
            frames[name] = frame[
                ["time", "open", "high", "low", "close", "tick_volume"]
            ]
        return frames

    def evaluate_m5(self, as_of_index: int) -> tuple[dict[str, Any], str]:
        if as_of_index < 0:
            return {}, stable_hash({})
        prefix = self.dataset.m5.iloc[: as_of_index + 1]
        decision_open = float(prefix.iloc[-1]["time"])
        context = build_expert_htf_context(
            decision_candle_open_time=decision_open,
            decision_timeframe_seconds=300,
            frame_data=self._resample_htf(prefix),
            sensitivity=self.config.engine_sensitivity,
            policy=self.config.htf_policy,
            allow_single_strong=self.config.allow_single_strong_htf,
        )
        result = run_pipeline(
            data=self.dataset.m5,
            symbol=self.dataset.symbol,
            timeframe="M5",
            as_of_index=int(as_of_index),
            options=PipelineOptions(
                strategy_model="EXPERT_SPEC_V1",
                engine_sensitivity=self.config.engine_sensitivity,
            ),
            runtime_state=self.runtime,
            higher_timeframe_context=context,
        )
        self.last_full_snapshot = json_safe(result.snapshot)
        return self.last_full_snapshot, stable_hash(self.last_full_snapshot)

    def _live_parent_candidate(
        self, snapshot: dict[str, Any], m5_index: int
    ) -> dict[str, Any] | None:
        setup = dict(snapshot.get("setup") or {})
        retracement = dict(snapshot.get("retracement") or {})
        if not setup.get("setup_id") or not retracement.get("qualified"):
            return None
        origin = dict(retracement.get("origin_swing") or {})
        counter = dict(retracement.get("counter_swing") or {})
        trigger = dict(retracement.get("active_failure_trigger") or {})
        fibonacci = dict(retracement.get("fibonacci") or setup.get("fibonacci") or {})
        if not origin or not counter or not trigger or not fibonacci.get("available"):
            return None
        current = self.dataset.m5.iloc[int(m5_index)]
        return {
            "setup_id": setup["setup_id"],
            "direction": setup["direction"],
            "anchor": origin,
            "counter": counter,
            "trigger": trigger,
            "logical_stop_structure": counter,
            "entry_index": int(m5_index),
            "entry_price": float(current["close"]),
            "stop_level": float(retracement.get("retracement_extreme_stop") or counter["level"]),
            "qualified_at": int(retracement.get("qualification_available_at_index") or m5_index),
            "fibonacci": fibonacci,
        }

    def evaluate_m1(
        self,
        *,
        m1_index: int,
        m5_index: int,
        event_time: float,
    ) -> dict[str, Any]:
        if m1_index < 0 or m5_index < 0 or not self.last_full_snapshot:
            return self.last_m1_report
        if self.committed_entry is not None:
            self._update_m1_management(m1_index)
            return self.last_m1_report
        candidate = self._live_parent_candidate(self.last_full_snapshot, m5_index)
        if candidate is None:
            self.last_m1_report = {
                "state": "M1_PARENT_NOT_ACTIVE",
                "entry_ready": False,
                "as_of_index": int(m1_index),
                "causal_valid": True,
            }
            return self.last_m1_report
        try:
            parent = build_parent_contract(
                candidate=candidate,
                m5_data=self.dataset.m5.iloc[: m5_index + 1],
                symbol=self.dataset.symbol,
            )
        except ValueError as error:
            # A qualified parent may still lack a legally placed current stop.
            # That is a causal WAIT state, never permission to manufacture one.
            self.last_m1_report = {
                "state": "M1_PARENT_INVALIDATION_UNAVAILABLE",
                "entry_ready": False,
                "as_of_index": int(m1_index),
                "causal_valid": True,
                "hard_blockers": [str(error)],
                "reason": "M1 monitoring waits until the canonical parent invalidation is valid.",
            }
            return self.last_m1_report
        # The temporary M5 fallback boundary is the current replay event. It is
        # used only to bound M1 discovery; it is never published as an entry.
        parent["m5_entry_time"] = float(event_time)
        parent["m5_entry_index"] = int(m5_index)
        # M1 child discovery needs only the parent monitoring window. Feeding
        # the full multi-month history made every replay tick quadratic while
        # adding no causal evidence to the current parent setup.
        parent_armed_time = float(parent.get("armed_time") or event_time)
        visible = self.dataset.m1.iloc[: m1_index + 1]
        lower_bound = parent_armed_time - 20 * 60
        local_start = int(visible[visible["time"] >= lower_bound].index.min()) if bool((visible["time"] >= lower_bound).any()) else 0
        local_m1 = visible.iloc[local_start:].reset_index(drop=True)
        report = find_m1_child_entry(
            parent=parent,
            m1_data=local_m1,
            sensitivity=2,
        )
        self.last_m1_report = json_safe(self._remap_indices(report, local_start))
        entry = dict(self.last_m1_report.get("entry") or {})
        if bool(self.last_m1_report.get("entry_ready") or entry.get("entry_ready")):
            self.committed_entry = entry
            self.entry_owner = "M1"
            self._update_m1_management(m1_index, just_opened=True)
        return self.last_m1_report

    def claim_m5_entry_if_ready(self, snapshot: dict[str, Any]) -> dict[str, Any] | None:
        entry = dict(snapshot.get("entry") or {})
        if self.committed_entry is None and entry.get("ready"):
            self.committed_entry = entry
            self.entry_owner = "M5"
            self.last_management = dict(snapshot.get("trailing_protection") or {})
            return entry
        if self.entry_owner == "M5":
            self.last_management = dict(snapshot.get("trailing_protection") or {})
        return None

    def _update_m1_management(self, m1_index: int, just_opened: bool = False) -> None:
        entry = dict(self.committed_entry or {})
        if not entry or self.entry_owner != "M1":
            return
        direction = str(entry.get("parent_direction") or entry.get("direction") or "NEUTRAL")
        if direction not in {"BULLISH", "BEARISH"}:
            return
        global_entry_index = int(entry.get("entry_index") or m1_index)
        self.m1_management_offset = max(0, global_entry_index - 140)
        prefix = self.dataset.m1.iloc[self.m1_management_offset : m1_index + 1].reset_index(drop=True)
        swings = confirmed_swings(
            prefix,
            as_of_index=len(prefix) - 1,
            sensitivity=2,
        )
        local_entry = self._remap_indices(entry, self.m1_management_offset, subtract=True)
        entry_model = None
        if just_opened:
            counter_index = int(local_entry.get("counter_structure_index") or local_entry["entry_index"])
            trigger_index = int(local_entry.get("failure_trigger_index") or local_entry["entry_index"])
            logical_index = int(local_entry.get("logical_stop_owner_index") or local_entry["entry_index"])
            stop_side = "LOW" if direction == "BULLISH" else "HIGH"
            counter_side = "LOW" if direction == "BULLISH" else "HIGH"
            trigger_side = "HIGH" if direction == "BULLISH" else "LOW"
            entry_model = {
                "setup_id": local_entry.get("parent_m5_setup_id"),
                "direction": direction,
                "entry_index": int(local_entry["entry_index"]),
                "entry_price": float(local_entry["entry_price"]),
                "anchor": {
                    "index": counter_index,
                    "level": float(local_entry.get("counter_structure_price") or local_entry["entry_price"]),
                    "side": counter_side,
                    "confirmed_at_index": min(counter_index + 2, int(local_entry["entry_index"])),
                },
                "counter": {
                    "index": counter_index,
                    "level": float(local_entry.get("counter_structure_price") or local_entry["entry_price"]),
                    "side": counter_side,
                    "confirmed_at_index": min(counter_index + 2, int(local_entry["entry_index"])),
                },
                "trigger": {
                    "index": trigger_index,
                    "level": float(local_entry.get("failure_trigger_price") or local_entry["entry_price"]),
                    "side": trigger_side,
                    "confirmed_at_index": int(local_entry.get("failure_trigger_available_at_index") or min(trigger_index + 2, int(local_entry["entry_index"]))),
                },
                "logical_stop_structure": {
                    "index": logical_index,
                    "level": float(local_entry.get("logical_stop") or local_entry["entry_price"]),
                    "side": stop_side,
                    "confirmed_at_index": min(logical_index + 2, int(local_entry["entry_index"])),
                },
                "stop_level": float(local_entry.get("logical_stop") or local_entry["entry_price"]),
                "fibonacci": dict((self.last_full_snapshot.get("retracement") or {}).get("fibonacci") or {}),
            }
        local_management = self.m1_manager.evaluate(
                data=prefix,
                symbol=self.dataset.symbol,
                timeframe="M1",
                as_of_index=len(prefix) - 1,
                direction=direction,
                context=self.last_full_snapshot.get("context"),
                confirmed_swings=swings,
                canonical_entry=entry_model,
            )
        self.last_management = json_safe(
            self._remap_indices(local_management, self.m1_management_offset)
        )

    def compact_snapshot(self) -> dict[str, Any]:
        full = self.last_full_snapshot
        structure = dict(full.get("structure") or {})
        swings = list(structure.get("confirmed_swings") or [])
        structure["confirmed_swings"] = swings[-80:]
        structure["confirmed_highs"] = list(structure.get("confirmed_highs") or [])[-40:]
        structure["confirmed_lows"] = list(structure.get("confirmed_lows") or [])[-40:]
        roots = {
            name: deepcopy(full.get(name) or {})
            for name in (
                "meta", "market", "control", "context", "transition", "validation",
                "protection", "impulse_cycle", "setup_invalidation", "retracement",
                "setup", "entry", "decision", "trade", "contract_health",
            )
        }
        roots["structure"] = structure
        roots["m1_entry"] = deepcopy(self.last_m1_report)
        roots["management"] = deepcopy(self.last_management)
        roots["identity"] = {
            "symbol": self.dataset.symbol,
            "strategy_version": self.config.strategy_version,
            "entry_owner": self.entry_owner,
            "setup_id": (full.get("setup") or {}).get("setup_id"),
        }
        return json_safe(roots)

    def root_states(self) -> dict[str, str]:
        compact = self.compact_snapshot()
        return {name: _state(value) for name, value in compact.items() if isinstance(value, dict)}
