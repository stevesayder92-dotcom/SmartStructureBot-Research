# Requirements Document: S2B.1.1 Contract Integrity Repair

## Introduction

This document specifies S2B.1.1, a research-only repair of causal timing/confirmation-latency and contract-integrity defects introduced by S2B.1's architecture. S2A.1 previously repaired proven future-data dependencies in S2A.0. S2B.1 was causally legal and suffix invariant but unnecessarily delayed in second-touch recognition by requiring N-right confirmation for Touch-2 candidates. S2B.1.1 repairs this latency without compromising causality by using causal ATR clocks frozen at Touch_2_Index and provisional triggers derived solely from closed pre-BOS candles. The repairs restore contract integrity by ensuring InitialStopContract is complete, immutable, and consumed—never reconstructed—by PaperSimulator.

S2B.1.1 is research-only. No live broker APIs, no demo order submission, no production trading changes. The scope is strictly: automated second-touch recognition timing, stop contract completeness, and metrics reconciliation for paper-only research comparison.

## Glossary

- **System**: The complete SmartStructureBot trading research system including strategy engine, simulator, and analysis tools
- **SecondTouchStructureEngine**: The component responsible for automated recognition of second-touch patterns (double-tops and double-bottoms)
- **Touch_1**: The first swing extreme in a potential second-touch pattern
- **Touch_2**: The second swing extreme that revisits the Touch_1 level within causal proximity tolerance
- **Touch_2_Index**: The actual swing index where Touch_2 wick formed, used as causal clock for Touch-Proximity ATR measurement
- **Available_At_Index**: The later swing index where Touch_2 becomes confirmed/visible; NEVER used for Touch-Proximity ATR
- **Touch-Proximity ATR**: The ATR value measured AT Touch_2_Index (not Available_At_Index), frozen permanently for that Touch-2 candidate, used to validate abs(Touch_2 - Touch_1) <= 0.25 * ATR
- **Causal ATR Clock**: The principle that ATR measurements must use the decision-point index, never future confirmation indices
- **ProvisionalTrigger**: The post-Touch-2 reaction swing derived from closed candles before BOS, becomes the invalidation reference for BOS proof
- **BOS (Break of Structure)**: A body-close break beyond ProvisionalTrigger in the setup direction, proving second-touch validity
- **SECOND_TOUCH_CANDIDATE**: State after Touch-2 identified but before post-Touch-2 trigger available
- **SECOND_TOUCH_PROVED_BY_BOS**: State after body-close BOS breaks the ProvisionalTrigger, authorizing entry
- **InitialStopContract**: The complete, immutable stop specification created at entry authorization, containing price, semantic routing, timeframe, direction, and owner identity
- **SECOND_TOUCH_WICK_EXTREME**: Semantic stop routing where structural owner is Touch_2 exact wick with M1/M5-specific invalidation rules
- **ActiveProtectionState**: The current risk boundary that may tighten or hold but never loosen post-entry
- **Direction-Aware Protection**: BUY protection may move upward or hold (never downward to increase risk); SELL protection may move downward or hold (never upward to increase risk)
- **SystemDirector**: The final strategy action authority that decides ENTRY/REENTRY/NO_ACTION
- **Suffix Invariance**: The causal law that decisions at timestamp T must remain identical regardless of which future timeline follows T
- **Variant_A (CANONICAL_CONTROL)**: Execution variant using permission=COUNTER_CONFIRMED_ACTIVE, pre-S2B.1.1 canonical recognition with N-right Touch-2 confirmation, no repaired second-touch timing
- **Variant_B (REPAIRED_SECOND_TOUCH_CANONICAL)**: Execution variant using permission=COUNTER_CONFIRMED_ACTIVE, repaired Touch-2 candidate recognition with causal ATR clocks, post-Touch-2 provisional trigger, body-close BOS proof, entry at BOS close, SECOND_TOUCH_WICK_EXTREME InitialStopContract
- **Variant_C (REPAIRED_SECOND_TOUCH_EARNED_EARLY)**: Execution variant with exact same repaired second-touch logic as Variant_B, only difference is permission=EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE
- **MANUAL_SHADOW**: Separate audit/visual evidence using manually provided anchor points, NEVER an execution variant, isolated from automated logic, used only for reconstruction reports and distinct visual overlays
- **PaperSimulator**: The closed-candle historical simulator that CONSUMES InitialStopContract without reconstruction
- **Clean-Checkout Fixture**: Test data checked into version control that must reproduce identical results on any clean git clone
- **Full Regression Acceptance Gate**: The requirement that all new S2B.1.1 tests AND all inherited strategy/simulator tests pass with zero regressions before S2B.1.1 is considered complete

