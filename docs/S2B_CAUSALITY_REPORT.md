# SmartStructureBot Phase S2B Causality Report

## Causal boundary

S2B may act only in the half-open interval `[parent_armed_time,
parent_active_time)`. ARMED permits observation, not execution. An early entry
requires a fully confirmed M1 sequence and occurs on the valid BOS candle close.
At or after ACTIVE, the research resolver returns the exact baseline report.

The causal parent snapshot contains identity, direction, protection and Fib
facts available at the decision close. Eventual M5 entry, stop, outcome,
MFE/MAE and management facts are analytics-only and cannot enter permission,
quality, entry, stop or arbitration.

## Trigger-order defect found during audit

The inherited trigger loop could scan an older confirmed swing far forward to
a later BOS before considering a newer swing whose valid BOS occurred earlier.
That made loop order, rather than candle time, choose the apparent first valid
entry. A frozen GOLD regression reproduced the defect.

The S2B pre-ACTIVE resolver now evaluates every causally available trigger
independently and chooses the earliest valid BOS close, tie-breaking by the
latest causally available trigger. The arbitration is explicitly limited to
pre-ACTIVE entries. This prevents both trigger-order delay and accidental
ACTIVE-era strategy drift.

Permanent regressions:

- `test_first_valid_arbitration_uses_earliest_bos_not_trigger_loop_order`
- `test_variant_returns_exact_baseline_resolution_after_active`

## Population invariants

- 77 setups earned early permission.
- Exactly 77 setup rows changed entry timing.
- 115 setups did not earn early permission.
- Across those 115, mismatches in entry owner/time/price, logical stop or
  sequence result: zero.
- Duplicate first entries: zero.
- Post-entry suffix changes to permission/quality/price/stop: zero.
- Live/demo capability: false.
- Order API calls: zero.

## Rejection funnel

The event-level funnel retains every decision and exact rejection state:

| State | Events | Unique setups |
|---|---:|---:|
| EARLY_VALID | 161 | 77 |
| INCOMPLETE_SEQUENCE | 112 | 85 |
| LOW_CAUSAL_QUALITY | 16 | 15 |
| MICRO_NOISE | 155 | 75 |
| NO_BODY_CLOSE_BOS | 153 | 84 |
| NO_COUNTER_STRUCTURE | 119 | 86 |
| OUTSIDE_PARENT | 1 | 1 |
| PROTECTION_BROKEN | 6 | 1 |
| STALE | 4 | 3 |
| WICK_ONLY | 34 | 26 |
| WRONG_BODY_DIRECTION | 1 | 1 |

Counts are event-level and may overlap the same parent across decision times;
unique-setup counts are separately reported to prevent inflation.

## Suffix proof

The focused suite tests the exact decision prefix against actual, extended,
materially modified, reversal and changed-eventual-M5 suffixes. It proves that
future candles and retrospective analytics cannot change early permission,
quality components, entry price, logical stop or the earlier decision.

