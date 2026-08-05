# Phase 4 qualified retracement specification

## Authoritative semantics

A setup begins with a causally confirmed same-direction impulse or
continuation BOS. Ordinary opposing candles and micro swings remain
continuation noise. A post-origin opposing move becomes a candidate only
when a directional candle body closes through approved internal continuation
structure from that impulse leg. It becomes a qualified retracement only
when explainable relative significance and/or meaningful causal
counter-structure supports it while the dominant protected swing remains
intact.

For bearish trend, the candidate breaks an internal high, develops bullish
counter-structure below the protected LH, then becomes an entry candidate
only when a bearish body closes below a meaningful post-qualification
counter low/HL. Bullish logic is the inverse.

A wick through dominant protection does not invalidate the setup by default.
A configured directional body close beyond protection publishes
`INVALIDATED_BY_PROTECTED_SWING`; it is not a continuation entry.

## Root contract

The Director publishes `retracement` with owner
`QualifiedRetracementEngine`. The contract includes:

- state, owner, `as_of_index`, availability, and `causal_valid`;
- origin BOS and causal availability indexes;
- candidate start and the broken internal continuation structure;
- significance model, score, relative-size ratio, ATR displacement,
  duration, overlap, prior-micro baseline, structure count, classification,
  and human-readable reasons;
- decision protected swing and its intact/invalidation status;
- qualification index and availability index;
- causal counter-structure points;
- post-qualification failure trigger;
- setup invalidation, entry index/price/direction, and readiness.

The internal continuation structure has `type`, `side`, `index`, `price`,
`confirmed_at_index`, `tradeable_at_index`, `origin_bos_index`,
`role=INTERNAL_CONTINUATION_STRUCTURE`, `importance`, and `causal_valid`.

## State machine

1. `NO_POST_BOS_COUNTER_MOVE`: causal origin exists, no approved opposing
   break exists.
2. `MICRO_COUNTER_NOISE`: opposing activity exists but does not establish an
   approved candidate.
3. `RETRACEMENT_CANDIDATE`: first meaningful internal continuation structure
   was broken, but maturity/significance is not yet established.
4. `WAITING_FOR_COUNTER_STRUCTURE`: candidate persists without sufficient
   supporting evidence.
5. `QUALIFIED_RETRACEMENT`: B-with-C qualification is causally available.
6. `WAITING_FOR_FAILURE_TRIGGER`: qualified setup exists but no valid
   post-qualification trigger failure is present.
7. `ENTRY_CANDIDATE`: current directional body close breaks the qualified
   retracement’s failure trigger.
8. `ENTRY_VALIDATED`: EntryValidator accepts the current candidate.
9. `CONSUMED`: the Director published the one permitted canonical entry.
10. `INVALIDATED_BY_PROTECTED_SWING`: dominant protection was violated by the
    configured directional body close.
11. `EXPIRED`: reserved terminal state for a later explicit expiry policy;
    Phase 4 does not invent a timeout.

Setup identity is created only from a qualified state. Candidate/noise states
cannot create consumable setup IDs.

## Configurable significance models

- `FIRST_COUNTER_BREAK`: research baseline; candidate break alone can mature.
- `FIRST_COUNTER_STRUCTURE`: requires supporting causal counter structure.
- `RELATIVE_RANGE`: meaningful internal break plus candidate excursion
  relative to prior impulse-leg opposing corrections.
- `ATR_AND_STRUCTURE`: meaningful internal break plus ATR-normalized
  displacement and structure evidence.
- `HYBRID`: mandatory internal break with relative-size, displacement,
  persistence, overlap, and counter-structure scoring.

The default is `HYBRID`. Thresholds are defined by
`QualifiedRetracementPolicy`; no symbol prices or dataset indexes are
hard-coded.

## Non-negotiable causal rules

- incomplete candles are excluded by the connector;
- a future-confirmed swing or BOS is unavailable;
- pre-origin compression cannot seed a candidate or setup;
- the origin BOS is not the entry BOS;
- a failure trigger must belong to the qualified retracement and become
  available after qualification;
- mutable pullback boundaries do not change identity;
- one setup is consumed at most once;
- HTF remains advisory in Phase 4;
- live orders, simulation, stop engines, ML optimization, and automatic HTF
  hard gating remain outside this phase.

