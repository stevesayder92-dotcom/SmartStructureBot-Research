# SmartStructureBot — Exact Handoff / Upload Order

Use this order so Kiro and Codex do not work from different source truths.

## Stage 1 — Kiro first (implementation + mass-test engineering)

### A. On Steve's laptop, create the repository snapshot

1. Open PowerShell in the ACTUAL current SmartStructureBot project root.
2. Extract `SmartStructureBot_Kiro_MassTest_Handoff.zip` somewhere convenient.
3. Copy `PACKAGE_SMARTSTRUCTUREBOT_FOR_KIRO.ps1` into the project root.
4. Run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\PACKAGE_SMARTSTRUCTUREBOT_FOR_KIRO.ps1
```

This creates:

`Desktop\SmartStructureBot_Kiro_Handoff\`

### B. Put these handoff documents into that Desktop folder

- `STRATEGY_MASTER_CONTRACT_TP1_ONLY.md`
- `KIRO_MASS_TEST_HANDOFF.md`
- `KIRO_RETURN_CHECKLIST.md`
- `HANDOFF_UPLOAD_ORDER.md`

### C. The folder should now contain at minimum

- `SmartStructureBot_SOURCE.zip`
- `STRATEGY_MASTER_CONTRACT_TP1_ONLY.md`
- `KIRO_MASS_TEST_HANDOFF.md`
- `KIRO_RETURN_CHECKLIST.md`
- `HANDOFF_UPLOAD_ORDER.md`
- `GIT_STATUS.txt`
- `GIT_BRANCH.txt`
- `GIT_COMMIT.txt`
- `GIT_LAST_COMMIT.txt`
- `PYTHON_VERSION.txt`
- `UNCOMMITTED_CHANGES.patch`
- `BASELINE_TESTS.txt`
- `DATA_MANIFEST_SHA256.txt`

If historical data is too large to fit inside `SmartStructureBot_SOURCE.zip`, attach/export the data separately and preserve the SHA256 manifest.

### D. Upload to Kiro

Upload ALL of the following to the same Kiro task/session:

1. `SmartStructureBot_SOURCE.zip`
2. `STRATEGY_MASTER_CONTRACT_TP1_ONLY.md`
3. `KIRO_MASS_TEST_HANDOFF.md`
4. `KIRO_RETURN_CHECKLIST.md`
5. `GIT_STATUS.txt`
6. `GIT_BRANCH.txt`
7. `GIT_COMMIT.txt`
8. `GIT_LAST_COMMIT.txt`
9. `UNCOMMITTED_CHANGES.patch`
10. `BASELINE_TESTS.txt`
11. `DATA_MANIFEST_SHA256.txt`
12. Historical M1/M5 datasets if not already inside the source ZIP

Primary datasets desired:

- GOLD# M1 + M5
- US100Cash# M1 + M5
- GER40Cash# M1 + M5
- US30Cash# M1 + M5
- OILCash# M1 + M5

Also attach AUDUSD#/EURUSD#/GBPUSD#/USDJPY# if available for stress testing.

Preferred history: 12–24 months. Minimum useful first study: ~6 months.

### E. Exact first prompt to Kiro

> Use `STRATEGY_MASTER_CONTRACT_TP1_ONLY.md` as the strategy authority and `KIRO_MASS_TEST_HANDOFF.md` as the engineering specification. Do not change or optimize the strategy. First consolidate the current repository into one clean branch containing the documented Gate-11 fixes and `TP1_ONLY_RESEARCH`. Preserve all normal runner code but disable runner/+0.01R/M5 runner chase under TP1-only mode. Then build a fast incremental prefix-causal replay engine and mass-test the frozen strategy on all supplied data. Produce every artifact in `KIRO_RETURN_CHECKLIST.md`. If code and the strategy contract disagree, report the disagreement rather than silently choosing the code. Do not begin AI/ML work.

---

## Stage 2 — Return Kiro results to ChatGPT / Steve

Do not accept screenshots alone.

Require Kiro to return:

- exact Git commit hash,
- clean source ZIP or branch archive,
- full git diff,
- full test logs,
- data SHA256 before/after,
- entry audit CSV,
- rejected-candidate CSV,
- closed-trade CSV,
- overall summary JSON,
- overall summary Markdown,
- per-symbol metrics,
- per-session metrics,
- M1 vs M5 metrics,
- Attempt 1 vs Attempt 2 metrics,
- fidelity/causality failure report,
- exact PowerShell reproduction command.

Then upload those artifacts back to ChatGPT for acceptance review.

---

## Stage 3 — Codex second (independent reviewer, NOT parallel strategy author)

Only after Kiro has produced a concrete tested branch/results.

### Upload to Codex

1. `STRATEGY_MASTER_CONTRACT_TP1_ONLY.md`
2. Kiro's exact tested source/branch archive
3. Kiro's `git diff`
4. Kiro's test logs
5. Kiro's entry audit CSV
6. Kiro's rejected-candidate CSV
7. Kiro's closed-trade CSV
8. Kiro's summary JSON/Markdown
9. Kiro's data SHA256 report
10. `KIRO_RETURN_CHECKLIST.md`

### Exact first prompt to Codex

> Act as an independent SmartStructureBot verification engineer. Treat `STRATEGY_MASTER_CONTRACT_TP1_ONLY.md` as strategy authority. Do not redesign or optimize the strategy. Audit Kiro's branch and evidence for: future-data leakage, prefix/suffix causality, duplicate ownership, incorrect trend confirmation, wrong retracement trigger, BOS timing, wrong pre-BOS wick stop, wrong parent-body TP1, M1/M5 ownership drift, re-entry errors, Attempt 3, management affecting entry population, hidden exclusions, incorrect R math, and non-reproducible mass-test results. Re-run or add adversarial tests where necessary. Report every disagreement. Do not add AI/ML.

---

## Source-of-truth hierarchy

1. Steve's explicit strategy rule
2. `STRATEGY_MASTER_CONTRACT_TP1_ONLY.md`
3. Canonical tests that implement that contract
4. `KIRO_MASS_TEST_HANDOFF.md`
5. Current canonical code
6. Historical S2B documents/code/comments

If lower-level material contradicts higher-level material, do not silently follow the lower-level source.

---

## Current experiment boundary

This mass test is TP1-only.

Winning trade:

`valid BOS entry -> original pre-BOS wick SL -> parent body TP1 -> 100% exit at TP1 -> setup complete`

There must be:

- no runner fraction,
- no +0.01R,
- no M5 post-TP1 chase,
- no post-TP1 runner event.

Runner code stays preserved for later A/B testing but is not part of current profitability baseline.
