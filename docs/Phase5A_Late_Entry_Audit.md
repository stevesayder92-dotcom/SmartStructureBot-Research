# Phase 5A entry freshness audit

## Canonical requested examples

| Index | Canonical status | First qualification | Active trigger | Qualification delay | Trigger delay | Distance after qualification | Classification |
|---:|---|---:|---:|---:|---:|---:|---|
| 3064 | Valid bearish entry | 2980 | 2986 | 84 candles | 78 candles | 6.663 ATR | DELAYED_BUT_SAME_RETRACEMENT |
| 3849 | Candidate, no canonical entry | — | — | — | — | — | AMBIGUOUS |
| 4050 | Valid bearish entry | 4013 | 4021 | 37 candles | 29 candles | 6.411 ATR | DELAYED_BUT_SAME_RETRACEMENT |

Both canonical entries retained a trigger explicitly tied to the same
qualified retracement and had zero active-trigger replacements. They are
therefore delayed but not automatically stale under the current descriptive
classification.

## Full comparison-set audit

The 21 qualified GOLD M1 comparison setups produced:

- 3 `DELAYED_BUT_SAME_RETRACEMENT`;
- 18 `AMBIGUOUS` setups without an entry in their selected evidence snapshot;
- 0 automatically classified `FRESH_ENTRY`;
- 0 automatically blocked as stale.

The comparison version of 3849 is deliberately separated from the canonical
result. It appeared as a delayed entry only under the flawed full-history
structure snapshot.

Phase 5A adds measurement and classification only. No delay limit or stale
entry block was added.

