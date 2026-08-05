from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "final_fidelity_evidence" / "full_test_output.txt"


def run() -> unittest.result.TestResult:
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(
        str(ROOT / "tests"),
        pattern="test_*.py",
    )
    result = unittest.TextTestRunner(
        stream=stream,
        verbosity=2,
    ).run(suite)
    text = stream.getvalue()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return result


if __name__ == "__main__":
    outcome = run()
    raise SystemExit(0 if outcome.wasSuccessful() else 1)
