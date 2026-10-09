import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from jobs.player_price_snapshot_job import _snapshot_time


class PriceSnapshotJobTest(unittest.TestCase):
    def setUp(self):
        self.kst = ZoneInfo("Asia/Seoul")

    def test_uses_morning_slot_after_three(self):
        now = datetime(2026, 8, 19, 9, 20, tzinfo=self.kst)
        self.assertEqual(
            _snapshot_time(None, now),
            datetime(2026, 8, 19, 3, tzinfo=self.kst),
        )

    def test_uses_afternoon_slot_after_fifteen(self):
        now = datetime(2026, 8, 19, 19, 20, tzinfo=self.kst)
        self.assertEqual(
            _snapshot_time(None, now),
            datetime(2026, 8, 19, 15, tzinfo=self.kst),
        )

    def test_before_three_uses_previous_afternoon_slot(self):
        now = datetime(2026, 8, 20, 1, 30, tzinfo=self.kst)
        self.assertEqual(
            _snapshot_time(None, now),
            datetime(2026, 8, 19, 15, tzinfo=self.kst),
        )

    def test_explicit_date_maps_to_morning_slot(self):
        self.assertEqual(
            _snapshot_time("2026-08-19"),
            datetime(2026, 8, 19, 3, tzinfo=self.kst),
        )


if __name__ == "__main__":
    unittest.main()
