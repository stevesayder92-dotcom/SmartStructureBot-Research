# S2B.1 second-touch structural trigger contract

Status: research only. This contract does not promote S2B, alter the default
M1 permission policy, or authorize live/demo execution.

## Frozen variants

| Variant | M1 permission | Trigger recognizer |
|---|---|---|
| `CANONICAL_CONTROL` | `COUNTER_CONFIRMED_ACTIVE` | accepted S2A.1 trigger |
| `SECOND_TOUCH_CANONICAL` | `COUNTER_CONFIRMED_ACTIVE` | causal second-touch migration |
| `SECOND_TOUCH_EARNED_EARLY` | earned-early research policy | causal second-touch migration |

The baseline recognizer remains the runtime default. Second-touch recognition
is enabled only by the explicit research configuration flag.

## Recognition contract

For a bearish parent, touch 1 and touch 2 are confirmed swing-high wick
extremes. For a bullish parent they are confirmed swing-low wick extremes.
They must:

1. belong to exactly the same parent, retracement, impulse cycle, dominant
   protection owner and Fibonacci anchor version;
2. be at least three candles apart;
3. be within `0.25 * causal ATR` of one another; and
4. contain a confirmed opposing reaction displaced at least
   `0.35 * causal ATR` from the touch structure.

After touch 2 is causally visible, the old trigger is superseded. The system
waits for the meaningful opposing reaction after touch 2. Only a correctly
directed candle body close beyond that new trigger can enter. Wick-only breaks
remain diagnostic rejections.

## Stop ownership

Normal setups keep the accepted stop contract. An accepted second-touch entry
uses the second touch's wick extreme as logical structural owner. M1 applies
its existing body-close invalidation semantics; M5 retains its existing causal
ATR-tolerant body-close invalidation. Emergency protection stays separate and
wider.

## Causality and attempt lifecycle

- Right-side swing confirmation delay is mandatory.
- A second touch formed after an entry cannot rewrite Attempt 1.
- A second touch formed before entry may supersede only within the same owner.
- Attempt 2 requires a fresh second touch, trigger, BOS and stop owner after
  Attempt-1 failure.
- One parent still permits one first entry and at most one re-entry.
- Prefix-only, actual-suffix, modified-suffix and reversal-suffix decisions
  must agree at the frozen decision boundary.

## Deferred management clarification

TP1 partial realization and post-TP1 runner protection are documented in the
Strategy Bible as pending S2B.2. S2B.1 does not modify TP1, management or
outcome simulation.

