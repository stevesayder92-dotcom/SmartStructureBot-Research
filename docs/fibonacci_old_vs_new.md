# Fibonacci Contract: Superseded Model vs Steve V2

| Item | Superseded interpretation | Authoritative Steve V2 |
|---|---|---|
| Model | Phase 10 depth-facing labels | `STEVE_REMAINING_IMPULSE_PERCENT_V2` |
| 0% | Impulse extreme | Impulse origin and full-structure retest |
| 100% | Impulse origin | Impulse extreme where retracement begins |
| Price path | Labels implied movement from origin toward extreme | Retracement moves from 100% toward 0% |
| Internal measure | Retracement depth | Both raw remaining impulse and complementary depth |
| Primary zone | Previously treated as a mid-depth region | 23.6%-38.2% remaining, equal to 61.8%-76.4% depth |
| Structural breach | Could be hidden by display clamping | Raw remaining below zero publishes `BELOW_0`; only display is clamped |
| Entry authority | Fib could be mistaken for a signal | Fib grades relevance only; structure and body-close BOS own entry |

## Authoritative formulas

Bullish:

```text
remaining =
    (current_retracement_price - impulse_origin_price)
    / (impulse_extreme_price - impulse_origin_price)
```

Bearish:

```text
remaining =
    (impulse_origin_price - current_retracement_price)
    / (impulse_origin_price - impulse_extreme_price)
```

For both:

```text
retracement_depth = 1.0 - remaining
```

The implementation publishes raw and display-safe values, anchor indexes,
anchor roles, the seven requested levels, lowest remaining percentage and
deepest retracement percentage.
