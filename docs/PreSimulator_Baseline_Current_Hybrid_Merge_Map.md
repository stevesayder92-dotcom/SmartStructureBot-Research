# Baseline → Current → Repaired Hybrid merge map

| Behaviour | Baseline owner | Current owner | Current difference | Canonical decision |
|---|---|---|---|---|
| First-entry identity and synchronization | Director / synchronized replay | Same | Stable and causal | KEEP_SEQUENCE_ELITE |
| Attempt-1 management | ProfitProtectionEngine / TradeManager | Elite overlay around a second simulation | Changed accepted outcomes without proven improvement | KEEP_BASELINE |
| Target lifecycle | TargetLifecycleEngine | Baseline plus final-state partial overlay | Partial fraction could use later state | KEEP_BASELINE + REPAIR partial commitment |
| Meaningful trails and opposing BOS | TradeManager | Baseline actions plus analytics | Analytics did not always affect outcome | KEEP_BASELINE authority |
| Sequence identity/counting | Setup registry | SequenceAccountingEngine | Correct identities, incorrect peak arithmetic | KEEP_SEQUENCE_ELITE + REPAIR equity |
| Parent viability | Setup lifecycle | Protection-intact shortcut | Too many re-entries | REPAIR_AND_REPLACE |
| M1/M5 re-entry ownership | M1 child / M5 parent | First technical BOS | Micro recross could outrank parent confirmation | REPAIR_AND_REPLACE |
| Attempt-2 management | Not complete | Basic stop/target replay | Missing fresh trails/transitions/full evidence | REPAIR_AND_REPLACE |
| Opportunity and deterioration | Baseline structural management | Supporting analytics | Useful evidence, weak commitment | KEEP_SEQUENCE_ELITE evidence; baseline TradeManager commits |
| Mature-profit floor | Proven structure | Structural selector | Correct principle, incomplete action path | REPAIR_AND_REPLACE |
| Emergency risk | Emergency broker stop | Logical-R denominator | Could report multi-R economic loss ambiguously | REPAIR_AND_REPLACE |
| Final-state partial sizing | Not used | Dynamic final-state overlay | Non-causal | REMOVE_OBSOLETE |
| Three management/risk profiles | Research reports | Experimental | Useful comparison only | AUDIT_ONLY |

The frozen 60 first entries are immutable. Any mismatch is reported as
`ENTRY_POPULATION_DRIFT` and excluded from the main comparison.
