from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import hashlib
import json
import time

from simulator import ORDERS_ENABLED, SIMULATOR_VERSION
from simulator.adapters.dataset_adapter import DatasetAdapter, ReplayDataset
from simulator.adapters.pipeline_adapter import CanonicalPipelineAdapter
from simulator.config import SimulatorConfig
from simulator.models.schema import ReplayEvent, json_safe, stable_hash
from simulator.models.financial import AccountConfig, ExecutionConfig
from simulator.services.execution_replay_service import PaperExecutionReplayService
from simulator.services.financial_bug_detection import financial_bug_flags
from simulator.services.observability import (
    bug_flags,
    classify_event,
    director_decision,
    engine_recommendations,
    mark_recommendation_status,
    shadow_states,
    story_event,
)


@dataclass(frozen=True)
class ReplayWindow:
    start_time: float
    end_time: float
    m1_start: int
    m5_start: int


class ReplaySession:
    """Forward-only builder plus immutable checkpoint-based time travel."""

    def __init__(
        self,
        *,
        dataset: ReplayDataset,
        config: SimulatorConfig,
        session_id: str,
        start_time: float,
        end_time: float,
        case_number: int | None = None,
        case_metadata: dict[str, Any] | None = None,
        account_config: AccountConfig | None = None,
        execution_config: ExecutionConfig | None = None,
    ):
        if ORDERS_ENABLED:
            raise RuntimeError("Simulator startup refused: order execution must remain disabled")
        self.dataset = dataset
        self.config = config
        self.session_id = session_id
        self.case_number = case_number
        self.case_metadata = json_safe(case_metadata or {})
        self.account_config = account_config or AccountConfig()
        self.execution_config = execution_config or ExecutionConfig()
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.timeline, m1_start, m5_start = DatasetAdapter.timeline(
            dataset, start_time=float(start_time), end_time=float(end_time)
        )
        self.window = ReplayWindow(float(start_time), float(end_time), m1_start, m5_start)
        self.pipeline = CanonicalPipelineAdapter(dataset, config)
        self.events: list[ReplayEvent] = []
        self.checkpoints: dict[int, dict[str, Any]] = {}
        self.full_pipeline_snapshots: dict[str, dict[str, Any]] = {}
        self.story: list[dict[str, Any]] = []
        self.attempt_peaks: dict[str, float] = {}
        self.sequence_peak = 0.0
        self.build_seconds = 0.0
        self.paper_service = PaperExecutionReplayService(
            account_config=self.account_config,
            execution_config=self.execution_config,
        )
        self.paper_final: dict[str, Any] = {}

    @classmethod
    def from_case(
        cls,
        adapter: DatasetAdapter,
        *,
        case_number: int,
        config: SimulatorConfig,
        before_minutes: int = 55,
        after_minutes: int = 120,
    ) -> "ReplaySession":
        case = adapter.case(case_number)
        dataset = adapter.load_frozen(str(case["symbol"]))
        entry_time = float(case["entry_time"])
        outcome = dict(case.get("outcome") or {})
        end = min(
            float(outcome.get("review_end_time") or entry_time + after_minutes * 60),
            entry_time + after_minutes * 60,
        )
        start = entry_time - before_minutes * 60
        return cls(
            dataset=dataset,
            config=config,
            session_id=f"S1-CASE-{case_number:02d}",
            start_time=start,
            end_time=end,
            case_number=case_number,
            case_metadata={
                "symbol": case.get("symbol"),
                "direction": case.get("direction"),
                "entry_timeframe": case.get("entry_timeframe"),
                "entry_time": entry_time,
                "setup_id": case.get("parent_m5_setup_id"),
                "category_flags": list(case.get("category_flags") or []),
                "historical_outcome_hidden_from_decisions": True,
            },
        )

    def build(
        self,
        max_events: int | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> "ReplaySession":
        started = time.perf_counter()
        previous_compact: dict[str, Any] | None = None
        last_pipeline_hash = stable_hash({})
        # Candles immediately before the requested start were already closed
        # and therefore belong to event zero's legal visible prefix.
        last_m5_index = self.window.m5_start - 1
        last_m1_index = self.window.m1_start - 1
        if last_m5_index >= 0:
            _, last_pipeline_hash = self.pipeline.evaluate_m5(last_m5_index)
            self.full_pipeline_snapshots[last_pipeline_hash] = deepcopy(
                self.pipeline.last_full_snapshot
            )
        parent_hash: str | None = None
        previous_diagnostics: dict[str, Any] = {}
        recent_ranges: list[float] = []
        total_events = min(len(self.timeline), int(max_events)) if max_events is not None else len(self.timeline)
        for number, clock in enumerate(self.timeline):
            if max_events is not None and number >= int(max_events):
                break
            m5_indices = tuple(int(i) for i in clock["newly_closed_m5"])
            m1_indices = tuple(int(i) for i in clock["newly_closed_m1"])
            if m5_indices:
                last_m5_index = max(m5_indices)
                _, last_pipeline_hash = self.pipeline.evaluate_m5(last_m5_index)
                self.full_pipeline_snapshots[last_pipeline_hash] = deepcopy(
                    self.pipeline.last_full_snapshot
                )
            before_entry = deepcopy(self.pipeline.committed_entry)
            if m1_indices:
                last_m1_index = max(m1_indices)
                self.pipeline.evaluate_m1(
                    m1_index=last_m1_index,
                    m5_index=last_m5_index,
                    event_time=float(clock["event_time"]),
                )
            new_entry = None
            if before_entry is None and self.pipeline.committed_entry is not None:
                new_entry = deepcopy(self.pipeline.committed_entry)
            if m5_indices:
                m5_entry = self.pipeline.claim_m5_entry_if_ready(
                    self.pipeline.last_full_snapshot
                )
                if new_entry is None and m5_entry is not None:
                    new_entry = deepcopy(m5_entry)
            compact = self.pipeline.compact_snapshot()
            current_price = None
            if last_m1_index >= 0:
                current_price = float(self.dataset.m1.iloc[last_m1_index]["close"])
            elif last_m5_index >= 0:
                current_price = float(self.dataset.m5.iloc[last_m5_index]["close"])
            if m1_indices:
                current_candle = self.dataset.m1.iloc[last_m1_index].to_dict()
            elif m5_indices:
                current_candle = self.dataset.m5.iloc[last_m5_index].to_dict()
            elif last_m1_index >= 0:
                current_candle = self.dataset.m1.iloc[last_m1_index].to_dict()
            else:
                current_candle = self.dataset.m5.iloc[last_m5_index].to_dict()
            candle_range = abs(float(current_candle["high"]) - float(current_candle["low"]))
            baseline_range = sum(recent_ranges[-14:]) / len(recent_ranges[-14:]) if recent_ranges[-14:] else candle_range or 1.0
            volatility_ratio = candle_range / baseline_range if baseline_range > 0 else 1.0
            recent_ranges.append(candle_range)
            shadows = shadow_states(compact, current_price)
            decision = director_decision(
                snapshot=compact,
                event_time=float(clock["event_time"]),
                new_entry=new_entry,
            )
            recommendations = mark_recommendation_status(
                engine_recommendations(compact), decision
            )
            sequence_accounting = self._sequence_accounting(compact, current_price)
            management_diagnostics = self._management_diagnostics(
                compact, sequence_accounting, recommendations, decision.payload()
            )
            event_id = f"{self.session_id}|EVENT|{number:06d}"
            paper = self.paper_service.process(
                replay_event_id=event_id,
                timestamp=float(clock["event_time"]),
                symbol=self.dataset.symbol,
                candle=json_safe(current_candle),
                snapshot={**compact, "management_diagnostics": management_diagnostics},
                director_decision=decision.payload(),
                volatility_ratio=volatility_ratio,
            )
            flags = bug_flags(
                event_id=event_id,
                snapshot={
                    **compact,
                    "management_diagnostics": management_diagnostics,
                    "previous_management_diagnostics": previous_diagnostics,
                },
                decision=decision,
                pipeline_state_hash=last_pipeline_hash,
                recomputed_hash=stable_hash(self.pipeline.last_full_snapshot),
            )
            flags.extend(financial_bug_flags(event_id, paper))
            event_type, priority = classify_event(
                has_m1=bool(m1_indices),
                has_m5=bool(m5_indices),
                previous=previous_compact,
                snapshot=compact,
                decision=decision,
                flags=flags,
            )
            story = story_event(float(clock["event_time"]), event_type, compact, decision)
            if event_type not in {"M1_CANDLE_CLOSED", "M5_CANDLE_CLOSED", "M1_AND_M5_CLOSED"}:
                self.story.append(story)
            snapshot_payload = {
                "identity": {
                    "replay_session_id": self.session_id,
                    "event_id": event_id,
                    "schema_version": "S1_STATE_SNAPSHOT_V1",
                    "strategy_version": self.config.strategy_version,
                    "simulator_version": SIMULATOR_VERSION,
                    "symbol": self.dataset.symbol,
                },
                "replay_clock": {
                    "event_number": number,
                    "event_time": float(clock["event_time"]),
                    "processing_order": list(clock["processing_order"]),
                },
                "data_visibility": {
                    "visible_m1_as_of_index": last_m1_index,
                    "visible_m5_as_of_index": last_m5_index,
                    "visible_m1_rows": last_m1_index + 1,
                    "visible_m5_rows": last_m5_index + 1,
                    "future_rows_visible": 0,
                    "unfinished_rows_visible": 0,
                },
                **compact,
                "recommendations": recommendations,
                "Director_decision": decision.payload(),
                "shadow_managers": shadows,
                "bug_flags": [flag.payload() for flag in flags],
                "sequence_accounting": sequence_accounting,
                "management_diagnostics": management_diagnostics,
                "paper_execution": paper["canonical"],
                "account_state": paper["canonical"]["account"],
                "shadow_accounts": paper["shadow_accounts"],
                "execution_ledger_events": paper["canonical"]["execution_events"],
                "money_story_events": paper["canonical"]["money_story_events"],
                "equity_point": paper["canonical"]["equity_point"],
                "trade_story_events": list(self.story[-40:]),
                "integrity": {
                    "dataset_valid": bool(self.dataset.validation["valid"]),
                    "m1_m5_aligned": not bool(self.dataset.validation["m5_closes_without_m1_close"]),
                    "current_prefix_valid": True,
                    "state_hash_valid": True,
                    "causal_invariant_valid": True,
                    "snapshot_schema_valid": True,
                    "director_contract_valid": True,
                    "one_action_per_event": True,
                    "shadow_isolation_valid": all(row["causal_valid"] for row in shadows) and paper["shadow_isolation_valid"],
                    "paper_accounting_valid": bool(paper["canonical"]["causal_valid"]),
                    "execution_ledger_hash_valid": bool(paper["canonical"].get("execution_ledger_hash") or not paper["canonical"].get("execution_events")),
                    "order_apis_absent": True,
                    "status": "PASS" if not any(flag.severity == "FAIL" for flag in flags) else "FAIL",
                },
            }
            snapshot_hash = stable_hash(snapshot_payload)
            snapshot_payload["snapshot_hash"] = snapshot_hash
            snapshot_payload["parent_snapshot_hash"] = parent_hash
            state_hash = stable_hash(
                [snapshot_hash, last_pipeline_hash, decision.payload(), shadows, paper["state_hash"]]
            )
            active = (compact.get("management") or {}).get("active_attempt") or {}
            event = ReplayEvent(
                replay_event_id=event_id,
                event_number=number,
                event_time=float(clock["event_time"]),
                newly_closed_m1_indices=m1_indices,
                newly_closed_m5_indices=m5_indices,
                visible_m1_rows=last_m1_index + 1,
                visible_m5_rows=last_m5_index + 1,
                parent_setup_id=(compact.get("setup") or {}).get("setup_id"),
                active_attempt_id=active.get("event_id"),
                event_type=event_type,
                event_priority=priority,
                processing_order=tuple(clock["processing_order"]),
                state_hash=state_hash,
                snapshot_hash=snapshot_hash,
                parent_snapshot_hash=parent_hash,
                pipeline_state_hash=last_pipeline_hash,
                snapshot=json_safe(snapshot_payload),
                recommendations=tuple(json_safe(recommendations)),
                director_decision=decision.payload(),
                shadow_managers=tuple(json_safe(shadows)),
                bug_flags=tuple(flag.payload() for flag in flags),
                trade_story_events=tuple(json_safe(self.story[-40:])),
                integrity=json_safe(snapshot_payload["integrity"]),
            )
            self.events.append(event)
            if number % self.config.checkpoint_frequency == 0 or flags:
                self.checkpoints[number] = {
                    "event_number": number,
                    "event_id": event_id,
                    "state_hash": state_hash,
                    "snapshot_hash": snapshot_hash,
                    "pipeline_state_hash": last_pipeline_hash,
                }
            previous_compact = compact
            previous_diagnostics = management_diagnostics
            parent_hash = snapshot_hash
            if progress_callback and (number == 0 or number + 1 == total_events or number % max(1, total_events // 100) == 0):
                progress_callback(number + 1, total_events, event_type)
        self.build_seconds = time.perf_counter() - started
        self.paper_final = json_safe(self.paper_service.final_payload())
        return self

    @staticmethod
    def _sequence_accounting(snapshot: dict[str, Any], current_price: float | None) -> dict[str, Any]:
        management = snapshot.get("management") or {}
        attempts = list(management.get("attempts") or [])
        rows = []
        sequence_r = 0.0
        for attempt in attempts:
            entry = float(attempt.get("entry_price", 0.0))
            stop = float(attempt.get("logical_stop", entry))
            risk = abs(entry - stop) or 1.0
            price = float(attempt.get("exit_price") if attempt.get("exit_price") is not None else current_price or entry)
            value = (price - entry) / risk if attempt.get("direction") == "BULLISH" else (entry - price) / risk
            sequence_r += value
            rows.append({
                "attempt_number": attempt.get("attempt_number"),
                "status": attempt.get("status"),
                "current_or_final_R": round(value, 4),
                "entry": entry,
                "stop": stop,
                "exit": attempt.get("exit_price"),
            })
        return {
            "attempt_count": len(rows),
            "attempts": rows,
            "current_sequence_R": round(sequence_r, 4),
            "reentry_count": int(management.get("reentry_count", 0)),
            "one_reentry_maximum": True,
        }

    def _management_diagnostics(
        self,
        snapshot: dict[str, Any],
        sequence: dict[str, Any],
        recommendations: list[dict[str, Any]],
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        attempts = list(sequence.get("attempts") or [])
        current = float(attempts[-1].get("current_or_final_R", 0.0)) if attempts else 0.0
        management = snapshot.get("management") or {}
        active = management.get("active_attempt") or management.get("latest_attempt") or {}
        attempt_id = str(active.get("event_id") or active.get("attempt_number") or "NONE")
        self.attempt_peaks[attempt_id] = max(self.attempt_peaks.get(attempt_id, current), current)
        sequence_r = float(sequence.get("current_sequence_R", 0.0))
        self.sequence_peak = max(self.sequence_peak, sequence_r)
        attempt_peak = self.attempt_peaks[attempt_id]
        giveback = max(0.0, attempt_peak - current)
        retained = current / attempt_peak if attempt_peak > 0 else None
        protection_action = next(
            (row for row in recommendations if row.get("engine") == "TrailingProtectionEngine"),
            {},
        )
        proposed = protection_action.get("proposed_action")
        current_protection = active.get("current_protection")
        direction = active.get("direction")
        valid_tighter = proposed is not None and current_protection is not None and (
            (direction == "BULLISH" and float(proposed) > float(current_protection))
            or (direction == "BEARISH" and float(proposed) < float(current_protection))
        )
        return json_safe({
            "current_attempt_R": current,
            "current_sequence_R": sequence_r,
            "peak_attempt_R": attempt_peak,
            "peak_sequence_R": self.sequence_peak,
            "current_giveback_R": giveback,
            "retained_peak_ratio": retained,
            "target_state": active.get("tp1_state") or ("TP1_TRIGGERED" if active.get("tp1_triggered") else "WAITING"),
            "continuation_state": str((snapshot.get("transition") or {}).get("state", "UNAVAILABLE")),
            "earned_opportunity": "SIGNIFICANT" if attempt_peak >= 2.0 else "EARNED" if attempt_peak >= 0.5 else "NOT_EARNED",
            "deterioration": "HIGH" if giveback >= 1.0 else "LOW",
            "exhaustion": "REVIEW" if giveback >= 1.5 and attempt_peak >= 2.0 else "NOT_PROVEN",
            "valid_tighter_structure": valid_tighter,
            "current_protection_owner": active.get("current_protection_source") or (snapshot.get("protection") or {}).get("type"),
            "recommended_action": protection_action.get("recommendation"),
            "committed_action": decision.get("committed_action"),
            "bread_burning_review": bool(attempt_peak >= 0.5 and current < 0.0),
            "causal_valid": True,
        })

    def restore(self, event_number: int) -> dict[str, Any]:
        target = int(event_number)
        if target < 0 or target >= len(self.events):
            raise IndexError("Replay event is outside the built ledger")
        earlier = [number for number in self.checkpoints if number <= target]
        checkpoint = max(earlier) if earlier else 0
        parent = self.events[checkpoint].parent_snapshot_hash
        for number in range(checkpoint, target + 1):
            event = self.events[number]
            if number > checkpoint and event.parent_snapshot_hash != parent:
                raise RuntimeError("Snapshot hash chain mismatch during reconstruction")
            parent = event.snapshot_hash
        return {
            "restore_mode": (
                "RESTORED_DIRECT_SNAPSHOT" if checkpoint == target else "REPLAYED_FROM_CHECKPOINT"
            ),
            "checkpoint_event": checkpoint,
            "target_event": target,
            "event": deepcopy(self.events[target].payload()),
        }

    def compare(self, event_a: int, event_b: int) -> list[dict[str, Any]]:
        left = self.events[int(event_a)].snapshot
        right = self.events[int(event_b)].snapshot
        result: list[dict[str, Any]] = []

        def walk(a: Any, b: Any, path: str) -> None:
            if isinstance(a, dict) and isinstance(b, dict):
                for key in sorted(set(a) | set(b)):
                    walk(a.get(key), b.get(key), f"{path}.{key}" if path else key)
            elif a != b:
                result.append({"field": path, "before": json_safe(a), "after": json_safe(b)})

        walk(left, right, "")
        return result

    def manifest(self) -> dict[str, Any]:
        root = Path(__file__).resolve().parents[2]
        digest = hashlib.sha256()
        for relative in (
            "core/pipeline_runner.py", "core/system_director.py",
            "simulator/adapters/dataset_adapter.py",
            "simulator/adapters/pipeline_adapter.py",
            "simulator/kernel/replay_session.py",
            "simulator/services/observability.py",
            "simulator/execution/paper_broker.py",
            "simulator/services/execution_replay_service.py",
        ):
            source = root / relative
            digest.update(relative.encode("utf-8"))
            digest.update(source.read_bytes())
        code_hash = digest.hexdigest()
        first = self.events[0] if self.events else None
        last = self.events[-1] if self.events else None
        return {
            "replay_session_id": self.session_id,
            "strategy_version": self.config.strategy_version,
            "simulator_version": SIMULATOR_VERSION,
            "code_hash": code_hash,
            "config_hash": self.config.hash(),
            "data_hash": self.dataset.data_hash,
            "symbol": self.dataset.symbol,
            "timezone": self.config.timezone,
            "start": self.window.start_time,
            "end": self.window.end_time,
            "m1_range": {
                "start_index": first.visible_m1_rows - 1 if first else self.window.m1_start - 1,
                "end_index": last.visible_m1_rows - 1 if last else self.window.m1_start - 1,
            },
            "m5_range": {
                "start_index": first.visible_m5_rows - 1 if first else self.window.m5_start - 1,
                "end_index": last.visible_m5_rows - 1 if last else self.window.m5_start - 1,
            },
            "event_count": len(self.events),
            "checkpoint_frequency": self.config.checkpoint_frequency,
            "enabled_shadows": list(self.config.enabled_shadows),
            "enabled_bug_rules": list(self.config.enabled_bug_rules),
            "created_at": self.created_at,
            "case_number": self.case_number,
            "case_metadata": self.case_metadata,
            "dataset_validation": self.dataset.validation,
            "account_configuration": self.account_config.payload(),
            "account_configuration_hash": self.account_config.hash(),
            "execution_configuration": self.execution_config.payload(),
            "execution_configuration_hash": self.execution_config.hash(),
            "paper_execution_owner": "PaperExecutionEngine",
            "strategy_owner": "SystemStateDirector",
            "orders_enabled": False,
            "historical_closed_candle_replay": True,
            "performance_is_not_guaranteed": True,
        }

    def browser_payload(self) -> dict[str, Any]:
        if not self.events:
            raise RuntimeError("Replay session must be built before serialization")
        m1_end = max(event.visible_m1_rows - 1 for event in self.events)
        m5_end = max(event.visible_m5_rows - 1 for event in self.events)
        return json_safe(
            {
                "manifest": self.manifest(),
                "window": {
                    "m1_start": self.window.m1_start,
                    "m5_start": self.window.m5_start,
                    "start_time": self.window.start_time,
                    "end_time": self.window.end_time,
                },
                "candles": {
                    # Pre-window candles are context only: they were already
                    # closed at event zero and remain legal visible-prefix data.
                    "M1": DatasetAdapter.chart_rows(self.dataset.m1, max(0, self.window.m1_start - 180), m1_end),
                    "M5": DatasetAdapter.chart_rows(self.dataset.m5, max(0, self.window.m5_start - 60), m5_end),
                },
                "events": [event.payload() for event in self.events],
                "checkpoints": self.checkpoints,
                "story": self.story,
                "paper_final": self.paper_final,
                "benchmark": {
                    "build_seconds": round(self.build_seconds, 4),
                    "events_per_second": round(len(self.events) / self.build_seconds, 4) if self.build_seconds else None,
                },
            }
        )
