# SmartStructureBot Bible

> Single source of truth for strategy, architecture, ownership, causality,
> replay, management, configuration, evidence, tests and terminology.

## 0. Document control

| Field | Value |
|---|---|
| Bible version | 1.2.0 |
| Baseline code | `SMARTSTRUCTUREBOT_SIMULATOR_BASELINE_V0_9` |
| Current delivery | Phase S1B realistic paper account and execution laboratory |
| Active strategy model | `EXPERT_SPEC_V1` |
| Active management model | `STEVE_STOP_MANAGEMENT_V3` |
| Runtime posture | Research/report/paper-signal only |
| Live capital | Prohibited |
| Last reconciled | 2026-08-03 |
| Authoritative strategy owner | Steve |
| Canonical state owner | `SystemStateDirector` |

### 0.1 Status vocabulary

| Status | Meaning |
|---|---|
| `IMPLEMENTED_VERIFIED` | Present in the active path and protected by tests/evidence. |
| `IMPLEMENTED_PARTIAL` | Present, but Phase 11 evidence or behavior remains incomplete. |
| `PHASE11_REQUIRED` | Authoritative required behavior that is not implemented yet. |
| `LEGACY_COMPATIBILITY` | Retained for regression/compatibility; not active under `EXPERT_SPEC_V1`. |
| `RESEARCH_ONLY` | May calculate or report, but may not place an order. |
| `PROHIBITED` | Must not exist in the current runtime. |

### 0.2 Mandatory change order

Every strategy or behavioral change must follow this order:

1. Update this Bible.
2. Update code owned by the engine named in this Bible.
3. Generate causal replay evidence.
4. Add or update tests.

No code-only strategy rule is authoritative. No replay label may invent a rule
that is absent from this Bible. No green test may weaken causality merely to
make an output pass.

### 0.3 Change record

Every future Bible edit must add:

- change identifier and date;
- Steve's rule or approved interpretation;
- affected owner and state contracts;
- previous behavior;
- new behavior;
- replay evidence identifiers;
- test identifiers;
- migration or compatibility notes.

#### CHG-2026-07-30-FX20

- Request: generate 20 new real currency-pair chart examples.
- Strategy rule change: none.
- Owners affected: replay/evidence tooling only.
- Code action: add a currency-pair evidence runner using the unchanged
  `EXPERT_SPEC_V1` pipeline and `STEVE_STOP_MANAGEMENT_V3`.
- Evidence requirement: 20 unique closed-candle FX entries, causal entry
  labels, separated post-entry review, CSV/JSON/HTML and no order calls.
- Tests: existing causal/runtime suite remains authoritative; the evidence
  audit must prove 20 rows, unique keys, zero future-data use and zero orders.

#### CHG-2026-07-31-FINAL-FIDELITY

- Steve's rule: M5 remains the sole parent setup timeframe while M1 becomes a
  synchronized child execution layer that may enter earlier, with M5 retained
  as the first-valid fallback.
- Fibonacci correction: `STEVE_REMAINING_IMPULSE_PERCENT_V2` replaces the
  former user-facing orientation. Zero percent is the full-structure retest
  origin; 100 percent is the impulse extreme where retracement begins.
- Owners affected: `FibonacciRetracementEngine`,
  `SynchronizedM1ReplayCoordinator`, `M1ChildStructureEngine`,
  `FirstValidEntryArbiter`, `TargetLifecycleEngine`,
  `ProfitProtectionEngine`, `ProfitCaptureMetricsEngine`, Director evidence
  publication and replay tooling.
- Previous behavior: M1 was evaluated as a late fallback after an already
  qualified M5 pullback and temporal origin matching was sufficient.
- New behavior: M1 is armed when the M5 retracement is born, becomes active
  when meaningful, and must match every parent ownership field. Merged
  closed-candle chronology decides whether M1 or M5 owns the entry.
- Compatibility: legacy `depth` fields remain temporarily published as aliases
  of `retracement_depth_ratio`; legacy Fibonacci model assertions are
  `OBSOLETE_CONFLICTING`.
- Evidence IDs: `FINAL_FIDELITY_SYNC_40`; tables
  `m1_advantage_audit`, `m1_rejection_audit`, `target_lifecycle_audit`,
  `profit_capture_audit`, `reentry_audit`, and `hard_soft_grade_audit`.
- Tests: `test_final_fidelity_contract.py` plus all tests classified
  `ACTIVE_AUTHORITATIVE` or `LEGACY_REGRESSION`.

#### CHG-2026-08-01-PHASE-S1

- Request: build a deterministic candle-by-candle visual debugger without
  changing strategy behavior or enabling orders.

#### CHG-2026-08-03-PHASE-S1B-PAPER-ACCOUNT

- Steve's rule: preserve every accepted Phase S1 strategy event and add a
  separate realistic ZAR paper-execution authority around those events.
- Owners affected: `PaperExecutionReplayService`, `PaperBroker`, account,
  contract, conversion, spread, slippage, commission, swap, fill, sizing,
  margin, intrabar, ledger, analytics, exports, data library and simulator UI.
- Previous behavior: canonical signals and structure-aware management were
  replayed without complete bid/ask fills, account feasibility or monetary
  accounting.
- New behavior: Director actions are unchanged; the paper authority may fill,
  reject or queue them and must disclose all economic assumptions. R500,
  R1,000, R2,500, R5,000 and positive custom ZAR balances are supported.
- Evidence IDs: `PHASE_S1B_ACCEPTANCE_20`,
  `PHASE_S1B_CAPITAL_COMPARISON_500_1000_5000`, financial ledger exports and
  the investor-facing realistic-paper review.
- Tests: the exact 50-contract
  `test_phase_s1b_financial_contract.py`, unchanged 37 Phase S1 contracts and
  unchanged inherited 291 strategy contracts.
- Compatibility: simulator version advances; baseline strategy version,
  strategy event hash, Director ownership and all original datasets remain
  unchanged. `orders_enabled` remains false.
- Strategy rule change: none. The frozen baseline remains authoritative.
- New owners: `ReplaySession`, `CanonicalPipelineAdapter`,
  `ObservabilityService`, `ExportService` and the browser presentation layer.
- Replay invariant: each event is calculated from the M1/M5 candles closed at
  or before its event time. Event zero is seeded from the final candles already
  closed at the requested start time. The unrevealed suffix is unavailable.
- Evidence: 12 curated frozen sessions, 673 immutable events, event/sequence/
  review exports, investor and losing-example manifests, and performance audit.
- Tests: the 37 tests in `simulator.tests.test_phase_s1_contract` plus the
  unchanged baseline suite. Order calls remain zero.

### 0.4 Conflict resolution

Priority is:

1. Steve's latest explicit clarification;
2. this Bible;
3. canonical Director contracts;
4. active `EXPERT_SPEC_V1` code;
5. replay evidence;
6. tests;
7. legacy code and historical reports.

If code and Bible disagree, work stops until the Bible is updated or code is
repaired. Historical charts never override a later explicit Steve correction.

## 1. Strategy identity

SmartStructureBot trades dominant-trend continuation after an opposing
retracement has failed.

Core sequence:

```text
Closed market data
→ causal HTF direction
→ dominant impulse
→ protected structure
→ opposing retracement
→ retracement qualification
→ failure trigger
→ same-direction body-close BOS
→ entry at BOS candle close
→ logical and emergency protection
→ objective and runner management
→ opposing meaningful BOS or logical invalidation exit
```

For a bullish trade:

- HTF trend is bullish;
- price forms a bearish retracement;
- a relevant low/LL and failure-trigger high are identified;
- a bullish candle body closes above the active trigger;
- entry is at that closed candle's close;
- initial logical protection belongs to the final important pre-BOS LOW/LL.

For a bearish trade, every rule mirrors:

- HTF trend is bearish;
- retracement is bullish;
- protection belongs to the final important pre-BOS HIGH/HH;
- a bearish candle body closes below the active trigger;
- entry is at that candle's close.

The strategy is not a generic breakout system, reversal system, Fibonacci-only
system, score-only system or indicator-cross system.

## 2. Non-negotiable causal laws

1. Decisions use fully closed candles only.
2. The forming candle is excluded at source.
3. Every decision is evaluated at `as_of_index`.
4. Data after `as_of_index` is inaccessible to decision engines.
5. A fixed-sensitivity swing becomes visible only after its right-side
   confirmation candles have closed.
6. Confirmed history must not repaint when later candles are appended.
7. HTF context uses only HTF candles closed by the decision candle close time.
8. BOS requires a candle-body close beyond structure; a wick is not BOS.
9. Entry occurs at the current BOS candle close, never on an old candle.
10. Initial stop selection cannot use a post-entry candle.
11. A wick through logical protection survives; invalidation needs the
    applicable body-close contract.
12. Scores and grades cannot compensate for hard structural invalidity.
13. Setup identity cannot be recreated merely because descriptive boundaries
    moved.
14. One parent setup may publish one first entry and at most one re-entry.
15. Protection may tighten or hold; it may never loosen.
16. No runtime order API is imported or called before the separately approved
    execution phase.

## 3. Runtime architecture

### 3.1 Active application flow

```text
main.py
→ load_runtime_config
→ connect_mt5 / get_market_data
→ validate_closed_candles
→ build causal H1/M30/M15 context
→ run_pipeline(strategy_model=EXPERT_SPEC_V1)
→ run_expert_strategy
→ SystemStateDirector snapshot
→ SignalLedger / ReplayInspector / research or paper-signal report
```

`main.py` is a thin launcher. It may load configuration, connect, request and
validate data, call the canonical pipeline and consume canonical outputs. It
must not independently reconstruct trend, phase, pullback, protection,
continuation or entry.

### 3.2 Active versus legacy path

`PipelineOptions.strategy_model == EXPERT_SPEC_V1` immediately delegates to
`run_expert_strategy`. This is the active strategy behavior.

`LEGACY_PHASE6` retains the historical modular chain for regression and
contract compatibility. It is not allowed to become a second active source of
strategy truth.

### 3.3 Engine inventory

| Engine/module | Owner responsibility | Active status |
|---|---|---|
| `application_runtime` | Thin orchestration, configuration, data audit, pipeline/replay invocation and reporting. | `IMPLEMENTED_VERIFIED` |
| `mt5_connector` | MT5 connection, safe suffix resolution, closed-candle acquisition and data audit. | `IMPLEMENTED_VERIFIED` |
| `runtime_config` | Safe-mode and parameter validation. | `IMPLEMENTED_VERIFIED` |
| `pipeline_runner` | One canonical entry point and active/legacy model dispatch. | `IMPLEMENTED_VERIFIED` |
| `system_director` | Causal data view, root ownership and canonical snapshot. | `IMPLEMENTED_VERIFIED` |
| `expert_strategy` | Active causal HTF, swing, retracement, entry and management orchestration. | `IMPLEMENTED_VERIFIED` |
| `htf_context` / expert HTF functions | H1/M30/M15 direction, strength, alignment and policy comparison. | `IMPLEMENTED_VERIFIED` |
| `market_structure` | Major, ATR-wave, flow and fixed-delay swing detection. | Active inside legacy; fixed-delay expert swings active in `expert_strategy`. |
| `structure_hierarchy` | Structural hierarchy enrichment. | `LEGACY_COMPATIBILITY` |
| `structure_strength` | Structural significance scoring. | `LEGACY_COMPATIBILITY` |
| `bos_detector` | Close-only BOS detection. | `LEGACY_COMPATIBILITY`; expert close-BOS logic active separately. |
| `bos_importance` | BOS role and quality classification. | `LEGACY_COMPATIBILITY` |
| `market_state` | Compressed structure trend state. | `LEGACY_COMPATIBILITY` |
| `phase_engine` | Expansion, pullback, transition and unclear-phase classification. | `LEGACY_COMPATIBILITY` |
| `master_structure_state` | Descriptive aggregate market structure. | `LEGACY_COMPATIBILITY` |
| `market_control_engine` | Trend-control and pullback-control description. | `LEGACY_COMPATIBILITY` |
| `transition_engine` | Trend-stable, warning, watch, recovered and confirmed transition state. | Root contract remains canonical; legacy analyzer retained. |
| `structure_validator` | Hard structural validity and risk modifier root. | `IMPLEMENTED_VERIFIED` |
| `protected_structure` | Dominant decision protection and setup invalidation ownership. | `IMPLEMENTED_VERIFIED` |
| `impulse_cycle` | Same-cycle origin, impulse and decision-protection contract. | `IMPLEMENTED_VERIFIED` |
| `qualified_retracement` | Canonical retracement origin, qualification, trigger and chronology in legacy path. | `IMPLEMENTED_VERIFIED` contracts; expert state machine active. |
| `fibonacci_contract` | Directional impulse anchors, depth, zones and same-parent reassessment. | `IMPLEMENTED_VERIFIED` |
| `semantic_swing_hierarchy` | Meaning-based swing roles, separate from raw fractals. | `IMPLEMENTED_VERIFIED` |
| `adaptive_decision` | A+/A/B/C/Invalid grading and risk adjustment. | `IMPLEMENTED_VERIFIED` |
| `continuation_engine` | Structural continuation candidate ownership. | `LEGACY_COMPATIBILITY`; expert entry state machine owns active candidate. |
| `entry_validator` | Executable current-candle validation. | `LEGACY_COMPATIBILITY`; equivalent expert checks active. |
| `entry_freshness` | Causal freshness classification; advisory only. | `IMPLEMENTED_VERIFIED` |
| `setup_lifecycle` | Stable setup identity, terminal states and one-re-entry ceiling. | `IMPLEMENTED_VERIFIED` |
| `steve_trade_management` | Stop, emergency protection, objective selection, trail, exit and re-entry. | `IMPLEMENTED_PARTIAL` pending Phase 11 management engines. |
| `m1_fallback` | Gate and validate M1 entry inside an active M5 parent. | `IMPLEMENTED_PARTIAL`; synchronized real M1 replay is absent. |
| `evidence_contract` | Normalized canonical decision-time evidence. | `IMPLEMENTED_VERIFIED` |
| `signal_ledger` | Append-only immutable replay event ledger. | `IMPLEMENTED_VERIFIED` |
| `replay_runner` | Candle-by-candle canonical pipeline replay. | `IMPLEMENTED_VERIFIED` for one timeframe. |
| `replay_inspector` | Tabular canonical entry inspection. | `IMPLEMENTED_VERIFIED` |
| `management_evidence` | Canonical chart-management contract. | `RESEARCH_ONLY` |
| `manual_review` | Validate Steve review labels; never alter strategy automatically. | `RESEARCH_ONLY` |
| `strategy_fidelity` | Compare manual labels to bot decisions. | `RESEARCH_ONLY` |
| `protection_audit` | Reproduce invalidation causally. | `RESEARCH_ONLY` |
| `TPObjectiveEngine` | Score all valid market objectives. | `PHASE11_REQUIRED` |
| `ProgressiveProfitProtectionEngine` | Early progress through full structure trail. | `PHASE11_REQUIRED` |
| `ProfitCaptureAnalysisEngine` | MFE, MAE, R, capture and giveback analysis. | `PHASE11_REQUIRED` |
| `TargetLifecycleEngine` | Created/touched/accepted/rejected/extended/expired targets. | `PHASE11_REQUIRED` |
| `RunnerQualityEngine` | Continuation health, exhaustion and objective deterioration. | `PHASE11_REQUIRED` |
| `SynchronizedM1ReplayEngine` | Process every M1 candle while an M5 parent is active. | `PHASE11_REQUIRED` |
| `TradeStoryEngine` | Complete causal narrative and decision explanations. | `PHASE11_REQUIRED` |
| `TradeConvictionEngine` | Multi-domain grading without new soft hard-filters. | `PHASE11_REQUIRED` |
| `LearningMetricsEngine` | Aggregate capture, giveback, runner, target, M1/M5 and re-entry metrics. | `PHASE11_REQUIRED` |

## 4. Director ownership

Only the registered owner may define the meaning of its root. Other engines may
read it or publish descriptive copies, but cannot reinterpret it.

| Director root | Canonical owner |
|---|---|
| `meta` | `SystemStateDirector` |
| `market` | `MarketStateEngine` |
| `structure` | `StructurePipeline` |
| `control` | `MarketControlEngine` |
| `context` | `HTFContextEngine` |
| `transition` | `TransitionEngine` |
| `validation` | `StructureValidator` |
| `protection` | `ProtectedStructureEngine` |
| `impulse_cycle` | `ImpulseCycleEngine` |
| `setup_invalidation` | `ProtectedStructureEngine` |
| `trailing_protection` | `TrailingProtectionEngine` |
| `retracement` | `QualifiedRetracementEngine` |
| `setup` | `SetupLifecycleRegistry` |
| `entry` | `ContinuationEngine` |
| `entry_freshness` | `EntryFreshnessEngine` |
| `pre_entry_evidence` | `EntryEvidencePipeline` |
| `decision` | `DecisionPipeline` |
| `execution` | `ExecutionIntelligence` |
| `trade` | `TradeLifecycle` |
| `post_entry_proof` | `EntryProofEngine` |
| `guardian` | `TradeGuardian` |
| `outcome` | `TradeOutcomeRecorder` |
| `contract_health` | `SystemStateDirector` |

