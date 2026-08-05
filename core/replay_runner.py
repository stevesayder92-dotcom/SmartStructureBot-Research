from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from core.pipeline_runner import (
    PipelineOptions,
    PipelineResult,
    run_pipeline,
)
from core.signal_ledger import SignalLedger
from core.setup_lifecycle import PipelineRuntimeState


@dataclass
class ReplayOptions:
    """
    Controls historical candle-by-candle replay.
    """

    start_index: int = 50
    end_index: Optional[int] = None

    continue_on_error: bool = False
    record_integrity_failures: bool = True
    enable_progress: bool = False
    progress_interval: int = 50


@dataclass
class ReplayError:
    as_of_index: int
    error_type: str
    message: str


@dataclass
class ReplayResult:
    symbol: str
    timeframe: Any
    source_rows: int
    start_index: int
    end_index: int

    candles_requested: int
    candles_processed: int
    pipeline_results: List[PipelineResult]

    ledger: SignalLedger
    errors: List[ReplayError]
    diagnostics: Dict[str, Any]


def _validate_replay_inputs(
    data: pd.DataFrame,
    symbol: str,
    options: ReplayOptions,
) -> tuple[int, int]:
    if not isinstance(data, pd.DataFrame):
        raise TypeError(
            "Replay data must be a pandas DataFrame"
        )

    if data.empty:
        raise ValueError(
            "Replay cannot run on an empty DataFrame"
        )

    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError(
            "Replay requires a non-empty symbol"
        )

    start_index = int(options.start_index)

    end_index = (
        len(data) - 1
        if options.end_index is None
        else int(options.end_index)
    )

    if start_index < 0:
        raise IndexError(
            "Replay start_index cannot be negative"
        )

    if end_index >= len(data):
        raise IndexError(
            f"Replay end_index {end_index} exceeds "
            f"the final candle {len(data) - 1}"
        )

    if start_index > end_index:
        raise ValueError(
            "Replay start_index cannot exceed end_index"
        )

    if options.progress_interval <= 0:
        raise ValueError(
            "progress_interval must be greater than zero"
        )

    return start_index, end_index


def _candle_to_dict(
    data: pd.DataFrame,
    as_of_index: int,
) -> Dict[str, Any]:
    """
    Convert one DataFrame row into a string-keyed candle dictionary.
    """

    raw_candle = (
        data.iloc[as_of_index].to_dict()
    )

    candle: Dict[str, Any] = {
        str(key): value
        for key, value in raw_candle.items()
    }

    candle["source_index"] = (
        as_of_index
    )

    return candle


def _integrity_failures(
    result: PipelineResult,
) -> List[str]:
    diagnostics = result.diagnostics
    failures: List[str] = []

    if not diagnostics.get(
        "future_access_test_passed",
        False,
    ):
        failures.append(
            "Director future-access test failed"
        )

    if not diagnostics.get(
        "contract_valid",
        False,
    ):
        failures.append(
            "Director contract is invalid"
        )

    integer_zero_fields = (
        "future_structures_used",
        "future_strength_used",
        "future_displacement_used",
        "non_causal_bos",
        "bos_before_confirmation",
        "wrong_bos_break_prices",
    )

    for field in integer_zero_fields:
        value = diagnostics.get(field, 0)

        if value != 0:
            failures.append(
                f"{field}={value}"
            )

    false_only_fields = (
        "future_protection_used",
        "future_setup_invalidation_used",
        "stale_setup_confirmation_used",
        "stale_continuation_used",
        "manager_continuation_conflict",
        "unexplained_structure_block",
        "recovered_transition_blocked",
    )

    for field in false_only_fields:
        if diagnostics.get(field, False):
            failures.append(
                f"{field}=True"
            )

    true_only_fields = (
        "market_control_causal",
        "market_control_as_of_matches",
        "transition_causal",
        "transition_as_of_matches",
        "setup_current_only",
        "setup_lifecycle_causal",
        "setup_as_of_matches",
        "setup_invalidation_causal",
        "continuation_current_only",
        "continuation_causal",
        "continuation_as_of_matches",
        "continuation_entry_is_current",
        "final_entry_is_current",
        "final_entry_is_causal",
        "final_entry_close_only",
        "canonical_entry_as_of_matches",
        "canonical_entry_price_matches_close",
    )

    for field in true_only_fields:
        if diagnostics.get(field) is not True:
            failures.append(
                f"{field} is not True"
            )

    entry_available = diagnostics.get(
        "final_entry_available",
        False,
    )

    if entry_available:
        entry_index = diagnostics.get(
            "final_entry_index"
        )

        if entry_index != result.requested_as_of_index:
            failures.append(
                "Final entry index does not equal "
                "the replay decision index"
            )

    chronology_blocked = (
        diagnostics.get("canonical_entry_state")
        == "BLOCKED_INCOHERENT_SETUP_CHRONOLOGY"
    )

    if diagnostics.get(
        "entry_validation_allowed",
        False,
    ) and not (
        diagnostics.get(
            "setup_consumed_before_candidate",
            False,
        )
        or chronology_blocked
    ):
        if not diagnostics.get(
            "canonical_entry_available",
            False,
        ):
            failures.append(
                "EntryValidator allowed a candidate but the "
                "canonical entry is unavailable"
            )

        if not diagnostics.get(
            "canonical_entry_ready",
            False,
        ):
            failures.append(
                "EntryValidator allowed a candidate but the "
                "canonical entry is not ready"
            )

        if not diagnostics.get(
            "director_entry_available",
            False,
        ):
            failures.append(
                "Validator-approved candidate did not reach "
                "the Director entry section"
            )

        if not diagnostics.get(
            "canonical_entry_causal",
            False,
        ):
            failures.append(
                "Validator-approved canonical entry is non-causal"
            )

    if chronology_blocked:
        if diagnostics.get(
            "canonical_entry_ready",
            False,
        ):
            failures.append(
                "Chronology-blocked setup emitted an entry"
            )
        if diagnostics.get(
            "director_entry_available",
            False,
        ):
            failures.append(
                "Chronology-blocked setup was published as available"
            )

    if diagnostics.get(
        "setup_consumed_before_candidate",
        False,
    ) and diagnostics.get(
        "continuation_ready",
        False,
    ):
        if diagnostics.get(
            "canonical_entry_ready",
            False,
        ):
            failures.append(
                "Consumed setup emitted another first-entry signal"
            )

        if diagnostics.get(
            "canonical_entry_state"
        ) != "BLOCKED_SETUP_CONSUMED":
            failures.append(
                "Consumed setup candidate was not explicitly "
                "blocked by canonical entry state"
            )

    return failures


