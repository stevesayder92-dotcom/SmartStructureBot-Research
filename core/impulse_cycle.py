from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional


IMPULSE_CYCLE_STATUSES = {
    "ACTIVE_IMPULSE",
    "WAITING_FOR_RETRACEMENT",
    "RETRACEMENT_ACTIVE",
    "ENTRY_CONSUMED",
    "INVALIDATED",
    "SUPERSEDED",
    "CLOSED",
}

PROTECTION_POLICIES = {
    "ORIGIN_DEFENDING_SWING",
    "LATEST_PROVEN_CONTINUATION_SWING",
    "HYBRID_PROVEN_REPLACEMENT",
}


def availability_index(item: Dict[str, Any]) -> int:
    index = int(item.get("index", 0))
    markers = (
        item.get("confirmed_at_index"),
        item.get("tradeable_at_index"),
        item.get("decision_available_at_index"),
        item.get("protected_at_index"),
    )
    return max(
        [index]
        + [int(value) for value in markers if value is not None]
    )


def structural_importance(point: Dict[str, Any]) -> float:
    score = float(point.get("decision_weight", 0) or 0)
    if point.get("is_tradeable_structure"):
        score = max(score, 3.0)
    if point.get("is_major"):
        score += 2.0
    if point.get("is_protected"):
        score += 2.0
    return score


@dataclass(frozen=True)
class DecisionProtectionPolicy:
    name: str = "ORIGIN_DEFENDING_SWING"
    minimum_structural_importance: float = 3.0

    def __post_init__(self) -> None:
        normalized = self.name.upper()
        if normalized not in PROTECTION_POLICIES:
            raise ValueError(
                f"Unknown decision-protection policy {self.name!r}; "
                f"available policies: {sorted(PROTECTION_POLICIES)}"
            )
        object.__setattr__(self, "name", normalized)


