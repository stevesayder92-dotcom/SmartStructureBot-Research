# SmartStructureBot — MASTER STRATEGY CONTRACT
## Temporary TP1-Only Research Baseline

**Authority:** This document is the strategy source of truth for the current mass-test branch.

If code, tests, comments, historical S2B documents, AI suggestions, Kiro, Codex, or any other module conflict with this document, **this document wins** unless Steve explicitly changes the strategy.

The purpose of the current branch is to test the simple strategy without runners. The normal runner code must remain preserved but disabled by the `TP1_ONLY_RESEARCH` profile.

---

# 1. Strategy in one sentence

Confirm a real trend, wait for a counter-trend retracement, enter exactly when that retracement's own structure fails by body-close BOS in the dominant direction, place the stop at the immediate pre-BOS wick, and in the current research profile close the entire trade at the body-based retracement-origin TP1.

---

# 2. Trend state machine — foundation of everything

Trend is evaluated causally using only closed candles.

## Bullish confirmation from NEUTRAL

1. Market starts `NEUTRAL`.
2. First **distinct bullish body-close break** of a legitimate structural high is **CHOCH WARNING only**.
3. This first break does **not** yet confirm the bullish trend.
4. The market must form/recognize a later distinct legitimate structural high.
5. A second distinct bullish **body-close** break confirms `BULLISH` trend.
6. Multiple closes through the same already-broken high do not count as additional breaks.
7. Wick-only penetration is not a structural break.

State flow:

`NEUTRAL -> first HH body-close break -> BULLISH_CHOCH_WARNING -> second distinct HH body-close break -> BULLISH_CONFIRMED`

## Bearish confirmation from NEUTRAL

Mirror the bullish rule:

`NEUTRAL -> first LL body-close break -> BEARISH_CHOCH_WARNING -> second distinct LL body-close break -> BEARISH_CONFIRMED`

## Trend reversal principle

A local retracement does not automatically reverse the dominant confirmed trend. Opposing structural evidence must satisfy the same causal reversal logic rather than a single noisy micro break.

---

# 3. Parent timeframe and child timeframe

- **M5 is the parent setup timeframe.**
- **M1 is a synchronized child/execution timeframe under the exact same M5 parent setup.**
- M1 may provide an earlier valid entry, but it is not allowed to invent a different parent, different TP1, or different strategy.
- H1/M30/M15 provide higher-timeframe context according to the configured causal HTF policy.

---

# 4. What happens immediately after trend confirmation

As soon as a trend is confirmed, the bot begins looking for a retracement.

For a bullish dominant trend, the retracement is bearish/counter-trend and develops its own small structure.

For a bearish dominant trend, the retracement is bullish/counter-trend and develops its own small structure.

The retracement is not itself a reversal of the dominant trend.

---

# 5. The permanent entry law

This is the heart of the strategy and must never be redefined by AI, scoring, Fibonacci, second-touch, or any other supporting engine.

## Bullish entry

1. Dominant trend is bullish.
2. A bearish retracement develops.
3. The retracement forms a legitimate **lower-high (LH)** structure.
4. A bullish candle **BODY CLOSES above the active retracement LH**.
5. That candle is the failed-retracement BOS.
6. **ENTER at that exact BOS candle close.**

## Bearish entry

1. Dominant trend is bearish.
2. A bullish retracement develops.
3. The retracement forms a legitimate **higher-low (HL)** structure.
4. A bearish candle **BODY CLOSES below the active retracement HL**.
5. That candle is the failed-retracement BOS.
6. **ENTER at that exact BOS candle close.**

## Explicitly forbidden extra entry requirements

Do not require any of the following after a structurally valid BOS:

- another confirmation candle,
- retest,
- AI approval,
- random score threshold,
- mandatory second-touch,
- Fibonacci sweet-spot approval,
- arbitrary delay.

Supporting engines may grade or explain a setup, but they may not redefine the core entry.

---

# 6. Entry freshness law

A structurally valid BOS is still too late if the intended parent TP1 has already been crossed before the entry occurs.

Therefore at the BOS candle:

- BUY: TP1 must still be above the entry.
- SELL: TP1 must still be below the entry.

If TP1 has already been crossed, block the entry with:

`TP1_BODY_TARGET_ALREADY_PASSED_NO_ENTRY`

This is a stale/late setup, not a valid trade.

---

# 7. Initial stop-loss law

