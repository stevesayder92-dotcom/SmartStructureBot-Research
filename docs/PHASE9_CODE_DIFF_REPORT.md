# Phase 9 code diff report

Working source: `SmartStructureBot_Phase9_SteveStops_20260729`.
The Desktop original was not modified.

## Replaced

- Removed `core/advanced_trade_management.py`. That file owned the rejected
  universal broad-wick ± 1 ATR stop, immediate every-fractal trailing and
  stop-out-armed re-entry behavior.
- Removed its obsolete regression test.
- Added `core/steve_trade_management.py` as the sole expert management owner.

## Canonical integration

- `core/expert_strategy.py`
  - preserves `_simulate_retracements` and entry selection;
  - selects the same-retracement pre-BOS invalidation structure;
  - publishes logical and emergency stop values separately;
  - publishes dominant protection at the Director `protection` root;
  - publishes logical invalidation at `setup_invalidation`;
  - publishes the causal manager at `trailing_protection`.
- `core/setup_lifecycle.py`
  - runtime state now owns `SteveTradeManagementEngine`;
  - a different parent setup resets the one-re-entry allowance only when the
    previous attempt is no longer active.
- `core/management_evidence.py`
  - forces charts/audits to consume canonical root contracts;
  - rejects future invalidation structures and stale entry indexes.

## M1 and configuration

- Added `core/m1_fallback.py`:
  - M1 gate requires an active qualified M5 pullback with no M5 entry;
  - M1 executes the same canonical pipeline;
  - M1 origin must belong to the parent M5 pullback;
  - initial logical stop is the relevant M1 swing candle close.
- `core/runtime_config.py` now validates management profile, TP1 model,
  logical/emergency/trailing tolerances, session list and research matrices.
- `core/application_runtime.py` constructs the management engine from those
  validated values.
- `core/replay_runner.py` accepts that configured persistent runtime state so
  application and replay still share one pipeline and contract.

## Evidence and tests

- Added 23 explicitly mandated deterministic tests plus extra regression
  coverage for M1 fallback and new-parent reset.
- Updated three Phase 7 assertions that encoded the rejected rules; entry
  trigger/price assertions remain unchanged.
- Added `tools/run_phase9_management_evidence.py` for the preserved ten plus
  ten new real-data examples.
- Added `tools/finalize_phase9_audits.py` and
  `tools/run_phase9_test_suite.py`.

## Invariants

- Accepted entry selection code was not outcome-tuned.
- `ENGINE_SENSITIVITY=3` confirmation availability remains causal.
- The initial stop never reads post-entry candles.
- No live mode or MT5 order function was added.
