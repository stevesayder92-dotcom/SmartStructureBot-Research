# Final Prefix-Causal Integrity Repair code report

## Preserved without strategy change

The frozen 60 first entries, setup and sequence identities, M5/M1 ownership, synchronized closed-candle clock, one-re-entry ceiling, Fibonacci orientation, M1 body-edge stop, M5 structural stop plus ATR tolerance, emergency stop, targets, partial rules, management thresholds, Director authority and sequence accounting are unchanged.

## Correctness replacements

- `core/prefix_causality.py` adds the immutable `CausalSwingLedger`.
- `PrefixParentViabilityStateMachine` replaces final-window high/low inspection with event-by-event extension proof and invalidation.
- `PrefixCausalReentryCoordinator` evaluates only candidates available at each merged M1/M5 close and applies the documented M5 tie-break for identical timestamps.
- `PrefixCausalTrailLedger` creates immutable trail candidate/proof/commit events from the current prefix.
- `CausalInvarianceTester` compares physical prefixes against multiple ordinary and adversarial future suffixes.
- `core/presimulator_repair.py` routes canonical parent, re-entry and Attempt-2 evidence through these prefix-causal owners.

## Evidence and tests

`tools/run_final_prefix_causal_repair.py` reruns the exact frozen 60, compares the previous repair with the causal result, generates 60 charts and every requested audit. `tests/test_final_prefix_causality.py` contains the 25 mandated deterministic tests. The complete repository contains 291 passing tests.

No order API exists in the repair path and no order function was called.
