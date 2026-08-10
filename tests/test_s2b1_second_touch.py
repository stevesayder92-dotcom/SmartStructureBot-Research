from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

import pandas as pd

from core.second_touch_structure import (
    SecondTouchConfig,
    evaluate_second_touch_structure,
    ownership_fingerprint,
    ownership_matches,
    second_touch_logical_boundary,
)
from core.synchronized_m1_replay import _first_body_close
from simulator.config import SimulatorConfig, load_config


ROOT = Path(__file__).resolve().parents[1]


class _Approx:
    def __init__(self, expected: float, tolerance: float = 1e-9):
        self.expected = float(expected)
        self.tolerance = tolerance

    def __eq__(self, actual: object) -> bool:
        return abs(float(actual) - self.expected) <= self.tolerance


class _Raises:
    def __init__(self, error: type[BaseException]):
        self.error = error

    def __enter__(self):
        return self

    def __exit__(self, error_type, error, traceback):
        if error_type is None:
            raise AssertionError(f"Expected {self.error.__name__}")
        return issubclass(error_type, self.error)


class _PytestCompatibility:
    approx = staticmethod(lambda expected: _Approx(expected))
    raises = staticmethod(lambda error: _Raises(error))


pytest = _PytestCompatibility()


def _data(rows: int = 40) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": [float(60 * index) for index in range(rows)],
            "open": [9.5] * rows,
            "high": [10.0] * rows,
            "low": [9.0] * rows,
            "close": [9.5] * rows,
        }
    )


def _owner(direction: str = "BEARISH") -> dict:
    return {
        "parent_setup_id": "PARENT-1",
        "retracement_id": "RET-1",
        "impulse_cycle_id": "IMPULSE-1",
        "direction": direction,
        "dominant_protection_identity": "PROTECTION-1",
        "fib_anchor_version": "FIB-1",
    }


def _point(side: str, index: int, price: float, available: int | None = None) -> dict:
    return {
        "side": side,
        "index": index,
        "level": price,
        "confirmed_at_index": index + 2 if available is None else available,
        "swing_id": f"{side}-{index}",
    }


def _bearish_swings() -> list[dict]:
    return [
        _point("HIGH", 5, 10.00, 7),
        _point("LOW", 9, 9.00, 11),
        _point("HIGH", 13, 10.10, 15),
        _point("LOW", 17, 9.20, 19),
    ]


def _bullish_swings() -> list[dict]:
    return [
        _point("LOW", 5, 9.00, 7),
        _point("HIGH", 9, 10.00, 11),
        _point("LOW", 13, 9.10, 15),
        _point("HIGH", 17, 9.90, 19),
    ]


def _evaluate(swings: list[dict], direction: str = "BEARISH", as_of: int = 19, **kwargs):
    owner = kwargs.pop("owner", _owner(direction))
    return evaluate_second_touch_structure(
        data=kwargs.pop("data", _data()),
        swings=swings,
        direction=direction,
        as_of_index=as_of,
        setup_start_index=kwargs.pop("setup_start_index", 0),
        owner=owner,
        expected_owner=kwargs.pop("expected_owner", owner),
        **kwargs,
    )


def test_bearish_double_top_uses_wick_extremes():
    result = _evaluate(_bearish_swings())
    assert result["state"] == "SECOND_TOUCH_CONFIRMED"
    assert result["touch_2"]["price"] == 10.10


def test_bullish_double_bottom_uses_wick_extremes():
    result = _evaluate(_bullish_swings(), "BULLISH")
    assert result["state"] == "SECOND_TOUCH_CONFIRMED"
    assert result["touch_2"]["price"] == 9.10


def test_touch_two_is_absent_before_confirmation_delay():
    assert _evaluate(_bearish_swings(), as_of=14)["state"] == "NO_SECOND_TOUCH"


def test_touch_two_candidate_exists_before_new_trigger_confirmation():
    result = _evaluate(_bearish_swings(), as_of=18)
    assert result["state"] == "SECOND_TOUCH_CANDIDATE"
    assert result["old_trigger_superseded"] is True


def test_second_touch_trigger_is_reaction_after_touch_two():
    result = _evaluate(_bearish_swings())
    assert result["active_trigger"]["swing_index"] == 17
    assert result["active_trigger"]["swing_index"] > result["touch_2"]["swing_index"]


def test_old_trigger_is_explicitly_superseded():
    assert _evaluate(_bearish_swings())["old_trigger_superseded"] is True


def test_second_touch_logical_stop_owner_is_touch_two():
    result = _evaluate(_bearish_swings())
    assert result["logical_stop_owner"] == result["touch_2"]


