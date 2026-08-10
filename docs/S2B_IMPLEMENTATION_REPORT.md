# SmartStructureBot Phase S2B Implementation Report

## Final result

Phase S2B is implemented behind the explicit research-only policy
`EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE`. The runtime default remains
`COUNTER_CONFIRMED_ACTIVE`. No live or demo execution was enabled and no order
API was called.

Final verdict: **RESEARCH_REJECTED**.

The hypothesis succeeded technically: 77 parents earned causal pre-ACTIVE M1
permission and entered a median 46 minutes earlier. It did not improve the
paired population economically under the existing structural-R replay:
expectancy declined from -0.076986R to -0.141892R and profit factor declined
from 0.936321 to 0.877132. S2B must not replace the default policy.

## Implemented architecture

- `M1PermissionPolicyEngine` publishes explicit parent and permission states.
- The variant may observe only after the exact M5 parent is causally ARMED.
- It must prove the complete inherited M1 counter-structure, sequence,
  body-close BOS, direction, wick, noise, freshness, boundary, protection,
  stop and quality contracts.
- A valid early BOS close owns attempt 1 and consumes later M1/M5 first-entry
  competitors. Existing management and the one-reentry maximum are unchanged.
- S2B owns only `[ARMED, ACTIVE)`. At or after ACTIVE it returns the exact
  accepted baseline resolver result.
- Simulator snapshots and overlays expose parent state, permission state,
  rejection reason, owner, trigger, entry, logical stop and quality without
  decision authority.

## Evidence population

- 290 candidate setups scanned.
- 192 paired HTF-aligned parents.
- 762 pre-ACTIVE events across 171 unique parents.
- 161 valid early events across 77 unique parents.
- 77 committed timing changes; 115 non-early parents were exactly unchanged.
- Seven available symbols: AUDUSD#, EURUSD#, GBPUSD#, GER40Cash#, GOLD#,
  US100Cash#, USDJPY#.
- US30Cash# and OILCash# were unavailable and are explicitly reported as such.
- 30 deterministic synchronized visual cases cover all mandated groups A-L.

## Test result

- Focused S2B: 30 passed.
- Complete strategy discovery: 340 passed.
- Complete simulator discovery: 87 passed.
- Distinct discovery total: 427 passed, zero failures. The 30 focused tests
  are included in the 340-test strategy discovery count.

## Required A-Z answers

**A.** Yes. The S2A.1 future-data repair is preserved. Initial decisions use
closed prefixes and causal parent snapshots; retrospective M5 outcome fields
are excluded from entry calculations.

**B.** Yes. Permission, quality, entry price and logical stop passed the full
A-E suffix-invariance contract.

**C.** 762 pre-ACTIVE events were evaluated.

**D.** 161 events passed every inherited M1 rule.

**E.** 77 unique setups earned early permission.

**F.** 77 setups changed attempt-1 timing. This equals the earned set exactly.

**G.** Median improvement: 46.0 minutes earlier.

**H.** Median direction-adjusted raw entry-price improvement: 0.00009. Because
raw units cannot be aggregated meaningfully across FX, gold and indices, the
portable normalized median is also reported: 0.320946 of baseline stop risk.

**I.** Median logical-stop-distance change: -0.00003 raw mixed-symbol units.
Negative means tighter. This raw aggregate has the same cross-symbol limitation.

**J.** 41 early stops were tighter.

**K.** 36 early stops were wider; zero were unchanged.

**L.** 4 setups changed from baseline M5 to S2B M1.

**M.** 73 changed from a later baseline M1 to an earlier S2B M1.

**N.** Zero duplicate first entries.

**O.** Baseline: 35.4167% win rate, -0.076986R expectancy, 0.936321 profit
factor (68 wins, 124 losses, 192 sequences).

**P.** S2B: 36.9792% win rate, -0.141892R expectancy, 0.877132 profit factor
(71 wins, 121 losses, 192 sequences).

**Q.** Paired all-population sequence-R difference: mean -0.064906R, median
0.000000R. Among the 77 changed setups: mean -0.161843R, median +0.171825R.

**R.** Using the fixed +/-0.05R equality band: 40 early better, 4 same, 33
early worse.

**S.** 13 baseline winners became S2B losses.

**T.** 16 baseline losses became S2B wins.

**U.** S2B did not bypass the false/micro/noise gates. The funnel rejected
155 MICRO_NOISE events across 75 parents, 34 WICK_ONLY events across 26,
153 NO_BODY_CLOSE_BOS events across 84, 112 INCOMPLETE_SEQUENCE events across
85, and 119 NO_COUNTER_STRUCTURE events across 86. This proves gate
preservation, not that every accepted early trade is economically high quality;
the worse expectancy shows that early permission still admits costly timing.

**V.** Per-symbol paired expectancy change: AUDUSD +0.281344R; EURUSD
+0.321141R; GBPUSD -0.171627R; GER40 -0.566350R; GOLD -0.020879R; US100
+0.328443R; USDJPY -0.538449R. Full win rates, expectancy and stop medians are
in `research_runs/s2b/per_symbol_comparison.csv`.

**W.** Yes. GER40 deteriorated materially (-0.566350R), US100 improved
materially (+0.328443R), and GOLD was near neutral/slightly worse (-0.020879R).
One universal early-permission policy is therefore not supported by this sample.

**X.** No. US30 and OIL are not represented because synchronized datasets were
not available. They are not silently substituted or inferred.

**Y.** No. The evidence does not support replacing ACTIVE-only permission.
Timing and win rate improved, but expectancy and profit factor worsened.

**Z.** Steve should review all 30 cases before any future research decision,
with special attention to the 13 baseline-winner/S2B-loser reversals, the 16
opposite conversions, all wider-stop cases, GER40 and USDJPY deterioration,
and all rejected group-L examples. Manual verdict fields are provided in the
visual manifest.

## Interpretation limitation

The paired outcome layer uses the existing structural-R management replay on
identical data and rules. It is a valid policy comparison, but it is not a net
account backtest with independently recomputed spread, slippage and commission
cashflows. Neither result is evidence of production profitability. The negative
expectancy of both variants is an additional reason to keep this research-only.

