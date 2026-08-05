from __future__ import annotations

import unittest

from core.setup_lifecycle import SetupLifecycleRegistry


class SetupLifecycleRegistryTest(unittest.TestCase):
    def setUp(self):
        self.registry = SetupLifecycleRegistry()

    def _observe(
        self,
        *,
        start: int = 20,
        end: int = 30,
        as_of: int = 40,
        origin: int = 10,
        direction: str = "BULLISH",
    ):
        return self.registry.observe(
            symbol="GER40Cash#",
            timeframe=5,
            direction=direction,
            origin_trend_bos_index=origin,
            initial_pullback_start=start,
            current_pullback_end=end,
            as_of_index=as_of,
            descriptive_status="WAITING_FOR_CONFIRMATION",
            retracement_direction="BEARISH_PULLBACK",
            quality="NORMAL_RETRACEMENT",
            causal=True,
        )

    def test_evolving_pullback_keeps_one_setup_id(self):
        first = self._observe()
        second = self._observe(
            start=22,
            end=35,
            as_of=41,
        )

        self.assertEqual(
            first["setup_id"],
            second["setup_id"],
        )
        self.assertEqual(
            second["initial_pullback_start"],
            20,
        )
        self.assertEqual(
            second["current_pullback_end"],
            35,
        )
        self.assertEqual(len(self.registry.setups), 1)

    def test_consumption_blocks_same_setup_identity(self):
        first = self._observe()
        consumed = self.registry.consume(
            first["setup_id"],
            42,
        )
        same = self._observe(
            start=25,
            end=39,
            as_of=43,
        )

        self.assertEqual(
            same["setup_id"],
            first["setup_id"],
        )
        self.assertEqual(same["status"], "CONSUMED")
        self.assertEqual(
            same["consumed_at_index"],
            42,
        )
        self.assertEqual(
            consumed["reentry_count"],
            0,
        )

    def test_new_post_completion_pullback_gets_new_id(self):
        first = self._observe()
        self.registry.consume(
            first["setup_id"],
            42,
        )
        new_setup = self._observe(
            start=50,
            end=55,
            as_of=60,
            origin=45,
        )

        self.assertNotEqual(
            first["setup_id"],
            new_setup["setup_id"],
        )
        self.assertEqual(
            new_setup["initial_pullback_start"],
            50,
        )
        self.assertEqual(len(self.registry.setups), 2)

    def test_reentry_is_hard_limited_to_one(self):
        setup = self._observe()
        armed = self.registry.arm_reentry(
            setup["setup_id"],
            44,
        )

        self.assertEqual(armed["reentry_count"], 1)
        self.assertEqual(
            armed["status"],
            "REENTRY_PENDING",
        )

        with self.assertRaisesRegex(
            ValueError,
            "at most one re-entry",
        ):
            self.registry.arm_reentry(
                setup["setup_id"],
                45,
            )


if __name__ == "__main__":
    unittest.main()
