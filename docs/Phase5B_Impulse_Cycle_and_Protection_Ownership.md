# Phase 5B — Impulse-Cycle and Protection Ownership

## Status

Research contract implemented. No protection policy is approved for live
capital, no order execution exists, and no freshness or HTF comparison changes
the canonical entry outcome.

## One ownership chain

Every continuation setup now has this causal chain:

`origin BOS → impulse cycle → qualified retracement → decision protection
→ setup invalidation → entry → trailing protection (post-entry only)`

The cycle identifier is deterministic:

`CYCLE-{symbol}-{timeframe}-{direction}-{origin_bos_index}`

The `ImpulseCycleEngine` publishes the cycle ID, direction, origin BOS and
availability, impulse boundaries, retracement start, terminal index, causal
validity, reasons and one required lifecycle status.

## Three independent protection roles

`DECISION_PROTECTION` is the main-trend HL/LH. It validates the active trend
and cycle. `SETUP_INVALIDATION` is the defended extreme inside the qualified
retracement. It validates the specific setup. `TRAILING_PROTECTION` is
post-entry only and remains `NOT_ACTIVE_BEFORE_OPEN_TRADE` in Phase 5B.

No role can silently substitute for another.

## Candidate contract

Every visible protection candidate records structure index, price, type,
confirmation and availability, cycle membership, relationship to the origin
or continuation BOS, confirming BOS, structural importance, replacement
eligibility, score, causal validity and rejection reasons.

A candidate is eligible only if it is decision-time available, predates entry,
has the correct HL/LH type and side, belongs to the active cycle, meets minimum
importance, and directly precedes the origin BOS or is proven by a later
same-direction continuation BOS.

If none qualifies, the state is
`WAITING_FOR_VALID_DECISION_PROTECTION`. There is no unrelated fallback.

## Research policies

- `ORIGIN_DEFENDING_SWING` holds the swing preceding the origin BOS.
- `LATEST_PROVEN_CONTINUATION_SWING` replaces it only with a newer same-cycle
  HL/LH proven by a later same-direction BOS.
- `HYBRID_PROVEN_REPLACEMENT` also requires minimum structural importance.

The default research baseline is `ORIGIN_DEFENDING_SWING`. This is not a
permanent selection; final approval requires Steve’s visual review.

## Invalidation and reproducibility

Protection remains directional body-close based. Wick-only crossings survive.
The auditor accepts only exact Director snapshots whose cycle and protection
IDs match. Full-history classifications and descriptive saved catalogs are
rejected as contaminated sources.

