from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping


HTF_SECONDS = {
    "H1": 60 * 60,
    "M30": 30 * 60,
    "M15": 15 * 60,
}

HTF_POLICIES = {
    "CONSENSUS_2_OF_3",
    "PREFER_M30_M15",
    "STRONGEST_SINGLE",
    "H1_ANCHOR",
}


@dataclass(frozen=True)
class HTFContextPolicy:
    name: str = "PREFER_M30_M15"
    allow_single_strong: bool = True
    priority_order: tuple[str, ...] = (
        "M30",
        "M15",
        "H1",
    )

    def __post_init__(self) -> None:
        normalized = str(self.name).upper()
        object.__setattr__(self, "name", normalized)

        if normalized not in HTF_POLICIES:
            raise ValueError(
                f"Unknown HTF policy {self.name!r}; "
                f"available policies: {sorted(HTF_POLICIES)}"
            )


def _directional(value: Any) -> bool:
    return value in {"BULLISH", "BEARISH"}


def _snapshot_signal(
    *,
    timeframe: str,
    record: Dict[str, Any],
) -> Dict[str, Any]:
    snapshot = record.get("snapshot") or {}
    market = snapshot.get("market") or {}
    structure = snapshot.get("structure") or {}
    validation = snapshot.get("validation") or {}
    health = snapshot.get("contract_health") or {}
    trend = market.get("trend")
    phase = (
        structure.get("phase")
        or market.get("phase")
    )
    causal = bool(
        record.get("causal", True)
        and health.get("valid", True)
    )
    hard_block = bool(
        validation.get("hard_block", False)
    )
    clean = bool(
        _directional(trend)
        and causal
        and not hard_block
    )
    strong = bool(
        clean
        and (
            "EXPANSION" in str(phase)
            or validation.get("verdict")
            == "STRUCTURE_VALID"
        )
    )

    return {
        "timeframe": timeframe,
        "trend": trend,
        "phase": phase,
        "clean": clean,
        "strong": strong,
        "causal": causal,
        "validation_verdict": validation.get(
            "verdict"
        ),
        "validation_hard_block": hard_block,
        "bar_open_time": record.get(
            "bar_open_time"
        ),
        "bar_close_time": record.get(
            "bar_close_time"
        ),
        "snapshot_as_of_index": (
            snapshot.get("meta", {}).get(
                "as_of_index"
            )
        ),
    }


class HigherTimeframeContextEngine:
    """
    Causally align closed H1/M30/M15 snapshots to one LTF decision.

    The engine selects HTF context only. It never recalculates local
    structure and it never allows an LTF counter-trend to rewrite the
    selected HTF direction.
    """

    def __init__(
        self,
        policy: HTFContextPolicy | None = None,
    ) -> None:
        self.policy = policy or HTFContextPolicy()

    def build(
        self,
        *,
        decision_candle_open_time: float,
        decision_timeframe_seconds: int,
        frame_histories: Mapping[
            str,
            Iterable[Dict[str, Any]],
        ],
    ) -> Dict[str, Any]:
        decision_available_at = (
            float(decision_candle_open_time)
            + int(decision_timeframe_seconds)
        )
        aligned: Dict[str, Dict[str, Any]] = {}
        future_records_rejected = 0

        for timeframe in ("H1", "M30", "M15"):
            seconds = HTF_SECONDS[timeframe]
            eligible = []

            for raw_record in frame_histories.get(
                timeframe,
                [],
            ):
                record = deepcopy(raw_record)
                open_time = float(
                    record["bar_open_time"]
                )
                close_time = float(
                    record.get(
                        "bar_close_time",
                        open_time + seconds,
                    )
                )
                record["bar_close_time"] = close_time

                if close_time <= decision_available_at:
                    eligible.append(record)
                else:
                    future_records_rejected += 1

            if not eligible:
                aligned[timeframe] = {
                    "timeframe": timeframe,
                    "available": False,
                    "reason": (
                        "No fully closed HTF candle was "
                        "available by the LTF decision"
                    ),
                }
                continue

            chosen = max(
                eligible,
                key=lambda item: float(
                    item["bar_close_time"]
                ),
            )
            signal = _snapshot_signal(
                timeframe=timeframe,
                record=chosen,
            )
            signal["available"] = True
            signal["closed_before_decision"] = bool(
                float(signal["bar_close_time"])
                <= decision_available_at
            )
            aligned[timeframe] = signal

        direction, state, single_strong, reasons = (
            self._select_direction(aligned)
        )
        votes = {
            "BULLISH": sum(
                1
                for frame in aligned.values()
                if frame.get("clean")
                and frame.get("trend") == "BULLISH"
            ),
            "BEARISH": sum(
                1
                for frame in aligned.values()
                if frame.get("clean")
                and frame.get("trend") == "BEARISH"
            ),
        }
        causal = all(
            not frame.get("available")
            or bool(
                frame.get(
                    "closed_before_decision",
                    False,
                )
                and frame.get("causal", False)
            )
            for frame in aligned.values()
        )

        return {
            "available": _directional(direction),
            "state": state,
            "approved_direction": direction,
            "policy": self.policy.name,
            "allow_single_strong": (
                self.policy.allow_single_strong
            ),
            "strong_single_accepted": single_strong,
            "decision_candle_open_time": float(
                decision_candle_open_time
            ),
            "decision_available_at": (
                decision_available_at
            ),
            "frames": aligned,
            "votes": votes,
            "causal": causal,
            "incomplete_htf_candles_used": False,
            "future_or_incomplete_records_rejected": (
                future_records_rejected
            ),
            "entry_alignment": "NOT_EVALUATED",
            "local_direction": None,
            "reason": reasons,
        }

    def _select_direction(
        self,
        frames: Mapping[str, Dict[str, Any]],
    ) -> tuple[
        str | None,
        str,
        bool,
        list[str],
    ]:
        clean = {
            timeframe: frame
            for timeframe, frame in frames.items()
            if frame.get("clean")
        }
        strong = {
            timeframe: frame
            for timeframe, frame in clean.items()
            if frame.get("strong")
        }
        policy = self.policy.name

        if policy == "CONSENSUS_2_OF_3":
            for direction in (
                "BULLISH",
                "BEARISH",
            ):
                count = sum(
                    1
                    for frame in clean.values()
                    if frame.get("trend") == direction
                )
                if count >= 2:
                    return (
                        direction,
                        "HTF_CONSENSUS",
                        False,
                        [
                            f"{count} approved HTFs agree "
                            f"on {direction}"
                        ],
                    )

        elif policy == "PREFER_M30_M15":
            m30 = clean.get("M30", {})
            m15 = clean.get("M15", {})

            if (
                m30
                and m15
                and m30.get("trend")
                == m15.get("trend")
            ):
                return (
                    m30.get("trend"),
                    "M30_M15_AGREEMENT",
                    False,
                    [
                        "M30 and M15 provide the "
                        "preferred agreement"
                    ],
                )

        elif policy == "H1_ANCHOR":
            h1 = clean.get("H1")
            if h1:
                return (
                    h1.get("trend"),
                    "H1_ANCHOR_SELECTED",
                    False,
                    [
                        "Causally closed H1 context "
                        "selected as anchor"
                    ],
                )

        elif policy == "STRONGEST_SINGLE":
            selected = self._priority_frame(
                strong
            )
            if selected:
                return (
                    selected.get("trend"),
                    "STRONG_SINGLE_CONTEXT",
                    True,
                    [
                        "Configured strongest-single "
                        "policy selected one clean HTF"
                    ],
                )

        if (
            self.policy.allow_single_strong
            and strong
        ):
            strong_directions = {
                frame.get("trend")
                for frame in strong.values()
            }

            if len(strong_directions) == 1:
                selected = self._priority_frame(
                    strong
                )
                assert selected is not None
                return (
                    selected.get("trend"),
                    "STRONG_SINGLE_CONTEXT",
                    True,
                    [
                        "One or more clean strong HTFs "
                        "support the same direction"
                    ],
                )

        return (
            None,
            "NO_APPROVED_HTF_CONTEXT",
            False,
            [
                "Configured policy did not produce "
                "an unambiguous HTF direction"
            ],
        )

    def _priority_frame(
        self,
        frames: Mapping[str, Dict[str, Any]],
    ) -> Dict[str, Any] | None:
        for timeframe in self.policy.priority_order:
            if timeframe in frames:
                return frames[timeframe]
        return None


