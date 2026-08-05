from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd

from core.pipeline_runner import (
    PipelineOptions,
    _build_retracement_origin_contract,
    run_pipeline,
)
from core.setup_lifecycle import (
    SetupLifecycleRegistry,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = (
    PROJECT_ROOT
    / "test_data"
    / "GER40Cash_M5_phase3_six_entry_origins.json"
)
DATA_PATH = (
    PROJECT_ROOT
    / "test_data"
    / "GER40Cash_M5_400_raw.csv"
)


class SixEntryOriginRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = json.loads(
            FIXTURE_PATH.read_text(
                encoding="utf-8"
            )
        )
        cls.data = pd.read_csv(DATA_PATH).reset_index(
            drop=True
        )

    def test_strategy_semantics_require_bos_before_pullback(self):
        coherent = _build_retracement_origin_contract(
            origin_trend_bos_index=20,
            initial_pullback_start=24,
            current_pullback_end=30,
            as_of_index=35,
        )
        incoherent = _build_retracement_origin_contract(
            origin_trend_bos_index=20,
            initial_pullback_start=12,
            current_pullback_end=18,
            as_of_index=35,
        )

        self.assertTrue(coherent["chronology_valid"])
        self.assertFalse(
            incoherent["chronology_valid"]
        )
        self.assertEqual(
            incoherent["required_order"],
            (
                "origin_trend_bos <= initial_pullback_start "
                "<= current_pullback_end <= entry_index"
            ),
        )

    def test_all_six_legacy_candidates_are_blocked_by_default(self):
        for entry in self.entries:
            with self.subTest(
                setup_id=entry["setup_id"]
            ):
                result = run_pipeline(
                    data=self.data,
                    symbol="GER40Cash#",
                    timeframe=5,
                    as_of_index=entry[
                        "entry_index"
                    ],
                    options=PipelineOptions(),
                )
                canonical = result.snapshot["entry"]
                setup = result.snapshot["setup"]
                retracement = result.snapshot[
                    "retracement"
                ]

                self.assertFalse(canonical["ready"])
                self.assertNotEqual(
                    canonical.get("setup_id"),
                    entry["setup_id"],
                )
                if setup:
                    self.assertNotEqual(
                        setup.get("setup_id"),
                        entry["setup_id"],
                    )
                    self.assertTrue(
                        setup["origin_audit"][
                            "chronology_valid"
                        ]
                    )
                start = retracement.get(
                    "qualified_retracement_start_index"
                )
                origin = retracement.get(
                    "origin_bos_index"
                )
                if start is not None:
                    self.assertLessEqual(origin, start)

    def test_fixture_preserves_accepted_six_entry_baseline(self):
        self.assertEqual(len(self.entries), 6)
        setup_ids = {
            entry["setup_id"]
            for entry in self.entries
        }
        self.assertEqual(len(setup_ids), 6)

        for entry in self.entries:
            self.assertGreater(
                entry["entry_index"],
                entry["origin_trend_bos"],
            )
            self.assertLess(
                entry["initial_pullback_start"],
                entry["origin_trend_bos"],
            )
            self.assertTrue(
                entry[
                    "requires_manual_origin_review"
                ]
            )

    def test_micro_boundaries_merge_without_changing_identity(self):
        for entry in self.entries:
            with self.subTest(
                setup_id=entry["setup_id"]
            ):
                registry = SetupLifecycleRegistry()
                initial = registry.observe(
                    symbol="GER40Cash#",
                    timeframe=5,
                    direction=entry["direction"],
                    origin_trend_bos_index=entry[
                        "origin_trend_bos"
                    ],
                    initial_pullback_start=entry[
                        "initial_pullback_start"
                    ],
                    current_pullback_end=entry[
                        "current_pullback_end"
                    ],
                    as_of_index=entry[
                        "entry_index"
                    ]
                    - 2,
                    descriptive_status=(
                        "WAITING_FOR_TRIGGER"
                    ),
                )
                evolved = registry.observe(
                    symbol="GER40Cash#",
                    timeframe=5,
                    direction=entry["direction"],
                    origin_trend_bos_index=entry[
                        "origin_trend_bos"
                    ],
                    initial_pullback_start=entry[
                        "initial_pullback_start"
                    ]
                    + 1,
                    current_pullback_end=entry[
                        "current_pullback_end"
                    ]
                    + 1,
                    as_of_index=entry[
                        "entry_index"
                    ]
                    - 1,
                    descriptive_status=(
                        "WAITING_FOR_TRIGGER"
                    ),
                )

                self.assertEqual(
                    evolved["setup_id"],
                    initial["setup_id"],
                )
                self.assertEqual(
                    evolved[
                        "initial_pullback_start"
                    ],
                    entry[
                        "initial_pullback_start"
                    ],
                )
                self.assertEqual(
                    evolved[
                        "current_pullback_end"
                    ],
                    entry[
                        "current_pullback_end"
                    ]
                    + 1,
                )
                self.assertTrue(
                    evolved["origin_audit"][
                        "micro_structures_merged"
                    ]
                )
                self.assertTrue(
                    evolved["origin_audit"][
                        "requires_manual_origin_review"
                    ]
                )

    def test_post_consumption_cycle_requires_later_start(self):
        entry = self.entries[0]
        registry = SetupLifecycleRegistry()
        setup = registry.observe(
            symbol="GER40Cash#",
            timeframe=5,
            direction=entry["direction"],
            origin_trend_bos_index=entry[
                "origin_trend_bos"
            ],
            initial_pullback_start=entry[
                "initial_pullback_start"
            ],
            current_pullback_end=entry[
                "current_pullback_end"
            ],
            as_of_index=entry["entry_index"] - 1,
            descriptive_status=(
                "WAITING_FOR_TRIGGER"
            ),
        )
        registry.consume(
            setup["setup_id"],
            entry["entry_index"],
        )
        old_compression = registry.observe(
            symbol="GER40Cash#",
            timeframe=5,
            direction=entry["direction"],
            origin_trend_bos_index=(
                entry["origin_trend_bos"] + 10
            ),
            initial_pullback_start=(
                entry["entry_index"] - 1
            ),
            current_pullback_end=(
                entry["entry_index"] + 2
            ),
            as_of_index=entry["entry_index"] + 2,
            descriptive_status=(
                "WAITING_FOR_TRIGGER"
            ),
        )
        new_cycle = registry.observe(
            symbol="GER40Cash#",
            timeframe=5,
            direction=entry["direction"],
            origin_trend_bos_index=(
                entry["origin_trend_bos"] + 20
            ),
            initial_pullback_start=(
                entry["entry_index"] + 1
            ),
            current_pullback_end=(
                entry["entry_index"] + 5
            ),
            as_of_index=entry["entry_index"] + 5,
            descriptive_status=(
                "WAITING_FOR_TRIGGER"
            ),
        )

        self.assertEqual(
            old_compression["setup_id"],
            setup["setup_id"],
        )
        self.assertNotEqual(
            new_cycle["setup_id"],
            setup["setup_id"],
        )

    def test_new_impulse_terminates_old_compression(self):
        registry = SetupLifecycleRegistry()
        old = registry.observe(
            symbol="GER40Cash#",
            timeframe=5,
            direction="BULLISH",
            origin_trend_bos_index=10,
            initial_pullback_start=12,
            current_pullback_end=20,
            as_of_index=25,
            descriptive_status="WAITING_FOR_TRIGGER",
        )
        closed = registry.close_for_new_impulse(
            old["setup_id"],
            31,
            new_origin_trend_bos_index=30,
        )
        new = registry.observe(
            symbol="GER40Cash#",
            timeframe=5,
            direction="BULLISH",
            origin_trend_bos_index=30,
            initial_pullback_start=32,
            current_pullback_end=36,
            as_of_index=40,
            descriptive_status="WAITING_FOR_TRIGGER",
        )

        self.assertEqual(closed["status"], "CLOSED")
        self.assertNotEqual(
            old["setup_id"],
            new["setup_id"],
        )
        self.assertLessEqual(
            new["origin_trend_bos"],
            new["initial_pullback_start"],
        )


if __name__ == "__main__":
    unittest.main()
