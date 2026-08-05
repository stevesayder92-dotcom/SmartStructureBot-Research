class ProtectedStructureEngine:
    """
    Causal decision-protection engine.

    Decision protection is used only to validate the active trend/setup.
    It is not a stop-loss engine and it does not manage trailing protection.

    Rules:
    - Protection must be available by the decision/anchor candle.
    - Protection must precede the active pullback when that boundary exists.
    - No unrestricted HL/LH fallback is allowed without a valid trend BOS.
    - Invalidation uses directional candle CLOSE, not body extremes or wicks.
    """

    def __init__(self, as_of_index=None):
        self.as_of_index = as_of_index

    def find_protected_structure(
        self,
        classified_highs,
        classified_lows,
        market_state,
        tradable_bos,
        anchor_bos=None,
    ):
        trend = market_state.get(
            "final_trend_context",
            market_state.get("trend", "UNKNOWN"),
        )
        as_of_index = self._resolve_as_of(
            classified_highs,
            classified_lows,
            tradable_bos,
        )
        active_pullback = market_state.get("active_retracement") or {}
        pullback_start = active_pullback.get("start_index")

        result = {
            "trend_context": trend,
            "protection_role": "DECISION_PROTECTION",
            "protected_high": None,
            "protected_low": None,
            "last_trend_bos": None,
            "anchor_bos_used": None,
            "anchor_source": None,
            "as_of_index": as_of_index,
            "protection_available_at_index": None,
            "protection_score": 0,
            "protection_grade": "D",
            "confidence": "VERY_LOW",
            "protection_confidence": "VERY_LOW",
            "candidate_count": 0,
            "protection_broken": False,
            "protection_broken_at_index": None,
            "protection_level": None,
            "causal_valid": True,
            "fallback_used": False,
            "selected_reason": [],
            "reason": [],
        }

        if trend not in ["BULLISH", "BEARISH"]:
            result["reason"].append("No directional trend context")
            return result

        anchor = self._select_anchor(
            trend=trend,
            tradable_bos=tradable_bos,
            anchor_bos=anchor_bos,
            as_of_index=as_of_index,
        )

        if anchor is None:
            result["reason"].append(
                "No causally available same-direction BOS anchor"
            )
            return result

        result["last_trend_bos"] = anchor
        result["anchor_bos_used"] = anchor
        result["anchor_source"] = (
            "CURRENT_ENTRY_BOS"
            if anchor_bos is not None
            and anchor.get("index") == anchor_bos.get("index")
            else "LATEST_TREND_BOS"
        )

        anchor_index = anchor.get("index")
        if anchor_index is None:
            result["causal_valid"] = False
            result["reason"].append("Anchor BOS has no index")
            return result

        if trend == "BULLISH":
            candidates = self._eligible_candidates(
                points=classified_lows,
                expected_side="LOW",
                allowed_types=["HL", "LL"],
                expected_type="HL",
                anchor_index=anchor_index,
                pullback_start=pullback_start,
                as_of_index=as_of_index,
            )
        else:
            candidates = self._eligible_candidates(
                points=classified_highs,
                expected_side="HIGH",
                allowed_types=["LH", "HH"],
                expected_type="LH",
                anchor_index=anchor_index,
                pullback_start=pullback_start,
                as_of_index=as_of_index,
            )

        result["candidate_count"] = len(candidates)

        if not candidates:
            result["reason"].append(
                "No causally available protection candidate before anchor"
            )
            return result

        chosen = self._choose_candidate(
            candidates,
            expected_type="HL" if trend == "BULLISH" else "LH",
            anchor_index=anchor_index,
        )

        score, grade, confidence, reasons = self._score_candidate(
            chosen,
            expected_type="HL" if trend == "BULLISH" else "LH",
            anchor_index=anchor_index,
        )
        chosen = chosen.copy()
        chosen["protection_score"] = score
        chosen["protection_grade"] = grade
        chosen["protection_confidence"] = confidence
        chosen["protection_reason"] = reasons

        availability = max(
            self._availability_index(chosen),
            int(anchor.get(
                "decision_available_at_index",
                anchor_index,
            )),
        )

        if availability > as_of_index:
            result["causal_valid"] = False
            result["reason"].append(
                "Protection becomes available after the decision candle"
            )
            return result

        level = chosen.get("body_price")

        anchor_price = anchor.get(
            "break_price",
            anchor.get("entry_price"),
        )

        if (
            isinstance(level, (int, float))
            and isinstance(anchor_price, (int, float))
        ):
            protection_on_correct_side = (
                float(level) < float(anchor_price)
                if trend == "BULLISH"
                else float(level) > float(anchor_price)
            )

            if not protection_on_correct_side:
                result["reason"].append(
                    "Rejected decision protection because it sits "
                    "on the wrong side of the anchor price"
                )
                result["candidate_count"] = len(candidates)
                return result

        result["protection_available_at_index"] = availability
        result["protection_level"] = level
        result["protection_score"] = score
        result["protection_grade"] = grade
        result["confidence"] = confidence
        result["protection_confidence"] = confidence
        result["selected_reason"] = reasons

        if trend == "BULLISH":
            result["protected_low"] = chosen
        else:
            result["protected_high"] = chosen

        result["reason"].append(
            "Decision protection selected from the latest eligible "
            "pre-pullback structure"
        )
        return result

    def find_setup_invalidation_structure(
        self,
        data,
        market_state,
        retracement_lifecycle,
        structure_points,
    ):
        """
        Select the defended extreme of the active pullback.

        This is the original setup invalidation structure used by the
        entry engine. It is deliberately separate from broad decision
        protection and from post-entry trail protection.

        Bullish setup: select the deepest causally available LOW inside
        the active bearish pullback.
        Bearish setup: select the highest causally available HIGH inside
        the active bullish pullback.

        Invalidation is always directional candle CLOSE. Wicks do not
        invalidate the setup.
        """
        trend = market_state.get(
            "final_trend_context",
            market_state.get("trend", "UNKNOWN"),
        )
        as_of_index = int(
            self.as_of_index
            if self.as_of_index is not None
            else len(data) - 1
        )
        active = market_state.get("active_retracement") or {}
        lifecycle = retracement_lifecycle or {}

        start_index = lifecycle.get(
            "start_index",
            active.get("start_index"),
        )
        end_index = lifecycle.get(
            "end_index",
            active.get("end_index"),
        )

        result = {
            "role": "SETUP_INVALIDATION_STRUCTURE",
            "trend_context": trend,
            "side": None,
            "raw_type": None,
            "structure": None,
            "index": None,
            "price": None,
            "available_at_index": None,
            "pullback_start_index": start_index,
            "pullback_end_index": end_index,
            "candidate_count": 0,
            "selection_method": "DEFENDED_RETRACEMENT_EXTREME",
            "body_close_invalidation": True,
            "invalidation_semantics": "DIRECTIONAL_CLOSE_ONLY",
            "broken": False,
            "broken_at_index": None,
            "causal_valid": True,
            "score": 0,
            "grade": "D",
            "reason": [],
        }

        if trend not in ["BULLISH", "BEARISH"]:
            result["reason"].append("No directional trend context")
            return result

        if start_index is None:
            result["causal_valid"] = False
            result["reason"].append("Active pullback has no start index")
            return result

        upper_bound = as_of_index - 1
        if upper_bound < int(start_index):
            result["reason"].append(
                "No completed pre-entry candle exists inside pullback"
            )
            return result

        expected_side = "LOW" if trend == "BULLISH" else "HIGH"
        candidates = []

        lifecycle_points = lifecycle.get("pullback_structure_points") or []
        source_points = lifecycle_points or structure_points or []

        for point in source_points:
            index = point.get("index")
            if index is None:
                continue
            if not (int(start_index) <= int(index) <= upper_bound):
                continue
            if point.get("side") != expected_side:
                continue
            if self._availability_index(point) > as_of_index:
                continue
            price = point.get("body_price")
            if not isinstance(price, (int, float)):
                continue
            candidate = point.copy()
            candidate["_availability"] = self._availability_index(point)
            candidates.append(candidate)

        result["candidate_count"] = len(candidates)

        if not candidates:
            result["reason"].append(
                "No causally available pullback extreme candidate"
            )
            return result

        if trend == "BULLISH":
            extreme_price = min(float(p["body_price"]) for p in candidates)
            tolerance = self._price_tolerance(data, as_of_index)
            defended = [
                p for p in candidates
                if float(p["body_price"]) <= extreme_price + tolerance
            ]
        else:
            extreme_price = max(float(p["body_price"]) for p in candidates)
            tolerance = self._price_tolerance(data, as_of_index)
            defended = [
                p for p in candidates
                if float(p["body_price"]) >= extreme_price - tolerance
            ]

        # A repeated defence near the extreme is meaningful. Choose the
        # latest member of that defended cluster, not a later micro swing
        # far away from the actual pullback extreme.
        chosen = sorted(
            defended,
            key=lambda p: (
                p.get("index", -1),
                p.get("decision_weight", 0),
            ),
        )[-1]

        price = float(chosen["body_price"])
        available_at = int(chosen["_availability"])
        chosen_index = int(chosen["index"])

        broken_at = None
        for index in range(max(available_at, chosen_index), as_of_index + 1):
            close_price = float(data.at[index, "close"])
            invalidated = (
                close_price < price
                if trend == "BULLISH"
                else close_price > price
            )
            if invalidated:
                broken_at = index
                break

        cluster_size = len(defended)
        score = 60
        if cluster_size >= 2:
            score += 20
        if chosen.get("is_major") or chosen.get("is_protected"):
            score += 10
        if chosen.get("type") in (
            ["HL", "LL"] if trend == "BULLISH" else ["LH", "HH"]
        ):
            score += 10
        score = min(100, score)

        grade = "A_PLUS" if score >= 90 else "A" if score >= 80 else "B"

        structure = chosen.copy()
        structure.pop("_availability", None)

        result.update({
            "side": expected_side,
            "raw_type": chosen.get("type"),
            "structure": structure,
            "index": chosen_index,
            "price": price,
            "available_at_index": available_at,
            "broken": broken_at is not None,
            "broken_at_index": broken_at,
            "score": score,
            "grade": grade,
        })

        if cluster_size >= 2:
            result["reason"].append(
                f"Defended extreme cluster contains {cluster_size} structures"
            )
        result["reason"].append(
            "Selected the defended pullback extreme that defines setup risk"
        )
        if broken_at is None:
            result["reason"].append(
                "No directional candle close invalidated the setup extreme"
            )
        else:
            result["reason"].append(
                f"Setup extreme invalidated by candle close at {broken_at}"
            )

        return result

    def _price_tolerance(self, data, as_of_index):
        start = max(0, int(as_of_index) - 20)
        ranges = (data["high"] - data["low"]).iloc[start:as_of_index]
        if ranges.empty:
            return 0.0
        average_range = float(ranges.mean())
        return max(0.0, average_range * 0.20)

    def validate_retracement_against_protection(
        self,
        retracement_zones,
        protected_structure,
        data,
    ):
        validated = []
        trend = protected_structure.get("trend_context", "UNKNOWN")
        level = protected_structure.get("protection_level")
        available_at = protected_structure.get(
            "protection_available_at_index"
        )

        for zone in retracement_zones:
            new_zone = zone.copy()
            new_zone["structure_valid"] = True
            new_zone["invalidated_at"] = None
            new_zone["protected_level"] = level
            new_zone["validity_reason"] = []

            if (
                trend not in ["BULLISH", "BEARISH"]
                or level is None
                or available_at is None
            ):
                new_zone["structure_valid"] = False
                new_zone["validity_reason"].append(
                    "No causally available decision protection"
                )
                validated.append(new_zone)
                continue

            start = max(
                int(zone.get("start_index", 0)),
                int(available_at),
            )
            end = min(
                int(zone.get("end_index", len(data) - 1)),
                len(data) - 1,
            )

            for index in range(start, end + 1):
                close_price = float(data["close"].iloc[index])

                invalidated = (
                    close_price < float(level)
                    if trend == "BULLISH"
                    else close_price > float(level)
                )

                if invalidated:
                    new_zone["structure_valid"] = False
                    new_zone["invalidated_at"] = index
                    new_zone["validity_reason"].append(
                        "Decision protection invalidated by directional close"
                    )
                    break

            if new_zone["structure_valid"]:
                new_zone["validity_reason"].append(
                    "Decision protection held through the retracement"
                )

            validated.append(new_zone)

        return validated

    def _select_anchor(
        self,
        trend,
        tradable_bos,
        anchor_bos,
        as_of_index,
    ):
        expected_entry = (
            "BULLISH_ENTRY_BOS"
            if trend == "BULLISH"
            else "BEARISH_ENTRY_BOS"
        )
        expected_bos = (
            "BULLISH_BOS"
            if trend == "BULLISH"
            else "BEARISH_BOS"
        )

        if (
            anchor_bos
            and anchor_bos.get("type") in [expected_entry, expected_bos]
            and anchor_bos.get("index", as_of_index + 1) <= as_of_index
            and anchor_bos.get("causal_valid", True)
        ):
            return anchor_bos

        candidates = [
            bos for bos in tradable_bos
            if bos.get("type") == expected_bos
            and bos.get("index") is not None
            and bos["index"] <= as_of_index
            and bos.get(
                "decision_available_at_index",
                bos["index"],
            ) <= as_of_index
            and bos.get("causal_valid", True)
        ]

        if not candidates:
            return None

        return sorted(candidates, key=lambda bos: bos["index"])[-1]

    def _eligible_candidates(
        self,
        points,
        expected_side,
        allowed_types,
        expected_type,
        anchor_index,
        pullback_start,
        as_of_index,
    ):
        upper_bound = anchor_index
        if pullback_start is not None:
            upper_bound = min(upper_bound, int(pullback_start))

        candidates = []
        for point in points:
            index = point.get("index")
            if index is None or index >= upper_bound:
                continue
            if point.get("side", expected_side) != expected_side:
                continue
            if point.get("type") not in allowed_types:
                continue
            if self._availability_index(point) > as_of_index:
                continue
            if (
                point.get("is_tradeable_structure", False)
                and point.get("tradeable_at_index") is not None
                and point["tradeable_at_index"] > as_of_index
            ):
                continue

            candidate = point.copy()
            candidate["_expected_type"] = (
                candidate.get("type") == expected_type
            )
            candidates.append(candidate)

        return candidates

    def _choose_candidate(
        self,
        candidates,
        expected_type,
        anchor_index,
    ):
        preferred = [
            point for point in candidates
            if point.get("type") == expected_type
        ]
        pool = preferred or candidates

        # Structural trading prioritises the latest valid decision point.
        return sorted(
            pool,
            key=lambda point: (
                point.get("index", -1),
                point.get("decision_weight", 0),
            ),
        )[-1]

    def _score_candidate(
        self,
        point,
        expected_type,
        anchor_index,
    ):
        score = 40
        reasons = []

        if point.get("type") == expected_type:
            score += 25
            reasons.append(
                f"Correct decision-protection type: {expected_type}"
            )
        else:
            score += 8
            reasons.append(
                f"Fallback structure type: {point.get('type')}"
            )

        if point.get("is_protected"):
            score += 15
            reasons.append("Hierarchy protection is causally available")
        elif point.get("is_major"):
            score += 10
            reasons.append("Major structure is causally available")

        gap = anchor_index - point.get("index", anchor_index)
        if 2 <= gap <= 50:
            score += 15
            reasons.append("Protection is structurally close to the anchor")
        elif gap > 100:
            score -= 15
            reasons.append("Protection is old relative to the anchor")

        score = max(0, min(100, score))

        if score >= 85:
            return score, "A_PLUS", "VERY_HIGH", reasons
        if score >= 72:
            return score, "A", "HIGH", reasons
        if score >= 58:
            return score, "B", "MEDIUM", reasons
        if score >= 42:
            return score, "C", "LOW", reasons
        return score, "D", "VERY_LOW", reasons

    def _availability_index(self, point):
        values = [
            point.get("confirmed_at_index"),
            point.get("tradeable_at_index"),
            point.get("protected_at_index"),
        ]
        values = [int(value) for value in values if value is not None]
        if values:
            return max(values)
        return int(point.get("index", 0))

    def _resolve_as_of(
        self,
        highs,
        lows,
        bos_events,
    ):
        if self.as_of_index is not None:
            return int(self.as_of_index)

        indexes = [
            point.get("index", 0)
            for point in list(highs) + list(lows) + list(bos_events)
        ]
        return max(indexes) if indexes else 0