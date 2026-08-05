from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd


@dataclass(frozen=True)
class ReplayInspectionRecord:
    """
    Human-review record for one unique causal entry signal.
    """

    sequence: int
    total_entries: int

    symbol: str
    timeframe: Any

    setup_id: Optional[str]
    entry_index: int
    candle_time: Any

    direction: Optional[str]
    trend: Optional[str]
    phase: Optional[str]

    state: Optional[str]
    setup_status: Optional[str]

    pullback_start_index: Optional[int]
    pullback_end_index: Optional[int]
    pullback_direction: Optional[str]
    pullback_quality: Optional[str]

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

    invalidation_type: Optional[str]
    invalidation_index: Optional[int]
    invalidation_level: Optional[float]
    invalidation_intact: Optional[bool]

    protection_available: bool
    protection_state: str
    protection_reasons: str
    protection_type: Optional[str]
    protection_index: Optional[int]
    protection_level: Optional[float]
    protection_intact: Optional[bool]

    transition_available: bool
    transition_reasons: str
    transition_state: Optional[str]
    transition_active: Optional[bool]
    transition_recovered: Optional[bool]

    validation_available: bool
    validation_state: str
    validation_reasons: str
    validation_verdict: Optional[str]
    validation_hard_block: Optional[bool]
    risk_modifier: Optional[float]

    decision_action: Optional[str]
    trade_allowed: bool
    causal: bool
    rejection_reason: Optional[str]


