# Final Fidelity Patch v1 code change report

## Preserved architecture

The patch retains the canonical Director, SignalLedger, synchronized M1/M5
coordinator, parent setup lifecycle, hard entry validator, Steve Fibonacci V2,
initial logical stop ownership, emergency stop, target lifecycle, replay
causality, and disabled order execution. The verified pre-patch release remains
unchanged in its original deliverable directory.

## Added behaviour

- `core/fidelity_patch.py` adds configurable evidence-only M1 quality,
  continuation, giveback, and exhaustion engines plus the single
  `TradeManagementCoordinator` commit owner.
- `core/synchronized_m1_replay.py` attaches the full 100-point M1 quality
  explanation after structural validation. The default C-grade policy is
  observe-only; it does not claim that structure was invalid.
- `config/final_fidelity_patch_v1.json` publishes every new threshold and
  confirms research-only operation.
- `tools/run_final_fidelity_patch_v1.py` runs identical-data baseline/patch
  analysis, chronological development/validation/holdout splits, 60 patched
  charts, the 40-case exact baseline reference, and all requested audits.
- `tests/test_final_fidelity_patch_v1.py` adds deterministic quality,
  continuation, hysteresis, giveback, exhaustion, ownership, stop, counting,
  causality, and no-order expectations.

## Honest behavioural result

The best retained configuration is selected by the mandate's multi-metric
criteria, not win rate. If validation or holdout fails any required behavioural
condition, the evidence report marks the relevant verdict PARTIAL, withholds
the strategy freeze, and keeps simulator readiness at NO. No result is
relabelled to manufacture a pass.

