# Bug-flag glossary

Bug flags are review signals. They cannot change a Director action.

| Flag | Review question |
|---|---|
| `PREFIX_STATE_MISMATCH` | Does the stored prefix differ from direct canonical recomputation? |
| `STATE_HASH_MISMATCH` | Was immutable state changed after hashing? |
| `MULTIPLE_ACTIONS_SAME_EVENT` | Was more than one canonical action committed? |
| `ORDER_API_DETECTED` | Did prohibited execution code become reachable? |
| `ENTRY_TOO_EARLY` | Was entry committed before owned closed-candle proof? |
| `STOP_USES_POST_ENTRY_DATA` | Does stop ownership depend on a later candle? |
| `REENTRY_BEFORE_EXTENSION_PROOF` | Was fresh parent proof missing? |
| `SEVERE_GIVEBACK` | Was earned opportunity lost despite legal tighter protection? |
| `WINNER_TO_LOSER_REVERSAL` | Did a materially positive attempt finish below initial risk? |
| `ENGINE_DIRECTOR_CONFLICT` | Which recommendation was rejected and why? |

Each flag stores event ID, severity, evidence and a suggested review question.
Playback pauses automatically on integrity `FAIL`. Manual classifications are
saved separately and never rewrite the flag or canonical event.
