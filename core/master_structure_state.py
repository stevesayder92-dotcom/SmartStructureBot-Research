class MasterStructureState:

    def __init__(self, data):
        self.data = data.copy()

    def build(self, classified_highs, classified_lows, bos_events, market_state):
        structure_points = []

        for high in classified_highs:
            p = high.copy()
            p["side"] = "HIGH"
            structure_points.append(p)

        for low in classified_lows:
            p = low.copy()
            p["side"] = "LOW"
            structure_points.append(p)

        structure_points = sorted(structure_points, key=lambda x: x["index"])

        trend = market_state.get(
            "final_trend_context",
            market_state.get("trend", "UNKNOWN")
        )

        master = {
            "trend": trend,
            "phase": market_state.get("phase", "UNKNOWN"),
            "protected_high": None,
            "protected_low": None,
            "last_bullish_bos": None,
            "last_bearish_bos": None,
            "last_trend_bos": None,
            "last_opposite_bos": None,
            "active_retracement": None,
            "structure_points": structure_points,
            "tradeable_highs": [h for h in classified_highs if h.get("is_tradeable_structure", True)],
            "tradeable_lows": [l for l in classified_lows if l.get("is_tradeable_structure", True)],
            "reason": []
        }

        self._attach_bos_memory(master, bos_events)
        self._attach_protected_structure(master)
        self._attach_active_retracement(master)

        return master

    def _attach_bos_memory(self, master, bos_events):
        trend = master["trend"]

        bullish = [
            b for b in bos_events
            if b["type"] == "BULLISH_BOS"
            and b.get("bos_role") != "EXTENSION_BOS"
        ]

        bearish = [
            b for b in bos_events
            if b["type"] == "BEARISH_BOS"
            and b.get("bos_role") != "EXTENSION_BOS"
        ]

        if bullish:
            master["last_bullish_bos"] = bullish[-1]

        if bearish:
            master["last_bearish_bos"] = bearish[-1]

        if trend == "BULLISH":
            master["last_trend_bos"] = master["last_bullish_bos"]
            master["last_opposite_bos"] = master["last_bearish_bos"]

        elif trend == "BEARISH":
            master["last_trend_bos"] = master["last_bearish_bos"]
            master["last_opposite_bos"] = master["last_bullish_bos"]

        # Fallback: if trend BOS is missing, use latest BOS matching trend direction
        if master["last_trend_bos"] is None:
            if trend == "BULLISH" and bullish:
                master["last_trend_bos"] = bullish[-1]
            elif trend == "BEARISH" and bearish:
                master["last_trend_bos"] = bearish[-1]

        master["reason"].append("BOS memory attached")

    def _attach_protected_structure(self, master):
        trend = master["trend"]
        last_trend_bos = master.get("last_trend_bos")

        highs = master["tradeable_highs"]
        lows = master["tradeable_lows"]

        # Always keep latest useful levels for completeness
        if highs:
            master["protected_high"] = highs[-1]

        if lows:
            master["protected_low"] = lows[-1]

        if trend == "BULLISH":
            if last_trend_bos:
                lows_before_bos = [
                    p for p in lows
                    if p["index"] < last_trend_bos["index"]
                    and p["type"] in ["HL", "LL"]
                ]

                if lows_before_bos:
                    master["protected_low"] = lows_before_bos[-1]
                    master["reason"].append("Bullish protected low set from low before trend BOS")

            elif lows:
                master["protected_low"] = lows[-1]
                master["reason"].append("Bullish fallback protected low used")

        elif trend == "BEARISH":
            if last_trend_bos:
                highs_before_bos = [
                    p for p in highs
                    if p["index"] < last_trend_bos["index"]
                    and p["type"] in ["LH", "HH"]
                ]

                if highs_before_bos:
                    master["protected_high"] = highs_before_bos[-1]
                    master["reason"].append("Bearish protected high set from high before trend BOS")

            elif highs:
                master["protected_high"] = highs[-1]
                master["reason"].append("Bearish fallback protected high used")

    def _attach_active_retracement(self, master):
        trend = master["trend"]

        if trend not in ["BULLISH", "BEARISH"]:
            return

        points = master["structure_points"]

        if trend == "BULLISH":
            counter_types = ["LH", "LL"]
            direction = "BEARISH_PULLBACK"
        else:
            counter_types = ["HH", "HL"]
            direction = "BULLISH_PULLBACK"

        recent_points = points[-14:]

        counter_points = [
            p for p in recent_points
            if p["type"] in counter_types
        ]

        if not counter_points:
            return

        first = counter_points[0]
        last = counter_points[-1]

        master["active_retracement"] = {
            "trend": trend,
            "retracement_direction": direction,
            "start_index": first["index"],
            "end_index": last["index"],
            "counter_structure_count": len(counter_points),
            "quality": self._quality_from_count(len(counter_points))
        }

        master["reason"].append("Active retracement attached")

    def _quality_from_count(self, count):
        if count >= 5:
            return "DEEP_RETRACEMENT"
        if count >= 3:
            return "VALID_RETRACEMENT"
        if count >= 1:
            return "EARLY_RETRACEMENT"
        return "NONE"