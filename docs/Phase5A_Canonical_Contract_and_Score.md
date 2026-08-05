# Phase 5A canonical evidence and score contract

## Immutable fields

Within one qualified setup, these fields never move:

- setup origin BOS;
- `first_candidate_index`;
- `first_qualification_index`;
- `qualification_available_at_index`;
- `initial_failure_trigger_index`;
- setup identity ingredients.

## Mutable fields

These may evolve causally without changing setup identity:

- active pullback end;
- `active_failure_trigger_index`;
- `active_failure_trigger_level`;
- `trigger_updated_at_index`;
- `trigger_update_count`;
- current significance measurements;
- entry index, which is populated only on the current accepted candle.

Every active trigger contains the setup’s origin BOS, first candidate,
qualification, and `belongs_to_same_qualified_retracement=true`. Points before
qualification cannot be selected, preventing stale triggers from previous
setups.

## Score range

The public `significance_score` is bounded to 0–100. The prior chart value
105.0 resulted from additive components whose theoretical total exceeded
100:

- internal structure break;
- relative range;
- ATR displacement;
- persistence;
- overlap;
- counter-structure support.

Phase 5A preserves that additive value as `raw_significance_score` and caps
only the public display score. `score_minimum=0`, `score_maximum=100`, and
`score_contract=DISPLAY_SCORE_CAPPED_0_100_RAW_SCORE_PRESERVED` are explicit.
Hybrid qualification still uses the raw component score against the existing
threshold, so qualification outcomes did not silently change.

## Protection evidence

Decision protection now publishes:

- selection reasons and causal availability;
- origin BOS and impulse-cycle start;
- whether it belongs to the same impulse cycle;
- whether a newer eligible swing exists;
- all newer candidate summaries;
- wick-only crossings that survived;
- invalidating candle OHLC and explicit body-close/wick flags.

These additions are audit metadata only. Phase 5A does not loosen the
body-close protection rule or automatically replace the selected swing.

