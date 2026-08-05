from __future__ import annotations

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    evidence = PROJECT_ROOT / "phase9_evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    output = evidence / "phase9_full_test_output.txt"
    suite = unittest.defaultTestLoader.discover(
        str(PROJECT_ROOT / "tests")
    )
    with output.open("w", encoding="utf-8") as stream:
        runner = unittest.TextTestRunner(
            stream=stream,
            verbosity=2,
        )
        result = runner.run(suite)
        stream.write(
            "\nPHASE9_SAFETY_CONFIRMATION: "
            "No order API imported or called.\n"
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
