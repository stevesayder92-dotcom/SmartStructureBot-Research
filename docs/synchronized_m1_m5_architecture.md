# Synchronized M5-Parent / M1-Child Architecture

## Ownership

`SystemStateDirector` and the M5 pipeline own the parent setup. M1 cannot
invent another setup. Each child event must exactly match:

```text
parent_m5_setup_id
parent_m5_retracement_id
parent_impulse_cycle_id
parent_direction
parent_protected_structure_id
parent_fib_anchor_version
```

A mismatch is a hard rejection.

## Closed-candle event order

At one merged close timestamp:

```text
1. Publish newly closed M5 parent candle, if present.
2. Rebuild only the parent state legally visible at that time.
3. Publish newly closed M1 child candle(s).
4. Evaluate M1 only when the current parent gate is ARMED or ACTIVE.
5. If M1 closes a valid BOS first, consume the first-entry opportunity.
6. If no valid M1 entry exists and M5 closes its BOS, take M5 fallback.
```

An M1 decision cannot see an unfinished M5 candle. An M5 decision cannot
inspect future M1 candles.

## Child entry sequence

The child detector requires a genuine countertrend sequence, an owned
failure trigger, a fresh body-close BOS, correct parent time/price location,
intact dominant protection, a logical body-edge stop on the correct side, and
a separate wider emergency stop. BOS body size, overlap, session, Fib
location and similar quality observations grade risk; they do not create
structure.

## First-valid arbitration

One arbiter owns both routes:

```text
valid M1 before M5 -> CONSUMED_BY_M1 -> later M5 duplicate blocked
no valid M1 + valid M5 -> CONSUMED_BY_M5 -> M1 gate closed
```

The audit retains the hypothetical M5 alternative for every M1 entry so
minutes saved, price improvement, stop reduction and RR change can be
measured.

## Management

M1 starts with `M1_RELEVANT_SWING_BODY_EDGE` protection. M5 fallback uses its
body edge plus configured ATR tolerance. Both keep a separate emergency stop.
M5 continuation may take over an M1 runner only when the proposed level
tightens or equals current protection.

Targets progress through distinct touch, close-through, acceptance,
rejection, reclaim and extension events. TP1 wick touch may fill a partial,
but does not force break-even. A rejection after accepted TP1 produces a
closed-candle runner exit. Trails require a later same-direction BOS to prove
the candidate and can never loosen protection.

## Re-entry

The parent owns a maximum of one re-entry. After first failure, the same
retracement and Fib anchors remain active only while dominant protection and
the parent cycle remain valid. A re-entry candidate closing at or after
dominant-protection failure is cancelled by the merged coordinator.

## Safety

All final-fidelity modules publish `research_only`, causal and closed-candle
properties. The release verifier scans runtime files for MT5 order patterns;
none are present.