def run_replay(
    *,
    data: pd.DataFrame,
    symbol: str,
    timeframe: Any,
    options: Optional[ReplayOptions] = None,
    pipeline_options: Optional[
        PipelineOptions
    ] = None,
    ledger: Optional[SignalLedger] = None,
    pipeline_callable: Callable[
        ...,
        PipelineResult,
    ] = run_pipeline,
    higher_timeframe_context_provider: Optional[
        Callable[[int], Dict[str, Any]]
    ] = None,
    runtime_state: Optional[PipelineRuntimeState] = None,
) -> ReplayResult:
    """
    Replay the verified causal pipeline one candle at a time.

    Every pipeline call receives the same complete source DataFrame,
    but run_pipeline physically truncates it at as_of_index before
    any engine receives market data.
    """

    if options is None:
        options = ReplayOptions()

    if pipeline_options is None:
        pipeline_options = PipelineOptions()

    if ledger is None:
        ledger = SignalLedger()

    start_index, end_index = (
        _validate_replay_inputs(
            data=data,
            symbol=symbol,
            options=options,
        )
    )

    results: List[PipelineResult] = []
    errors: List[ReplayError] = []
    if runtime_state is None:
        runtime_state = PipelineRuntimeState()

    integrity_failure_count = 0
    processed_indexes: List[int] = []

    for as_of_index in range(
        start_index,
        end_index + 1,
    ):
        try:
            pipeline_arguments = {
                "data": data,
                "symbol": symbol,
                "timeframe": timeframe,
                "as_of_index": as_of_index,
                "options": pipeline_options,
                "runtime_state": runtime_state,
            }

            if (
                higher_timeframe_context_provider
                is not None
            ):
                pipeline_arguments[
                    "higher_timeframe_context"
                ] = (
                    higher_timeframe_context_provider(
                        as_of_index
                    )
                )

            pipeline_result = pipeline_callable(
                **pipeline_arguments
            )

            failures = _integrity_failures(
                pipeline_result
            )

            candle = _candle_to_dict(
                data=data,
                as_of_index=as_of_index,
            )

            ledger_event = ledger.record_snapshot(
                snapshot=pipeline_result.snapshot,
                candle=candle,
            )

            ledger_entry_event_created = bool(
                ledger_event is not None
                and ledger_event.event_type
                == "ENTRY_SIGNAL"
            )
            pipeline_result.diagnostics[
                "ledger_entry_event_created"
            ] = ledger_entry_event_created

            canonical_ready = bool(
                pipeline_result.diagnostics.get(
                    "canonical_entry_ready",
                    False,
                )
            )

            if (
                canonical_ready
                and not ledger_entry_event_created
            ):
                failures.append(
                    "Canonical ready entry did not create exactly "
                    "one SignalLedger ENTRY_SIGNAL"
                )

            if (
                not canonical_ready
                and ledger_entry_event_created
            ):
                failures.append(
                    "Non-ready canonical entry created an allowed "
                    "SignalLedger ENTRY_SIGNAL"
                )

            if failures:
                integrity_failure_count += 1

                message = " | ".join(failures)

                if not options.continue_on_error:
                    raise RuntimeError(
                        "Replay causal-integrity failure "
                        f"at candle {as_of_index}: "
                        f"{message}"
                    )

            results.append(pipeline_result)
            processed_indexes.append(as_of_index)

            if (
                options.enable_progress
                and (
                    as_of_index == start_index
                    or as_of_index == end_index
                    or (
                        as_of_index - start_index + 1
                    )
                    % options.progress_interval
                    == 0
                )
            ):
                print(
                    "REPLAY",
                    f"{as_of_index}/{end_index}",
                    pipeline_result.diagnostics.get(
                        "final_trend"
                    ),
                    pipeline_result.diagnostics.get(
                        "continuation_state"
                    ),
                )

        except Exception as error:
            errors.append(
                ReplayError(
                    as_of_index=as_of_index,
                    error_type=type(error).__name__,
                    message=str(error),
                )
            )

            if not options.continue_on_error:
                raise

    expected_indexes = list(
        range(start_index, end_index + 1)
    )

    duplicate_processed_indexes = (
        len(processed_indexes)
        - len(set(processed_indexes))
    )

    missing_processed_indexes = sorted(
        set(expected_indexes)
        - set(processed_indexes)
    )

    ledger_summary = ledger.summary()
    entry_events = ledger.entry_events()
    rejected_entries = ledger.rejected_entries()

    stale_ledger_entries = [
        event
        for event in entry_events
        if event.get("entry_index")
        != event.get("as_of_index")
    ]

    non_causal_ledger_entries = [
        event
        for event in entry_events
        if not event.get("causal", False)
    ]

    continuation_candidate_count = sum(
        1
        for result in results
        if result.diagnostics.get(
            "continuation_ready",
            False,
        )
    )
    validator_approved_count = sum(
        1
        for result in results
        if result.diagnostics.get(
            "entry_validation_allowed",
            False,
        )
    )
    canonical_entry_count = sum(
        1
        for result in results
        if result.diagnostics.get(
            "canonical_entry_ready",
            False,
        )
    )
    director_entry_count = sum(
        1
        for result in results
        if result.diagnostics.get(
            "director_entry_available",
            False,
        )
    )
    blocked_candidates = Counter()

    for result in results:
        if not result.diagnostics.get(
            "continuation_ready",
            False,
        ):
            continue

        if result.diagnostics.get(
            "canonical_entry_ready",
            False,
        ):
            continue

        entry = (
            result.snapshot.get("entry", {})
            or {}
        )
        blocked_candidates[
            str(entry.get("state") or "UNKNOWN")
        ] += 1

    diagnostics = {
        "source_rows": len(data),
        "start_index": start_index,
        "end_index": end_index,
        "candles_requested": len(
            expected_indexes
        ),
        "candles_processed": len(
            processed_indexes
        ),
        "processed_indexes": (
            processed_indexes
        ),
        "missing_processed_indexes": (
            missing_processed_indexes
        ),
        "duplicate_processed_indexes": (
            duplicate_processed_indexes
        ),
        "pipeline_error_count": len(
            errors
        ),
        "integrity_failure_count": (
            integrity_failure_count
        ),
        "continuation_candidate_count": (
            continuation_candidate_count
        ),
        "validator_approved_count": (
            validator_approved_count
        ),
        "canonical_entry_count": (
            canonical_entry_count
        ),
        "director_entry_count": (
            director_entry_count
        ),
        "inspector_unique_entry_count": len(
            entry_events
        ),
        "blocked_candidates_by_reason": dict(
            blocked_candidates
        ),
        "ledger_event_count": (
            ledger_summary.get(
                "total_events",
                0,
            )
        ),
        "ledger_entry_count": len(
            entry_events
        ),
        "ledger_rejected_entry_count": len(
            rejected_entries
        ),
        "ledger_non_causal_events": (
            ledger_summary.get(
                "non_causal_events",
                0,
            )
        ),
        "ledger_proof_leaks": (
            ledger_summary.get(
                "post_entry_proof_leaks",
                0,
            )
        ),
        "stale_ledger_entry_count": len(
            stale_ledger_entries
        ),
        "non_causal_ledger_entry_count": (
            len(non_causal_ledger_entries)
        ),
        "all_requested_candles_processed": (
            processed_indexes
            == expected_indexes
        ),
        "replay_passed": bool(
            processed_indexes
            == expected_indexes
            and not errors
            and integrity_failure_count == 0
            and duplicate_processed_indexes == 0
            and not missing_processed_indexes
            and not stale_ledger_entries
            and not non_causal_ledger_entries
            and ledger_summary.get(
                "non_causal_events",
                0,
            )
            == 0
            and ledger_summary.get(
                "post_entry_proof_leaks",
                0,
            )
            == 0
        ),
    }

    return ReplayResult(
        symbol=symbol,
        timeframe=timeframe,
        source_rows=len(data),
        start_index=start_index,
        end_index=end_index,
        candles_requested=len(
            expected_indexes
        ),
        candles_processed=len(
            processed_indexes
        ),
        pipeline_results=results,
        ledger=ledger,
        errors=errors,
        diagnostics=diagnostics,
    )
