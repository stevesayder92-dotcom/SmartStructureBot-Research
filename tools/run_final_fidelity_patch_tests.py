from __future__ import annotations

import io
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "final_fidelity_patch_v1_evidence" / "full_test_output.txt"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run() -> unittest.result.TestResult:
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    text = stream.getvalue()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return result


if __name__ == "__main__":
    outcome = run()
    raise SystemExit(0 if outcome.wasSuccessful() else 1)
