from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd

from core.mt5_connector import (
    MarketDataContractError,
    connect_mt5,
    get_market_data,
    resolve_symbol,
    validate_closed_candles,
)


BASE_NOW = datetime(
    2026,
    7,
    23,
    12,
    7,
    tzinfo=timezone.utc,
)
M5_SECONDS = 300
CURRENT_BAR_START = 1784808300


def make_frame(
    count: int = 100,
    *,
    end_open: int = CURRENT_BAR_START - M5_SECONDS,
) -> pd.DataFrame:
    start = end_open - (count - 1) * M5_SECONDS
    times = [
        start + offset * M5_SECONDS
        for offset in range(count)
    ]
    return pd.DataFrame(
        {
            "time": times,
            "open": [100.0] * count,
            "high": [101.0] * count,
            "low": [99.0] * count,
            "close": [100.5] * count,
            "tick_volume": [1] * count,
            "spread": [0] * count,
            "real_volume": [0] * count,
        }
    )


def validate(
    frame: pd.DataFrame,
    **overrides,
):
    arguments = {
        "symbol": "GER40Cash#",
        "timeframe": "M5",
        "requested_candles": 100,
        "minimum_history": 100,
        "source_timezone": "UTC",
        "broker_timezone": "Africa/Johannesburg",
        "stale_after_intervals": 3,
        "strict_missing_candles": False,
        "now_utc": BASE_NOW,
    }
    arguments.update(overrides)
    return validate_closed_candles(
        frame,
        **arguments,
    )


class FakeMT5:
    TIMEFRAME_M5 = 5

    def __init__(self, frame: pd.DataFrame):
        self.frame = frame
        self.calls = []

    def symbols_get(self):
        return [
            SimpleNamespace(name="GER40Cash#"),
        ]

    def copy_rates_from_pos(
        self,
        symbol,
        timeframe,
        start_pos,
        candles,
    ):
        self.calls.append(
            (
                symbol,
                timeframe,
                start_pos,
                candles,
            )
        )
        return self.frame.to_records(index=False)


class ClosedCandleDataSafetyTest(unittest.TestCase):
    def test_disconnected_mt5_is_rejected(self):
        class DisconnectedMT5:
            @staticmethod
            def initialize():
                return False

            @staticmethod
            def last_error():
                return (1, "terminal unavailable")

        with self.assertRaisesRegex(
            ConnectionError,
            "initialization failed",
        ):
            connect_mt5(DisconnectedMT5())

    def test_forming_candle_is_excluded_at_source(self):
        api = FakeMT5(make_frame())
        data, audit = get_market_data(
            "GER40Cash#",
            "M5",
            100,
            mt5_api=api,
            minimum_history=100,
            source_timezone="UTC",
            broker_timezone="Africa/Johannesburg",
            now_utc=BASE_NOW,
        )

        self.assertEqual(api.calls[0][2], 1)
        self.assertTrue(
            audit.forming_candle_excluded
        )
        self.assertEqual(len(data), 100)

    def test_forming_candle_in_payload_is_rejected(self):
        frame = make_frame()
        frame.loc[
            frame.index[-1],
            "time",
        ] = CURRENT_BAR_START

        with self.assertRaisesRegex(
            MarketDataContractError,
            "forming candle",
        ):
            validate(frame)

    def test_server_wall_clock_is_converted_to_real_utc(self):
        server_last_open = int(
            datetime(
                2026,
                7,
                23,
                15,
                0,
                tzinfo=timezone.utc,
            ).timestamp()
        )
        frame = make_frame(
            count=3,
            end_open=server_last_open,
        )

        normalized, audit = validate(
            frame,
            requested_candles=3,
            minimum_history=3,
            source_timezone="Etc/GMT-3",
            broker_timezone="Etc/GMT-3",
        )

        expected_utc = pd.Timestamp(
            "2026-07-23T12:00:00Z"
        )
        self.assertEqual(
            normalized.loc[2, "time_utc"],
            expected_utc,
        )
        self.assertEqual(
            normalized.loc[2, "time"],
            int(expected_utc.timestamp()),
        )
        self.assertEqual(
            audit.last_timestamp_utc,
            expected_utc.isoformat(),
        )

    def test_duplicate_timestamps_are_rejected(self):
        frame = make_frame()
        frame.loc[
            frame.index[-1],
            "time",
        ] = frame.loc[
            frame.index[-2],
            "time",
        ]

        with self.assertRaisesRegex(
            MarketDataContractError,
            "Duplicate",
        ):
            validate(frame)

    def test_missing_candle_gap_is_detected(self):
        frame = (
            make_frame(count=101)
            .drop(index=50)
            .reset_index(drop=True)
        )

        _, audit = validate(frame)
        self.assertEqual(audit.missing_gap_count, 1)
        self.assertEqual(audit.missing_intervals, 1)

        with self.assertRaisesRegex(
            MarketDataContractError,
            "Missing candle gaps",
        ):
            validate(
                frame,
                strict_missing_candles=True,
            )

    def test_stale_data_is_rejected(self):
        frame = make_frame(
            end_open=(
                CURRENT_BAR_START
                - 10 * M5_SECONDS
            )
        )

        with self.assertRaisesRegex(
            MarketDataContractError,
            "stale",
        ):
            validate(frame)

    def test_insufficient_history_is_rejected(self):
        with self.assertRaisesRegex(
            MarketDataContractError,
            "Insufficient history",
        ):
            validate(
                make_frame(count=99),
            )

    def test_symbol_suffix_resolution_is_safe(self):
        self.assertEqual(
            resolve_symbol(
                "GER40Cash",
                ["GER40Cash#"],
            ),
            "GER40Cash#",
        )

        with self.assertRaisesRegex(
            MarketDataContractError,
            "Ambiguous",
        ):
            resolve_symbol(
                "GER40Cash",
                [
                    "GER40Cash#",
                    "GER40Cash##",
                ],
            )


if __name__ == "__main__":
    unittest.main()
