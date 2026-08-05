class MarketStructureDetector:

    def __init__(self, data):
        self.data = data.copy()


    def detect_swings(
        self,
        min_swing_distance=3,
        min_price_distance=1.5
    ):

        swing_highs = []
        swing_lows = []

        last_swing_high_index = -100
        last_swing_low_index = -100

        last_swing_high_body = None
        last_swing_low_body = None

        for i in range(2, len(self.data) - 2):

            current_high = self.data['high'][i]
            current_low = self.data['low'][i]

            current_open = self.data['open'][i]
            current_close = self.data['close'][i]

            high_body_price = max(current_open, current_close)
            low_body_price = min(current_open, current_close)

            previous_high_1 = self.data['high'][i - 1]
            previous_high_2 = self.data['high'][i - 2]
            next_high_1 = self.data['high'][i + 1]
            next_high_2 = self.data['high'][i + 2]

            previous_low_1 = self.data['low'][i - 1]
            previous_low_2 = self.data['low'][i - 2]
            next_low_1 = self.data['low'][i + 1]
            next_low_2 = self.data['low'][i + 2]

            # Swing High
            if (
                current_high > previous_high_1 and
                current_high > previous_high_2 and
                current_high > next_high_1 and
                current_high > next_high_2
            ):

                valid_distance = i - last_swing_high_index >= min_swing_distance

                valid_price = (
                    last_swing_high_body is None or
                    abs(high_body_price - last_swing_high_body) >= min_price_distance
                )

                if valid_distance and valid_price:

                    swing_highs.append({
                        'index': i,
                        'confirmed_at_index': i + 2,
                        'confirmation_method': 'FIVE_BAR_FRACTAL',
                        'wick_price': current_high,
                        'body_price': high_body_price
                    })

                    last_swing_high_index = i
                    last_swing_high_body = high_body_price

            # Swing Low
            if (
                current_low < previous_low_1 and
                current_low < previous_low_2 and
                current_low < next_low_1 and
                current_low < next_low_2
            ):

                valid_distance = i - last_swing_low_index >= min_swing_distance

                valid_price = (
                    last_swing_low_body is None or
                    abs(low_body_price - last_swing_low_body) >= min_price_distance
                )

                if valid_distance and valid_price:

                    swing_lows.append({
                        'index': i,
                        'confirmed_at_index': i + 2,
                        'confirmation_method': 'FIVE_BAR_FRACTAL',
                        'wick_price': current_low,
                        'body_price': low_body_price
                    })

                    last_swing_low_index = i
                    last_swing_low_body = low_body_price

        return swing_highs, swing_lows


    def classify_structure(self, swing_highs, swing_lows):

        classified_highs = []
        classified_lows = []

        for i in range(1, len(swing_highs)):

            current_high = swing_highs[i]
            previous_high = swing_highs[i - 1]

            if current_high['body_price'] > previous_high['body_price']:
                structure_type = 'HH'
            else:
                structure_type = 'LH'

            classified_highs.append({
                **current_high,
                'type': structure_type
            })

        for i in range(1, len(swing_lows)):

            current_low = swing_lows[i]
            previous_low = swing_lows[i - 1]

            if current_low['body_price'] > previous_low['body_price']:
                structure_type = 'HL'
            else:
                structure_type = 'LL'

            classified_lows.append({
                **current_low,
                'type': structure_type
            })

        return classified_highs, classified_lows
    

    def detect_flow_points(
        self,
        continuation_threshold=0.8,
        pullback_threshold=0.3
    ):

        flow_highs = []
        flow_lows = []

        closes = self.data['close']
        highs = self.data['high']
        lows = self.data['low']

        current_direction = None

        for i in range(2, len(self.data) - 2):

            current_close = closes[i]

            previous_close = closes[i - 1]

            candle_move = current_close - previous_close

            # =========================
            # BULLISH FLOW DETECTION
            # =========================

            if candle_move > continuation_threshold:

                current_direction = "bullish"

                # detect recent pullback low
                recent_low = min(
                    lows[i - 2],
                    lows[i - 1],
                    lows[i]
                )

                recent_low_index = lows[
                    i - 2:i + 1
                ].idxmin()

                flow_low_index = self.data.index.get_loc(recent_low_index)

                flow_lows.append({
                    'index': flow_low_index,
                    'confirmed_at_index': i,
                    'confirmation_method': 'FLOW_MOVE_CONFIRMED',
                    'wick_price': recent_low,
                    'body_price': min(
                        self.data['open'][flow_low_index],
                        self.data['close'][flow_low_index]
                    )
                })

            # =========================
            # BEARISH FLOW DETECTION
            # =========================

            elif candle_move < -continuation_threshold:

                current_direction = "bearish"

                # detect recent pullback high
                recent_high = max(
                    highs[i - 2],
                    highs[i - 1],
                    highs[i]
                )

                recent_high_index = highs[
                    i - 2:i + 1
                ].idxmax()

                flow_high_index = self.data.index.get_loc(recent_high_index)

                flow_highs.append({
                    'index': flow_high_index,
                    'confirmed_at_index': i,
                    'confirmation_method': 'FLOW_MOVE_CONFIRMED',
                    'wick_price': recent_high,
                    'body_price': max(
                        self.data['open'][flow_high_index],
                        self.data['close'][flow_high_index]
                    )
                })

        return flow_highs, flow_lows
    
    def calculate_atr(self, period=14):
        data = self.data.copy()

        data['previous_close'] = data['close'].shift(1)

        data['high_low'] = data['high'] - data['low']
        data['high_previous_close'] = abs(data['high'] - data['previous_close'])
        data['low_previous_close'] = abs(data['low'] - data['previous_close'])

        data['true_range'] = data[
            ['high_low', 'high_previous_close', 'low_previous_close']
        ].max(axis=1)

        data['atr'] = data['true_range'].rolling(period).mean()

        return data['atr']


    def detect_atr_wave_structure(
        self,
        atr_period=14,
        atr_multiplier=1.2
    ):
        """
        Validated Fractal Swing Engine.

        Logic:
        1. Find 5-bar fractal candidates.
        2. Do NOT treat candidates as real swings immediately.
        3. Lock swing low only after price breaks above the next retracement high.
        4. Lock swing high only after price breaks below the next retracement low.
        5. Use ATR distance to ignore tiny noise.
        """

        atr_values = self.calculate_atr(atr_period)

        fractal_window = 2
        min_swing_gap = 5
        validation_lookahead = 80

        candidates = []

        # =========================
        # 1. FIND FRACTAL CANDIDATES
        # =========================

        for i in range(fractal_window, len(self.data) - fractal_window):

            atr = atr_values[i]

            if atr != atr or atr <= 0:
                continue

            current_high = self.data["high"][i]
            current_low = self.data["low"][i]

            current_open = self.data["open"][i]
            current_close = self.data["close"][i]

            body_high = max(current_open, current_close)
            body_low = min(current_open, current_close)

            left_highs = [
                self.data["high"][i - 1],
                self.data["high"][i - 2]
            ]

            right_highs = [
                self.data["high"][i + 1],
                self.data["high"][i + 2]
            ]

            left_lows = [
                self.data["low"][i - 1],
                self.data["low"][i - 2]
            ]

            right_lows = [
                self.data["low"][i + 1],
                self.data["low"][i + 2]
            ]

            is_fractal_high = (
                current_high > max(left_highs)
                and current_high > max(right_highs)
            )

            is_fractal_low = (
                current_low < min(left_lows)
                and current_low < min(right_lows)
            )

            if is_fractal_high:
                candidates.append({
                    "side": "HIGH",
                    "index": i,
                    "fractal_confirmed_at_index": i + fractal_window,
                    "wick_price": current_high,
                    "body_price": body_high,
                    "atr": atr
                })

            if is_fractal_low:
                candidates.append({
                    "side": "LOW",
                    "index": i,
                    "fractal_confirmed_at_index": i + fractal_window,
                    "wick_price": current_low,
                    "body_price": body_low,
                    "atr": atr
                })

        candidates = sorted(candidates, key=lambda x: x["index"])

        locked_highs = []
        locked_lows = []

        # =========================
        # 2. LOCK SWINGS ONLY AFTER STRUCTURE VALIDATION
        # =========================

        for idx, candidate in enumerate(candidates):

            candidate_index = candidate["index"]
            candidate_atr = candidate["atr"]

            min_price_distance = candidate_atr * atr_multiplier

            # =========================
            # LOCK SWING LOW
            # A swing low is locked only after price breaks above
            # the next retracement high.
            # =========================

            if candidate["side"] == "LOW":

                next_high = None

                for future in candidates[idx + 1:]:

                    if future["index"] - candidate_index > validation_lookahead:
                        break

                    if future["side"] == "HIGH":
                        distance = abs(
                            future["body_price"] - candidate["body_price"]
                        )

                        if distance >= min_price_distance:
                            next_high = future
                            break

                if next_high is None:
                    continue

                validation_found = False

                for candle_index in range(
                    next_high["index"] + 1,
                    min(next_high["index"] + validation_lookahead, len(self.data))
                ):

                    candle_body_high = max(
                        self.data["open"][candle_index],
                        self.data["close"][candle_index]
                    )

                    if candle_body_high > next_high["body_price"]:
                        validation_found = True
                        validation_index = candle_index
                        break

                if not validation_found:
                    continue

                locked_low = {
                    "index": candidate["index"],
                    "confirmed_at_index": validation_index,
                    "fractal_confirmed_at_index": candidate[
                        "fractal_confirmed_at_index"
                    ],
                    "wick_price": candidate["wick_price"],
                    "body_price": candidate["body_price"],
                    "method": "VALIDATED_FRACTAL_LOW",
                    "confirmation_method": "BREAK_OF_RETRACEMENT_HIGH",
                    "validated_by_break_index": validation_index,
                    "validation_level": next_high["body_price"],
                    "validation_structure_index": next_high["index"]
                }

                if locked_lows:
                    previous = locked_lows[-1]

                    too_close = (
                        locked_low["index"] - previous["index"] < min_swing_gap
                    )

                    if too_close:
                        if locked_low["body_price"] < previous["body_price"]:
                            locked_lows[-1] = locked_low
                        continue

                locked_lows.append(locked_low)

            # =========================
            # LOCK SWING HIGH
            # A swing high is locked only after price breaks below
            # the next retracement low.
            # =========================

            elif candidate["side"] == "HIGH":

                next_low = None

                for future in candidates[idx + 1:]:

                    if future["index"] - candidate_index > validation_lookahead:
                        break

                    if future["side"] == "LOW":
                        distance = abs(
                            candidate["body_price"] - future["body_price"]
                        )

                        if distance >= min_price_distance:
                            next_low = future
                            break

                if next_low is None:
                    continue

                validation_found = False

                for candle_index in range(
                    next_low["index"] + 1,
                    min(next_low["index"] + validation_lookahead, len(self.data))
                ):

                    candle_body_low = min(
                        self.data["open"][candle_index],
                        self.data["close"][candle_index]
                    )

                    if candle_body_low < next_low["body_price"]:
                        validation_found = True
                        validation_index = candle_index
                        break

                if not validation_found:
                    continue

                locked_high = {
                    "index": candidate["index"],
                    "confirmed_at_index": validation_index,
                    "fractal_confirmed_at_index": candidate[
                        "fractal_confirmed_at_index"
                    ],
                    "wick_price": candidate["wick_price"],
                    "body_price": candidate["body_price"],
                    "method": "VALIDATED_FRACTAL_HIGH",
                    "confirmation_method": "BREAK_OF_RETRACEMENT_LOW",
                    "validated_by_break_index": validation_index,
                    "validation_level": next_low["body_price"],
                    "validation_structure_index": next_low["index"]
                }

                if locked_highs:
                    previous = locked_highs[-1]

                    too_close = (
                        locked_high["index"] - previous["index"] < min_swing_gap
                    )

                    if too_close:
                        if locked_high["body_price"] > previous["body_price"]:
                            locked_highs[-1] = locked_high
                        continue

                locked_highs.append(locked_high)

        return locked_highs, locked_lows
    

    def evaluate_trade_permission(self, bos, market_state):

        grade = bos.get("importance_grade", "D")

        trade_allowed = False
        risk_multiplier = 0.0
        reason = []

        if grade == "A_PLUS":
            trade_allowed = True
            risk_multiplier = 1.0
            reason.append("Elite BOS")

        elif grade == "A":
            trade_allowed = True
            risk_multiplier = 0.8
            reason.append("Strong BOS")

        elif grade == "B":
            trade_allowed = True
            risk_multiplier = 0.5
            reason.append("Acceptable BOS")

        elif grade == "C":
            trade_allowed = True
            risk_multiplier = 0.25
            reason.append("Speculative BOS")

        else:
            trade_allowed = False
            risk_multiplier = 0.0
            reason.append("Weak BOS")

        return {
            "trade_allowed": trade_allowed,
            "risk_multiplier": risk_multiplier,
            "reason": reason
        }


    def evaluate_all_permissions(self, scored_bos, market_state):

        permissions = []

        for bos in scored_bos:

            result = self.evaluate_trade_permission(
                bos,
                market_state
            )

            permissions.append({
                **bos,
                **result
            })

        return permissions