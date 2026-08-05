# Windows setup

Requirements: 64-bit Python 3.12 and a modern browser. MT5 is not required for
the frozen simulator sessions.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m unittest simulator.tests.test_phase_s1_contract -v
.\run_simulator.bat
```

The launcher binds to `127.0.0.1:8765`; it does not expose the app to the
network. If that port is busy:

```powershell
python run_simulator.py --port 8877
```

Frozen evidence lives under `simulator_evidence\sessions`. Keep the project on
a local drive with write permission so manual reviews and exports can be saved.
