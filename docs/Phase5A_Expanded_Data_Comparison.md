# Phase 5A expanded closed-data comparison

## Acquisition

The safe connector acquired and validated:

- GER40Cash# M5: 2,200 closed candles;
- GOLD# M5: 2,200 closed candles;
- existing GOLD# M1: 5,515 candles retained.

US100Cash# M5 was rejected because the broker payload returned from source
position 1 still contained a candle at or beyond the current UTC bar
boundary. The forming-candle check was not bypassed.

The exact research acquisition command used was:

```powershell
$env:PYTHONPATH='C:\Users\ST103\Documents\Codex\2026-07-18\i\work\smartstructurebot_runtime_deps'
$env:MPLBACKEND='Agg'
python main.py
```

`config/research.json` specified `candles=2200`,
`minimum_history=2000`, `replay_start_index=2199`, the exact broker symbol,
M5, UTC timestamps, and a research-only `closed_data_export_path`.

## Hybrid comparison

| Dataset | Origin BOS | Candidates | Qualified | Protection invalidations | Triggers | Unique entries | /1,000 | Bull | Bear | Chronology / future / stale / failures |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| GER40Cash# M5 2,200 | 39 | 38 | 7 | 30 | 4 | 3 | 1.4286 | 1 | 2 | 0 / 0 / 0 / 0 |
| GOLD# M5 2,200 | 51 | 48 | 6 | 39 | 0 | 0 | 0.0000 | 0 | 0 | 0 / 0 / 0 / 0 |
| GOLD# M1 5,515 | 123 | 122 | 21 | 102 | 6 | 3 | 0.5540 | 0 | 3 | 0 / 0 / 0 / 0 |

The table is a causal-availability Hybrid research comparison using one final
structure catalogue per dataset. It is not substituted for the canonical
decision-time evidence audit. The inconsistency audit separately reruns
critical entry/protection indexes through `run_pipeline`.

No policy was selected or modified because it produced more trades.

