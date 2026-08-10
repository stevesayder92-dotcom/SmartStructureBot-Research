# S2B.1 implementation report

## Scope and safety

S2B.1 adds one shared `SecondTouchStructureEngine` used by M1, M5 and the
prefix-causal re-entry evaluator. The feature is disabled by default. The
canonical M1 policy remains `COUNTER_CONFIRMED_ACTIVE`; no live/demo execution
or order API was added. TP1 and trade management were not changed.

## Recognition and migration

- Double tops use confirmed swing-high wick extremes; double bottoms use
  confirmed swing-low wick extremes.
- Touch proximity is frozen at `0.25 * causal ATR`.
- A separating reaction must move at least `0.35 * causal ATR`, and touches
  must be at least three candles apart.
- Exact parent/retracement/impulse/protection/Fib ownership is mandatory.
- When touch 2 becomes causal before entry, trigger 1 is superseded. The system
  waits for the meaningful post-touch-2 reaction and a correctly directed body
  close beyond that new trigger.
- A historical entry that occurred before touch 2 remains immutable.

Second-touch M1 entries use touch 2's wick as their logical stop owner. M5 uses
the same wick owner plus the already-established 0.15 ATR body-close tolerance.
Attempt 2 requires a fresh post-failure touch/trigger/BOS/stop identity, while
the one-re-entry limit remains intact.

## Fixed replay

The accepted S2B control table (192 setups, SHA-256
`48ba21f8dd4f2052b8204ff3e130313fc799378dab05b1f3ffe9395a07f23b6e`)
was paired against the new B/C pass. The result contains 157 common same-parent
setups and 40 explicitly published terminal-set differences. The seven
available symbols were AUDUSD#, EURUSD#, GBPUSD#, GER40Cash#, GOLD#,
US100Cash# and USDJPY#. US30Cash# and OILCash# are `DATA_NOT_AVAILABLE`.

## Outcome

| Variant | Win rate | Expectancy | Profit factor | Median final R |
|---|---:|---:|---:|---:|
| Canonical control | 35.03% | -0.0083R | 0.9928 | -0.8000R |
| Second-touch canonical | 34.39% | -0.2770R | 0.7344 | -1.0263R |
| Second-touch + earned early | 38.22% | -0.1382R | 0.8671 | -0.6237R |

There were 58 unique confirmed second-touch parents and 58 old-trigger
supersessions. ACTIVE-only first-entry facts changed in 97 paired setups; the
earned-early variant differed from control in 113. Five of the 13 prior
baseline-winner-to-S2B-loser cases improved in R, which is not enough to offset
the population deterioration.

Verdict: `S2B_REMAINS_RESEARCH_REJECTED`. These figures are research replay
statistics, not a profitability claim.

