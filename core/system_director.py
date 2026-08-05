from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Iterable, Optional, cast

import pandas as pd


class DataContractError(RuntimeError):
    """Raised when a required system-state field is missing."""


class CausalDataView:
    """
    Protects the system from future-candle leakage.

    Every decision must be calculated with data visible only up to
    `as_of_index`, inclusive.
    """

    def __init__(self, data: pd.DataFrame, as_of_index: int):
        if data is None or data.empty:
            raise ValueError("CausalDataView requires non-empty market data")

        if not isinstance(as_of_index, int):
            raise TypeError("as_of_index must be an integer")

        if as_of_index < 0 or as_of_index >= len(data):
            raise IndexError(
                f"as_of_index {as_of_index} is outside data range "
                f"0..{len(data) - 1}"
            )

        self._full_data = data
        self.as_of_index = as_of_index

    @property
    def data(self) -> pd.DataFrame:
        """
        Returns only candles known at the decision time.

        A copy is returned so an engine cannot mutate the shared source.
        """
        return self._full_data.iloc[: self.as_of_index + 1].copy()

    @property
    def current_candle(self) -> Dict[str, Any]:
        return cast(
            Dict[str, Any],
            self._full_data.iloc[self.as_of_index].to_dict(),
        )
    @property
    def previous_candle(self) -> Optional[Dict[str, Any]]:
        if self.as_of_index == 0:
            return None

        return cast(
            Dict[str, Any],
            self._full_data.iloc[self.as_of_index - 1].to_dict(),
        )

    def window(self, candles: int) -> pd.DataFrame:
        if candles <= 0:
            raise ValueError("candles must be greater than zero")

        start = max(0, self.as_of_index - candles + 1)
        return self._full_data.iloc[start : self.as_of_index + 1].copy()

    def row(self, index: int) -> Dict[str, Any]:
        if index > self.as_of_index:
            raise DataContractError(
                f"Future-data access blocked: requested candle {index}, "
                f"but decision is at candle {self.as_of_index}"
            )

        if index < 0:
            raise IndexError("Candle index cannot be negative")

        return cast(
            Dict[str, Any],
            self._full_data.iloc[index].to_dict(),
        )

