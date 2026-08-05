# Final Sequence Elite v1 — exact test results

Environment: bundled Python runtime, `MPLBACKEND=Agg`, research-only project.

## Patch suite

Command: `python -m unittest tests.test_sequence_elite_patch -v`

```text
Ran 40 tests in 0.032s
OK
```

## Full repository suite

Command: `python -m unittest discover -s tests -p "test_*.py" -v`

```text
Ran 227 tests in 91.069s
OK
```

Clean release rerun:

```text
Ran 227 tests in 97.912s
OK
```

## Evidence runner

```text
Frozen primary setups: 60
Separate supplementary setups: 20
Execution attempts: 99
Executed re-entries: 39
Future-candle violations: 0
Unfinished-candle violations: 0
Duplicate entries: 0
More than one re-entry per parent: 0
Order API calls: 0
```
