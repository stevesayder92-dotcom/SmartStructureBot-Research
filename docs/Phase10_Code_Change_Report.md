# Phase 10 Exact Code-Change Report

## New contracts

- `core/fibonacci_contract.py`: causal directional impulse anchors, complete
  Fibonacci levels, configurable thresholds, depth zones, and same-parent
  re-entry reassessment.
- `core/semantic_swing_hierarchy.py`: contextual decision roles above raw
  3/3 fractals with ATR displacement and availability indexes.
- `core/adaptive_decision.py`: hard-block separation from grades and risk
  modifiers.

## Canonical expert pipeline

`core/expert_strategy.py` now:

- requires correct-direction candle bodies for first entry;
- publishes same-direction origin BOS and impulse-cycle detail;
- rejects a retracement that breaks the 100% cycle origin;
- publishes Fibonacci under retracement, setup, entry, decision, and cycle
  evidence;
- publishes semantic swing hierarchy under the canonical structure root;
- publishes setup grade, risk modifier, hard blockers, and soft factors;
- rejects an entry whose logical stop is not beyond the entry price;
- preserves current-candle and no-future contracts.

## HTF context

`build_expert_htf_context` retains strict 2-of-3 but now accepts a configured
policy. It reports `STRONG_ALIGNED`, `ALIGNED`,
`SINGLE_STRONG_SUPPORT`, `MIXED_BUT_USABLE`, `CONFLICT`, or `RANGING`
behavior with an explicit risk modifier.

## Stops, trails, and re-entry

`core/steve_trade_management.py` now:

- uses lower body edge for BUY invalidation and upper body edge for SELL;
- applies M5 ATR tolerance outside that body edge;
- requires an invalidating candle body to point against the trade;
- requires correct-direction and minimum-body displacement before a later
  continuation BOS can prove a trail;
- stores the entry-time Fibonacci contract;
- moves first failure to
  `FIRST_ENTRY_FAILED_RETRACEMENT_ACTIVE`;
- exposes `parent_retracement_active` and `reentry_monitoring`;
- reassesses Fibonacci with the same parent anchors;
- requires a correct-direction fresh re-entry BOS;
- preserves one re-entry maximum and cloned initial sizing logic.

## Configuration and launcher

`PipelineOptions`, `RuntimeConfig`, `application_runtime`, and both research
config files expose Fibonacci thresholds, HTF policy, single-strong support,
and trail proof displacement. `OILCash#` is accepted as a safe configurable
symbol, although no OIL data was supplied for this audit.

## Tests and evidence

- 25 new mandated Phase 10 tests.
- 150 total tests.
- 20 fresh, closed-candle M5 examples excluding all Phase 9 example keys.
- PNG, HTML, CSV, JSON, funnel, coverage, and manual review artifacts.
