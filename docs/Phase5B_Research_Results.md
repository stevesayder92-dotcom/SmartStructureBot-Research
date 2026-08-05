# Phase 5B — Research Results

## Closed-candle acquisition

| Dataset | Result | Closed candles | Notes |
|---|---:|---:|---|
| GER40Cash# M5 | available | 5,000 | monotonic, unique, forming candle excluded |
| GOLD# M5 | available | 5,000 | monotonic, unique, forming candle excluded |
| GOLD# M1 | available | 6,000 | expands the retained 5,515-candle history |
| US100Cash# M5 | unavailable | 0 | position-1 payload still contained a forming candle |
| US30Cash# M5 | unavailable | 0 | position-1 payload still contained a forming candle |

The missing datasets were rejected without a safety bypass. Weekend/session
gaps are reported in the acquisition audit and were not treated as duplicate
or non-monotonic data.

## Expanded causal replay

| Dataset | Cycles | Candidates | Qualified | Protection unavailable | Hybrid replacements | Invalidations | Director entries | Bull/Bear | Entries / 1,000 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GER40 M5 5,000 | 98 | 98 | 2 | 71 | 67 | 27 | 0 | 0 / 0 | 0.0000 |
| GOLD M5 5,000 | 99 | 99 | 5 | 55 | 72 | 39 | 1 | 0 / 1 | 0.2041 |
| GOLD M1 6,000 | 137 | 137 | 12 | 76 | 100 | 49 | 1 | 1 / 0 | 0.1695 |

All three datasets reported zero causal violations and zero pipeline failures.
The GER40 qualified-engine candidate was rejected by the Director because the
qualified retracement had no active failure trigger. A raw pre-qualification
counter swing had previously been substituted by `ContinuationEngine`; Phase
5B now blocks that path as `WAITING_FOR_FAILURE_TRIGGER`.

## Protection policy comparison

`candidate_count` in the CSV is the total candidate catalog population across
unique decision snapshots, not a unique-swing count.

| Dataset | Policy | Selected | No protection | Invalidations | Replacements | Wrong cycle | Future / stale |
|---|---|---:|---:|---:|---:|---:|---:|
| GER40 M5 | Origin defending | 28 | 70 | 27 | 0 | 0 | 0 / 0 |
| GER40 M5 | Latest proven | 76 | 22 | 22 | 67 | 0 | 0 / 0 |
| GER40 M5 | Hybrid proven | 76 | 22 | 22 | 67 | 0 | 0 / 0 |
| GOLD M5 | Origin defending | 45 | 54 | 39 | 0 | 0 | 0 / 0 |
| GOLD M5 | Latest proven | 79 | 20 | 32 | 72 | 0 | 0 / 0 |
| GOLD M5 | Hybrid proven | 79 | 20 | 32 | 72 | 0 | 0 / 0 |
| GOLD M1 | Origin defending | 62 | 75 | 49 | 0 | 0 | 0 / 0 |
| GOLD M1 | Latest proven | 120 | 17 | 45 | 100 | 0 | 0 / 0 |
| GOLD M1 | Hybrid proven | 120 | 17 | 45 | 100 | 0 | 0 / 0 |

Latest-proven and hybrid produced identical automated totals on these
datasets. Hybrid is the recommended policy for Steve’s review because it
retains the explicit minimum-importance guard; it is not permanently
activated. Manual-review agreement is unavailable until Steve completes the
review workbook.

## Canonical invalidation audit

Twenty invalidations were reproduced from exact Director decision snapshots.
The canonical population reproduced 20/20 (100%). Fifty-one attempted records
did not reproduce from a canonical Director snapshot; they are excluded from
canonical statistics and exported separately as comparison/exporter
discrepancies.

All 20 canonical invalidations were directional body closes. Wick-only
crossings remain non-invalidating.

## Entry freshness

Current expanded entries:

- GOLD M5 index 4591: `STALE_RETRACEMENT_ENTRY`;
- GOLD M1 index 3636: `STALE_RETRACEMENT_ENTRY`.

Accepted Phase 5A reference entries:

| Entry | Candles since qualification | Candles since trigger | ATR distance | Structure only | + ATR | + time and ATR | Trigger refresh |
|---|---:|---:|---:|---|---|---|---|
| 3064 | 76 | 37 | 5.868852 | allow | block | block | block |
| 4050 | 37 | 29 | 6.411290 | allow | block | block | block |

Entry 3064 remains a Phase 5B canonical entry. Entry 4050 is now blocked
earlier by `WAITING_FOR_VALID_DECISION_PROTECTION`; the table reports the
requested counterfactual freshness treatment from its accepted Phase 5A
decision snapshot. Thresholds were not chosen from these two entries.

## HTF advisory

No causal H1/M30/M15 histories accompanied the expanded entry decisions.
Therefore all four policies report `NO_CLEAN_CONTEXT` for both current
entries. No HTF hard block was applied.

## Manual package

The final package contains:

- 2 Director-confirmed canonical-entry charts;
- 20 canonical invalidation charts;
- 6 policy replacement examples;
- 2 delayed-entry examples;
- 12 rejected micro-noise/unqualified examples;
- 42 total charts, an HTML report, CSV review sheet and formatted XLSX review
  workbook.

Every decision label uses data available by the event candle. The 20 candles
after the event are outcome display only.

## Recommendation and blockers

Proceed to manual ownership/freshness review. Do not begin simulation yet.
The major blockers are unreviewed policy replacement points, uncalibrated
freshness thresholds, missing safe US100/US30 data, absent causal HTF histories
for expanded entries, and no approved final HTF gate.

