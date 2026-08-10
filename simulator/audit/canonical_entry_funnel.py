from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable
import json

import pandas as pd

from simulator.models.schema import json_safe, stable_hash


UNAVAILABLE = "UNAVAILABLE"


def _present(value: Any) -> Any:
    return UNAVAILABLE if value is None else value


def _iso(timestamp: Any) -> str:
    if timestamp in (None, UNAVAILABLE):
        return UNAVAILABLE
    return datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat()


def _close_timestamp(frame: pd.DataFrame, index: Any, seconds: int) -> Any:
    if index in (None, UNAVAILABLE):
        return UNAVAILABLE
    value = int(index)
    if value < 0 or value >= len(frame):
        return UNAVAILABLE
    return float(frame.iloc[value]["time"]) + float(seconds)


def _open_timestamp(frame: pd.DataFrame, index: Any) -> Any:
    if index in (None, UNAVAILABLE):
        return UNAVAILABLE
    value = int(index)
    if value < 0 or value >= len(frame):
        return UNAVAILABLE
    return float(frame.iloc[value]["time"])


def _minutes(start: Any, end: Any) -> Any:
    if start in (None, UNAVAILABLE) or end in (None, UNAVAILABLE):
        return UNAVAILABLE
    return round((float(end) - float(start)) / 60.0, 6)


def _candles(start: Any, end: Any, seconds: int) -> Any:
    minutes = _minutes(start, end)
    if minutes == UNAVAILABLE:
        return UNAVAILABLE
    return round(float(minutes) * 60.0 / float(seconds), 6)


def classify_m1_event(state: str) -> str:
    """Map an exact engine event to the mandated reporting taxonomy."""
    normalized = str(state or "").upper()
    if normalized in {
        "M1_TRIGGER_SIDE_SWING_BEFORE_PARENT_ACTIVE",
        "M1_TRIGGER_BEFORE_PARENT_ACTIVE_REJECTED",
    }:
        return "M1_TRIGGER_SIDE_SWING_BEFORE_PARENT_ACTIVE"
    if normalized == "M1_BOS_BEFORE_PARENT_ACTIVE_REJECTED":
        return "M1_BODY_CLOSE_BOS_BEFORE_PARENT_ACTIVE"
    if normalized == "M1_ENTRY_FOUND":
        return "M1_TRIGGER_WHILE_PARENT_ACTIVE"
    if normalized in {
        "M1_REJECTED_NO_SYNCHRONIZED_ACTIVE_WINDOW",
        "M1_TRIGGER_AFTER_PARENT_EXPIRED_REJECTED",
    }:
        return "M1_TRIGGER_AFTER_PARENT_EXPIRED"
    if normalized in {
        "M1_RANDOM_BOS_REJECTED_NO_COUNTER_STRUCTURE",
        "M1_RANDOM_BOS_REJECTED_INCOMPLETE_SEQUENCE",
        "M1_RANDOM_BOS_REJECTED_ONE_CANDLE_NOISE",
        "M1_RANDOM_BOS_REJECTED_MICRO_NOISE",
    }:
        return "M1_TRIGGER_INVALID_MICRO_NOISE"
    if normalized == "M1_WICK_ONLY_BOS_REJECTED":
        return "M1_TRIGGER_WICK_ONLY"
    if normalized == "M1_WRONG_BODY_DIRECTION_REJECTED":
        return "M1_TRIGGER_WRONG_DIRECTION"
    return "OTHER"


def _first_reason(root: dict[str, Any]) -> str:
    reasons = root.get("reasons") or root.get("reason") or []
    if isinstance(reasons, str):
        return reasons
    return str(reasons[0]) if reasons else UNAVAILABLE


