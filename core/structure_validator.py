class StructureValidator:
    """
    Recovery-aware structural reconciler.

    Hard blocking is reserved for genuine structural death:
    - no directional trend,
    - non-causal decision protection,
    - decision protection broken by a directional close,
    - or an unresolved chronological control transition.

    Pullback pressure, control disagreement, CHOCH watch states and recovered
    transitions are advisory. They may reduce risk but do not erase a valid
    current-candle failed-retracement BOS.
    """

    def validate(
        self,
        trend,
        master_state,
        protected_structure,
    ):
        control = master_state.get("market_control", {}) or {}
        transition = master_state.get("transition_state", {}) or {}

        reasons = []
        warnings = []
        hard_failures = []

        protection_exists = (
            protected_structure.get("protected_low") is not None
            or protected_structure.get("protected_high") is not None
        )
        protection_causal = protected_structure.get(
            "causal_valid",
            False,
        )
        protection_broken = protected_structure.get(
            "protection_broken",
            False,
        )

        transition_state = transition.get(
            "state",
            "TREND_STABLE",
        )
        transition_active = transition.get(
            "transition_active",
            transition.get("sequence_confirmed", False),
        )
        transition_confirmed = transition.get(
            "sequence_confirmed",
            False,
        )
        transition_recovered = transition.get(
            "transition_recovered",
            transition_state == "TRANSITION_RECOVERED",
        )

        if trend not in ["BULLISH", "BEARISH"]:
            hard_failures.append("No directional trend")

        if not protection_exists:
            warnings.append(
                "No decision protection is currently available"
            )
        elif not protection_causal:
            hard_failures.append(
                "Decision protection contract is non-causal"
            )

        if protection_broken:
            hard_failures.append(
                "Decision protection was invalidated by directional close"
            )

        unresolved_transition = bool(
            transition_confirmed
            and transition_active
            and not transition_recovered
        )
        if unresolved_transition:
            hard_failures.append(
                "Unresolved chronological control transition confirmed"
            )

        score = 100

        if not protection_exists:
            score -= 25

        control_state = control.get(
            "control_state",
            "UNKNOWN",
        )
        control_side = control.get("control_side")
        auction_state = control.get("auction_state")

        if control_state == "TREND_CONTROL_CHALLENGED":
            score -= 20
            warnings.append("Main-trend control is challenged")
        elif control_state == "PULLBACK_CONTROL_ACTIVE":
            score -= 8
            reasons.append(
                "Counter-trend auction is active inside the pullback"
            )

        if auction_state == "COUNTER_TREND_PULLBACK":
            reasons.append(
                "Opposite auction control is pullback context, not automatic "
                "trend invalidation"
            )

        if transition_state == "TRANSITION_WARNING":
            score -= 18
            warnings.append(
                "Two-step transition sequence is developing"
            )
        elif transition_state == "TRANSITION_WATCH":
            score -= 8
            warnings.append(
                "Opposite BOS exists without complete control transfer"
            )
        elif transition_state == "TRANSITION_RECOVERED":
            score -= 4
            reasons.append(
                "Earlier transition pressure was resolved by a later "
                "main-trend BOS"
            )

        protection_score = protected_structure.get(
            "protection_score",
            0,
        )
        if protection_exists:
            if protection_score >= 72:
                reasons.append(
                    "Decision protection supports the setup"
                )
            elif protection_score < 42:
                score -= 12
                warnings.append(
                    "Decision protection confidence is low"
                )

        score = max(0, min(100, round(score, 2)))

        if hard_failures:
            verdict = "STRUCTURE_INVALID"
            trade_bias = "BLOCK"
            score = min(score, 35)
        elif score >= 80:
            verdict = "STRUCTURE_VALID"
            trade_bias = "ALLOW"
        elif score >= 60:
            verdict = "STRUCTURE_CAUTION"
            trade_bias = "REDUCE_RISK"
        else:
            verdict = "STRUCTURE_DANGER"
            trade_bias = "REDUCE_RISK"

        reasons.extend(hard_failures)

        return {
            "trend": trend,
            "structure_score": score,
            "verdict": verdict,
            "trade_bias": trade_bias,
            "hard_block": bool(hard_failures),
            "hard_failures": hard_failures,
            "structural_death_confirmed": bool(hard_failures),
            "hard_block_reason": (
                hard_failures[0] if hard_failures else None
            ),
            "control_side": control_side,
            "control_state": control_state,
            "auction_state": auction_state,
            "transition_state": transition_state,
            "transition_risk": transition.get(
                "transition_risk",
                0,
            ),
            "transition_sequence_confirmed": transition_confirmed,
            "transition_active": transition_active,
            "transition_recovered": transition_recovered,
            "protected_score": protection_score,
            "protection_exists": protection_exists,
            "protection_broken": protection_broken,
            "risk_modifier": (
                0.0
                if hard_failures
                else 1.0
                if trade_bias == "ALLOW"
                else 0.6
            ),
            "warnings": warnings,
            "reasons": reasons,
        }
