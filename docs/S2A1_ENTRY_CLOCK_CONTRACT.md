# S2A.1 Entry Clock Contract

All timestamps are UTC close timestamps. A swing at index `i` with sensitivity
`N` is not available until candle `i + N` has closed. Candle-open timestamps
are never treated as decision timestamps.

| Clock | Exact production meaning | Earliest legal use |
|---|---|---|
| `anchor.index` | M5 pullback-origin/impulse-extreme swing occurrence | Never by itself |
| `anchor.confirmed_at_index` | Right-side confirmation candle for the anchor | Its M5 close |
| `parent.armed_time` | Close of `anchor.confirmed_at_index` | M1 observation may start |
| `counter.index` | Opposing M5 counter swing occurrence | Never by itself |
| `counter.confirmed_at_index` | Right-side confirmation candle for the counter | Its M5 close |
| `parent.active_time` | Close of `counter.confirmed_at_index` | Canonical M1 execution may start |
| `candidate.qualified_at` | Availability index at which `FAILURE_TRIGGER_CONFIRMED` is emitted | Describes M5 failure-trigger confirmation; not legal entry time |
| M1 trigger swing time | Open timestamp of the trigger-side swing candle | Descriptive only |
| M1 trigger available time | Close of the trigger's right-side confirmation candle | Trigger may enter sequence/BOS validation |
| M1 BOS close time | Close of the correctly directed body-close candle beyond the trigger | Legal M1 entry time after every gate passes |
| M5 fallback entry time | Close of the canonical M5 BOS entry candle | M5 fallback may be committed only at/after this time |

`ARMED` means the parent anchor and immutable parent identity are causally
known. It does not mean the parent has the counter structure required for a
canonical M1 execution. `ACTIVE` means that M5 counter swing has also been
causally confirmed. The ARMED-to-ACTIVE interval is shadow-audit territory in
S2A.1; it does not create canonical trades.

The authoritative source for `qualified_at` is
`core/expert_strategy.py::_simulate_retracements`: it is assigned on the same
iteration that appends `FAILURE_TRIGGER_CONFIRMED`. The accurate name is
`m5_failure_trigger_confirmed_at_index`.

