# Phase 4 code diff report

Baseline: repaired clean Phase 3 release
`SmartStructureBot_release_clean_20260724`.

## Added

- `core/qualified_retracement.py`: causal B-with-C retracement genesis,
  internal continuation structure, relative significance models, dominant
  protection rule, failure trigger, and explicit Phase 4 state contract.
- `tests/test_phase4_qualified_retracement.py`: fifteen deterministic
  scenarios required by the mandate.
- `tests/test_phase4_real_data_integration.py`: closed GOLD data through the
  canonical Director entry path.
- `tools/run_phase4_policy_comparison.py`: frozen/comparable-data model audit.
- `tools/run_phase4_replay_audit.py`: frozen replay parity and targeted
  real-data canonical-entry audit.
- `tools/export_phase4_visual_review.py`: wide, zoom, and outcome charts plus
  manual review fields.
- `tools/fetch_phase4_closed_data.py`: closed-candle research acquisition
  helper; no order operations.
- Phase 4 ownership, specification, model/readiness, and this diff report.

## Modified

- `core/pipeline_runner.py`: removes legacy retracement ownership from the
  canonical path, runs `QualifiedRetracementEngine`, unconditionally enforces
  origin chronology, creates setup identity only after qualification, adapts
  the contract for existing ContinuationEngine/EntryValidator consumers, and
  publishes the Director `retracement` root.
- `core/system_director.py`: registers `retracement` ownership and corrects
  canonical setup ownership to `SetupLifecycleRegistry`.
- `core/application_runtime.py`: includes the canonical retracement root in
  application outputs without recomputation.
- Existing entry, root-contract, HTF, setup-consumption, and six-entry tests:
  updated to assert Phase 4 semantics while preserving the accepted Phase 3
  safety contracts.
- `README.md`: Phase 4 commands, ownership, chronology, review, and safety.

## Excluded from the clean runtime release

- legacy `core/retracement_engine.py` and `core/retracement_manager.py`;
- Phase 2/3 audit exporters;
- `__pycache__`, `.pyc`, temporary runtime dependencies, logs, numbered
  backups, and duplicate projects.

The audit working tree retains legacy source files only to document the
root-cause comparison. They are not imported by the canonical pipeline and
are not present in the clean delivery tree.

## Strategy logic deliberately not added

- trade simulation;
- live order execution;
- final stop/trailing engine;
- ML optimization;
- automatic HTF hard gating.