The active expert path must still publish these canonical roots. SignalLedger
and ReplayInspector consume roots; they may never scan descriptive nested
market fields for replacement truth.

## 5. Market data contract

Required OHLC fields are `time`, `open`, `high`, `low`, `close`; volume is
descriptive. Timestamps must be monotonic and unique. Duplicate timestamps,
missing gaps, stale feeds, disconnected MT5, insufficient history and forming
candles must be detected.

Timestamp rules:

- source timezone and broker timezone are explicit;
- decision alignment is performed in UTC;
- readable broker time may be exported;
- the last returned candle must be the last fully closed candle;
- safe broker suffix resolution may select an approved suffixed symbol, but
  cannot silently substitute an unrelated market.

## 6. HTF context

HTF frames are H1, M30 and M15. M5 is the primary execution frame; M1 is a
fallback execution frame inside an approved M5 parent.

Current policy options:

- `STRICT_2_OF_3_H1_M30_M15`;
- `PREFERRED_M30_M15`;
- `ONE_EXCEPTIONALLY_CLEAN_HTF`;
- `CONFLICT_RISK_REDUCTION`;
- active research configuration: `ADAPTIVE_STRUCTURE_POLICY`.

Rules:

1. Use close-only breaks of causally confirmed HTF swings.
2. Never use an incomplete HTF candle.
3. Local countertrend structure cannot overwrite approved HTF direction.
4. Two aligned frames may approve direction.
5. One exceptionally clean approved HTF may support a setup when configured.
6. Mixed usable context reduces risk; true conflict may block.
7. Policy alternatives must remain explicit and testable, not hidden.

States include `ALIGNED_BULLISH`, `ALIGNED_BEARISH`,
`STRONG_ALIGNED_BULLISH`, `STRONG_ALIGNED_BEARISH`,
`SINGLE_STRONG_SUPPORT_BULLISH`, `SINGLE_STRONG_SUPPORT_BEARISH`,
`MIXED_BUT_USABLE_BULLISH`, `MIXED_BUT_USABLE_BEARISH`, `CONFLICT`,
`INSUFFICIENT_HTF_DATA`, `HTF_FRAME_UNAVAILABLE` and
`STRICT_2_OF_3_CONTEXT_NOT_SUPPLIED`.

## 7. Swing and structure contract

### 7.1 Fixed-delay confirmation

With sensitivity `N`, a swing at candle `i` becomes available no earlier than
`i + N`. The first `N` candles on each side must satisfy the strict swing rule.
Appending future candles cannot alter a swing already confirmed at an earlier
`as_of_index`.

### 7.2 Structural classifications

Price-sequence labels are HH, HL, LH and LL. Semantic roles are:

- `MICRO_NOISE`;
- `INTERNAL_CONTINUATION_STRUCTURE`;
- `COUNTER_TREND_STRUCTURE`;
- `SETUP_TRIGGER_STRUCTURE`;
- `SETUP_INVALIDATION_STRUCTURE`;
- `DOMINANT_PROTECTED_STRUCTURE`;
- `TRAILING_STRUCTURE_CANDIDATE`;
- `PROVEN_TRAILING_STRUCTURE`.

A raw fractal is not automatically important, tradeable, protected or a trail.

### 7.3 BOS

Valid entry BOS:

- breaks the active failure-trigger level;
- uses candle close, not wick;
- candle body direction agrees with trade direction;
- occurs on the current decision candle;
- uses a trigger available by the decision close;
- belongs to the current parent retracement;
- cannot be stale or inherited from a previous setup.

## 8. Impulse and Fibonacci

For bullish structure:

- Fib 0% is the same-cycle impulse-origin low, dominant protected support and
  full structural retracement point;
- Fib 100% is the bullish impulse high where retracement begins.

For bearish structure:

- Fib 0% is the same-cycle impulse-origin high, dominant protected resistance
  and full structural retracement point;
- Fib 100% is the bearish impulse low where retracement begins.

The authoritative model is `STEVE_REMAINING_IMPULSE_PERCENT_V2`. Price retraces
from 100% toward 0%. Published levels are 100.0, 78.6, 61.8, 50.0, 38.2, 23.6
and 0.0 percent remaining impulse.

The engine publishes both raw ratios:

```text
retracement_depth_ratio = 1.0 - remaining_impulse_ratio

bullish remaining =
    (current_retracement_price - impulse_origin_price)
    / (impulse_extreme_price - impulse_origin_price)

bearish remaining =
    (impulse_origin_price - current_retracement_price)
    / (impulse_origin_price - impulse_extreme_price)
```

Raw values are never clamped for structural decisions. Display percentages may
be clamped only for presentation. A raw remaining ratio below zero means the
dominant origin was breached.

Published fields:

- `fib_zero_index`, `fib_zero_price`,
  `fib_zero_role=FULL_STRUCTURE_RETEST_ORIGIN`;
- `fib_hundred_index`, `fib_hundred_price`,
  `fib_hundred_role=RETRACEMENT_START_IMPULSE_EXTREME`;
- `remaining_impulse_ratio`, `remaining_impulse_percent`;
- `retracement_depth_ratio`, `retracement_depth_percent`;
- `lowest_remaining_percent_reached`;
- `deepest_retracement_percent_reached`.

Zones use remaining impulse percentage:

| Remaining impulse | State |
|---|---|
| `> 78.6%` | `ABOVE_78_6_REMAINING` |
| `61.8% to 78.6%` | `61_8_TO_78_6_REMAINING` |
| `38.2% to 61.8%` | `38_2_TO_61_8_REMAINING` |
| `23.6% to 38.2%` | `STEVE_PRIMARY_DEEP_SWEET_SPOT` |
| `0% to 23.6%` | `0_TO_23_6_REMAINING` |
| `< 0%` | `BELOW_0` and hard structural breach |

The manual sweet spot is 23.6% through 38.2% remaining, equivalent to 61.8%
through 76.4% retracement depth. Fibonacci grades relevance, timing,
conviction, risk and M1 activation priority. It never creates an entry, never
hard-rejects every setup outside the sweet spot and never overrides broken
dominant protection.

## 9. Retracement lifecycle

### 9.1 Current implemented lifecycle

```text
WAITING_FOR_PULLBACK_ORIGIN
→ DEVELOPING_PULLBACK
→ WAITING_FOR_CLOSE_BOS
→ CONSUMED
```

Supporting events:

- `PULLBACK_ORIGIN_CONFIRMED`;
- `PULLBACK_ORIGIN_MOVED_TO_NEW_EXTREME`;
- `COUNTER_SWING_CONFIRMED`;
- `WEAK_COUNTER_SWING_REQUIRES_SEQUENCE`;
- `FAILURE_TRIGGER_CONFIRMED`;
- `FAILURE_TRIGGER_UPDATED`;
- `WICK_ONLY_TRIGGER_SWEEP_NO_ENTRY`;
- `WRONG_DIRECTION_BODY_CLOSE_REJECTED`;
- `IMPULSE_ORIGIN_BROKEN_NO_ENTRY`;
- `CLOSE_BOS_ENTRY_AND_SETUP_CONSUMED`;
- `UNBROKEN_TREND_EXTREME_RESET_ORIGIN`.

The initial pullback start is stable. Current boundaries may evolve. Micro
structures inside one broader compression merge into the same setup.

### 9.2 Phase 11 evolving lifecycle

Authoritative target states are:

```text
BORN
→ GROWING
→ HEALTHY
→ DEEPENING
→ WEAKENING
→ FAILING
→ COMPLETED
→ CONSUMED
→ EXPIRED
```

This richer lifecycle is `PHASE11_REQUIRED`. The retracement survives first
trade failure when dominant trend, protected structure and parent setup remain
valid. It terminates on trend change, protected-structure failure, expiry or
second attempt failure.

## 10. Setup identity and ownership

A setup ID is anchored to symbol, timeframe, direction, origin BOS and initial
pullback start. Its identity does not change when current pullback boundaries
evolve.

Current setup states:

```text
DETECTED
→ DEVELOPING
→ WAITING_FOR_TRIGGER
→ CANDIDATE_READY
→ ENTRY_VALIDATED
→ CONSUMED
```

Additional states are `INVALIDATED`, `EXPIRED`, `REENTRY_PENDING` and `CLOSED`.

Terminal states are `CONSUMED`, `INVALIDATED`, `EXPIRED`, `CLOSED`.

A genuinely new setup requires:

- direction changed; or
- prior setup is terminal and the new pullback starts after its terminal
  index; or
- a meaningful new directional impulse/BOS occurs after the old compression.

A newly relabeled historical BOS cannot reopen or clone an old setup.

## 11. Entry decision tree

```text
IF closed-candle data invalid:
    block
ELSE build causal HTF context

IF approved direction is neutral/conflicting:
    HARD_BLOCK_HTF_NEUTRAL
ELSE detect only causally available swings
     identify same-direction impulse and retracement origin
     evolve counter structure and failure trigger

IF impulse origin is broken at/through Fib 1:
    invalidate cycle
ELSE IF current candle only wicks through trigger:
    wait; keep trigger active
ELSE IF close breaks trigger but candle body direction is wrong:
    reject current candle
ELSE IF correct-direction body closes beyond trigger:
    select last important pre-BOS stop owner
    validate stop is on protective side
    grade valid setup
    publish canonical entry at current close
    consume first-entry capability
```

Entry states include `WAITING_FOR_QUALIFIED_RETRACEMENT`,
`WAITING_FOR_CLOSE_BOS`, `ENTRY_VALIDATED`, `RE_ENTRY_VALIDATED`,
`NO_ACTIVE_SETUP_AFTER_CONSUMPTION`, `BLOCKED_HTF_NEUTRAL`,
`HARD_BLOCK_INVALID_LOGICAL_STOP_SIDE`, `BLOCKED_MANAGEMENT_LIFECYCLE`
and `NO_TRADE_NEUTRAL_HTF`.

## 12. Hard blocks versus grading

Hard blocks:

- future-data or incomplete-candle use;
- no approved direction;
- structurally invalid or stale/foreign trigger;
- wick-only BOS;
- wrong-direction BOS candle;
- setup already consumed outside the one re-entry allowance;
- impulse origin/protected structure invalidated;
- missing or incoherent setup identity/chronology;
- logical stop not on the protective side of entry;
- second failure for the same parent.

Soft factors:

- shallow retracement;
- extreme but still protected retracement;
- weaker HTF support;
- lower BOS displacement;
- reduced structure clarity;
- session quality;
- target/continuation quality once Phase 11 is implemented.

Grades and maximum risk modifiers:

| Grade | Risk modifier |
|---|---:|
| `A_PLUS` | 1.00 |
| `A` | 0.85 |
| `B` | 0.60 |
| `C` | 0.30 |
| `INVALID` | 0.00 |

Soft weakness lowers grade/risk. It must not silently become a universal
no-trade filter.

## 13. Initial stop and emergency stop

### 13.1 Stop owner

Buy: last important pre-entry LOW/LL inside the qualified retracement.

Sell: last important pre-entry HIGH/HH inside the qualified retracement.

Preferred owner is the final opposing reaction between failure trigger and
entry BOS. The entry BOS itself may causally prove this reaction extreme at
the entry close. No future right-side candle is needed for that specific
entry-proved reaction.

If no opposing reaction exists, use the latest fixed-delay confirmed
protective swing inside the same retracement.

### 13.2 Price boundary

M1:

- buy uses lower body edge;
- sell uses upper body edge;
- a wick alone does not invalidate.

M5:

- use relevant structure body edge;
- apply configurable ATR tolerance outside that edge;
- wick through survives;
- small marginal close within tolerance survives/warns;
- meaningful body close beyond boundary invalidates.

The phrase “M1 candle close stop” is deprecated. Canonical terminology is
`BODY_EDGE`; any remaining descriptive string using “candle close” must be
renamed during Phase 11 without changing price behavior.

### 13.3 Emergency stop

Emergency broker stop is wider than logical protection and exists only for
catastrophic/software risk. It is research-calculated and not sent. It must
never be reported as the normal strategy-loss level.

## 14. Target and objective contract

### 14.1 Current Phase 10.1 behavior

Default TP1 is `PREVIOUS_IMPULSE_EXTREME`. It is valid only when favorable
relative to entry. A wick touch is enough to mark TP1 reached. TP1 touch does
not automatically force break-even.

Other supported research models are `PREVIOUS_HTF_EXTREME`,
`NEAREST_MEANINGFUL_LIQUIDITY` and `CONFIGURABLE_R`.

### 14.2 Phase 11 TP Objective Engine

Status: `PHASE11_REQUIRED`.

Candidate objectives:

1. previous impulse extreme;
2. nearest meaningful external liquidity;
3. previous HTF objective;
4. measured continuation objective;
5. research R objective.

For every candidate calculate:

- distance;
- R:R;
- continuation room;
- available structure;
- liquidity quality;
- continuation probability.

Select the highest-quality valid objective. Never fabricate one. If none is
valid, publish `NO_VALID_OBJECTIVE`.

Required fields:

- objective owner;
- objective type and price;
- reason;
- confidence;
- quality;
- candidate comparison;
- `as_of_index`;
- `causal_valid`;
- `post_entry_data_used = false`.

### 14.3 Target lifecycle

Status: `PHASE11_REQUIRED`.

```text
TARGET_CREATED
→ TARGET_TOUCHED
→ TARGET_ACCEPTED or TARGET_REJECTED
→ TARGET_EXTENDED or TARGET_EXPIRED
```

Touch types are `WICK_TOUCH` and `BODY_CLOSE`. Touch is not the same as
acceptance. Acceptance/rejection must influence runner behavior.

## 15. Trade management

### 15.1 Current attempt lifecycle

```text
ATTEMPT_OPENED_RESEARCH_ONLY
→ ACTIVE
→ CLOSED_LOGICAL_INVALIDATION
or OPPOSING_MEANINGFUL_BOS_EXIT
```

Trail lifecycle:

```text
NO_TRAIL_AVAILABLE
→ TRAIL_CANDIDATE_UNPROVEN
→ TRAIL_PROVEN
→ TRAIL_MOVED or TRAIL_HELD
→ TRAIL_INVALIDATED
```

Buy trail:

- post-entry HL is a candidate;
- later meaningful bullish body-close BOS proves it;
- move below HL only when tighter.

Sell trail mirrors with LH and bearish BOS.

Raw fractals, wick breaks and micro opposing BOS do not move or exit the
runner.

### 15.2 Progressive profit protection

Status: `PHASE11_REQUIRED`.

```text
Initial Logical Protection
→ EARLY_PROGRESS
→ FIRST_LOCK
→ CONTINUATION_LOCK
→ FULL_STRUCTURE_TRAIL
→ Opposing BOS Exit
```

Early progress may activate after meaningful displacement, TP1, first
continuation BOS or large unrealized profit. It does not automatically equal
break-even.

For a long after TP1/proof, tighter protection uses `MAX(entry, proven HL)`.
For a short it uses `MIN(entry, proven LH)`. Protection never loosens.

### 15.3 Runner quality

Status: `PHASE11_REQUIRED`.

Runner health evaluates continuation strength, momentum, target acceptance,
expansion, compression, exhaustion and opposing structure. The runner remains
alive while continuation is healthy and exits only on objective deterioration,
logical invalidation, target policy or opposing meaningful BOS.

## 16. Re-entry

One re-entry maximum per parent setup.

Current implemented states:

- `NOT_ELIGIBLE_BEFORE_FIRST_FAILURE`;
- `FIRST_ENTRY_FAILED_RETRACEMENT_ACTIVE`;
- `ONE_REENTRY_CONSUMED`;
- `REENTRY_REJECTED_DOMINANT_PROTECTION_FAILED`;
- `CLOSED_AFTER_SECOND_FAILURE`.

Phase 11 authoritative flow:

```text
first attempt stops
→ verify dominant trend
→ verify protected structure
→ keep same parent retracement active
→ monitor every new closed candle
→ first meaningful same-direction continuation BOS
→ one re-entry
→ allowance becomes zero
```

