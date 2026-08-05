# SMARTSTRUCTUREBOT — CODEX MASTER COMPLETION BRIEF v2.0

## Project identity

Project: SmartStructureBot  
Owner: Steve Sayder  
Platform: Python + MetaTrader 5  
Primary symbols: GOLD#, US100Cash#, US30Cash#, GER40Cash#, OILCash#  
HTF context: H1, M30, M15  
Primary entry timeframe: M5  
Fallback/refinement timeframe: M1  
Sessions: London, New York, London–New York overlap  
Current status: causal research and validation system; not approved for unattended live capital.

## Authoritative strategy

SmartStructureBot trades continuation after a failed retracement.

```text
Valid dominant trend
→ counter-trend move
→ counter-structure forms
→ counter-structure fails
→ candle body closes through the relevant trigger
→ enter at that BOS candle close
→ manage with structure
```

The failed-retracement BOS candle is simultaneously:

- retracement end;
- continuation confirmation;
- intended entry candle.

Wicks do not confirm BOS or logical invalidation. One valid body-close candle is enough. Entry price is the actual BOS candle close, not the trigger level and not a body extreme.

## Non-negotiable strategy rules

1. No future-data leakage.
2. No stale historical entry may remain executable.
3. No second confirmation candle or retest is required by default.
4. A local pullback does not automatically reverse the dominant trend.
5. Do not solve every weakness by adding hard filters.
6. Prefer scoring and risk tiers:
   - strong setup → normal risk;
   - acceptable setup → reduced risk;
   - structurally invalid setup → reject.
7. M1 logical invalidation uses body close beyond the relevant swing close.
8. M5 logical invalidation uses structure plus configurable ATR tolerance.
9. Keep a distant emergency broker stop separate from the logical software stop.
10. Allow at most one re-entry per setup when the original setup remains structurally valid.

## Current intended pipeline

```text
Market data
↓
Causal truncation at as_of_index
↓
SystemStateDirector
↓
Swing detection and validation
↓
Structure classification
↓
Hierarchy and importance
↓
BOS detection
↓
Trend and phase
↓
Master structure state
↓
Market control
↓
Transition state
↓
Decision protection
↓
Retracement lifecycle
↓
Setup invalidation structure
↓
ContinuationEngine
↓
EntryValidator
↓
Canonical final entry
↓
SignalLedger
↓
ReplayInspector
↓
Trade simulator
↓
Performance analytics
↓
Paper execution
↓
Controlled live execution
```

## Ownership boundaries

### SystemStateDirector

Single owner of the current snapshot and approved communication contracts. Engines must not pass uncontrolled mutable truth between themselves.

### RetracementManager

Describes the current pullback lifecycle and the current structural failure trigger. It must remain causal and may not preserve an old confirmation as a new current entry.

### ContinuationEngine

Owns structural continuation detection only:

```text
Did the current candle close beyond the failed-pullback trigger?
```

It remains a close-only structural engine.

### EntryValidator

Owns executable candle validation after ContinuationEngine finds a structural candidate.

Initial mandatory checks:

Bullish:

```text
candidate index == current as_of_index
close > trigger
close > open
candidate is causal
```

Bearish:

```text
candidate index == current as_of_index
close < trigger
close < open
candidate is causal
```

Future scoring may include body ratio, close strength, ATR expansion, break distance, opposing wick, displacement, engulfing behavior, and session quality. Do not put these responsibilities back into ContinuationEngine.

### SignalLedger

Append-only causal audit ledger. It must record accepted and rejected candidates, preserve stable setup identity, prevent duplicates, and never recompute upstream truth.

### ReplayInspector

Human-review layer for canonical entries. It must expose setup ID, trigger, entry, protection, invalidation, validator result, lifecycle status, and nearby candles.

## Current verified progress

Earlier replay achieved:

```text
Candles Processed       : 300
Pipeline Errors         : 0
Integrity Failures      : 0
Non-Causal Events       : 0
Stale Entries           : 0
Post-Entry Proof Leaks  : 0
Replay Passed           : True
```

Stable ledger ownership reduced repeated raw entry signals from roughly 237 to a much smaller unique count.

ReplayInspector then exposed:

- bearish entries on bullish-bodied candles;
- bullish entries on bearish-bodied candles;
- repeated apparent setups inside one unresolved pullback;
- wrong-side decision protection;
- confusing success reasons stored as rejection reasons.

This led to:

- a separate EntryValidator;
- protection-side sanity checking;
- preservation of causal replay assertions.

## Immediate anomaly Codex must solve first

Latest output:

```text
Progress output contains ENTRY_READY states.
Some candidates are BLOCKED_WRONG_CANDLE_DIRECTION.
ReplayInspector reports Unique Entries: 0.
Test result: PASS.
```

Zero entries is not automatically success.

