# EXPERT_SPEC_V1 implementation contract

## Causal swing clock

For `ENGINE_SENSITIVITY = 3`, candidate candle `i` must be strictly
higher than the preceding and following three highs for a swing high,
or strictly lower than the preceding and following three lows for a
swing low.

The point occurs at `i` but is first decision-available at `i + 3`.
It is never published before that candle closes and is immutable after
publication.

## Higher-timeframe direction

H1, M30 and M15 are evaluated independently using only complete bars.
A candle close above the last confirmed swing high makes that frame
bullish. A candle close below the last confirmed swing low makes it
bearish. Wicks do not change direction.

The context approves a direction only with two matching votes. One
strong frame cannot override two disagreeing or neutral frames.

## M5 pullback and entry

For a bearish setup, the state machine requires:

1. a confirmed lowest swing low as pullback origin;
2. a later confirmed swing high showing the counter move;
3. a later confirmed higher swing low as the failure trigger;
4. a candle close below the active failure trigger.

The bullish sequence is the exact mirror. Later eligible trigger swings
may update the active trigger while preserving the original setup and
initial trigger evidence. A wick-only cross preserves the setup and does
not enter.

Entry price is the decision candle close. The research stop is the
highest bearish-retracement wick or lowest bullish-retracement wick.
The setup is consumed after its first canonical entry.

## Management contract

After a short entry, each newly confirmed M5 swing high may lower the
research trailing stop. A candle close above the last confirmed M5 swing
high publishes an exit signal. Long management mirrors this with swing
lows and closes below.

Management outputs never call an order API.
