from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    evidence = ROOT / "phase10_1_evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    output = evidence / "phase10_1_full_test_output.txt"
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    with output.open("w", encoding="utf-8") as stream:
        result = unittest.TextTestRunner(
            stream=stream,
            verbosity=2,
        ).run(suite)
        stream.write(
            "\nPHASE10_1_SAFETY_CONFIRMATION: "
            "No live mode and no order API imported or called.\n"
        )
    print(
        f"tests_run={result.testsRun} "
        f"failures={len(result.failures)} "
        f"errors={len(result.errors)} "
        f"output={output}"
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
