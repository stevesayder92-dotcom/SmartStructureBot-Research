# Developer guide

Strategy behavior stays in `core/`. The simulator may call existing canonical
functions only through `CanonicalPipelineAdapter`. Do not port logic to
JavaScript or make `SignalLedger`/UI own an action.

Build one case:

```powershell
python -m simulator.cli build --case 2 --before-minutes 25 --after-minutes 35
```

Build curated evidence:

```powershell
python tools\build_phase_s1_evidence.py
```

Run the S1 and baseline tests:

```powershell
python -m unittest simulator.tests.test_phase_s1_contract -v
python -m unittest discover -s tests -p "test_*.py" -v
```

When changing replay infrastructure: update the Bible, code, regenerated
evidence and tests in that order. Keep event JSON stable or increment the schema
version. Any new advice must remain non-authoritative. Any new flag needs an
evidence payload, suggested question and isolation test. Never add order APIs.