def test_exact_price_equality_is_not_required():
    assert _evaluate(_bearish_swings())["touch_distance"] == pytest.approx(0.1)


def test_touch_distance_beyond_atr_tolerance_is_rejected():
    swings = _bearish_swings()
    swings[2]["level"] = 10.8
    assert _evaluate(swings)["state"] == "SECOND_TOUCH_TOO_DISTANT"


def test_adjacent_touch_noise_is_rejected():
    swings = _bearish_swings()
    swings[2]["index"] = 7
    swings[2]["confirmed_at_index"] = 9
    assert _evaluate(swings)["state"] == "SECOND_TOUCH_REJECTED_NOISE"


def test_missing_separating_reaction_is_rejected():
    swings = [point for point in _bearish_swings() if point["index"] != 9]
    assert _evaluate(swings)["state"] == "SECOND_TOUCH_REJECTED_NOISE"


def test_micro_separating_reaction_is_rejected():
    swings = _bearish_swings()
    swings[1]["level"] = 9.9
    assert _evaluate(swings)["state"] == "SECOND_TOUCH_REJECTED_NOISE"


def test_foreign_parent_ownership_is_rejected():
    expected = _owner()
    candidate = {**expected, "parent_setup_id": "FOREIGN"}
    result = _evaluate(_bearish_swings(), owner=candidate, expected_owner=expected)
    assert result["state"] == "SECOND_TOUCH_FOREIGN_PARENT"


def test_timestamp_proximity_cannot_replace_owner_identity():
    expected = _owner()
    candidate = {**expected, "retracement_id": "OTHER"}
    assert not ownership_matches(expected, candidate)


def test_complete_owner_fingerprint_is_stable():
    assert ownership_fingerprint(_owner()) == ownership_fingerprint(dict(_owner()))


def test_consumed_setup_rejects_second_touch():
    result = _evaluate(_bearish_swings(), setup_consumed=True)
    assert result["state"] == "SECOND_TOUCH_AFTER_CONSUMPTION"


def test_failed_dominant_protection_rejects_second_touch():
    result = _evaluate(_bearish_swings(), protection_intact=False)
    assert result["state"] == "SECOND_TOUCH_PROTECTION_FAILED"


def test_setup_start_excludes_old_foreign_structure():
    assert _evaluate(_bearish_swings(), setup_start_index=10)["state"] == "NO_SECOND_TOUCH"


def test_wick_only_bos_is_rejected():
    data = _data(8)
    data.loc[4, ["open", "high", "low", "close"]] = [9.5, 9.7, 8.8, 9.2]
    index, rejects = _first_body_close(
        data=data, start_index=4, end_index=4, direction="BEARISH", trigger_level=9.0
    )
    assert index is None
    assert rejects[0]["state"] == "M1_WICK_ONLY_BOS_REJECTED"


def test_body_close_bos_is_accepted():
    data = _data(8)
    data.loc[4, ["open", "high", "low", "close"]] = [9.5, 9.6, 8.7, 8.9]
    index, _ = _first_body_close(
        data=data, start_index=4, end_index=4, direction="BEARISH", trigger_level=9.0
    )
    assert index == 4


def test_wrong_direction_body_close_is_rejected():
    data = _data(8)
    data.loc[4, ["open", "high", "low", "close"]] = [8.8, 9.4, 8.7, 8.9]
    index, rejects = _first_body_close(
        data=data, start_index=4, end_index=4, direction="BEARISH", trigger_level=9.0
    )
    assert index is None
    assert rejects[-1]["state"] == "M1_WRONG_BODY_DIRECTION_REJECTED"


def test_bullish_body_close_symmetry():
    data = _data(8)
    data.loc[4, ["open", "high", "low", "close"]] = [9.5, 10.3, 9.4, 10.1]
    index, _ = _first_body_close(
        data=data, start_index=4, end_index=4, direction="BULLISH", trigger_level=10.0
    )
    assert index == 4


def test_m1_m5_recognition_semantics_are_identical():
    m1 = _evaluate(_bearish_swings())
    m5 = _evaluate(_bearish_swings())
    assert (m1["state"], m1["touch_2"], m1["active_trigger"]) == (
        m5["state"], m5["touch_2"], m5["active_trigger"]
    )


def test_future_suffix_cannot_change_frozen_touch_identity():
    original = _data(40)
    modified = original.copy()
    modified.loc[25:, ["high", "low", "close"]] = [100.0, -100.0, 50.0]
    before = _evaluate(_bearish_swings(), data=original)
    after = _evaluate(_bearish_swings(), data=modified)
    assert before["touch_2"] == after["touch_2"]