The stop belongs to the **immediate relevant pre-BOS reaction swing**, not an arbitrary old protected structure and not a candle body edge.

## BUY

- Identify the relevant low formed immediately before the bullish BOS move.
- Stop ownership basis = the **wick extreme** of that low.
- Canonical owner basis string: `PRE_BOS_SWING_WICK_EXTREME`.

## SELL

- Identify the relevant high formed immediately before the bearish BOS move.
- Stop ownership basis = the **wick extreme** of that high.
- Canonical owner basis string: `PRE_BOS_SWING_WICK_EXTREME`.

The candle color does not decide stop ownership. Price structure does.

Do not substitute an older broad retracement extreme simply because it is farther away.

---

# 8. TP1 law — exact candle and exact price

TP1 belongs to the swing candle that existed **immediately before the parent retracement began**.

TP1 is a BODY price, not the wick.

## BUY

The parent retracement begins from a swing-high candle.

`TP1 = max(open, close)` of that swing-high candle.

This is the **upper body edge** of the pre-retracement swing-high candle.

## SELL

The parent retracement begins from a swing-low candle.

`TP1 = min(open, close)` of that swing-low candle.

This is the **lower body edge** of the pre-retracement swing-low candle.

Do not use the swing wick as TP1.

M1 entries inherit this exact M5 parent TP1; they do not rebuild TP1 from an M1 swing.

---

# 9. TEMPORARY MASS-TEST MANAGEMENT PROFILE

## Profile name

`TP1_ONLY_RESEARCH`

This is the management profile that must be used for the current mass test.

It intentionally removes runner behavior so we can answer whether the core strategy is profitable before runner management.

For every valid trade:

1. Use the same entry rules.
2. Use the same initial pre-BOS wick stop.
3. Use the same body-based parent TP1.
4. If TP1 is reached, **close 100% of the trade at the exact TP1 price**.
5. `tp1_partial_fraction = 1.0`.
6. `runner_fraction = 0.0`.
7. Do not create or arm a +0.01R runner stop.
8. Do not trail M5 HL/LH after TP1.
9. Do not create any post-TP1 runner-management event.
10. Mark that attempt/setup as completed after TP1 according to lifecycle rules.
11. Return to searching for the next valid setup.

The original runner code must NOT be deleted. It must be isolated behind another management profile for later research.

---

# 10. Re-entry law during TP1-only research

The existing one-reentry rule remains unless the mass-test branch explicitly reports Attempt-1-only statistics separately.

- Maximum one same-parent re-entry.
- Attempt 1 fails.
- If the original parent trend/protection/setup remains valid, wait for a **fresh legitimate same-direction BOS**.
- That fresh BOS may become Attempt 2.
- Attempt 2 entry price = its own BOS candle close.
- Attempt 2 stop = its own fresh immediate pre-BOS wick.
- Attempt 2 inherits the SAME parent retracement-origin body TP1.
- No Attempt 3.

Research must report both:

1. **Attempt-1-only performance**, and
2. **full sequence including legal Attempt 2**.

This isolates whether re-entry helps or hurts the core edge.

---

# 11. M1 law

M1 is allowed to enter earlier only under the exact same M5 parent.

- M1 must see a legitimate child counter-trend structure.
- Valid M1 entry is still a body-close BOS through the active child LH/HL.
- M1 entry = BOS candle close.
- M1 stop = immediate relevant pre-BOS M1 wick.
- M1 TP1 = exact parent M5 body TP1.
- M1 quality/scoring is advisory; it cannot veto an otherwise structurally valid entry.
- Second-touch is advisory/supporting evidence; it cannot delay or replace a normal legitimate LH/HL BOS.
- `PARENT_ARMED` with `active_time=None` is a valid pre-ACTIVE state and must never crash.
- M1 and M5 may compete for the same parent Attempt 1, but exactly one first attempt may win.

---

# 12. Fibonacci / scoring / second-touch role

These are supporting intelligence only.

They may:

- describe retracement depth,
- provide evidence,
- grade quality,
- support future research.

They may NOT:

- redefine trend,
- redefine the active LH/HL entry trigger,
- move entry away from BOS close,
- move the initial stop away from the pre-BOS wick,
- move TP1 away from the parent-body level,
- create more than one re-entry,
- rescue structurally invalid setups,
- reject structurally valid setups solely for a soft score.

---

# 13. Causality laws

Every result must be reproducible from information available at the decision candle.