No new major trend or brand-new retracement is required. Fresh evidence must
belong to the same active retracement; stale pre-failure structure is not
enough. Attempt two keeps the parent setup ID, receives a distinct event ID and
clones initial sizing logic. Second failure closes the parent.

## 17. M1 entry and transition

### 17.1 Gate

M1 is a child execution layer of the active M5 parent and may activate only
when:

- valid HTF/M5 dominant direction exists;
- an M5 impulse cycle is active;
- a meaningful counter-trend move has begun and has an active retracement ID;
- dominant protection remains valid;
- synchronized closed M1 candles are available.

M1 requires internal counter structure, relevant M1 failure trigger,
same-direction correct-body close BOS and current-candle entry.

Every M1 event must match `parent_m5_setup_id`,
`parent_m5_retracement_id`, `parent_impulse_cycle_id`, `parent_direction`,
`parent_protected_structure_id` and `parent_fib_anchor_version`. Any mismatch is
a hard block.

Monitoring states are `CLOSED`, `ARMED`, `ACTIVE`, `ENTRY_FOUND`,
`CONSUMED_BY_M1`, `CONSUMED_BY_M5`, `CANCELLED` and `EXPIRED`.

M1 logical protection is `M1_RELEVANT_SWING_BODY_EDGE`. For a bullish entry it
is the lower body edge of the final relevant pre-BOS M1 low; for bearish it is
the upper body edge of the final relevant pre-BOS M1 high. Wick-only breach
survives. Later M5 protection may replace M1 protection only when it tightens
or equals it.

### 17.2 Synchronized replay and first-valid ownership

`SynchronizedM1ReplayEngine` is required to:

```text
activate from M5 parent
→ process every M1 closed candle
→ permit M1 BOS entry
→ manage M1 protection
→ transition to proven M5 protection
→ continue management to exit
```

The coordinator processes one merged M1/M5 closed-candle timeline. M5
snapshots update only at M5 close times. M1 never sees an unfinished M5 candle;
M5 never sees a future M1 candle.

The authoritative state flow is:

- `M5_RETRACEMENT_BORN -> ARMED`;
- `M5_RETRACEMENT_MEANINGFUL -> ACTIVE`;
- `VALID_M1_BOS -> ENTRY_FOUND -> CONSUMED_BY_M1`;
- `VALID_M5_BOS_FIRST -> CONSUMED_BY_M5`;
- `DOMINANT_PROTECTION_BROKEN -> CANCELLED`.

The first valid entry consumes the parent opportunity. A later M5 entry cannot
duplicate an M1 first entry, and an earlier M5 fallback closes the M1
first-entry gate. Maximum one re-entry remains owned by the same M5 parent; the
first valid M1 or M5 re-entry owns it.

### 17.3 M1-to-M5 management

Management states are `M1_MANAGED`, `M5_CONTINUATION_PROVED`,
`M1_TO_M5_TRANSITIONED`, `TRANSITION_REJECTED_WOULD_LOOSEN` and
`M5_MANAGED_RUNNER`. M5 proof must be a closed continuation BOS, a post-entry
M5 HL/LH later proved by BOS, or acceptance beyond the first structural
objective. Transition records its proof candle and reason and never widens
protection.

Every M1 entry records the hypothetical M5 alternative, minutes and M1 bars
saved, price improvement, both stop distances, stop-reduction percentage and
RR improvement. Its result is classified as `M1_CLEAR_ADVANTAGE`,
`M1_SMALL_ADVANTAGE`, `M1_NO_ADVANTAGE`, `M1_FALSE_EARLY_ENTRY`,
`M1_SAVED_VALID_MOVE` or `M5_WAS_BETTER`.

At least 40 real synchronized examples are required, including 15 valid M1
entries, ten M5 fallbacks, five messy M1 rejections, five valid re-entries and
five dominant-protection failures with no re-entry. Synthetic examples do not
satisfy this gate.

## 18. Phase 11 profit capture analysis

Status: `PHASE11_REQUIRED`.

Every completed trade exports:

- entry and exit index/time/price;
- MFE and MAE;
- peak R and final R;
- giveback R;
- capture percentage;
- time to peak;
- time to exit;
- explanation of returned profit.

Formulas:

```text
initial_risk = abs(entry_price - initial_logical_stop)
favourable_move = direction_adjusted(MFE_price - entry_price)
adverse_move = direction_adjusted(entry_price - MAE_price)
peak_R = favourable_move / initial_risk
final_R = direction_adjusted(exit_price - entry_price) / initial_risk
giveback_R = max(0, peak_R - final_R)
capture_ratio = final_R / peak_R when peak_R > 0
giveback_ratio = giveback_R / peak_R when peak_R > 0
```

Classifications are `EXCELLENT_CAPTURE`, `GOOD_CAPTURE`,
`ACCEPTABLE_CAPTURE`, `POOR_CAPTURE`, `SEVERE_GIVEBACK`, `EARLY_EXIT`,
`OVER_MANAGED` and `UNDER_PROTECTED`.

## 19. Trade story

Status: `PHASE11_REQUIRED`.

Every trade story must be causal and reconstructible from ledger events:

```text
HTF direction
→ impulse and protection
→ retracement direction/depth/state
→ qualification and seller/buyer quality
→ failure trigger
→ BOS and entry
→ logical/emergency protection
→ objective creation and lifecycle
→ progressive protection
→ continuation/runner state
→ exit
→ peak/final/giveback R
→ capture classification and reason
```

Every state change records owner, index, price/level where relevant, reasons
and causal validity.

## 20. Replay contract

Replay calls the same pipeline as application runtime once per candle with a
persistent `PipelineRuntimeState`. It records the Director snapshot through
SignalLedger. Replay may continue on error only when explicitly configured.

Current ledger event types:

- `SETUP_ACTIVE`;
- `SETUP_CONFIRMED`;
- `ENTRY_SIGNAL`;
- `ENTRY_REJECTED`;
- `SETUP_INVALIDATED`;
- `NO_EVENT` (not stored).

Current strategy/management replay events:

- setup: `SETUP_DETECTED`, `BOUNDARY_OBSERVED`, `CANDIDATE_READY`,
  `SETUP_CONSUMED`, `SETUP_INVALIDATED`, `SETUP_CLOSED_NEW_IMPULSE`,
  `REENTRY_ARMED`;
- retracement: `PULLBACK_ORIGIN_CONFIRMED`,
  `PULLBACK_ORIGIN_MOVED_TO_NEW_EXTREME`, `COUNTER_SWING_CONFIRMED`,
  `FAILURE_TRIGGER_CONFIRMED`, `FAILURE_TRIGGER_UPDATED`,
  `WEAK_COUNTER_SWING_REQUIRES_SEQUENCE`,
  `UNBROKEN_TREND_EXTREME_RESET_ORIGIN`;
- entry: `WICK_ONLY_TRIGGER_SWEEP_NO_ENTRY`,
  `WRONG_DIRECTION_BODY_CLOSE_REJECTED`,
  `IMPULSE_ORIGIN_BROKEN_NO_ENTRY`,
  `CLOSE_BOS_ENTRY_AND_SETUP_CONSUMED`;
- management: `ATTEMPT_OPENED_RESEARCH_ONLY`,
  `WICK_THROUGH_LOGICAL_LEVEL_SURVIVED`, `TP1_TRIGGERED_RESEARCH`,
  `TRAIL_CANDIDATE_UNPROVEN`, `TRAIL_MOVED`, `TRAIL_HELD`,
  `FIRST_ENTRY_FAILED_RETRACEMENT_ACTIVE`,
  `FRESH_QUALIFIED_REENTRY_BOS`, `CLOSED_AFTER_SECOND_FAILURE`,
  `NEW_PARENT_SETUP_MANAGEMENT_RESET`.

Phase 11 adds objective, target lifecycle, progressive protection, runner
quality, capture, synchronized M1 and trade-story events. They must be
append-only and decision-time causal.

Replay integrity requires:

- future access blocked;
- zero future structures/strength/displacement/protection;
- no stale setup or continuation;
- current-only setup and entry;
- entry index equals decision index;
- entry price equals current close;
- close-only and causal flags true;
- canonical Director and ledger agreement.

## 21. Evidence contract

Pre-entry annotations may use only information available at entry. Post-entry
candles may be displayed in a visually separated outcome region and may not
alter pre-entry labels.

Phase 11 validation needs 30–50 new real examples covering winners, losers,
M1/M5 entries, re-entries/no re-entry, shallow/deep and sweet/outside-sweet
retracements, strong/weak trends, opposing-BOS exits and long runners.

Every chart shows:

- HTF trend and phase;
- dominant protected structure;
- impulse and Fib;
- qualified retracement and lifecycle;
- failure trigger and availability;
- entry;
- stop owner, logical stop and emergency stop;
- objective/target lifecycle;
- trail and runner state;
- exit;
- capture and giveback;
- trade story.

## 22. Learning metrics

Status: `PHASE11_REQUIRED`.

Per trade: entry, exit, MFE, MAE, peak/final R, capture/giveback, entry score,
management score, trend score, conviction grade, story and reason.

Portfolio research statistics:

- average giveback;
- average capture;
- average runner length;
- average trail delay;
- average TP distance;
- average re-entry success;
- average M1 advantage;
- average M5 advantage.

Metrics are descriptive research. They cannot automatically mutate strategy
parameters or enable self-learning/live behavior without a separately approved
governance contract.

## 23. Configurable parameters

### 23.1 Runtime

| Parameter | Default | Meaning |
|---|---:|---|
| `mode` | `RESEARCH` | Allowed: research, report, paper signal. |
| `symbol` | `GER40Cash#` | Requested broker symbol. |
| `timeframe` | `M5` | Primary decision timeframe. |
| `candles` | 400 | Requested closed candles. |
| `replay_start_index` | 100 | First replay decision candle. |
| `broker_timezone` | `UTC` | Explicit broker display timezone. |
| `source_timezone` | `UTC` | Source timestamp timezone. |
| `minimum_history` | 100 | Minimum accepted rows. |
| `stale_after_intervals` | 3 | Feed staleness ceiling. |
| `strict_missing_candles` | false | Whether gaps hard-fail. |
| `preferred_symbol_suffix` | `#` | Safe suffix preference. |
| `approved_symbols` | GOLD, GER40, US100, US30, OIL suffixed symbols | Symbol allowlist. |
| `htf_timeframes` | H1, M30, M15 | Context frames. |
| `strategy_model` | `EXPERT_SPEC_V1` | Active strategy path. |
| `engine_sensitivity` | 3 | Fixed swing confirmation delay. |
| `fibonacci_minimum_depth` | 0.236 | Relevant depth threshold. |
| `fibonacci_primary_minimum` | 0.382 | Sweet-spot lower edge. |
| `fibonacci_primary_maximum` | 0.618 | Sweet-spot upper edge. |
| `fibonacci_deep_maximum` | 0.786 | Deep-valid ceiling. |
| `htf_policy` | strict 2-of-3 | Context selection policy. |
| `htf_allow_single_strong` | false | Permit exceptional single frame. |
| `htf_candles` | 300 | HTF history. |
| `entry_timeframes` | M5, M1 fallback | Allowed entry paths. |
| `allowed_sessions` | London, New York, overlap | Research session labels. |
| `session_filter_mode` | `RESEARCH_COMPARISON` | Session behavior. |
| `management_profile` | `TWIN_POSITION_50_50` | Position-management plan. |
| `tp1_model` | `PREVIOUS_IMPULSE_EXTREME` | Current TP1 model. |
| `configurable_r_target` | 1.0 | Fixed-R research target. |
| `m5_logical_atr_tolerance` | 0.15 | Boundary tolerance. |
| `m5_min_body_atr` | 0.35 | Meaningful invalidating body. |
| `m5_min_close_distance_atr` | 0.10 | Meaningful distance beyond boundary. |
| `emergency_stop_atr_buffer` | 1.0 | Wider emergency buffer. |
| `trail_atr_tolerance` | 0.10 | Trail boundary tolerance. |
| `trail_min_body_atr` | 0.25 | Minimum trail-proof BOS body. |
| `m1_minimum_counter_bars` | 3 | Minimum M1 countertrend sequence length before a child BOS may qualify. |
| `m1_max_trigger_age` | 30 | Maximum closed M1 candles for a fresh child trigger. |
| `target_approach_fraction` | 0.10 | Fraction of target distance used to mark `APPROACHED`. |
| `profit_lock_trigger_r` | 1.0 | Closed-candle positive-R threshold for the first small lock. |
| `profit_lock_r` | 0.10 | R retained by the first configurable profit lock. |
| `tp1_partial_fraction` | 0.50 | Portion allowed to fill on a TP1 wick touch. |

### 23.2 Other policies

- `PipelineOptions`: `enable_debug`, `enable_health_report`,
  `enable_visualizer`, `enable_trade_memory`, `enable_trade_lifecycle`,
  `enforce_retracement_origin`, `retracement_qualification_model`,
  `decision_protection_policy`, `strategy_model`, `engine_sensitivity` and
  the four Fibonacci thresholds. Diagnostic flags do not alter strategy
  ownership.
- `FibonacciConfig`: 0.236, 0.382, 0.618, 0.786 thresholds.
- `EntryFreshnessPolicy`: ATR limit 3.0, mature distance 1.5 ATR,
  timeframe candle limits M1 30, M5 18, M15 12, M30 8, H1 6.
- `QualifiedRetracementPolicy`: hybrid model, importance 3.0, range 1.35,
  ATR displacement 0.85, strong displacement 1.35, persistence 2,
  overlap 0.8, display score 60, maximum origins 12.
- `DecisionProtectionPolicy`: origin-defending swing, minimum importance 3.0.
- `ReplayOptions`: start 50, optional end, stop on error by default,
  integrity failures recorded, progress off, interval 50.
- `SteveManagementConfig`: same stop/trail/target defaults as runtime.
  Its internal names include `m5_atr_tolerance` and
  `emergency_atr_buffer`; runtime maps these from
  `m5_logical_atr_tolerance` and `emergency_stop_atr_buffer`.
- `htf_research_policies`: explicit policy comparison list retained in
  configuration.

All constants are research defaults, not optimized claims.

## 24. Test expectations

The reconciled Bible-governed baseline contains 158 passing tests: the 154
Phase 10.1 behavioral tests plus four Bible integrity tests. Each name below is an
authoritative behavioral expectation.

### Canonical entry and data

- `test_legacy_entry_is_not_restored_by_phase4`
- `test_noise_candle_creates_no_ledger_entry`
- `test_blocked_candidate_is_published_non_ready`
- `test_stale_candidate_cannot_be_published`
- `test_future_suffix_does_not_change_entry`
- `test_phase4_pipeline_never_publishes_pre_origin_setup`
- `test_disconnected_mt5_is_rejected`
- `test_forming_candle_is_excluded_at_source`
- `test_forming_candle_in_payload_is_rejected`
- `test_server_wall_clock_is_converted_to_real_utc`
- `test_duplicate_timestamps_are_rejected`
- `test_missing_candle_gap_is_detected`
- `test_stale_data_is_rejected`
- `test_insufficient_history_is_rejected`
- `test_symbol_suffix_resolution_is_safe`
- `test_remaining_root_contracts_are_complete`
- `test_ledger_consumes_root_contract_values`
- `test_phase4_retracement_root_is_causal`
- `test_main_is_a_thin_launcher`
- `test_application_and_replay_share_pipeline_contract`
- `test_live_mode_is_rejected`

### HTF

- `test_m30_m15_preferred_agreement`
- `test_consensus_policy_requires_two_clean_frames`
- `test_one_clean_strong_htf_can_be_accepted`
- `test_future_htf_snapshot_cannot_retroactively_change_context`
- `test_local_countertrend_does_not_overwrite_htf`
- `test_pipeline_publishes_context_without_hardcoding_gate`

### Qualified retracement and ownership

