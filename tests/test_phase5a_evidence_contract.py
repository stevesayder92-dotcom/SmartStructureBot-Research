from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from core.evidence_contract import (
    EVIDENCE_FIELDS,
    canonical_entry_evidence,
)
from core.manual_review import (
    REQUIRED_REVIEW_COLUMNS,
    analyze_reviews,
    validate_review_frame,
)
from core.pipeline_runner import PipelineOptions, run_pipeline
from core.qualified_retracement import (
    QualifiedRetracementEngine,
)
from core.signal_ledger import SignalLedger


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Phase5AEvidenceContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gold = pd.read_csv(
            PROJECT_ROOT / "research_data" / "GOLD_M1.csv"
        ).reset_index(drop=True)
        cls.entry_3064 = run_pipeline(
            data=cls.gold,
            symbol="GOLD#",
            timeframe="M1",
            as_of_index=3064,
            options=PipelineOptions(),
        )

    def test_audit_export_and_ledger_use_canonical_snapshot(self):
        snapshot = self.entry_3064.snapshot
        evidence = canonical_entry_evidence(snapshot)
        entry = snapshot["entry"]
        for field in EVIDENCE_FIELDS:
            self.assertEqual(
                entry.get(field),
                evidence.get(field),
                field,
            )
        ledger = SignalLedger()
        event = ledger.record_snapshot(
            snapshot,
            self.gold.iloc[3064].to_dict(),
        )
        self.assertIsNotNone(event)
        assert event is not None
        for field in EVIDENCE_FIELDS:
            self.assertEqual(
                getattr(event, field),
                evidence.get(field),
                field,
            )

    def test_first_qualification_is_immutable(self):
        later = run_pipeline(
            data=self.gold,
            symbol="GOLD#",
            timeframe="M1",
            as_of_index=3070,
            options=PipelineOptions(),
        )
        first = self.entry_3064.snapshot["retracement"]
        second = later.snapshot["retracement"]
        self.assertEqual(
            first["first_candidate_index"],
            second["first_candidate_index"],
        )
        self.assertEqual(
            first["first_qualification_index"],
            second["first_qualification_index"],
        )
        self.assertEqual(
            first["qualification_available_at_index"],
            first["first_qualification_index"],
        )

    def test_explicit_active_trigger_updates(self):
        data = pd.DataFrame(
            [
                {
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                }
                for _ in range(20)
            ]
        )
        engine = QualifiedRetracementEngine(
            data,
            as_of_index=19,
        )
        points = [
            {
                "type": "HL",
                "side": "LOW",
                "index": 8,
                "body_price": 99.0,
                "confirmed_at_index": 10,
                "decision_weight": 3,
            },
            {
                "type": "HL",
                "side": "LOW",
                "index": 12,
                "body_price": 98.5,
                "confirmed_at_index": 14,
                "decision_weight": 4,
            },
        ]
        history = engine._failure_trigger_history(
            trend="BEARISH",
            qualification_index=6,
            points=points,
            origin_index=3,
            candidate_index=5,
        )
        self.assertEqual(
            history[0]["trigger"]["index"],
            8,
        )
        self.assertEqual(
            history[-1]["trigger"]["index"],
            12,
        )
        self.assertEqual(len(history) - 1, 1)
        self.assertTrue(
            history[-1]["trigger"][
                "belongs_to_same_qualified_retracement"
            ]
        )

    def test_no_stale_trigger_from_previous_setup(self):
        data = pd.DataFrame(
            [
                {
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                }
                for _ in range(15)
            ]
        )
        engine = QualifiedRetracementEngine(
            data,
            as_of_index=14,
        )
        history = engine._failure_trigger_history(
            trend="BEARISH",
            qualification_index=8,
            points=[
                {
                    "type": "HL",
                    "side": "LOW",
                    "index": 4,
                    "body_price": 99.0,
                    "confirmed_at_index": 5,
                    "decision_weight": 5,
                },
                {
                    "type": "HL",
                    "side": "LOW",
                    "index": 10,
                    "body_price": 98.0,
                    "confirmed_at_index": 12,
                    "decision_weight": 3,
                },
            ],
            origin_index=6,
            candidate_index=7,
        )
        self.assertEqual(len(history), 1)
        self.assertEqual(
            history[0]["trigger"]["index"],
            10,
        )

    def test_protection_body_close_and_wick_contract(self):
        data = pd.DataFrame(
            [
                {
                    "open": 102.0,
                    "high": 103.0,
                    "low": 101.0,
                    "close": 102.0,
                },
                {
                    "open": 102.0,
                    "high": 103.0,
                    "low": 99.0,
                    "close": 101.0,
                },
                {
                    "open": 101.0,
                    "high": 102.0,
                    "low": 98.0,
                    "close": 99.0,
                },
            ]
        )
        protected = {"level": 100.0}
        wick_engine = QualifiedRetracementEngine(
            data,
            as_of_index=1,
        )
        self.assertIsNone(
            wick_engine._protected_violation_evidence(
                trend="BULLISH",
                protected=protected,
                start=1,
            )
        )
        self.assertTrue(
            wick_engine._protected_wick_crossings(
                trend="BULLISH",
                protected=protected,
                start=1,
            )[0]["survived"]
        )
        body_engine = QualifiedRetracementEngine(
            data,
            as_of_index=2,
        )
        violation = (
            body_engine._protected_violation_evidence(
                trend="BULLISH",
                protected=protected,
                start=1,
            )
        )
        self.assertIsNotNone(violation)
        assert violation is not None
        self.assertTrue(violation["body_close_crossed"])
        self.assertFalse(violation["wick_only"])

    def test_protection_belongs_to_origin_cycle(self):
        protected = self.entry_3064.snapshot[
            "retracement"
        ]["decision_protected_swing"]
        self.assertTrue(
            protected["belongs_to_origin_impulse_cycle"]
        )
        self.assertLessEqual(
            protected["impulse_cycle_start_index"],
            protected["index"],
        )
        self.assertLess(
            protected["index"],
            protected["origin_bos_index"],
        )

    def test_score_range_contract_preserves_raw_score(self):
        retracement = self.entry_3064.snapshot[
            "retracement"
        ]
        significance = retracement["significance"]
        self.assertEqual(
            significance["significance_score"],
            100.0,
        )
        self.assertGreater(
            significance["raw_significance_score"],
            100.0,
        )
        self.assertTrue(retracement["qualified"])

    def test_manual_review_import_validation(self):
        row = {column: "" for column in REQUIRED_REVIEW_COLUMNS}
        row.update(
            {
                "setup_id": "SETUP-1",
                "symbol": "GOLD#",
                "timeframe": "M1",
                "direction": "BEARISH",
                "first_candidate_index": 10,
                "first_qualification_index": 12,
                "active_failure_trigger_index": 14,
                "entry_index": 20,
                "steve_verdict": "ACCEPT",
            }
        )
        frame = pd.DataFrame([row])
        validate_review_frame(frame)
        result = analyze_reviews(frame)
        self.assertEqual(result["agreement_rate"], 1.0)
        self.assertFalse(
            result["threshold_changes_auto_applied"]
        )
        invalid = frame.copy()
        invalid.at[0, "steve_verdict"] = "YES"
        with self.assertRaises(ValueError):
            validate_review_frame(invalid)


if __name__ == "__main__":
    unittest.main()
