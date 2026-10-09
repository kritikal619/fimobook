import unittest
from datetime import datetime, timedelta, timezone

from app import kst_datetime_filter


class KstDatetimeFilterTest(unittest.TestCase):
    def test_naive_database_utc_is_shifted_to_kst(self):
        value = datetime(2026, 8, 13, 1, 30)
        self.assertEqual(kst_datetime_filter(value), "2026-08-13 10:30")

    def test_aware_utc_is_shifted_to_kst_across_date_boundary(self):
        value = datetime(2026, 8, 13, 18, 30, tzinfo=timezone.utc)
        self.assertEqual(kst_datetime_filter(value), "2026-08-14 03:30")

    def test_aware_non_utc_value_is_converted_to_kst(self):
        value = datetime(2026, 8, 13, 10, 30, tzinfo=timezone(timedelta(hours=2)))
        self.assertEqual(kst_datetime_filter(value), "2026-08-13 17:30")

    def test_custom_format_and_missing_value(self):
        value = datetime(2026, 8, 13, 18, 30)
        self.assertEqual(kst_datetime_filter(value, "%m.%d"), "08.14")
        self.assertEqual(kst_datetime_filter(None), "-")


if __name__ == "__main__":
    unittest.main()