## Requirements

### Requirement 1: Causal ATR Clock Integrity for Touch-Proximity Validation

**User Story:** As a quantitative researcher, I want Touch-2 proximity measurements to use ATR frozen at Touch_2_Index, so that second-touch recognition remains causally valid and suffix invariant.

#### Acceptance Criteria

1. WHEN Touch_2 candidate forms, THE SecondTouchStructureEngine SHALL measure Touch-Proximity ATR at Touch_2_Index (the actual swing index)
2. THE SecondTouchStructureEngine SHALL validate abs(Touch_2.price - Touch_1.price) <= 0.25 * Touch-Proximity ATR
3. THE SecondTouchStructureEngine SHALL NOT use Available_At_Index for Touch-Proximity ATR measurement
4. THE SecondTouchStructureEngine SHALL freeze Touch-Proximity ATR permanently for that Touch-2 candidate
5. WHEN later timestamps provide more historical data, THE Touch-Proximity ATR measurement SHALL remain unchanged

### Requirement 2: Touch-2 Candidate Recognition Without N-Right Confirmation

**User Story:** As a quantitative researcher, I want Touch-2 candidates to be recognized immediately when the wick closes, so that second-touch detection does not introduce unnecessary latency while preserving causality.

#### Acceptance Criteria

1. WHEN a swing wick revisits Touch_1 level within proximity tolerance, THE SecondTouchStructureEngine SHALL recognize SECOND_TOUCH_CANDIDATE state
2. THE SecondTouchStructureEngine SHALL NOT require N-right confirmation before recognizing Touch-2 candidate
3. THE SecondTouchStructureEngine SHALL require minimum separation of 3 bars between Touch_1 and Touch_2
4. THE SecondTouchStructureEngine SHALL require meaningful separating reaction abs(reaction.price - Touch_1.price) >= 0.35 * causal ATR
5. THE SecondTouchStructureEngine SHALL use only closed candles for swing identification

### Requirement 3: ProvisionalTrigger Derivation Before BOS

**User Story:** As a quantitative researcher, I want post-Touch-2 reactions to establish a ProvisionalTrigger from closed pre-BOS candles, so that BOS proof has a causally valid reference without waiting for N-right confirmation.

#### Acceptance Criteria

1. WHEN Touch-2 candidate exists, THE SecondTouchStructureEngine SHALL monitor for post-Touch-2 reaction swings
2. WHEN post-Touch-2 reaction swing closes beyond Touch_2 by meaningful threshold (>= 0.35 * causal ATR), THE SecondTouchStructureEngine SHALL designate it as ProvisionalTrigger
3. THE SecondTouchStructureEngine SHALL derive ProvisionalTrigger from closed candles only
4. THE SecondTouchStructureEngine SHALL establish ProvisionalTrigger before any BOS evaluation
5. WHEN ProvisionalTrigger exists, THE SecondTouchStructureEngine SHALL use it as the BOS invalidation reference

### Requirement 4: Body-Close BOS Proof

**User Story:** As a quantitative researcher, I want body-close BOS breaks beyond ProvisionalTrigger to prove second-touch validity, so that entry authorization uses causally sound proof events.

#### Acceptance Criteria

1. WHEN a candle body closes beyond ProvisionalTrigger in the setup direction, THE SecondTouchStructureEngine SHALL recognize BOS proof
2. THE SecondTouchStructureEngine SHALL require body close (not wick) for BOS proof
3. WHEN BOS proof completes, THE SecondTouchStructureEngine SHALL transition to SECOND_TOUCH_PROVED_BY_BOS state
4. THE SecondTouchStructureEngine SHALL NOT authorize entry before SECOND_TOUCH_PROVED_BY_BOS state
5. THE SecondTouchStructureEngine SHALL use only closed candles for BOS evaluation

### Requirement 5: Complete Immutable InitialStopContract with SECOND_TOUCH_WICK_EXTREME Routing

**User Story:** As a quantitative researcher, I want InitialStopContract to be complete and immutable at entry authorization, using SECOND_TOUCH_WICK_EXTREME semantic routing with M1/M5-specific invalidation rules, so that PaperSimulator consumes contracts without reconstruction and stop semantics are historically accurate.

#### Acceptance Criteria