- Closed candles only.
- Forming candle excluded.
- No future-confirmed swing may leak backward.
- `as_of_index=i` from full data must equal the physical prefix ending at `i`.
- HTF bars used at a decision must already be closed at that timestamp.
- A later suffix must not rewrite an earlier fixed decision.
- Stop owner must exist before/on entry, not after it.
- TP1 owner must exist before the retracement and entry.
- Historical setup/attempt identity is immutable.

No causality assertion may be weakened merely to make the mass test faster.

---

# 14. Canonical authority / ownership

`SystemStateDirector` remains the canonical strategy state owner.

Engines calculate their domain and publish contracts. Downstream code may consume those contracts but may not secretly recompute or redefine upstream truth.

The mass-test harness must continue canonical pipeline state. It must **not reconstruct a second TradeManager from an abbreviated snapshot**, because that previously dropped trigger/stop lineage and produced false errors.

Management profile must not influence entry discovery. The same frozen entry population must be reusable later for TP1-only vs runner A/B comparison.

---

# 15. What the current mass test is trying to prove

We are separating three possibilities:

## Outcome A — Code fidelity high + TP1-only profitable

Core strategy shows an edge. The runner subsystem is the main remaining engineering/research problem.

## Outcome B — Code fidelity high + TP1-only flat/negative

The machine is largely executing the strategy correctly; the raw strategy/selectivity becomes the research target.

## Outcome C — Fidelity failures remain

The code is still the problem. Repair every divergence and rerun the entire study from zero before judging profitability.

---

# 16. Required mass-test outputs

The mass test must report at minimum:

- total parent setups,
- accepted entries,
- rejected candidates and exact reason,
- Attempt-1 count,
- Attempt-2 count,
- M1 entries,
- M5 entries,
- bullish/sell breakdown,
- TP1 wins,
- stop losses,
- stale-TP1 blocks,
- open-at-dataset-boundary trades,
- win rate,
- expectancy in R,
- total R,
- profit factor,
- average winner R,
- average loser R,
- max drawdown in R,
- max consecutive losses,
- MFE/MAE if available,
- per-symbol statistics,
- per-session statistics,
- M1 vs M5 statistics,
- Attempt 1 vs Attempt 2 statistics,
- zero-future-data assertion results,
- source-data SHA256 before/after,
- every fidelity/contract failure.

Open trades at the end of the dataset must not be force-closed just to create a result.

---

# 17. Absolute prohibitions for Kiro / Codex during this phase

Do NOT:

- add AI/ML,
- add indicators to improve results,
- optimize thresholds before frozen baseline reporting,
- change Fib ratios to improve P&L,
- change the two-break trend law,
- change BOS from body-close semantics,
- add a retest requirement,
- change pre-BOS wick stop ownership,
- move TP1 to wick,
- re-enable runners in the TP1-only baseline,
- arm +0.01R in TP1-only mode,
- permit Attempt 3,
- hide losing/rejected setups,
- use old S2B profit labels as current results,
- use future-confirmed swings,
- let management change the entry population,
- silently mutate source data.

The objective is **truth**, not a pretty backtest.

---

# 18. Human-readable bullish example

`NEUTRAL`
→ first HH body-close break = CHOCH warning
→ second distinct HH body-close break = bullish confirmed
→ bearish M5 retracement forms
→ relevant retracement LH forms
→ bullish BODY CLOSE breaks LH
→ **BUY at BOS close**
→ SL owned by immediate pre-BOS LOW wick
→ confirm parent-body TP1 remains above entry
→ **TP1 = upper body edge of swing-high candle that started retracement**
→ in `TP1_ONLY_RESEARCH`, close **100% at TP1**
→ setup completes / look for next setup

# 19. Human-readable bearish example

`NEUTRAL`
→ first LL body-close break = CHOCH warning
→ second distinct LL body-close break = bearish confirmed
→ bullish M5 retracement forms
→ relevant retracement HL forms
→ bearish BODY CLOSE breaks HL
→ **SELL at BOS close**
→ SL owned by immediate pre-BOS HIGH wick
→ confirm parent-body TP1 remains below entry
→ **TP1 = lower body edge of swing-low candle that started retracement**
→ in `TP1_ONLY_RESEARCH`, close **100% at TP1**
→ setup completes / look for next setup

---

# Final authority statement

For the current mass-test phase, this document is the plain-language strategy contract Kiro and Codex must code and audit against.

**Do not infer a different strategy from historical code. Do not optimize it. Implement and test this exact contract first.**
