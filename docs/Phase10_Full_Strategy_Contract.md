# SmartStructureBot Phase 10 Full Strategy Contract

## Identity

The system researches dominant-trend continuation after a meaningful
counter-trend retracement fails. It does not trade a raw breakout, a wick,
or an isolated fractal.

## Canonical sequence

1. Determine causal H1/M30/M15 context from closed candles.
2. Confirm the dominant direction and same-direction body-close BOS.
3. Bind a stable impulse cycle and dominant protected structure.
4. Ignore or downgrade micro counter-moves.
5. Start one parent retracement after meaningful counter structure appears.
6. Preserve the parent setup identity while that retracement evolves.
7. Measure the retracement against causal 0/100 impulse anchors.
8. Classify depth as `SHALLOW`, `EARLY_RELEVANT`,
   `PRIMARY_SWEET_SPOT`, `DEEP_BUT_VALID`, or `EXTREME`.
9. Require a causally confirmed counter structure and relevant failure
   trigger.
10. Enter only when the current candle body points with the dominant trend
    and closes beyond that trigger.
11. Place the logical stop at the relevant pre-BOS body boundary: exact body
    edge on M1 and body edge plus causal ATR tolerance on M5.
12. Keep the emergency broker stop wider and logically separate.
13. Treat every new post-entry fractal as unproven until a later meaningful,
    displaced, correct-direction body-close BOS proves it.
14. Never loosen trailing protection.
15. Exit only on meaningful logical body-close invalidation or opposing
    meaningful BOS; a wick alone survives.
16. After a first early failure, preserve the parent retracement when
    dominant protection is intact and observe fresh structure.
17. Allow one re-entry from a fresh relevant counter structure and the next
    same-direction body-close BOS. Keep the parent setup ID and use a
    different event ID.
18. A dominant-protection failure or second logical failure closes the
    parent.

## Hard invalidity

- missing or conflicting directional context under the selected HTF policy;
- future or unconfirmed structure;
- wrong-direction BOS candle body;
- stale or already-consumed trigger;
- broken impulse 100% origin;
- unavailable or wrong-side logical stop;
- dominant protection failed before re-entry;
- more than one re-entry;
- second failure for the same parent setup;
- live/unattended execution request.

## Soft quality

Fibonacci location, mild HTF weakness, modest displacement, session quality,
and visual cleanliness affect `A_PLUS`, `A`, `B`, or `C` grade and risk.
They do not silently erase otherwise valid structure. `INVALID` is reserved
for an explicit hard blocker.

## HTF policy

Supported research policies include strict 2-of-3, preferred M30/M15,
one exceptionally clean HTF when the other frames are neutral, and
conflict-risk comparison. Local counter-trend structure cannot overwrite
the approved HTF direction by itself.

## M5 and M1

M5 remains primary. M1 is only a fallback inside a valid M5 parent context
when the M5 trigger is absent or late. M1 management may transition to M5
protection only when the new M5 boundary is tighter.

## Safety

All decisions use closed candles and explicit structure-availability
indexes. No order API is imported or called. Runtime modes remain
`RESEARCH`, `REPORT`, and `PAPER_SIGNAL`; `LIVE` is rejected.