1. WHEN SECOND_TOUCH_PROVED_BY_BOS state authorizes entry, THE System SHALL create InitialStopContract with: price, semantic_routing, timeframe, direction, owner_identity
2. THE System SHALL set semantic_routing = SECOND_TOUCH_WICK_EXTREME for second-touch entries
3. THE InitialStopContract SHALL designate Touch_2 exact wick as structural owner
4. WHILE timeframe = M1, THE System SHALL apply exact-wick invalidation (ATR tolerance = 0, wick excursion survives, body-close beyond logical boundary invalidates)
5. WHILE timeframe = M5, THE System SHALL apply upstream ATR-tolerant invalidation (ATR tolerance = 0.15 * causal ATR, logical boundary = Touch_2_wick +/- tolerance based on direction)
6. THE InitialStopContract SHALL remain immutable after creation
7. THE PaperSimulator SHALL consume InitialStopContract without reconstructing stop semantics
8. THE System SHALL NOT modify InitialStopContract based on future market data

### Requirement 6: Entry Timing at BOS Candle Close

**User Story:** As a quantitative researcher, I want entry to occur at the close of the BOS candle, so that entry timing is causally sound and simulator execution is historically accurate.

#### Acceptance Criteria

1. WHEN BOS body-close proof completes, THE SystemDirector SHALL evaluate entry authorization at BOS candle close
2. THE SystemDirector SHALL NOT enter before BOS candle closes
3. WHEN entry is authorized, THE System SHALL record entry price = BOS candle close price
4. THE System SHALL create InitialStopContract at BOS candle close timestamp
5. THE PaperSimulator SHALL execute entry at BOS candle close with zero future-data access

### Requirement 7: Frozen Automated Recognition Geometry

**User Story:** As a quantitative researcher, I want second-touch recognition thresholds to remain frozen at specified values, so that no threshold tuning is performed to make manual anchors pass or improve profitability.

#### Acceptance Criteria

1. THE SecondTouchStructureEngine SHALL use Touch-Proximity tolerance = 0.25 * Touch-Proximity ATR
2. THE SecondTouchStructureEngine SHALL use meaningful reaction threshold = 0.35 * causal ATR
3. THE SecondTouchStructureEngine SHALL use minimum separation = 3 bars
4. THE System SHALL NOT adjust these thresholds based on manual anchor alignment
5. THE System SHALL NOT adjust these thresholds based on profitability metrics
6. THE System SHALL retain same parent/setup/retracement ownership as S2B.1

### Requirement 8: Exact Execution Variant Definitions

**User Story:** As a quantitative researcher, I want unambiguous definitions of Variants A/B/C and MANUAL_SHADOW, so that execution semantics and analysis scope are clear.

#### Acceptance Criteria

1. THE System SHALL define Variant_A (CANONICAL_CONTROL) as: permission=COUNTER_CONFIRMED_ACTIVE, pre-S2B.1.1 canonical recognition with N-right Touch-2 confirmation, no repaired second-touch timing
2. THE System SHALL define Variant_B (REPAIRED_SECOND_TOUCH_CANONICAL) as: permission=COUNTER_CONFIRMED_ACTIVE, repaired Touch-2 candidate recognition with causal ATR clocks, post-Touch-2 provisional trigger, body-close BOS proof, entry at BOS close, SECOND_TOUCH_WICK_EXTREME InitialStopContract
3. THE System SHALL define Variant_C (REPAIRED_SECOND_TOUCH_EARNED_EARLY) as: exact same repaired second-touch logic as Variant_B, only difference is permission=EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE
4. THE System SHALL define MANUAL_SHADOW as: separate audit/visual evidence using manually provided anchor points, NEVER an execution variant, isolated from automated logic, used only for reconstruction reports and distinct visual overlays
5. THE System SHALL NOT route manual annotations or MANUAL_SHADOW data to Variant_A, Variant_B, or Variant_C execution logic

### Requirement 9: Direction-Aware ActiveProtectionState Never Loosens

**User Story:** As a quantitative researcher, I want ActiveProtectionState to tighten or hold but never loosen in a direction that increases risk, so that risk management is sound and historical contracts are preserved.

#### Acceptance Criteria

1. THE System SHALL maintain InitialStopContract as immutable historical truth
2. THE System SHALL maintain ActiveProtectionState as separate mutable protection boundary
3. WHILE direction = BUY, THE System SHALL allow ActiveProtectionState to move upward or hold
4. WHILE direction = BUY, THE System SHALL NOT allow ActiveProtectionState to move downward (increasing risk)
5. WHILE direction = SELL, THE System SHALL allow ActiveProtectionState to move downward or hold
6. WHILE direction = SELL, THE System SHALL NOT allow ActiveProtectionState to move upward (increasing risk)
7. THE System SHALL NOT rewrite InitialStopContract when applying trailing stops

