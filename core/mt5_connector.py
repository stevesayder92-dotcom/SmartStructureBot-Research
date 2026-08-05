from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

import pandas as pd


TIMEFRAME_SECONDS = {
    "M1": 60,
    "M5": 5 * 60,
    "M15": 15 * 60,
    "M30": 30 * 60,
    "H1": 60 * 60,
}


class MarketDataContractError(RuntimeError):
    """Raised when MT5 data is unsafe for a causal decision."""


@dataclass(frozen=True)
class CandleDataAudit:
    symbol: str
    timeframe: str
    source_timezone: str
    broker_timezone: str
    requested_candles: int
    received_candles: int
    forming_candle_excluded: bool
    first_timestamp_utc: str
    last_timestamp_utc: str
    last_timestamp_broker: str
    monotonic: bool
    unique: bool
    duplicate_count: int
    missing_gap_count: int
    missing_intervals: int
    stale: bool
    age_after_last_close_seconds: float
    sufficient_history: bool
    strict_missing_candles: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_mt5() -> Any:
    try:
        import MetaTrader5 as mt5
    except ImportError as error:
        raise RuntimeError(
            "MetaTrader5 is unavailable in this Python runtime"
        ) from error

    return mt5


def connect_mt5(mt5_api: Any = None) -> Any:
    api = mt5_api or _load_mt5()

    if not api.initialize():
        last_error = (
            api.last_error()
            if hasattr(api, "last_error")
            else None
        )
        raise ConnectionError(
            f"MT5 initialization failed: {last_error}"
        )

    return api


def shutdown_mt5(mt5_api: Any) -> None:
    if mt5_api is not None and hasattr(
        mt5_api,
        "shutdown",
    ):
        mt5_api.shutdown()


def timeframe_seconds(timeframe: str) -> int:
    normalized = str(timeframe).upper()

    if normalized not in TIMEFRAME_SECONDS:
        raise ValueError(
            f"Unsupported timeframe {timeframe!r}; "
            f"allowed: {sorted(TIMEFRAME_SECONDS)}"
        )

    return TIMEFRAME_SECONDS[normalized]


def resolve_symbol(
    requested_symbol: str,
    available_symbols: Iterable[str],
    preferred_suffix: str = "#",
) -> str:
    requested = str(requested_symbol).strip()
    available = sorted(
        {
            str(symbol).strip()
            for symbol in available_symbols
            if str(symbol).strip()
        }
    )

    if not requested:
        raise ValueError("Requested symbol cannot be empty")

    if requested in available:
        return requested

    if requested.endswith(preferred_suffix):
        raise MarketDataContractError(
            f"Exact suffixed symbol {requested!r} is unavailable"
        )

    matches = [
        symbol
        for symbol in available
        if symbol == requested + preferred_suffix
        or symbol.rstrip(preferred_suffix) == requested
    ]

    if len(matches) == 1:
        return matches[0]

    if not matches:
        raise MarketDataContractError(
            f"No MT5 symbol safely matches {requested!r}"
        )

    raise MarketDataContractError(
        f"Ambiguous MT5 symbol {requested!r}: {matches}"
    )


def _mt5_timeframe_constant(
    mt5_api: Any,
    timeframe: str,
) -> Any:
    normalized = str(timeframe).upper()
    attribute = f"TIMEFRAME_{normalized}"

    if not hasattr(mt5_api, attribute):
        raise ValueError(
            f"MT5 API has no {attribute} constant"
        )

    return getattr(mt5_api, attribute)


def _available_symbol_names(mt5_api: Any) -> list[str]:
    symbols = mt5_api.symbols_get()

    if symbols is None:
        raise MarketDataContractError(
            "MT5 returned no symbol catalogue"
        )

    return [
        str(item.name)
        for item in symbols
        if getattr(item, "name", None)
    ]


