# Final Fidelity Patch v1 configuration

All values are research defaults; order execution is disabled. ATR means price
distance measured in the current timeframe's average true range. R means the
initial entry-to-logical-stop risk.

| Parameter | Default | Units | Purpose and expected impact |
|---|---:|---|---|
| M1 component weights | 20/15/20/10/15/10/10 | points | Explainable 100-point quality score; changing them shifts grades, not structural validity. |
| M1 grade thresholds | 85/70/55 | points | A+/A/B boundaries; higher values retain fewer early entries. |
| C M1 policy | OBSERVE_ONLY | policy | Studies low-value structural signals without opening a research attempt. |
| meaningful_m1_swing_atr | 0.35 | ATR | Separates readable counter movement from micro noise. |
| stale_trigger_candles | 30 | M1 candles | Penalizes old triggers; structural hard staleness remains separate. |
| overlap_warning_ratio | 0.65 | ratio | Penalizes disorderly overlapping M1 action. |
| bos_displacement_atr | 0.35 | ATR | Reference for a meaningful body-close BOS. |
| continuation thresholds | 80/65/45/25 | points | Strong/healthy/weakening/exhaustion bands. |
| hysteresis_confirmations | 2 | closed candles | Stops soft states oscillating on one candle. |
| favourable_progress_r | 0.35 | R | Marks early useful progress. |
| early_protection_r | 0.90 | R | Eligibility input only; never creates an arbitrary stop. |
| small_profit_lock_r | 0.10 | R | Small lock used only with mature exhaustion/giveback support. |
| elevated_giveback_r | 0.75 | R | Starts contextual giveback review. |
| severe_giveback_r | 1.25 | R | Escalates protection when maturity and deterioration agree. |
| unacceptable_capture_ratio | 0.25 | ratio | Flags mature trades retaining under one quarter of peak R. |
| exhaustion thresholds | 80/65/45/25 | points | Confirmed/high/meaningful/early warning bands. |
| partial_exit_research | true | boolean | Records partial-exit research; cannot call an order API. |
| runner_exit_policy | structure or target supported | policy | Prevents score-only panic exits. |
