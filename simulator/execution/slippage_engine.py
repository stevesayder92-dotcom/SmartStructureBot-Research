from __future__ import annotations

import hashlib

from simulator.models.financial import ContractSpecification, ExecutionConfig


class SlippageEngine:
    def calculate(
        self,
        *,
        spec: ContractSpecification,
        config: ExecutionConfig,
        replay_event_id: str,
        order_id: str,
        order_kind: str,
        volatility_ratio: float = 1.0,
    ) -> dict[str, float | str | None]:
        model = config.slippage_model
        seed_text = f"{config.session_seed}|{spec.canonical_symbol}|{replay_event_id}|{order_id}|{order_kind}"
        digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
        unit = int(digest[:16], 16) / float(0xFFFFFFFFFFFFFFFF)
        cost_factor = {"IDEALIZED_CONTROL": 0.5, "NORMAL_ESTIMATED": 1.0, "STRESSED_COSTS": 2.0}[config.cost_profile]
        base = max(0.1, spec.base_spread_points * 0.08) * cost_factor
        kind_factor = 2.5 if order_kind == "EMERGENCY_STOP" else 1.25 if order_kind in {"EXIT", "PARTIAL"} else 1.0
        if order_kind == "TARGET":
            points = 0.0
        elif model == "NO_SLIPPAGE":
            points = 0.0
        elif model == "FIXED_AVERAGE_SLIPPAGE":
            points = max(0.0, config.fixed_slippage_points) * kind_factor
        elif model == "VOLATILITY_AWARE_SLIPPAGE":
            points = base * max(0.75, min(3.0, volatility_ratio)) * kind_factor * (0.5 + unit)
        else:
            points = base * kind_factor * (0.5 + unit)
        return {
            "slippage_points": round(points, 6),
            "slippage_model": model,
            "random_seed": digest if model == "DETERMINISTIC_SEEDED" else None,
        }
