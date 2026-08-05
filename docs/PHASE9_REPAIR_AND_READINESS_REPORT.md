# Phase 9 repair and research-readiness report

## Outcome

Phase 8 entry selection and its ten reviewed entry identities were preserved.
The rejected stop, trailing and re-entry manager was removed and replaced by
the authoritative Steve V2 management contracts.

This release is ready for Steve's visual/manual review. It is not approved for
automated demo execution and has no live-order path.

## Implemented

- Four independent canonical roles:
  - dominant decision protection;
  - setup logical invalidation;
  - emergency broker stop;
  - causally proven trailing protection.
- Relevant defended pre-BOS initial invalidation selection.
- M1 candle-close and M5 tolerant body-close invalidation.
- Configurable ATR, body, distance, emergency and trail parameters.
- Raw trail candidates remain unproven.
- Later same-direction body-close BOS proves HL/LH continuation.
- Protection never loosens.
- Opposing meaningful BOS exit.
- Three management profiles and four TP1 objective models.
- One fresh-structure re-entry with distinct event ID.
- Second failure permanently closes the parent.
- New parent setup resets the one-re-entry allowance.
- M1 fallback coordinator and non-loosening M1-to-M5 transition contract.
- Runtime configuration now supplies these parameters to replay/application.

## Evidence results

- Preserved reviewed entries: 10.
- New real closed-data examples: 10.
- New-example instruments: 3 GOLD, 3 GER40, 4 US100.
- Sessions: London, New York and overlap.
- Requested behavior categories unavailable: none.
- Relevant broad extreme rejected in favour of the directly defended
  structure: 14 of 20.
- Examples with at least one proven trail: 6.
- Opposing meaningful BOS exits: 5.
- Valid one-time re-entries within the 60-candle review window: 9.
- Re-entry rejected after dominant protection failure: 6.
- Order API calls: 0.

The high observed re-entry count is evidence for manual review, not proof that
the re-entry definition is final. It was not tuned against outcomes.

## Tests

The final complete suite ran 125 tests in 103.707 seconds:

```text
Ran 125 tests in 103.707s
OK
PHASE9_SAFETY_CONFIRMATION: No order API imported or called.
```

This includes the 23 requested deterministic tests plus M1 fallback,
new-parent reset and configuration wiring regressions.

## Safety audit

- `LIVE` remains rejected by runtime configuration.
- No `order_send` or equivalent order function exists in runtime source.
- MetaTrader 5 is used only for closed-candle acquisition.
- Initial stop selection records `post_entry_candles_used=false`.
- Chart future candles are management/outcome evidence only.
- Entry trigger, entry index and entry price were not outcome-tuned.

## Remaining blockers before automated demo

1. Steve must review the 20 charts and label ACCEPT / REJECT / UNCERTAIN.
2. The questions in `PHASE9_REMAINING_STRATEGY_QUESTIONS.md` need decisions,
   especially M5 invalidation strength, M1 body level and TP1 touch rule.
3. The M1 fallback coordinator is implemented and deterministic, but the
   forward application still needs a dual-timeframe scheduler that processes
   every M1 close while retaining the active M5 parent setup. It must be added
   only after the visual rule is accepted.
4. Paper/demo execution, spread/slippage, broker volume, tick-value sizing,
   disconnect recovery and restart persistence remain deliberately disabled.
5. Manual review must decide whether nine re-entries in twenty examples match
   Steve's intended definition of “fresh meaningful structure.”

## Recommendation

Review examples 11–20 first, then preserved examples 1–10. Do not tune the
defaults from win/loss outcomes. Reject or refine the structure labels
directly; only after that review should the dual-timeframe forward scheduler
and paper execution simulator be implemented.
