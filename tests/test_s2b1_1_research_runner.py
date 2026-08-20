from pathlib import Path

from tools import run_s2b1_1_research as r


def _variant(final=1.0, tf="M1", state="SECOND_TOUCH_PROVED_BY_BOS"):
    return {
        "entry_timeframe": tf,
        "entry_epoch": 1000.0,
        "entry_price": 10.0,
        "logical_stop": 9.0,
        "stop_distance": 1.0,
        "final_R": final,
        "result": "WIN" if final > 0 else "LOSS",
        "MFE_R": 2.0,
        "MAE_R": -0.5,
        "peak_R": 2.0,
        "giveback_R": 1.0,
        "reentry_used": False,
        "second_touch": {"state": state, "double_top_or_bottom": "DOUBLE_BOTTOM", "old_trigger_superseded": True},
        "second_touch_entry": True,
        "initial_stop_contract": {"owner_price_basis": "SECOND_TOUCH_WICK_EXTREME"},
    }


def test_anchor_identity_is_exact_and_manual_shadow_only():
    assert r.ANCHORS == (
        ("AUDUSD#", "BEARISH", "PB_2121"),
        ("USDJPY#", "BEARISH", "PB_1538"),
        ("GER40Cash#", "BEARISH", "PB_2066"),
        ("GER40Cash#", "BULLISH", "PB_2365"),
    )


def test_metric_schema_contains_locked_research_fields():
    rows = [{"A": _variant(1.0), "B": _variant(-1.0, "M5"), "C": _variant(0.5)}]
    m = r._metrics(rows, "B", total_events=3, unique_parents=1, terminal_differences=0)
    required = {
        "total_events", "unique_parent_setups", "proved_second_touch_parents", "double_tops", "double_bottoms",
        "trigger_supersessions", "terminal_population_differences", "m1_entry_count", "m5_entry_count",
        "MFE_R", "MAE_R", "peak_R", "final_R", "giveback_R", "win_rate", "expectancy_R", "profit_factor_R",
    }
    assert required <= set(m)
    assert m["m5_entry_count"] == 1
    assert m["proved_second_touch_parents"] == 1


def test_proved_state_supports_repaired_and_legacy_control():
    assert r._is_proved(_variant(state="SECOND_TOUCH_PROVED_BY_BOS"))
    assert r._is_proved(_variant(state="SECOND_TOUCH_CONFIRMED"))
    assert not r._is_proved(_variant(state="NO_SECOND_TOUCH"))


def test_missing_anchor_report_is_explicit_rejection_not_guess():
    text = r._anchor_report(None, None, "AUDUSD#", "BEARISH", "PB_2121")
    assert "REJECTED / NOT IN PAIRED POPULATION" in text


def test_runner_is_repo_local_and_output_isolated():
    source = Path(r.__file__).read_text(encoding="utf-8")
    assert "../Codex" not in source
    assert "SmartStructureBot_RealisticPaperAccount_20260803" not in source
    assert str(r.OUT).replace("\\", "/").endswith("research_runs/s2b1_1")
