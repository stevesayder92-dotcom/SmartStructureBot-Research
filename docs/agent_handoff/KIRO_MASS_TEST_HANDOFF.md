# SmartStructureBot — Kiro Mass-Test Engineering Handoff

## Mission
Consolidate the latest SmartStructureBot strategy-fidelity repairs into one clean research branch, implement/verify the temporary `TP1_ONLY_RESEARCH` management variant, build a fast but strictly causal large-scale replay engine, and produce evidence that separates:

1. code/contract defects,
2. strategy execution fidelity,
3. strategy performance.

Kiro is engineering manpower, **not strategy authority**. Do not change the frozen strategy rules to improve results.

---

## Authoritative base
Start from the user's current SmartStructureBot repository. If the laptop repository is older or uncertain, use the latest packaged baseline `SmartStructureBot_Gate0_to_10_Cumulative.zip` as the minimum source baseline and then consolidate the Gate-11 fixes below.

Create a branch:

`research/gate11-tp1-only-mass-test`

Before editing, record:

- `git status`
- `git branch --show-current`
- `git rev-parse HEAD`
- `git log -1 --oneline`
- Python version
- SHA256 hashes for all research data files

Do not mutate historical source data.

---

# Frozen core strategy contract

## Trend
Per analyzed timeframe:

- NEUTRAL -> first distinct same-direction structural body-close break = CHOCH warning only.
- Second distinct same-direction structural body-close break = confirmed trend.
- Wick-only breaks do not count.
- Repeated closes through the same already-broken swing are not new breaks.
- Mirror HH logic for bullish and LL logic for bearish.

## Parent / retracement
- M5 is parent setup timeframe.
- M1 is synchronized child execution timeframe under the exact same M5 parent.
- Once trend confirms, immediately look for a retracement.
- Bullish parent: retracement counter-structure forms LHs; bullish body-close BOS through the relevant retracement LH is the entry.
- Bearish parent: retracement counter-structure forms HLs; bearish body-close BOS through the relevant retracement HL is the entry.
- Entry price is exactly the BOS candle close.
- No confirmation candle, retest, AI veto, second-touch veto, or score veto may redefine a structurally valid entry.

## Entry freshness
The parent body TP1 must still be ahead of entry at the BOS candle.

If it has already been crossed, block the trade with:

`TP1_BODY_TARGET_ALREADY_PASSED_NO_ENTRY`

## Initial SL
- BUY: immediate relevant pre-BOS low **wick**.
- SELL: immediate relevant pre-BOS high **wick**.
- Stop owner basis: `PRE_BOS_SWING_WICK_EXTREME`.
- Do not replace with a body edge.
- The owner is the final causal pre-BOS reaction swing, not an arbitrary earlier overall extreme.

## TP1
- BUY: upper body edge `max(open, close)` of the swing-high candle that existed immediately before the parent retracement started.
- SELL: lower body edge `min(open, close)` of the mirrored swing-low candle.
- TP1 is never the wick extreme.

## Re-entry
- Maximum one same-parent re-entry.
- Attempt 1 fails -> if original parent trend/protection/setup remains valid -> first fresh legitimate same-direction BOS may become Attempt 2.
- Attempt 2 gets a fresh BOS entry and fresh immediate pre-BOS wick stop.
- Attempt 2 inherits the same parent retracement-origin body TP1.
- No Attempt 3.

## M1
- M1 may enter earlier under the same M5 parent.
- M1 BOS close is entry.
- M1 stop is immediate pre-BOS wick.
- M1 inherits exact parent M5 TP1.
- Quality/scoring is advisory only; it cannot veto a structurally valid BOS.
- Second-touch is advisory/supporting evidence; it cannot delay or supersede a valid normal LH/HL failure BOS.
- `PARENT_ARMED` with `active_time=None` must never crash earned-early evaluation.

---

# Temporary research variant: TP1_ONLY_RESEARCH

