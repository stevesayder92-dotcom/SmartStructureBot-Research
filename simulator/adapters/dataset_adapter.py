from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import pickle

import pandas as pd

from core.synchronized_m1_replay import (
    build_closed_candle_timeline,
    validate_closed_series,
)
from simulator.config import project_root
from simulator.models.schema import json_safe


TIMEFRAME_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600}


@dataclass(frozen=True)
class ReplayDataset:
    symbol: str
    m1: pd.DataFrame
    m5: pd.DataFrame
    data_hash: str
    source: str
    validation: dict[str, Any]


class DatasetAdapter:
    """The only owner allowed to expose candle rows to the replay clock."""

    def __init__(self, root: Path | None = None):
        self.root = root or project_root()
        self._cases: list[dict[str, Any]] | None = None
        self._datasets: dict[str, dict[str, pd.DataFrame]] | None = None
        self._source_manifest: list[dict[str, Any]] | None = None

    @property
    def source_path(self) -> Path:
        return self.root / "research_data_sync" / "sequence_elite_source.pkl"

    def _load_source(self) -> None:
        if self._cases is not None:
            return
        with self.source_path.open("rb") as handle:
            cases, datasets, manifest = pickle.load(handle)
        self._cases = [dict(row) for row in cases]
        self._datasets = datasets
        self._source_manifest = list(manifest)

    def cases(self, limit: int | None = None) -> list[dict[str, Any]]:
        self._load_source()
        assert self._cases is not None
        rows = self._cases if limit is None else self._cases[: int(limit)]
        result: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            outcome = dict(row.get("outcome") or {})
            metrics = dict(outcome.get("metrics") or {})
            result.append(
                {
                    "case_number": index,
                    "symbol": row.get("symbol"),
                    "direction": row.get("direction"),
                    "entry_timeframe": row.get("entry_timeframe"),
                    "entry_time": row.get("entry_time"),
                    "entry_time_utc": row.get("entry_time_utc"),
                    "setup_id": row.get("parent_m5_setup_id"),
                    "session": row.get("session"),
                    "category_flags": list(row.get("category_flags") or []),
                    "first_entry_failed": bool(outcome.get("first_entry_failed")),
                    "valid_reentry": bool(outcome.get("valid_reentry")),
                    "peak_R": metrics.get("peak_R"),
                    "final_R": metrics.get("final_R"),
                }
            )
        return result

    def case(self, case_number: int) -> dict[str, Any]:
        self._load_source()
        assert self._cases is not None
        index = int(case_number) - 1
        if index < 0 or index >= len(self._cases):
            raise IndexError(f"Unknown frozen case {case_number}")
        return self._cases[index]

    @staticmethod
    def _normalize(data: pd.DataFrame) -> pd.DataFrame:
        required = ["time", "open", "high", "low", "close"]
        missing = [name for name in required if name not in data.columns]
        if missing:
            raise ValueError(f"Dataset missing columns: {', '.join(missing)}")
        result = data.copy().reset_index(drop=True)
        for name in ("time", "open", "high", "low", "close"):
            result[name] = pd.to_numeric(result[name], errors="raise")
        if "tick_volume" not in result:
            result["tick_volume"] = 0
        return result

    @staticmethod
    def _frame_hash(m1: pd.DataFrame, m5: pd.DataFrame) -> str:
        digest = hashlib.sha256()
        for name, frame in (("M1", m1), ("M5", m5)):
            digest.update(name.encode("ascii"))
            digest.update(
                frame[["time", "open", "high", "low", "close"]]
                .to_csv(index=False, float_format="%.10f")
                .encode("utf-8")
            )
        return digest.hexdigest()

    def load_frozen(self, symbol: str) -> ReplayDataset:
        self._load_source()
        assert self._datasets is not None
        if symbol not in self._datasets:
            raise KeyError(f"Frozen dataset does not contain {symbol}")
        source = self._datasets[symbol]
        m1 = self._normalize(source["M1"])
        m5 = self._normalize(source["M5"])
        validation = self.validate(m1=m1, m5=m5)
        return ReplayDataset(
            symbol=symbol,
            m1=m1,
            m5=m5,
            data_hash=self._frame_hash(m1, m5),
            source=str(self.source_path),
            validation=validation,
        )

    def load_csv_pair(self, *, symbol: str, m1_path: Path, m5_path: Path) -> ReplayDataset:
        m1 = self._normalize(pd.read_csv(m1_path))
        m5 = self._normalize(pd.read_csv(m5_path))
        validation = self.validate(m1=m1, m5=m5)
        return ReplayDataset(
            symbol=symbol,
            m1=m1,
            m5=m5,
            data_hash=self._frame_hash(m1, m5),
            source=f"{m1_path}|{m5_path}",
            validation=validation,
        )

    def load_parquet_pair(self, *, symbol: str, m1_path: Path, m5_path: Path) -> ReplayDataset:
        """Load an explicit M1/M5 Parquet pair under the strict data contract."""
        m1 = self._normalize(pd.read_parquet(m1_path))
        m5 = self._normalize(pd.read_parquet(m5_path))
        validation = self.validate(m1=m1, m5=m5)
        return ReplayDataset(
            symbol=symbol,
            m1=m1,
            m5=m5,
            data_hash=self._frame_hash(m1, m5),
            source=f"{m1_path}|{m5_path}",
            validation=validation,
        )

    @staticmethod
    def validate(*, m1: pd.DataFrame, m5: pd.DataFrame) -> dict[str, Any]:
        m1_report = validate_closed_series(data=m1, timeframe_seconds=60)
        m5_report = validate_closed_series(data=m5, timeframe_seconds=300)
        ohlc_errors: list[dict[str, Any]] = []
        for timeframe, frame in (("M1", m1), ("M5", m5)):
            bad = frame[
                (frame["high"] < frame[["open", "close"]].max(axis=1))
                | (frame["low"] > frame[["open", "close"]].min(axis=1))
                | (frame["high"] < frame["low"])
            ]
            if not bad.empty:
                ohlc_errors.append({"timeframe": timeframe, "rows": bad.index[:20].tolist()})
        m1_closes = set((m1["time"].astype(float) + 60.0).round(6))
        m5_closes = set((m5["time"].astype(float) + 300.0).round(6))
        alignment_errors = sorted(m5_closes.difference(m1_closes))
        valid = bool(
            m1_report["valid"]
            and m5_report["valid"]
            and not ohlc_errors
            and not alignment_errors
        )
        return json_safe(
            {
                "state": "VALID" if valid else "WARNING_OR_INVALID",
                "valid": valid,
                "timezone": "UTC",
                "m1": m1_report,
                "m5": m5_report,
                "ohlc_errors": ohlc_errors,
                "m5_closes_without_m1_close": alignment_errors[:50],
                "missing_candles_are_never_filled": True,
            }
        )

    @staticmethod
    def timeline(
        dataset: ReplayDataset,
        *,
        start_time: float,
        end_time: float,
    ) -> tuple[list[dict[str, Any]], int, int]:
        m1_times = dataset.m1["time"].astype(float)
        m5_times = dataset.m5["time"].astype(float)
        m1_start = max(0, int(m1_times.searchsorted(start_time - 60.0, side="left")))
        m5_start = max(0, int(m5_times.searchsorted(start_time - 300.0, side="left")))
        m1_end = int(m1_times.searchsorted(end_time, side="right"))
        m5_end = int(m5_times.searchsorted(end_time, side="right"))
        local_m1 = dataset.m1.iloc[m1_start:m1_end].reset_index(drop=True)
        local_m5 = dataset.m5.iloc[m5_start:m5_end].reset_index(drop=True)
        timeline = build_closed_candle_timeline(m5_data=local_m5, m1_data=local_m1)
        selected: list[dict[str, Any]] = []
        for row in timeline:
            if float(row["event_time"]) < start_time or float(row["event_time"]) > end_time:
                continue
            selected.append(
                {
                    **row,
                    "newly_closed_m1": [m1_start + int(i) for i in row["newly_closed_m1"]],
                    "newly_closed_m5": [m5_start + int(i) for i in row["newly_closed_m5"]],
                    "visible_m1_as_of_index": (
                        m1_start + int(row["visible_m1_as_of_index"])
                        if int(row["visible_m1_as_of_index"]) >= 0
                        else m1_start - 1
                    ),
                    "visible_m5_as_of_index": (
                        m5_start + int(row["visible_m5_as_of_index"])
                        if int(row["visible_m5_as_of_index"]) >= 0
                        else m5_start - 1
                    ),
                }
            )
        return selected, m1_start, m5_start

    @staticmethod
    def chart_rows(frame: pd.DataFrame, start: int, end: int) -> list[dict[str, Any]]:
        clipped = frame.iloc[max(0, start): min(len(frame), end + 1)]
        return json_safe(
            [
                {
                    "index": int(index),
                    "time": float(row.time),
                    "open": float(row.open),
                    "high": float(row.high),
                    "low": float(row.low),
                    "close": float(row.close),
                    "volume": float(getattr(row, "tick_volume", 0.0)),
                    **(
                        {"spread": float(getattr(row, "spread"))}
                        if hasattr(row, "spread") and getattr(row, "spread") == getattr(row, "spread")
                        else {}
                    ),
                    **(
                        {"bid_close": float(getattr(row, "bid_close"))}
                        if hasattr(row, "bid_close") and getattr(row, "bid_close") == getattr(row, "bid_close")
                        else {}
                    ),
                    **(
                        {"ask_close": float(getattr(row, "ask_close"))}
                        if hasattr(row, "ask_close") and getattr(row, "ask_close") == getattr(row, "ask_close")
                        else {}
                    ),
                }
                for index, row in clipped.iterrows()
            ]
        )
