# Final Sequence Recovery and Elite Management v1

This research-only patch preserves the frozen 60-entry population. It does not
place orders and it does not alter entry selection.

## Re-entry ownership

After the first logical failure, M1 and M5 are evaluated from their own closed
candles. A candidate needs a fresh, unconsumed body-close BOS, a causally
confirmed counter-structure formed inside the recovery window, correct candle
direction, at least `0.35 ATR` body displacement, an intact parent, and a fresh
timeframe-owned stop. The first valid close owns Attempt 2 and closes the other
gate. M1 trigger freshness is two M5 periods (10 M1 candles); M5 freshness is
12 M5 candles. Close depth of `0.30 ATR` is recorded as a soft grade only.

One parent setup may have at most two attempts. Attempt 2 failure permanently
closes that parent sequence. Attempt metrics and sequence metrics are separate.

## Initial stop interpretation

The stop structure is the last important causal pre-entry HL for a buy or LH
for a sell. The structure body edge is the charted strategy stop. On M5 only,
`0.15 ATR` tolerance is kept as a separate body-close invalidation boundary.
No future swing confirmation is used.

## Opportunity protection

Protection needs two independent keys: earned opportunity and deterioration
risk. P/L alone cannot trigger a mature-profit action. Opportunity states use
peak R, structural proof, and target lifecycle. Risk uses failed extensions,
target rejection, opposing displacement, giveback, retained peak, and two-event
hysteresis. A mature floor must be a proven, tightening structure on the correct
side of price; it is never an arbitrary R level.

## Partial profiles

- `STRUCTURE_RUNNER_ONLY`: no partial.
- `PARTIAL_PLUS_RUNNER`: 50% partial when TP1 is available.
- `DYNAMIC_PARTIAL_PLUS_RUNNER`: 25% after acceptance/extension, 50% on a wick
  touch/body close, and 65% on rejection or mature high-risk deterioration.

The numeric source of truth is
`config/sequence_elite_v1.json`. Threshold changes require Bible, code, replay,
and test updates in that order.
