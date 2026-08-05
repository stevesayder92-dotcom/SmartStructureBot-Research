# Phase S1B code-diff report

## Preserved without strategy change

- canonical `run_pipeline` / `SystemStateDirector` ownership;
- closed-candle M5-parent/M1-child replay chronology;
- immutable ReplayEvent and StateSnapshot hash chain;
- retracement, stop, target, management and one-re-entry rules;
- 12 accepted Phase S1 sessions and the frozen research dataset;
- all 291 inherited strategy tests and 37 Phase S1 contracts.

The original Phase S1 clean release was not edited. S1B was implemented in a
separate working/release tree.

## Added

- financial account/configuration/result models;
- paper account, paper order, paper position and paper broker;
- symbol-specific estimated contract profiles and safe suffix normalization;
- native/static conversion to ZAR with missing-rate contracts;
- native/session/volatility/fixed spread models;
- deterministic seeded, fixed, volatility-aware and no-slippage controls;
- opening/closing/partial commission and optional swap framework;
- logical/emergency-risk and margin-constrained position sizing;
- side-correct bid/ask fill engine and intrabar ambiguity resolver;
- hash-linked immutable execution ledger;
- equity, drawdown, cost, risk, attempt/sequence, symbol/session analytics;
- independent canonical and six shadow money accounts;
- financial bug/review flags and complete financial export set;
- portable seven-symbol M1/M5 CSV library with manifests;
- bounded asynchronous date-range replay API;
- account dialog, permanent account bar, paper/close tickets, active position,
  money story, equity chart, display modes, chart interaction and data library;
- exact 50-test S1B financial contract and 20 visual acceptance scenarios.

## Modified integration surfaces

- `ReplaySession` now passes immutable Director actions into a separate paper
  service and publishes paper snapshots without changing canonical decisions.
- `DatasetAdapter` preserves optional spread/bid/ask fields.
- `ExportService` publishes ledgers, statements and financial analytics.
- `simulator.app` exposes safe paper reprice and data-library/build endpoints.
- CLI exposes library/range operations.
- Bible, README, config and package metadata identify Phase S1B research mode.

## Deliberately not added

- MT5 order placement or position control;
- automatic demo/live execution;
- unverified claims that XM contract/spread metadata is exact;
- a rule allowing the paper engine to create or modify strategy signals.
