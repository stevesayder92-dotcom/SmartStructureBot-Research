from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from core.evidence_contract import canonical_entry_evidence


@dataclass
class SignalLedgerEvent:
    """
    One immutable decision-time event.

    This records what the bot genuinely knew at one candle.
    It must never be rewritten using later candles.
    """

    symbol: str
    timeframe: Any
    as_of_index: int
    candle_time: Any
    close_price: Optional[float]

    event_type: str
    state: str
    direction: Optional[str]

    setup_id: Optional[str]
    decision_id: Optional[str]

    trend: Optional[str]
    phase: Optional[str]

    setup_status: Optional[str]
    pullback_direction: Optional[str]
    pullback_start_index: Optional[int]
    pullback_end_index: Optional[int]
    pullback_quality: Optional[str]

    protection_available: bool
    protection_state: str
    protection_reasons: str
    protection_type: Optional[str]
    protection_index: Optional[int]
    protection_level: Optional[float]
    protection_intact: Optional[bool]

    invalidation_type: Optional[str]
    invalidation_index: Optional[int]
    invalidation_level: Optional[float]
    invalidation_intact: Optional[bool]

    transition_available: bool
    transition_reasons: str
    transition_state: Optional[str]
    transition_active: Optional[bool]
    transition_recovered: Optional[bool]

    entry_ready: bool
    entry_index: Optional[int]
    entry_price: Optional[float]
    entry_type: Optional[str]
    entry_quality: Optional[str]
    entry_score: Optional[float]
    first_candidate_index: Optional[int]
    first_qualification_index: Optional[int]
    qualification_available_at_index: Optional[int]
    initial_failure_trigger_index: Optional[int]
    active_failure_trigger_index: Optional[int]
    active_failure_trigger_level: Optional[float]
    trigger_updated_at_index: Optional[int]
    trigger_update_count: int
    significance_score: Optional[float]
    raw_significance_score: Optional[float]

    probability_score: Optional[float]
    probability_grade: Optional[str]

    decision_action: Optional[str]
    trade_allowed: bool

    rejection_reason: Optional[str]
    validation_available: bool
    validation_state: str
    validation_reasons: str
    validation_verdict: Optional[str]
    validation_hard_block: Optional[bool]
    risk_modifier: Optional[float]

    causal: bool = True
    post_entry_proof_used: bool = False
    recorded_at: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )


