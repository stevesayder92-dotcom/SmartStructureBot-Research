from __future__ import annotations

import copy
from pathlib import Path

import pandas as pd

from core.second_touch_structure import evaluate_second_touch_structure
from core.synchronized_m1_replay import build_parent_contract
from core.steve_trade_management import (
    SteveManagementConfig,
    build_initial_stop_contract,
    emergency_broker_stop,
    select_setup_logical_invalidation,
)


def _frame() -> pd.DataFrame:
    rows=[]
    for i in range(16):
        rows.append(dict(time=float(i*60), open=9.5, high=9.8, low=9.3, close=9.5))
    rows[2].update(open=9.7, high=10.0, low=9.4, close=9.7)   # historical touch-1
    rows[5].update(open=9.5, high=9.7, low=9.0, close=9.3)    # separating reaction
    rows[8].update(open=9.7, high=10.10, low=9.5, close=9.8)  # touch-2 wick candidate
    rows[9].update(open=9.7, high=9.8, low=9.20, close=9.4)   # provisional bearish trigger LOW
    rows[10].update(open=9.5, high=9.6, low=8.9, close=9.0)   # bearish body-close BOS
    return pd.DataFrame(rows)


def _owner(direction="BEARISH"):
    return {
        "parent_setup_id":"PARENT-1",
        "retracement_id":"RET-1",
        "impulse_cycle_id":"IMP-1",
        "direction":direction,
        "dominant_protection_identity":"PROT-1",
        "fib_anchor_version":"FIB-1",
    }


def _touch1_swings():
    return [{"side":"HIGH","index":2,"level":10.0,"confirmed_at_index":4,"swing_id":"H2"}]


def test_repaired_touch2_candidate_does_not_wait_for_n_right_confirmation():
    data=_frame(); owner=_owner()
    result=evaluate_second_touch_structure(
        data=data, swings=_touch1_swings(), direction="BEARISH", as_of_index=8,
        setup_start_index=0, owner=owner, expected_owner=owner, causal_repair=True,
    )
    assert result["state"] == "SECOND_TOUCH_CANDIDATE"
    assert result["touch_2"]["swing_index"] == 8
    assert result["touch_2"]["available_at_index"] == 8
    assert result["touch_proximity_atr_source_index"] == 8


def test_repaired_bearish_trigger_is_post_touch_low_and_bos_proves_it():
    data=_frame(); owner=_owner()
    result=evaluate_second_touch_structure(
        data=data, swings=_touch1_swings(), direction="BEARISH", as_of_index=10,
        setup_start_index=0, owner=owner, expected_owner=owner, causal_repair=True,
    )
    assert result["state"] == "SECOND_TOUCH_PROVED_BY_BOS"
    assert result["active_trigger"]["side"] == "LOW"
    assert result["active_trigger"]["swing_index"] == 9
    assert result["bos_proof_index"] == 10
    assert result["active_trigger"]["swing_index"] < result["bos_proof_index"]


def test_suffix_invariance_at_fixed_decision_timestamp():
    data=_frame(); owner=_owner()
    prefix=data.iloc[:11].copy()
    a=evaluate_second_touch_structure(data=prefix, swings=_touch1_swings(), direction="BEARISH", as_of_index=10, setup_start_index=0, owner=owner, expected_owner=owner, causal_repair=True)
    futures=[]
    for bump in (0.0, 5.0, -4.0):
        full=data.copy()
        full.loc[11:, ["open","high","low","close"]] = full.loc[11:, ["open","high","low","close"]] + bump
        futures.append(full)
    for full in futures:
        b=evaluate_second_touch_structure(data=full, swings=_touch1_swings(), direction="BEARISH", as_of_index=10, setup_start_index=0, owner=owner, expected_owner=owner, causal_repair=True)
        for key in ("state","touch_2_index","touch_proximity_atr_source_index","bos_proof_index"):
            assert b.get(key) == a.get(key)
        assert b["active_trigger"]["swing_index"] == a["active_trigger"]["swing_index"]
        assert b["active_trigger"]["price"] == a["active_trigger"]["price"]