This experiment is NOT the permanent strategy. It isolates the runner subsystem.

For every valid trade:

- same entry,
- same initial SL,
- same TP1,
- same one-reentry ceiling,
- if TP1 is touched: close **100%** at the exact TP1 price,
- `tp1_partial_fraction = 1.0`,
- `runner_fraction = 0.0`,
- no +0.01R runner stop,
- no post-TP1 M5 runner chase,
- parent/setup becomes complete after TP1,
- system returns to searching for the next valid parent setup.

Required profile/config name:

`TP1_ONLY_RESEARCH`

Do not delete runner code. Gate it behind management profile selection.

---

# Gate-11 fixes that must be consolidated before mass testing

## Fix A — +0.01R semantics in the normal runner profile
The permanent runner profile eventually needs a real touch-stop contract after TP1, not generic body-close invalidation. For the TP1-only experiment this path must be disabled, but preserve the repair behind the normal profile.

Important causality rule: when only M5 OHLC is available, do not invent same-bar ordering between TP1 touch and newly activated +0.01R stop. Use synchronized M1 if available; otherwise apply an explicit conservative/next-candle rule.

## Fix B — Earned-early M1 ARMED parent
`parent.active_time` may legitimately be `None`. Never `float(None)`. Treat this as pre-ACTIVE/earned-early evaluation only.

## Fix C — M1 -> M5 runner handoff
In the normal runner profile, an M1 entry retains M1 entry ownership, but after TP1, M5 owns HL/LH runner structural exit monitoring. For `TP1_ONLY_RESEARCH`, no runner survives TP1, so this handoff should not affect results.

## Fix D — Fidelity auditor
Auditor must understand the management profile. Under `TP1_ONLY_RESEARCH`, the correct TP1 event is a 100% terminal exit and the absence of runner events is expected, not a contract loss.

## Fix E — Population harness
Never reconstruct a second TradeManager from a reduced entry snapshot. Continue the canonical TradeManager/runtime state opened by the pipeline. A prior research harness incorrectly dropped trigger/stop lineage and produced false errors such as:

`Qualified entry must publish its logical structure and trigger`

That was a harness bug, not SmartStructureBot strategy logic.

---

# Mass-test data

## Primary target symbols
1. `GOLD#`
2. `US100Cash#`
3. `GER40Cash#`
4. `US30Cash#`
5. `OILCash#`

## Stress-test symbols if available
- `AUDUSD#`
- `EURUSD#`
- `GBPUSD#`
- `USDJPY#`

## Timeframes
- M1 and M5 raw closed candles are mandatory.
- Derive H1/M30/M15 context causally from authoritative history or export those timeframes too if the project already uses broker-native HTF bars.

## History size
Minimum useful study: 6 months.
Preferred certification study: 12–24 months.
If possible, include multiple volatility/regime periods.

Do NOT use the forming candle.
Do NOT deduplicate by silently rewriting timestamps.
Do NOT modify source CSVs.

---

# Performance / replay engineering task

Build an incremental causal replay system rather than recomputing full history from scratch at each candle.

Recommended ledgers:

- CausalSwingLedger
- HTFStateLedger
- ParentSetupLedger
- Entry/AttemptLedger
- TradeManagementStateLedger

For each newly closed candle, process only information that became available at that timestamp.

Required invariant:

For any decision index `i`, result from full data with `as_of_index=i` must equal result from physical prefix `data.iloc[:i+1]`.

No future-confirmed swing may leak backward.

A fast structural pre-screen may remove candles that mathematically cannot be an entry, but the **canonical pipeline must retain sole authority to approve/reject trades**.

---

# Every trade must produce an audit row

Required fields at minimum:

