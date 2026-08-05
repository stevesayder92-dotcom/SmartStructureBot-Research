from __future__ import annotations

from typing import Any

from simulator.models.financial import MonetaryEvent
from simulator.models.schema import stable_hash


class ExecutionLedger:
    """Append-only, hash-linked monetary event ledger."""

    def __init__(self) -> None:
        self.events: list[MonetaryEvent] = []
        self._parent_hash: str | None = None

    def append(self, **payload: Any) -> MonetaryEvent:
        core = {**payload, "parent_state_hash": self._parent_hash}
        state_hash = stable_hash(core)
        event = MonetaryEvent(**core, state_hash=state_hash)
        self.events.append(event)
        self._parent_hash = state_hash
        return event

    def payload(self) -> list[dict[str, Any]]:
        return [event.payload() for event in self.events]

    @property
    def last_hash(self) -> str | None:
        return self._parent_hash
