# Phase 10.1 Swing-Stop and TP1 Feedback Repair

## Accepted user corrections

The Phase 10 chart review exposed two strategy-fidelity mismatches.

1. The initial logical stop was still owned by the earlier counter-swing in
   several setups. The correct owner is the last important pre-entry LOW/LL
   for a bullish BOS or HIGH/HH for a bearish BOS.
2. TP1 should use the previous impulse extreme by default and a wick touch is
   sufficient to classify the target as reached.

## Causal stop selection

The engine first inspects the reaction between the active failure trigger and
the entry BOS. When that interval contains an opposing candle, the most
protective reaction extreme becomes the logical-stop owner. The entry BOS
close proves this reaction structure at the entry index. No post-entry or
future right-side candle is used.

If no opposing reaction exists, the engine falls back to the latest
fixed-delay confirmed protective swing inside the same qualified
retracement.

The price contract itself remains unchanged:

- M1 uses the relevant candle body edge;
- M5 uses the relevant body edge plus configured ATR tolerance;
- wick-only movement does not logically invalidate;
- the emergency broker stop remains separate and wider.

## TP1

The default TP1 model is `PREVIOUS_IMPULSE_EXTREME`. A bullish trade targets
the previous impulse high and a bearish trade targets the previous impulse
low, provided the level is favorable relative to entry. The research manager
uses candle high/low to recognize a TP1 touch; it does not require a close.

## Safety

This release remains research-only. It does not import, invoke, or enable an
order API.
