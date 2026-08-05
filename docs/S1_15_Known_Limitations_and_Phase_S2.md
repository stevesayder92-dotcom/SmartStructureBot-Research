# Known limitations and Phase S2 recommendations

## Phase S1B financial limitations (2026-08-03)

- Contract sizes, commission schedules, margin terms and minimum/step volumes
  are explicit estimated research profiles, not verified XM account metadata.
- Native candle spread is used when present; missing history falls back to a
  documented symbol/session model. Tick-by-tick spread paths are unavailable.
- Slippage is deterministic for repeatable sensitivity testing, but is not yet
  calibrated to historical XM fills, news conditions or account execution.
- Static research conversion rates make ZAR accounting explicit but are not a
  historical FX conversion feed.
- Swap is disabled by default; its enabled model is a framework, not a verified
  symbol/day broker schedule.
- OHLC intrabar ambiguity uses closed child bars where available and an honest
  conservative/flag fallback; it cannot reconstruct absent ticks.
- The portable library covers seven configured symbols and finite ranges.
- The UI is a synchronized custom research chart, not the full TradingView
  product or a broker terminal.
- No forward market-feed paper adapter or demo order adapter is implemented.
  Forward paper and automatic demo readiness therefore remain NO.

Before Phase S2 forward-paper work, capture exact XM `symbol_info` metadata,
verified commission/swap rules, historical or broker conversion data, and a
larger holdout/stress corpus. Preserve the Director/paper-execution boundary.

## Original Phase S1 limitations

Known limitations:

- Replay uses frozen historical broker candles; execution costs and fill
  uncertainty are not simulated.
- The 12 sessions are curated for behavioral coverage, not performance claims.
- Shadow policies are isolated comparison frameworks, not optimized managers.
- Bug rules cover the mandated initial categories but are diagnostic heuristics.
- Canonical pipeline construction is CPU-bound; building long sessions takes
  minutes, though browser playback is immediate after build.
- Manual acceptance by Steve remains outstanding.
- No demo or live order adapter exists in Phase S1.

Phase S2 should use the unchanged event ledger to compare management policies,
giveback control, runner preservation, M1/M5 re-entry ownership and transaction
cost sensitivity. It should add unbiased date-range sampling and holdout
statistics before any demo-readiness proposal. Every change must update the
Bible, code, evidence and tests in order. Do not add order execution until a
separate reviewed mandate explicitly authorizes it.