- symbol
- timestamp
- parent_setup_id
- retracement_id
- direction
- HTF votes / approved direction
- first-break/second-break trend state
- parent retracement origin index/time
- trigger type and trigger index
- BOS index/time
- entry timeframe (M1/M5)
- entry price
- TP1 freshness result
- pre-BOS stop owner index/time/price
- stop basis
- TP1 origin candle index/time
- TP1 body price
- attempt_number
- reentry_count
- exit reason
- exit price
- R result
- integrity status
- first divergence reason if not MATCHES_STRATEGY

For rejected candidates, preserve rejection reason rather than silently dropping them.

---

# Required TP1-only metrics

Overall and by symbol/session/timeframe/direction:

- parent setup count
- entry count
- Attempt-1 count
- Attempt-2 count
- stale TP1 blocks
- TP1 wins
- initial-stop losses
- open-at-boundary trades (excluded from closed expectancy)
- win rate
- expectancy R
- total R
- profit factor
- average winner R
- average loser R
- maximum R drawdown
- maximum consecutive losses
- MFE and MAE where available
- M1 vs M5 expectancy
- first attempt vs re-entry expectancy
- bullish vs bearish
- London / overlap / New York / other session buckets

For TP1-only research, a TP1 winner's R is simply distance(entry, TP1) / initial_risk with sign/direction handled correctly. A stop loss uses actual initial-stop semantics. Do not force-close open boundary trades.

---

# A/B management experiment

After TP1_ONLY_RESEARCH is certified, run the SAME frozen entry population through two management profiles without changing entries:

A. `TP1_ONLY_RESEARCH`
B. normal runner profile

The entry population must be frozen/shared. If entries differ between A and B, that is a bug.

Compare:

- expectancy
- PF
- drawdown
- TP1 hit population
- runner contribution
- winner-to-loser giveback

This is how we decide whether runner logic helps or harms an already-valid core strategy.

---

# Acceptance gates before AI

Kiro must not declare success unless all are true:

1. Core/unit regression green (except separately documented environment fixture issue).
2. Prefix/suffix invariance green.
3. No unfinished candle access.
4. Zero live/demo order API calls.
5. Historical data SHA256 unchanged before/after.
6. Every canonical entry has stop + TP1 lineage.
7. Ledger preserves Attempt 1 and legal Attempt 2 separately.
8. No Attempt 3.
9. `TP1_ONLY_RESEARCH` creates no runner events after TP1.
10. Exact same entry population can be reused for A/B management comparison.
11. Clean Windows checkout can reproduce the results.
12. Full results exported as CSV + JSON + Markdown summary.

---

# Decision framework

## Outcome A — Fidelity high + TP1-only expectancy positive
Interpretation: core strategy shows an edge; runner subsystem becomes the main engineering/research problem. Freeze TP1-only baseline for AI-readiness research, but do not confuse it with permanent live strategy.

## Outcome B — Fidelity high + TP1-only expectancy flat/negative
Interpretation: code is largely executing correctly; core strategy/selectivity requires research. Do not add AI to hide a negative baseline.

## Outcome C — Fidelity failures remain
Interpretation: code/handoff/causality is still the problem. Repair first and rerun from zero before judging strategy.

---

# Kiro must not

- tune Fib ratios to improve results,
- change the two-break trend law,
- add indicators/AI filters,
- change BOS from body-close semantics,
- change the pre-BOS wick stop,
- move TP1 to wick,
- permit more than one re-entry,
- use future-confirmed structure,
- drop failed/rejected examples from evidence,
- optimize symbols/sessions before first reporting the frozen baseline.

---

# Deliverables back to Steve / ChatGPT

1. Git commit hash of the exact tested build.
2. `git diff` from base.
3. Full test output.
4. Data file manifest + SHA256 before/after.
5. Entry-level audit CSV.
6. Closed-trade CSV.
7. Rejection-reason CSV.
8. Overall summary JSON + Markdown.
9. Per-symbol/session/timeframe metrics.
10. A list of every fidelity/contract failure and exact fix.
11. Reproduction command(s) for Windows PowerShell.
12. No AI work until ChatGPT/Steve review these artifacts.
