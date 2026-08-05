# Phase 5A code diff report

Baseline: accepted `SmartStructureBot_Phase4_Clean_Final`.

## Core changes

- Added `core/evidence_contract.py` as the single audit/export evidence
  vocabulary and consistency validator.
- Added `core/manual_review.py` for strict CSV validation and calibration
  analysis without threshold mutation.
- Updated `QualifiedRetracementEngine` with immutable first qualification,
  explicit initial/active trigger history, score range contract, protection
  OHLC evidence, wick survival, and impulse-cycle provenance.
- Updated `pipeline_runner.py` to publish the same fields in the canonical
  entry root.
- Updated SignalLedger and ReplayInspector to carry the canonical evidence
  fields rather than reconstructing them.
- Added optional research-only closed-data export after the safe connector
  validates candles.

## Tools and evidence

- Added evidence consistency, protection, and freshness audit/export tool.
- Added expanded Hybrid data comparison.
- Added completed-review ingestion CLI.
- Updated chart labels to distinguish first qualification, initial trigger,
  active trigger, last trigger update, capped score, and raw score.
- Added a canonical CSV and formatted XLSX review package.

## Tests

Eight Phase 5A tests cover:

- snapshot/audit/ledger agreement;
- immutable first qualification;
- active trigger updates;
- trigger setup ownership;
- stale trigger exclusion;
- body-close and wick protection;
- impulse-cycle protection provenance;
- score boundary and raw score preservation;
- manual review validation.

No simulator, order execution, stop engine, ML optimizer, automatic HTF hard
gate, or threshold change was added.

