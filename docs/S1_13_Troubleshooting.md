# Troubleshooting

- **No sessions:** run `python tools\build_phase_s1_evidence.py` and reload.
- **Port in use:** launch with `python run_simulator.py --port 8877`.
- **Session unavailable:** verify `session.json.gz` and `manifest.json` exist.
- **Blank M5 at event zero:** the package is stale; rebuild with the Phase S1
  kernel that seeds the final already-closed M5 candle.
- **Causality FAIL:** playback intentionally pauses. Open Debug mode, inspect
  flags, state difference and the event export. Do not bypass the check.
- **Charts crowded:** use a review preset or toggle layers; state is unchanged.
- **Slow evidence build:** canonical replay is CPU-bound. Use two workers; the
  benchmark is not a trading result.
- **Review not saved:** ensure the project directory is writable.
- **Dependency error:** activate the intended venv and reinstall requirements.

Never “fix” a red integrity state by weakening assertions, reading the future
suffix or bypassing the Director.