Codex must determine whether:

1. all candidates were correctly rejected;
2. validator-approved entries are not reaching the canonical entry state;
3. continuation_state["entry_ready"] is mutated before the Director snapshot;
4. final_entry_bos is not mapped into the Director entry section;
5. SignalLedger no longer recognizes the new validation state;
6. setup deduplication collapses unrelated entries;
7. field names disagree between EntryValidator, pipeline_runner, Director, SignalLedger, and ReplayInspector.

Trace one ENTRY_READY candle through:

```text
ContinuationEngine
→ EntryValidator
→ final_entry_bos
→ Director entry section
→ SignalLedger.record_snapshot
→ SignalLedger._resolve_event_type
→ ReplayInspector.entry_records
```

Add a diagnostic table with:

```text
as_of_index
trend
continuation_state
continuation_entry_ready
continuation_entry_index
entry_validation_state
entry_validation_allowed
canonical_entry_available
canonical_entry_index
director_entry_ready
ledger_event_type
setup_id
```

The first disappearing allowed candidate must fail the test with a precise message.

Do not make SignalLedger read raw continuation candidates. It must read one canonical final entry.

## Canonical final entry contract

Codex should standardize one object similar to:

```python
{
    "available": bool,
    "state": str,
    "setup_id": str | None,
    "direction": "BULLISH" | "BEARISH" | None,
    "index": int | None,
    "price": float | None,
    "type": str | None,
    "trigger_index": int | None,
    "trigger_level": float | None,
    "quality": str | None,
    "score": float | None,
    "validation": dict,
    "causal": bool,
    "current_candle_only": bool,
    "reason": list[str],
}
```

Invariants:

- available only after EntryValidator allows it;
- index equals current as_of_index;
- price equals current candle close;
- causal is true;
- no future proof is present;
- one canonical entry object only;
- downstream systems consume this object rather than recomputing it.

## Stable setup lifecycle

A setup ID must not change merely because a later descriptive pullback boundary changes.

Create a Director-owned setup lifecycle with:

```text
setup_id
symbol
timeframe
direction
origin_trend_bos
initial_pullback_start
current_pullback_end
status
created_at_index
updated_at_index
confirmed_at_index
invalidated_at_index
consumed_at_index
reentry_count
```

Recommended states:

```text
DETECTED
DEVELOPING
WAITING_FOR_TRIGGER
CANDIDATE_READY
ENTRY_VALIDATED
CONSUMED
INVALIDATED
EXPIRED
REENTRY_PENDING
CLOSED
```

Rules:

- identity created once;
- boundaries may update without changing identity;
- compression does not create repeated new setups;
- after execution mark setup CONSUMED;
- one first entry per setup;
- one re-entry maximum when explicitly armed.

## Protection architecture

Keep these separate:

1. decision protection;
2. setup invalidation;
3. post-entry trailing protection.

Codex must verify:

- bullish decision protection is below the anchor/current price;
- bearish decision protection is above it;
- protection existed before the decision;
- availability timestamps are causal;
- setup invalidation is the defended pullback extreme;
- trailing uses meaningful continuation HL/LH structure only.

## Repository audit instructions

Before major edits:

1. enumerate every file;
2. identify numbered, backup, duplicate, nested-project, and obsolete copies;
3. identify the single active import root;
4. map every engine's inputs, outputs, owner, and consumers;
5. identify duplicate owners of trend, phase, active pullback, setup ID, protection, invalidation, continuation BOS, final entry, permission, execution, and open-trade state;
6. produce the dependency and ownership report first.

There must be one active project root and one active core package.

## Required test suite

Unit tests:

```text
test_causal_data_view.py
test_structure_contracts.py
test_bos_body_close.py
test_retracement_lifecycle.py
test_setup_invalidation.py
test_continuation_engine.py
test_entry_validator.py
test_protection_side.py
test_setup_identity.py
test_setup_consumption.py
test_signal_ledger.py
test_position_sizing.py
test_trade_simulator.py
```

Integration tests:

```text
test_pipeline_foundation.py
test_pipeline_structure.py
test_pipeline_setup_entry.py
test_canonical_entry_flow.py
test_replay_runner.py
test_replay_mt5_data.py
test_replay_inspector.py
test_trade_simulation_replay.py
```

Mandatory scenarios:

1. valid bullish entry;
2. valid bearish entry;
3. trigger crossed by wrong-direction candle → validator blocks;
4. wick-only break → no BOS;
5. stale entry → hard block;
6. future-confirmed structure → causal failure;
7. wrong-side protection → rejected;
8. same setup across many candles → stable ID and one entry;
9. genuinely new setup → new ID;
10. one permitted re-entry, then no more.

## Trade simulator requirements

Do not claim profitability before canonical entries are trustworthy.

Build a sequential event-driven simulator with:

