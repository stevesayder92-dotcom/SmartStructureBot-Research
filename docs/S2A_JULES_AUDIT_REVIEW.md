# Phase S2A review of the Jules funnel audit

## Authority and artifact inventory

The Phase S2A mandate identifies six external artifacts, including
`tools/audit/funnel_audit.py`. None of the six files exists in the active
Phase S1B working source, any earlier SmartStructureBot work/deliverable tree,
the Desktop, Downloads, Documents search roots, or the Codex attachment store
available to this task.

Consequently a literal source-line review is impossible from the supplied
files. The table below reviews every defect quoted verbatim by the mandate.
The `line` column is `UNAVAILABLE_SOURCE_NOT_SUPPLIED` rather than an invented
line number. Previous numerical conclusions remain non-authoritative until
the missing source and its original datasets can be hashed and reproduced.

| line | field | current reported behaviour | why invalid | correct canonical source | previous conclusion usable? |
|---|---|---|---|---|---|
| `UNAVAILABLE_SOURCE_NOT_SUPPLIED` | accepted synchronized entries | Manifest says 0 while Markdown says 88. | Two outputs from one run do not reconcile. At least one is stale or computed from different semantics. | Canonical `entry`, simulator `Director_decision`, and immutable paper event for the same setup/event clock. | No. |
| `UNAVAILABLE_SOURCE_NOT_SUPPLIED` | candidate verdict | CSV says 141 rejected and 0 accepted while Markdown says 88 accepted and 53 non-accepted. | Acceptance cannot be reconstructed from report membership or a different output table. | Canonical Director action per setup, with event and unique-setup counts separated. | No. |
| `UNAVAILABLE_SOURCE_NOT_SUPPLIED` | blocker totals | CSV blocker counts total 141 rejected candidates. | The total contradicts the claimed 88 accepted cases and therefore does not reconcile to a single candidate population. | First blocking owner/code from the canonical snapshot at that candle. | No. |
| `UNAVAILABLE_SOURCE_NOT_SUPPLIED` | HTF mismatch | CSV says 120; Markdown says 23. | Conflicting counts with no common denominator, dataset hash or event/setup distinction. | `HTFContextEngine.state`, `approved_direction`, `hard_block`, reasons and causal availability at the candidate candle. | No. |
| `UNAVAILABLE_SOURCE_NOT_SUPPLIED` | insufficient history | CSV says 6; Markdown says 27. | Conflicting counts and no proof that both outputs use the same full closed-candle population. | Closed-series validation plus the exact engine WAIT/BLOCK state. | No. |
| `UNAVAILABLE_SOURCE_NOT_SUPPLIED` | M1 alignment | CSV says 8; Markdown says 3. | Conflicting counts and no distinction between repeated M1 events and unique parent setups. | `M1ChildStructureEngine` rejection event plus `parent_m5_setup_id`; publish event and unique-setup counts. | No. |
| `UNAVAILABLE_SOURCE_NOT_SUPPLIED` | `significance_score` | Reportedly copied from `fibonacci.display_remaining_impulse_percent`. | Remaining impulse is a Fibonacci location metric, not the retracement significance score requested by the audit. | `UNAVAILABLE` unless a canonical significance contract publishes a score. | No. |
| `UNAVAILABLE_SOURCE_NOT_SUPPLIED` | `counter_structure_count` | Reportedly set to 1 when `pool_match`, otherwise 0. | Pool membership is neither a measured count nor canonical structure evidence. | Exact canonical counter-structure collection, if published; otherwise `UNAVAILABLE`. | No. |
| `UNAVAILABLE_SOURCE_NOT_SUPPLIED` | `duration_component` | Reportedly set to 10 when `pool_match`, otherwise 0. | Hard-coded acceptance membership creates a circular measurement. | Canonical qualification component, if published; otherwise `UNAVAILABLE`. | No. |
| `UNAVAILABLE_SOURCE_NOT_SUPPLIED` | `overlap_component` | Reportedly set to 8 when `pool_match`, otherwise 0. | Hard-coded acceptance membership creates a circular measurement. | Canonical qualification component, if published; otherwise `UNAVAILABLE`. | No. |
| `UNAVAILABLE_SOURCE_NOT_SUPPLIED` | `structure_component` | Reportedly set to 20 when `pool_match`, otherwise 0. | Hard-coded acceptance membership creates a circular measurement. | Canonical qualification component, if published; otherwise `UNAVAILABLE`. | No. |
| `UNAVAILABLE_SOURCE_NOT_SUPPLIED` | `qualification_index` | Reportedly substituted with the candidate M5 index. | The entry candidate candle is not necessarily the candle on which the trigger became causally available. | `QualifiedRetracementEngine.qualification_available_at_index`. | No. |
| `UNAVAILABLE_SOURCE_NOT_SUPPLIED` | `protected_structure_index` | Reportedly substituted with `fib_zero_index`. | Fibonacci origin and protected-structure ownership are distinct contracts even when their prices sometimes coincide. | `ProtectedStructureEngine.relevant_structure_index`; otherwise `UNAVAILABLE`. | No. |
| `UNAVAILABLE_SOURCE_NOT_SUPPLIED` | 605 M1 rejection events | Treated as a missed-opportunity lead. | One parent can emit several trigger/rejection events; event count is not missed-trade count. | Immutable M1 events deduplicated by setup/event identity, alongside unique setup count. | Lead only; not a strategy conclusion. |
| `UNAVAILABLE_SOURCE_NOT_SUPPLIED` | 381 early-trigger events across 82/88 parents | Suggested parent-activation timing weakness. | The relationship is plausible but must be reproduced from canonical parent active time and M1 event state. Repeated scans can duplicate the same event. | `parent.active_time`, M1 rejection state/index, canonical event deduplication. | Lead only. |
| `UNAVAILABLE_SOURCE_NOT_SUPPLIED` | last 1,800 M5 bars | Audit reportedly truncated history. | It excludes usable closed data without a canonical research requirement. | Every usable row in `simulator_data/library`, processed without candidate sampling. | No for full-library prevalence. |
| `UNAVAILABLE_SOURCE_NOT_SUPPLIED` | maximum 60 candidates | Audit reportedly downsampled candidates. | Sampling changes event and setup prevalence and can hide bottlenecks. | Full production candidate output, chronologically batched only. | No for counts or rates. |

## Safe conclusion

The external package supplied useful hypotheses but no trustworthy numerical
result. Phase S2A independently measures canonical state and writes absent
fields as `UNAVAILABLE`. If the original six artifacts are later supplied,
their hashes and exact line numbers should be appended to this document; they
must not replace the new canonical evidence.
