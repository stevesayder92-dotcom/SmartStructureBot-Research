# S2B.1.1 Implementation Tasks

- [x] Task 0 — Update SmartStructureBot_Bible.md before source edits with the locked S2B.1.1 semantics only.
- [x] Task 1 — Capture immutable research_data/ SHA-256 baseline and move clean-checkout fixture dependency to tracked test_data/s2b1_1/.
- [x] Task 2 — Implement causal second-touch recognition: Touch_2_Index candidate, no N-right delay, 0.25 ATR proximity, 0.35 ATR reaction, 3-bar separation, provisional pre-BOS trigger, body-close BOS proof.
- [x] Task 3 — Repair InitialStopContract semantics and body-edge contamination in core/steve_trade_management.py; preserve M1 exact wick and M5 0.15*ATR(entry_index) boundaries.
- [x] Task 4 — Preserve existing Director-owned decision architecture and propagate repaired second-touch evidence without creating another Director.
- [x] Task 5 — Propagate second-touch owner semantics through synchronized M1/re-entry/research paths; keep InitialStopContract separate from mutable protection.
- [x] Task 6 — Add deterministic S2B.1.1 tests for causal timing, suffix invariance, exact wick ownership and contract completeness.
- [ ] Task 7 — Generate and validate all four manual reconstruction reports from repository-local anchor evidence.
- [x] Task 8 — Add portable tools/run_s2b1_1_research.py with no sibling Codex workspace dependency and isolated research_runs/s2b1_1 output.
- [ ] Task 9 — Execute complete A/B/C research across all available symbols and publish final reconciliation metrics.
- [ ] Task 10 — Final release gate: inherited simulator suite in native project Python environment, complete research rerun, before/after research_data hash equality, zero order APIs, final reports, commit/push only after Steve approval.

## Final acceptance gates

1. New S2B.1.1 tests pass.
2. Inherited strategy tests pass except environment-incompatible pickle tests when run outside the project's native Python/pandas environment; those must pass on the native Windows environment before release.
3. BUY/SELL × M1/M5 stop-contract semantics proven.
4. research_data hash unchanged.
5. No sibling workspace dependency.
6. Zero live/demo/order API usage.
7. A/B/C metrics complete.
8. Variant/manual visual integrity verified.
