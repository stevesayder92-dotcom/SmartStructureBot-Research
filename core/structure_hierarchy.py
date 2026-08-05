class StructureHierarchyEngine:
    """
    Causal structure hierarchy.

    A point may occur at one candle but only become major, protected,
    liquid, or tradeable at a later candle. Every hierarchy label therefore
    carries an explicit availability index.
    """

    def __init__(self, data, as_of_index=None):
        self.data = data.copy().reset_index(drop=True)
        self.as_of_index = (
            len(self.data) - 1
            if as_of_index is None
            else int(as_of_index)
        )

    def build_hierarchy(self, classified_highs, classified_lows):
        highs = [point.copy() for point in classified_highs]
        lows = [point.copy() for point in classified_lows]

        all_points = []

        for point in highs:
            point["side"] = "HIGH"
            all_points.append(point)

        for point in lows:
            point["side"] = "LOW"
            all_points.append(point)

        all_points = sorted(
            all_points,
            key=lambda point: (
                point.get("index", -1),
                point.get(
                    "confirmed_at_index",
                    point.get("index", -1),
                ),
            ),
        )

        if not all_points:
            return [], [], []

        for point in all_points:
            confirmed_at = point.get(
                "confirmed_at_index",
                point.get("index"),
            )

            point["structure_rank"] = "INTERNAL"
            point["decision_weight"] = 1

            point["is_major"] = False
            point["major_at_index"] = None

            point["is_protected"] = False
            point["protected_at_index"] = None
            point["protected_by_index"] = None

            point["is_liquidity"] = False
            point["liquidity_at_index"] = None

            point["is_tradeable_structure"] = False
            point["tradeable_at_index"] = None

            point["hierarchy_available_at_index"] = confirmed_at
            point["hierarchy_reason"] = []

        self._mark_major_points(all_points)
        self._mark_protected_points(all_points)
        self._mark_liquidity_points(all_points)
        self._mark_tradeable_points(all_points)

        final_highs = [
            point for point in all_points
            if point["side"] == "HIGH"
        ]
        final_lows = [
            point for point in all_points
            if point["side"] == "LOW"
        ]

        return final_highs, final_lows, all_points

    def _confirmed_at(self, point):
        return point.get(
            "confirmed_at_index",
            point.get("index"),
        )

    def _mark_major_points(self, points, lookback=3):
        """
        Major status may require right-side points, so major_at_index is the
        latest confirmation time among all points used in that decision.
        """

        for position, point in enumerate(points):
            left = points[max(0, position - lookback):position]
            right = points[
                position + 1:position + 1 + lookback
            ]

            same_side_neighbours = [
                candidate
                for candidate in left + right
                if candidate["side"] == point["side"]
            ]

            if not same_side_neighbours:
                continue

            if point["side"] == "HIGH":
                qualifies = point["body_price"] >= max(
                    candidate["body_price"]
                    for candidate in same_side_neighbours
                )
            else:
                qualifies = point["body_price"] <= min(
                    candidate["body_price"]
                    for candidate in same_side_neighbours
                )

            if not qualifies:
                continue

            evidence_points = [point] + same_side_neighbours
            major_at = max(
                self._confirmed_at(candidate)
                for candidate in evidence_points
            )

            point["major_at_index"] = major_at
            point["hierarchy_available_at_index"] = max(
                point["hierarchy_available_at_index"],
                major_at,
            )

            if major_at <= self.as_of_index:
                point["is_major"] = True
                point["structure_rank"] = "MAJOR"
                point["decision_weight"] += 3
                point["hierarchy_reason"].append(
                    "Major status became available after nearby "
                    "same-side structures were confirmed"
                )

    def _mark_protected_points(self, points, forward_points=7):
        """
        Protected status is retrospective unless its availability time is
        recorded. A low becomes protected only when a later confirmed HH
        proves bullish expansion. A high becomes protected only when a later
        confirmed LL proves bearish expansion.
        """

        for position, point in enumerate(points):
            future = points[
                position + 1:position + 1 + forward_points
            ]

            confirming_point = None

            if (
                point["side"] == "LOW"
                and point["type"] in ["HL", "LL"]
            ):
                confirming_candidates = [
                    candidate
                    for candidate in future
                    if candidate["side"] == "HIGH"
                    and candidate["type"] == "HH"
                ]

                if confirming_candidates:
                    confirming_point = confirming_candidates[0]

            elif (
                point["side"] == "HIGH"
                and point["type"] in ["LH", "HH"]
            ):
                confirming_candidates = [
                    candidate
                    for candidate in future
                    if candidate["side"] == "LOW"
                    and candidate["type"] == "LL"
                ]

                if confirming_candidates:
                    confirming_point = confirming_candidates[0]

            if confirming_point is None:
                continue

            protected_at = max(
                self._confirmed_at(point),
                self._confirmed_at(confirming_point),
            )

            point["protected_at_index"] = protected_at
            point["protected_by_index"] = confirming_point["index"]
            point["hierarchy_available_at_index"] = max(
                point["hierarchy_available_at_index"],
                protected_at,
            )

            if protected_at <= self.as_of_index:
                point["is_protected"] = True
                point["structure_rank"] = "PROTECTED"
                point["decision_weight"] += 4
                point["hierarchy_reason"].append(
                    "Protected status became available after "
                    f"{confirming_point['type']} confirmation"
                )

    def _mark_liquidity_points(
        self,
        points,
        tolerance_ratio=0.25,
    ):
        atr = self._average_range()
        tolerance = atr * tolerance_ratio if atr > 0 else 0

        for position, point in enumerate(points):
            previous_same_side = [
                candidate
                for candidate in points[:position]
                if candidate["side"] == point["side"]
            ][-5:]

            matching_previous = next(
                (
                    candidate
                    for candidate in reversed(previous_same_side)
                    if abs(
                        point["body_price"]
                        - candidate["body_price"]
                    ) <= tolerance
                ),
                None,
            )

            if matching_previous is None:
                continue

            liquidity_at = max(
                self._confirmed_at(point),
                self._confirmed_at(matching_previous),
            )

            point["liquidity_at_index"] = liquidity_at
            point["hierarchy_available_at_index"] = max(
                point["hierarchy_available_at_index"],
                liquidity_at,
            )

            if liquidity_at <= self.as_of_index:
                point["is_liquidity"] = True
                point["decision_weight"] += 2
                point["hierarchy_reason"].append(
                    "Near-equal same-side structure became "
                    "available as liquidity"
                )

    def _mark_tradeable_points(self, points):
        for point in points:
            availability_candidates = []

            if point["is_major"]:
                availability_candidates.append(
                    point["major_at_index"]
                )

            if point["is_protected"]:
                availability_candidates.append(
                    point["protected_at_index"]
                )

            if (
                point["is_liquidity"]
                and point["decision_weight"] >= 3
            ):
                availability_candidates.append(
                    point["liquidity_at_index"]
                )

            if point["decision_weight"] >= 4:
                availability_candidates.append(
                    point["hierarchy_available_at_index"]
                )

            availability_candidates = [
                value
                for value in availability_candidates
                if value is not None
            ]

            if availability_candidates:
                tradeable_at = min(availability_candidates)
                point["tradeable_at_index"] = tradeable_at
                point["is_tradeable_structure"] = (
                    tradeable_at <= self.as_of_index
                )
            else:
                point["structure_rank"] = "INTERNAL"
                point["is_tradeable_structure"] = False

    def _average_range(self, period=20):
        ranges = self.data["high"] - self.data["low"]

        if len(ranges) < period:
            return float(ranges.mean())

        return float(ranges.tail(period).mean())
