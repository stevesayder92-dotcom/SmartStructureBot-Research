# Phase S1B architecture and ownership map

## Runtime flow

```text
Portable/frozen closed candles
        |
        v
ReplaySession + canonical pipeline adapter
        |
        v
SystemStateDirector -------------------------- strategy authority
        | committed action + immutable snapshot
        v
PaperExecutionReplayService ----------------- execution coordinator only
        |                          |
        v                          +--> isolated shadow PaperBrokers
PaperBroker
  |-- ContractSpecificationService
  |-- CurrencyConversionEngine
  |-- SpreadEngine -> explicit bid/ask
  |-- SlippageEngine -> deterministic adverse fill
  |-- CommissionEngine / SwapEngine
  |-- PositionSizer -> logical/emergency/margin caps
  |-- MarginEngine / IntrabarResolver
  |-- PaperAccount / PositionState
  +-- ExecutionLedger (hash linked)
        |
        +--> analytics, flags, exports, equity and money story
        +--> read-only browser interface
```

The Director owns whether the strategy enters, moves protection, takes a
partial, exits or permits re-entry. The paper subsystem owns whether that
committed action is economically executable under the selected account and
cost assumptions. It cannot create a signal or rewrite a stop.

## State isolation

Strategy snapshots and strategy event hashes do not include mutable UI state.
Canonical and shadow paper brokers each own separate account, position,
ledger, story and equity histories. They share only immutable strategy events,
closed candles and the deterministic cost seed. Account size may change fill
feasibility and P/L but not the Director action sequence.

## Safety boundary

- `ORDERS_ENABLED = False` and `PAPER_EXECUTION_ONLY = True`.
- No `MetaTrader5`, `order_send`, positions or broker network call exists in
  the simulator execution package.
- The server binds locally and accepts symbols/ranges from its configured data
  library; browser-supplied filesystem paths are rejected by design.
- Contract and conversion assumptions are labeled estimated research profiles.

## New root packages

- `simulator/execution`: paper broker, fills, contract/currency/cost/sizing/
  margin/intrabar/ledger engines.
- `simulator/analytics`: account, drawdown, equity, cost, risk, sequence,
  symbol and session metrics.
- `simulator/models/financial.py`: immutable configuration/results and mutable
  paper position/account state.
- `simulator/services`: paper replay, financial flags, data library, range
  build and financial exports.
- `simulator_data/library`: portable M1/M5 CSV data and source manifests.

## HTTP contracts

- `GET /api/health`
- `GET /api/sessions`
- `GET /api/data-library`
- `GET /api/data-library/{symbol}`
- `GET /api/replay/session/{session_id}`
- `POST /api/paper/reprice`
- `POST /api/replay/build`
- `GET /api/replay/build/{job_id}/status`
- `POST /api/review`
- `DELETE /api/replay/session/{generated_session_id}`

Generated-session deletion is restricted to the safe runtime root and the
`S1B-` session prefix.
