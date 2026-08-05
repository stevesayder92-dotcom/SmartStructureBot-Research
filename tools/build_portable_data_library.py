from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import platform

import pandas as pd

from simulator.adapters.dataset_adapter import DatasetAdapter
from simulator.config import project_root
from simulator.execution.contract_specification import ContractSpecificationService, normalize_symbol


def frame_manifest(frame: pd.DataFrame, path: Path) -> dict:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "rows": len(frame),
        "first_timestamp": float(frame.iloc[0]["time"]),
        "last_timestamp": float(frame.iloc[-1]["time"]),
        "data_hash": digest,
        "file": path.name,
        "columns": list(frame.columns),
        "spread_availability": "NATIVE" if "spread" in frame.columns and frame["spread"].notna().any() else "NOT_AVAILABLE_USE_ESTIMATED_PROFILE",
    }


def main() -> None:
    root = project_root()
    destination = root / "simulator_data" / "library"
    destination.mkdir(parents=True, exist_ok=True)
    adapter = DatasetAdapter(root)
    adapter._load_source()
    symbols = sorted(adapter._datasets or {})
    contracts = ContractSpecificationService()
    index = []
    for symbol in symbols:
        dataset = adapter.load_frozen(symbol)
        folder = destination / normalize_symbol(symbol)
        folder.mkdir(parents=True, exist_ok=True)
        m1_path, m5_path = folder / "M1.csv", folder / "M5.csv"
        dataset.m1.to_csv(m1_path, index=False, float_format="%.10f")
        dataset.m5.to_csv(m5_path, index=False, float_format="%.10f")
        manifest = {
            "schema_version": "SMARTSTRUCTUREBOT_PORTABLE_DATA_V1",
            "symbol": symbol,
            "timezone": "UTC",
            "source": "Frozen research source converted from internal pickle cache",
            "native_or_derived": "NATIVE_OHLC_FROM_FROZEN_SOURCE",
            "timeframes": {"M1": frame_manifest(dataset.m1, m1_path), "M5": frame_manifest(dataset.m5, m5_path)},
            "validation": dataset.validation,
            "gaps": {"M1": dataset.validation["m1"].get("published_gaps", []), "M5": dataset.validation["m5"].get("published_gaps", [])},
            "contract_spec_source": contracts.get(symbol).source_status,
            "contract_spec_warning": contracts.get(symbol).source_note,
            "creation_environment": {"python": platform.python_version(), "pandas": pd.__version__, "platform": platform.platform()},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        manifest["library_hash"] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        index.append(manifest)
        print(symbol, manifest["timeframes"]["M1"]["rows"], manifest["timeframes"]["M5"]["rows"])
    (destination / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(json.dumps({"symbols": len(index), "destination": str(destination)}, indent=2))


if __name__ == "__main__":
    main()
