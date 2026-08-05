from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "test_authority_manifest.json"


def run() -> dict:
    rows = []
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.FunctionDef)
                and node.name.startswith("test_")
            ):
                continue
            authority = (
                "ACTIVE_AUTHORITATIVE"
                if path.name
                in {
                    "test_final_fidelity_contract.py",
                    "test_strategy_bible_contract.py",
                    "test_closed_candle_data_safety.py",
                    "test_main_canonical_runtime.py",
                }
                else "LEGACY_REGRESSION"
            )
            rows.append(
                {
                    "file": path.name,
                    "test": node.name,
                    "classification": authority,
                }
            )
    report = {
        "owner": "TestAuthorityAudit",
        "state": "ALL_TESTS_CLASSIFIED",
        "authoritative_strategy_contract": (
            "SmartStructureBot_Bible CHG-2026-07-31-FINAL-FIDELITY"
        ),
        "counts": {
            category: sum(
                row["classification"] == category for row in rows
            )
            for category in (
                "ACTIVE_AUTHORITATIVE",
                "LEGACY_REGRESSION",
                "OBSOLETE_CONFLICTING",
            )
        },
        "superseded_expectations": [
            {
                "source_test": (
                    "test_phase10_full_strategy_contract."
                    "test_01_fibonacci_anchors_are_directionally_correct"
                ),
                "classification": "OBSOLETE_CONFLICTING",
                "old_rule": "Fib 0 was impulse extreme and Fib 100 origin",
                "replacement": (
                    "Fib 0 is origin and Fib 100 is retracement-start "
                    "impulse extreme"
                ),
            },
            {
                "source_test": (
                    "test_phase10_full_strategy_contract."
                    "test_04_sweet_spot_bos_receives_high_relevance"
                ),
                "classification": "OBSOLETE_CONFLICTING",
                "old_rule": "38.2%-61.8% retracement depth was primary",
                "replacement": (
                    "23.6%-38.2% remaining impulse is Steve's primary "
                    "deep sweet spot"
                ),
            },
            {
                "source": "M1_RELEVANT_SWING_CANDLE_CLOSE terminology",
                "classification": "OBSOLETE_CONFLICTING",
                "replacement": "M1_RELEVANT_SWING_BODY_EDGE",
            },
        ],
        "tests": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps({**result["counts"], "tests": len(result["tests"])}, indent=2))