def _entry_model(direction="BEARISH"):
    return {
        "setup_id":"PARENT-1",
        "retracement_id":"RET-1",
        "direction":direction,
        "entry_index":10,
        "entry_price":9.0 if direction=="BEARISH" else 10.4,
        "counter":{"index":8,"side":"HIGH" if direction=="BEARISH" else "LOW","level":10.1 if direction=="BEARISH" else 9.0,"confirmed_at_index":8},
        "trigger":{"index":9,"side":"LOW" if direction=="BEARISH" else "HIGH","level":9.2 if direction=="BEARISH" else 10.2,"confirmed_at_index":9},
        "logical_stop_structure":{
            "owner":"SecondTouchStructureEngine",
            "selection_method":"SECOND_TOUCH_WICK_EXTREME",
            "owner_price_basis":"SECOND_TOUCH_WICK_EXTREME",
            "index":8,
            "side":"HIGH" if direction=="BEARISH" else "LOW",
            "level":10.1 if direction=="BEARISH" else 9.0,
            "price":10.1 if direction=="BEARISH" else 9.0,
            "confirmed_at_index":8,
            "available_at_index":8,
        },
        "stop_level":10.5 if direction=="BEARISH" else 8.5,
    }


def test_second_touch_m1_stop_uses_exact_wick_not_body_edge():
    data=_frame(); cfg=SteveManagementConfig()
    inv=select_setup_logical_invalidation(data=data, entry_model=_entry_model(), timeframe="M1", config=cfg)
    assert inv["owner_price_basis"] == "SECOND_TOUCH_WICK_EXTREME"
    assert inv["logical_structure_level"] == 10.10
    assert inv["logical_boundary"] == 10.10
    assert inv["body_upper_edge"] != inv["logical_boundary"]


def test_second_touch_m5_sell_boundary_is_wick_plus_tolerance():
    data=_frame(); cfg=SteveManagementConfig()
    inv=select_setup_logical_invalidation(data=data, entry_model=_entry_model(), timeframe="M5", config=cfg)
    assert inv["logical_boundary"] == inv["owner_price"] + inv["atr_tolerance_value"]


def test_initial_stop_contract_is_complete_and_semantically_stable():
    data=_frame(); cfg=SteveManagementConfig()
    model=_entry_model()
    inv=select_setup_logical_invalidation(data=data, entry_model=model, timeframe="M5", config=cfg)
    emergency=emergency_broker_stop(logical_invalidation=inv, config=cfg)
    contract=build_initial_stop_contract(invalidation=inv, emergency=emergency, entry_model=model, attempt_number=1)
    required={"contract_id","contract_version","owner_type","owner_index","owner_time","owner_price","owner_price_basis","timeframe","direction","logical_structure_level","initial_logical_invalidation_level","ATR_tolerance","emergency_stop","invalidation_semantics","setup_id","retracement_id","attempt_number","contract_hash"}
    assert required <= set(contract)
    assert contract["owner_price_basis"] == "SECOND_TOUCH_WICK_EXTREME"
    frozen=copy.deepcopy(contract)
    inv["body_upper_edge"] = -999.0
    assert contract == frozen


def test_parent_contract_rejects_unavailable_fibonacci_anchors_explicitly():
    data = _frame()
    candidate = _entry_model()
    candidate.update({
        "anchor": {"index": 2, "confirmed_at_index": 4, "level": 10.0},
        "counter": {"index": 8, "confirmed_at_index": 8, "level": 10.1},
        "fibonacci": {
            "available": False,
            "reasons": ["No causally confirmed same-cycle impulse-origin swing is available"],
        },
    })
    try:
        build_parent_contract(candidate=candidate, m5_data=data, symbol="TEST#")
    except ValueError as exc:
        assert "causally available Fibonacci anchors" in str(exc)
    else:
        raise AssertionError("Unavailable Fibonacci anchors must reject parent construction")