- `test_01_micro_noise_only`
- `test_02_internal_break_without_maturity`
- `test_03_qualified_bearish_trend_retracement`
- `test_04_valid_bearish_entry`
- `test_05_valid_bullish_mirror`
- `test_06_protected_swing_violation`
- `test_07_wick_through_protection`
- `test_08_pre_origin_compression_is_ignored`
- `test_09_one_strong_counter_structure_can_qualify`
- `test_10_weak_first_bounce_stays_candidate`
- `test_11_identity_stability`
- `test_12_new_impulse_cycle_gets_new_identity`
- `test_13_prequalification_trigger_is_rejected`
- `test_14_future_confirmed_structure_is_unavailable`
- `test_15_compression_merging_creates_no_setup_ids`
- `test_gold_qualified_entry_reaches_canonical_director`
- `test_audit_export_and_ledger_use_canonical_snapshot`
- `test_first_qualification_is_immutable`
- `test_explicit_active_trigger_updates`
- `test_no_stale_trigger_from_previous_setup`
- `test_protection_body_close_and_wick_contract`
- `test_protection_belongs_to_origin_cycle`
- `test_score_range_contract_preserves_raw_score`
- `test_manual_review_import_validation`
- `test_impulse_cycle_contract_is_causal`
- `test_unrelated_old_cycle_protection_is_rejected`
- `test_origin_defending_protection_remains_stable`
- `test_newer_protection_requires_continuation_bos`
- `test_raw_latest_swing_cannot_replace_protection`
- `test_replacement_is_causal_and_current`
- `test_waiting_is_published_without_fallback`
- `test_freshness_is_deterministic`
- `test_trigger_refresh_must_belong_to_same_setup`
- `test_stale_classification_does_not_change_outcome`
- `test_htf_comparisons_are_advisory`
- `test_canonical_invalidation_reproduces`
- `test_full_history_contamination_is_rejected`
- `test_protection_belongs_to_current_cycle`
- `test_protection_roles_are_independent_roots`
- `test_entry_freshness_is_causal_and_advisory`
- `test_no_future_cycle_or_protection_data`
- `test_no_order_api_calls_exist_in_runtime`
- `test_missing_qualified_trigger_cannot_use_raw_fallback`

### Strategy fidelity and expert path

- `test_incomplete_review_is_never_scored_as_rejection`
- `test_complete_trade_requires_structural_labels`
- `test_disagreements_are_field_specific`
- `test_summary_needs_thirty_labels_for_readiness_inference`
- `test_freshness_exposes_trigger_confirmation_delay`
- `test_real_entry_publishes_fractal_and_locked_trigger_times`
- `test_swing_is_invisible_until_third_right_candle_closes`
- `test_confirmed_history_is_suffix_invariant_and_never_repaints`
- `test_htf_direction_uses_close_not_wick`
- `test_strict_two_of_three_and_no_single_strong_override`
- `test_incomplete_htf_candle_is_excluded`
- `test_bearish_close_bos_enters_at_close_with_retracement_stop`
- `test_wick_only_cross_does_not_enter_and_trigger_remains`
- `test_bullish_rules_are_an_exact_mirror`
- `test_raw_confirmed_swing_is_not_a_proven_trail`
- `test_neutral_htf_hard_blocks_every_entry`
- `test_replay_emits_one_canonical_entry_without_lookahead`

### Phase 10 full contract

- `test_01_fibonacci_anchors_are_directionally_correct`
- `test_02_fibonacci_depth_is_causal`
- `test_03_fibonacci_minimum_is_configurable`
- `test_04_sweet_spot_bos_receives_high_relevance`
- `test_05_shallow_strong_bos_remains_tradable`
- `test_06_deep_retracement_valid_while_protection_holds`
- `test_07_first_failure_leaves_parent_retracement_active`
- `test_08_early_failure_does_not_automatically_invalidate_parent`
- `test_09_fresh_relevant_bos_allows_one_reentry`
- `test_10_reentry_requires_no_new_major_setup`
- `test_11_reentry_same_parent_separate_event_id`
- `test_12_dominant_protection_failure_blocks_reentry`
- `test_13_second_failure_closes_parent`
- `test_14_soft_filters_reduce_risk_instead_of_blocking`
- `test_15_m1_fallback_requires_valid_m5_context`
- `test_16_m1_to_m5_transition_never_loosens`
- `test_17_raw_fractal_is_not_automatically_meaningful`
- `test_18_trail_requires_meaningful_continuation_proof`
- `test_19_tp1_touch_does_not_automatically_force_break_even`
- `test_20_opposing_meaningful_bos_exits`
- `test_21_wick_only_logical_stop_survives`
- `test_22_body_close_invalidation_exits`
- `test_23_no_future_data_changes_confirmed_history`
- `test_24_no_stale_trigger_entry`
- `test_25_no_order_apis`

### Phase 10.1 Steve feedback

- `test_sell_stop_uses_last_reaction_high_proved_by_entry_bos`
- `test_buy_stop_uses_last_reaction_low_proved_by_entry_bos`
- `test_no_opposing_reaction_uses_causal_confirmed_fallback`
- `test_previous_impulse_tp1_is_triggered_by_wick_touch`

### Stop, trail, re-entry and M1

- `test_initial_stop_uses_relevant_pre_bos_structure`
- `test_post_entry_candles_cannot_change_initial_stop`
- `test_broad_pullback_wick_is_rejected_when_irrelevant`
- `test_m1_wick_through_logical_level_survives`
- `test_m1_body_close_beyond_level_invalidates`
- `test_m5_wick_through_logical_level_survives`
- `test_m5_small_marginal_close_respects_tolerance`
- `test_m5_momentum_close_beyond_boundary_invalidates`
- `test_emergency_stop_is_separate_and_wider`
- `test_raw_post_entry_fractal_cannot_move_trail`
- `test_proven_continuation_hl_moves_buy_protection`
- `test_proven_continuation_lh_moves_sell_protection`
- `test_trailing_protection_never_loosens`
- `test_opposing_meaningful_bos_exits`
- `test_micro_opposing_bos_does_not_force_exit`
- `test_first_stop_alone_does_not_arm_reentry`
- `test_fresh_qualified_bos_arms_only_one_reentry`
- `test_second_failure_permanently_closes_parent_setup`
- `test_brand_new_parent_setup_resets_one_reentry_allowance`
- `test_m1_to_m5_management_transition_never_loosens`
- `test_qualified_m5_pullback_can_use_current_m1_close_bos`
- `test_chart_audit_uses_canonical_decision_time_contracts`
- `test_future_structures_are_rejected`
- `test_stale_trigger_is_rejected_by_chart_contract`
- `test_no_order_api_is_imported_or_called`
- `test_management_research_parameters_load_from_config`

### Setup chronology

- `test_micro_noise_does_not_create_consumable_setup`
- `test_canonical_candidate_setup_id_is_never_none`
- `test_evolving_pullback_keeps_one_setup_id`
- `test_consumption_blocks_same_setup_identity`
- `test_new_post_completion_pullback_gets_new_id`
- `test_reentry_is_hard_limited_to_one`
- `test_strategy_semantics_require_bos_before_pullback`
- `test_all_six_legacy_candidates_are_blocked_by_default`
- `test_fixture_preserves_accepted_six_entry_baseline`
- `test_micro_boundaries_merge_without_changing_identity`
- `test_post_consumption_cycle_requires_later_start`
- `test_new_impulse_terminates_old_compression`

### 24.1 Phase 11 required test expectations

Before Phase 11 completion, tests must prove:

1. objective candidates are causal, independently scored and never fabricated;
2. `NO_VALID_OBJECTIVE` is published when appropriate;
3. target touch distinguishes wick, body close, acceptance and rejection;
4. target acceptance/rejection changes runner behavior causally;
5. progressive protection moves through named states and never auto-forces BE;
6. long protection uses `MAX`, short uses `MIN`, and neither loosens;
7. runner ignores raw fractals and responds to measured deterioration;
8. every closed trade exports exact MFE/MAE/peak/final/giveback/capture values;
9. trade story can be rebuilt solely from ledger events;
10. same retracement survives first failure when dominant protection holds;
11. first meaningful continuation BOS may re-enter without a new major setup;
12. second failure terminates the parent;
13. synchronized M1 replay processes every eligible M1 closed candle;
14. M1 body-edge stop and M5 transition are causal and non-loosening;
15. at least 20 real M1 cases and 30–50 total new real cases are exported;
16. learning metrics reconcile exactly to underlying trade records;
17. no new soft factor becomes a universal hard block;
18. no order API is imported or called.

### 24.2 Bible integrity

- `test_bible_exists_and_contains_required_sections`
- `test_bible_names_every_core_module`
- `test_bible_names_every_test_expectation`
- `test_bible_documents_director_ownership_and_runtime_parameters`

## 25. Completion gates

Already verified:

- closed candle only;
- no future data;
- canonical Director, ledger and replay ownership;
- causal HTF direction;
- qualified retracement, Fib and BOS foundations;
- M5 entry;
- corrected initial and emergency stop;
- one-re-entry ceiling;
- current structural trail and opposing-BOS exit;
- research-only safety.

Not yet complete:

- intelligent multi-candidate objective selection;
- target lifecycle/acceptance;
- progressive protection states;
- continuation-quality runner;
- profit-capture and giveback analytics;
- synchronized real M1 replay and 20 examples;
- full evolving retracement states;
- trade story;
- broader conviction scoring;
- 30–50 Phase 11 replay package;
- learning metrics and aggregate reports.

Strategy development ends only when every Phase 11 gate has code, replay
evidence and passing tests.

## 26. Glossary

| Term | Definition |
|---|---|
| `as_of_index` | Last candle legally visible to a decision. |
| Active trigger | Latest same-parent failure trigger valid at decision time. |
| BOS | Candle-body close beyond relevant structure. |
| Body edge | Lower of open/close for bullish protection; upper for bearish. |
| Causal | Available without any candle or structure from the future. |
| CHOCH | Warning that control may be changing; not automatically an entry. |
| Closed candle | Candle whose interval has fully ended. |
| Counter structure | Structure moving against dominant trend inside retracement. |
| Decision protection | Dominant structure whose failure changes setup validity. |
| Emergency stop | Wider catastrophic broker protection, separate from logical stop. |
| Entry BOS | Same-direction close beyond active retracement-failure trigger. |
| Failure trigger | Structure whose break proves retracement failure. |
| Fib 0% | Same-cycle impulse origin and full-structure retest point. |
| Fib 100% | Impulse extreme where retracement begins. |
| Forming candle | Current incomplete candle; forbidden for decisions. |
| Giveback R | Peak R minus final R, floored at zero. |
| Hard block | Structural or causal invalidity that forbids entry. |
| HH/HL/LH/LL | Higher high, higher low, lower high, lower low. |
| HTF | Higher timeframe: H1, M30 or M15. |
| Impulse | Dominant directional move preceding retracement. |
| Logical stop | Strategy invalidation boundary evaluated by body-close rules. |
| M1 child entry | Synchronized lower-timeframe execution owned by an active M5 parent retracement. |
| MFE | Maximum favorable excursion after entry. |
| MAE | Maximum adverse excursion after entry. |
| Meaningful structure | Structure with contextual displacement/role, not merely a fractal. |
| Objective | Causally justified market target candidate. |
| Parent setup | Stable identity owning first entry, retracement and one re-entry. |
| Protected structure | Dominant structure whose validity protects the thesis. |
| Qualified retracement | Countertrend move with sufficient causal structure and valid protection. |
| Re-entry | One reserved second attempt in the same valid parent retracement. |
| Replay | Candle-by-candle use of the same canonical pipeline. |
| Repaint | Historical decision or structure changing after future candles arrive. |
| Risk modifier | Maximum sizing fraction resulting from grade/context. |
| Runner | Position portion managed for continuing structure rather than fixed TP. |
| Setup invalidation | Local structure that invalidates the entry setup. |
| SignalLedger | Append-only record of canonical decision-time events. |
| Soft factor | Quality weakness that grades risk but does not erase valid structure. |
| Swing confirmation | Fixed right-side delay or causal entry-BOS proof for final reaction stop. |
| Target acceptance | Market behavior showing trade beyond/around a touched objective is accepted. |
| Target rejection | Market behavior rejecting an objective after touch. |
| TP1 | First research objective; wick touch may count as reached. |
| Trail candidate | New HL/LH not yet proved by continuation BOS. |
| Proven trail | Candidate structure confirmed by meaningful same-direction BOS. |
| Wick survival | Wick crosses logical level but required body-close invalidation is absent. |

## 27. Superseded Phase 11 implementation order

1. Add Phase 11 test expectations and schemas to this Bible.
2. Implement TP Objective and Target Lifecycle contracts.
3. Implement Progressive Profit Protection and Runner Quality.
4. Implement Profit Capture and Learning Metrics.
5. Implement evolving Retracement Lifecycle and active re-entry refinements.
6. Implement synchronized M1 replay and body-edge terminology repair.
7. Implement Trade Story and Conviction outputs.
8. Generate 30–50 new real replay cases, including at least 20 M1 cases.
9. Reconcile every output to this Bible and run the complete suite.
10. Publish completion report or explicit remaining gaps.

No trade simulator, demo or live execution begins until this sequence is
reviewed and accepted.

Section 27 is retained only as historical migration context and is superseded
by Section 28.

## 28. Final fidelity implementation and readiness gate

Canonical implementation modules are `synchronized_m1_replay` and
`final_fidelity_management`; they extend the existing Director-owned research
pipeline and do not expose order execution.

Authoritative implementation order:

1. Publish the final-fidelity contract in this Bible.
2. Implement Steve Fibonacci V2 orientation and compatibility aliases.
3. Implement the synchronized M5-parent/M1-child coordinator and strict parent
   ownership.
4. Implement first-valid entry arbitration, M1 body-edge stop and no-widening
   M1-to-M5 transition.
5. Implement objective hierarchy/lifecycle, progressive protection, proven
   trailing, opposing-BOS ownership and capture metrics.
6. Preserve one re-entry per M5 parent across both entry timeframes.
7. Acquire causally aligned real M1 and M5 data for the mandated instruments.
8. Classify tests as `ACTIVE_AUTHORITATIVE`, `LEGACY_REGRESSION` or
   `OBSOLETE_CONFLICTING`; quarantine only true conflicts.
9. Generate at least 40 synchronized paired charts: 15 M1 entries, ten M5
   fallbacks, five messy M1 rejections, five valid re-entries and five
   dominant-protection failures with no re-entry.
10. Publish advantage, rejection, target, capture, re-entry and hard/soft
    audits plus full deterministic test output.

Simulator readiness requires:

- zero future-data or unfinished-candle decisions;
- zero duplicate M1/M5 first entries;
- zero unrelated M1 parent attachments;
- Steve Fibonacci V2 orientation;
- demonstrated real M1 entries and real M5 fallback cases;
- measured M1 stop advantage and false-entry rate;
- demonstrated no-widening M1-to-M5 transition;
- target wick-touch, close-through, acceptance and rejection states;
- measured giveback and capture;
- maximum one re-entry per M5 parent;
- replay reproducibility;
- all authoritative tests passing;
- live execution disabled.

The final verdict must report separately:

- `CODE_COMPLETE`;
- `STRATEGY_FIDELITY_PROVEN`;
- `RESEARCH_VALIDATED`;
- `SIMULATOR_READY`.

Passing tests alone proves none of the latter three.

### 28.1 Authoritative final-fidelity test expectations

- `test_fibonacci_zero_is_origin_and_hundred_is_extreme`
- `test_fibonacci_remaining_and_depth_are_complements`
- `test_raw_fibonacci_breach_is_not_hidden_by_display_clamp`
- `test_unrelated_m1_parent_is_hard_rejected`
- `test_synchronized_timeline_never_exposes_unfinished_candles`
- `test_valid_m1_entry_uses_relevant_swing_body_edge`
- `test_first_valid_m1_consumes_and_blocks_later_m5`
- `test_m5_fallback_closes_m1_gate_when_no_child_entry`
- `test_m1_to_m5_transition_never_widens`
- `test_one_reentry_per_parent_and_protection_failure_blocks`
- `test_target_wick_close_acceptance_and_rejection_are_distinct`
- `test_target_hierarchy_rejects_wrong_side_objective`
- `test_target_rejection_after_acceptance_exits_runner`
- `test_tp1_touch_does_not_force_break_even`
- `test_emergency_broker_stop_caps_catastrophic_wick`
- `test_profit_capture_metrics_are_exact`
- `test_replay_contract_is_reproducible_and_research_only`
# Final Fidelity Patch v1.0 — pre-simulator strategy freeze candidate

This section is authoritative for the last fidelity patch before the
candle-by-candle simulator.  It preserves every earlier causal, ownership,
entry, stop, target, and order-disable contract.  The implementation module is
`core/fidelity_patch.py` and the configuration version is
`FINAL_FIDELITY_PATCH_V1`.

## Ownership and decision tree

`M1EntryQualityEngine`, `ContinuationQualityEngine`,
`GivebackControlEngine`, and `ExhaustionEngine` are evidence-only engines.
They cannot mutate a setup, position, stop, or exit.  Their reports flow to
`TradeManagementCoordinator`, which commits exactly one management action for
each fully closed candle.  The Director remains the system-level authority and
order execution remains disabled.

```text
closed M1/M5 event
  -> structural ownership and hard validation
  -> M1EntryQualityEngine (soft score; never rewrites structural validity)
  -> first-valid-entry arbiter
  -> ContinuationQualityEngine
  -> GivebackControlEngine
  -> ExhaustionEngine
  -> TradeManagementCoordinator (one committed action)
  -> Director / SignalLedger / replay evidence
```