### Requirement 10: Suffix Invariance Hard Law

**User Story:** As a quantitative researcher, I want all second-touch decisions at timestamp T to remain identical regardless of future timeline, so that causality is preserved and historical analysis is trustworthy.

#### Acceptance Criteria

1. WHEN evaluating second-touch state at timestamp T, THE System SHALL produce identical decisions for: Touch-2 candidate identity, Touch-Proximity ATR value, Touch-Proximity ATR source index, ProvisionalTrigger identity, ProvisionalTrigger level, SECOND_TOUCH_PROVED_BY_BOS state, entry readiness, entry price, InitialStopContract, owner identity, setup_id, retracement_id, attempt_number, SystemDirector final decision
2. THE System SHALL maintain this invariance across different future timelines: (A) prefix ending at T, (B) prefix + actual future, (C) prefix + modified future, (D) prefix + reversal future
3. THE System SHALL allow later timestamps to produce later decisions
4. THE System SHALL NOT alter historical decisions when more future data becomes available
5. THE System SHALL use only closed candles for all decisions
6. THE System SHALL NOT access future data when evaluating decisions at timestamp T
7. THE System SHALL keep historical decisions immutable

### Requirement 11: SystemDirector Final Strategy Action Authority

**User Story:** As a quantitative researcher, I want SystemDirector to remain the sole final authority for ENTRY/REENTRY/NO_ACTION decisions, so that strategy action governance is clear.

#### Acceptance Criteria

1. THE SystemDirector SHALL make final decisions on ENTRY, REENTRY, or NO_ACTION
2. THE System SHALL NOT allow any component to override SystemDirector decisions
3. THE SystemDirector SHALL authorize maximum one first attempt plus maximum one fresh-structure re-entry per setup
4. THE SystemDirector SHALL NOT authorize entry before SECOND_TOUCH_PROVED_BY_BOS state
5. THE SystemDirector SHALL respect protection-intact and setup-not-consumed requirements

### Requirement 12: Variant-Scoped Visual State Integrity

**User Story:** As a quantitative researcher, I want visual overlays to reflect variant-specific automated state accurately, so that NO_SECOND_TOUCH variants do not display authoritative second-touch BOS/stop overlays.

#### Acceptance Criteria

1. WHEN automated variant state = NO_SECOND_TOUCH, THE Visualizer SHALL NOT display authoritative second-touch BOS/stop overlay for that variant
2. WHEN automated variant state = SECOND_TOUCH_PROVED_BY_BOS, THE Visualizer SHALL display authoritative repaired overlays
3. THE Visualizer SHALL scope visual state to: CANONICAL_CONTROL, REPAIRED_SECOND_TOUCH_CANONICAL, REPAIRED_SECOND_TOUCH_EARNED_EARLY, MANUAL_SHADOW
4. THE Visualizer SHALL render MANUAL_SHADOW overlays visually distinct from automated variant overlays
5. THE Visualizer SHALL operate in read-only mode without feeding automated state

### Requirement 13: Manual Anchor Reconstruction Reports

**User Story:** As a quantitative researcher, I want four manual-anchor reconstruction reports (Touch_1, Touch_2, ProvisionalTrigger, EntryBOS), so that I can audit how automated logic handles manually anchored events without manual data feeding automated execution.

#### Acceptance Criteria

1. THE System SHALL produce Touch_1 reconstruction report comparing manual anchor to automated recognition
2. THE System SHALL produce Touch_2 reconstruction report comparing manual anchor to automated recognition
3. THE System SHALL produce ProvisionalTrigger reconstruction report comparing manual anchor to automated recognition
4. THE System SHALL produce EntryBOS reconstruction report comparing manual anchor to automated recognition
5. THE System SHALL isolate manual anchor data from automated execution logic

### Requirement 14: Full A/B/C Metrics Reconciliation Without Forced Equality

**User Story:** As a quantitative researcher, I want complete metrics for Variants A/B/C with reconciliation analysis, so that I can compare execution outcomes without forcing trade count equality.

#### Acceptance Criteria

1. THE System SHALL compute full trade metrics for Variant_A (CANONICAL_CONTROL)
2. THE System SHALL compute full trade metrics for Variant_B (REPAIRED_SECOND_TOUCH_CANONICAL)
3. THE System SHALL compute full trade metrics for Variant_C (REPAIRED_SECOND_TOUCH_EARNED_EARLY)
4. THE System SHALL produce reconciliation analysis comparing A/B/C outcomes
5. THE System SHALL NOT force trade count equality across variants

