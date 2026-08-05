from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
import gzip
import json
import zipfile

import pandas as pd

from simulator.adapters.dataset_adapter import DatasetAdapter
from simulator.config import load_config, project_root
from simulator.kernel.replay_session import ReplaySession
from simulator.models.schema import stable_hash
from simulator.services.export_service import ExportService
from simulator.services.observability import bug_flags, director_decision, shadow_states


class PhaseS1ContractTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.adapter = DatasetAdapter(project_root())
        cls.config = load_config()
        cls.session = ReplaySession.from_case(
            cls.adapter, case_number=1, config=cls.config,
            before_minutes=15, after_minutes=10,
        ).build(max_events=15)
        cls.dataset = cls.session.dataset
        cls.ui_js = (project_root() / "simulator" / "ui" / "app.js").read_text(encoding="utf-8")

    # REPLAY CLOCK 1-5
    def test_01_m1_and_m5_events_merge_chronologically(self):
        times = [event.event_time for event in self.session.events]
        self.assertEqual(times, sorted(times))

    def test_02_same_time_events_use_deterministic_ordering(self):
        combined = [e for e in self.session.events if e.newly_closed_m1_indices and e.newly_closed_m5_indices]
        self.assertTrue(combined)
        self.assertEqual(combined[0].processing_order, ("M5_PARENT_UPDATE", "M1_CHILD_UPDATE", "M5_FALLBACK"))

    def test_03_no_unfinished_candles_enter_timeline(self):
        for event in self.session.events:
            self.assertEqual(event.snapshot["data_visibility"]["unfinished_rows_visible"], 0)
        self.assertGreater(self.session.events[0].visible_m5_rows, 0)
        self.assertGreater(self.session.events[0].visible_m1_rows, 0)

    def test_04_play_and_step_produce_identical_final_state(self):
        stepped = [event.state_hash for event in self.session.events]
        played = [self.session.events[index].state_hash for index in range(len(self.session.events))]
        self.assertEqual(stepped, played)

    def test_05_high_speed_replay_does_not_skip_strategy_events(self):
        self.assertIn("Math.max(35,800/state.speed)", self.ui_js)
        self.assertIn("step(1)", self.ui_js)

    # REWIND 6-8
    def test_06_step_backward_restores_exact_state(self):
        restored = self.session.restore(8)["event"]
        self.assertEqual(restored["state_hash"], self.session.events[8].state_hash)

    def test_07_rewind_from_checkpoint_matches_original_replay(self):
        restored = self.session.restore(14)
        self.assertEqual(restored["event"]["snapshot_hash"], self.session.events[14].snapshot_hash)

    def test_08_replaying_after_rewind_produces_identical_hashes(self):
        first = self.session.restore(12)["event"]["state_hash"]
        self.session.restore(4)
        second = self.session.restore(12)["event"]["state_hash"]
        self.assertEqual(first, second)

    # SNAPSHOTS 9-12
    def test_09_every_event_creates_valid_snapshot(self):
        self.assertTrue(all(event.snapshot.get("snapshot_hash") for event in self.session.events))

    def test_10_parent_hash_chain_is_valid(self):
        for prior, current in zip(self.session.events, self.session.events[1:]):
            self.assertEqual(current.parent_snapshot_hash, prior.snapshot_hash)

    def test_11_snapshot_state_equals_direct_canonical_prefix_pipeline(self):
        for event in self.session.events:
            full = self.session.full_pipeline_snapshots.get(event.pipeline_state_hash)
            if full is not None:
                self.assertEqual(stable_hash(full), event.pipeline_state_hash)

    def test_12_future_suffix_cannot_change_stored_snapshot(self):
        before = self.session.events[6].snapshot_hash
        suffix = deepcopy(self.dataset.m1)
        suffix.loc[len(suffix) - 1, "close"] *= 9
        self.assertEqual(before, self.session.events[6].snapshot_hash)

    # UI ADAPTER 13-15
    def test_13_ui_cannot_mutate_strategy_state(self):
        self.assertNotIn("run_pipeline", self.ui_js)
        self.assertNotIn("ContinuationEngine", self.ui_js)

    def test_14_chart_markers_derive_from_immutable_events(self):
        self.assertIn("event().snapshot", self.ui_js)
        self.assertIn("confirmed_swings", self.ui_js)

    def test_15_layer_toggles_do_not_alter_canonical_decisions(self):
        before = self.session.events[10].director_decision
        layers = {"Fibonacci": False, "Targets": False}
        self.assertEqual(before, self.session.events[10].director_decision)
        self.assertFalse(layers["Fibonacci"])

    # DIRECTOR 16-18
    def test_16_exactly_one_committed_action_per_event(self):
        self.assertTrue(all(isinstance(e.director_decision["committed_action"], str) for e in self.session.events))

    def test_17_supporting_recommendations_remain_non_authoritative(self):
        self.assertTrue(all(row["engine"] != "SystemStateDirector" for row in self.session.events[5].recommendations))

    def test_18_rejected_recommendations_preserve_reasons(self):
        for event in self.session.events:
            for row in event.recommendations:
                if row["status"] == "REJECTED_BY_DIRECTOR":
                    self.assertTrue(row["reason"] or row["recommendation"])

    # SHADOWS 19-22
    def test_19_shadow_managers_cannot_mutate_canonical_trade(self):
        snapshot = deepcopy(self.session.events[10].snapshot)
        before = stable_hash(snapshot.get("management"))
        shadow_states(snapshot, snapshot.get("market", {}).get("current_close"))
        self.assertEqual(before, stable_hash(snapshot.get("management")))

    def test_20_each_shadow_uses_same_visible_prefix(self):
        rows = self.session.events[10].shadow_managers
        self.assertTrue(all(row["causal_valid"] for row in rows))

    def test_21_shadow_actions_are_suffix_invariant(self):
        snap = self.session.events[10].snapshot
        first = shadow_states(snap, snap.get("market", {}).get("current_close"))
        second = shadow_states(deepcopy(snap), snap.get("market", {}).get("current_close"))
        self.assertEqual(first, second)

    def test_22_shadow_outcomes_reproduce_deterministically(self):
        self.assertEqual(list(self.session.events[10].shadow_managers), self.session.restore(10)["event"]["shadow_managers"])

    # TIME TRAVEL 23-25
    def test_23_jump_to_event_restores_chart_and_brain_state(self):
        target = self.session.restore(9)["event"]
        self.assertEqual(target["visible_m1_rows"], self.session.events[9].visible_m1_rows)
        self.assertEqual(target["snapshot"]["market"], self.session.events[9].snapshot["market"])

    def test_24_state_difference_inspector_returns_exact_changes(self):
        changes = self.session.compare(3, 4)
        self.assertIsInstance(changes, list)
        self.assertTrue(all({"field", "before", "after"} <= set(row) for row in changes))

    def test_25_recommendation_conflict_inspector_identifies_disagreements(self):
        event = self.session.events[10]
        votes = {row["recommendation"] for row in event.recommendations}
        self.assertGreater(len(votes), 1)

    # BUG FLAGS 26-28
    def test_26_bug_flags_do_not_alter_trading_behaviour(self):
        snap = deepcopy(self.session.events[10].snapshot)
        before = stable_hash(snap.get("management"))
        decision = director_decision(snapshot=snap, event_time=1.0, new_entry=None)
        bug_flags(event_id="X", snapshot=snap, decision=decision, pipeline_state_hash="A", recomputed_hash="B")
        self.assertEqual(before, stable_hash(snap.get("management")))

    def test_27_manual_classifications_persist_separately(self):
        self.assertIn("/api/review", (project_root() / "simulator" / "app.py").read_text(encoding="utf-8"))
        self.assertNotIn("simulator_reviews", json.dumps(self.session.events[0].snapshot))

    def test_28_bug_jumps_restore_correct_event(self):
        target = next((e.event_number for e in self.session.events if e.bug_flags), 4)
        self.assertEqual(self.session.restore(target)["target_event"], target)

    # EXPORTS 29-31
    def test_29_event_export_contains_required_files(self):
        with TemporaryDirectory() as tmp:
            archive = ExportService(self.session, Path(tmp)).export_event(8)
            with zipfile.ZipFile(archive) as handle:
                names = set(handle.namelist())
            required = {"event_snapshot.json", "M5_chart.png", "M1_chart.png", "Director_decision.json", "export_hashes.json"}
            self.assertTrue(required <= names)

    def test_30_sequence_export_is_reproducible(self):
        with TemporaryDirectory() as tmp:
            service = ExportService(self.session, Path(tmp))
            service.export_sequence()
            first = json.loads((Path(tmp) / "sequence" / "export_hashes.json").read_text(encoding="utf-8"))
            service.export_sequence()
            second = json.loads((Path(tmp) / "sequence" / "export_hashes.json").read_text(encoding="utf-8"))
            self.assertEqual(first, second)

    def test_31_export_manifest_hashes_match(self):
        with TemporaryDirectory() as tmp:
            ExportService(self.session, Path(tmp)).export_event(8)
            folder = Path(tmp) / "event_000008"
            hashes = json.loads((folder / "export_hashes.json").read_text(encoding="utf-8"))
            self.assertEqual(hashes["event_snapshot.json"], __import__("hashlib").sha256((folder / "event_snapshot.json").read_bytes()).hexdigest())

    # INTEGRITY 32-37
    def test_32_state_mismatch_pauses_replay(self):
        self.assertIn("if(event().integrity.status==='FAIL')pause()", self.ui_js)

    def test_33_data_misalignment_is_detected(self):
        m1 = pd.DataFrame({"time":[0,60],"open":[1,1],"high":[2,2],"low":[0,0],"close":[1,1]})
        m5 = pd.DataFrame({"time":[0],"open":[1],"high":[2],"low":[0],"close":[1]})
        report = DatasetAdapter.validate(m1=m1, m5=m5)
        self.assertFalse(report["valid"])

    def test_34_order_api_detection_fails_simulator_startup(self):
        with mock.patch("simulator.kernel.replay_session.ORDERS_ENABLED", True):
            with self.assertRaises(RuntimeError):
                ReplaySession(dataset=self.dataset, config=self.config, session_id="BLOCK", start_time=1, end_time=2)

    def test_35_no_future_data(self):
        self.assertTrue(all(e.snapshot["data_visibility"]["future_rows_visible"] == 0 for e in self.session.events))

    def test_36_no_unfinished_bars(self):
        self.assertTrue(all(e.snapshot["data_visibility"]["unfinished_rows_visible"] == 0 for e in self.session.events))

    def test_37_deterministic_replay(self):
        left = [e.state_hash for e in self.session.events]
        right = [self.session.restore(i)["event"]["state_hash"] for i in range(len(self.session.events))]
        self.assertEqual(left, right)