Hard invalidation always overrides soft quality.  Soft weakness normally
changes grade, research risk, observation status, or management aggression.  A
`C_M1` is structurally valid but defaults to `OBSERVE_ONLY`; this policy is
configurable and its full reason breakdown is retained.

## M1 entry quality states and score

The seven configured components total 100 points:

- counter-trend clarity: 20;
- trigger significance: 15;
- body-close BOS quality: 20;
- compression-to-expansion: 10;
- entry location and reward room: 15;
- timing/stop advantage over M5: 10;
- market cleanliness: 10.

Grades are `A_PLUS_M1` at 85+, `A_M1` at 70+, `B_M1` at 55+, and
`C_M1` below 55.  Behaviour labels are `CLEAN_EARLY_ENTRY`,
`ACCEPTABLE_EARLY_ENTRY`, `WEAK_BUT_VALID`, and
`RANDOM_OR_LOW_VALUE_M1`.  Every report includes component points, positive
reasons, negative reasons, trigger age, counter-move size, BOS body/ATR,
close distance beyond the trigger, overlap, time saved, stop reduction,
`as_of_index`, and causal validity.

Final M1 outcome events are `M1_VALID_NORMAL_LOSS`,
`M1_FALSE_EARLY_NO_M5_CONFIRMATION`, `M1_FALSE_MICRO_BOS`,
`M1_WRONG_CHILD_STRUCTURE`, `M1_PREMATURE_DURING_ACTIVE_COUNTER_MOVE`,
`M1_CLEAR_ADVANTAGE`, and `M1_SAVED_MOVE`.  A loss is never automatically
classified as a bad signal.

## Continuation lifecycle

`ContinuationQualityEngine` publishes component scores for progress,
displacement, pullback health, structural progression, objective acceptance,
and momentum deterioration.  Its states are `NOT_ESTABLISHED`,
`EARLY_EXPANSION`, `HEALTHY_CONTINUATION`, `STRONG_CONTINUATION`,
`WEAKENING_CONTINUATION`, `COMPRESSION`, `EXHAUSTION_WARNING`, and
`CONTINUATION_FAILED`.  Soft transitions require the configured number of
repeated confirmations; a body-close failure through owned protection may
fail immediately.

`TradeMaturityState` progresses through `INITIAL_RISK`, `EARLY_PROGRESS`,
`PROFIT_OPPORTUNITY`, `FIRST_OBJECTIVE_REACHED`,
`CONTINUATION_CONFIRMED`, `RUNNER_PHASE`, `EXHAUSTION_REVIEW`, and `EXITED`.
TP1 wick touch is distinct from body-close acceptance and never forces an
automatic break-even stop.

## Profit protection, giveback, and exhaustion

`ProfitProtectionEngine` recommendations are
`KEEP_INITIAL_PROTECTION`, `REDUCE_INITIAL_RISK`,
`PROTECT_BREAK_EVEN_REGION`, `LOCK_SMALL_PROFIT`,
`TRAIL_M1_PROVEN_STRUCTURE`, `TRAIL_M5_PROVEN_STRUCTURE`,
`PROTECT_TP1_ACCEPTANCE`, `AGGRESSIVE_EXHAUSTION_PROTECTION`, and `EXIT`.
Only causally proven post-entry structures may trail.  An M1-to-M5 transition
may tighten but never widen the current stop.

`GivebackControlEngine` calculates `current_R`, `peak_R`,
`unrealized_giveback_R = peak_R - current_R`, and capture ratio
`current_R / peak_R`.  States are `NORMAL_FLUCTUATION`,
`ACCEPTABLE_GIVEBACK`, `ELEVATED_GIVEBACK`,
`SEVERE_GIVEBACK_WARNING`, and `UNACCEPTABLE_GIVEBACK`.  Giveback alone does
not exit; maturity, continuation, volatility, objective state, and owned
protection provide context.

`ExhaustionEngine` combines failed extension, momentum decay, opposing
displacement, target reaction, compression, and profit-at-risk.  States are
`NO_EXHAUSTION`, `EARLY_WARNING`, `MEANINGFUL_WARNING`, `HIGH_EXHAUSTION`,
and `EXHAUSTION_CONFIRMED`.  Healthy continuation caps the exhaustion state
and records rejection reasons such as `NORMAL_PULLBACK`,
`PROTECTION_INTACT`, `NO_OPPOSING_DISPLACEMENT`, and
`CONTINUATION_STILL_HEALTHY`.

Management priority is: emergency stop; logical invalidation; meaningful
opposing BOS through owned protection; proven trail; healthy runner hold;
contextual exhaustion protection/exit; contextual giveback protection; hold.
Exactly one decision event is committed per candle.

## Identity and counting

One `parent_setup_id` owns one `TRADE_SEQUENCE`.  The sequence contains one
`FIRST_ENTRY` and, only after a qualified failure, at most one `RE_ENTRY`.
These are `EXECUTION_ATTEMPT` 1 and 2, not two market setups.  A first M1 entry
consumes the same slot that the later M5 signal would otherwise use; that M5
signal becomes confirmation and management evidence.  Reports must separately
publish setup count, trade-sequence count, execution-attempt count, and
re-entry count.

## Configurable parameters

All defaults live in `FidelityPatchConfig`; there are no engine-local strategy
thresholds.  Parameters include M1 component weights and grade/risk policy,
meaningful swing ATR (0.35 ATR), trigger staleness (30 candles), overlap
warning (0.65), BOS displacement (0.35 ATR), continuation weights and state
thresholds, hysteresis confirmations (2), early progress/protection R,
small-profit lock R, elevated/severe giveback thresholds, unacceptable capture
ratio, exhaustion thresholds, partial-exit research toggle, and runner-exit
policy.  Units and behavioural purpose are published in
`docs/FinalFidelityPatch_v1_Configuration.md` and
`config/final_fidelity_patch_v1.json`.

## Replay events and test expectations

New replay evidence includes `M1_QUALITY_EVALUATED`,
`M1_LOW_VALUE_OBSERVE_ONLY`, `CONTINUATION_QUALITY_UPDATED`,
`TRADE_MATURITY_CHANGED`, `GIVEBACK_STATE_CHANGED`,
`EXHAUSTION_STATE_CHANGED`, `PROTECTION_RECOMMENDED`, and
`MANAGEMENT_ACTION_COMMITTED`.  Each event carries one closed-candle
`as_of_index`; no supporting engine can commit an action.

Tests must prove deterministic score breakdowns; structural validity remains
separate from quality; meaningful counter-trends and clean BOS candles score
above noise; stale triggers are penalized; hysteresis prevents one-candle
oscillation; normal pullbacks do not become exhaustion; opposing protection
failure exits; TP1 wick touch does not force break-even; stops never widen;
M1-to-M5 transitions never widen; contextual giveback arithmetic is exact;
supporting engines do not mutate; there is one committed action per event;
M1/M5 first entries do not duplicate; one setup plus re-entry is one sequence
and two attempts; replay uses no future or unfinished candles; identical input
is deterministic; and order APIs remain unused.

Executable patch expectations are named
`test_quality_breakdown_is_deterministic_and_sums_to_score`,
`test_clean_bos_scores_above_wick_heavy_noise`,
`test_stale_trigger_is_penalized_without_rewriting_structure`,
`test_m1_outcome_does_not_call_every_loss_false`,
`test_continuation_hysteresis_rejects_one_candle_oscillation`,
`test_meaningful_protection_break_fails_continuation`,
`test_normal_pullback_is_not_exhaustion`,
`test_contextual_giveback_severity`,
`test_supporting_reports_do_not_mutate_and_one_action_commits`,
`test_patched_management_never_widens_and_wick_tp1_does_not_force_be`,
`test_identity_count_one_setup_one_sequence_two_attempts`, and
`test_defaults_are_research_only`.

# Final Sequence Recovery and Elite Management Patch

This is the final behavioural completion candidate before the simulator. It
freezes the existing 60 setup identities, entries, historical ranges, and
development/validation/holdout assignments. It adds sequence recovery and
earned-opportunity management without redesigning the Director or weakening
causality.

## Identity and cross-timeframe re-entry lifecycle

A `SETUP` is one parent M5 retracement. Its `parent_setup_id` is also its
`trade_sequence_id`. An `EXECUTION_ATTEMPT` is one position inside that
sequence. Attempt 1 is the first valid M1 or M5 entry. After its logical
failure, `CrossTimeframeReentryCoordinator` evaluates parent viability. The
parent remains eligible only when dominant M5 protection is intact, direction
has not changed, the impulse cycle still owns the retracement, the retracement
has not expired, and `reentry_count == 0`.

An eligible parent becomes
`FIRST_ATTEMPT_FAILED_PARENT_RETRACEMENT_ACTIVE`. Closed M1 and M5 events are
merged chronologically. The first fresh, same-parent, body-close continuation
BOS owns Attempt 2. Valid transitions are M1-to-M1, M1-to-M5, M5-to-M1, and
M5-to-M5. The winning candidate closes the competing gate, increments
`attempt_number` to 2, sets `reentry_count` to 1, and recalculates trigger,
logical stop, emergency stop, targets, and management from its own timeframe.
Attempt-1 stops and triggers are never reused. A second failure sets
`CLOSED_AFTER_SECOND_FAILURE`; no third attempt exists.

Required event fields are `parent_setup_id`, `trade_sequence_id`,
`execution_attempt_id`, `attempt_number`, `entry_timeframe`, `reentry_count`,
direction, retracement ID, impulse-cycle ID, re-entry owner, trigger index/time/
price, parent-validity reason, availability time, competing candidates, and
winning reason.

Sequence accounting publishes Attempt 1 R, Attempt 2 R,
`combined_sequence_R`, sequence MFE/MAE/peak/giveback/capture, whether the first
loss recovered, re-entry contribution, and separate setup/sequence/attempt
counts. One parent with two attempts remains one setup and one sequence.

## Stop ownership clarification

Every first or re-entry stop belongs to the final meaningful pre-BOS structure
whose body-close failure invalidates that exact entry. For a buy this is the
last important pre-entry swing low/HL; for a sell it is the last important
pre-entry swing high/LH. The chosen structure must be confirmed and available
at entry, control the counter-trend leg, lie on the correct side of entry, and
not be an unrelated older extreme. M1 uses its body edge. M5 uses the relevant
structure plus the existing ATR-tolerant invalidation contract. This rule is
the named regression for review case 60.

## Earned opportunity and two-key protection

`EarnedOpportunityEngine` publishes `NOT_EARNED`, `OPPORTUNITY_EMERGING`,
`OPPORTUNITY_EARNED`, `SIGNIFICANT_OPPORTUNITY_EARNED`, or
`MAJOR_RUNNER_OPPORTUNITY` from closed-candle R, continuation structure,
displacement, and target progress. Numerical profit alone is insufficient.

`OpportunityRiskEngine` publishes `NO_DANGER`, `WATCH`, `ELEVATED_RISK`,
`HIGH_RISK`, or `OPPORTUNITY_FAILURE` with hysteresis. Evidence includes failed
extensions, target rejection/reclaim, momentum decay, opposing displacement,
overlap, deep pullback, weakened continuation, threatened owned protection,
and contextual giveback.

Protection requires two keys: earned opportunity plus meaningful danger.
Healthy continuation produces `NORMAL_PULLBACK_ALLOWED`. Mature protection may
tighten only to a causally proven structural owner. `MatureProfitFloorEngine`
selects the latest valid proven M1/M5 continuation structure, failed opposing
reversal, accepted-target retest, or meaningful internal continuation
structure. Without one it returns `NO_VALID_PROFIT_FLOOR_STRUCTURE`; it never
invents a numerical stop and never widens protection.

Management priority remains: emergency stop; logical invalidation; meaningful
opposing BOS through owned protection; confirmed exhaustion plus opportunity
failure; mature structural protection; proven trail; early structural risk
reduction; hold. Supporting engines recommend and the Trade Manager/Director
commits exactly one action per closed candle.

## Target profiles and behavioural metrics

The research profiles are `STRUCTURE_RUNNER_ONLY`, `PARTIAL_PLUS_RUNNER`, and
`DYNAMIC_PARTIAL_PLUS_RUNNER`. TP1 wick touch may fill a partial but cannot
force break-even. Dynamic partials use target reaction: acceptance keeps a
larger runner, sharp rejection permits a larger partial, and deterioration
without TP1 permits a protective partial only when earned-opportunity evidence
exists.

`WINNER_TO_LOSER_REVERSAL` is reported at peaks 0.5R, 1R, 2R, and 3R plus the
specified severe return thresholds. Long-runner states are
`LONG_RUNNER_PRESERVED`, `LONG_RUNNER_PREMATURELY_EXITED`,
`LONG_RUNNER_PROTECTED_EFFECTIVELY`, and
`LONG_RUNNER_GAVE_BACK_EXCESSIVELY`.

All new parameters live in `SequenceEliteConfig`: opportunity R thresholds,
continuation proof, deterioration hysteresis, target rejection, giveback and
retained-peak thresholds, mature-profit eligibility, dynamic partial fractions,
research profile, re-entry freshness, cross-timeframe winner policy, parent
expiry, and normal-pullback tolerance. They are soft unless explicitly named
as identity, causality, freshness, stop-side, protection, or one-re-entry hard
contracts. No order API is enabled.

# Pre-Simulator Canonical Repair — Repaired Hybrid Strategy

This section supersedes the experimental FinalSequenceElite behaviour while
preserving its engineering contracts.  The accepted Final Fidelity Patch v1
is the Attempt-1 management control.  The repaired hybrid may add one
structurally justified re-entry, corrected economic-risk accounting, and
causal management evidence; it may not alter the frozen first-entry population.
The implementation owner is `core/presimulator_repair.py`.

## Hybrid ownership and merge policy

`SystemStateDirector` remains the sole strategy-state owner. Closed-candle
acquisition, the synchronized M1/M5 clock, setup/retracement/impulse identity,
first-entry ownership, SignalLedger, replay contracts, Fibonacci orientation,
qualified retracement, dominant protection, logical/emergency stops, and the
one-re-entry ceiling are `KEEP_SEQUENCE_ELITE`.

Accepted baseline Attempt-1 target lifecycle, meaningful trail behaviour,
opposing-BOS exits, ordinary-pullback tolerance, runner treatment, and committed
TradeManager actions are `KEEP_BASELINE`.  Chronological sequence equity,
parent viability, strategic re-entry readiness, complete Attempt-2 management,
event-time partial commitment, and emergency-risk sizing are
`REPAIR_AND_REPLACE`.  Final-state-informed partial sizing and protection-intact
equals re-entry eligibility are `REMOVE_OBSOLETE`.  Alternative emergency-risk
models and profile comparisons are `AUDIT_ONLY`.

## Chronological sequence equity

For each closed-candle event, `sequence_equity_R` equals realized R from closed
attempts plus unrealized R from the current open attempt. Attempt 2 starts from
Attempt 1's realized result. The maximum and minimum of this chronological
curve own sequence peak and trough. Final R is the sum of realized attempts;
giveback is `max(0, peak - final)`. `profit_retained_ratio` is clamped to zero
when final R is non-positive after a positive peak; that condition is a
winner-to-loser reversal. `final_result_relative_to_peak` remains a separate,
unclamped diagnostic and must never be labelled profit retained.

## Authoritative parent viability

`ParentViabilityEngine` evaluates, in order: re-entry ceiling, dominant
protection body-close failure, confirmed opposite M5 trend, superseded impulse
cycle, completed retracement, expiry, and proof that the same counter-trend move
continued or deepened after the early failure. Its terminal states are
`CLOSED_REENTRY_LIMIT`, `INVALIDATED_DOMINANT_PROTECTION`,
`INVALIDATED_TREND_CHANGE`, `INVALIDATED_NEW_CYCLE`,
`COMPLETED_NO_REENTRY`, `EXPIRED`, and `NO_REENTRY_UNPROVEN_PARENT`; only
`SAME_RETRACEMENT_EXTENDED` enables monitoring. Protection intact by itself is
never sufficient.

## Strategic re-entry readiness

The readiness lifecycle is `REENTRY_NOT_ELIGIBLE`, `FIRST_ATTEMPT_FAILED`,
`PARENT_VALIDITY_REVIEW`, `SAME_RETRACEMENT_ACTIVE`,
`WAITING_FOR_CHILD_RESET`, `WAITING_FOR_M5_CONFIRMATION`,
`M1_REENTRY_CANDIDATE`, `M5_REENTRY_CANDIDATE`, `REENTRY_READY`,
`REENTRY_OPEN`, `REENTRY_CONSUMED`, `REENTRY_CANCELLED`, and
`CLOSED_AFTER_SECOND_FAILURE`.

