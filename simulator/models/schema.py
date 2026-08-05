from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import hashlib
import json


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return round(value, 10)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def stable_hash(value: Any) -> str:
    raw = json.dumps(
        json_safe(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class DirectorDecision:
    committed_action: str
    priority: int
    timestamp: float
    price: float | None = None
    current_protection: float | None = None
    new_protection: float | None = None
    exit_size: float = 0.0
    exit_reason: str | None = None
    accepted_recommendation: str | None = None
    rejected_recommendations: tuple[str, ...] = ()
    consistency_verdict: str = "PASS"
    safety_verdict: str = "PASS"
    narrative: str = "No canonical action was required on this candle."
    owner: str = "SystemStateDirector"
    causal_valid: bool = True

    def payload(self) -> dict[str, Any]:
        return json_safe(asdict(self))


@dataclass(frozen=True)
class BugFlag:
    bug_flag_id: str
    event_id: str
    severity: str
    category: str
    title: str
    evidence: dict[str, Any]
    affected_structure: str | None = None
    affected_engine: str | None = None
    director_action: str = "NO_ACTION"
    suggested_review_question: str = "Does this match the intended strategy?"
    review_status: str = "UNREVIEWED"

    def payload(self) -> dict[str, Any]:
        return json_safe(asdict(self))


@dataclass(frozen=True)
class ReplayEvent:
    replay_event_id: str
    event_number: int
    event_time: float
    newly_closed_m1_indices: tuple[int, ...]
    newly_closed_m5_indices: tuple[int, ...]
    visible_m1_rows: int
    visible_m5_rows: int
    parent_setup_id: str | None
    active_attempt_id: str | None
    event_type: str
    event_priority: int
    processing_order: tuple[str, ...]
    state_hash: str
    snapshot_hash: str
    parent_snapshot_hash: str | None
    pipeline_state_hash: str
    snapshot: dict[str, Any]
    recommendations: tuple[dict[str, Any], ...]
    director_decision: dict[str, Any]
    shadow_managers: tuple[dict[str, Any], ...]
    bug_flags: tuple[dict[str, Any], ...]
    trade_story_events: tuple[dict[str, Any], ...]
    integrity: dict[str, Any]
    schema_version: str = "S1_REPLAY_EVENT_V1"

    def payload(self) -> dict[str, Any]:
        return json_safe(asdict(self))

