# Final Sequence Elite v1 — code change report

## Bible-first contract

The Strategy Bible was updated before implementation. It now owns sequence
identity, cross-timeframe re-entry, final invalidation structure, earned
opportunity, opportunity risk, mature structural floors, partial profiles, and
all 40 deterministic patch-test names.

## Runtime additions

- `core/sequence_recovery.py`: one-shot synchronized M1/M5 re-entry,
  attempt/sequence accounting, causal stop selector, opportunity and risk
  engines, structural floor selection, research partial profiles, and
  behavioural metrics.
- `core/synchronized_m1_replay.py`: publishes the final important pre-entry M5
  structure body edge separately from its ATR-tolerant close boundary.
- `config/sequence_elite_v1.json`: all new research parameters and explicit
  order-disable flags.
- `tools/run_sequence_elite_evidence.py`: replays the frozen 60 plus 20 separate
  supplementary setups; emits charts, CSV/JSON/Markdown audits, focused
  collections, and a manual review page.
- `tests/test_sequence_elite_patch.py`: 40 deterministic contract tests.

## Causal re-entry clarification

A re-entry BOS cannot be created retrospectively. The recovery window must
contain a causally confirmed meaningful counter-structure; the entry candle
must make a fresh cross of an unconsumed trigger. M1 and M5 compete by actual
closed-candle availability. Trigger close depth is a soft quality factor and
does not hard-filter a structurally valid re-entry.

## Evidence result and freeze decision

The architecture and causal contracts passed, but the behaviour did not earn a
strategy freeze. On the identical 60, average sequence result fell from
`0.1544R` to `0.0069R`; holdout fell from `-0.2686R` to `-0.8495R`.
Thirty-nine re-entries averaged `-0.3010R`, with only two recovered sequences.
Trade 51 also produced a valid M1 close before the requested later M5 close.
Forcing M5 would contradict `FIRST_VALID_CLOSED_BOS_WINS` or require a
case-specific exception. The simulator-readiness verdict therefore remains NO.

No entry population was changed, no future/unfinished candle was used, and no
order API was called.
