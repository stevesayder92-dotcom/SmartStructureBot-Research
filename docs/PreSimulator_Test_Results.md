# Pre-Simulator Canonical Repair test results

Environment: bundled 64-bit Python on Windows, research-only configuration.

## Repair contract suite

```text
.......................................
----------------------------------------------------------------------
Ran 39 tests in 1.160s

OK
```

## Full authoritative repository suite

```text
..........................................................................................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 266 tests in 100.703s

OK
```

The replay also reports zero future-candle violations, unfinished-candle violations, duplicate first entries, more-than-one re-entry cases, incomplete Attempt-2 management records, non-causal partial decisions, sequence-accounting violations, emergency account-risk breaches, and order API calls.
