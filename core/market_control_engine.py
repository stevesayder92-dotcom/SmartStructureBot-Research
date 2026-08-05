class MarketControlEngine:
    """
    Current-auction control engine.

    It separates:
    - main trend control,
    - temporary counter-trend pullback control,
    - and genuine evidence that main-trend control has been challenged.

    Normal pullback LH/LL or HH/HL structures are not automatically treated
    as a broken main trend.
    """

    def __init__(self, as_of_index=None):
        self.as_of_index = as_of_index

    def analyze(
        self,
        trend,
        master_state,
        bos_events,
        lookback_points=18,
    ):
        points = master_state.get("structure_points", [])
        active_pullback = master_state.get("active_retracement") or {}
        as_of_index = self._resolve_as_of(points, bos_events)

        visible_points = [
            point for point in points
            if point.get("index") is not None
            and point["index"] <= as_of_index
            and point.get(
                "confirmed_at_index",
                point["index"],
            ) <= as_of_index
        ]
        visible_points = sorted(
            visible_points,
            key=lambda point: point["index"],
        )

        recent_points = (
            visible_points[-lookback_points:]
            if visible_points
            else []
        )

        recent_start = (
            recent_points[0]["index"]
            if recent_points
            else max(0, as_of_index - 100)
        )
        recent_bos = [
            bos for bos in bos_events
            if bos.get("index") is not None
            and recent_start <= bos["index"] <= as_of_index
            and bos.get("bos_role") != "EXTENSION_BOS"
            and bos.get("causal_valid", True)
        ]
        recent_bos = sorted(
            recent_bos,
            key=lambda bos: bos["index"],
        )

        latest_point = recent_points[-1] if recent_points else None
        latest_bos = recent_bos[-1] if recent_bos else None
        pullback_active = bool(active_pullback)
        pullback_direction = active_pullback.get(
            "retracement_direction"
        )

        trend_bos_type = (
            "BULLISH_BOS"
            if trend == "BULLISH"
            else "BEARISH_BOS"
        )
        opposite_bos_type = (
            "BEARISH_BOS"
            if trend == "BULLISH"
            else "BULLISH_BOS"
        )

        same_direction_bos = [
            bos for bos in recent_bos
            if bos.get("type") == trend_bos_type
        ]
        opposite_bos = [
            bos for bos in recent_bos
            if bos.get("type") == opposite_bos_type
        ]

        reasons = []
        warnings = []

        if latest_bos:
            control_side = (
                "BUYERS"
                if latest_bos.get("type") == "BULLISH_BOS"
                else "SELLERS"
            )
            reasons.append(
                "Current auction side follows the latest completed BOS"
            )
        elif latest_point:
            control_side = (
                "BUYERS"
                if latest_point.get("type") in ["HH", "HL"]
                else "SELLERS"
            )
            reasons.append(
                "Current auction side follows the latest confirmed structure"
            )
        else:
            control_side = "BALANCED"
            reasons.append("No completed auction evidence")

        latest_same = (
            same_direction_bos[-1]
            if same_direction_bos
            else None
        )
        latest_opposite = (
            opposite_bos[-1]
            if opposite_bos
            else None
        )

        contradiction_score = 0

        if (
            latest_opposite
            and (
                latest_same is None
                or latest_opposite["index"] > latest_same["index"]
            )
        ):
            contradiction_score = 35
            warnings.append(
                "Latest completed BOS is opposite the main trend"
            )

            broken_type = latest_opposite.get(
                "broken_structure_type"
            )
            protected_break_type = (
                broken_type in ["HL", "HH"]
                if trend == "BULLISH"
                else broken_type in ["LH", "LL"]
            )
            if protected_break_type:
                contradiction_score = 55
                warnings.append(
                    "Opposite BOS broke a trend-side structure"
                )

        if pullback_active:
            reasons.append(
                "Counter-trend structures are treated as active pullback "
                "evidence, not automatic trend failure"
            )

        if contradiction_score >= 55:
            control_state = "TREND_CONTROL_CHALLENGED"
        elif contradiction_score >= 35:
            control_state = "PULLBACK_CONTROL_ACTIVE"
        else:
            control_state = "TREND_CONTROL_STABLE"

        trend_control_score = max(
            0,
            100 - contradiction_score,
        )

        buyer_percent = 50
        seller_percent = 50
        if control_side == "BUYERS":
            buyer_percent, seller_percent = 65, 35
        elif control_side == "SELLERS":
            buyer_percent, seller_percent = 35, 65

        counts = {
            "HH": sum(
                point.get("type") == "HH"
                for point in recent_points
            ),
            "HL": sum(
                point.get("type") == "HL"
                for point in recent_points
            ),
            "LH": sum(
                point.get("type") == "LH"
                for point in recent_points
            ),
            "LL": sum(
                point.get("type") == "LL"
                for point in recent_points
            ),
            "bullish_bos": sum(
                bos.get("type") == "BULLISH_BOS"
                for bos in recent_bos
            ),
            "bearish_bos": sum(
                bos.get("type") == "BEARISH_BOS"
                for bos in recent_bos
            ),
        }

        return {
            "trend": trend,
            "as_of_index": as_of_index,
            "control_side": control_side,
            "control_state": control_state,
            "auction_state": (
                "COUNTER_TREND_PULLBACK"
                if pullback_active
                and (
                    (trend == "BULLISH" and control_side == "SELLERS")
                    or (
                        trend == "BEARISH"
                        and control_side == "BUYERS"
                    )
                )
                else "TREND_SIDE_AUCTION"
            ),
            "buyer_control": buyer_percent,
            "seller_control": seller_percent,
            "trend_control_score": trend_control_score,
            "contradiction_score": contradiction_score,
            "latest_bos": latest_bos,
            "latest_same_direction_bos": latest_same,
            "latest_opposite_bos": latest_opposite,
            "pullback_active": pullback_active,
            "pullback_direction": pullback_direction,
            "current_auction_only": True,
            "causal_valid": True,
            "recent_structure_counts": counts,
            "warnings": warnings,
            "reasons": reasons,
        }

    def _resolve_as_of(self, points, bos_events):
        if self.as_of_index is not None:
            return int(self.as_of_index)
        indexes = [
            item.get("index", 0)
            for item in list(points) + list(bos_events)
        ]
        return max(indexes) if indexes else 0
