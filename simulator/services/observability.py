from __future__ import annotations

from typing import Any

from simulator.models.schema import BugFlag, DirectorDecision, stable_hash


EVENT_PRIORITY = {
    "BUG_FLAG_CREATED": 100,
    "TRADE_SEQUENCE_CLOSED": 95,
    "OPPOSING_BOS_EXIT": 94,
    "EXHAUSTION_EXIT": 93,
    "REENTRY_OPENED": 90,
    "FIRST_ATTEMPT_EXITED": 89,
    "FIRST_ENTRY_OPENED": 88,
    "M1_ENTRY_READY": 85,
    "M5_ENTRY_READY": 84,
    "PROTECTION_MOVED": 80,
    "TARGET_STATE_CHANGED": 75,
    "EXTENSION_PROVEN": 70,
    "RETRACEMENT_QUALIFIED": 65,
    "RETRACEMENT_BORN": 60,
    "SETUP_CREATED": 55,
    "M1_AND_M5_CLOSED": 20,
    "M5_CANDLE_CLOSED": 15,
    "M1_CANDLE_CLOSED": 10,
}

BUG_RULE_CATALOG = {
    "ENTRY": (
        "ENTRY_TOO_EARLY", "ENTRY_TOO_LATE", "M1_MICRO_BOS_ACCEPTED",
        "M1_PARENT_MISMATCH", "M5_CONFIRMATION_IGNORED", "STALE_TRIGGER_USED",
        "WRONG_CANDLE_DIRECTION", "DUPLICATE_ENTRY_ATTEMPT",
    ),
    "REENTRY": (
        "REENTRY_BEFORE_EXTENSION_PROOF", "M1_RECROSS_USED_WITHOUT_CHILD_RESET",
        "REENTRY_TOO_AGGRESSIVE", "VALID_M5_REENTRY_IGNORED",
        "PARENT_INVALID_BUT_REENTRY_ARMED", "SECOND_REENTRY_ATTEMPTED",
    ),
    "STOP": (
        "INITIAL_STOP_WRONG_OWNER", "STOP_USES_POST_ENTRY_DATA", "WICK_FALSE_STOP",
        "STOP_WIDENED", "EMERGENCY_RISK_TOO_LARGE",
        "VALID_TIGHTER_STRUCTURE_IGNORED",
    ),
    "MANAGEMENT": (
        "PROFIT_EARNED_NOT_PROTECTED", "NORMAL_PULLBACK_EXITED_EARLY",
        "TARGET_REJECTION_IGNORED", "TRAIL_AVAILABLE_NOT_USED",
        "TRAIL_MOVED_TOO_EARLY", "SEVERE_GIVEBACK", "WINNER_TO_LOSER_REVERSAL",
        "LONG_RUNNER_KILLED", "EXHAUSTION_WARNING_IGNORED",
        "ENGINE_DIRECTOR_CONFLICT",
    ),
    "SYSTEM": (
        "PREFIX_STATE_MISMATCH", "SUFFIX_INVARIANCE_FAILURE",
        "DATA_ALIGNMENT_ERROR", "STATE_HASH_MISMATCH",
        "MULTIPLE_ACTIONS_SAME_EVENT", "ORDER_API_DETECTED",
    ),
}


def _state(value: Any, fallback: str = "UNAVAILABLE") -> str:
    return str(value.get("state", fallback)) if isinstance(value, dict) else fallback


