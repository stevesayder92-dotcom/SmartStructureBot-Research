from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from core.pipeline_runner import PipelineOptions
from core.replay_inspector import ReplayInspector
from core.replay_runner import (
    ReplayOptions,
    run_replay,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = (
    PROJECT_ROOT
    / "test_data"
    / "GER40Cash_M5_400_raw.csv"
)
REQUIRED_FIELDS = {
    "availability",
    "state",
    "owner",
    "as_of_index",
    "causal_valid",
    "relevant_structure_index",
    "relevant_structure_level",
    "reasons",
}


class DirectorRootContractsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = pd.read_csv(DATA_PATH)
        cls.replay = run_replay(
            data=cls.data,
            symbol="GER40Cash#",
            timeframe=5,
            options=ReplayOptions(
                start_index=100,
                end_index=102,
            ),
            pipeline_options=PipelineOptions(
                enforce_retracement_origin=False,
            ),
        )
        cls.snapshot = (
            cls.replay.pipeline_results[-1].snapshot
        )

    def test_remaining_root_contracts_are_complete(self):
        expected_owners = {
            "protection": "ProtectedStructureEngine",
            "transition": "TransitionEngine",
            "validation": "StructureValidator",
        }

        for section, owner in (
            expected_owners.items()
        ):
            with self.subTest(section=section):
                contract = self.snapshot[section]
                self.assertTrue(
                    REQUIRED_FIELDS.issubset(
                        contract
                    )
                )
                self.assertEqual(
                    contract["owner"],
                    owner,
                )
                self.assertEqual(
                    contract["as_of_index"],
                    102,
                )
                self.assertTrue(
                    contract["causal_valid"]
                )
                self.assertIsInstance(
                    contract["reasons"],
                    list,
                )

    def test_ledger_consumes_root_contract_values(self):
        self.assertEqual(
            self.replay.ledger.entry_events(
                allowed_only=True
            ),
            [],
        )
        self.assertIsNotNone(
            self.snapshot["validation"][
                "hard_block"
            ]
        )
        self.assertIsNotNone(
            self.snapshot["validation"][
                "risk_modifier"
            ]
        )
        self.assertEqual(
            self.snapshot["retracement"]["owner"],
            "QualifiedRetracementEngine",
        )

    def test_phase4_retracement_root_is_causal(self):
        contract = self.snapshot["retracement"]
        self.assertEqual(
            contract["as_of_index"],
            102,
        )
        self.assertTrue(contract["causal_valid"])
        start = contract.get(
            "qualified_retracement_start_index"
        )
        origin = contract.get("origin_bos_index")
        if start is not None:
            self.assertLessEqual(origin, start)


if __name__ == "__main__":
    unittest.main()