def validate_closed_candles(
    data: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    requested_candles: int,
    minimum_history: int,
    source_timezone: str,
    broker_timezone: str,
    stale_after_intervals: int,
    strict_missing_candles: bool,
    now_utc: Optional[datetime] = None,
) -> tuple[pd.DataFrame, CandleDataAudit]:
    if not isinstance(data, pd.DataFrame):
        raise TypeError("Market data must be a DataFrame")

    required = {
        "time",
        "open",
        "high",
        "low",
        "close",
    }
    missing = required.difference(data.columns)

    if missing:
        raise MarketDataContractError(
            "MT5 data is missing columns: "
            + ", ".join(sorted(missing))
        )

    if len(data) < int(minimum_history):
        raise MarketDataContractError(
            f"Insufficient history: received {len(data)}, "
            f"minimum {minimum_history}"
        )

    try:
        source_zone = ZoneInfo(source_timezone)
        broker_zone = ZoneInfo(broker_timezone)
    except Exception as error:
        raise MarketDataContractError(
            "source_timezone and broker_timezone must be "
            "explicit IANA timezone names"
        ) from error

    normalized = data.copy().reset_index(drop=True)
    numeric_time = pd.to_numeric(
        normalized["time"],
        errors="coerce",
    )

    if numeric_time.isna().any():
        raise MarketDataContractError(
            "MT5 candle timestamps must be numeric epoch seconds"
        )

    # Some MT5 brokers encode server wall-clock values in the numeric
    # epoch field instead of UTC. Interpret the field in the explicitly
    # configured source/server zone first, then convert to real UTC.
    source_wall_clock = pd.to_datetime(
        numeric_time,
        unit="s",
        utc=False,
    )
    timestamps = (
        source_wall_clock.dt.tz_localize(
            source_zone,
            ambiguous="raise",
            nonexistent="raise",
        )
        .dt.tz_convert(timezone.utc)
    )
    duplicate_count = int(
        timestamps.duplicated(keep=False).sum()
    )
    unique = duplicate_count == 0
    monotonic = bool(
        timestamps.is_monotonic_increasing
    )

    if not unique:
        raise MarketDataContractError(
            f"Duplicate candle timestamps detected: "
            f"{duplicate_count} rows"
        )

    if not monotonic:
        raise MarketDataContractError(
            "Candle timestamps are not strictly monotonic"
        )

    seconds = timeframe_seconds(timeframe)
    diffs = timestamps.diff().dt.total_seconds()
    gaps = diffs[diffs > seconds]
    missing_intervals = int(
        sum(
            max(0, round(float(gap) / seconds) - 1)
            for gap in gaps
        )
    )

    if strict_missing_candles and not gaps.empty:
        raise MarketDataContractError(
            f"Missing candle gaps detected: {len(gaps)} gaps, "
            f"{missing_intervals} missing intervals"
        )

    if now_utc is None:
        now = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        now = now_utc.replace(tzinfo=timezone.utc)
    else:
        now = now_utc.astimezone(timezone.utc)

    current_bar_start_epoch = (
        int(now.timestamp()) // seconds
    ) * seconds
    forming_mask = timestamps >= pd.to_datetime(
        current_bar_start_epoch,
        unit="s",
        utc=True,
    )

    if bool(forming_mask.any()):
        raise MarketDataContractError(
            "Currently forming candle was present in the "
            "closed-candle dataset: latest_open_utc="
            f"{timestamps.iloc[-1].isoformat()}, "
            f"current_bar_start_utc="
            f"{pd.to_datetime(current_bar_start_epoch, unit='s', utc=True).isoformat()}"
        )

    latest_open = timestamps.iloc[-1].to_pydatetime()
    latest_close = latest_open.timestamp() + seconds
    age_after_close = max(
        0.0,
        now.timestamp() - latest_close,
    )
    stale = bool(
        age_after_close
        > int(stale_after_intervals) * seconds
    )

    if stale:
        raise MarketDataContractError(
            f"MT5 data is stale by {age_after_close:.0f} seconds "
            f"after the last candle close"
        )

    normalized["time_utc"] = timestamps
    normalized["time"] = timestamps.map(
        lambda timestamp: int(timestamp.timestamp())
    )
    normalized["time_broker"] = (
        timestamps.dt.tz_convert(broker_zone)
    )
    normalized.attrs["source_timezone"] = (
        source_zone.key
    )
    normalized.attrs["broker_timezone"] = (
        broker_zone.key
    )

    audit = CandleDataAudit(
        symbol=symbol,
        timeframe=str(timeframe).upper(),
        source_timezone=source_zone.key,
        broker_timezone=broker_zone.key,
        requested_candles=int(requested_candles),
        received_candles=len(normalized),
        forming_candle_excluded=True,
        first_timestamp_utc=(
            timestamps.iloc[0].isoformat()
        ),
        last_timestamp_utc=(
            timestamps.iloc[-1].isoformat()
        ),
        last_timestamp_broker=(
            timestamps.iloc[-1]
            .tz_convert(broker_zone)
            .isoformat()
        ),
        monotonic=monotonic,
        unique=unique,
        duplicate_count=duplicate_count,
        missing_gap_count=len(gaps),
        missing_intervals=missing_intervals,
        stale=stale,
        age_after_last_close_seconds=(
            age_after_close
        ),
        sufficient_history=(
            len(normalized) >= minimum_history
        ),
        strict_missing_candles=bool(
            strict_missing_candles
        ),
    )
    normalized.attrs["candle_data_audit"] = (
        audit.to_dict()
    )
    return normalized, audit


def get_market_data(
    symbol: str,
    timeframe: str,
    candles: int = 100,
    *,
    mt5_api: Any = None,
    minimum_history: Optional[int] = None,
    source_timezone: str = "UTC",
    broker_timezone: str = "UTC",
    stale_after_intervals: int = 3,
    strict_missing_candles: bool = False,
    preferred_suffix: str = "#",
    now_utc: Optional[datetime] = None,
) -> tuple[pd.DataFrame, CandleDataAudit]:
    api = mt5_api or _load_mt5()
    resolved_symbol = resolve_symbol(
        requested_symbol=symbol,
        available_symbols=_available_symbol_names(api),
        preferred_suffix=preferred_suffix,
    )
    mt5_timeframe = _mt5_timeframe_constant(
        api,
        timeframe,
    )

    # Position zero is the currently forming candle. Starting from one
    # is the primary closed-candle safety boundary.
    rates = api.copy_rates_from_pos(
        resolved_symbol,
        mt5_timeframe,
        1,
        int(candles),
    )

    if rates is None:
        last_error = (
            api.last_error()
            if hasattr(api, "last_error")
            else None
        )
        raise MarketDataContractError(
            f"No MT5 data returned for {resolved_symbol}: "
            f"{last_error}"
        )

    frame = pd.DataFrame(rates)
    return validate_closed_candles(
        frame,
        symbol=resolved_symbol,
        timeframe=timeframe,
        requested_candles=int(candles),
        minimum_history=(
            int(minimum_history)
            if minimum_history is not None
            else int(candles)
        ),
        source_timezone=source_timezone,
        broker_timezone=broker_timezone,
        stale_after_intervals=(
            stale_after_intervals
        ),
        strict_missing_candles=(
            strict_missing_candles
        ),
        now_utc=now_utc,
    )