- current-close entry or configurable next-tick approximation;
- spread;
- commission;
- slippage;
- tick size;
- tick value;
- volume step;
- minimum volume;
- logical body-close stop;
- emergency broker stop;
- meaningful structure trailing;
- opposing BOS exit;
- optional partial close;
- one re-entry;
- session cutoff;
- kill conditions.

Record:

```text
trade_id
setup_id
symbol
timeframe
direction
entry_index
entry_price
actual_fill
trigger
logical_stop
emergency_stop
risk_percent
volume
spread
slippage
MFE
MAE
max_R
final_R
exit_index
exit_price
exit_reason
reentry_count
duration
```

## Analytics requirements

Report by:

- symbol;
- session;
- timeframe;
- trend phase;
- setup quality;
- validator grade;
- protection grade;
- pullback quality;
- stop style;
- trailing style;
- re-entry use.

Minimum metrics:

```text
trade count
win rate
profit factor
expectancy
average R
median R
max drawdown
MFE
MAE
average duration
stagnation rate
re-entry performance
```

Use train, validation, out-of-sample, and walk-forward testing. Do not optimize and evaluate on the same sample.

## Live safety requirements

No unattended live execution until:

1. replay passes;
2. canonical entries are manually reviewed;
3. simulator passes;
4. out-of-sample results are acceptable;
5. paper trading runs without contract violations;
6. broker specifications are verified;
7. restart and reconciliation are tested.

Required safeguards:

- duplicate-order prevention;
- max daily loss;
- max concurrent risk;
- max consecutive losses;
- spread guard;
- slippage guard;
- stale-price guard;
- MT5 disconnection handling;
- order reconciliation;
- restart recovery;
- emergency kill switch;
- audit logging.

## Rules Codex must follow

- Do not remove causal assertions to make tests pass.
- Do not bypass the Director.
- Do not let downstream engines recompute upstream truth.
- Do not merge protection roles.
- Do not silently change strategy rules.
- Do not hard-code one symbol's prices.
- Do not optimize only on GER40 or 400 candles.
- Do not claim profitability from a tiny sample.
- Do not activate live trading.
- Do not let machine learning rewrite production rules.
- Do not add many hard filters without measuring trade-frequency impact.
- Record rejected candidates and reasons.
- Do not label successful entry reasons as rejection reasons.
- Remove ambiguity from numbered duplicate runtime files.
- Do not change setup identity because descriptive boundaries update.

## Required Codex deliverables

1. Repository audit report.
2. Dependency and ownership map.
3. Issue register with severity, file, class, method, cause, consequence, and fix.
4. Architecture decision record.
5. Complete corrected files.
6. Automated unit and integration tests.
7. Command log and test results.
8. Replay audit with candidate, allowed, blocked, ledger, stale, and causal counts.
9. Entry-review dataset.
10. Event-driven backtest report.
11. Production-readiness report with completed, partial, blocked, and unsafe items.

## Completion criteria

Architecture:

- one active root;
- one Director;
- one setup owner;
- one canonical entry;
- one execution decision owner;
- one trade lifecycle owner.

Causality:

- zero future leakage;
- zero stale entries;
- zero post-entry proof in entry decisions;
- deterministic candle-by-candle replay.

Entry behavior:

- entry index equals current candle;
- entry price equals current close;
- correct direction;
- correct trigger;
- validator state visible;
- approved candidates reach ledger;
- blocked candidates do not;
- no unexplained zero-entry result;
- no duplicate consumed-setup entries.

Replay target:

```text
Pipeline Errors         : 0
Integrity Failures      : 0
Non-Causal Events       : 0
Stale Entries           : 0
Post-Entry Proof Leaks  : 0
Replay Passed           : True
```

Human strategy match:

- manually review representative entries;
- compare system decision against Steve's decision;
- record agreement and reason.

## Priority order

```text
1. Repository and import cleanup
2. Dependency and ownership map
3. Contract stabilization
4. Zero-entry anomaly
5. Canonical entry pipeline
6. Stable setup identity and consumption
7. Protection correctness
8. Replay and inspector completeness
9. Manual behavior validation
10. Trade simulator
11. Trade management
12. Analytics
13. Multi-symbol and session testing
14. Bounded optimization
15. Paper trading
16. Controlled live deployment
```

## Immediate first instruction to Codex

Reproduce the latest zero-entry anomaly using the active source files. Trace one ENTRY_READY candle end to end and produce a root-cause report before changing logic. Then implement the smallest correct architectural fix so validator-approved current entries appear exactly once in the canonical ledger, validator-blocked candidates remain auditable but are not allowed, and every replay causality assertion still passes.

The finished system is not expected to win every trade. It is expected to implement Steve's manual strategy faithfully, avoid hindsight, explain every decision, measure real performance, and operate safely.