M1 is strategically ready only after a post-failure child reset: a meaningful
new counter-trend leg, fresh owned trigger different from Attempt 1, causal
confirmation, and a fresh child stop. M5 is ready after a fresh same-parent M5
continuation BOS with dominant protection intact. The first strategically ready
closed BOS owns Attempt 2; a merely technical M1 recross cannot outrank M5.
Attempt 2 closes the competing gates and its closure makes the parent terminal.

## Complete Attempt-2 state

Attempt 2 builds fresh identity, entry, logical and emergency stops, risk,
targets, management timeframe, continuation, trail, exhaustion,
earned-opportunity, protection, and exit state. It processes every later closed
candle through the same authoritative management pipeline as Attempt 1.
Attempt-1 triggers, trails, targets, and protection are never reused. Every
executed re-entry publishes `attempt_2_management_complete`.

## Emergency economic risk

Logical and emergency distances, money risk, and R units are distinct.
`emergency_risk_multiple = emergency_stop_distance / logical_stop_distance`.
Model A sizes from the emergency stop so its loss equals configured account
risk. Model B starts from logical-stop sizing then reduces size until emergency
loss is below `MAX_EMERGENCY_ACCOUNT_RISK`. Both models are reported; the
research comparison uses the configured model and never changes structure.

## Causal partial commitment and authoritative actions

A partial is decided at its exact closed-candle event from the current target,
continuation, opportunity, and deterioration states. Its index, time, fraction,
price, reason, and state snapshot are frozen. Later candles cannot rewrite it.
The initial repaired profile permits at most one TP1 partial plus runner.

Supporting engines only recommend. The authoritative TradeManager commits one
of `HOLD`, `KEEP_INITIAL_STOP`, `REDUCE_RISK_TO_STRUCTURE`,
`MOVE_TO_PROVEN_M1_STRUCTURE`, `MOVE_TO_PROVEN_M5_STRUCTURE`,
`LOCK_STRUCTURAL_PROFIT`, `TAKE_CAUSAL_PARTIAL`, `EXIT_OPPOSING_BOS`,
`EXIT_LOGICAL_INVALIDATION`, `EXIT_EXHAUSTION_CONFIRMED`, or `EXIT_EMERGENCY`
per candle. Profit alone and one weak candle cannot tighten. Healthy continuation
publishes `HOLD_NORMAL_PULLBACK`. Aggressive protection requires earned
opportunity, meaningful deterioration, elevated giveback, and a proven
tightening structure.

## Required repair test expectations

`test_loss_plus_open_profit_builds_cumulative_equity`,
`test_sequence_peak_is_chronological`, `test_sequence_giveback_formula`,
`test_winner_to_loser_reversal_formula`,
`test_negative_final_has_zero_profit_retained_ratio`,
`test_attempt2_builds_fresh_management_state`,
`test_attempt2_builds_fresh_targets`, `test_attempt2_builds_fresh_trails`,
`test_attempt2_may_transition_m1_to_m5`,
`test_attempt2_may_exit_opposing_bos`,
`test_attempt2_management_complete_for_reentry`,
`test_intact_protection_alone_does_not_allow_reentry`,
`test_fresh_child_reset_allows_m1_reentry`,
`test_immediate_original_trigger_reuse_is_rejected`,
`test_m5_confirmation_may_own_after_m1_failure`,
`test_strategic_candidate_outranks_technical_candidate`,
`test_reentry_limit_is_one`, `test_second_failure_is_terminal`,
`test_partial_uses_decision_time_state`,
`test_future_rejection_cannot_rewrite_partial`,
`test_partial_prefix_is_suffix_invariant`,
`test_emergency_risk_multiple_formula`,
`test_position_size_caps_emergency_account_risk`,
`test_logical_and_account_r_are_separate`,
`test_profit_alone_does_not_tighten`, `test_one_weak_candle_does_not_tighten`,
`test_opportunity_and_deterioration_may_tighten`,
`test_tightening_requires_structure_owner`, `test_hybrid_stop_never_loosens`,
`test_healthy_pullback_remains_open`, `test_strong_continuation_keeps_runner`,
`test_tp1_wick_does_not_force_break_even_hybrid`,
`test_one_committed_action_per_event_hybrid`,
`test_supporting_engines_cannot_mutate_position_hybrid`,
`test_frozen_population_has_no_duplicate_first_entries`,
`test_repair_uses_no_future_candles`, `test_repair_uses_no_unfinished_candles`,
`test_repaired_replay_is_deterministic`, and
`test_repair_calls_no_order_api`.

# Final Prefix-Causal Integrity Patch — Simulator Baseline V0.9

This section is the authoritative correctness contract for
`SMARTSTRUCTUREBOT_SIMULATOR_BASELINE_V0_9`. It changes no trading threshold,
first-entry rule, Fibonacci rule, stop rule, target rule, re-entry ceiling or
management philosophy. It replaces only decision paths whose historical
answers could depend on a later suffix.

## Prefix-causality invariant

For every decision index `i`, the canonical result produced from the complete
dataset with `as_of_index=i` must equal the result produced from the physical
prefix `data.iloc[:i+1]`. This applies to swings, parent viability, extension
proof, retracement identity, M1 and M5 re-entry candidates, candidate owner,
Attempt-2 stop, target state, continuation, opportunity, trail evidence,
protection, partial decision, committed action and cumulative equity.

Full-history swing catalogues filtered backward are forbidden. Full recovery
windows summarized by their final high or low are forbidden. Final post-entry
trail catalogues that silently rewrite earlier evidence are forbidden.

## Immutable causal swing ledger

The implementation module is `core/prefix_causality.py`.
`CausalSwingLedger` processes one newly closed candle at a time. A potential
swing at index `s` becomes available only at `s + ENGINE_SENSITIVITY`. Its
immutable confirmation event stores `swing_id`, index, side, price,
confirmation-time classification and role, timeframe, detection index,
confirmation index, availability index, prefix rows used and causal validity.
A future role change must be a separate promotion, demotion or supersession
event; the original event is never mutated.

## Stateful parent review

At Attempt-1 failure, `PrefixParentViabilityStateMachine` stores the failure
snapshot and enters `PARENT_REVIEW_ACTIVE`. It then moves through
`WAITING_FOR_SAME_RETRACEMENT_EXTENSION`, `SAME_RETRACEMENT_ACTIVE`,
`PARENT_INVALIDATED`, `PARENT_EXPIRED`, `REENTRY_CONSUMED` or
`CLOSED_AFTER_SECOND_FAILURE` using only newly closed M1/M5 events.

Extension requires a causally confirmed post-failure counter-structure that
deepens the same retracement by the existing meaningful-reset threshold while
dominant protection remains intact. ATR supports distance measurement but the
confirmed structure owns the decision. The extension event freezes its index,
time, price, structure ID, reason, score and distance. No earlier candidate can
be restored after this event appears.

## Prefix-causal re-entry competition

Every new M1 and M5 close updates its own ledger and the parent snapshot. M1
requires a fresh child reset and fresh trigger; M5 requires a fresh parent
continuation trigger. Neither is eligible before the extension event. Only
candidates available at the current merged event time compete. The earlier
close owns; identical close times prefer M5 parent confirmation. At most one
Attempt 2 is permitted.

Every candidate publishes its decision index/time, parent and retracement IDs,
child cycle, trigger ID/index/availability/price, child-reset availability,
current as-of index, prefix rows used, stop evidence and causal validity.

## Prefix-causal Attempt-2 management

Attempt 2 owns a fresh incremental management state. Each later closed candle
updates target lifecycle, continuation, M1/M5 structures, trail proof,
transition, opportunity, giveback, exhaustion, opposing BOS, logical and
emergency invalidation, and one Director-committed action. The previously
accepted thresholds and management authority remain unchanged.

Each immutable trail event stores `trail_event_id`, attempt and timeframe,
structure ID/index/price/role, candidate detection and confirmation, proof BOS
and availability, commitment index, old/new protection, current as-of index,
prefix rows used and causal validity. A later structure creates a new event; it
cannot edit an older event.

## Suffix-invariance verification

`CausalInvarianceTester` compares canonical fields from a physical prefix with
the same as-of decision after one-, five-, twenty-candle and full suffixes.
Adversarial suffixes include extreme highs, extreme lows, major impulses,
large reversals, long compression and duplicated micro swings. Earlier
canonical decisions must remain byte-for-byte equivalent in the audited
fields.

## Final prefix-causality test expectations

1. `test_parent_viability_never_scans_beyond_current_index`
2. `test_extension_proof_has_precise_causal_availability_candle`
3. `test_candidate_before_extension_proof_remains_invalid_permanently`
4. `test_future_extension_cannot_retroactively_validate_old_candidate`
5. `test_m1_swing_classification_is_prefix_invariant`
6. `test_m5_swing_classification_is_prefix_invariant`
7. `test_m1_reentry_trigger_is_suffix_invariant`
8. `test_m5_reentry_trigger_is_suffix_invariant`
9. `test_reentry_owner_is_suffix_invariant`
10. `test_attempt2_initial_stop_is_suffix_invariant`
11. `test_attempt2_trail_candidates_are_prefix_causal`
12. `test_attempt2_proof_bos_is_prefix_causal`
13. `test_trail_commitment_is_suffix_invariant`
14. `test_target_state_at_index_is_suffix_invariant`
15. `test_partial_decision_at_index_is_suffix_invariant`
16. `test_management_action_at_index_is_suffix_invariant`
17. `test_sequence_equity_at_index_is_suffix_invariant`
18. `test_full_future_reversal_cannot_change_earlier_action`
19. `test_trade_51_chronological_regression`
20. `test_frozen_60_first_entry_population_remains_unchanged`
21. `test_no_future_data`
22. `test_no_unfinished_bars`
23. `test_no_duplicate_first_entries`
24. `test_maximum_one_reentry`
25. `test_no_order_apis`

## Freeze and operational state

This version may be frozen only as `SMARTSTRUCTUREBOT_SIMULATOR_BASELINE_V0_9`
after all causal gates and the full authoritative suite pass. It is not Strategy
V1.0, is not automatic-demo-ready, and contains no order execution. Further
behavioural calibration belongs in the candle-by-candle simulator against
frozen comparison datasets.

### Final sequence patch deterministic test expectations

- `test_m1_first_failure_may_allow_m5_reentry`
- `test_m5_first_failure_may_allow_m1_reentry`
- `test_first_valid_reentry_closes_competing_gate`
- `test_same_parent_setup_id_is_preserved`
- `test_attempt_number_increments_to_two`
- `test_reentry_stop_belongs_to_winning_timeframe`
- `test_stale_attempt_one_trigger_cannot_be_reused`
- `test_second_failure_closes_parent_permanently`
- `test_no_third_attempt_is_permitted`
- `test_trade_51_regression_lifecycle_is_explicitly_audited`
- `test_one_setup_two_attempts_counts_once`
- `test_combined_sequence_r_is_correct`
- `test_reentry_contribution_is_correct`
- `test_sequence_recovery_flag_is_correct`
- `test_attempt_and_sequence_metrics_remain_separate`
- `test_opportunity_not_earned_from_profit_alone`
- `test_opportunity_earned_with_structure_and_progress`
- `test_major_runner_opportunity_uses_large_peak`
- `test_healthy_continuation_caps_false_risk`
- `test_opportunity_failure_requires_confluence`
- `test_risk_hysteresis_rejects_one_event_flip`
- `test_normal_pullback_is_explicitly_allowed`
- `test_mature_floor_requires_earned_opportunity`
- `test_mature_floor_requires_deterioration_risk`
- `test_mature_floor_selects_proven_long_structure`
- `test_mature_floor_selects_proven_short_structure`
- `test_mature_floor_rejects_unproven_structure`
- `test_structure_runner_profile_has_no_partial`
- `test_static_partial_profile_uses_half`
- `test_dynamic_acceptance_profile_preserves_runner`
- `test_dynamic_rejection_profile_protects_more`
- `test_winner_to_loser_threshold_half_r`
- `test_winner_to_loser_threshold_one_r`
- `test_winner_to_loser_threshold_two_r`
- `test_long_runner_preservation_bucket`
- `test_long_runner_excessive_giveback_bucket`
- `test_sequence_config_is_research_only`
- `test_sequence_config_file_matches_research_mode`
- `test_sequence_module_contains_no_order_send_call`
- `test_evidence_runner_publishes_zero_order_flag`

## Phase S1 simulator contract

### Identity and authority

Phase S1 is an observability and replay layer around the frozen
`SMARTSTRUCTUREBOT_SIMULATOR_BASELINE_V0_9`. It may reveal, replay, compare,
annotate and export canonical decisions. It may not manufacture an entry,
alter a threshold, optimize a management rule or call a broker order API.

Authority is one-way:

```text
frozen closed candles
  -> deterministic replay clock
  -> canonical run_pipeline/SystemStateDirector
  -> immutable ReplayEvent and StateSnapshot
  -> read-only UI, shadows, flags and exports
```

The Director owns the sole committed action. Engine recommendations are
advisory and retain acceptance/rejection reasons. Shadow managers consume the
same visible prefix and cannot mutate canonical state.

### Replay clock and lifecycle

M1 and M5 close events are merged by UTC close time. When both close together,
processing order is `M5_PARENT_UPDATE`, `M1_CHILD_UPDATE`, `M5_FALLBACK`.
Only complete bars participate. Event zero includes the immediately preceding
M1/M5 candles because they were already closed at the requested start.

Each event stores event identity, event time, newly closed indices, visible-row
counts, processing order, pipeline hash, snapshot hash, parent hash,
recommendations, Director decision, shadows, flags, story events and integrity.
Events never change after publication. Checkpoints accelerate restoration;
forward replay after rewind must reproduce the same hashes.

### Simulator states

- Session: `UNBUILT`, `READY`, `PLAYING`, `PAUSED`, `COMPLETE`, `FAILED`.
- Integrity: `PASS` or `FAIL`; automatic playback pauses on `FAIL`.
- Event: candle close, setup/phase/target/protection/entry/exit/re-entry change,
  or bug flag.
- Recommendation: `WAITING_FOR_CONFIRMATION`, `ACCEPTED_BY_DIRECTOR`,
  `REJECTED_BY_DIRECTOR`, `NOT_ACTIONABLE`.
- Review: `ACCEPT`, `REJECT`, `UNCERTAIN`; stored outside canonical state.

### Snapshot contract

Every snapshot publishes identity, replay clock, data visibility, canonical
root contracts, M1 child state, management, recommendations, Director action,
shadow managers, bug flags, sequence accounting, story, integrity and hash
chain. `future_rows_visible` and `unfinished_rows_visible` must remain zero.

### UI and chart rules

M5 parent and M1 execution charts share the event timestamp. Both charts draw
only rows whose source index is at or below the event's visible index. Layers
are presentation-only. Investor, normal and debug modes cannot change state.
Navigation supports play/pause, single step, significant event, entry, exit,
re-entry, flag, jump, reset and keyboard shortcuts. The timeline scrolls only
inside its own panel so chart review position is preserved.

### Shadows, flags and exports

Required shadows are pure structure runner, TP1 partial plus runner, earned
opportunity manager, M5 confirmation re-entry and M1 reset re-entry. Each is
isolated, suffix-invariant and explicitly non-authoritative.

Bug flags are diagnostic signals, never strategy actions. The initial suite
covers prefix/state mismatch, multiple actions, order API detection, early
entry, post-entry stop evidence, premature re-entry, severe giveback,
winner-to-loser reversal and engine/Director conflict.

Exports contain immutable JSON, CSV, high-resolution chart PNGs, manifest
hashes and review forms. Supported bundles are one event, one sequence, one
full replay and one ChatGPT review package.

### Phase S1 configurable parameters

Configuration owns timezone, checkpoint frequency, default speed, swing
sensitivity, HTF policy, single-strong-HTF allowance, visible chart windows,
presentation mode, enabled shadows and enabled bug rules. Strategy thresholds
remain owned by the baseline and are not simulator parameters.

### Phase S1 test expectation

The exact 37-test contract covers clock ordering, closed bars, speed equality,
rewind, checkpoint reconstruction, snapshot/hash integrity, suffix invariance,
UI isolation, one Director action, recommendation trace, shadow isolation,
state diff, bug isolation, review separation, export hashes, automatic pause,
misalignment detection, order-API refusal, no future data, no unfinished bars
and deterministic replay. Phase S1 cannot be accepted from screenshots alone.

## Phase S1B — realistic paper account and cost authority

### Ownership boundary and decision tree

