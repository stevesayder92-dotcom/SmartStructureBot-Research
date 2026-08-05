class BOSImportanceEngine:

    def __init__(self, data):
        self.data = data.copy()

    def score_bos_events(self, bos_events, market_state):
        scored = []

        for bos in bos_events:
            score = 0
            reasons = []

            # 1. BOS role
            if bos["bos_role"] == "MASTER_BOS":
                score += 25
                reasons.append("Master BOS")
            elif bos["bos_role"] == "NEW_SETUP_BOS":
                score += 20
                reasons.append("Fresh setup BOS")
            elif bos["bos_role"] == "EXTENSION_BOS":
                score += 5
                reasons.append("Extension BOS only")

            # 2. Direction alignment
            if market_state["trend"] == "BULLISH" and bos["type"] == "BULLISH_BOS":
                score += 25
                reasons.append("Aligned with bullish market state")

            elif market_state["trend"] == "BEARISH" and bos["type"] == "BEARISH_BOS":
                score += 25
                reasons.append("Aligned with bearish market state")

            elif market_state["trend"] == "RANGING":
                score += 10
                reasons.append("Market ranging, reduced confidence")

            else:
                score -= 10
                reasons.append("Against market state")

            # 3. BOS class
            if "REVERSAL_OR_ENTRY" in bos["bos_class"]:
                score += 20
                reasons.append("Broke opposite structure")

            elif "CONTINUATION" in bos["bos_class"]:
                score += 15
                reasons.append("Continuation BOS")

            # 4. Candle body strength
            candle_range = self.data["high"][bos["index"]] - self.data["low"][bos["index"]]
            candle_body = abs(self.data["close"][bos["index"]] - self.data["open"][bos["index"]])

            if candle_range > 0:
                body_ratio = candle_body / candle_range
            else:
                body_ratio = 0

            if body_ratio >= 0.6:
                score += 20
                reasons.append("Strong body close")
            elif body_ratio >= 0.4:
                score += 10
                reasons.append("Acceptable body close")
            else:
                score -= 5
                reasons.append("Weak body close")

             # 5. ATR-based break strength
            break_distance = abs(
                bos["break_price"] - bos["broken_structure_price"]
            )

            atr_value = self._calculate_atr_at_index(bos["index"])

            if atr_value > 0:
                atr_break_ratio = break_distance / atr_value
            else:
                atr_break_ratio = 0

            if atr_break_ratio >= 0.8:
                score += 20
                reasons.append("Explosive ATR break")
            elif atr_break_ratio >= 0.5:
                score += 15
                reasons.append("Strong ATR break")
            elif atr_break_ratio >= 0.25:
                score += 8
                reasons.append("Acceptable ATR break")
            elif atr_break_ratio >= 0.10:
                score += 3
                reasons.append("Small ATR break")
            else:
                score -= 8
                reasons.append("Tiny ATR break")

            bos_atr_ratio = round(atr_break_ratio, 2)

            # Final grade
            if score >= 80:
                grade = "A_PLUS"
                risk = 1.0
            elif score >= 65:
                grade = "A"
                risk = 0.8
            elif score >= 50:
                grade = "B"
                risk = 0.5
            elif score >= 35:
                grade = "C"
                risk = 0.25
            else:
                grade = "D"
                risk = 0.0

            new_bos = bos.copy()
            new_bos["importance_score"] = score
            new_bos["importance_grade"] = grade
            new_bos["risk_multiplier"] = risk
            new_bos["atr_break_ratio"] = bos_atr_ratio
            new_bos["importance_reasons"] = reasons

            scored.append(new_bos)

        return scored

    def get_tradable_bos(self, scored_bos):
        return [
            bos for bos in scored_bos
            if bos["importance_grade"] in ["A_PLUS", "A", "B"]
        ]

    def _calculate_atr_at_index(self, index, period=14):

        if index < period:
            return 0

        recent_data = self.data.iloc[index - period:index]

        ranges = recent_data["high"] - recent_data["low"]

        return ranges.mean()
    