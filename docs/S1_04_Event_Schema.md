# ReplayEvent schema

A ReplayEvent is the immutable unit of playback.

Required identity and clock fields: `replay_event_id`, `event_number`,
`event_time`, newly closed M1/M5 indices, visible-row counts and processing
order.

Required ownership fields: parent setup ID and active attempt ID when
available.

Required decision fields: event type/priority, recommendations, one
`director_decision`, shadows, bug flags and story events.

Required integrity fields: `state_hash`, `snapshot_hash`,
`parent_snapshot_hash`, `pipeline_state_hash` and the full integrity object.

Event types include candle closes, phase changes, retracement qualification,
M1/M5 entry readiness, protection movement, target change, first-attempt exit,
re-entry, opposing BOS exit and bug flag. A candle-close event may legitimately
commit `NO_ACTION`; a committed action is never inferred from a label.

`ReplaySession.restore()` returns the exact stored event. `compare()` reports
field-level before/after values without altering either event.
