class PhaseEngine:

    def __init__(self):
        pass

    def determine_phase(self, market_state, bos_events):
        phase = {
            "trend": market_state["trend"],
            "phase": market_state["phase"],
            "transition": "NONE",
            "choch_warning": market_state["choch_warning"],
            "confirmation": False,
            "reason": []
        }

        if not bos_events:
            phase["reason"].append("No BOS events detected")
            return phase

        recent_bos = bos_events[-5:]

        bullish_reversal_bos = [
            bos for bos in recent_bos
            if bos["bos_class"] == "BULLISH_REVERSAL_OR_ENTRY_BOS"
        ]

        bearish_reversal_bos = [
            bos for bos in recent_bos
            if bos["bos_class"] == "BEARISH_REVERSAL_OR_ENTRY_BOS"
        ]

        bullish_continuation_bos = [
            bos for bos in recent_bos
            if bos["bos_class"] == "BULLISH_CONTINUATION_BOS"
        ]

        bearish_continuation_bos = [
            bos for bos in recent_bos
            if bos["bos_class"] == "BEARISH_CONTINUATION_BOS"
        ]

        if market_state["trend"] == "BULLISH":

            if bearish_reversal_bos:
                phase["transition"] = "BULLISH_TO_BEARISH_WARNING"
                phase["phase"] = "CHOCH_WARNING"
                phase["choch_warning"] = True
                phase["reason"].append(
                    "Bearish BOS broke bullish protection structure"
                )

            if bearish_reversal_bos and bearish_continuation_bos:
                phase["transition"] = "BULLISH_TO_BEARISH_CONFIRMED"
                phase["phase"] = "BEARISH_CONFIRMATION"
                phase["confirmation"] = True
                phase["reason"].append(
                    "Bearish reversal BOS followed by bearish continuation BOS"
                )

        elif market_state["trend"] == "BEARISH":

            if bullish_reversal_bos:
                phase["transition"] = "BEARISH_TO_BULLISH_WARNING"
                phase["phase"] = "CHOCH_WARNING"
                phase["choch_warning"] = True
                phase["reason"].append(
                    "Bullish BOS broke bearish protection structure"
                )

            if bullish_reversal_bos and bullish_continuation_bos:
                phase["transition"] = "BEARISH_TO_BULLISH_CONFIRMED"
                phase["phase"] = "BULLISH_CONFIRMATION"
                phase["confirmation"] = True
                phase["reason"].append(
                    "Bullish reversal BOS followed by bullish continuation BOS"
                )

        else:
            phase["transition"] = "RANGE_OR_UNCLEAR"
            phase["reason"].append("Market state is not clearly bullish or bearish")

        return phase