### Requirement 15: Clean-Checkout Fixture Repair

**User Story:** As a quantitative researcher, I want all test fixtures checked into version control to reproduce identical results on clean checkouts, so that tests are stable and portable.

#### Acceptance Criteria

1. THE System SHALL store test fixtures in version-controlled paths
2. WHEN a test runs on a clean git clone, THE System SHALL reproduce identical test results
3. THE System SHALL NOT depend on gitignored artifacts for test execution
4. THE System SHALL NOT depend on research_runs/s2b1/research_data_before.json or other gitignored paths
5. THE System SHALL repair any fixtures that fail clean-checkout reproduction

### Requirement 16: Research Data Full-Tree Immutability

**User Story:** As a quantitative researcher, I want research_data/ tree to remain byte-identical before and after S2B.1.1 changes, so that historical research integrity is preserved.

#### Acceptance Criteria

1. THE System SHALL compute BEFORE_HASH = hash of full research_data/ tree before S2B.1.1 changes
2. THE System SHALL compute AFTER_HASH = hash of full research_data/ tree after S2B.1.1 changes
3. THE System SHALL verify BEFORE_HASH == AFTER_HASH
4. THE System SHALL reject S2B.1.1 completion if hashes differ
5. THE System SHALL isolate new S2B.1.1 outputs to research_runs/s2b1_1/ directory

### Requirement 17: No Sibling Codex Workspace Dependency

**User Story:** As a quantitative researcher, I want S2B.1.1 to depend only on the current workspace, so that no external Codex directories are required.

#### Acceptance Criteria

1. THE System SHALL NOT depend on sibling Codex workspace paths
2. THE System SHALL NOT import from ../Codex/ or similar external directories
3. THE System SHALL NOT read configuration from external Codex workspaces
4. THE System SHALL source all code and configuration from the current workspace
5. THE System SHALL execute all tests using only current workspace resources

### Requirement 18: Full Regression Acceptance Gate

**User Story:** As a quantitative researcher, I want all new S2B.1.1 tests AND all inherited tests to pass with zero regressions, so that S2B.1.1 completion is verified comprehensively.

#### Acceptance Criteria

1. THE System SHALL pass all new S2B.1.1 tests
2. THE System SHALL pass all inherited strategy tests
3. THE System SHALL pass all inherited simulator tests
4. THE System SHALL pass end-to-end stop contract tests for BUY direction
5. THE System SHALL pass end-to-end stop contract tests for SELL direction
6. THE System SHALL pass end-to-end stop contract tests for M1 timeframe
7. THE System SHALL pass end-to-end stop contract tests for M5 timeframe
8. THE System SHALL pass suffix-invariance tests
9. THE System SHALL pass clean-checkout fixture tests
10. THE System SHALL verify research_data BEFORE_HASH == AFTER_HASH
11. THE System SHALL NOT invoke live broker order APIs
12. THE System SHALL NOT invoke demo broker order APIs
13. THE System SHALL NOT add order submission APIs
14. THE System SHALL NOT use order submission APIs

### Requirement 19: Research and Paper Scope Only

**User Story:** As a quantitative researcher, I want S2B.1.1 scope strictly limited to research and paper analysis, so that no live trading infrastructure is modified.

#### Acceptance Criteria

1. THE System SHALL limit S2B.1.1 scope to: automated second-touch recognition timing, stop contract completeness, metrics reconciliation
2. THE System SHALL NOT modify TP1 targets
3. THE System SHALL NOT modify AI integration
4. THE System SHALL NOT modify scanner infrastructure
5. THE System SHALL NOT modify HTF orchestration
6. THE System SHALL NOT modify session management
7. THE System SHALL NOT modify risk management
8. THE System SHALL NOT modify profit-taking strategies
9. THE System SHALL NOT modify live broker APIs
10. THE System SHALL NOT modify demo broker APIs

### Requirement 20: Zero Live or Demo Order API Usage

**User Story:** As a quantitative researcher, I want absolute confirmation that no live or demo order APIs are invoked, so that S2B.1.1 remains strictly research-only.

#### Acceptance Criteria

1. THE System SHALL NOT call live broker order submission APIs during S2B.1.1 execution
2. THE System SHALL NOT call demo broker order submission APIs during S2B.1.1 execution
3. THE System SHALL NOT add new order submission API functions
4. THE System SHALL NOT modify existing order submission API functions
5. THE System SHALL verify zero order API invocations in final acceptance tests