`SystemStateDirector` remains the sole strategy authority. It may commit
entry, partial, protection, exit, cancellation or re-entry actions. The
paper-execution subsystem has no right to create, modify, delay for quality,
or improve a strategy signal. It owns only feasibility, modeled execution and
money state.

```text
closed replay candle
  -> canonical pipeline / Director action (immutable)
  -> PaperExecutionReplayService
       -> PaperBroker feasibility decision
          -> contract + currency + spread + slippage + commission
          -> position size + emergency-risk cap + margin cap
          -> fill, queue, block, partial, close or no execution action
       -> immutable execution ledger
       -> account/equity/margin state
       -> isolated shadow paper brokers
  -> read-only UI, exports, flags and evidence
```

The paper decision tree is:

```text
if no Director order action: mark market and account only
elif entry and another position is open: reject concurrent position
elif account depleted or stopped out: reject
else obtain explicit contract and ZAR conversion
     construct bid and ask from native spread or disclosed fallback
     apply deterministic adverse slippage
     size from logical risk, emergency risk and free margin
     if minimum lot exceeds hard limits: block visibly
     elif next-open timing selected: queue causally
     else: fill paper order and append ledger events

while open:
  emergency stop is broker-style wick protection
  logical stop moves/exits only when the Director commits it
  partials obey minimum lot and remaining-volume constraints
  closes use the economically correct bid/ask side
  margin state may warn, call or stop out
```

### Engines, modules and contracts

| Module | Sole responsibility | Important outputs |
|---|---|---|
| `PaperExecutionReplayService` | Replay one immutable strategy ledger through canonical and isolated shadow accounts | paper events, strategy hash, shadow isolation |
| `PaperBroker` | Convert one Director action into at most one primary paper action and account mutation | ticket, position, account, story, ledger |
| `PaperAccount` | Balance/equity/free-margin/drawdown state | `AccountState` |
| `ContractSpecificationService` | Symbol-specific trading economics | minimum/step, ticks, contract, margin, costs, provenance |
| `CurrencyConversionEngine` | Native quote currency to ZAR | rate, source, timestamp, missing-rate status |
| `SpreadEngine` | Native, fixed or symbol/session estimated spread | bid/ask distance, state, provenance |
| `SlippageEngine` | Deterministic causal adverse slippage | points, seed, model |
| `CommissionEngine` | Opening, closing and partial commission | ZAR charge kept separate from spread |
| `SwapEngine` | Optional daily/triple holding cost | ZAR charge or `SWAP_NOT_MODELLED` |
| `FillEngine` | Side-correct paper fill | bid, ask, requested, adjusted and final prices |
| `PositionSizer` | Risk/margin constrained volume | ideal, capped and final lots plus block reason |
| `MarginEngine` | Required margin and margin-health state | used/free margin, level, warning/call/stop-out |
| `IntrabarResolver` | Honest same-bar target/stop ordering | child resolution, conservative fallback or ambiguity |
| `ExecutionLedger` | Append-only hash-linked monetary events | parent hash, state hash, balances and causal flag |
| financial analytics | Drawdown, equity, costs, risk, attempt/sequence, symbol/session | ZAR and R reports |
| `DataLibraryService` | Read the configured portable library only | safe symbols/ranges and provenance |
| `ReplayBuildService` | Bounded background range builds | job status, progress, output session |
| `ExportService` | Reproducible portable audit packages | CSV, JSONL, HTML and manifests |

### Financial state vocabulary and lifecycle

- Account: `ACTIVE`, `LOW_MARGIN_WARNING`, `MARGIN_CALL`, `STOP_OUT`,
  `ACCOUNT_DEPLETED`, `SIMULATION_COMPLETE`.
- Paper order: `PAPER_ORDER_REQUESTED`, `PAPER_ORDER_FILLED`,
  `PAPER_ORDER_REJECTED`, `PAPER_ENTRY_QUEUED_NEXT_OPEN`.
- Sizing: `EXACT_RISK_ACHIEVED`, `ROUNDED_WITHIN_TOLERANCE`,
  `UNSAFE_MINIMUM_VOLUME_OVERRIDE`, `MINIMUM_VOLUME_OVER_RISK`,
  `INSUFFICIENT_MARGIN`, `MISSING_CONVERSION_RATE`,
  `INVALID_STOP_DISTANCE`.
- Position: `OPEN`, `PARTIALLY_CLOSED`, `CLOSED`.
- Costs: spread, slippage, commission and swap remain separately attributed.
- Margin: `HEALTHY`, `LOW_MARGIN_WARNING`, `MARGIN_CALL`, `STOP_OUT`.
- Intrabar: `TARGET_FIRST`, `STOP_FIRST`, `NEITHER`, `UNRESOLVED`.
- Data build: `QUEUED`, `BUILDING`, `COMPLETE`, `FAILED`.

An attempt has its own fill, risk, cost and realized result. Re-entry is a new
attempt in the same strategy sequence and is sized from current balance/equity
when compounding is enabled. A brand-new parent setup begins a new sequence.
Shadow accounts have independent balances, positions, ledgers and hashes; they
share signals, candles and the deterministic cost seed only.

### Economic rules and formulas

All accounts are ZAR. `planned_risk` is selected from current balance, current
equity, fixed rand, broker minimum or grade-adjusted research risk. Default
compounding is on.

```text
logical_risk_per_lot = logical_stop_ticks * tick_value * ZAR_rate
emergency_risk_per_lot =
    (emergency_stop_ticks + spread_ticks + emergency_slippage_ticks)
    * tick_value * ZAR_rate
ideal_lots = planned_risk / logical_risk_per_lot
final_lots = floor_to_step(min(
    ideal_lots,
    logical_account_cap / logical_risk_per_lot,
    emergency_account_cap / emergency_risk_per_lot,
    free_margin / margin_per_lot,
    broker_maximum
))
equity = balance + floating_net_PL
free_margin = equity - used_margin
margin_level_percent = equity / used_margin * 100
net_attempt_PL = reference_gross_PL - spread - slippage - commission - swap
drawdown = peak_equity - current_equity
```

The final lot size always rounds down. A below-minimum result is accepted only
when the broker minimum remains within hard account/emergency/margin caps and
the declared tolerance. Otherwise it is visibly blocked. Unsafe override is
off by default and, when deliberately selected for research, is labeled.

BUY enters at ask and exits at bid. SELL enters at bid and exits at ask.
Spread is never charged a second time outside price-side economics. Seeded
slippage is adverse, reproducible and larger for emergency stops. Commission
and swap are not hidden inside spread.

Logical stops preserve Steve's close-based invalidation rule. Emergency stops
are wider catastrophic wick protection. Paper execution must never replace
one with the other. When target and stop touch one OHLC bar, already-closed
lower-timeframe candles may resolve order; otherwise the configured
conservative or explicit-ambiguity policy is published.

### Execution replay events

The monetary ledger may publish `PAPER_ORDER_REQUESTED`,
`PAPER_ORDER_FILLED`, `PAPER_ORDER_REJECTED`, `POSITION_OPENED`,
`LOGICAL_STOP_UPDATED`, `PARTIAL_REQUESTED`, `PARTIAL_FILLED`,
`PARTIAL_REJECTED`, `COMMISSION_CHARGED`, `SWAP_CHARGED`,
`POSITION_CLOSED`, `MARGIN_WARNING`, `MARGIN_CALL` and `STOP_OUT`. Every row
contains replay/account/setup/sequence/attempt identity, symbol, timestamp,
volume, requested/fill price, separate costs, gross/net P/L, post-event
balance/equity/margin, causal validity and the ledger hash chain.

### Configurable S1B parameters

- account: positive starting balance; risk model; risk percent/fixed rand;
  maximum logical and emergency account risk; leverage; margin thresholds;
  one-position limit; compounding; explicit unsafe-minimum override;
- execution: broker profile; `IDEALIZED_CONTROL`, `NORMAL_ESTIMATED` or
  `STRESSED_COSTS`; spread/slippage/commission/swap model; BOS-close or
  next-open timing; intrabar policy; partial fraction; deterministic seed;
- build: configured symbol, UTC start/end, context preload and event bound;
- presentation: simple, trader, debug or investor mode and chart layers.

`NORMAL_ESTIMATED` is the primary financial result. Idealized is a control,
stressed is sensitivity. Contract profiles and static conversion rates remain
`ESTIMATED_RESEARCH_PROFILE` until verified broker/historical metadata is
available; the interface and reports must disclose this limitation.

### Data, interface, flags and exports

Portable canonical data is CSV with a manifest (Parquet may be emitted when a
supported engine is available). Browser requests select only configured
symbols and ranges; arbitrary filesystem paths are prohibited. Builds expose
progress and errors and may be deleted only inside their runtime-session root.

The UI permanently displays paper-only/order-disabled status, account
balance/equity/floating/realized/cost/margin/drawdown, active position,
complete fill or rejection ticket, dual synchronized M5/M1 charts, execution
bid/ask/spread, logical/emergency stops, targets/protection, equity curve,
money story, canonical versus shadow money, Director ownership and review
flags. Chart interaction and display modes never mutate strategy or money.

Financial flags include minimum-volume over-risk, excessive emergency risk,
high slippage, extreme spread, partial not executable, costs erased edge,
margin warning/call, stop-out and missing conversion. A flag is a review
prompt only and cannot create an order or alter the Director.

Financial exports include account configuration, contract and conversion
provenance, immutable execution ledger JSONL/CSV, statement HTML/CSV, equity,
attempt/sequence/cost/margin/performance, symbol/session, shadow comparisons,
money story, flag report and a hash manifest.

### Phase S1B test expectation

Exactly 50 deterministic financial contracts cover account state, sizing,
bid/ask, spread, slippage, commission/swap, partials, margin, conversion,
accounting, causal prefix invariance, rewind, shadow isolation, account-size
signal invariance, intrabar ambiguity and order/broker safety. Acceptance also
requires all 37 Phase S1 tests and all 291 inherited strategy tests to remain
green. Visual evidence complements but never replaces these tests.

## Phase S2A — canonical entry-funnel truth instrumentation

Phase S2A is an audit-only layer. It cannot qualify a retracement, loosen a
filter, change a threshold, select an entry, alter a Director action, mutate a
paper account used by production replay, or call an order API. Its only
authority is to observe immutable outputs already published by the canonical
engines, Director, synchronized M1 child engine and isolated paper execution.

The audited funnel is:

```text
HTF context
-> origin BOS
-> protected structure
-> retracement birth
-> retracement significance
-> retracement qualification
-> parent activation
-> M1 child monitoring
-> M1 trigger candidate
-> M5 trigger candidate
-> entry validation
-> SystemDirector commitment
-> isolated paper-execution probe
```

Every S2A value must be copied from a canonical engine output or immutable
canonical event/state object. A value absent from those contracts is written
as `UNAVAILABLE`; no proxy, score substitution, acceptance-membership
inference or fabricated default is permitted. In particular, Fibonacci
remaining impulse is not retracement significance, pool membership is not a
counter-structure count or score component, candidate index is not
qualification index, and Fib zero index is not protected-structure index.

M1 audit events are classified as
`M1_TRIGGER_BEFORE_PARENT_ACTIVE`,
`M1_TRIGGER_WHILE_PARENT_ACTIVE`,
`M1_TRIGGER_AFTER_PARENT_EXPIRED`,
`M1_TRIGGER_INVALID_MICRO_NOISE`, `M1_TRIGGER_WICK_ONLY`,
`M1_TRIGGER_WRONG_DIRECTION`, or `OTHER`. Event count and unique parent setup
count are always published separately. Repeated observations of the same
canonical M1 event are deduplicated by immutable setup/event identity and may
never become additional missed trades.

Qualification latency uses only canonical availability times. Retracement
birth, first meaningful counter move, qualification, M1 trigger, valid M1
body-close BOS, M5 BOS and actual committed entry retain separate timestamps.
The audit distinguishes a future leak from causal confirmation latency:
waiting for the right-side swing confirmation is latency, while allowing a
later suffix to change an already published earlier decision is leakage.

Audit mode processes every usable closed row in the portable library. It may
batch symbols chronologically for runtime reasons but may not downsample
candidates. The S2A evidence package owns funnel rows, parent timing, M1
events, blocker counts, a reconciled summary, report and reproducibility
manifest. Its tests require observer non-mutation, exact count reconciliation,
explainable setup lifecycle, setup/event count separation, parent timing,
deterministic replay, suffix invariance, closed-candle safety and zero order
API calls.

### Phase S2A test expectations

- `test_observer_does_not_mutate_canonical_inputs`
- `test_exact_funnel_count_reconciliation`
- `test_every_setup_has_explainable_lifecycle`
- `test_multiple_m1_events_are_not_multiple_setups`
- `test_parent_active_timing_classification`
- `test_missing_canonical_metric_is_unavailable_not_substituted`
- `test_deterministic_observer_replay`
- `test_suffix_invariance_of_earlier_pipeline_decision`
- `test_swing_availability_timestamp_is_respected`
- `test_unfinished_candle_is_rejected_by_audit_data_contract`
- `test_audit_modules_contain_no_order_send_call`

## Phase S2A.1 — synchronized M1 causality repair and early-entry shadow audit

S2A.1 has priority over entry-frequency optimisation. Its production change is
strictly a causality repair: synchronized M1 decisions may depend only on
closed-candle facts available at the M1 decision close. HTF policy, existing
structural filters, quality thresholds, canonical parent activation and order
execution remain unchanged. Early entries found before canonical parent
`ACTIVE` are research shadows only and have no authority over the Director,
entry arbiter, paper account or lifecycle.

### Parent clocks and ownership

```text
M5 anchor swing occurs
  -> anchor confirmed after ENGINE_SENSITIVITY right candles
  -> parent ARMED at the close of the anchor-confirmation candle
M5 opposing counter swing occurs
  -> counter confirmed after ENGINE_SENSITIVITY right candles
  -> parent ACTIVE at the close of the counter-confirmation candle
M5 failure-trigger swing occurs
  -> failure trigger confirmed after right-side confirmation
  -> candidate.qualified_at = failure-trigger confirmation availability index
M1 trigger-side swing occurs
  -> trigger becomes available only after M1 right-side confirmation
  -> a correctly directed body closes beyond it
  -> legal M1 entry time is that M1 candle close, subject to every existing gate
M5 body-close BOS occurs
  -> M5 fallback entry time is that M5 candle close
```

`candidate["qualified_at"]` therefore means
`m5_failure_trigger_confirmed_at_index`; it is not a first legal trade-entry
timestamp. `ARMED` means the parent pullback anchor is causally confirmed and
M1 observation may begin. `ACTIVE` means the required M5 counter swing is
causally confirmed and canonical M1 execution is permitted.

Every parent contract has two explicitly separated sections:

- `causal_parent_context`: identity, direction and only parent facts known by
  the decision time, each with an availability class and as-of time/index;
- `retrospective_m5_outcome`: eventual M5 entry, stop and comparison metrics,
  marked analytics-only.

Retrospective M5 outcome fields may never affect M1 component scores, total,
grade, policy, observe-only state, entry readiness, entry price, logical stop,
Director commitment or first-valid arbitration. Timing advantage versus an
eventual M5 entry and stop reduction versus an eventual M5 stop are post-hoc
diagnostics only. Removing their former score contribution does not authorize
weight redistribution or threshold tuning.

### Complete synchronized-M1 causal decision tree

```text
take causal parent snapshot as of decision close T
  -> confirm parent ownership and dominant protection
  -> use only M1 candles closed by T
  -> find causally available trigger-side swings
  -> require opposing counter structure
  -> require complete initial/counter/trigger sequence
  -> require current displacement and minimum counter bars
  -> require correctly directed body-close BOS (wick-only remains rejected)
  -> require freshness and causal parent price boundary
  -> derive logical stop from a swing available by entry close
  -> compute causal M1 quality only
  -> C_M1 remains OBSERVE_ONLY under unchanged thresholds
  -> canonical execution remains blocked before parent ACTIVE
  -> first valid canonical entry owns the parent once
```

For any M1 decision timestamp `T`, running the complete parent construction,
child structure, quality and arbitration path on (A) the exact prefix, (B) the
same prefix plus any suffix and (C) the same prefix plus a materially different
suffix must publish identical trigger, readiness, entry index/price/stop,
quality components/total/grade/policy, owner and arbitration decision at `T`.

### ARMED-to-ACTIVE shadow audit