class SignalLedger:
    """
    Append-only event ledger for causal replay.

    Responsibilities:
    - record one system decision per candle;
    - preserve rejected and accepted candidates;
    - prevent duplicate events;
    - identify multiple entries in one historical range;
    - export replay results for auditing and visualization.
    """

    def __init__(self) -> None:
        self._events: List[SignalLedgerEvent] = []
        self._event_keys: set[tuple[Any, ...]] = set()

    @property
    def events(self) -> List[Dict[str, Any]]:
        """
        Return defensive copies so outside code cannot mutate history.
        """
        return [
            deepcopy(asdict(event))
            for event in self._events
        ]

    def record_snapshot(
        self,
        snapshot: Dict[str, Any],
        candle: Dict[str, Any],
    ) -> Optional[SignalLedgerEvent]:
        """
        Convert one SystemStateDirector snapshot into a ledger event.

        Returns None when there is no meaningful setup or decision event.
        """

        meta = snapshot.get("meta", {}) or {}
        market = snapshot.get("market", {}) or {}
        structure = snapshot.get("structure", {}) or {}
        transition = snapshot.get("transition", {}) or {}
        validation = snapshot.get("validation", {}) or {}
        protection = snapshot.get("protection", {}) or {}
        setup = snapshot.get("setup", {}) or {}
        entry = snapshot.get("entry", {}) or {}
        decision = snapshot.get("decision", {}) or {}
        execution = snapshot.get("execution", {}) or {}
        evidence = canonical_entry_evidence(snapshot)

        as_of_index = self._safe_int(meta.get("as_of_index"))

        if as_of_index is None:
            raise ValueError(
                "SignalLedger requires meta.as_of_index"
            )

        published_setup_id = (
            entry.get("setup_id")
            or setup.get("setup_id")
            or meta.get("setup_id")
        )

        setup_status = setup.get("status")
        entry_ready = entry.get("ready") is True

        if entry_ready and published_setup_id is None:
            raise ValueError(
                "SignalLedger requires an upstream setup_id "
                "for every canonical ready entry"
            )
        decision_action = (
            decision.get("action")
            or execution.get("action")
        )

        event_type = self._resolve_event_type(
            setup_status=setup_status,
            entry_ready=entry_ready,
            decision_action=decision_action,
            entry_state=entry.get("state"),
            validation_hard_block=validation.get("hard_block"),
        )

        # Do not flood the ledger with completely inactive candles.
        if event_type == "NO_EVENT":
            return None

        explicit_allowed = decision.get(
            "allowed"
        )

        if explicit_allowed is None:
            explicit_allowed = execution.get(
                "allowed"
            )

        trade_allowed = bool(
            entry_ready
            if explicit_allowed is None
            else explicit_allowed
        )

        rejection_reason = (
            self._resolve_rejection_reason(
                entry=entry,
                validation=validation,
                decision=decision,
                execution=execution,
            )
            if event_type == "ENTRY_REJECTED"
            else None
        )

        close_price = self._safe_float(
            candle.get("close")
        )

        event = SignalLedgerEvent(
            symbol=str(meta.get("symbol", "UNKNOWN")),
            timeframe=meta.get("timeframe"),
            as_of_index=as_of_index,
            candle_time=candle.get("time"),
            close_price=close_price,

            event_type=event_type,
            state=str(
                entry.get("state")
                or setup_status
                or decision_action
                or "UNKNOWN"
            ),
            direction=(
                entry.get("direction")
                or setup.get("trend")
                or market.get("trend")
            ),

            setup_id=(
                published_setup_id
            ),
            decision_id=meta.get("decision_id"),

            trend=market.get("trend"),
            phase=structure.get("phase"),

            setup_status=setup_status,
            pullback_direction=setup.get(
                "pullback_direction"
            ),
            pullback_start_index=self._safe_int(
                setup.get("pullback_start_index")
            ),
            pullback_end_index=self._safe_int(
                setup.get("pullback_end_index")
            ),
            pullback_quality=setup.get("quality"),

            protection_available=bool(
                protection.get("available", False)
            ),
            protection_state=str(
                protection.get(
                    "state",
                    "PROTECTION_UNAVAILABLE",
                )
            ),
            protection_reasons=self._reason_text(
                protection.get("reasons")
            ),
            protection_type=protection.get("type"),
            protection_index=self._safe_int(
                protection.get("index")
            ),
            protection_level=self._safe_float(
                protection.get("level")
            ),
            protection_intact=self._safe_bool(
                protection.get("intact")
            ),

            invalidation_type=entry.get(
                "setup_invalidation_type"
            ),
            invalidation_index=self._safe_int(
                entry.get("setup_invalidation_index")
            ),
            invalidation_level=self._safe_float(
                entry.get("setup_invalidation_level")
            ),
            invalidation_intact=self._safe_bool(
                entry.get("setup_invalidation_intact")
            ),

            transition_available=bool(
                transition.get("available", False)
            ),
            transition_reasons=self._reason_text(
                transition.get("reasons")
            ),
            transition_state=transition.get("state"),
            transition_active=self._safe_bool(
                transition.get("active")
            ),
            transition_recovered=self._safe_bool(
                transition.get("recovered")
            ),

            entry_ready=entry_ready,
            entry_index=self._safe_int(
                entry.get("index")
            ),
            entry_price=self._safe_float(
                entry.get("price")
            ),
            entry_type=entry.get("type"),
            entry_quality=entry.get("quality"),
            entry_score=self._safe_float(
                entry.get("score")
            ),
            first_candidate_index=self._safe_int(
                evidence.get("first_candidate_index")
            ),
            first_qualification_index=self._safe_int(
                evidence.get("first_qualification_index")
            ),
            qualification_available_at_index=self._safe_int(
                evidence.get(
                    "qualification_available_at_index"
                )
            ),
            initial_failure_trigger_index=self._safe_int(
                evidence.get(
                    "initial_failure_trigger_index"
                )
            ),
            active_failure_trigger_index=self._safe_int(
                evidence.get(
                    "active_failure_trigger_index"
                )
            ),
            active_failure_trigger_level=self._safe_float(
                evidence.get(
                    "active_failure_trigger_level"
                )
            ),
            trigger_updated_at_index=self._safe_int(
                evidence.get("trigger_updated_at_index")
            ),
            trigger_update_count=int(
                evidence.get("trigger_update_count", 0)
                or 0
            ),
            significance_score=self._safe_float(
                evidence.get("significance_score")
            ),
            raw_significance_score=self._safe_float(
                evidence.get("raw_significance_score")
            ),

            probability_score=self._safe_float(
                decision.get("probability_score")
            ),
            probability_grade=decision.get(
                "probability_grade"
            ),

            decision_action=decision_action,
            trade_allowed=trade_allowed,

            rejection_reason=rejection_reason,
            validation_available=bool(
                validation.get("available", False)
            ),
            validation_state=str(
                validation.get(
                    "state",
                    "VALIDATION_UNAVAILABLE",
                )
            ),
            validation_reasons=self._reason_text(
                validation.get("reasons")
            ),
            validation_verdict=validation.get("verdict"),
            validation_hard_block=self._safe_bool(
                validation.get("hard_block")
            ),
            risk_modifier=self._safe_float(
                validation.get("risk_modifier")
            ),

            causal=bool(
                entry.get("causal", True)
                and setup.get("causal", True)
                and transition.get(
                    "causal_valid",
                    True,
                )
                and validation.get(
                    "causal_valid",
                    True,
                )
                and protection.get(
                    "causal_valid",
                    True,
                )
            ),
            post_entry_proof_used=bool(
                decision.get("post_entry_proof_used", False)
            ),
        )

        key = self._event_key(event)

        if key in self._event_keys:
            return None

        self._events.append(event)
        self._event_keys.add(key)

        return deepcopy(event)

    def record_event(
        self,
        event: SignalLedgerEvent,
    ) -> bool:
        """
        Directly append a prebuilt event.

        Returns False when the event already exists.
        """

        key = self._event_key(event)

        if key in self._event_keys:
            return False

        self._events.append(deepcopy(event))
        self._event_keys.add(key)

        return True

    def entry_events(
        self,
        allowed_only: bool = False,
    ) -> List[Dict[str, Any]]:
        result = []

        for event in self._events:
            if event.event_type != "ENTRY_SIGNAL":
                continue

            if allowed_only and not event.trade_allowed:
                continue

            result.append(deepcopy(asdict(event)))

        return result

    def rejected_entries(self) -> List[Dict[str, Any]]:
        return [
            deepcopy(asdict(event))
            for event in self._events
            if event.event_type == "ENTRY_REJECTED"
        ]

    def setup_events(self) -> List[Dict[str, Any]]:
        return [
            deepcopy(asdict(event))
            for event in self._events
            if event.event_type in {
                "SETUP_ACTIVE",
                "SETUP_CONFIRMED",
                "ENTRY_SIGNAL",
                "ENTRY_REJECTED",
                "SETUP_INVALIDATED",
            }
        ]

    def to_dataframe(self) -> pd.DataFrame:
        if not self._events:
            return pd.DataFrame()

        return pd.DataFrame(
            [asdict(event) for event in self._events]
        )

    def export_csv(self, path: str) -> str:
        dataframe = self.to_dataframe()
        dataframe.to_csv(path, index=False)
        return path

    def summary(self) -> Dict[str, Any]:
        total_events = len(self._events)

        entry_signals = [
            event
            for event in self._events
            if event.event_type == "ENTRY_SIGNAL"
        ]

        allowed_entries = [
            event
            for event in entry_signals
            if event.trade_allowed
        ]

        rejected_entries = [
            event
            for event in self._events
            if event.event_type == "ENTRY_REJECTED"
        ]

        non_causal_events = [
            event
            for event in self._events
            if not event.causal
        ]

        proof_leak_events = [
            event
            for event in self._events
            if event.post_entry_proof_used
        ]

        return {
            "total_events": total_events,
            "entry_signals": len(entry_signals),
            "allowed_entries": len(allowed_entries),
            "rejected_entries": len(rejected_entries),
            "non_causal_events": len(non_causal_events),
            "post_entry_proof_leaks": len(
                proof_leak_events
            ),
            "first_event_index": (
                self._events[0].as_of_index
                if self._events
                else None
            ),
            "last_event_index": (
                self._events[-1].as_of_index
                if self._events
                else None
            ),
        }

    @staticmethod
    def _resolve_event_type(
        setup_status: Any,
        entry_ready: bool,
        decision_action: Any,
        entry_state: Any,
        validation_hard_block: Any,
    ) -> str:
        action = str(decision_action or "").upper()
        state = str(entry_state or "").upper()
        setup = str(setup_status or "").upper()

        if entry_ready and action in {
            "ENTER_TRADE",
            "BUY",
            "SELL",
        }:
            return "ENTRY_SIGNAL"
        
        if (
            entry_ready
            and state in {
                "ENTRY_READY",
                "ENTRY_VALIDATED",
            }
            and not action
        ):
            return "ENTRY_SIGNAL"

        if entry_ready and action in {
            "NO_TRADE",
            "BLOCK",
            "REJECT",
        }:
            return "ENTRY_REJECTED"

        if state.startswith("BLOCKED_"):
            return "ENTRY_REJECTED"

        if validation_hard_block is True and setup:
            return "SETUP_INVALIDATED"

        if setup == "CONFIRMED":
            return "SETUP_CONFIRMED"

        if setup in {
            "ACTIVE",
            "DEVELOPING",
            "WAITING_FOR_CONFIRMATION",
            "COUNTER_MOVE_ACTIVE",
        }:
            return "SETUP_ACTIVE"

        return "NO_EVENT"

    @staticmethod
    def _resolve_rejection_reason(
        entry: Dict[str, Any],
        validation: Dict[str, Any],
        decision: Dict[str, Any],
        execution: Dict[str, Any],
    ) -> Optional[str]:
        reason_candidates = [
            entry.get("reason"),
            entry.get("rejection_reason"),
            validation.get("hard_block_reason"),
            decision.get("reason"),
            execution.get("reason"),
        ]

        for candidate in reason_candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()

            if isinstance(candidate, list) and candidate:
                return " | ".join(
                    str(item)
                    for item in candidate
                )

        state = entry.get("state")

        if isinstance(state, str) and state.startswith(
            "BLOCKED_"
        ):
            return state

        return None

    @staticmethod
    def _event_key(
        event: SignalLedgerEvent,
    ) -> tuple[Any, ...]:
        """
        Preserve only the first actionable entry for each setup.

        Setup lifecycle events remain candle-specific so replay inspection
        can still show how a setup developed through time.
        """

        if (
            event.event_type == "ENTRY_SIGNAL"
            and event.setup_id is not None
        ):
            return (
                event.symbol,
                str(event.timeframe),
                event.event_type,
                event.setup_id,
            )

        return (
            event.symbol,
            str(event.timeframe),
            event.as_of_index,
            event.event_type,
            event.setup_id,
            event.entry_index,
            event.decision_action,
        )

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        if value is None:
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        if value is None:
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_bool(value: Any) -> Optional[bool]:
        if value is None:
            return None

        return bool(value)

    @staticmethod
    def _reason_text(value: Any) -> str:
        if isinstance(value, str):
            return value

        if isinstance(value, list):
            return " | ".join(
                str(item)
                for item in value
            )

        return ""
