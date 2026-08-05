# Phase S1 simulator architecture

The simulator is a read-only shell around the frozen
`SMARTSTRUCTUREBOT_SIMULATOR_BASELINE_V0_9`.

```text
sequence_elite_source.pkl
  -> DatasetAdapter (validation and UTC normalization)
  -> ReplaySession (merged M1/M5 clock and checkpoints)
  -> CanonicalPipelineAdapter
       -> run_pipeline / SystemStateDirector
       -> synchronized M1 child engine
       -> existing management engine
  -> immutable ReplayEvent ledger
       -> recommendations and Director trace
       -> isolated shadow managers
       -> diagnostic bug flags
       -> chart/story/export projections
```

Python owns all strategy calculations. JavaScript receives immutable event
payloads and only controls presentation and navigation. The HTTP server uses
the Python standard library and exposes health, session and separate manual
review endpoints. `simulator/__init__.py` refuses startup if orders are enabled.

Primary modules:

- `simulator/adapters/dataset_adapter.py`: source loading and data validation.
- `simulator/adapters/pipeline_adapter.py`: only bridge to canonical strategy.
- `simulator/kernel/replay_session.py`: deterministic ledger and time travel.
- `simulator/services/observability.py`: advice, Director narrative, shadows and flags.
- `simulator/services/export_service.py`: reproducible evidence bundles.
- `simulator/app.py`: local research server.
- `simulator/ui/`: inspectable dual-chart application.

No UI, flag, shadow or export may write to canonical runtime state.
