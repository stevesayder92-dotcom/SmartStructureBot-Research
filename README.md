# SmartStructureBot Phase S1B Realistic Paper Laboratory

Completion evidence and readiness verdict: [PHASE_S1B_FINAL_REPORT.md](PHASE_S1B_FINAL_REPORT.md)

Phase S1B preserves the frozen `SMARTSTRUCTUREBOT_SIMULATOR_BASELINE_V0_9`
strategy and adds a separate deterministic ZAR paper broker, realistic account
feasibility, bid/ask fills, spread, slippage, commissions, optional swap,
margin, partials, paper tickets, money story, equity and independent shadow
accounts. The simulator also provides synchronized M5/M1 charts, immutable
events, rewind, bot-brain observability, dynamic configured-range builds and
portable data/export packages.

No strategy rule was changed. No order API is enabled, imported or called.
This is historical paper research—not forward demo execution.

## Install and launch on Windows

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
.\run_simulator.bat
```

Or launch explicitly:

```powershell
python run_simulator.py --port 8765
```

## Headless replay and verification

```powershell
python -m simulator.cli cases --limit 12
python -m simulator.cli build --case 2 --before-minutes 25 --after-minutes 35
python -m simulator.cli library
python tools\build_phase_s1b_evidence.py
python -m unittest discover -s simulator\tests -p "test_*.py" -v
python -m unittest discover -s tests -p "test_*.py" -v
```

The 12 accepted Phase S1 sessions are in `simulator_evidence\sessions`; the
portable configured library is in `simulator_data\library`. The 20 financial
acceptance scenarios and three-capital report are in `phase_s1b_evidence`.
Start with `S1-CASE-02` for the investor M1 example and `S1-CASE-10` for the
losing/risk-discipline example. Documentation is indexed by `docs\S1_*.md`.

Visible disclaimer: historical closed-candle research replay; no live orders;
performance is not guaranteed.

---

# SmartStructureBot Simulator Baseline V0.9

This release is the **Final Prefix-Causal Integrity Repair**. The exact 60 first entries, IDs, splits, Fibonacci rules, stops, targets, management thresholds and one-re-entry ceiling are frozen. Parent review, M1/M5 re-entry discovery and Attempt-2 trails now process immutable closed-candle prefix events.

Authoritative version: `SMARTSTRUCTUREBOT_SIMULATOR_BASELINE_V0_9`.

```powershell
python -m unittest tests.test_final_prefix_causality -v
python -m unittest discover -s tests -p "test_*.py"
python tools\run_final_prefix_causal_repair.py
```

Open `final_prefix_causal_evidence\final_prefix_causal_review.html` for the exact-60 review and `final_prefix_causal_evidence\trade_51\trade_51_chronological_report.md` for the mandatory Trade 51 chronology.

All causal acceptance gates pass. This is ready to become the candle-by-candle simulator baseline, but it is not Strategy V1.0 and is not automatic-demo-ready. Order execution remains disabled.

---

# Previous Pre-Simulator Canonical Repair

This is the repaired hybrid research build based on the canonical FinalSequenceElite repository. Its 60 first entries are frozen. Attempt 1 uses accepted Final Fidelity Patch v1 management; strategic re-entry, complete Attempt-2 management, chronological sequence accounting, causal partial decisions, and emergency-risk sizing are repaired in the hybrid layer.

Current verdict: **EXPERIMENTAL_SIMULATOR_READY**. This permits candle-by-candle simulator development only. Demo and live order execution remain disabled.

## Rebuild and verify this repair

```powershell
python -m unittest tests.test_presimulator_repair
python -m unittest discover -s tests -p "test_*.py"
python tools\run_presimulator_repair.py
```

Open `presimulator_repair_evidence\presimulator_repair_review.html` for the 60-case chart review. Trade 51 has a dedicated package in `presimulator_repair_evidence\trade_51`.

The authoritative rules are in `SmartStructureBot_Bible.md`; the exact baseline/current/repaired ownership choices are in `docs\PreSimulator_Baseline_Current_Hybrid_Merge_Map.md`.

---

# Previous Final Fidelity research release

## Final Fidelity Patch v1 research commands

The patch remains closed-candle research only. It never calls an order API.

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python tools/run_final_fidelity_patch_v1.py
```

Open `final_fidelity_patch_v1_evidence/final_fidelity_patch_v1_review.html`
for the 60-case synchronized review and
`final_fidelity_patch_v1_evidence/baseline_reference.html` for the exact
40-case pre-patch reference. Development, validation and untouched holdout
results are separate. Strategy freeze is withheld unless every mandated
success criterion passes.

This release implements the final pre-simulator strategy-fidelity mandate.
The permanent source of truth is
[`SmartStructureBot_Bible.md`](SmartStructureBot_Bible.md).

The system remains research-only. `LIVE` mode is rejected, and the runtime
contains no MT5 order API call.

## What is implemented

- Steve Fibonacci remaining-impulse orientation V2;
- synchronized closed-candle M5-parent/M1-child replay;
- exact parent setup, retracement, impulse, direction, protection and Fib
  ownership on every M1 event;
- first-valid M1 entry with M5 fallback and duplicate-entry prevention;
- M1 relevant-swing body-edge stop plus a separate emergency stop;
- M1-to-M5 management transition that cannot widen protection;
- target hierarchy and wick/close/acceptance/rejection lifecycle;
- progressive protection, proven structural trails and target-rejection exit;
- one re-entry ceiling per parent M5 setup;
- M1 advantage, failure, giveback and profit-capture audits;
- 40 paired M5/M1 review charts from real closed broker candles.

## Install

Use 64-bit Python 3.12 on Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item config\research.example.json config\research.local.json
```

Edit the copied configuration for the broker's exact symbol suffixes and
server timezone.

## Safe research run

Open and log into the matching MetaTrader 5 terminal:

```powershell
python main.py --config config\research.local.json
```

Only `RESEARCH`, `REPORT`, and `PAPER_SIGNAL` are accepted. The connector
excludes the forming candle and validates staleness, duplicates, monotonic
time, gaps and minimum history.

## Final-fidelity evidence

Open:

```text
final_fidelity_evidence/final_fidelity_review.html
```

Rebuild the deterministic evidence package:

```powershell
python tools\run_final_fidelity_evidence.py
```

This is the full scan and may take several minutes. Refresh only management,
reports and the existing selected charts:

```powershell
python -c "from tools.run_final_fidelity_evidence import refresh_profit_management; refresh_profit_management()"
```

Verify the release twice against the same selected decisions:

```powershell
python tools\verify_final_fidelity_release.py
```

## Tests

```powershell
python tools\classify_tests.py
python tools\run_final_fidelity_test_suite.py
```

The exact final output is saved to
`final_fidelity_evidence/full_test_output.txt`.

## Safety boundary

- No trade simulator is included.
- No demo or live orders are placed.
- Spread metadata is retained in the source exports, but the 40-case outcome
  audit does not yet model commission, slippage, or broker execution.
- Manual chart acceptance and broader unbiased replay validation are required
  before demo execution should be considered.

## Final sequence recovery evidence

```powershell
python tools\run_sequence_elite_evidence.py
python -m unittest tests.test_sequence_elite_patch -v
python -m unittest discover -s tests -p "test_*.py" -v
```

Open `sequence_elite_evidence/sequence_elite_review.html` to review the frozen
60 cases followed by 20 separate supplementary cases. This patch is not cleared
for a candle-by-candle execution simulator or demo orders; read the readiness
verdict and unresolved-issues report first.
