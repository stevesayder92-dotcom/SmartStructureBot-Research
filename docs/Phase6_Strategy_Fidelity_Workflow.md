# Phase 6 — Strategy Fidelity Calibration

## Objective

Phase 6 measures whether the bot makes the same structural decision Steve
would make on the same closed candles. It does not optimize profitability,
simulate trades, or enable order execution.

## Why this phase exists

Phase 5B proved causality and ownership, but it did not prove strategy
fidelity. The accepted expanded replay produced only two canonical entries,
both classified as stale, with no causal HTF data supplied to those decisions.

The first Phase 6 audit also separates two trigger timestamps that Phase 5B
visually collapsed:

- `fractal_confirmed_at_index`: the swing is visible after the causal
  two-candle fractal window;
- `structural_confirmed_at_index`: the swing becomes locked under the current
  full-structure policy;
- `tradeable_at_index`: the current engine allows it to act as the failure
  trigger.

If structural confirmation occurs on the entry candle, the chart now says so
explicitly. That is evidence of a likely human-versus-code disagreement, not
permission to weaken the rule automatically.

## Workflow

1. Open `phase6_evidence/phase6_fidelity_review.html`.
2. Compare the full lifecycle panel with the entry zoom.
3. Fill `phase6_evidence/phase6_manual_labels.json`.
4. Set `review_status` to `COMPLETE` only after entering Steve's actual
   direction, origin BOS, pullback origin, failure trigger, entry/no-entry,
   and reason.
5. Run:

   ```powershell
   python tools/analyze_phase6_fidelity.py
   ```

6. Repair the largest disagreement category first and add those completed
   examples as regression fixtures.

## Acceptance gate before demo testing

At least 30 completed, broker-candle-mapped examples are required before the
workflow will infer any readiness result. The set must include buys, sells,
no-trades, compression, liquidity sweeps, equal highs/lows, double/triple
tops or bottoms, sweet-zone context, and HTF agreement/disagreement.

No incomplete example is treated as a rejection. No threshold is adjusted
automatically.

## Current blocker

Steve's two manual screenshots are included as authoritative visual
references, but their exact candles are not present in the current June/July
research datasets. They must be mapped to exact XM symbols, broker timestamps,
and OHLC histories before they can become executable regression tests.
