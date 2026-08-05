class ContinuationEngine:
    """
    Protection-gated, causal continuation engine.

    Strategy contract:
    1. A directional trend exists.
    2. A structural pullback is active.
    3. Decision protection exists and remains intact.
    4. The current candle CLOSE breaks the latest available
       counter-trend failure trigger.
    5. The BOS itself confirms the pullback failure.
    6. Entry is immediately available at the current candle close.

    Entry quality is advisory only. It never deletes a structurally
    valid current-candle BOS.
    """

    def __init__(self, data, as_of_index=None):
        self.data = data.copy().reset_index(drop=True)
        self.as_of_index = (
            len(self.data) - 1
            if as_of_index is None
            else int(as_of_index)
        )

        if (
            self.as_of_index < 0
            or self.as_of_index >= len(self.data)
        ):
            raise IndexError(
                f"as_of_index {self.as_of_index} is outside "
                f"0..{len(self.data) - 1}"
            )

    def analyze(
        self,
        master_state,
        structure_points,
        bos_events,
        protected_structure=None,
        setup_invalidation=None,
        retracement_lifecycle=None,
        structure_validation=None,
    ):
        trend = master_state.get("trend", "UNKNOWN")
        phase = master_state.get("phase", "UNKNOWN")
        active = master_state.get("active_retracement") or {}
        protected_structure = protected_structure or {}
        setup_invalidation = setup_invalidation or {}
        retracement_lifecycle = retracement_lifecycle or {}
        structure_validation = structure_validation or {}

        result = {
            "trend": trend,
            "phase": phase,
            "state": "NO_TRADE",
            "as_of_index": self.as_of_index,
            "counter_move_started": False,
            "counter_move_start_index": None,
            "counter_move_end_index": None,
            "counter_structure_points": [],
            "failure_trigger": None,
            "continuation_bos": None,
            "entry_ready": False,
            "entry_index": None,
            "entry_price": None,
            "entry_quality": None,
            "entry_score": None,
            "all_continuations": [],
            "current_candle_only": True,
            "stale_fallback_used": False,
            "break_semantics": "DIRECTIONAL_CLOSE_ONLY",
            "decision_protection_available": bool(
                protected_structure.get("protection_level") is not None
            ),
            "decision_protection_level": protected_structure.get(
                "protection_level"
            ),
            "setup_invalidation_required": True,
            "setup_invalidation_available": False,
            "setup_invalidation_intact": False,
            "setup_invalidation_level": None,
            "setup_invalidation_index": None,
            "setup_invalidation_type": None,
            # Legacy aliases retained temporarily for downstream compatibility.
            "protection_required": True,
            "protection_available": False,
            "protection_intact": False,
            "protection_level": None,
            "protection_role": "SETUP_INVALIDATION_STRUCTURE",
            "validation_hard_block": structure_validation.get(
                "hard_block",
                False,
            ),
            "causal_valid": True,
            "reason": [],
        }

        if trend not in ["BULLISH", "BEARISH"]:
            result["reason"].append("No clear directional trend")
            return result

        if not active:
            result["reason"].append("No active structural pullback")
            return result

        start_index = active.get("start_index")
        end_index = active.get("end_index")

        if start_index is None or end_index is None:
            result["state"] = "INVALID_SETUP_CONTRACT"
            result["causal_valid"] = False
            result["reason"].append(
                "Active pullback is missing start/end indexes"
            )
            return result

        if start_index > self.as_of_index:
            result["state"] = "INVALID_SETUP_CONTRACT"
            result["causal_valid"] = False
            result["reason"].append(
                "Pullback starts after the current decision candle"
            )
            return result

        if not setup_invalidation.get("causal_valid", False):
            result["state"] = "BLOCKED_NON_CAUSAL_SETUP_INVALIDATION"
            result["causal_valid"] = False
            result["reason"].append(
                "Setup invalidation structure is not causally valid"
            )
            return result

        invalidation_level = setup_invalidation.get("price")
        invalidation_available_at = setup_invalidation.get(
            "available_at_index"
        )

        result["setup_invalidation_level"] = invalidation_level
        result["setup_invalidation_index"] = setup_invalidation.get("index")
        result["setup_invalidation_type"] = setup_invalidation.get("raw_type")
        result["setup_invalidation_available"] = (
            isinstance(invalidation_level, (int, float))
            and isinstance(invalidation_available_at, int)
            and invalidation_available_at <= self.as_of_index
        )

        # Legacy aliases now refer to the exact setup invalidation structure.
        result["protection_level"] = invalidation_level
        result["protection_available"] = result[
            "setup_invalidation_available"
        ]

        if not result["setup_invalidation_available"]:
            result["state"] = "WAITING_FOR_SETUP_INVALIDATION"
            result["reason"].append(
                "No causally available setup invalidation structure"
            )
            return result

        assert isinstance(
            invalidation_level,
            (int, float),
        )
        invalidation_level_value = float(invalidation_level)

        current_close = float(
            self.data.at[self.as_of_index, "close"]
        )

        invalidation_broken_now = bool(
            setup_invalidation.get("broken", False)
        )

        result["setup_invalidation_intact"] = not invalidation_broken_now
        result["protection_intact"] = not invalidation_broken_now

        if invalidation_broken_now:
            result["state"] = "BLOCKED_SETUP_INVALIDATION_BROKEN"
            result["reason"].append(
                "Setup invalidation structure was broken by directional close"
            )
            return result

        if structure_validation.get("hard_block", False):
            result["state"] = "BLOCKED_STRUCTURE_INVALID"
            result["reason"].extend(
                structure_validation.get(
                    "hard_failures",
                    ["Structure validator issued a hard block"],
                )
            )
            return result

        lifecycle_points = retracement_lifecycle.get(
            "pullback_structure_points",
            [],
        )
        source_points = lifecycle_points or structure_points

        visible_points = [
            point.copy()
            for point in source_points
            if self._point_is_available(point)
            and start_index
            <= point.get("index", -1)
            <= self.as_of_index
        ]
        visible_points = sorted(
            visible_points,
            key=lambda point: point["index"],
        )

        counter_types = (
            ["LH", "LL"]
            if trend == "BULLISH"
            else ["HH", "HL"]
        )
        counter_points = [
            point
            for point in visible_points
            if point.get("type") in counter_types
        ]

        result["counter_move_started"] = bool(counter_points)
        result["counter_move_start_index"] = start_index
        result["counter_move_end_index"] = end_index
        result["counter_structure_points"] = counter_points

        if not counter_points:
            result["state"] = "WAITING_FOR_COUNTER_STRUCTURE"
            result["reason"].append(
                "Active pullback has no available counter structure"
            )
            return result

        qualification_index = retracement_lifecycle.get(
            "first_qualification_index",
            retracement_lifecycle.get("qualification_index"),
        )
        lifecycle_trigger = (
            retracement_lifecycle.get("active_failure_trigger")
            or retracement_lifecycle.get("failure_trigger")
        )
        trigger = lifecycle_trigger

        if trigger is None:
            result["state"] = "WAITING_FOR_FAILURE_TRIGGER"
            result["reason"].append(
                "The qualified retracement owner has not published "
                "a causal failure trigger; raw counter swings cannot "
                "be substituted"
            )
            return result

        trigger_index_value = trigger.get("index")
        if (
            qualification_index is None
            or trigger_index_value is None
            or int(trigger_index_value) < int(qualification_index)
            or not trigger.get(
                "belongs_to_same_qualified_retracement",
                False,
            )
        ):
            result["state"] = "BLOCKED_STALE_OR_FOREIGN_TRIGGER"
            result["reason"].append(
                "Failure trigger is pre-qualification or does not "
                "belong to the active qualified retracement"
            )
            return result

        trigger_level = trigger.get(
            "body_price",
            trigger.get("level"),
        )
        trigger_index = trigger.get("index")

        result["failure_trigger"] = {
            "type": trigger.get("type"),
            "side": trigger.get("side"),
            "index": trigger_index,
            "confirmed_at_index": trigger.get(
                "confirmed_at_index",
                trigger_index,
            ),
            "tradeable_at_index": trigger.get(
                "tradeable_at_index"
            ),
            "level": trigger_level,
        }

        if trigger_level is None:
            result["state"] = "INVALID_TRIGGER"
            result["causal_valid"] = False
            result["reason"].append(
                "Pullback trigger has no body_price"
            )
            return result

        break_confirmed = (
            current_close > float(trigger_level)
            if trend == "BULLISH"
            else current_close < float(trigger_level)
        )

        if not break_confirmed:
            result["state"] = "COUNTER_MOVE_ACTIVE"
            result["reason"].append(
                "Protection is intact, but the current candle close "
                "has not broken the pullback failure trigger"
            )
            return result

        score, quality = self._score_current_bos(
            trend=trend,
            trigger_level=float(trigger_level),
            counter_count=len(counter_points),
        )

        entry_type = (
            "BULLISH_ENTRY_BOS"
            if trend == "BULLISH"
            else "BEARISH_ENTRY_BOS"
        )

        entry_bos = {
            "type": entry_type,
            "index": self.as_of_index,
            "break_price": current_close,
            "entry_price": current_close,
            "broken_structure_index": trigger_index,
            "broken_structure_confirmed_at_index": trigger.get(
                "confirmed_at_index",
                trigger_index,
            ),
            "broken_structure_price": float(trigger_level),
            "broken_structure_type": trigger.get("type"),
            "bos_role": "PROTECTION_GATED_FAILED_RETRACEMENT_BOS",
            "entry_quality": quality,
            "entry_confidence_score": score,
            "decision_available_at_index": self.as_of_index,
            "break_semantics": "DIRECTIONAL_CLOSE_ONLY",
            "decision_protection_level": protected_structure.get(
                "protection_level"
            ),
            "setup_invalidation_level": invalidation_level_value,
            "setup_invalidation_index": setup_invalidation.get("index"),
            "setup_invalidation_type": setup_invalidation.get("raw_type"),
            "setup_invalidation_role": "SETUP_INVALIDATION_STRUCTURE",
            "setup_invalidation_intact_at_entry": True,
            # Legacy aliases retained temporarily.
            "protection_level": invalidation_level_value,
            "protection_role": "SETUP_INVALIDATION_STRUCTURE",
            "protection_intact_at_entry": True,
            "causal_valid": True,
            "current_candle_only": True,
        }

        current_continuation = {
            "trend": trend,
            "counter_start_index": start_index,
            "counter_end_index": self.as_of_index,
            "counter_points": counter_points,
            "failure_trigger": result["failure_trigger"],
            "entry_bos": entry_bos,
            "entry_index": self.as_of_index,
            "entry_price": current_close,
            "entry_quality": quality,
            "entry_score": score,
            "decision_protection_level": protected_structure.get(
                "protection_level"
            ),
            "setup_invalidation_level": invalidation_level_value,
            "setup_invalidation_index": setup_invalidation.get("index"),
            "setup_invalidation_type": setup_invalidation.get("raw_type"),
            "setup_invalidation_intact": True,
            "protection_level": invalidation_level_value,
            "protection_intact": True,
        }

        result["continuation_bos"] = entry_bos
        result["entry_ready"] = True
        result["entry_index"] = self.as_of_index
        result["entry_price"] = current_close
        result["entry_quality"] = quality
        result["entry_score"] = score
        result["all_continuations"] = [current_continuation]
        result["state"] = "ENTRY_READY"
        result["reason"].append(
            "Setup invalidation held and the current candle close "
            "broke the failed-pullback trigger"
        )
        return result

    def _point_is_available(self, point):
        point_index = point.get("index")

        if point_index is None:
            return False

        confirmed_at = point.get(
            "confirmed_at_index",
            point_index,
        )

        if (
            confirmed_at is None
            or confirmed_at > self.as_of_index
        ):
            return False

        tradeable_at = point.get("tradeable_at_index")

        if (
            point.get("is_tradeable_structure", False)
            and tradeable_at is not None
            and tradeable_at > self.as_of_index
        ):
            return False

        return point_index <= self.as_of_index

    def _select_trigger(self, trend, counter_points):
        if trend == "BULLISH":
            candidates = [
                point
                for point in counter_points
                if point.get("side") == "HIGH"
                and point.get("type") == "LH"
            ]
            if not candidates:
                candidates = [
                    point
                    for point in counter_points
                    if point.get("side") == "HIGH"
                ]
        else:
            candidates = [
                point
                for point in counter_points
                if point.get("side") == "LOW"
                and point.get("type") == "HL"
            ]
            if not candidates:
                candidates = [
                    point
                    for point in counter_points
                    if point.get("side") == "LOW"
                ]

        if not candidates:
            return None

        return sorted(
            candidates,
            key=lambda point: point["index"],
        )[-1]

    def _score_current_bos(
        self,
        trend,
        trigger_level,
        counter_count,
    ):
        index = self.as_of_index
        candle_high = float(
            self.data.at[index, "high"]
        )
        candle_low = float(
            self.data.at[index, "low"]
        )
        candle_open = float(
            self.data.at[index, "open"]
        )
        candle_close = float(
            self.data.at[index, "close"]
        )

        candle_range = candle_high - candle_low
        body_size = abs(candle_close - candle_open)

        prior_ranges = (
            self.data["high"] - self.data["low"]
        ).iloc[max(0, index - 20):index]

        avg_range = (
            float(prior_ranges.mean())
            if not prior_ranges.empty
            else 0.0
        )

        if candle_range <= 0 or avg_range <= 0:
            return 0, "C_ENTRY"

        if trend == "BULLISH":
            close_break = candle_close - trigger_level
            close_strength = (
                candle_close - candle_low
            ) / candle_range
            candle_direction_good = (
                candle_close > candle_open
            )
        else:
            close_break = trigger_level - candle_close
            close_strength = (
                candle_high - candle_close
            ) / candle_range
            candle_direction_good = (
                candle_close < candle_open
            )

        score = 0
        score += 20 if counter_count >= 2 else 5

        if candle_range >= avg_range * 0.75:
            score += 20

        if body_size >= avg_range * 0.35:
            score += 25

        if close_strength >= 0.58:
            score += 25

        if close_break >= avg_range * 0.12:
            score += 20

        if candle_direction_good:
            score += 10

        if score >= 85:
            return score, "A_ENTRY"

        if score >= 65:
            return score, "B_ENTRY"

        return score, "C_ENTRY"