The former label `M1_TRIGGER_BEFORE_PARENT_ACTIVE_REJECTED` described a
trigger-side swing availability event, not a proven BOS. The canonical event
name is `M1_TRIGGER_SIDE_SWING_BEFORE_PARENT_ACTIVE`. A shadow evaluator may
continue each such event candle-by-candle through all existing counter,
sequence, displacement, bar-count, body-close, body-direction, wick-only,
micro-noise, staleness, boundary, stop-side, protection and causal-quality
checks. Its terminal states include `SHADOW_VALID_EARLY_M1`,
`SHADOW_NO_COUNTER_STRUCTURE`, `SHADOW_INCOMPLETE_SEQUENCE`,
`SHADOW_MICRO_NOISE`, `SHADOW_NO_BODY_CLOSE_BOS`, `SHADOW_WICK_ONLY`,
`SHADOW_STALE`, `SHADOW_OUTSIDE_PARENT`, `SHADOW_PROTECTION_BROKEN` and
`SHADOW_LOW_CAUSAL_QUALITY`.

Shadow eligibility uses no post-entry candle. Later M5 entry, later canonical
owner, minutes earlier, price improvement, stop-distance improvement and MFE
before canonical entry are analytics-only outcome comparisons. Event counts
and unique setup counts are always separate. No S2A.1 shadow result may alter
canonical behaviour.

### Phase S2A.1 test expectations

- pre-repair future-M5 dependency is captured and documented;
- causal parent snapshots contain no post-decision fact;
- M1 quality, entry, stop and arbitration are suffix invariant;
- post-hoc M5 metrics cannot influence M1 quality;
- shadow evaluation cannot alter canonical decisions;
- trigger-side swings are not mislabeled as valid BOS events;
- existing body-close and wick-only gates remain unchanged;
- all inherited strategy and simulator tests remain green;
- static and runtime evidence confirms no order API call.

The executable S2A.1 contract names are:

- `test_future_m5_outcome_cannot_change_earlier_m1_decision`
- `test_causal_parent_snapshot_contains_no_post_t_fact`
- `test_complete_m1_path_is_suffix_invariant`
- `test_post_hoc_m5_metrics_cannot_influence_quality`
- `test_shadow_evaluator_does_not_change_canonical_decision`
- `test_pre_active_event_is_a_swing_not_a_bos_label`
- `test_body_close_and_wick_only_protections_are_unchanged`
- `test_s2a1_modules_contain_no_order_send_call`

## Phase S2B — earned early M1 permission (research policy only)

S2B tests one fixed hypothesis without changing the default strategy: after an
exact M5 parent is causally `PARENT_ARMED`, a fully proven M1 continuation
sequence may independently earn `EARLY_M1_PERMISSION_EARNED` before the
existing M5 counter-confirmed `PARENT_ACTIVE` time. `ACTIVE` is never renamed,
backdated or equated to `ARMED`. The default `m1_permission_policy` remains
`COUNTER_CONFIRMED_ACTIVE`; the opt-in research value is
`EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE`. The latter is forbidden in live or
demo execution and has no order authority.

### S2B ownership and lifecycle

```text
PARENT_NOT_AVAILABLE
  -> M5 anchor confirmation publishes PARENT_ARMED
  -> M1 observation is allowed, but ARMED alone is never entry permission
  -> either:
       complete owned M1 sequence + valid body-close BOS + all unchanged gates
         -> EARLY_M1_PERMISSION_EARNED -> M1 attempt 1
     or M5 counter confirmation
         -> PARENT_ACTIVE -> existing M1 permission
     or later M5 body-close continuation
         -> existing M5 fallback attempt 1
```

The parent owner remains `SystemStateDirector`; M1 evidence is owned by
`M1ChildStructureEngine`; permission evaluation is owned by
`M1PermissionPolicyEngine`; first-entry commitment remains owned by the
Director/first-valid arbiter. Ownership requires the exact setup,
retracement, impulse-cycle, protection, direction and Fib-anchor identities.
Timestamp proximity cannot establish ownership. A newer independent parent,
failed dominant protection, unavailable causal Fib/location, consumption,
invalidation or any post-decision dependency blocks early permission.

### S2B decision tree and immutable entry contract

```text
policy is COUNTER_CONFIRMED_ACTIVE?
  -> require normal PARENT_ACTIVE exactly as S2A.1
policy is EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE?
  -> before ARMED: reject
  -> at ARMED with no complete M1 proof: observe only
  -> before ACTIVE: require meaningful counter structure, complete sequence,
     unchanged displacement and bar minimums, available fresh trigger,
     correct-direction body-close BOS, non-wick/non-noise evidence, intact
     parent boundary/protection, exact ownership and unchanged causal quality
  -> all pass: publish EARLY_M1_PERMISSION_EARNED and normal M1 candidate
  -> at/after ACTIVE: return the exact unchanged normal ACTIVE resolver result;
     S2B arbitration has no authority in this interval
```

Entry is the valid BOS candle close. Initial logical stop is the accepted M1
relevant-swing body edge available at entry; the separate emergency stop stays
wider. No suffix, later M5 outcome, future stop, target, state, MFE/MAE or
retrospective analytics may influence parent ownership, permission, trigger,
quality, grade, policy, price, stops, arbitration or Director action at `T`.
M1-to-M5 management may tighten but never widen protection.

One parent still owns one first entry. An earned-early M1 entry consumes M1 and
M5 attempt-1 competitors, preserves parent and sequence identity, and enters
the unchanged management lifecycle as attempt 1. It creates no extra re-entry:
the existing maximum remains one and all existing proof/blocking rules remain.
No S2B score bonus exists; the ten S2A.1 points remain unassigned and every
quality threshold, swing sensitivity, Fib rule, HTF rule, M5 rule, management,
target, risk, cost and session contract is unchanged.

For decision time `T`, prefix run A, actual-suffix run B, modified-suffix run C,
future-reversal run D and different-later-M5-outcome run E must have identical
parent ID, permission, trigger, BOS validity, quality components/total, grade,
policy, entry readiness/index/time/price, logical/emergency stop, owner and
Director action. Retrospective comparisons are post-hoc only.

### Phase S2B test expectations

- `test_early_m1_cannot_execute_before_parent_armed`
- `test_parent_armed_alone_does_not_permit_entry`
- `test_valid_m1_counter_structure_is_required`
- `test_complete_m1_sequence_is_required`
- `test_wick_only_bos_remains_rejected`
- `test_wrong_body_direction_remains_rejected`
- `test_one_candle_micro_noise_remains_rejected`
- `test_stale_trigger_remains_rejected`
- `test_protected_structure_failure_blocks_early_entry`
- `test_unrelated_m1_structure_cannot_hijack_parent`
- `test_timestamp_proximity_cannot_establish_ownership`
- `test_early_m1_entry_occurs_on_bos_candle_close`
- `test_first_early_m1_consumes_later_m1_m5_attempt1`
- `test_one_parent_still_produces_one_first_entry`
- `test_existing_one_reentry_limit_remains_one`
- `test_m1_logical_stop_uses_existing_contract`
- `test_post_entry_candles_cannot_rewrite_initial_stop`
- `test_m1_to_m5_transition_never_widens_protection`
- `test_future_suffix_cannot_change_early_permission`
- `test_future_suffix_cannot_change_m1_quality`
- `test_future_suffix_cannot_change_entry_price`
- `test_future_suffix_cannot_change_logical_stop`
- `test_future_m5_outcome_cannot_change_early_decision`
- `test_first_valid_arbitration_uses_earliest_bos_not_trigger_loop_order`
- `test_variant_returns_exact_baseline_resolution_after_active`
- `test_retrospective_analytics_cannot_enter_entry_calculation`
- `test_baseline_policy_reproduces_s2a1_results`
- `test_shadow_diagnostics_cannot_mutate_director_action`
- `test_no_duplicate_first_entry_after_early_m1`
- `test_no_live_demo_order_api_enabled_or_called`

## Phase S2B.1 — second-touch structural trigger fidelity

Change record: `S2B1_SECOND_TOUCH_TRIGGER_FIDELITY`.

This strategy-fidelity rule preserves S2A.1 causality and leaves the canonical
permission default `COUNTER_CONFIRMED_ACTIVE`. A double top or double bottom is
optional structural evolution inside one existing parent retracement. A normal
single-reaction setup remains legal when no meaningful second touch exists.

### Canonical terminology and ownership

- `SECOND_TOUCH_CANDIDATE`: two same-side wick extremes are causally visible
  inside one parent, separated by an opposing meaningful reaction, but the
  second-touch-owned trigger is not yet available.
- `SECOND_TOUCH_CONFIRMED`: touch 2 and its subsequent meaningful reaction
  trigger are both confirmed using closed candles and right-side swing delay.
- `SECOND_TOUCH_TRIGGER_OWNER`: the meaningful reaction structure after touch
  2 that alone may own the next BOS decision.
- `TRIGGER_SUPERSEDED_BY_SECOND_TOUCH`: the first-touch trigger is retained in
  history but loses execution authority at the causal second-touch migration
  time.
- `ACTIVE_SECOND_TOUCH_TRIGGER`: the confirmed touch-2-owned trigger currently
  eligible for a correctly directed body-close BOS.

A touch uses candle wick extremes: HIGH for a bearish double top and LOW for a
bullish double bottom. Candle bodies need not be equal and exact floating-point
equality is forbidden. S2B.1 explicitly reuses the established structure
hierarchy proximity scale of `0.25 * causal ATR`, now published as the research
parameter `second_touch_proximity_atr_ratio = 0.25`. The separating reaction
must satisfy the existing meaningful-structure displacement of at least
`0.35 * causal ATR`; confirmed swings and a minimum three-candle separation
prevent adjacent noise. These values are fixed before outcome replay and may
not be tuned from S2B.1 results.

Second-touch ownership requires the exact same `parent_setup_id`,
`retracement_id`, `impulse_cycle_id`, direction, dominant-protection identity
and Fib-anchor version. Timestamp proximity alone is never ownership. Foreign,
consumed, post-protection-failure, too-distant and micro/noise structures are
rejected with explicit states.

### Trigger migration decision tree

```text
normal owned reaction trigger A
  -> no meaningful touch 2 before entry
       -> preserve trigger A, body-close BOS, existing stop contract
  -> same-parent touch 2 becomes causally confirmed before entry
       -> retain A in history
       -> A = TRIGGER_SUPERSEDED_BY_SECOND_TOUCH
       -> wait for meaningful reaction structure after touch 2
       -> publish trigger B = ACTIVE_SECOND_TOUCH_TRIGGER
       -> only correctly directed BODY CLOSE beyond B may enter
       -> entry price is that BOS candle close
```

For bearish parents, touch 1/touch 2 are wick highs and trigger B is the
meaningful reaction LOW after touch 2. For bullish parents, touch 1/touch 2 are
wick lows and trigger B is the meaningful reaction HIGH after touch 2. This is
not a generic neckline rule and never selects an arbitrary nearest candle.

If Attempt 1 legally entered before touch 2 existed, later structure cannot
rewrite or erase it. After a causal Attempt-1 failure, a same-parent second
touch may become fresh Attempt-2 evidence only with a fresh identity, trigger,
body-close BOS, stop owner, emergency stop and management state. Attempt-1
trigger/stop reuse is forbidden. The maximum remains one re-entry; no third
attempt can be created.

### Second-touch stop and invalidation contract

The general relevant-swing body-edge stop remains unchanged for normal entries.
Only accepted second-touch entries use this exception:

- bearish: logical structural owner is touch-2 HIGH wick extreme;
- bullish: logical structural owner is touch-2 LOW wick extreme;
- M1: wick through the logical level survives; a body close beyond it applies
  the existing logical invalidation contract;
- M5: the touch-2 wick extreme owns structure and the existing causal
  ATR-tolerant body-close invalidation remains unchanged;
- emergency protection remains separate and wider.

Wicks may establish touches. Wicks may never establish BOS. M1 and M5 use one
shared semantic recognizer with timeframe-specific stop/invalidation handling.

### S2B.1 policy variants

- `CANONICAL_CONTROL`: ACTIVE-only permission, existing trigger behavior.
- `SECOND_TOUCH_CANONICAL`: ACTIVE-only permission, second-touch migration.
- `SECOND_TOUCH_EARNED_EARLY`: earned-early research permission plus
  second-touch migration.

S2B remains research rejected unless fixed paired evidence proves otherwise.
No S2B.1 result may automatically promote either research policy.

### Phase S2B.1 causality and test expectations

At decision timestamp T, prefix-only, actual-suffix, modified-suffix and future
reversal runs must publish identical touch identity/extreme, supersession,
active trigger, BOS, readiness, entry time/price, logical stop, attempt owner
and Director decision. A touch that forms after an entry cannot change that
historical decision.

Permanent tests cover wick-defined tops/bottoms, wick-only BOS rejection,
body-close BOS, same-parent ownership, noise/foreign rejection, pre-entry
supersession, old-trigger blocking, touch-2 trigger and wick-stop ownership,
M1/M5 symmetry, M5 causal tolerance, post-entry immutability, fresh Attempt 2,
no trigger reuse, one-reentry/one-first-entry limits, S2A.1 preservation,
baseline-off reproduction, research-data hashes, absence of order APIs and the
complete suffix matrix.

The canonical shared implementation module is `second_touch_structure`.
Its published terminal/rejection vocabulary is `NO_SECOND_TOUCH`,
`SECOND_TOUCH_CANDIDATE`, `SECOND_TOUCH_CONFIRMED`,
`SECOND_TOUCH_REJECTED_NOISE`, `SECOND_TOUCH_FOREIGN_PARENT`,
`SECOND_TOUCH_AFTER_CONSUMPTION`, `SECOND_TOUCH_PROTECTION_FAILED`,
`SECOND_TOUCH_TOO_DISTANT`, `FIRST_TRIGGER_SUPERSEDED`, and
`WAITING_SECOND_TOUCH_BOS`. A candidate carries the explicit reason
`SECOND_TOUCH_TRIGGER_NOT_AVAILABLE`; no such rejection is collapsed into a
generic no-action result.

Its permanent S2B.1 test expectations are:

- `test_bearish_double_top_uses_wick_extremes`
- `test_bullish_double_bottom_uses_wick_extremes`
- `test_touch_two_is_absent_before_confirmation_delay`
- `test_touch_two_candidate_exists_before_new_trigger_confirmation`
- `test_second_touch_trigger_is_reaction_after_touch_two`
- `test_old_trigger_is_explicitly_superseded`
- `test_second_touch_logical_stop_owner_is_touch_two`
- `test_exact_price_equality_is_not_required`
- `test_touch_distance_beyond_atr_tolerance_is_rejected`
- `test_adjacent_touch_noise_is_rejected`
- `test_missing_separating_reaction_is_rejected`
- `test_micro_separating_reaction_is_rejected`
- `test_foreign_parent_ownership_is_rejected`
- `test_timestamp_proximity_cannot_replace_owner_identity`
- `test_complete_owner_fingerprint_is_stable`
- `test_consumed_setup_rejects_second_touch`
- `test_failed_dominant_protection_rejects_second_touch`
- `test_setup_start_excludes_old_foreign_structure`
- `test_wick_only_bos_is_rejected`
- `test_body_close_bos_is_accepted`
- `test_wrong_direction_body_close_is_rejected`
- `test_bullish_body_close_symmetry`
- `test_m1_m5_recognition_semantics_are_identical`
- `test_future_suffix_cannot_change_frozen_touch_identity`
- `test_future_suffix_cannot_change_frozen_trigger`
- `test_post_entry_touch_cannot_rewrite_earlier_no_touch_decision`
- `test_fresh_attempt_two_can_be_recognized_after_new_start`
- `test_attempt_one_structure_cannot_be_reused_after_failure_start`
- `test_default_feature_flag_is_off`
- `test_default_m1_permission_policy_is_unchanged`
- `test_config_file_keeps_second_touch_research_disabled`
- `test_published_fixed_parameters_match_bible`
- `test_invalid_proximity_configuration_is_rejected`
- `test_invalid_reaction_configuration_is_rejected`
- `test_invalid_separation_configuration_is_rejected`
- `test_research_data_hashes_still_match_frozen_manifest`
- `test_no_order_api_added_to_s2b1_source`
- `test_tp1_clarification_is_documentation_only`
- `test_m1_second_touch_boundary_is_exact_touch_wick`
- `test_m5_second_touch_boundary_retains_causal_atr_tolerance`

## Pending S2B.2 management clarification — documentation only

Do not implement during S2B.1. After TP1, realize 50% and retain 50% as runner.
Candidate protection is halfway between entry and TP1. If that level would sit
inside a structurally normal retracement/retest zone and choke a healthy runner,
use a small positive, cost-covered break-even protection instead. Existing
tighter proven protection always wins. Protection may tighten or hold, never
loosen. TP1, management and outcome code remain unchanged until S2B.2 is
explicitly authorized.
