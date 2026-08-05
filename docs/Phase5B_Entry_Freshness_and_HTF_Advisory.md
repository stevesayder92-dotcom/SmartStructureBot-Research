# Phase 5B — Entry Freshness and HTF Advisory Contracts

## Entry freshness

`EntryFreshnessEngine` publishes first qualification, active trigger and entry
indexes; candles since qualification and trigger; ATR distance; trigger update
count; same-retracement and counter-structure assertions; classification,
reasons and causal validity.

Classifications are `FRESH_ENTRY`, `MATURE_ENTRY`,
`DELAYED_SAME_RETRACEMENT`, `STALE_RETRACEMENT_ENTRY`, and `AMBIGUOUS`.

The compared policies are `STRUCTURE_ONLY`,
`STRUCTURE_PLUS_ATR_DISTANCE`, `STRUCTURE_PLUS_TIME_AND_DISTANCE`, and
`TRIGGER_REFRESH`. Time and ATR limits are explicit research configuration,
not optimized results. A freshness verdict never changes canonical entry.

## HTF advisory comparison

Every entry context compares `PREFER_M30_M15` with
`allow_single_strong=true`, `CONSENSUS_2_OF_3`, `STRONGEST_SINGLE`, and
`H1_ANCHOR`.

Each reports `ALIGNED`, `CONFLICT`, `NO_CLEAN_CONTEXT`,
`SINGLE_STRONG_SUPPORT`, or `MULTI_FRAME_SUPPORT`. Every record contains
`advisory_only=true` and `hard_block_applied=false`.

## Manual review

Steve’s sheet provides `ACCEPT`, `REJECT`, and `UNCERTAIN` plus manual
protected swing, replacement point, freshness verdict and reason. Protection,
freshness and HTF policies stay advisory until that review is analysed.

