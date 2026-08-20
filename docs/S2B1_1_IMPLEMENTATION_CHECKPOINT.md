# S2B.1.1 Implementation Checkpoint

## Status

Core deterministic repair implemented on top of the exact S2B.1 `022ee1a` archive. This checkpoint is **not yet the final S2B.1.1 release** because the full multi-symbol A/B/C research rerun and the native Windows simulator regression suite still need to complete.

## Implemented

- Bible-first S2B.1.1 change-order section added before source modifications.
- Causal repaired second-touch path added alongside legacy S2B.1 control behavior.
- Repaired Touch-2 candidate recognition uses the actual Touch_2_Index candle close and does not wait for N-right confirmation.
- Touch-Proximity ATR is frozen at Touch_2_Index.
- Frozen thresholds preserved: 0.25 ATR proximity, 0.35 ATR meaningful reaction, 3-bar minimum separation.
- Bullish double-bottom provisional trigger uses post-Touch-2 reaction HIGH.
- Bearish double-top provisional trigger uses post-Touch-2 reaction LOW.
- ProvisionalTrigger is derived from closed pre-BOS candles; BOS candle cannot create the level it breaks.
- Body-close BOS proof publishes `SECOND_TOUCH_PROVED_BY_BOS` in repaired mode.
- Legacy S2B.1 behavior remains available for Variant A/control.
- `select_setup_logical_invalidation()` explicitly honors `SECOND_TOUCH_WICK_EXTREME` and cannot substitute candle body edges for repaired second-touch entries.
- M1 repaired second-touch stop = exact Touch-2 wick, zero ATR tolerance.
- M5 repaired second-touch stop keeps existing causal ATR clock at `entry_index`, tolerance 0.15 ATR, BUY = wick - tolerance, SELL = wick + tolerance.
- Existing emergency-stop algorithm preserved.
- Complete semantic InitialStopContract builder added with 17 required fields + optional deterministic hash.
- Attempt stores immutable `initial_stop_contract` separately from mutable protection state.
- Synchronized M1 path propagates repaired second-touch evidence and wick ownership.
- Re-entry prefix-causality path supports repaired second-touch proof without legacy N-right trigger ownership.
- Simulator config gains opt-in `second_touch_causal_repair` flag; defaults remain disabled.
- Existing S2B research helper accepts legacy/repaired recognition mode.
- New repository-local `tools/run_s2b1_1_research.py` removes the sibling Codex control-file dependency and writes only under `research_runs/s2b1_1/`.
- S2B.1 clean-checkout hash test moved away from ignored `research_runs/s2b1/research_data_before.json` into tracked `test_data/s2b1_1/research_data_manifest.json`.
- New deterministic contract-integrity tests added.
- tasks.md created without Kiro.

## Tests completed in this environment

- Focused S2B.1 + S2B.1.1 + management/presimulator/Bible suites: **195 passed**.
- Repository `tests/` excluding the one environment-incompatible pickle test: **441 passed + 15 subtests passed**.
- S2B.1 legacy suite plus new S2B.1.1 suite: **126 passed** before later integration patches; focused final suite remained green.

## Environment limitation

The container uses a different Python/pandas runtime than the original Windows project environment. Tests that unpickle historical pandas objects fail here with:

`TypeError: StringDtype.__init__() takes from 1 to 2 positional arguments but 3 were given`

This is an environment deserialization mismatch, not an S2B.1.1 assertion failure. The native Windows project Python environment must run the full simulator suite before final release.

## Research-data integrity

All six canonical `research_data/` files remain byte-identical to the captured pre-implementation manifest (per-file SHA-256 equality = true).

## Remaining final-release work

1. Run the native Windows inherited simulator suite.
2. Execute complete multi-symbol A/B/C S2B.1.1 research runner.
3. Generate the four manual reconstruction reports (AUDUSD PB_2121, USDJPY PB_1538, GER40 PB_2066, GER40 PB_2365) against repository-local data.
4. Produce final A/B/C reconciliation metrics and visuals.
5. Re-check `research_data/` hashes after all research execution.
6. Verify zero live/demo/order API usage.
7. Review final diffs, then commit/push only after Steve approval.
