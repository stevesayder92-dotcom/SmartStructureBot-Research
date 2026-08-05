# Phase 5A evidence consistency root-cause report

## Finding

The GOLD 3064 discrepancy was an implementation/export snapshot bug.

The Phase 4 replay audit called `run_pipeline` on the decision-time candle
prefix. At index 3064 that canonical snapshot reported:

- first candidate: 2944;
- first qualification: 2980;
- qualification available: 2980;
- initial failure trigger structure: 2986;
- active failure trigger structure: 2986 at 4566.42;
- trigger became selectable at 3028;
- entry: 3064.

The Phase 4 visual exporter instead ran the final 5,515-candle pipeline once,
then passed those full-history structure points into
`QualifiedRetracementEngine` for earlier decisions. Availability filtering
prevented direct future-index use, but later candles had already changed the
classification and confirmation metadata of historical swings. That path
therefore selected qualification 2988 and trigger 3027.

These were not intentional “first versus latest” fields. They came from
different structural snapshots.

## Repair

`core/evidence_contract.py` now defines the vocabulary consumed by audits and
exporters:

- `first_candidate_index`: immutable first approved internal break;
- `first_qualification_index`: immutable first candle at which the configured
  model qualifies the candidate;
- `qualification_available_at_index`: first causal availability of that
  qualification;
- `initial_failure_trigger_index`: first trigger structure selected after
  qualification;
- `active_failure_trigger_index` and
  `active_failure_trigger_level`: current trigger at the decision candle;
- `trigger_updated_at_index`: candle when the active trigger most recently
  became selectable;
- `trigger_update_count`: number of changes after initial selection;
- `entry_index`: canonical current decision candle or null.

`qualification_index` remains a compatibility alias for
`first_qualification_index`. `failure_trigger` remains a compatibility alias
for `active_failure_trigger`. The evidence validator raises an error if either
alias disagrees.

The same fields are copied into:

- the Director `retracement` root;
- the Director `entry` root;
- SignalLedger events;
- ReplayInspector records;
- CSV/JSON audits;
- canonical review rows;
- chart annotations.

## Other corrected evidence

- GOLD 4050 agrees after canonical export: qualification 4013, trigger 4021,
  entry 4050. Its causally selected origin is 3982, not the Phase 4
  full-history exporter’s 3979.
- GOLD 3849 was not a canonical entry. At the decision-time snapshot it was a
  bullish `RETRACEMENT_CANDIDATE` with no qualification, trigger, setup ID, or
  entry. It remains in the visual package only as an exporter-discrepancy
  example.

No Hybrid thresholds or qualification outcomes were changed to increase
trade count.