def engine_recommendations(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    entry = snapshot.get("entry") or {}
    m1 = snapshot.get("m1_entry") or {}
    management = snapshot.get("management") or {}
    protection = snapshot.get("protection") or {}
    transition = snapshot.get("transition") or {}
    context = snapshot.get("context") or {}
    latest_attempt = management.get("latest_attempt") or {}
    fresh_exit = (
        latest_attempt.get("exit_index") is not None
        and management.get("as_of_index") is not None
        and int(latest_attempt["exit_index"]) == int(management["as_of_index"])
    )
    moves = list(latest_attempt.get("trail_movements") or [])
    fresh_trail = bool(
        moves and management.get("as_of_index") is not None
        and int(moves[-1].get("as_of_index", -1)) == int(management["as_of_index"])
    )
    rows = [
        {
            "engine": "HTFContextEngine",
            "recommendation": "FOLLOW_APPROVED_HTF" if context.get("available") else "WAIT",
            "priority": 70,
            "confidence": context.get("risk_modifier"),
            "proposed_action": context.get("approved_direction"),
            "structural_owner": "H1/M30/M15",
            "reason": "; ".join((context.get("reasons") or [context.get("state", "")])[:2]),
            "status": "NOT_ACTIONABLE",
        },
        {
            "engine": "QualifiedRetracementEngine",
            "recommendation": "MONITOR_CONTINUATION" if (snapshot.get("retracement") or {}).get("qualified") else "WAIT",
            "priority": 75,
            "confidence": (snapshot.get("setup") or {}).get("risk_modifier"),
            "proposed_action": _state(snapshot.get("retracement")),
            "structural_owner": (snapshot.get("setup") or {}).get("setup_id"),
            "reason": "; ".join(((snapshot.get("retracement") or {}).get("reason") or [])[:2]),
            "status": "WAITING_FOR_CONFIRMATION",
        },
        {
            "engine": "M1ChildStructureEngine",
            "recommendation": "ENTER_M1" if m1.get("entry_ready") else "WAIT_M1_PROOF",
            "priority": 90,
            "confidence": (m1.get("entry") or {}).get("m1_quality_score"),
            "proposed_action": (m1.get("entry") or {}).get("entry_price"),
            "structural_owner": (m1.get("entry") or {}).get("parent_m5_setup_id"),
            "reason": _state(m1),
            "status": "WAITING_FOR_CONFIRMATION",
        },
        {
            "engine": "ContinuationEngine",
            "recommendation": "ENTER_M5" if entry.get("ready") else "HOLD",
            "priority": 85,
            "confidence": entry.get("risk_modifier"),
            "proposed_action": entry.get("price"),
            "structural_owner": entry.get("setup_id"),
            "reason": "; ".join((entry.get("reason") or [])[:2]),
            "status": "WAITING_FOR_CONFIRMATION",
        },
        {
            "engine": "TrailingProtectionEngine",
            "recommendation": (
                "EXIT" if fresh_exit
                else "PROTECT" if fresh_trail
                else "HOLD"
            ),
            "priority": 95,
            "confidence": 1.0 if management.get("available") else 0.0,
            "proposed_action": management.get("trailing_stop"),
            "structural_owner": (management.get("latest_attempt") or {}).get("current_protection_source"),
            "reason": _state(management),
            "status": "NOT_ACTIONABLE",
        },
        {
            "engine": "ProtectedStructureEngine",
            "recommendation": "KEEP_PARENT" if protection.get("intact", True) else "CANCEL_SETUP",
            "priority": 100,
            "confidence": 1.0,
            "proposed_action": protection.get("level"),
            "structural_owner": protection.get("type"),
            "reason": "; ".join((protection.get("reasons") or [])[:1]),
            "status": "NOT_ACTIONABLE",
        },
        {
            "engine": "TransitionEngine",
            "recommendation": "CONTINUATION_CONFIRMED" if transition.get("recovered") else "WAIT",
            "priority": 60,
            "confidence": 1.0 if transition.get("causal_valid") else 0.0,
            "proposed_action": transition.get("relevant_structure_level"),
            "structural_owner": transition.get("relevant_structure_index"),
            "reason": _state(transition),
            "status": "NOT_ACTIONABLE",
        },
    ]
    return rows


def director_decision(
    *, snapshot: dict[str, Any], event_time: float, new_entry: dict[str, Any] | None
) -> DirectorDecision:
    management = snapshot.get("management") or {}
    latest = management.get("latest_attempt") or {}
    prior = management.get("attempts") or []
    action = "NO_ACTION"
    priority = 0
    price = None
    protection = latest.get("current_protection")
    narrative = "No canonical action was required; the active structure remains under observation."
    accepted = None
    rejected: list[str] = []
    if new_entry:
        owner = str(snapshot.get("identity", {}).get("entry_owner") or "M5")
        attempt = int(new_entry.get("attempt_number") or 1)
        action = (
            f"ENTER_REENTRY_{owner}" if attempt == 2 else f"ENTER_{owner}"
        )
        priority = 90
        price = float(new_entry.get("entry_price") or new_entry.get("price"))
        accepted = f"{owner} entry recommendation"
        narrative = f"Director committed the first causally valid {owner} continuation entry."
    elif (
        latest and int(latest.get("attempt_number", 1) or 1) == 2
        and latest.get("entry_index") is not None
        and management.get("as_of_index") is not None
        and int(latest["entry_index"]) == int(management["as_of_index"])
    ):
        owner = str(latest.get("timeframe") or latest.get("entry_timeframe") or "M1")
        action = f"ENTER_REENTRY_{owner}"
        priority = 90
        price = latest.get("entry_price")
        accepted = f"{owner} re-entry recommendation"
        narrative = f"Director committed the one permitted {owner} re-entry after fresh parent proof."
    elif (
        latest and str(latest.get("status", "ACTIVE")) != "ACTIVE"
        and latest.get("exit_index") is not None
        and management.get("as_of_index") is not None
        and int(latest["exit_index"]) == int(management["as_of_index"])
    ):
        reason = str(latest.get("exit_reason") or latest.get("status"))
        action = "EXIT_OPPOSING_BOS" if "OPPOSING" in reason else "EXIT_LOGICAL"
        priority = 95
        price = latest.get("exit_price")
        accepted = "TrailingProtectionEngine exit recommendation"
        narrative = f"Director closed the attempt after {reason.replace('_', ' ').lower()}."
    elif latest and latest.get("trail_movements"):
        last_move = latest["trail_movements"][-1]
        if int(last_move.get("as_of_index", -1)) == int(management.get("as_of_index", -2)):
            action = "MOVE_TO_PROVEN_M5_STRUCTURE" if latest.get("timeframe") == "M5" else "MOVE_TO_PROVEN_M1_STRUCTURE"
            priority = 80
            protection = last_move.get("new_protection", protection)
            accepted = "TrailingProtectionEngine protection recommendation"
            narrative = "Director tightened protection to a causally proven continuation structure."
    for row in engine_recommendations(snapshot):
        if row["status"] == "WAITING_FOR_CONFIRMATION" and accepted not in (None, row["engine"]):
            rejected.append(f"{row['engine']}: {row['recommendation']}")
    return DirectorDecision(
        committed_action=action,
        priority=priority,
        timestamp=float(event_time),
        price=price,
        current_protection=protection,
        new_protection=protection,
        exit_reason=latest.get("exit_reason"),
        accepted_recommendation=accepted,
        rejected_recommendations=tuple(rejected),
        narrative=narrative,
    )


def mark_recommendation_status(
    rows: list[dict[str, Any]], decision: DirectorDecision
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        rec = str(row["recommendation"])
        if decision.committed_action.endswith("M1") and row["engine"] == "M1ChildStructureEngine":
            item["status"] = "ACCEPTED_BY_DIRECTOR"
        elif decision.committed_action.endswith("M5") and row["engine"] == "ContinuationEngine":
            item["status"] = "ACCEPTED_BY_DIRECTOR"
        elif decision.committed_action.startswith("EXIT") and row["engine"] == "TrailingProtectionEngine":
            item["status"] = "ACCEPTED_BY_DIRECTOR"
        elif rec.startswith("ENTER") or rec in {"EXIT", "PROTECT", "CANCEL_SETUP"}:
            item["status"] = "REJECTED_BY_DIRECTOR"
        elif item["status"] == "WAITING_FOR_CONFIRMATION":
            item["status"] = "WAITING_FOR_CONFIRMATION"
        else:
            item["status"] = "NOT_ACTIONABLE"
        result.append(item)
    return result


def shadow_states(snapshot: dict[str, Any], current_price: float | None) -> list[dict[str, Any]]:
    management = snapshot.get("management") or {}
    latest = management.get("latest_attempt") or {}
    if not latest:
        return [
            {"profile": name, "open": False, "current_action": "WAIT_FOR_ENTRY", "final_R": None, "causal_valid": True}
            for name in (
                "CANONICAL", "PURE_STRUCTURE_RUNNER", "TP1_PARTIAL_PLUS_RUNNER",
                "EARNED_OPPORTUNITY_MANAGER", "M5_CONFIRMATION_REENTRY", "M1_RESET_REENTRY",
            )
        ]
    entry = float(latest["entry_price"])
    stop = float(latest["logical_stop"])
    direction = str(latest["direction"])
    risk = abs(entry - stop) or 1.0
    price = float(current_price if current_price is not None else entry)
    current_r = (price - entry) / risk if direction == "BULLISH" else (entry - price) / risk
    canonical_open = str(latest.get("status")) == "ACTIVE"
    canonical_action = "HOLD" if canonical_open else str(latest.get("exit_reason") or "CLOSED")
    rows = []
    for name in (
        "CANONICAL", "PURE_STRUCTURE_RUNNER", "TP1_PARTIAL_PLUS_RUNNER",
        "EARNED_OPPORTUNITY_MANAGER", "M5_CONFIRMATION_REENTRY", "M1_RESET_REENTRY",
    ):
        action = canonical_action
        fraction = 1.0
        if name == "TP1_PARTIAL_PLUS_RUNNER" and latest.get("tp1_triggered"):
            action, fraction = "PARTIAL_TAKEN_RUNNER_OPEN", 0.5
        elif name == "EARNED_OPPORTUNITY_MANAGER" and current_r > 1.0:
            action = "PROTECT_EARNED_OPPORTUNITY"
        elif name == "PURE_STRUCTURE_RUNNER" and canonical_open:
            action = "HOLD_UNTIL_STRUCTURE_BREAK"
        rows.append(
            {
                "profile": name,
                "open": canonical_open,
                "entry": entry,
                "stop": stop,
                "position_fraction": fraction,
                "unrealized_R": round(current_r * fraction, 4),
                "peak_R": None,
                "giveback": None,
                "current_action": action,
                "final_R": None if canonical_open else round(current_r, 4),
                "deviation_from_canonical": action != canonical_action,
                "causal_valid": True,
                "immutable_decision_hash": stable_hash([name, action, round(current_r, 6)]),
            }
        )
    return rows


def bug_flags(
    *, event_id: str, snapshot: dict[str, Any], decision: DirectorDecision,
    pipeline_state_hash: str, recomputed_hash: str,
) -> list[BugFlag]:
    flags: list[BugFlag] = []
    integrity = snapshot.get("contract_health") or {}
    management = snapshot.get("management") or {}
    latest = management.get("latest_attempt") or {}
    diagnostics = snapshot.get("management_diagnostics") or {}
    previous_diagnostics = snapshot.get("previous_management_diagnostics") or {}
    m1_entry = (snapshot.get("m1_entry") or {}).get("entry") or {}
    m5_entry = snapshot.get("entry") or {}
    if pipeline_state_hash != recomputed_hash:
        flags.append(BugFlag(
            bug_flag_id=f"{event_id}|STATE_HASH_MISMATCH", event_id=event_id,
            severity="FAIL", category="SYSTEM", title="STATE_HASH_MISMATCH",
            evidence={"stored": pipeline_state_hash, "recomputed": recomputed_hash},
            affected_engine="ReplayKernel", director_action=decision.committed_action,
            suggested_review_question="Why did the reconstructed prefix differ from the stored canonical state?",
        ))
    if not bool(integrity.get("causal_valid", True)):
        flags.append(BugFlag(
            bug_flag_id=f"{event_id}|PREFIX_STATE_MISMATCH", event_id=event_id,
            severity="FAIL", category="SYSTEM", title="PREFIX_STATE_MISMATCH",
            evidence=integrity, affected_engine="SystemStateDirector",
            director_action=decision.committed_action,
        ))
    if bool(integrity.get("order_api_called", False)) or bool(management.get("order_api_called", False)):
        flags.append(BugFlag(
            bug_flag_id=f"{event_id}|ORDER_API_DETECTED", event_id=event_id,
            severity="FAIL", category="SYSTEM", title="ORDER_API_DETECTED",
            evidence={"orders": True}, affected_engine="SimulatorStartupGuard",
            director_action=decision.committed_action,
        ))
    if decision.committed_action.startswith("ENTER"):
        selected = m1_entry if "M1" in decision.committed_action else m5_entry
        entry_index = selected.get("entry_index") or selected.get("as_of_index")
        available_index = selected.get("failure_trigger_available_at_index") or selected.get("as_of_index")
        if not bool(selected.get("causal_valid", True)) or (
            entry_index is not None and available_index is not None and int(available_index) > int(entry_index)
        ):
            flags.append(BugFlag(
                bug_flag_id=f"{event_id}|ENTRY_TOO_EARLY", event_id=event_id,
                severity="FAIL", category="ENTRY", title="ENTRY_TOO_EARLY",
                evidence={"entry_index": entry_index, "proof_available_index": available_index},
                affected_engine="EntryValidator", director_action=decision.committed_action,
                suggested_review_question="Was the owned trigger legally available before the committed entry?",
            ))
        stop_index = selected.get("logical_stop_owner_index") or selected.get("logical_stop_structure_index")
        if stop_index is not None and entry_index is not None and int(stop_index) > int(entry_index):
            flags.append(BugFlag(
                bug_flag_id=f"{event_id}|STOP_USES_POST_ENTRY_DATA", event_id=event_id,
                severity="FAIL", category="STOP", title="STOP_USES_POST_ENTRY_DATA",
                evidence={"entry_index": entry_index, "stop_owner_index": stop_index},
                affected_engine="InitialStopEngine", director_action=decision.committed_action,
                suggested_review_question="Why was a stop structure unavailable at entry selected?",
            ))
        entry_price = selected.get("entry_price") or selected.get("price")
        logical_stop = selected.get("logical_stop") or selected.get("stop_level")
        direction = selected.get("parent_direction") or selected.get("direction")
        wrong_side = entry_price is not None and logical_stop is not None and (
            (direction == "BULLISH" and float(logical_stop) >= float(entry_price))
            or (direction == "BEARISH" and float(logical_stop) <= float(entry_price))
        )
        if wrong_side:
            flags.append(BugFlag(
                bug_flag_id=f"{event_id}|INITIAL_STOP_WRONG_OWNER", event_id=event_id,
                severity="FAIL", category="STOP", title="INITIAL_STOP_WRONG_OWNER",
                evidence={"direction": direction, "entry": entry_price, "stop": logical_stop},
                affected_engine="InitialStopEngine", director_action=decision.committed_action,
            ))
    if decision.committed_action.startswith("ENTER_REENTRY"):
        extension = bool(
            management.get("parent_extension_proven")
            or management.get("extension_proven")
            or any(
                row.get("event") in {"PARENT_EXTENSION_PROVEN", "FRESH_QUALIFIED_REENTRY_BOS"}
                for row in (management.get("history") or [])
            )
        )
        if not extension:
            flags.append(BugFlag(
                bug_flag_id=f"{event_id}|REENTRY_BEFORE_EXTENSION_PROOF", event_id=event_id,
                severity="FAIL", category="REENTRY", title="REENTRY_BEFORE_EXTENSION_PROOF",
                evidence={"parent_extension_proven": extension},
                affected_engine="ReentryEngine", director_action=decision.committed_action,
            ))
    if int(management.get("reentry_count", 0) or 0) > 1:
        flags.append(BugFlag(
            bug_flag_id=f"{event_id}|SECOND_REENTRY_ATTEMPTED", event_id=event_id,
            severity="FAIL", category="REENTRY", title="SECOND_REENTRY_ATTEMPTED",
            evidence={"reentry_count": management.get("reentry_count")},
            affected_engine="ReentryEngine", director_action=decision.committed_action,
        ))
    if (
        float(diagnostics.get("current_giveback_R", 0.0) or 0.0) >= 2.0
        and float(previous_diagnostics.get("current_giveback_R", 0.0) or 0.0) < 2.0
    ):
        flags.append(BugFlag(
            bug_flag_id=f"{event_id}|SEVERE_GIVEBACK", event_id=event_id,
            severity="REVIEW", category="MANAGEMENT", title="SEVERE_GIVEBACK",
            evidence={"peak_R": diagnostics.get("peak_attempt_R"), "current_R": diagnostics.get("current_attempt_R"), "giveback_R": diagnostics.get("current_giveback_R")},
            affected_engine="TrailingProtectionEngine", director_action=decision.committed_action,
            suggested_review_question="Was a causally proven tighter structure available before this giveback?",
        ))
    if diagnostics.get("valid_tighter_structure") and decision.committed_action in {"NO_ACTION", "HOLD"}:
        flags.append(BugFlag(
            bug_flag_id=f"{event_id}|VALID_TIGHTER_STRUCTURE_IGNORED", event_id=event_id,
            severity="REVIEW", category="STOP", title="VALID_TIGHTER_STRUCTURE_IGNORED",
            evidence={"recommended": diagnostics.get("recommended_action"), "committed": decision.committed_action},
            affected_engine="TrailingProtectionEngine", director_action=decision.committed_action,
        ))
    if latest:
        entry = float(latest.get("entry_price", 0.0))
        stop = float(latest.get("logical_stop", entry))
        current = (snapshot.get("market") or {}).get("current_close")
        if current is not None and entry != stop:
            risk = abs(entry - stop)
            current_r = (float(current) - entry) / risk if latest.get("direction") == "BULLISH" else (entry - float(current)) / risk
            if (
                current_r < 0 and latest.get("tp1_triggered")
                and float(previous_diagnostics.get("current_attempt_R", 0.0) or 0.0) >= 0.0
            ):
                flags.append(BugFlag(
                    bug_flag_id=f"{event_id}|WINNER_TO_LOSER_REVERSAL", event_id=event_id,
                    severity="WARNING", category="MANAGEMENT", title="WINNER_TO_LOSER_REVERSAL",
                    evidence={"current_R": round(current_r, 4), "tp1_triggered": True},
                    affected_engine="TrailingProtectionEngine", director_action=decision.committed_action,
                    suggested_review_question="Was the earned opportunity protected according to the Bible?",
                ))
    recommendations = engine_recommendations(snapshot)
    actionable = {row["recommendation"] for row in recommendations if row["recommendation"] in {"EXIT", "PROTECT", "CANCEL_SETUP"}}
    if actionable and decision.committed_action in {"NO_ACTION", "HOLD"}:
        flags.append(BugFlag(
            bug_flag_id=f"{event_id}|ENGINE_DIRECTOR_CONFLICT", event_id=event_id,
            severity="REVIEW", category="MANAGEMENT", title="ENGINE_DIRECTOR_CONFLICT",
            evidence={"engine_votes": sorted(actionable), "director": decision.committed_action},
            affected_engine="SystemStateDirector", director_action=decision.committed_action,
            suggested_review_question="Did the Director correctly reject the supporting recommendation?",
        ))
    return flags


def classify_event(
    *, has_m1: bool, has_m5: bool, previous: dict[str, Any] | None,
    snapshot: dict[str, Any], decision: DirectorDecision, flags: list[BugFlag],
) -> tuple[str, int]:
    if any(flag.severity == "FAIL" for flag in flags):
        event_type = "BUG_FLAG_CREATED"
    elif decision.committed_action.startswith("ENTER_REENTRY"):
        event_type = "REENTRY_OPENED"
    elif decision.committed_action.startswith("ENTER_M1"):
        event_type = "M1_ENTRY_READY"
    elif decision.committed_action.startswith("ENTER_M5"):
        event_type = "M5_ENTRY_READY"
    elif decision.committed_action.startswith("EXIT"):
        event_type = "OPPOSING_BOS_EXIT" if "OPPOSING" in decision.committed_action else "FIRST_ATTEMPT_EXITED"
    elif decision.committed_action.startswith("MOVE_TO"):
        event_type = "PROTECTION_MOVED"
    elif previous is not None and _state(previous.get("retracement")) != _state(snapshot.get("retracement")):
        event_type = "RETRACEMENT_QUALIFIED" if (snapshot.get("retracement") or {}).get("qualified") else "RETRACEMENT_BORN"
    elif previous is not None and (previous.get("setup") or {}).get("setup_id") != (snapshot.get("setup") or {}).get("setup_id"):
        event_type = "SETUP_CREATED"
    elif has_m1 and has_m5:
        event_type = "M1_AND_M5_CLOSED"
    elif has_m5:
        event_type = "M5_CANDLE_CLOSED"
    else:
        event_type = "M1_CANDLE_CLOSED"
    return event_type, EVENT_PRIORITY.get(event_type, 10)


def story_event(event_time: float, event_type: str, snapshot: dict[str, Any], decision: DirectorDecision) -> dict[str, Any]:
    context = snapshot.get("context") or {}
    retracement = snapshot.get("retracement") or {}
    fib = retracement.get("fibonacci") or {}
    messages = {
        "SETUP_CREATED": "A new M5 parent continuation setup became causally available.",
        "RETRACEMENT_BORN": "The parent impulse entered an opposing retracement.",
        "RETRACEMENT_QUALIFIED": f"Retracement qualified in {fib.get('zone', 'the current')} Fibonacci location.",
        "M1_ENTRY_READY": "M1 closed beyond its owned trigger; the Director committed the early entry.",
        "M5_ENTRY_READY": "M5 continuation BOS closed and the Director committed the fallback entry.",
        "PROTECTION_MOVED": "A proven continuation structure allowed protection to tighten.",
        "FIRST_ATTEMPT_EXITED": "The first attempt closed after logical invalidation.",
        "REENTRY_OPENED": "One causally valid re-entry was committed after fresh proof.",
        "OPPOSING_BOS_EXIT": "The runner exited after an opposing meaningful structure break.",
        "BUG_FLAG_CREATED": "Replay paused because an integrity failure was detected.",
    }
    return {
        "timestamp": float(event_time),
        "category": "TRADE" if event_type not in {"M1_CANDLE_CLOSED", "M5_CANDLE_CLOSED", "M1_AND_M5_CLOSED"} else "DATA",
        "title": event_type,
        "description": messages.get(event_type, f"Closed-candle replay advanced with HTF state {context.get('state', 'unavailable')}."),
        "director_action": decision.committed_action,
    }