def test_future_suffix_cannot_change_frozen_trigger():
    original = _evaluate(_bearish_swings())
    extra = _bearish_swings() + [_point("HIGH", 25, 30.0, 27), _point("LOW", 29, 1.0, 31)]
    frozen = _evaluate(extra, as_of=19)
    assert original["active_trigger"] == frozen["active_trigger"]


def test_post_entry_touch_cannot_rewrite_earlier_no_touch_decision():
    assert _evaluate(_bearish_swings(), as_of=12)["state"] == "NO_SECOND_TOUCH"


def test_fresh_attempt_two_can_be_recognized_after_new_start():
    swings = [
        _point("HIGH", 22, 10.0, 24),
        _point("LOW", 26, 9.0, 28),
        _point("HIGH", 30, 10.1, 32),
        _point("LOW", 34, 9.1, 36),
    ]
    assert _evaluate(swings, as_of=36, setup_start_index=20)["state"] == "SECOND_TOUCH_CONFIRMED"


def test_attempt_one_structure_cannot_be_reused_after_failure_start():
    assert _evaluate(_bearish_swings(), as_of=19, setup_start_index=20)["state"] == "NO_SECOND_TOUCH"


def test_default_feature_flag_is_off():
    assert SimulatorConfig().second_touch_enabled is False


def test_default_m1_permission_policy_is_unchanged():
    assert SimulatorConfig().m1_permission_policy == "COUNTER_CONFIRMED_ACTIVE"


def test_config_file_keeps_second_touch_research_disabled():
    assert load_config().second_touch_enabled is False


def test_published_fixed_parameters_match_bible():
    config = SimulatorConfig()
    assert (config.second_touch_proximity_atr_ratio, config.second_touch_meaningful_reaction_atr_ratio) == (0.25, 0.35)
    assert config.second_touch_minimum_separation_bars == 3


def test_invalid_proximity_configuration_is_rejected():
    with pytest.raises(ValueError):
        SecondTouchConfig(proximity_atr_ratio=0)


def test_invalid_reaction_configuration_is_rejected():
    with pytest.raises(ValueError):
        SecondTouchConfig(meaningful_reaction_atr_ratio=0)


def test_invalid_separation_configuration_is_rejected():
    with pytest.raises(ValueError):
        SecondTouchConfig(minimum_separation_bars=0)


def test_research_data_hashes_still_match_frozen_manifest():
    manifest = json.loads((ROOT / "research_runs/s2b1/research_data_before.json").read_text(encoding="utf-8-sig"))
    for record in manifest["files"]:
        path = ROOT / record["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]


def test_no_order_api_added_to_s2b1_source():
    forbidden = ("order_send(", "TRADE_ACTION_DEAL", "mt5.BUY", "mt5.SELL")
    paths = [
        ROOT / "core/second_touch_structure.py",
        ROOT / "core/expert_strategy.py",
        ROOT / "core/synchronized_m1_replay.py",
        ROOT / "core/prefix_causality.py",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert not any(token in text for token in forbidden)


def test_tp1_clarification_is_documentation_only():
    bible = (ROOT / "SmartStructureBot_Bible.md").read_text(encoding="utf-8")
    assert "Pending S2B.2 management clarification" in bible
    assert "Do not implement during S2B.1" in bible


def test_m1_second_touch_boundary_is_exact_touch_wick():
    result = second_touch_logical_boundary(
        wick_extreme=10.0,
        direction="BEARISH",
        timeframe="M1",
        causal_atr=2.0,
    )
    assert result["logical_invalidation_boundary"] == 10.0
    assert result["atr_tolerance"] == 0.0


def test_m5_second_touch_boundary_retains_causal_atr_tolerance():
    bearish = second_touch_logical_boundary(
        wick_extreme=10.0,
        direction="BEARISH",
        timeframe="M5",
        causal_atr=2.0,
    )
    bullish = second_touch_logical_boundary(
        wick_extreme=10.0,
        direction="BULLISH",
        timeframe="M5",
        causal_atr=2.0,
    )
    assert bearish["logical_invalidation_boundary"] == pytest.approx(10.3)
    assert bullish["logical_invalidation_boundary"] == pytest.approx(9.7)


class SecondTouchContractTests(unittest.TestCase):
    """Expose the contract functions to the repository's unittest runner."""


for _name, _function in list(globals().items()):
    if _name.startswith("test_") and callable(_function):
        setattr(
            SecondTouchContractTests,
            _name,
            lambda self, function=_function: function(),
        )