class ReplayInspector:
    """
    Convert causal ledger entry events into human-review reports.

    This class does not simulate trade outcomes and never looks forward
    to decide whether an entry was valid. It only presents what the
    system knew at the original decision candle.
    """

    def __init__(
        self,
        *,
        data: pd.DataFrame,
        ledger: Any,
    ) -> None:
        if not isinstance(data, pd.DataFrame):
            raise TypeError(
                "ReplayInspector data must be a pandas DataFrame"
            )

        if data.empty:
            raise ValueError(
                "ReplayInspector cannot inspect empty market data"
            )

        required_columns = {
            "open",
            "high",
            "low",
            "close",
        }

        missing = required_columns.difference(data.columns)

        if missing:
            raise ValueError(
                "ReplayInspector data is missing columns: "
                + ", ".join(sorted(missing))
            )

        if not hasattr(ledger, "entry_events"):
            raise TypeError(
                "ReplayInspector requires a SignalLedger-compatible object"
            )

        self.data = data.copy().reset_index(drop=True)
        self.ledger = ledger

    def entry_records(
        self,
        *,
        allowed_only: bool = True,
    ) -> List[ReplayInspectionRecord]:
        events = self.ledger.entry_events(
            allowed_only=allowed_only
        )

        records: List[ReplayInspectionRecord] = []
        total_entries = len(events)

        for sequence, event in enumerate(events, start=1):
            entry_index = self._safe_int(
                event.get("entry_index")
            )

            if entry_index is None:
                entry_index = self._safe_int(
                    event.get("as_of_index")
                )

            if entry_index is None:
                raise ValueError(
                    "Entry event has neither entry_index nor as_of_index"
                )

            if not 0 <= entry_index < len(self.data):
                raise IndexError(
                    f"Entry index {entry_index} is outside "
                    f"0..{len(self.data) - 1}"
                )

            candle_time = event.get("candle_time")

            if candle_time is None and "time" in self.data.columns:
                candle_time = self.data.at[
                    entry_index,
                    "time",
                ]

            records.append(
                ReplayInspectionRecord(
                    sequence=sequence,
                    total_entries=total_entries,

                    symbol=str(
                        event.get("symbol", "UNKNOWN")
                    ),
                    timeframe=event.get("timeframe"),

                    setup_id=event.get("setup_id"),
                    entry_index=entry_index,
                    candle_time=candle_time,

                    direction=event.get("direction"),
                    trend=event.get("trend"),
                    phase=event.get("phase"),

                    state=event.get("state"),
                    setup_status=event.get("setup_status"),

                    pullback_start_index=self._safe_int(
                        event.get("pullback_start_index")
                    ),
                    pullback_end_index=self._safe_int(
                        event.get("pullback_end_index")
                    ),
                    pullback_direction=event.get(
                        "pullback_direction"
                    ),
                    pullback_quality=event.get(
                        "pullback_quality"
                    ),

                    entry_price=self._safe_float(
                        event.get("entry_price")
                    ),
                    entry_type=event.get("entry_type"),
                    entry_quality=event.get("entry_quality"),
                    entry_score=self._safe_float(
                        event.get("entry_score")
                    ),
                    first_candidate_index=self._safe_int(
                        event.get("first_candidate_index")
                    ),
                    first_qualification_index=self._safe_int(
                        event.get(
                            "first_qualification_index"
                        )
                    ),
                    qualification_available_at_index=self._safe_int(
                        event.get(
                            "qualification_available_at_index"
                        )
                    ),
                    initial_failure_trigger_index=self._safe_int(
                        event.get(
                            "initial_failure_trigger_index"
                        )
                    ),
                    active_failure_trigger_index=self._safe_int(
                        event.get(
                            "active_failure_trigger_index"
                        )
                    ),
                    active_failure_trigger_level=self._safe_float(
                        event.get(
                            "active_failure_trigger_level"
                        )
                    ),
                    trigger_updated_at_index=self._safe_int(
                        event.get(
                            "trigger_updated_at_index"
                        )
                    ),
                    trigger_update_count=int(
                        event.get(
                            "trigger_update_count",
                            0,
                        )
                        or 0
                    ),
                    significance_score=self._safe_float(
                        event.get("significance_score")
                    ),
                    raw_significance_score=self._safe_float(
                        event.get(
                            "raw_significance_score"
                        )
                    ),

                    invalidation_type=event.get(
                        "invalidation_type"
                    ),
                    invalidation_index=self._safe_int(
                        event.get("invalidation_index")
                    ),
                    invalidation_level=self._safe_float(
                        event.get("invalidation_level")
                    ),
                    invalidation_intact=self._safe_bool(
                        event.get("invalidation_intact")
                    ),

                    protection_available=bool(
                        event.get(
                            "protection_available",
                            False,
                        )
                    ),
                    protection_state=str(
                        event.get(
                            "protection_state",
                            "PROTECTION_UNAVAILABLE",
                        )
                    ),
                    protection_reasons=str(
                        event.get(
                            "protection_reasons",
                            "",
                        )
                    ),
                    protection_type=event.get(
                        "protection_type"
                    ),
                    protection_index=self._safe_int(
                        event.get("protection_index")
                    ),
                    protection_level=self._safe_float(
                        event.get("protection_level")
                    ),
                    protection_intact=self._safe_bool(
                        event.get("protection_intact")
                    ),

                    transition_available=bool(
                        event.get(
                            "transition_available",
                            False,
                        )
                    ),
                    transition_reasons=str(
                        event.get(
                            "transition_reasons",
                            "",
                        )
                    ),
                    transition_state=event.get(
                        "transition_state"
                    ),
                    transition_active=self._safe_bool(
                        event.get("transition_active")
                    ),
                    transition_recovered=self._safe_bool(
                        event.get("transition_recovered")
                    ),

                    validation_available=bool(
                        event.get(
                            "validation_available",
                            False,
                        )
                    ),
                    validation_state=str(
                        event.get(
                            "validation_state",
                            "VALIDATION_UNAVAILABLE",
                        )
                    ),
                    validation_reasons=str(
                        event.get(
                            "validation_reasons",
                            "",
                        )
                    ),
                    validation_verdict=event.get(
                        "validation_verdict"
                    ),
                    validation_hard_block=self._safe_bool(
                        event.get("validation_hard_block")
                    ),
                    risk_modifier=self._safe_float(
                        event.get("risk_modifier")
                    ),

                    decision_action=event.get(
                        "decision_action"
                    ),
                    trade_allowed=bool(
                        event.get("trade_allowed", False)
                    ),
                    causal=bool(
                        event.get("causal", True)
                    ),
                    rejection_reason=event.get(
                        "rejection_reason"
                    ),
                )
            )

        return records

    def print_report(
        self,
        *,
        allowed_only: bool = True,
        context_before: int = 3,
        context_after: int = 3,
    ) -> None:
        records = self.entry_records(
            allowed_only=allowed_only
        )

        print("=" * 78)
        print("SMARTSTRUCTUREBOT REPLAY INSPECTOR")
        print("=" * 78)
        print(f"Unique Entries          : {len(records)}")
        print(f"Allowed Only            : {allowed_only}")
        print("=" * 78)

        if not records:
            print("No entry signals available for inspection.")
            return

        for record in records:
            self._print_entry(
                record=record,
                context_before=context_before,
                context_after=context_after,
            )

    def export_review_csv(
        self,
        path: str,
        *,
        allowed_only: bool = True,
    ) -> str:
        records = self.entry_records(
            allowed_only=allowed_only
        )

        rows: List[Dict[str, Any]] = []

        for record in records:
            row = {
                key: value
                for key, value in record.__dict__.items()
            }

            row["manual_verdict"] = ""
            row["manual_reason"] = ""
            row["reviewed_by"] = ""
            row["reviewed_at"] = ""

            if not record.protection_available:
                explanation = (
                    record.protection_state
                    + (
                        ": "
                        + record.protection_reasons
                        if record.protection_reasons
                        else ""
                    )
                )
                row["protection_type"] = explanation
                row["protection_index"] = explanation
                row["protection_level"] = explanation
                row["protection_intact"] = explanation

            rows.append(row)

        dataframe = pd.DataFrame(rows)

        output_path = Path(path)
        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        dataframe.to_csv(
            output_path,
            index=False,
        )

        return str(output_path)

    def _print_entry(
        self,
        *,
        record: ReplayInspectionRecord,
        context_before: int,
        context_after: int,
    ) -> None:
        print()
        print("-" * 78)
        print(
            f"ENTRY {record.sequence} OF "
            f"{record.total_entries}"
        )
        print("-" * 78)

        self._print_field(
            "Symbol",
            record.symbol,
        )
        self._print_field(
            "Timeframe",
            record.timeframe,
        )
        self._print_field(
            "Setup ID",
            record.setup_id,
        )
        self._print_field(
            "Entry Index",
            record.entry_index,
        )
        self._print_field(
            "Candle Time",
            record.candle_time,
        )
        self._print_field(
            "Direction",
            record.direction,
        )
        self._print_field(
            "Trend",
            record.trend,
        )
        self._print_field(
            "Phase",
            record.phase,
        )
        self._print_field(
            "Entry State",
            record.state,
        )
        self._print_field(
            "Setup Status",
            record.setup_status,
        )

        print("-" * 78)

        self._print_field(
            "Pullback Start",
            record.pullback_start_index,
        )
        self._print_field(
            "Pullback End",
            record.pullback_end_index,
        )
        self._print_field(
            "Pullback Direction",
            record.pullback_direction,
        )
        self._print_field(
            "Pullback Quality",
            record.pullback_quality,
        )

        print("-" * 78)

        self._print_field(
            "Entry Price",
            record.entry_price,
        )
        self._print_field(
            "Entry Type",
            record.entry_type,
        )
        self._print_field(
            "Entry Quality",
            record.entry_quality,
        )
        self._print_field(
            "Entry Score",
            record.entry_score,
        )

        print("-" * 78)

        self._print_field(
            "Invalidation Type",
            record.invalidation_type,
        )
        self._print_field(
            "Invalidation Index",
            record.invalidation_index,
        )
        self._print_field(
            "Invalidation Level",
            record.invalidation_level,
        )
        self._print_field(
            "Invalidation Intact",
            record.invalidation_intact,
        )

        self._print_field(
            "Protection Type",
            record.protection_type,
        )
        self._print_field(
            "Protection Index",
            record.protection_index,
        )
        self._print_field(
            "Protection Level",
            record.protection_level,
        )
        self._print_field(
            "Protection Intact",
            record.protection_intact,
        )

        print("-" * 78)

        self._print_field(
            "Transition State",
            record.transition_state,
        )
        self._print_field(
            "Transition Active",
            record.transition_active,
        )
        self._print_field(
            "Transition Recovered",
            record.transition_recovered,
        )
        self._print_field(
            "Validation Verdict",
            record.validation_verdict,
        )
        self._print_field(
            "Validation Hard Block",
            record.validation_hard_block,
        )
        self._print_field(
            "Risk Modifier",
            record.risk_modifier,
        )

        print("-" * 78)

        self._print_field(
            "Decision Action",
            record.decision_action,
        )
        self._print_field(
            "Trade Allowed",
            record.trade_allowed,
        )
        self._print_field(
            "Causal",
            record.causal,
        )
        self._print_field(
            "Rejection Reason",
            record.rejection_reason,
        )

        self._print_candle_context(
            entry_index=record.entry_index,
            context_before=context_before,
            context_after=context_after,
        )

        print("-" * 78)
        print(
            "MANUAL VERDICT         : "
            "[ACCEPT / REJECT / UNCERTAIN]"
        )
        print(
            "MANUAL REASON          : "
            "________________________________"
        )

    def _print_candle_context(
        self,
        *,
        entry_index: int,
        context_before: int,
        context_after: int,
    ) -> None:
        start = max(
            0,
            entry_index - max(context_before, 0),
        )
        end = min(
            len(self.data) - 1,
            entry_index + max(context_after, 0),
        )

        print("-" * 78)
        print(
            f"CANDLE CONTEXT          : "
            f"{start}..{end}"
        )
        print(
            "Index | Time | Open | High | Low | Close | Entry"
        )

        for index in range(start, end + 1):
            row = self.data.iloc[index]

            time_value = (
                row.get("time")
                if "time" in self.data.columns
                else ""
            )

            marker = (
                "<-- ENTRY"
                if index == entry_index
                else ""
            )

            print(
                f"{index} | "
                f"{time_value} | "
                f"{self._format_number(row.get('open'))} | "
                f"{self._format_number(row.get('high'))} | "
                f"{self._format_number(row.get('low'))} | "
                f"{self._format_number(row.get('close'))} | "
                f"{marker}"
            )

    @staticmethod
    def _print_field(
        label: str,
        value: Any,
    ) -> None:
        print(f"{label:<23}: {value}")

    @staticmethod
    def _format_number(value: Any) -> str:
        try:
            return f"{float(value):.5f}"
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _safe_float(
        value: Any,
    ) -> Optional[float]:
        if value is None:
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(
        value: Any,
    ) -> Optional[int]:
        if value is None:
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_bool(
        value: Any,
    ) -> Optional[bool]:
        if value is None:
            return None

        return bool(value)