class CanonicalEntryFunnelObserver:
    """
    Non-mutating projection of canonical engine and immutable event outputs.

    The observer deliberately contains no market-structure, qualification,
    entry or management rules. Derived fields are limited to timestamps,
    latency, deduplication and count reconciliation over canonical values.
    """

    STAGES = (
        "HTF_CONTEXT",
        "ORIGIN_BOS",
        "PROTECTED_STRUCTURE",
        "RETRACEMENT_BIRTH",
        "RETRACEMENT_SIGNIFICANCE",
        "RETRACEMENT_QUALIFICATION",
        "PARENT_ACTIVATION",
        "M1_CHILD_MONITORING",
        "M1_TRIGGER_CANDIDATE",
        "M5_TRIGGER_CANDIDATE",
        "ENTRY_VALIDATION",
        "SYSTEM_DIRECTOR_COMMITMENT",
        "PAPER_EXECUTION",
    )

    def __init__(self) -> None:
        self.funnel_rows: list[dict[str, Any]] = []
        self.parent_rows: list[dict[str, Any]] = []
        self.m1_rows: list[dict[str, Any]] = []
        self.setup_rows: list[dict[str, Any]] = []
        self._m1_keys: set[str] = set()
        self._setup_ids: set[str] = set()
        self.non_mutation_checks: list[bool] = []

    @staticmethod
    def _hash_inputs(values: Iterable[Any]) -> str:
        return stable_hash([json_safe(value) for value in values])

    def observe(
        self,
        *,
        symbol: str,
        candidate: dict[str, Any],
        context: dict[str, Any],
        m5_data: pd.DataFrame,
        m1_data: pd.DataFrame,
        parent: dict[str, Any] | None = None,
        m1_report: dict[str, Any] | None = None,
        director_snapshot: dict[str, Any] | None = None,
        director_action: dict[str, Any] | None = None,
        paper_result: dict[str, Any] | None = None,
    ) -> None:
        original_values = (
            candidate,
            context,
            parent,
            m1_report,
            director_snapshot,
            director_action,
            paper_result,
        )
        before = self._hash_inputs(original_values)
        candidate = deepcopy(candidate)
        context = deepcopy(context)
        parent = deepcopy(parent or {})
        m1_report = deepcopy(m1_report or {})
        snapshot = deepcopy(director_snapshot or {})
        action = deepcopy(director_action or {})
        paper = deepcopy(paper_result or {})

        setup_id = str(candidate.get("setup_id") or UNAVAILABLE)
        direction = str(candidate.get("direction") or UNAVAILABLE)
        sequence_id = str(
            (snapshot.get("management") or snapshot.get("trailing_protection") or {}).get(
                "sequence_id"
            )
            or setup_id
        )
        attempt = int(
            ((m1_report.get("entry") or {}).get("attempt_number"))
            or ((snapshot.get("entry") or {}).get("attempt_number"))
            or 1
        )
        entry_index = candidate.get("entry_index")
        m5_entry_time = _close_timestamp(m5_data, entry_index, 300)
        anchor = dict(candidate.get("anchor") or {})
        counter = dict(candidate.get("counter") or {})
        trigger = dict(candidate.get("trigger") or {})
        fibonacci = dict(candidate.get("fibonacci") or {})
        origin_bos = dict(candidate.get("origin_bos") or {})
        birth_index = anchor.get("confirmed_at_index")
        birth_time = _close_timestamp(m5_data, birth_index, 300)
        counter_index = counter.get("confirmed_at_index")
        counter_time = _close_timestamp(m5_data, counter_index, 300)
        qualification_index = candidate.get("qualified_at")
        qualification_time = _close_timestamp(m5_data, qualification_index, 300)
        parent_active_time = parent.get("active_time", UNAVAILABLE)
        parent_armed_time = parent.get("armed_time", UNAVAILABLE)
        context_direction = str(context.get("approved_direction") or "NEUTRAL")
        htf_aligned = bool(
            context.get("available") and context_direction == direction
        )

        m1_entry = dict(m1_report.get("entry") or {})
        m1_ready = bool(m1_report.get("entry_ready") and m1_entry)
        canonical_entry = dict(snapshot.get("entry") or {})
        director_ready = bool(canonical_entry.get("ready"))
        actual_entry_time = (
            m1_entry.get("entry_time")
            if m1_ready
            else m5_entry_time
            if director_ready
            else UNAVAILABLE
        )
        actual_entry_timeframe = (
            "M1" if m1_ready else "M5" if director_ready else UNAVAILABLE
        )
        validation = dict(snapshot.get("validation") or {})
        execution = dict(snapshot.get("execution") or {})
        paper_canonical = dict(paper.get("canonical") or {})
        paper_action = paper_canonical.get(
            "primary_execution_action", UNAVAILABLE
        )

        if setup_id in self._setup_ids:
            raise ValueError(f"Duplicate independent setup observation: {setup_id}")
        self._setup_ids.add(setup_id)

        first_blocking_owner = UNAVAILABLE
        blocker_code = UNAVAILABLE
        blocker_reason = UNAVAILABLE
        if not htf_aligned:
            first_blocking_owner = context.get("owner", "HTFContextEngine")
            blocker_reason = context.get("state", UNAVAILABLE)
        elif not parent:
            first_blocking_owner = "SystemStateDirector"
            blocker_reason = "PARENT_CONTRACT_UNAVAILABLE"
        elif snapshot and not director_ready and not m1_ready:
            first_blocking_owner = (
                validation.get("owner")
                or canonical_entry.get("owner")
                or "SystemStateDirector"
            )
            blocker_code = (
                validation.get("hard_block_reason")
                or (validation.get("hard_blockers") or [UNAVAILABLE])[0]
            )
            blocker_reason = (
                validation.get("state")
                or canonical_entry.get("state")
                or UNAVAILABLE
            )

        common = {
            "symbol": symbol,
            "event_timestamp": _iso(m5_entry_time),
            "m1_index": _present(m1_entry.get("entry_index")),
            "m5_index": _present(entry_index),
            "setup_id": setup_id,
            "sequence_id": sequence_id,
            "attempt": attempt,
            "direction": direction,
            "director_action": action.get(
                "committed_action",
                (snapshot.get("decision") or {}).get("action", UNAVAILABLE),
            ),
            "first_blocking_waiting_owner": first_blocking_owner,
            "exact_canonical_blocker_code": blocker_code,
            "canonical_blocker_reason": blocker_reason,
            "causal_valid": bool(
                candidate.get("fibonacci", {}).get("causal_valid", True)
                and context.get("causal_valid", True)
                and parent.get("causal_valid", True)
                and m1_report.get("causal_valid", True)
                and (snapshot.get("entry") or {}).get("causal", True)
            ),
            "closed_candles_only": bool(
                parent.get("closed_candles_only", True)
                and m1_report.get("closed_candles_only", True)
            ),
            "future_data_used": bool(m1_report.get("future_data_used", False)),
        }

        stage_values = {
            "HTF_CONTEXT": (
                context.get("state", UNAVAILABLE),
                context_direction,
                context.get("owner", "HTFContextEngine"),
            ),
            "ORIGIN_BOS": (
                origin_bos.get("type", UNAVAILABLE),
                _present(origin_bos.get("direction")),
                "ExpertStrategyEngine",
            ),
            "PROTECTED_STRUCTURE": (
                parent.get("state", UNAVAILABLE),
                _present(parent.get("dominant_protection_intact")),
                parent.get("owner", "SystemStateDirector") if parent else UNAVAILABLE,
            ),
            "RETRACEMENT_BIRTH": (
                "PULLBACK_ORIGIN_CONFIRMED" if anchor else UNAVAILABLE,
                _present(anchor.get("classification") or anchor.get("side")),
                "QualifiedRetracementEngine",
            ),
            "RETRACEMENT_SIGNIFICANCE": (
                _present(fibonacci.get("zone") or fibonacci.get("remaining_zone")),
                _present(
                    fibonacci.get(
                        "retracement_depth_ratio", fibonacci.get("depth")
                    )
                ),
                "FibonacciContract",
            ),
            "RETRACEMENT_QUALIFICATION": (
                "QUALIFIED" if qualification_index is not None else UNAVAILABLE,
                _present(qualification_index),
                "QualifiedRetracementEngine",
            ),
            "PARENT_ACTIVATION": (
                parent.get("state", UNAVAILABLE),
                _present(parent_active_time),
                parent.get("owner", UNAVAILABLE),
            ),
            "M1_CHILD_MONITORING": (
                m1_report.get("state", UNAVAILABLE),
                _present(m1_report.get("m1_was_monitored")),
                m1_report.get("owner", UNAVAILABLE),
            ),
            "M1_TRIGGER_CANDIDATE": (
                (m1_entry.get("state") if m1_ready else m1_report.get("state"))
                or UNAVAILABLE,
                _present(m1_report.get("entry_ready")),
                m1_report.get("owner", UNAVAILABLE),
            ),
            "M5_TRIGGER_CANDIDATE": (
                "M5_CLOSE_BOS_CANDIDATE",
                _present(candidate.get("entry_price")),
                "ContinuationEngine",
            ),
            "ENTRY_VALIDATION": (
                validation.get("state", UNAVAILABLE),
                _present(validation.get("allowed")),
                validation.get("owner", UNAVAILABLE),
            ),
            "SYSTEM_DIRECTOR_COMMITMENT": (
                canonical_entry.get("state", UNAVAILABLE),
                action.get(
                    "committed_action",
                    (snapshot.get("decision") or {}).get("action", UNAVAILABLE),
                ),
                "SystemStateDirector",
            ),
            "PAPER_EXECUTION": (
                execution.get("action", UNAVAILABLE),
                paper_action,
                "PaperExecutionReplayService" if paper else UNAVAILABLE,
            ),
        }
        for stage in self.STAGES:
            state, recommendation, owner = stage_values[stage]
            self.funnel_rows.append(
                {
                    **common,
                    "current_pipeline_stage": stage,
                    "engine_state": state,
                    "engine_recommendation": recommendation,
                    "engine_owner": owner,
                    "stage_available": state != UNAVAILABLE,
                }
            )

        first_m1_trigger_time = UNAVAILABLE
        first_m1_available_time = UNAVAILABLE
        first_valid_m1_time = (
            m1_entry.get("entry_time", UNAVAILABLE) if m1_ready else UNAVAILABLE
        )
        m1_events = list(m1_report.get("rejections") or [])
        if m1_ready:
            m1_events.append(m1_entry)
        for ordinal, event in enumerate(m1_events):
            state = str(event.get("state") or "OTHER")
            event_index = event.get("m1_index", event.get("entry_index"))
            event_time = (
                event.get("entry_time")
                if event.get("entry_time") is not None
                else _close_timestamp(m1_data, event_index, 60)
            )
            trigger_index = event.get(
                "trigger_index", event.get("failure_trigger_index")
            )
            trigger_time = (
                event.get("trigger_time")
                if event.get("trigger_time") is not None
                else _open_timestamp(m1_data, trigger_index)
            )
            trigger_available_index = event.get(
                "trigger_available_at_index",
                event.get("failure_trigger_available_at_index", event_index),
            )
            trigger_available_time = _close_timestamp(
                m1_data, trigger_available_index, 60
            )
            if trigger_time != UNAVAILABLE and (
                first_m1_trigger_time == UNAVAILABLE
                or float(trigger_time) < float(first_m1_trigger_time)
            ):
                first_m1_trigger_time = trigger_time
            if trigger_available_time != UNAVAILABLE and (
                first_m1_available_time == UNAVAILABLE
                or float(trigger_available_time) < float(first_m1_available_time)
            ):
                first_m1_available_time = trigger_available_time
            classification = classify_m1_event(state)
            event_key = stable_hash(
                [
                    symbol,
                    setup_id,
                    state,
                    _present(event.get("trigger_index")),
                    _present(event_index),
                    _present(event.get("failure_trigger_price")),
                ]
            )
            if event_key in self._m1_keys:
                continue
            self._m1_keys.add(event_key)
            hard_blockers = list(event.get("hard_blockers") or [])
            parent_qualified_at_event = (
                bool(float(event_time) >= float(qualification_time))
                if event_time != UNAVAILABLE and qualification_time != UNAVAILABLE
                else UNAVAILABLE
            )
            gate_state = (
                "M5_PARENT_NOT_ACTIVE"
                if "M5_PARENT_NOT_ACTIVE" in hard_blockers
                else "M5_PARENT_ACTIVE"
                if parent and event_time != UNAVAILABLE
                and parent_active_time != UNAVAILABLE
                and float(event_time) >= float(parent_active_time)
                else UNAVAILABLE
            )
            self.m1_rows.append(
                {
                    "symbol": symbol,
                    "setup_id": setup_id,
                    "sequence_id": sequence_id,
                    "attempt": attempt,
                    "direction": direction,
                    "event_ordinal": ordinal,
                    "event_key": event_key,
                    "canonical_engine_state": state,
                    "classification": classification,
                    "event_timestamp": _iso(event_time),
                    "event_index": _present(event_index),
                    "trigger_timestamp": _iso(trigger_time),
                    "trigger_index": _present(trigger_index),
                    "trigger_available_timestamp": _iso(trigger_available_time),
                    "trigger_available_at_index": _present(trigger_available_index),
                    "parent_setup_id": setup_id,
                    "parent_retracement_state": UNAVAILABLE,
                    "parent_qualified": parent_qualified_at_event,
                    "parent_qualification_timestamp": _iso(qualification_time),
                    "parent_qualification_index": _present(qualification_index),
                    "m1_parent_gate_state": gate_state,
                    "trigger_relevance_state": state,
                    "bos_body_close_valid": (
                        True
                        if state == "M1_ENTRY_FOUND"
                        else False
                        if state in {
                            "M1_WICK_ONLY_BOS_REJECTED",
                            "M1_WRONG_BODY_DIRECTION_REJECTED",
                        }
                        else UNAVAILABLE
                    ),
                    "wick_only": state == "M1_WICK_ONLY_BOS_REJECTED",
                    "child_reset_sequence_state": UNAVAILABLE,
                    "protected_structure_status_at_trigger": UNAVAILABLE,
                    "fib_relevance_at_trigger": UNAVAILABLE,
                    "same_trigger_later_stale": UNAVAILABLE,
                    "eventual_canonical_entry_timestamp": _iso(actual_entry_time),
                    "eventual_canonical_entry_timeframe": actual_entry_timeframe,
                    "hard_blockers": json.dumps(hard_blockers),
                    "canonical_reason": event.get("reason", UNAVAILABLE),
                    "causal_valid": bool(event.get("causal_valid", True)),
                    "future_data_used": bool(event.get("future_data_used", False)),
                }
            )

        relation = UNAVAILABLE
        if first_m1_available_time != UNAVAILABLE and qualification_time != UNAVAILABLE:
            if float(first_m1_available_time) < float(qualification_time):
                relation = "BEFORE_QUALIFICATION"
            elif float(first_m1_available_time) == float(qualification_time):
                relation = "ON_QUALIFICATION"
            else:
                relation = "AFTER_QUALIFICATION"
        self.parent_rows.append(
            {
                "symbol": symbol,
                "setup_id": setup_id,
                "sequence_id": sequence_id,
                "attempt": attempt,
                "direction": direction,
                "retracement_birth_timestamp": _iso(birth_time),
                "retracement_birth_index": _present(birth_index),
                "first_meaningful_counter_timestamp": _iso(counter_time),
                "first_meaningful_counter_index": _present(counter_index),
                "first_legal_qualification_timestamp": _iso(qualification_time),
                "first_legal_qualification_index": _present(qualification_index),
                "parent_armed_timestamp": _iso(parent_armed_time),
                "parent_active_timestamp": _iso(parent_active_time),
                "first_m1_trigger_timestamp": _iso(first_m1_trigger_time),
                "first_m1_trigger_available_timestamp": _iso(
                    first_m1_available_time
                ),
                "first_valid_m1_body_close_bos_timestamp": _iso(first_valid_m1_time),
                "first_m5_bos_timestamp": _iso(m5_entry_time),
                "actual_entry_timestamp": _iso(actual_entry_time),
                "actual_entry_timeframe": actual_entry_timeframe,
                "birth_to_qualification_minutes": _minutes(
                    birth_time, qualification_time
                ),
                "birth_to_qualification_m5_candles": _candles(
                    birth_time, qualification_time, 300
                ),
                "first_m1_trigger_availability_to_qualification_minutes": _minutes(
                    first_m1_available_time, qualification_time
                ),
                "first_m1_trigger_availability_to_qualification_m1_candles": _candles(
                    first_m1_available_time, qualification_time, 60
                ),
                "qualification_to_actual_entry_minutes": _minutes(
                    qualification_time, actual_entry_time
                ),
                "qualification_to_actual_entry_m1_candles": _candles(
                    qualification_time, actual_entry_time, 60
                ),
                "first_m1_trigger_relation": relation,
                "early_trigger_became_stale_before_qualification": UNAVAILABLE,
                "m5_fallback_after_earlier_m1_trigger": bool(
                    actual_entry_timeframe == "M5"
                    and first_m1_available_time != UNAVAILABLE
                    and float(first_m1_available_time) < float(m5_entry_time)
                ),
                "htf_context_state": context.get("state", UNAVAILABLE),
                "htf_aligned": htf_aligned,
                "parent_gate_available": bool(parent),
                "director_entry_ready": director_ready,
                "paper_execution_action": paper_action,
                "origin_bos_index": _present(origin_bos.get("index")),
                "protected_structure_index": UNAVAILABLE,
                "protected_structure_level": _present(
                    parent.get("dominant_protection_level")
                ),
                "fib_zero_index": _present(fibonacci.get("fib_zero_index")),
                "retracement_depth_ratio": _present(
                    fibonacci.get("retracement_depth_ratio", fibonacci.get("depth"))
                ),
                "significance_score": UNAVAILABLE,
                "counter_structure_count": UNAVAILABLE,
                "duration_component": UNAVAILABLE,
                "overlap_component": UNAVAILABLE,
                "structure_component": UNAVAILABLE,
                "causal_valid": common["causal_valid"],
            }
        )
        self.setup_rows.append(
            {
                "symbol": symbol,
                "setup_id": setup_id,
                "direction": direction,
                "htf_aligned": htf_aligned,
                "retracement_born": bool(anchor),
                "retracement_qualified": qualification_index is not None,
                "parent_gate_active": bool(parent),
                "m1_event_count": len(
                    [row for row in self.m1_rows if row["setup_id"] == setup_id]
                ),
                "m1_entry_ready": m1_ready,
                "m5_entry_ready": director_ready,
                "actual_entry_timeframe": actual_entry_timeframe,
                "actual_entry_timestamp": _iso(actual_entry_time),
                "director_action": action.get("committed_action", UNAVAILABLE),
                "paper_execution_action": paper_action,
                "first_blocking_waiting_owner": first_blocking_owner,
                "canonical_blocker_code": blocker_code,
                "canonical_blocker_reason": blocker_reason,
                "causal_valid": common["causal_valid"],
                "future_data_used": common["future_data_used"],
                "lifecycle_explainable": True,
            }
        )
        after = self._hash_inputs(original_values)
        self.non_mutation_checks.append(before == after)
        if before != after:
            raise AssertionError("Audit observer mutated a canonical input")

    def summary(self) -> dict[str, Any]:
        setups = list(self.setup_rows)
        m1 = list(self.m1_rows)
        classifications = Counter(row["classification"] for row in m1)
        engine_states = Counter(row["canonical_engine_state"] for row in m1)
        early = [
            row
            for row in m1
            if row["classification"]
            == "M1_TRIGGER_SIDE_SWING_BEFORE_PARENT_ACTIVE"
        ]
        relevant = [
            row
            for row in m1
            if row["classification"]
            in {
                "M1_TRIGGER_SIDE_SWING_BEFORE_PARENT_ACTIVE",
                "M1_TRIGGER_WHILE_PARENT_ACTIVE",
                "M1_TRIGGER_AFTER_PARENT_EXPIRED",
            }
        ]
        aligned = [row for row in setups if row["htf_aligned"]]
        parent_active = [row for row in setups if row["parent_gate_active"]]
        entries = [
            row
            for row in setups
            if row["actual_entry_timeframe"] in {"M1", "M5"}
        ]
        before_setup_ids = {row["setup_id"] for row in early}
        before_setups = [row for row in setups if row["setup_id"] in before_setup_ids]
        m5_after_early = [
            row
            for row in before_setups
            if row["actual_entry_timeframe"] == "M5"
        ]
        never_entry = [
            row
            for row in before_setups
            if row["actual_entry_timeframe"] not in {"M1", "M5"}
        ]
        stage_losses = {
            "HTF_CONTEXT": len(setups) - len(aligned),
            "PARENT_ACTIVATION": len(aligned) - len(parent_active),
            "SYSTEM_DIRECTOR_COMMITMENT": len(parent_active) - len(entries),
        }
        bottleneck_stage = max(stage_losses, key=stage_losses.get) if setups else UNAVAILABLE
        blocker_counter = Counter(
            str(row["canonical_blocker_reason"])
            for row in setups
            if row["canonical_blocker_reason"] != UNAVAILABLE
        )
        dominant_reason = (
            blocker_counter.most_common(1)[0][0] if blocker_counter else UNAVAILABLE
        )
        if bottleneck_stage == "HTF_CONTEXT":
            reason_category = "INTENTIONAL_STRATEGY_RULE"
        elif bottleneck_stage == "PARENT_ACTIVATION":
            reason_category = "IMPLEMENTATION_MISMATCH_OR_DATA_LIMITATION"
        elif bottleneck_stage == "SYSTEM_DIRECTOR_COMMITMENT":
            reason_category = "CANONICAL_VALIDATION_OR_MANAGEMENT_RULE"
        else:
            reason_category = "UNKNOWN"
        return json_safe(
            {
                "scope": {
                    "candidate_source": "FULL_PRODUCTION_M5_SCAN_BOTH_DIRECTIONS",
                    "downsampled": False,
                    "important_limitation": (
                        "The current production engine exposes terminal M5 candidate "
                        "lifecycles, not a complete immutable stream of every abandoned "
                        "pre-qualification retracement. Counts below describe that exact "
                        "observable candidate population; unavailable broader counts are "
                        "not inferred."
                    ),
                },
                "answers": {
                    "independent_setups_in_observable_candidate_population": len(setups),
                    "retracements_born_in_observable_candidate_population": sum(
                        bool(row["retracement_born"]) for row in setups
                    ),
                    "all_retracements_born_including_abandoned": UNAVAILABLE,
                    "retracements_qualified_in_observable_candidate_population": sum(
                        bool(row["retracement_qualified"]) for row in setups
                    ),
                    "parent_gates_activated": len(parent_active),
                    "relevant_m1_trigger_events": len(relevant),
                    "unique_setups_with_relevant_m1_triggers": len(
                        {row["setup_id"] for row in relevant}
                    ),
                    "m1_triggers_before_parent_activation_events": len(early),
                    "unique_setups_affected_by_early_triggers": len(before_setup_ids),
                    "early_triggers_later_stale": UNAVAILABLE,
                    "early_trigger_setups_later_receiving_m5_entry": len(m5_after_early),
                    "early_trigger_setups_never_receiving_entry": len(never_entry),
                    "largest_unique_setup_loss_stage": bottleneck_stage,
                    "largest_unique_setup_loss_count": stage_losses.get(
                        bottleneck_stage, 0
                    ),
                    "dominant_reason": dominant_reason,
                    "dominant_reason_category": reason_category,
                    "actual_future_leak_detected": bool(
                        any(not row["causal_valid"] for row in setups)
                        or any(row["future_data_used"] for row in setups)
                    ),
                },
                "counts": {
                    "candidate_setups": len(setups),
                    "htf_aligned_candidate_setups": len(aligned),
                    "parent_active_setups": len(parent_active),
                    "canonical_entry_setups": len(entries),
                    "m1_events": len(m1),
                    "m1_event_classifications": dict(sorted(classifications.items())),
                    "m1_canonical_engine_states": dict(sorted(engine_states.items())),
                    "stage_losses_unique_setups": stage_losses,
                    "funnel_rows": len(self.funnel_rows),
                    "expected_funnel_rows": len(setups) * len(self.STAGES),
                },
                "integrity": {
                    "observer_non_mutation": all(self.non_mutation_checks),
                    "every_setup_explainable": all(
                        bool(row["lifecycle_explainable"]) for row in setups
                    ),
                    "unique_setup_count_reconciles": len(self._setup_ids) == len(setups),
                    "m1_event_count_reconciles": len(self._m1_keys) == len(m1),
                    "funnel_count_reconciles": len(self.funnel_rows)
                    == len(setups) * len(self.STAGES),
                    "multiple_m1_events_are_not_multiple_setups": len(m1)
                    >= len({row["setup_id"] for row in m1}),
                    "order_api_called": False,
                },
            }
        )

    def blocker_counts(self) -> list[dict[str, Any]]:
        counts: Counter[tuple[str, str, str]] = Counter()
        setup_ids: dict[tuple[str, str, str], set[str]] = {}
        for row in self.setup_rows:
            reason = str(row["canonical_blocker_reason"])
            if reason == UNAVAILABLE:
                continue
            key = (
                str(row["first_blocking_waiting_owner"]),
                str(row["canonical_blocker_code"]),
                reason,
            )
            counts[key] += 1
            setup_ids.setdefault(key, set()).add(str(row["setup_id"]))
        for row in self.m1_rows:
            blockers = json.loads(row["hard_blockers"] or "[]")
            if not blockers:
                continue
            key = (
                "M1ChildStructureEngine",
                str(blockers[0]),
                str(row["canonical_engine_state"]),
            )
            counts[key] += 1
            setup_ids.setdefault(key, set()).add(str(row["setup_id"]))
        return [
            {
                "owner": key[0],
                "canonical_blocker_code": key[1],
                "canonical_reason": key[2],
                "event_count": count,
                "unique_setup_count": len(setup_ids[key]),
            }
            for key, count in sorted(
                counts.items(), key=lambda item: (-item[1], item[0])
            )
        ]
