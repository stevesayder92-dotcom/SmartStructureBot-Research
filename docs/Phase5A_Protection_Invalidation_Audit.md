# Phase 5A protected-swing invalidation audit

## Population and sample

The Phase 4 comparison reported 102 GOLD M1 protected-swing invalidations.
Its saved transition catalog contains 101 unique
origin/candidate/invalidation identities; the difference is a catalog
transition-count artifact.

The Phase 5A audit selected:

- five earliest unique invalidations;
- five latest unique invalidations;
- ten deterministic random invalidations;
- ten bullish and ten bearish examples overall.

Each row in `protection_invalidation_audit.csv` includes the origin BOS,
protected swing, selection reason, availability, candidate start,
invalidating OHLC, body/wick classification, impulse-cycle provenance, newer
eligible swings, canonical reproduction result, chart, and Steve review
fields.

## Results

- 20/20 comparison invalidations were directional body closes.
- 0/20 were wick-only invalidations.
- 17/20 selected swings were marked inside the same impulse cycle.
- 3/20 selected swings predated the marked impulse-cycle boundary.
- 11/20 had a newer eligible protected swing in the comparison snapshot.
- 12/20 reproduced as protected invalidations when the full canonical
  decision-time pipeline was run at the same index.
- 8/20 did not reproduce canonically.

## Conclusion

The high rate is not evidence that body-close protection should be weakened.
The sampled candles genuinely crossed their selected comparison levels by
body close. However, impulse-cycle ownership and full-history versus
decision-time swing selection materially inflate or alter the comparison
population.

Protection replacement remains a manual calibration question. No automatic
“use the newer swing” rule was added because that could either tighten or
loosen protection depending on direction and must be approved from the
charts.

