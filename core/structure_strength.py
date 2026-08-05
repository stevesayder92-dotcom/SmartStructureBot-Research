class StructureStrengthEngine:
    """
    Causal structure-strength scorer.

    The score uses only:
    - the structure candle,
    - candles before it,
    - and candles up to confirmed_at_index.

    It never uses candles after the structure became available.
    """

    def __init__(self, data):
        self.data = data.copy().reset_index(drop=True)

    def score_structure_points(self, classified_points):
        scored_points = []

        for point in classified_points:
            structure_index = point.get("index")
            confirmed_at = point.get(
                "confirmed_at_index",
                structure_index,
            )

            if structure_index is None or confirmed_at is None:
                continue

            if not 0 <= structure_index < len(self.data):
                continue

            confirmed_at = min(
                int(confirmed_at),
                len(self.data) - 1,
            )

            if confirmed_at < structure_index:
                continue

            candle_range = (
                self.data.at[structure_index, "high"]
                - self.data.at[structure_index, "low"]
            )
            candle_body = abs(
                self.data.at[structure_index, "close"]
                - self.data.at[structure_index, "open"]
            )

            body_ratio = (
                candle_body / candle_range
                if candle_range > 0
                else 0.0
            )

            wick_size = max(candle_range - candle_body, 0.0)

            average_range = self._average_prior_range(
                confirmed_at,
                lookback=20,
            )

            causal_displacement = self._causal_displacement(
                structure_index,
                confirmed_at,
            )

            displacement_ratio = (
                causal_displacement / average_range
                if average_range > 0
                else 0.0
            )

            score = 0

            if body_ratio >= 0.60:
                score += 25
            elif body_ratio >= 0.40:
                score += 15
            else:
                score += 5

            if displacement_ratio >= 2.0:
                score += 35
            elif displacement_ratio >= 1.0:
                score += 20
            elif displacement_ratio >= 0.5:
                score += 10

            if wick_size > candle_body:
                score += 10

            confirmation_delay = confirmed_at - structure_index

            if confirmation_delay <= 3:
                score += 15
            elif confirmation_delay <= 8:
                score += 8

            score = min(score, 100)

            new_point = point.copy()
            new_point["strength_score"] = score
            new_point["strength_class"] = self._strength_class(score)
            new_point["strength_available_at_index"] = confirmed_at
            new_point["strength_is_causal"] = True
            new_point["causal_displacement"] = causal_displacement
            new_point["causal_displacement_ratio"] = displacement_ratio
            new_point["confirmation_delay"] = confirmation_delay
            new_point["future_displacement_used"] = False

            scored_points.append(new_point)

        return scored_points

    def _causal_displacement(
        self,
        structure_index,
        confirmed_at,
    ):
        window = self.data.iloc[
            structure_index:confirmed_at + 1
        ]

        if window.empty:
            return 0.0

        structure_close = float(
            self.data.at[structure_index, "close"]
        )
        highest = float(window["high"].max())
        lowest = float(window["low"].min())

        return max(
            abs(highest - structure_close),
            abs(structure_close - lowest),
        )

    def _average_prior_range(
        self,
        index,
        lookback=20,
    ):
        start = max(0, index - lookback)
        ranges = (
            self.data["high"] - self.data["low"]
        ).iloc[start:index]

        if ranges.empty:
            return 0.0

        return float(ranges.mean())

    def _strength_class(self, score):
        if score >= 70:
            return "STRONG"

        if score >= 40:
            return "MEDIUM"

        return "WEAK"
