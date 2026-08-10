# SmartStructureBot Phase S2B Baseline Compatibility Report

## Baseline identity

The source is the accepted post-S2A.1 extracted release tree. It is not a Git
repository, so branch and commit metadata do not exist. The pre-change
`research_runs/s2b/baseline_manifest.json` freezes critical source,
configuration, S2A.1 evidence and dataset-index SHA256 values. The final
reproducibility manifest records all post-change hashes and a deterministic
working-tree hash.

## Compatibility result

The default policy remains `COUNTER_CONFIRMED_ACTIVE`.

The focused regression proves that implicit default and explicit baseline
policy return identical reports. The full paired audit provides a stronger
population proof: every one of the 115 parents that did not earn pre-ACTIVE
permission had the same baseline/S2B entry timeframe, time, price, logical
stop and sequence result. Mismatches: zero.

S2B changed exactly the 77 parents that earned pre-ACTIVE permission. No
ACTIVE-era result changed merely because the research policy was enabled.

## Unchanged contracts

No HTF policy or threshold, Fib semantic, retracement threshold, swing
sensitivity, M5 BOS rule, M1 body-close/wick rule, M1 quality threshold,
management rule, target hierarchy, re-entry allowance, account-risk rule,
spread/slippage rule, session/news rule or order-execution policy was retuned.

The only production interface additions are:

- a configuration field whose default is the accepted baseline policy;
- read-only canonical permission state and observability fields;
- an opt-in research resolver for the pre-ACTIVE interval.

When the S2B policy is off, the new resolver is not entered.

## Test evidence

- 30/30 focused S2B tests passed.
- 340/340 complete strategy tests passed.
- 87/87 complete simulator tests passed.
- No inherited failures.
- Static order-call test found no `order_send`/`OrderSend` call in S2B paths.

Full command output is preserved in
`research_runs/s2b/full_test_results.txt`.

