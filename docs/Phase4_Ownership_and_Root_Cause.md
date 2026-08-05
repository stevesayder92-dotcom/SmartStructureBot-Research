# Phase 4 ownership and root-cause trace

## Root cause

The previous broad-compression defect came from two independent clocks.
`MasterStructureState._attach_active_retracement()` selected every recent
counter-type swing from the final fourteen structure points and assigned the
first and last of those points as the active retracement boundaries. It did
not require an origin BOS, an internal continuation-structure break, or
post-origin chronology. `RetracementManager` copied those boundaries.
Separately, the pipeline selected a later “latest trend BOS” as the setup
origin. `SetupLifecycleRegistry` then encoded the old boundary and the later
BOS into one identity. The resulting setup could therefore claim a pullback
that had already existed before its alleged impulse origin.

Phase 4 removes that split ownership. The old result is retained only as
`legacy_active_retracement` for descriptive audit evidence and is cleared
before any canonical decision. `QualifiedRetracementEngine` now selects the
same-direction origin BOS, discovers the first post-origin internal break,
checks protection, assesses relative significance, confirms qualification,
and selects a post-qualification failure trigger. The pipeline creates a
setup only from that contract and only after unconditional chronology
validation.

## Canonical field map

| Field | File / class / method | First assignment and later mutation | Canonical owner | Consumer | Source and causal timestamps |
|---|---|---|---|---|---|
| `setup_origin_bos` | `core/qualified_retracement.py` / `QualifiedRetracementEngine.analyze()` and `_origin_contract()` | Assigned from a causally visible, same-direction, non-extension BOS. Never replaced by an arbitrary later dataset BOS. | `QualifiedRetracementEngine` | pipeline origin audit, protection adapter, setup registry, Director root `retracement` | Source is `atr_bos_events`. `detected_at_index`, `confirmed_at_index`, and `decision_available_at_index` are copied from the selected event and must all be no later than the decision candle. |
| decision protected swing | `core/qualified_retracement.py` / `_decision_protection()` | Selected from a causal meaningful HL for bullish trend or LH for bearish trend at/before the origin. Its intact/broken status may evolve; its identity does not drift inside the setup. | `QualifiedRetracementEngine` | structure validation, Director root `protection`, EntryValidator | Source is approved structure points or the causal supplied protection point. Detection is the structure index; confirmation/availability are the point’s confirmation/tradeability indexes. |
| `active_retracement.start_index` | `QualifiedRetracementEngine.analyze()` then adapter in `core/pipeline_runner.py` | Set to the first causal body-close break of approved internal continuation structure after origin. It is not sourced from the old fourteen-point window. | `QualifiedRetracementEngine`; pipeline is adapter only | ContinuationEngine and descriptive market consumers | `detected_at_index`, `confirmed_at_index`, and `decision_available_at_index` equal the break candle unless the source contract supplies a later causal availability. |
| `active_retracement.end_index` / `current_pullback_end` | `QualifiedRetracementEngine.analyze()` then pipeline adapter | Evolves to the current causal decision boundary. This mutable boundary is excluded from setup identity. | `QualifiedRetracementEngine` | lifecycle adapter, setup registry, reporting | Available on the current `as_of_index`; it cannot exceed that index. |
| qualification index | `QualifiedRetracementEngine._qualification_index()` | First assigned when the configured significance model and supporting counter-structure become causally sufficient. It remains at the first qualifying candle. | `QualifiedRetracementEngine` | setup creation, trigger selector, Director retracement contract | Derived only from causal counter points/significance evidence. `qualification_available_at_index` is the same or later causal availability, never future data. |
| broken internal continuation structure | `QualifiedRetracementEngine._first_counter_break()` | Assigned once from the meaningful impulse-leg high (bearish trend) or low (bullish trend) broken by a directional body close. | `QualifiedRetracementEngine` | candidate contract, significance assessment, visual/review output | Source point carries `index`, `price`, `confirmed_at_index`, `tradeable_at_index`, `origin_bos_index`, importance, role, and `causal_valid`. |
| legacy `RetracementManager.start_index` | `core/retracement_manager.py` / `build_retracement_lifecycle()` | Historically copied `master_state.active_retracement.start_index`. It is no longer called by the canonical pipeline. | none in Phase 4 | audit/reference only | Legacy field had no origin-relative causal guarantee; it is not a decision input. |
| `SetupLifecycleRegistry.initial_pullback_start` | `core/setup_lifecycle.py` / `observe()` | Created only after `qualified=True` and chronology passes. Later observed micro-boundary changes do not overwrite the immutable first start. | `SetupLifecycleRegistry` after qualification | canonical setup, ledger, replay inspector | Source is the qualified start. Setup creation occurs at current `as_of_index` after qualification is available. |
| `current_pullback_end` | `QualifiedRetracementEngine.analyze()` and `SetupLifecycleRegistry.observe()` | Updated as the qualified setup develops. It cannot move backward before start or forward beyond `as_of_index`. | engine for analysis; registry for lifecycle history | continuation, setup history, reports | Current-candle descriptive boundary; not part of identity. |
| `setup_id` | `core/setup_lifecycle.py` / `_create_setup_id()` called by `observe()` | Created once after qualification from symbol, timeframe, direction, origin BOS index, and qualified start. It changes only after a terminal setup and a genuine new impulse/pullback cycle. | `SetupLifecycleRegistry` | Director setup/entry roots, SignalLedger, ReplayInspector | Creation is causally available at the first qualified observation. No pre-origin, failure-trigger, micro-swing, end-boundary, or `as_of_index` field is used. |

## Enforced order and ownership boundary

The executable path always enforces:

`setup_origin_bos.index <= qualified_retracement_start_index <=
current_pullback_end <= entry_index <= as_of_index`

The former `enforce_retracement_origin=False` constructor field remains only
for source compatibility with old callers; Phase 4 intentionally ignores it
and does not permit it to bypass chronology. Neither `main.py`,
`SignalLedger`, nor `ReplayInspector` reconstructs any of these fields.

