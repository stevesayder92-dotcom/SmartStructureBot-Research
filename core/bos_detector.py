class BOSDetector:
    """
    Causal BOS Detector.

    Rules:
    - Bullish BOS requires candle CLOSE above the structure level.
    - Bearish BOS requires candle CLOSE below the structure level.
    - Wicks and candle-body extremes do not count as BOS.
    - A structure cannot be broken before it has been confirmed.
    - break_price is always the candle close.
    """

    def __init__(self, data):
        self.data = data.copy().reset_index(drop=True)

    def detect_bos(self, classified_highs, classified_lows):
        raw_bos_events = []
        broken_high_indexes = set()
        broken_low_indexes = set()

        structure_highs = sorted(
            classified_highs,
            key=lambda point: (
                point.get("index", -1),
                point.get("confirmed_at_index", point.get("index", -1)),
            ),
        )
        structure_lows = sorted(
            classified_lows,
            key=lambda point: (
                point.get("index", -1),
                point.get("confirmed_at_index", point.get("index", -1)),
            ),
        )

        for candle_index in range(len(self.data)):
            candle_close = self.data.at[candle_index, "close"]

            previous_highs = [
                high for high in structure_highs
                if high.get("index") is not None
                and high["index"] < candle_index
                and high.get("confirmed_at_index", high["index"]) <= candle_index
                and high["index"] not in broken_high_indexes
                and high.get("is_tradeable_structure", True)
                and high.get(
                    "tradeable_at_index",
                    high.get("confirmed_at_index", high["index"])
                ) <= candle_index
            ]

            previous_lows = [
                low for low in structure_lows
                if low.get("index") is not None
                and low["index"] < candle_index
                and low.get("confirmed_at_index", low["index"]) <= candle_index
                and low["index"] not in broken_low_indexes
                and low.get("is_tradeable_structure", True)
                and low.get(
                    "tradeable_at_index",
                    low.get("confirmed_at_index", low["index"])
                ) <= candle_index
            ]

            if previous_highs:
                last_high = previous_highs[-1]
                level = last_high.get("body_price")
                if level is not None and candle_close > level:
                    raw_bos_events.append(
                        self._build_bos_event(
                            "BULLISH_BOS",
                            candle_index,
                            candle_close,
                            last_high,
                        )
                    )
                    broken_high_indexes.add(last_high["index"])

            if previous_lows:
                last_low = previous_lows[-1]
                level = last_low.get("body_price")
                if level is not None and candle_close < level:
                    raw_bos_events.append(
                        self._build_bos_event(
                            "BEARISH_BOS",
                            candle_index,
                            candle_close,
                            last_low,
                        )
                    )
                    broken_low_indexes.add(last_low["index"])

        clean = self.remove_same_candle_conflicts(raw_bos_events)
        return self.cluster_bos_events(clean)

    def _build_bos_event(
        self,
        bos_type,
        candle_index,
        candle_close,
        broken_structure,
    ):
        structure_index = broken_structure.get("index")
        confirmed_at = broken_structure.get(
            "confirmed_at_index",
            structure_index,
        )
        structure_price = broken_structure.get("body_price")
        structure_type = broken_structure.get("type")

        return {
            "type": bos_type,
            "index": candle_index,
            "break_price": candle_close,
            "entry_price": candle_close,
            "broken_structure_index": structure_index,
            "broken_structure_confirmed_at_index": confirmed_at,
            "broken_structure_price": structure_price,
            "broken_structure_type": structure_type,
            "bos_class": self._classify_bos(
                bos_type,
                structure_type,
            ),
            "decision_available_at_index": candle_index,
            "break_semantics": "DIRECTIONAL_CLOSE_ONLY",
            "causal_valid": (
                confirmed_at is not None
                and confirmed_at <= candle_index
            ),
        }

    def _classify_bos(self, bos_type, broken_structure_type):
        if bos_type == "BULLISH_BOS":
            if broken_structure_type in ["LH", "LL"]:
                return "BULLISH_REVERSAL_OR_ENTRY_BOS"
            return "BULLISH_CONTINUATION_BOS"

        if bos_type == "BEARISH_BOS":
            if broken_structure_type in ["HH", "HL"]:
                return "BEARISH_REVERSAL_OR_ENTRY_BOS"
            return "BEARISH_CONTINUATION_BOS"

        return "UNKNOWN_BOS"

    def remove_same_candle_conflicts(self, bos_events):
        grouped = {}

        for bos in bos_events:
            grouped.setdefault(bos["index"], []).append(bos)

        cleaned = []

        for events in grouped.values():
            if len(events) == 1:
                cleaned.append(events[0])
                continue

            best_event = max(
                events,
                key=lambda bos: abs(
                    bos["break_price"]
                    - bos["broken_structure_price"]
                ),
            )
            cleaned.append(best_event)

        return sorted(cleaned, key=lambda event: event["index"])

    def cluster_bos_events(self, bos_events, max_gap=5):
        if not bos_events:
            return []

        clustered_events = []
        last_master = None

        for bos in bos_events:
            new_bos = bos.copy()

            if last_master is None:
                new_bos["bos_role"] = "MASTER_BOS"
                clustered_events.append(new_bos)
                last_master = new_bos
                continue

            same_direction = (
                new_bos["type"] == last_master["type"]
            )
            close_to_master = (
                new_bos["index"] - last_master["index"]
                <= max_gap
            )

            if same_direction and close_to_master:
                new_bos["bos_role"] = "EXTENSION_BOS"
                new_bos["master_bos_index"] = (
                    last_master["index"]
                )
            else:
                new_bos["bos_role"] = "NEW_SETUP_BOS"
                last_master = new_bos

            clustered_events.append(new_bos)

        return clustered_events

    def get_trade_eligible_bos(self, bos_events):
        return [
            bos for bos in bos_events
            if bos.get("bos_role") != "EXTENSION_BOS"
            and bos.get("causal_valid", False)
        ]
