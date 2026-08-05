# Phase 4 model comparison and readiness

## Datasets

- Frozen GER40Cash# M5: 400 candles, retained exactly as the chronology
  regression fixture.
- Closed GOLD# M1: 5,515 available historical candles, exceeding the required
  comparable-data minimum.

A fresh 2,000+ GER40Cash# M5 feed and US100Cash# dataset were not available
inside the permitted workspace. The MT5 acquisition attempt could not be
completed in this sandbox, so this report does not invent those results.

## Results

| Dataset / model | Candidates | Qualified | Protection invalidations | Triggers | Validator approvals | Unique entries | Chronology blocks | Duplicate/consumed blocks | Entries / 1,000 | Errors / leaks / stale |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GER40 400 / FIRST_COUNTER_BREAK | 5 | 2 | 3 | 0 | 0 | 0 | 0 | 0 | 0.0000 | 0 / 0 / 0 |
| GER40 400 / FIRST_COUNTER_STRUCTURE | 5 | 1 | 3 | 0 | 0 | 0 | 0 | 0 | 0.0000 | 0 / 0 / 0 |
| GER40 400 / RELATIVE_RANGE | 5 | 2 | 3 | 0 | 0 | 0 | 0 | 0 | 0.0000 | 0 / 0 / 0 |
| GER40 400 / ATR_AND_STRUCTURE | 5 | 1 | 3 | 0 | 0 | 0 | 0 | 0 | 0.0000 | 0 / 0 / 0 |
| GER40 400 / HYBRID | 5 | 1 | 3 | 0 | 0 | 0 | 0 | 0 | 0.0000 | 0 / 0 / 0 |
| GOLD 5,515 / FIRST_COUNTER_BREAK | 122 | 30 | 102 | 15 | 107 | 8 | 0 | 99 | 1.4774 | 0 / 0 / 0 |
| GOLD 5,515 / FIRST_COUNTER_STRUCTURE | 122 | 21 | 102 | 6 | 49 | 3 | 0 | 46 | 0.5540 | 0 / 0 / 0 |
| GOLD 5,515 / RELATIVE_RANGE | 122 | 24 | 102 | 6 | 49 | 3 | 0 | 46 | 0.5540 | 0 / 0 / 0 |
| GOLD 5,515 / ATR_AND_STRUCTURE | 122 | 21 | 102 | 6 | 49 | 3 | 0 | 46 | 0.5540 | 0 / 0 / 0 |
| GOLD 5,515 / HYBRID | 122 | 21 | 102 | 6 | 49 | 3 | 0 | 46 | 0.5540 | 0 / 0 / 0 |

The accepted Phase 2 audit baseline reported six GER40 entries, but all six
had `initial_pullback_start < origin_trend_bos` and are intentionally not
restored.

“Validator approvals” counts causal approval observations before lifecycle
deduplication. “Unique entries” counts one consumed entry per stable setup.
The duplicate/consumed count therefore demonstrates the lifecycle guard; it
is not an error count.

## Recommendation

Keep `HYBRID` as the research default. It removes nine GOLD qualifications
that the counter-break-only model accepts, converges with the two
structure-aware alternatives on the same three unique entries, and exposes
its relative-size/displacement/structure reasons. This recommendation is
based on structural agreement and explainability, not on selecting the
highest or lowest trade count.

The current evidence is not enough to declare production readiness. The
visual package has six causally qualified setups, of which three reach unique
Hybrid entry candidates. The requested six unique qualified entries cannot
be honestly produced from the available default-model data. More closed
GER40/US100 history and Steve’s manual verdicts are required before threshold
approval.

## Remaining strategy questions

1. Should a directional body close beyond dominant protection invalidate on
   the first close, or require a minimum body fraction/displacement?
2. What maximum lookback should define “recent” micro corrections when the
   impulse leg is unusually long?
3. Should one extremely strong counter structure qualify even when no prior
   micro-correction baseline exists?
4. Which broker/server timezone is authoritative for XM historical review?
5. Should `EXPIRED` be time-based, origin-replacement-based, or session-based?
6. After Steve labels the review sheet, which disagreements are definition
   errors versus tunable significance thresholds?

## Safety conclusion

Research readiness: **conditional pass**. Causal chronology, current-candle
entry publication, setup identity, closed-candle checks, and lifecycle
consumption are covered by tests. Production/live readiness: **not approved**.
No simulator, final stop engine, ML optimizer, automatic HTF gate, or order
execution has been added.

