# S2A.1 M1 Causal Field Audit

The runtime parent contract now publishes `causal_parent_context` separately
from `retrospective_m5_outcome`. Only the first section may enter M1 structure,
quality or canonical arbitration.

| Field | Classification | Production treatment |
|---|---|---|
| parent/setup/retracement/impulse/protection IDs | `CAUSAL_AT_ARMED` | Immutable ownership |
| `parent_direction` | `CAUSAL_AT_ARMED` | Immutable child direction |
| anchor identity, level, `armed_time` | `CAUSAL_AT_ARMED` | Observation boundary |
| fixed Fib zero/hundred anchors and price boundary | `CAUSAL_AT_ARMED` | Immutable location envelope |
| counter identity, level, `active_time` | `CAUSAL_AT_ACTIVE` | Canonical execution boundary |
| `dominant_protection_intact` | `CAUSAL_AT_M1_ENTRY` | Recomputed from candles closed by the proposed M1 entry |
| current Fib zone/depth | `CAUSAL_AT_M1_ENTRY` | Recomputed from fixed anchors and candles closed by the proposed M1 entry |
| current parent retracement state | `CAUSAL_AT_M1_ENTRY` | Snapshot carries explicit as-of time/index |
| `m5_failure_trigger_index/price` | `RETROSPECTIVE_ONLY` for earlier M1 | Stored only in retrospective outcome |
| `m5_failure_trigger_confirmed_at_index` | `RETROSPECTIVE_ONLY` for earlier M1 | Chronology analytics only |
| `m5_entry_time/index/price` | `RETROSPECTIVE_ONLY` | Fallback/outcome analytics after occurrence |
| `m5_logical_stop` and structure index/level | `RETROSPECTIVE_ONLY` | Never enters M1 score or stop |
| `m5_logical_stop_contract` | `RETROSPECTIVE_ONLY` | Analytics only |
| `m5_emergency_stop` | `RETROSPECTIVE_ONLY` | M5 fallback execution only after occurrence |
| minutes saved versus M5 | `RETROSPECTIVE_ONLY` | Post-hoc evidence |
| price/stop/RR improvement versus M5 | `RETROSPECTIVE_ONLY` | Post-hoc evidence |
| eventual target/result | `RETROSPECTIVE_ONLY` | Outcome review only |
| terminal candidate object | `RETROSPECTIVE_ONLY` | Deep-copied under retrospective outcome; absent from causal snapshots |

Audit conclusion: no field classified `RETROSPECTIVE_ONLY` is read by
`M1EntryQualityEngine.evaluate`. `find_m1_child_entry` receives an explicit
decision time and bounds M1 discovery to that close. `arbitrate_first_valid_entry`
may choose M5 only after the M5 fallback timestamp has occurred; later outcome
metrics are built separately by `build_post_hoc_m1_advantage`.

