# Pre-Simulator Canonical Repair code report

## Scope

This repair starts from `SmartStructureBot_FinalSequenceElite_v1_20260731_CANONICAL`. It preserves the frozen 60 first entries and makes no change to MT5 order execution. The build remains closed-candle research only.

## New canonical module

`core/presimulator_repair.py` owns the repaired hybrid layer:

- chronological sequence equity;
- parent viability after Attempt-1 failure;
- strategic M1-versus-M5 re-entry ownership;
- complete fresh Attempt-2 management;
- causal event-time partial commitment;
- emergency-risk Model A/Model B calculation;
- authoritative one-action-per-candle management overlay.

## Existing module change

`core/fidelity_patch.py` accepts causal opposing-BOS event indexes during management simulation. The optional parameter defaults to an empty sequence, so existing callers and the accepted Attempt-1 baseline remain compatible.

## Evidence runner

`tools/run_presimulator_repair.py` freezes the original 60 entries, runs accepted baseline/current SequenceElite/repaired hybrid on the same cases and split assignments, publishes all mandatory audits, and regenerates 60 readable review charts. It cannot place orders.

## Tests

`tests/test_presimulator_repair.py` contains the 39 deterministic repair tests named in the Strategy Bible. The complete repository test suite contains 266 passing tests.

## Removed or replaced behaviour

- non-chronological sequence peak construction;
- final-state-informed partial sizing;
- protection-intact as a complete re-entry decision;
- merely technical M1 BOS automatically outranking strategic readiness;
- incomplete/basic Attempt-2 simulation;
- multiple supporting engines mutating position state independently.

## Safety

The frozen population has zero entry drift, duplicates, future-candle use, unfinished-candle use, third attempts, incomplete Attempt-2 records, non-causal partial decisions, sequence-accounting violations, emergency account-risk breaches, and order API calls.
