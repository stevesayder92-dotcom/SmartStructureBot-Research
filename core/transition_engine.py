class TransitionEngine:
    """
    Chronological, recovery-aware control-transition engine.

    A transition is active only while the ordered opposite-direction sequence
    remains the latest unresolved control event.

    Bullish trend danger sequence:
        bearish BOS -> later LH -> later LL

    Bearish trend danger sequence:
        bullish BOS -> later HL -> later HH

    A later BOS back in the main-trend direction resolves the old sequence.
    """

    def __init__(self, as_of_index=None):
        self.as_of_index = as_of_index

    def analyze(
        self,
        trend,
        structure_points,
        bos_events,
        lookback=60,
    ):
        as_of_index = self._resolve_as_of(
            structure_points,
            bos_events,
        )
        start_index = max(0, as_of_index - lookback)

        points = sorted(
            [
                point for point in structure_points
                if point.get("index") is not None
                and start_index <= point["index"] <= as_of_index
                and point.get(
                    "confirmed_at_index",
                    point["index"],
                ) <= as_of_index
            ],
            key=lambda point: point["index"],
        )

        events = sorted(
            [
                bos for bos in bos_events
                if bos.get("index") is not None
                and start_index <= bos["index"] <= as_of_index
                and bos.get("bos_role") != "EXTENSION_BOS"
                and bos.get("causal_valid", True)
            ],
            key=lambda bos: bos["index"],
        )

        result = {
            "trend": trend,
            "as_of_index": as_of_index,
            "state": "TREND_STABLE",
            "transition_risk": 0,
            "opposite_pressure": 0,
            "sequence_started": False,
            "sequence_confirmed": False,
            "historical_sequence_confirmed": False,
            "transition_active": False,
            "transition_recovered": False,
            "recovery_bos": None,
            "sequence_end_index": None,
            "sequence_age": None,
            "opposite_bos": None,
            "step_two": None,
            "step_three": None,
            "chronological_sequence": [],
            "current_window_only": True,
            "causal_valid": True,
            "recent_counts": self._counts(points, events),
            "reasons": [],
        }

        if trend not in ["BULLISH", "BEARISH"]:
            result["state"] = "TRANSITION_UNKNOWN"
            result["transition_risk"] = 50
            result["reasons"].append("No directional trend")
            return result

        opposite_type = (
            "BEARISH_BOS"
            if trend == "BULLISH"
            else "BULLISH_BOS"
        )
        trend_type = (
            "BULLISH_BOS"
            if trend == "BULLISH"
            else "BEARISH_BOS"
        )
        step_two_type = "LH" if trend == "BULLISH" else "HL"
        step_three_type = "LL" if trend == "BULLISH" else "HH"

        opposite_events = [
            event for event in events
            if event.get("type") == opposite_type
        ]

        if not opposite_events:
            result["reasons"].append(
                "No opposite-direction BOS in the current window"
            )
            return result

        opposite_bos = opposite_events[-1]
        opposite_index = int(opposite_bos["index"])

        result["sequence_started"] = True
        result["opposite_bos"] = opposite_bos
        result["chronological_sequence"].append(
            {
                "step": 1,
                "type": opposite_type,
                "index": opposite_index,
            }
        )

        recovery_after_step_one = [
            event for event in events
            if event.get("type") == trend_type
            and event["index"] > opposite_index
        ]

        after_bos = [
            point for point in points
            if point["index"] > opposite_index
        ]

        step_two_candidates = [
            point for point in after_bos
            if point.get("type") == step_two_type
        ]

        if not step_two_candidates:
            if recovery_after_step_one:
                return self._mark_recovered(
                    result,
                    recovery_after_step_one[-1],
                    "Main-trend BOS recovered the opposite break before "
                    "a transition structure completed",
                )

            result["state"] = "TRANSITION_WATCH"
            result["transition_risk"] = 30
            result["opposite_pressure"] = 30
            result["transition_active"] = True
            result["reasons"].append(
                "Opposite BOS exists, but no ordered second transition "
                "structure has confirmed"
            )
            return result

        step_two = step_two_candidates[0]
        step_two_index = int(step_two["index"])
        result["step_two"] = step_two
        result["chronological_sequence"].append(
            {
                "step": 2,
                "type": step_two_type,
                "index": step_two_index,
            }
        )

        recovery_after_step_two = [
            event for event in events
            if event.get("type") == trend_type
            and event["index"] > step_two_index
        ]

        step_three_candidates = [
            point for point in after_bos
            if point["index"] > step_two_index
            and point.get("type") == step_three_type
        ]

        if not step_three_candidates:
            if recovery_after_step_two:
                return self._mark_recovered(
                    result,
                    recovery_after_step_two[-1],
                    "Main-trend BOS recovered the developing transition "
                    "before final control transfer",
                )

            result["state"] = "TRANSITION_WARNING"
            result["transition_risk"] = 55
            result["opposite_pressure"] = 55
            result["transition_active"] = True
            result["reasons"].append(
                "Opposite BOS and second transition step confirmed; "
                "final control-transfer structure is still missing"
            )
            return result

        step_three = step_three_candidates[0]
        step_three_index = int(step_three["index"])
        result["step_three"] = step_three
        result["sequence_end_index"] = step_three_index
        result["sequence_age"] = as_of_index - step_three_index
        result["historical_sequence_confirmed"] = True
        result["chronological_sequence"].append(
            {
                "step": 3,
                "type": step_three_type,
                "index": step_three_index,
            }
        )

        recovery_events = [
            event for event in events
            if event.get("type") == trend_type
            and event["index"] > step_three_index
        ]

        if recovery_events:
            return self._mark_recovered(
                result,
                recovery_events[-1],
                "A later main-trend BOS resolved the completed opposite "
                "transition sequence",
            )

        result["sequence_confirmed"] = True
        result["transition_active"] = True
        result["state"] = "TRANSITION_CONFIRMED"
        result["transition_risk"] = 90
        result["opposite_pressure"] = 90
        result["reasons"].append(
            "Complete unresolved chronological control-transfer sequence "
            "confirmed"
        )
        return result

    def _mark_recovered(self, result, recovery_bos, reason):
        result["state"] = "TRANSITION_RECOVERED"
        result["transition_risk"] = 15
        result["opposite_pressure"] = 15
        result["sequence_confirmed"] = False
        result["transition_active"] = False
        result["transition_recovered"] = True
        result["recovery_bos"] = recovery_bos
        result["reasons"].append(reason)
        return result

    def _counts(self, points, events):
        return {
            "HH": sum(p.get("type") == "HH" for p in points),
            "HL": sum(p.get("type") == "HL" for p in points),
            "LH": sum(p.get("type") == "LH" for p in points),
            "LL": sum(p.get("type") == "LL" for p in points),
            "bullish_bos": sum(
                b.get("type") == "BULLISH_BOS"
                for b in events
            ),
            "bearish_bos": sum(
                b.get("type") == "BEARISH_BOS"
                for b in events
            ),
        }

    def _resolve_as_of(self, points, bos_events):
        if self.as_of_index is not None:
            return int(self.as_of_index)

        indexes = [
            item.get("index", 0)
            for item in list(points) + list(bos_events)
        ]
        return max(indexes) if indexes else 0