class ImpulseCycleEngine:
    """Build the causal ownership envelope for one continuation setup."""

    def __init__(self, *, symbol: str, timeframe: str) -> None:
        self.symbol = str(symbol)
        self.timeframe = str(timeframe)

    def build(
        self,
        *,
        trend: str,
        origin_bos: Dict[str, Any],
        structure_points: Iterable[Dict[str, Any]],
        bos_events: Iterable[Dict[str, Any]],
        as_of_index: int,
        qualified_retracement_start_index: Optional[int] = None,
        entry_consumed: bool = False,
        invalidated: bool = False,
        terminal_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        direction = str(trend).upper()
        current = int(as_of_index)
        origin_index = origin_bos.get("index")
        reasons: list[str] = []

        if direction not in {"BULLISH", "BEARISH"}:
            return self._unavailable(
                direction=direction,
                as_of_index=current,
                reason="Impulse cycle requires a directional trend",
            )
        if origin_index is None:
            return self._unavailable(
                direction=direction,
                as_of_index=current,
                reason="Impulse cycle requires an origin BOS index",
            )

        origin_index = int(origin_index)
        origin_available = availability_index(origin_bos)
        expected_bos = (
            "BULLISH_BOS" if direction == "BULLISH" else "BEARISH_BOS"
        )
        visible_same_direction = sorted(
            [
                dict(event)
                for event in bos_events
                if event.get("type") == expected_bos
                and event.get("index") is not None
                and int(event["index"]) <= current
                and availability_index(event) <= current
                and event.get("causal_valid", True)
            ],
            key=lambda event: int(event["index"]),
        )
        previous_origins = [
            int(event["index"])
            for event in visible_same_direction
            if int(event["index"]) < origin_index
            and event.get("bos_role") != "EXTENSION_BOS"
        ]
        lower_bound = max(previous_origins) if previous_origins else 0
        expected_side = "LOW" if direction == "BULLISH" else "HIGH"
        pre_origin = [
            dict(point)
            for point in structure_points
            if point.get("side") == expected_side
            and point.get("index") is not None
            and lower_bound <= int(point["index"]) < origin_index
            and availability_index(point) <= current
        ]
        impulse_start = (
            max(pre_origin, key=lambda point: int(point["index"]))["index"]
            if pre_origin
            else lower_bound
        )
        impulse_start = int(impulse_start)

        if direction == "BULLISH":
            impulse_extreme = max(
                [origin_index]
                + [
                    int(point["index"])
                    for point in structure_points
                    if point.get("side") == "HIGH"
                    and point.get("index") is not None
                    and origin_index <= int(point["index"]) <= current
                    and availability_index(point) <= current
                ]
            )
        else:
            impulse_extreme = max(
                [origin_index]
                + [
                    int(point["index"])
                    for point in structure_points
                    if point.get("side") == "LOW"
                    and point.get("index") is not None
                    and origin_index <= int(point["index"]) <= current
                    and availability_index(point) <= current
                ]
            )

        later_origins = [
            int(event["index"])
            for event in visible_same_direction
            if int(event["index"]) > origin_index
            and event.get("bos_role") != "EXTENSION_BOS"
        ]
        superseded_at = min(later_origins) if later_origins else None

        if invalidated:
            status = "INVALIDATED"
        elif entry_consumed:
            status = "ENTRY_CONSUMED"
        elif superseded_at is not None:
            status = "SUPERSEDED"
            terminal_index = superseded_at
        elif terminal_index is not None:
            status = "CLOSED"
        elif qualified_retracement_start_index is not None:
            status = "RETRACEMENT_ACTIVE"
        elif current > origin_index:
            status = "WAITING_FOR_RETRACEMENT"
        else:
            status = "ACTIVE_IMPULSE"

        causal_valid = bool(
            origin_index <= current
            and origin_available <= current
            and impulse_start <= origin_index
            and (
                qualified_retracement_start_index is None
                or int(qualified_retracement_start_index) <= current
            )
            and (
                terminal_index is None
                or int(terminal_index) <= current
            )
        )
        if causal_valid:
            reasons.append(
                "Origin BOS and cycle boundaries are available at decision time"
            )
        else:
            reasons.append(
                "One or more cycle boundaries are not causally available"
            )

        return {
            "availability": "AVAILABLE",
            "available": True,
            "owner": "ImpulseCycleEngine",
            "cycle_id": (
                f"CYCLE-{self.symbol}-{self.timeframe}-"
                f"{direction}-{origin_index}"
            ),
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": direction,
            "origin_bos_index": origin_index,
            "origin_bos_available_at_index": origin_available,
            "impulse_start_index": impulse_start,
            "impulse_extreme_index": impulse_extreme,
            "qualified_retracement_start_index": (
                int(qualified_retracement_start_index)
                if qualified_retracement_start_index is not None
                else None
            ),
            "terminal_index": (
                int(terminal_index)
                if terminal_index is not None
                else None
            ),
            "status": status,
            "state": status,
            "as_of_index": current,
            "causal_valid": causal_valid,
            "reason": reasons,
        }

    def _unavailable(
        self,
        *,
        direction: str,
        as_of_index: int,
        reason: str,
    ) -> Dict[str, Any]:
        return {
            "availability": "UNAVAILABLE",
            "available": False,
            "owner": "ImpulseCycleEngine",
            "cycle_id": None,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": direction,
            "origin_bos_index": None,
            "origin_bos_available_at_index": None,
            "impulse_start_index": None,
            "impulse_extreme_index": None,
            "qualified_retracement_start_index": None,
            "terminal_index": None,
            "status": "CLOSED",
            "state": "CLOSED",
            "as_of_index": int(as_of_index),
            "causal_valid": True,
            "reason": [reason],
        }


class DecisionProtectionSelector:
    """Select decision protection only from candidates owned by one cycle."""

    def __init__(
        self,
        *,
        policy: Optional[DecisionProtectionPolicy] = None,
    ) -> None:
        self.policy = policy or DecisionProtectionPolicy()

    def select(
        self,
        *,
        cycle: Dict[str, Any],
        trend: str,
        structure_points: Iterable[Dict[str, Any]],
        bos_events: Iterable[Dict[str, Any]],
        as_of_index: int,
        current_price: Optional[float] = None,
        entry_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        catalog = self.catalog(
            cycle=cycle,
            trend=trend,
            structure_points=structure_points,
            bos_events=bos_events,
            as_of_index=as_of_index,
            current_price=current_price,
            entry_index=entry_index,
        )
        eligible = [
            candidate
            for candidate in catalog
            if candidate["replacement_eligible"]
            and not candidate["rejection_reasons"]
        ]
        origin = [
            item
            for item in eligible
            if item["relationship_to_origin_bos"]
            == "DIRECTLY_PRECEDES_ORIGIN_BOS"
        ]
        continuation = [
            item
            for item in eligible
            if item["relationship_to_origin_bos"]
            == "DEFENDED_SAME_CYCLE_CONTINUATION_BOS"
        ]

        chosen: Optional[Dict[str, Any]] = None
        policy = self.policy.name
        if policy == "ORIGIN_DEFENDING_SWING":
            chosen = origin[-1] if origin else None
        elif policy == "LATEST_PROVEN_CONTINUATION_SWING":
            chosen = continuation[-1] if continuation else (
                origin[-1] if origin else None
            )
        elif policy == "HYBRID_PROVEN_REPLACEMENT":
            proven = [
                item
                for item in continuation
                if item["selection_score"]
                >= self.policy.minimum_structural_importance * 10
            ]
            chosen = proven[-1] if proven else (
                origin[-1] if origin else None
            )

        base = {
            "role": "DECISION_PROTECTION",
            "owner": "DecisionProtectionSelector",
            "cycle_id": cycle.get("cycle_id"),
            "origin_bos_index": cycle.get("origin_bos_index"),
            "selection_policy": policy,
            "policy_activation": "RESEARCH_COMPARISON_NOT_PERMANENT",
            "candidate_count": len(catalog),
            "eligible_candidate_count": len(eligible),
            "all_candidates": catalog,
            "as_of_index": int(as_of_index),
            "body_close_invalidation": True,
            "wick_invalidation": False,
            "causal_valid": bool(cycle.get("causal_valid", False)),
        }
        if chosen is None:
            return {
                **base,
                "availability": "UNAVAILABLE",
                "available": False,
                "state": "WAITING_FOR_VALID_DECISION_PROTECTION",
                "type": None,
                "side": None,
                "index": None,
                "level": None,
                "confirmed_at_index": None,
                "decision_available_at_index": None,
                "relationship_to_origin_bos": None,
                "replacement_eligible": False,
                "selection_score": 0.0,
                "rejection_reasons": [
                    "No candidate satisfies cycle ownership, causal, "
                    "side, chronology and BOS-relationship requirements"
                ],
                "reason": [
                    "WAITING_FOR_VALID_DECISION_PROTECTION"
                ],
            }

        return {
            **base,
            "availability": "AVAILABLE",
            "available": True,
            "state": "DECISION_PROTECTION_AVAILABLE",
            "type": chosen["structure_type"],
            "side": chosen["side"],
            "index": chosen["structure_index"],
            "level": chosen["structure_price"],
            "confirmed_at_index": chosen["confirmed_at_index"],
            "decision_available_at_index": chosen["available_at_index"],
            "relationship_to_origin_bos": chosen[
                "relationship_to_origin_bos"
            ],
            "caused_or_defended_bos": chosen[
                "caused_or_defended_bos"
            ],
            "confirming_bos_index": chosen["confirming_bos_index"],
            "replacement_eligible": chosen["replacement_eligible"],
            "selection_score": chosen["selection_score"],
            "rejection_reasons": [],
            "belongs_to_origin_impulse_cycle": True,
            "impulse_cycle_start_index": cycle.get(
                "impulse_start_index"
            ),
            "newer_valid_protected_swing_exists": any(
                item["structure_index"] > chosen["structure_index"]
                and item["replacement_eligible"]
                and not item["rejection_reasons"]
                for item in catalog
            ),
            "newer_protected_swing_candidates": [
                item
                for item in catalog
                if item["structure_index"] > chosen["structure_index"]
                and item["replacement_eligible"]
                and not item["rejection_reasons"]
            ],
            "reason": [
                "Selected protection has an explicit structural "
                "relationship to the current impulse cycle",
                f"Research comparison policy: {policy}",
            ],
        }

    def catalog(
        self,
        *,
        cycle: Dict[str, Any],
        trend: str,
        structure_points: Iterable[Dict[str, Any]],
        bos_events: Iterable[Dict[str, Any]],
        as_of_index: int,
        current_price: Optional[float] = None,
        entry_index: Optional[int] = None,
    ) -> list[Dict[str, Any]]:
        direction = str(trend).upper()
        expected_side = "LOW" if direction == "BULLISH" else "HIGH"
        expected_type = "HL" if direction == "BULLISH" else "LH"
        expected_bos = (
            "BULLISH_BOS" if direction == "BULLISH" else "BEARISH_BOS"
        )
        origin_index = cycle.get("origin_bos_index")
        cycle_start = cycle.get("impulse_start_index")
        cycle_id = cycle.get("cycle_id")
        current = int(as_of_index)
        decision_entry = (
            int(entry_index) if entry_index is not None else current
        )

        if origin_index is None or cycle_start is None or cycle_id is None:
            return []
        origin_index = int(origin_index)
        cycle_start = int(cycle_start)

        visible_bos = sorted(
            [
                dict(event)
                for event in bos_events
                if event.get("type") == expected_bos
                and event.get("index") is not None
                and int(event["index"]) <= current
                and availability_index(event) <= current
                and event.get("causal_valid", True)
            ],
            key=lambda event: int(event["index"]),
        )
        points = [
            dict(point)
            for point in structure_points
            if point.get("side") == expected_side
            and point.get("index") is not None
            and int(point["index"]) < decision_entry
            and availability_index(point) <= current
        ]
        pre_origin_expected = [
            point
            for point in points
            if cycle_start <= int(point["index"]) < origin_index
            and point.get("type") == expected_type
        ]
        origin_defender_index = (
            max(int(point["index"]) for point in pre_origin_expected)
            if pre_origin_expected
            else None
        )
        catalog: list[Dict[str, Any]] = []

        for point in sorted(points, key=lambda item: int(item["index"])):
            index = int(point["index"])
            level = point.get("body_price", point.get("price"))
            available = availability_index(point)
            rejections: list[str] = []
            belongs = cycle_start <= index < decision_entry
            if not belongs:
                rejections.append("UNRELATED_OLD_IMPULSE_CYCLE")
            if available > current:
                rejections.append("FUTURE_STRUCTURE")
            if index >= decision_entry:
                rejections.append("DOES_NOT_PREDATE_ENTRY")
            if not isinstance(level, (int, float)):
                rejections.append("MISSING_STRUCTURE_PRICE")
            correct_side = True
            if (
                current_price is not None
                and isinstance(level, (int, float))
            ):
                correct_side = (
                    float(level) < float(current_price)
                    if direction == "BULLISH"
                    else float(level) > float(current_price)
                )
                if not correct_side:
                    rejections.append("WRONG_SIDE_OF_PRICE")

            confirming = next(
                (
                    event
                    for event in visible_bos
                    if int(event["index"]) > index
                    and int(event["index"]) <= decision_entry
                ),
                None,
            )
            if index == origin_defender_index:
                relationship = "DIRECTLY_PRECEDES_ORIGIN_BOS"
                confirming_index = origin_index
            elif index >= origin_index and confirming is not None:
                relationship = "DEFENDED_SAME_CYCLE_CONTINUATION_BOS"
                confirming_index = int(confirming["index"])
            else:
                relationship = "NO_APPROVED_BOS_RELATIONSHIP"
                confirming_index = None
                rejections.append("NO_DOCUMENTED_BOS_RELATIONSHIP")

            importance = structural_importance(point)
            if point.get("type") != expected_type:
                rejections.append("WRONG_PROTECTION_STRUCTURE_TYPE")
            if importance < self.policy.minimum_structural_importance:
                rejections.append("BELOW_MINIMUM_STRUCTURAL_IMPORTANCE")

            eligible = bool(
                belongs
                and correct_side
                and point.get("type") == expected_type
                and importance
                >= self.policy.minimum_structural_importance
                and relationship != "NO_APPROVED_BOS_RELATIONSHIP"
                and available <= current
                and index < decision_entry
                and isinstance(level, (int, float))
            )
            score = min(
                100.0,
                importance * 10.0
                + (
                    30.0
                    if relationship == "DIRECTLY_PRECEDES_ORIGIN_BOS"
                    else 25.0
                    if relationship
                    == "DEFENDED_SAME_CYCLE_CONTINUATION_BOS"
                    else 0.0
                ),
            )
            catalog.append(
                {
                    "structure_index": index,
                    "structure_price": (
                        float(level)
                        if isinstance(level, (int, float))
                        else None
                    ),
                    "structure_type": point.get("type"),
                    "side": expected_side,
                    "confirmed_at_index": int(
                        point.get("confirmed_at_index", available)
                    ),
                    "available_at_index": available,
                    "cycle_id": cycle_id if belongs else None,
                    "belongs_to_cycle": belongs,
                    "relationship_to_origin_bos": relationship,
                    "caused_or_defended_bos": (
                        relationship
                        != "NO_APPROVED_BOS_RELATIONSHIP"
                    ),
                    "confirming_bos_index": confirming_index,
                    "replacement_eligible": eligible,
                    "selection_score": round(score, 3),
                    "structural_importance": round(importance, 3),
                    "rejection_reasons": sorted(set(rejections)),
                    "causal_valid": available <= current,
                }
            )
        return catalog


def compare_protection_policies(
    *,
    cycle: Dict[str, Any],
    trend: str,
    structure_points: Iterable[Dict[str, Any]],
    bos_events: Iterable[Dict[str, Any]],
    as_of_index: int,
    current_price: Optional[float] = None,
    entry_index: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    """Return independent advisory selections without mutating runtime state."""
    return {
        name: DecisionProtectionSelector(
            policy=DecisionProtectionPolicy(name=name)
        ).select(
            cycle=cycle,
            trend=trend,
            structure_points=structure_points,
            bos_events=bos_events,
            as_of_index=as_of_index,
            current_price=current_price,
            entry_index=entry_index,
        )
        for name in sorted(PROTECTION_POLICIES)
    }
