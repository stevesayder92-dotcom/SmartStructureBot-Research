from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import hashlib
import json

from simulator import SIMULATOR_VERSION, STRATEGY_VERSION


@dataclass(frozen=True)
class SimulatorConfig:
    strategy_version: str = STRATEGY_VERSION
    simulator_version: str = SIMULATOR_VERSION
    timezone: str = "UTC"
    checkpoint_frequency: int = 25
    default_speed: float = 1.0
    engine_sensitivity: int = 3
    htf_policy: str = "STRICT_2_OF_3_H1_M30_M15"
    allow_single_strong_htf: bool = False
    m1_permission_policy: str = "COUNTER_CONFIRMED_ACTIVE"
    second_touch_enabled: bool = False
    second_touch_proximity_atr_ratio: float = 0.25
    second_touch_meaningful_reaction_atr_ratio: float = 0.35
    second_touch_minimum_separation_bars: int = 3
    max_visible_m1: int = 240
    max_visible_m5: int = 120
    mode: str = "TRADER"
    enabled_shadows: tuple[str, ...] = (
        "PURE_STRUCTURE_RUNNER",
        "TP1_PARTIAL_PLUS_RUNNER",
        "EARNED_OPPORTUNITY_MANAGER",
        "M5_CONFIRMATION_REENTRY",
        "M1_RESET_REENTRY",
        "PROTECT_WINNER_FROM_LOSS",
    )
    enabled_bug_rules: tuple[str, ...] = (
        "PREFIX_STATE_MISMATCH",
        "STATE_HASH_MISMATCH",
        "MULTIPLE_ACTIONS_SAME_EVENT",
        "ORDER_API_DETECTED",
        "ENTRY_TOO_EARLY",
        "STOP_USES_POST_ENTRY_DATA",
        "REENTRY_BEFORE_EXTENSION_PROOF",
        "SEVERE_GIVEBACK",
        "WINNER_TO_LOSER_REVERSAL",
        "ENGINE_DIRECTOR_CONFLICT",
        "RISK_EXCEEDS_CONFIG",
        "EMERGENCY_RISK_EXCEEDS_CAP",
        "INSUFFICIENT_MARGIN",
        "MINIMUM_VOLUME_TOO_LARGE",
        "SPREAD_ABNORMALLY_HIGH",
        "SLIPPAGE_ABNORMALLY_HIGH",
        "PARTIAL_NOT_EXECUTABLE",
        "COSTS_ERASED_EDGE",
        "ACCOUNT_STOP_OUT",
        "CURRENCY_CONVERSION_MISSING",
    )

    def manifest_payload(self) -> dict[str, Any]:
        return asdict(self)

    def hash(self) -> str:
        raw = json.dumps(
            self.manifest_payload(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


DEFAULT_CONFIG = SimulatorConfig()


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_config(path: Path | None = None) -> SimulatorConfig:
    if path is None:
        path = project_root() / "config" / "simulator_phase_s1.json"
    if not path.exists():
        return DEFAULT_CONFIG
    raw = json.loads(path.read_text(encoding="utf-8"))
    allowed = set(DEFAULT_CONFIG.manifest_payload())
    clean = {key: value for key, value in raw.items() if key in allowed}
    for key in ("enabled_shadows", "enabled_bug_rules"):
        if key in clean:
            clean[key] = tuple(clean[key])
    return SimulatorConfig(**clean)