class SystemStateDirector:
    """
    The single owner of truth for SmartStructureBot.

    Engines do not pass unrelated dictionaries directly to one another.
    Each engine reads an approved state section and writes only its own
    output section through this director.
    """

    REQUIRED_SECTIONS = (
        "meta",
        "market",
        "structure",
        "control",
        "context",
        "transition",
        "validation",
        "protection",
        "impulse_cycle",
        "setup_invalidation",
        "trailing_protection",
        "retracement",
        "setup",
        "entry",
        "entry_freshness",
        "pre_entry_evidence",
        "decision",
        "execution",
        "trade",
        "post_entry_proof",
        "guardian",
        "outcome",
        "contract_health",
    )

    SECTION_OWNERS = {
        "meta": "SystemStateDirector",
        "market": "MarketStateEngine",
        "structure": "StructurePipeline",
        "control": "MarketControlEngine",
        "context": "HTFContextEngine",
        "transition": "TransitionEngine",
        "validation": "StructureValidator",
        "protection": "ProtectedStructureEngine",
        "impulse_cycle": "ImpulseCycleEngine",
        "setup_invalidation": "ProtectedStructureEngine",
        "trailing_protection": "TrailingProtectionEngine",
        "retracement": "QualifiedRetracementEngine",
        "setup": "SetupLifecycleRegistry",
        "entry": "ContinuationEngine",
        "entry_freshness": "EntryFreshnessEngine",
        "pre_entry_evidence": "EntryEvidencePipeline",
        "decision": "DecisionPipeline",
        "execution": "ExecutionIntelligence",
        "trade": "TradeLifecycle",
        "post_entry_proof": "EntryProofEngine",
        "guardian": "TradeGuardian",
        "outcome": "TradeOutcomeRecorder",
        "contract_health": "SystemStateDirector",
    }

    def __init__(
        self,
        symbol: str,
        timeframe: Any,
        data: pd.DataFrame,
        as_of_index: int,
    ):
        self._market_data = data
        self._state: Dict[str, Any] = {
            section: {} for section in self.REQUIRED_SECTIONS
        }

        self._state["meta"] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "as_of_index": as_of_index,
            "created_at": datetime.now().isoformat(),
            "state_version": 1,
            "setup_id": None,
            "decision_id": None,
        }

        self._state["contract_health"] = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "updates": [],
        }

    # ---------------------------------------------------------
    # CAUSAL DATA ACCESS
    # ---------------------------------------------------------

    @property
    def market_view(self) -> CausalDataView:
        return CausalDataView(
            data=self._market_data,
            as_of_index=self.as_of_index,
        )

    @property
    def as_of_index(self) -> int:
        return int(self._state["meta"]["as_of_index"])

    def advance_to(self, as_of_index: int) -> None:
        if as_of_index < self.as_of_index:
            raise ValueError(
                "System Director cannot move backwards in market time"
            )

        if as_of_index >= len(self._market_data):
            raise IndexError(
                f"Cannot advance to candle {as_of_index}; "
                f"data ends at {len(self._market_data) - 1}"
            )

        self._state["meta"]["as_of_index"] = as_of_index
        self._state["meta"]["state_version"] += 1

    # ---------------------------------------------------------
    # STATE READ / WRITE
    # ---------------------------------------------------------

    def read(self, section: str) -> Dict[str, Any]:
        self._validate_section(section)
        return deepcopy(self._state[section])

    def write(
        self,
        section: str,
        payload: Optional[Dict[str, Any]],
        producer: str,
        replace: bool = True,
    ) -> None:
        self._validate_section(section)

        expected_owner = self.SECTION_OWNERS.get(section)

        if expected_owner and producer != expected_owner:
            self._contract_warning(
                f"{producer} wrote section '{section}', but its registered "
                f"owner is {expected_owner}"
            )

        clean_payload = payload or {}

        if not isinstance(clean_payload, dict):
            raise TypeError(
                f"Section '{section}' must receive a dictionary, "
                f"not {type(clean_payload).__name__}"
            )

        if replace:
            self._state[section] = deepcopy(clean_payload)
        else:
            self._state[section].update(deepcopy(clean_payload))

        self._state["contract_health"]["updates"].append(
            {
                "section": section,
                "producer": producer,
                "as_of_index": self.as_of_index,
                "state_version": self._state["meta"]["state_version"],
            }
        )

    def get(
        self,
        path: str,
        default: Any = None,
    ) -> Any:
        """
        Read a nested field using dot notation.

        Example:
            director.get("setup.status")
        """
        value: Any = self._state

        for part in path.split("."):
            if not isinstance(value, dict) or part not in value:
                return default
            value = value[part]

        return deepcopy(value)

    def require(self, *paths: str) -> Dict[str, Any]:
        """
        Require critical fields.

        Missing information becomes a visible contract failure instead
        of silently becoming None, zero or False.
        """
        result = {}
        missing = []

        for path in paths:
            marker = object()
            value = self.get(path, marker)

            if value is marker or value is None:
                missing.append(path)
            else:
                result[path] = value

        if missing:
            message = (
                "Missing required system-state fields: "
                + ", ".join(missing)
            )
            self._contract_error(message)
            raise DataContractError(message)

        return result

    # ---------------------------------------------------------
    # IDENTITIES
    # ---------------------------------------------------------

    def set_setup_id(self, setup_id: str) -> None:
        self._state["meta"]["setup_id"] = setup_id

    def set_decision_id(self, decision_id: str) -> None:
        self._state["meta"]["decision_id"] = decision_id

    def ensure_same_setup(self, sections: Iterable[str]) -> bool:
        """
        Confirms that multiple sections belong to one setup.

        Each relevant section should eventually carry its own setup_id.
        """
        expected = self.get("meta.setup_id")
        mismatches = []

        if expected is None:
            self._contract_error("meta.setup_id has not been assigned")
            return False

        for section in sections:
            section_setup_id = self.get(f"{section}.setup_id")

            if section_setup_id != expected:
                mismatches.append(
                    f"{section}.setup_id={section_setup_id}"
                )

        if mismatches:
            self._contract_error(
                "Setup identity mismatch. Expected "
                f"{expected}; found: {', '.join(mismatches)}"
            )
            return False

        return True

    # ---------------------------------------------------------
    # ENTRY GATES
    # ---------------------------------------------------------

    def entry_contract_valid(self) -> bool:
        """
        Mandatory logical gates.

        Scores can never compensate for these failures.
        """
        required_paths = (
            "market.trend",
            "structure.phase",
            "validation.verdict",
            "setup.status",
            "entry.ready",
            "entry.index",
            "entry.price",
            "entry.direction",
        )

        try:
            self.require(*required_paths)
        except DataContractError:
            return False

        if self.get("setup.status") not in {
            "ENTRY_VALIDATED",
            "CONSUMED",
            "REENTRY_PENDING",
        }:
            self._contract_error(
                "Entry blocked: setup.status is not an "
                "entry-capable lifecycle state"
            )
            return False

        if self.get("entry.ready") is not True:
            self._contract_error(
                "Entry blocked: entry.ready is not True"
            )
            return False

        if self.get("validation.verdict") == "STRUCTURE_INVALID":
            self._contract_error(
                "Entry blocked: structure validation is invalid"
            )
            return False

        entry_index = self.get("entry.index")

        if entry_index != self.as_of_index:
            self._contract_error(
                f"Entry blocked: entry index {entry_index} does not equal "
                f"decision candle {self.as_of_index}"
            )
            return False

        if not self.ensure_same_setup(
            ("setup", "entry")
        ):
            return False

        return True

    # ---------------------------------------------------------
    # SNAPSHOT
    # ---------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        return deepcopy(self._state)

    def contract_report(self) -> Dict[str, Any]:
        return deepcopy(self._state["contract_health"])

    # ---------------------------------------------------------
    # INTERNAL HELPERS
    # ---------------------------------------------------------

    def _validate_section(self, section: str) -> None:
        if section not in self.REQUIRED_SECTIONS:
            raise KeyError(
                f"Unknown state section '{section}'. "
                f"Allowed sections: {self.REQUIRED_SECTIONS}"
            )

    def _contract_error(self, message: str) -> None:
        self._state["contract_health"]["valid"] = False
        self._state["contract_health"]["errors"].append(
            {
                "message": message,
                "as_of_index": self.as_of_index,
            }
        )

    def _contract_warning(self, message: str) -> None:
        self._state["contract_health"]["warnings"].append(
            {
                "message": message,
                "as_of_index": self.as_of_index,
            }
        )
