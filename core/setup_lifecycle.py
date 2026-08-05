from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from core.steve_trade_management import (
    SteveTradeManagementEngine,
)


TERMINAL_SETUP_STATES = {
    "CONSUMED",
    "INVALIDATED",
    "EXPIRED",
    "CLOSED",
}

SETUP_STATES = {
    "DETECTED",
    "DEVELOPING",
    "WAITING_FOR_TRIGGER",
    "CANDIDATE_READY",
    "ENTRY_VALIDATED",
    "CONSUMED",
    "INVALIDATED",
    "EXPIRED",
    "REENTRY_PENDING",
    "CLOSED",
}


class SetupLifecycleRegistry:
    """
    Persistent owner of setup identity and consumption state.

    Descriptive pullback boundaries may evolve, but setup identity is
    created once from immutable origin fields and remains stable until
    a genuinely new post-terminal pullback appears.
    """

    def __init__(self) -> None:
        self._setups: Dict[str, Dict[str, Any]] = {}
        self._active_by_market: Dict[
            tuple[str, str],
            str,
        ] = {}

    def observe(
        self,
        *,
        symbol: str,
        timeframe: Any,
        direction: str,
        origin_trend_bos_index: Optional[int],
        initial_pullback_start: int,
        current_pullback_end: int,
        as_of_index: int,
        descriptive_status: str,
        retracement_direction: Optional[str] = None,
        quality: Optional[str] = None,
        causal: bool = True,
    ) -> Dict[str, Any]:
        if direction not in {"BULLISH", "BEARISH"}:
            raise ValueError(
                "Setup direction must be BULLISH or BEARISH"
            )

        start = int(initial_pullback_start)
        end = int(current_pullback_end)
        current_index = int(as_of_index)
        origin = (
            int(origin_trend_bos_index)
            if origin_trend_bos_index is not None
            else None
        )
        market_key = (str(symbol), str(timeframe))
        active_id = self._active_by_market.get(
            market_key
        )
        active = (
            self._setups.get(active_id)
            if active_id is not None
            else None
        )

        if self._is_genuinely_new(
            active=active,
            direction=direction,
            origin_trend_bos_index=origin,
            pullback_start=start,
        ):
            setup_id = self._create_setup_id(
                symbol=symbol,
                timeframe=timeframe,
                direction=direction,
                origin_trend_bos_index=origin,
                initial_pullback_start=start,
            )
            setup = {
                "setup_id": setup_id,
                "symbol": str(symbol),
                "timeframe": timeframe,
                "direction": direction,
                "trend": direction,
                "origin_trend_bos": origin,
                "initial_pullback_start": start,
                "current_pullback_end": end,
                "status": "DETECTED",
                "created_at_index": current_index,
                "updated_at_index": current_index,
                "confirmed_at_index": None,
                "consumed_at_index": None,
                "invalidated_at_index": None,
                "expired_at_index": None,
                "closed_at_index": None,
                "reentry_count": 0,
                "retracement_direction": (
                    retracement_direction
                ),
                "quality": quality,
                "causal": bool(causal),
                "current_candle_only": True,
                "reason": [
                    "Setup identity created by the "
                    "authoritative lifecycle registry"
                ],
                "history": [
                    {
                        "event": "SETUP_DETECTED",
                        "as_of_index": current_index,
                        "status": "DETECTED",
                        "observed_pullback_start": start,
                        "current_pullback_end": end,
                        "origin_trend_bos": origin,
                        "descriptive_status": (
                            descriptive_status
                        ),
                    }
                ],
            }
            self._setups[setup_id] = setup
            self._active_by_market[market_key] = (
                setup_id
            )
        else:
            assert active is not None
            setup = active
            setup["current_pullback_end"] = end
            setup["updated_at_index"] = current_index
            setup["retracement_direction"] = (
                retracement_direction
            )
            setup["quality"] = quality
            setup["causal"] = bool(
                setup.get("causal", True)
                and causal
            )
            self._append_history(
                setup,
                event="BOUNDARY_OBSERVED",
                as_of_index=current_index,
                observed_pullback_start=start,
                current_pullback_end=end,
                observed_origin_trend_bos=origin,
                descriptive_status=(
                    descriptive_status
                ),
            )

        if setup["status"] not in TERMINAL_SETUP_STATES:
            setup["status"] = self._map_status(
                descriptive_status
            )
            setup["history"][-1]["status"] = (
                setup["status"]
            )

        return self._published(setup)

    def mark_candidate_ready(
        self,
        setup_id: str,
        as_of_index: int,
    ) -> Dict[str, Any]:
        setup = self._require(setup_id)

        if setup["status"] not in TERMINAL_SETUP_STATES:
            setup["status"] = "CANDIDATE_READY"
            setup["updated_at_index"] = int(
                as_of_index
            )
            self._append_history(
                setup,
                event="CANDIDATE_READY",
                as_of_index=int(as_of_index),
            )

        return self._published(setup)

    def consume(
        self,
        setup_id: str,
        as_of_index: int,
    ) -> Dict[str, Any]:
        setup = self._require(setup_id)
        current_index = int(as_of_index)

        if setup["status"] == "CONSUMED":
            return self._published(setup)

        if setup["status"] in {
            "INVALIDATED",
            "EXPIRED",
            "CLOSED",
        }:
            raise ValueError(
                f"Cannot consume terminal setup {setup_id} "
                f"in state {setup['status']}"
            )

        setup["status"] = "ENTRY_VALIDATED"
        setup["confirmed_at_index"] = current_index
        setup["updated_at_index"] = current_index
        setup["status"] = "CONSUMED"
        setup["consumed_at_index"] = current_index
        setup["reason"].append(
            "First canonical entry emitted; setup consumed"
        )
        self._append_history(
            setup,
            event="SETUP_CONSUMED",
            as_of_index=current_index,
        )

        return self._published(setup)

    def invalidate(
        self,
        setup_id: str,
        as_of_index: int,
        reason: str,
    ) -> Dict[str, Any]:
        setup = self._require(setup_id)

        if setup["status"] != "CONSUMED":
            setup["status"] = "INVALIDATED"
            setup["invalidated_at_index"] = int(
                as_of_index
            )
            setup["updated_at_index"] = int(
                as_of_index
            )
            setup["reason"].append(str(reason))
            self._append_history(
                setup,
                event="SETUP_INVALIDATED",
                as_of_index=int(as_of_index),
                reason=str(reason),
            )

        return self._published(setup)

    def close_for_new_impulse(
        self,
        setup_id: str,
        as_of_index: int,
        *,
        new_origin_trend_bos_index: int,
    ) -> Dict[str, Any]:
        """
        End an unconsumed compression when a genuinely newer
        directional impulse has established a new BOS origin.

        Merely relabelling an old BOS is insufficient: the new origin
        must occur after the setup's latest pullback boundary.
        """

        setup = self._require(setup_id)
        current_index = int(as_of_index)
        new_origin = int(new_origin_trend_bos_index)
        previous_end = int(
            setup["current_pullback_end"]
        )

        if setup["status"] in TERMINAL_SETUP_STATES:
            return self._published(setup)
        if new_origin <= previous_end:
            raise ValueError(
                "A new impulse may close a setup only when its "
                "BOS occurs after the existing pullback boundary"
            )
        if new_origin > current_index:
            raise ValueError(
                "A new impulse BOS cannot be in the future"
            )

        setup["status"] = "CLOSED"
        setup["closed_at_index"] = current_index
        setup["updated_at_index"] = current_index
        setup["reason"].append(
            "Meaningful new directional impulse terminated "
            "the prior compression"
        )
        self._append_history(
            setup,
            event="SETUP_CLOSED_NEW_IMPULSE",
            as_of_index=current_index,
            new_origin_trend_bos_index=new_origin,
        )
        return self._published(setup)

    def arm_reentry(
        self,
        setup_id: str,
        as_of_index: int,
    ) -> Dict[str, Any]:
        setup = self._require(setup_id)

        if int(setup.get("reentry_count", 0)) >= 1:
            raise ValueError(
                "A setup may arm at most one re-entry"
            )

        setup["reentry_count"] = 1
        setup["status"] = "REENTRY_PENDING"
        setup["updated_at_index"] = int(
            as_of_index
        )
        self._append_history(
            setup,
            event="REENTRY_ARMED",
            as_of_index=int(as_of_index),
        )

        return self._published(setup)

    def is_consumed(self, setup_id: str) -> bool:
        return (
            self._require(setup_id).get("status")
            == "CONSUMED"
        )

    def get(self, setup_id: str) -> Dict[str, Any]:
        return self._published(
            self._require(setup_id)
        )

    @property
    def setups(self) -> list[Dict[str, Any]]:
        return [
            self._published(setup)
            for setup in self._setups.values()
        ]

    @staticmethod
    def _map_status(
        descriptive_status: str,
    ) -> str:
        status = str(
            descriptive_status or ""
        ).upper()

        if status == "INVALID_SETUP":
            return "INVALIDATED"

        if status in {
            "WAITING_FOR_TRIGGER",
            "WAITING_FOR_CONFIRMATION",
            "CONFIRMED",
        }:
            return "WAITING_FOR_TRIGGER"

        if status in SETUP_STATES:
            return status

        return "DEVELOPING"

    @staticmethod
    def _is_genuinely_new(
        *,
        active: Optional[Dict[str, Any]],
        direction: str,
        origin_trend_bos_index: Optional[int],
        pullback_start: int,
    ) -> bool:
        if active is None:
            return True

        if active.get("direction") != direction:
            return True

        if active.get("status") not in TERMINAL_SETUP_STATES:
            return False

        terminal_index = (
            active.get("consumed_at_index")
            or active.get("invalidated_at_index")
            or active.get("expired_at_index")
            or active.get("closed_at_index")
        )

        if (
            terminal_index is not None
            and pullback_start > int(terminal_index)
        ):
            return True

        # A newer descriptive BOS alone is not proof of a new setup.
        # The detector can relabel the same historical pullback while
        # its start remains before the consumed/terminal candle.
        return False

    def _create_setup_id(
        self,
        *,
        symbol: str,
        timeframe: Any,
        direction: str,
        origin_trend_bos_index: Optional[int],
        initial_pullback_start: int,
    ) -> str:
        origin = (
            str(origin_trend_bos_index)
            if origin_trend_bos_index is not None
            else "NONE"
        )
        base = (
            f"{symbol}|{timeframe}|{direction}|"
            f"BOS_{origin}|PB_{initial_pullback_start}"
        )

        if base not in self._setups:
            return base

        version = 2

        while f"{base}|V{version}" in self._setups:
            version += 1

        return f"{base}|V{version}"

    def _require(
        self,
        setup_id: str,
    ) -> Dict[str, Any]:
        if setup_id not in self._setups:
            raise KeyError(
                f"Unknown setup_id {setup_id}"
            )

        return self._setups[setup_id]

    @staticmethod
    def _append_history(
        setup: Dict[str, Any],
        *,
        event: str,
        as_of_index: int,
        **details: Any,
    ) -> None:
        setup.setdefault("history", []).append(
            {
                "event": str(event),
                "as_of_index": int(as_of_index),
                "status": setup.get("status"),
                **details,
            }
        )

    @staticmethod
    def _published(
        setup: Dict[str, Any],
    ) -> Dict[str, Any]:
        result = deepcopy(setup)
        result["pullback_start_index"] = result.get(
            "initial_pullback_start"
        )
        result["pullback_end_index"] = result.get(
            "current_pullback_end"
        )
        result["pullback_direction"] = result.get(
            "retracement_direction"
        )
        result["start_index"] = result.get(
            "initial_pullback_start"
        )
        result["end_index"] = result.get(
            "current_pullback_end"
        )
        observed_starts = sorted(
            {
                int(event["observed_pullback_start"])
                for event in result.get("history", [])
                if event.get(
                    "observed_pullback_start"
                )
                is not None
            }
        )
        origin = result.get("origin_trend_bos")
        initial = result.get(
            "initial_pullback_start"
        )
        result["origin_audit"] = {
            "initial_pullback_start_stable": True,
            "observed_pullback_starts": (
                observed_starts
            ),
            "boundary_revision_count": max(
                0,
                len(observed_starts) - 1,
            ),
            "micro_structures_merged": (
                len(observed_starts) > 1
            ),
            "origin_precedes_or_equals_pullback": (
                origin is None
                or initial is None
                or int(origin) <= int(initial)
            ),
            "requires_manual_origin_review": bool(
                origin is not None
                and initial is not None
                and int(initial) < int(origin)
            ),
        }
        return result


@dataclass
class PipelineRuntimeState:
    setup_registry: SetupLifecycleRegistry = field(
        default_factory=SetupLifecycleRegistry
    )
    expert_trade_manager: SteveTradeManagementEngine = field(
        default_factory=SteveTradeManagementEngine
    )