def attach_local_alignment(
    context: Dict[str, Any],
    local_direction: Any,
) -> Dict[str, Any]:
    result = deepcopy(context)
    approved = result.get("approved_direction")
    result["local_direction"] = local_direction

    if not _directional(approved):
        result["entry_alignment"] = (
            "NO_APPROVED_HTF_CONTEXT"
        )
    elif not _directional(local_direction):
        result["entry_alignment"] = (
            "LOCAL_DIRECTION_UNKNOWN"
        )
    elif approved == local_direction:
        result["entry_alignment"] = "ALIGNED"
    else:
        result["entry_alignment"] = "CONFLICT"
        result.setdefault("reason", []).append(
            "Local counter-trend direction does not "
            "overwrite the approved HTF direction"
        )

    return result


def compare_htf_advisory_policies(
    context: Dict[str, Any],
    local_direction: Any,
) -> Dict[str, Dict[str, Any]]:
    """Compare all approved HTF policies without hard-blocking an entry."""
    frames = deepcopy(context.get("frames") or {})
    comparisons: Dict[str, Dict[str, Any]] = {}
    policies = (
        ("PREFER_M30_M15", True),
        ("CONSENSUS_2_OF_3", False),
        ("STRONGEST_SINGLE", True),
        ("H1_ANCHOR", False),
    )
    for name, allow_single in policies:
        engine = HigherTimeframeContextEngine(
            HTFContextPolicy(
                name=name,
                allow_single_strong=allow_single,
            )
        )
        direction, state, single_strong, reasons = (
            engine._select_direction(frames)
        )
        support_count = sum(
            1
            for frame in frames.values()
            if frame.get("clean")
            and frame.get("trend") == direction
        )
        if not _directional(direction):
            classification = "NO_CLEAN_CONTEXT"
        elif (
            _directional(local_direction)
            and direction != local_direction
        ):
            classification = "CONFLICT"
        elif single_strong:
            classification = "SINGLE_STRONG_SUPPORT"
        elif support_count >= 2:
            classification = "MULTI_FRAME_SUPPORT"
        else:
            classification = "ALIGNED"
        comparisons[name] = {
            "policy": name,
            "allow_single_strong": allow_single,
            "approved_direction": direction,
            "state": state,
            "classification": classification,
            "supporting_frame_count": support_count,
            "reason": reasons,
            "advisory_only": True,
            "hard_block_applied": False,
        }
    return comparisons
