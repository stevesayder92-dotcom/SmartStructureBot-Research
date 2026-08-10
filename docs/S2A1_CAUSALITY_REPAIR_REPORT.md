# S2A.1 Causality Repair Report

## Proven defect and repair

The pre-repair regression failed with the same closed M1 prefix: changing only later M5 outcome facts changed score `56.743 -> 51.143`, grade `B_M1 -> C_M1`, policy `REDUCED_RESEARCH_RISK -> OBSERVE_ONLY`, entry readiness and arbitration. The causal repair removes the future-M5 timing/stop component without redistributing its ten points, recomputes time-varying parent facts at the M1 close, and prevents arbitration from selecting an M5 fallback before that fallback exists.

## Full-data evidence

- Direction-specific terminal M5 candidates scanned: **290**
- HTF-aligned parent setups: **192**
- Pre-active trigger-side swing events: **762** across **171** setups
- Fully valid shadow early M1 events: **163** across **78** setups
- Median timing advantage (earliest valid event per setup): **46.0 minutes**
- Median stop-distance improvement: **7.143%**
- Causal quality observations: **195**; grade changes from future-data removal: **104**
- Old grade distribution: **A_PLUS_M1 22, A_M1 110, B_M1 55, C_M1 8**
- Causal grade distribution: **A_PLUS_M1 0, A_M1 74, B_M1 91, C_M1 30**
- Median score change from eliminating future-dependent information: **-8.119 points**

## Verdict

A. **Yes.** Original M1 quality depended on future M5 entry/stop facts.  
B. **Yes.** The reproduced case crossed B_M1/C_M1 and executable/observe-only.  
C. **Yes.** Those facts are now analytics-only and absent from causal snapshots.  
D. **Yes.** The complete synchronized path passed unchanged and materially different suffix tests.  
E. `candidate["qualified_at"]` is the M5 failure-trigger confirmation availability index.  
F. ARMED is anchor-confirmed observation; ACTIVE is counter-confirmed canonical M1 permission.  
G. **163 events.**  
H. **78 unique setups.**  
I. **46.0 minutes median.**  
J. **7.143% median stop-distance improvement.**  
K. **Yes for S2B investigation only; S2A.1 does not activate early entries.**

Research only. HTF policy unchanged. No live/demo order API called.

## Final test result

- S2A.1 focused causality contracts: **8/8 PASS**
- Entire inherited strategy suite: **310/310 PASS**
- Entire simulator suite: **87/87 PASS**
- Order API calls: **0**
