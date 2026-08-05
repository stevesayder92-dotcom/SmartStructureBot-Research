# Phase 5B — Code Diff and Forward-Research Readiness

## Source boundary

The accepted Phase 5A tree was copied to a new Phase 5B working source. The
Phase 5A source and the original Desktop project were not edited.

## Added runtime modules

- `core/impulse_cycle.py` owns impulse-cycle construction, protection
  candidate catalogs and the three advisory replacement policies.
- `core/entry_freshness.py` owns deterministic freshness classification and
  four non-enforcing policy comparisons.
- `core/protection_audit.py` reproduces protection invalidations only from an
  exact canonical decision snapshot.

## Changed runtime modules

- `core/qualified_retracement.py` now creates an explicit cycle, delegates
  decision protection to the cycle-aware selector, and publishes all policy
  comparisons.
- `core/pipeline_runner.py` publishes independent Director roots for impulse
  cycle, decision protection, setup invalidation, trailing protection and
  entry freshness. HTF comparison remains advisory.
- `core/system_director.py` owns the new root contracts.
- `core/htf_context.py` compares all four requested HTF policies without
  applying a hard gate.

## Added research and review tools

- closed-candle Phase 5B acquisition;
- expanded multi-symbol causal comparison;
- canonical invalidation reproduction;
- consolidated chart/HTML/CSV review export;
- formatted Excel review workbook build and verification.

## Test expansion

The suite increased from 62 to 81 tests. New coverage includes wrong-cycle
rejection, stable origin protection, BOS-proven replacement, raw-latest-swing
rejection, causal replacement, waiting-without-fallback, deterministic
freshness, same-setup trigger refresh, stale classification without strategy
mutation, HTF advisory-only behavior, canonical audit reproduction,
full-history contamination rejection, independent protection roots and static
absence of order APIs. It also contains a real-data regression proving that a
missing qualified failure trigger cannot be replaced by a raw counter swing.

## Forward-research readiness

The project is ready for manual review of ownership and freshness evidence. It
is not ready for trade simulation or live capital.

Remaining gates:

1. Steve must review the consolidated charts and mark protection/freshness
   judgments.
2. A final protection replacement policy must be selected after that review.
3. Freshness thresholds must be calibrated across broader regimes, not two
   highlighted entries.
4. A final HTF gate must be selected after causal multi-timeframe histories
   are available for all tested entries.
5. US100 and US30 datasets must pass the existing closed-candle guard; safety
   rejection cannot be bypassed.
6. Simulator design remains intentionally out of scope.

## Execution safety

No `order_send`, `order_check`, `positions_get`, `TRADE_ACTION_DEAL`, broker
execution adapter or simulator call is present in the runtime. MT5 was used
only for symbol discovery and closed-candle research acquisition.
