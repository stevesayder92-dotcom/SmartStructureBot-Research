# StateSnapshot schema

Every immutable event contains a `snapshot` with these roots:

| Root | Purpose |
|---|---|
| `identity` | Session, event, schema, strategy, simulator and symbol identity. |
| `replay_clock` | Event number/time and deterministic processing order. |
| `data_visibility` | M1/M5 indices and rows; future/unfinished counts. |
| canonical roots | `meta`, `market`, `structure`, `control`, `context`, `transition`, `validation`, `protection`, `impulse_cycle`, `setup_invalidation`, `retracement`, `setup`, `entry`, `decision`, `trade`, `contract_health`. |
| `m1_entry` | Synchronized child monitoring, rejections and accepted entry. |
| `management` | Canonical attempt, target, trail, exit and re-entry state. |
| `recommendations` | Non-authoritative engine advice. |
| `Director_decision` | Sole committed action and reasons. |
| `shadow_managers` | Isolated alternative policies. |
| `bug_flags` | Diagnostic evidence only. |
| `sequence_accounting` | Attempt and sequence R ledger. |
| `trade_story_events` | Human-readable published state changes. |
| `integrity` | Causality, schema, ownership, isolation and order checks. |

The snapshot ends with `snapshot_hash` and `parent_snapshot_hash`. JSON is
normalized before hashing. Earlier snapshots are never modified.
