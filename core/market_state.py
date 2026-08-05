class MarketStateEngine:

    def __init__(self):
        pass

    def compress_structure_points(
        self,
        highs,
        lows,
        min_index_gap=4
    ):
        compressed_highs = []
        compressed_lows = []

        for high in highs:
            if not compressed_highs:
                compressed_highs.append(high)
                continue

            previous = compressed_highs[-1]

            if high["index"] - previous["index"] <= min_index_gap:
                if high["body_price"] > previous["body_price"]:
                    compressed_highs[-1] = high
            else:
                compressed_highs.append(high)

        for low in lows:
            if not compressed_lows:
                compressed_lows.append(low)
                continue

            previous = compressed_lows[-1]

            if low["index"] - previous["index"] <= min_index_gap:
                if low["body_price"] < previous["body_price"]:
                    compressed_lows[-1] = low
            else:
                compressed_lows.append(low)

        return compressed_highs, compressed_lows

    def analyze_structure_state(
        self,
        classified_highs,
        classified_lows,
        total_candles
    ):
        state = {
            "trend": "UNKNOWN",
            "phase": "UNKNOWN",
            "strength_score": 0,
            "choch_warning": False,
            "reason": []
        }

        if len(classified_highs) < 2 or len(classified_lows) < 2:
            state["phase"] = "NOT_ENOUGH_DATA"
            state["reason"].append("Not enough structure data")
            return state

        recent_highs = classified_highs[-6:]
        recent_lows = classified_lows[-6:]

        hh_count = sum(1 for h in recent_highs if h["type"] == "HH")
        lh_count = sum(1 for h in recent_highs if h["type"] == "LH")
        hl_count = sum(1 for l in recent_lows if l["type"] == "HL")
        ll_count = sum(1 for l in recent_lows if l["type"] == "LL")

        bullish_score = (hh_count * 20) + (hl_count * 20)
        bearish_score = (lh_count * 20) + (ll_count * 20)

        raw_score = max(bullish_score, bearish_score)
        state["strength_score"] = min(raw_score, 100)

        score_difference = abs(bullish_score - bearish_score)

        if bullish_score > bearish_score and score_difference >= 20:
            state["trend"] = "BULLISH"

            if hh_count >= 1 and hl_count >= 1:
                state["phase"] = "BULLISH_EXPANSION"
                state["reason"].append("Recent structure shows HH/HL dominance")
            else:
                state["phase"] = "BULLISH_WEAK"
                state["reason"].append("Bullish bias but incomplete HH/HL structure")

        elif bearish_score > bullish_score and score_difference >= 20:
            state["trend"] = "BEARISH"

            if lh_count >= 1 and ll_count >= 1:
                state["phase"] = "BEARISH_EXPANSION"
                state["reason"].append("Recent structure shows LH/LL dominance")
            else:
                state["phase"] = "BEARISH_WEAK"
                state["reason"].append("Bearish bias but incomplete LH/LL structure")

        else:
            state["trend"] = "RANGING"
            state["phase"] = "CONSOLIDATION"
            state["reason"].append("Recent structure is mixed")

        last_high = recent_highs[-1]
        last_low = recent_lows[-1]

        if state["trend"] == "BULLISH" and last_low["type"] == "LL":
            state["choch_warning"] = True
            state["phase"] = "CHOCH_WARNING"
            state["reason"].append("Bullish warning: latest low became LL")

        elif state["trend"] == "BEARISH" and last_high["type"] == "HH":
            state["choch_warning"] = True
            state["phase"] = "CHOCH_WARNING"
            state["reason"].append("Bearish warning: latest high became HH")

        return state