from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import re

from simulator.adapters.dataset_adapter import DatasetAdapter, ReplayDataset
from simulator.config import project_root
from simulator.execution.contract_specification import ContractSpecificationService, normalize_symbol


SAFE_SYMBOL = re.compile(r"^[A-Za-z0-9#._-]{1,40}$")


class DataLibraryService:
    """Configured portable-data catalogue; browser requests never supply paths."""

    def __init__(self, root: Path | None = None):
        self.root = (root or project_root() / "simulator_data" / "library").resolve()
        self.contracts = ContractSpecificationService()

    def _symbol_folder(self, symbol: str) -> Path:
        if not SAFE_SYMBOL.fullmatch(symbol):
            raise ValueError("Invalid symbol identifier")
        key = normalize_symbol(symbol)
        candidate = (self.root / key).resolve()
        candidate.relative_to(self.root)
        return candidate

    def list_symbols(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if not self.root.exists():
            return rows
        for manifest_path in sorted(self.root.glob("*/manifest.json")):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["replay_readiness"] = "READY" if (manifest_path.parent / "M1.csv").exists() and (manifest_path.parent / "M5.csv").exists() else "NOT_READY"
            rows.append(manifest)
        return rows

    def describe(self, symbol: str) -> dict[str, Any]:
        folder = self._symbol_folder(symbol)
        manifest = folder / "manifest.json"
        if not manifest.exists():
            raise KeyError(f"Portable data is not configured for {symbol}")
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["contract_specification"] = self.contracts.get(payload["symbol"]).payload()
        payload["replay_readiness"] = "READY"
        return payload

    def load(self, symbol: str) -> ReplayDataset:
        folder = self._symbol_folder(symbol)
        manifest = self.describe(symbol)
        return DatasetAdapter(project_root()).load_csv_pair(
            symbol=str(manifest["symbol"]),
            m1_path=folder / "M1.csv",
            m5_path=folder / "M5.csv",
        )

    def available_range(self, symbol: str) -> tuple[float, float]:
        manifest = self.describe(symbol)
        start = max(float(manifest["timeframes"]["M1"]["first_timestamp"]), float(manifest["timeframes"]["M5"]["first_timestamp"]))
        end = min(float(manifest["timeframes"]["M1"]["last_timestamp"]) + 60.0, float(manifest["timeframes"]["M5"]["last_timestamp"]) + 300.0)
        return start, end


def parse_replay_time(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        raise ValueError("Replay timestamp is required")
    try:
        return float(text)
    except ValueError:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
