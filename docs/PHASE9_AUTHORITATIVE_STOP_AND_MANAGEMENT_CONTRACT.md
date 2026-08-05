# Phase 9 authoritative Steve stop and management contract

Status: research/replay only. Entry selection remains the accepted
`EXPERT_SPEC_V1` model. No order API is imported or called.

## Four independent roles

1. `DOMINANT_DECISION_PROTECTION`
   - Owner: `ProtectedStructureEngine`.
   - Purpose: the meaningful M30/M15/H1 HL or LH showing that the approved
     dominant direction remains valid.
   - It governs trend/setup survival and re-entry permission.

2. `SETUP_LOGICAL_INVALIDATION`
   - Owner: `ProtectedStructureEngine`.
   - Purpose: disprove the specific failed-retracement entry.
   - BUY selects the relevant pre-trigger LOW/LL from the same qualified
     retracement. SELL selects its relevant pre-trigger HIGH/HH.
   - M5 boundary is beyond that wick by configurable causal ATR tolerance.
   - M1 boundary is the relevant swing candle close.
   - The selected structure, trigger and confirmations must exist by entry.

3. `EMERGENCY_BROKER_STOP`
   - Owner: `TradeGuardian`.
   - Purpose: catastrophe, disconnection, crash or unavailable software exit.
   - It is wider than the logical boundary and is not the normal loss level.
   - It is calculated and visualized only in this release.

4. `TRAILING_PROTECTION`
   - Owner: `TrailingProtectionEngine`.
   - A raw post-entry HL/LH starts as `TRAIL_CANDIDATE_UNPROVEN`.
   - A later same-direction body-close BOS must break the associated impulse
     extreme before that candidate becomes `TRAIL_PROVEN`.
   - Protection moves only if the proven level tightens risk. It never loosens.
   - A body-close opposing BOS through meaningful protection exits.

## Initial invalidation record

Every canonical entry stores:

```text
invalidation_role
structure_index / structure_type
wick_price / body_close_level
atr_at_entry / atr_tolerance
logical_boundary
available_at_index / causal_valid
selection_reason
post_entry_candles_used = false
```

It also stores `logical_stop`, `emergency_broker_stop`,
`logical_exit_condition`, and `emergency_exit_condition` separately.

## M5 closed-candle failure

Wicks do not invalidate. A close must be beyond the tolerant logical boundary
and meet either the configured body-strength or distance-beyond-boundary
threshold. Defaults (`0.15 ATR` boundary tolerance, `0.35 ATR` body strength,
`0.10 ATR` distance) are research defaults, not optimized constants.

## Re-entry

The state after first logical failure is
`FIRST_ATTEMPT_FAILED_AWAITING_FRESH_STRUCTURE`; re-entry is not armed.
The engine requires a fresh post-failure counter-swing, a later fresh
same-direction trigger, a body-close BOS beyond that trigger, intact dominant
protection, and `reentry_count == 0`. Attempt two has a distinct event ID and
clones the configured sizing profile. Its failure sets
`CLOSED_AFTER_SECOND_FAILURE`.

## M1 fallback

`core.m1_fallback.evaluate_m1_fallback` opens only while a qualified M5
pullback is active and no current M5 entry exists. M1 uses the canonical
Director pipeline, must begin within the parent M5 pullback, and enters only
at the current M1 close-confirmed BOS. A later proven M5 structure may replace
M1 protection only when it does not loosen risk.

## Configurable research comparisons

Management profiles are `STRUCTURE_RUNNER_ONLY`, `TWIN_POSITION_50_50`, and
`PARTIAL_PLUS_RUNNER`. TP1 models are previous HTF extreme, previous impulse
extreme, configurable R, and nearest meaningful liquidity.

Sessions remain London, New York and overlap research windows. HTF policy
alternatives remain comparisons; this repair does not tune the entry dataset.
