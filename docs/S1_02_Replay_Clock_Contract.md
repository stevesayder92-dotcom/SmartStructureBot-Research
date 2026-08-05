# Replay-clock contract

All timestamps are UTC epoch seconds. Candle `time` is its open time; visibility
begins at `time + timeframe_seconds`.

Rules:

1. Exclude forming candles.
2. Merge M1 and M5 closes chronologically.
3. At equal close time process M5 parent, M1 child, then M5 fallback.
4. Seed event zero with the final M1/M5 candles already closed at session start.
5. Pass only the current M5 as-of index to `run_pipeline`.
6. Bound M1 child discovery to its active parent window, preserving global indices.
7. Never reveal a candle with close time after the event.
8. Never skip events at high playback speed.

An event's visible prefix is defined by `visible_m1_rows` and
`visible_m5_rows`. The chart additionally may display older history that was
already closed; it may never display the unrevealed suffix. A same-time event's
`processing_order` is recorded in the ledger and export.

Replay speed changes wall-clock delay only. Step, play and maximum speed must
produce identical final hashes.
