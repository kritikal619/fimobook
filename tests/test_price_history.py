import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from price_history import (
    build_snapshot_rows,
    connect_price_history,
    extract_price_array,
    get_player_price_history,
    load_player_price_history,
    replace_daily_snapshots,
)


class PriceHistoryTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "prices.db"
        self.connection = connect_price_history(self.database_path)

    def tearDown(self):
        self.connection.close()
        self.temp_dir.cleanup()

    def test_extracts_all_levels_and_legacy_base_price(self):
        prices = extract_price_array(
            {"n8Price": "1200", "n8Price1": 1500, "n8Price2": 0}
        )
        self.assertEqual(prices[0], 1200)
        self.assertEqual(prices[1], 1500)
        self.assertIsNone(prices[2])
        self.assertEqual(len(prices), 16)

    def test_skips_players_without_a_cid_or_any_price(self):
        rows = build_snapshot_rows(
            [
                {"cid": 101, "n8Price0": 1000},
                {"cid": 102, "n8Price0": 0},
                {"cid": "bad", "n8Price0": 2000},
            ],
            date(2026, 8, 12),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 101)

    def test_same_day_rerun_atomically_replaces_snapshot(self):
        first_players = [
            {"cid": 101, "n8Price0": 1000, "n8Price1": 1500},
            {"cid": 102, "n8Price0": 2000},
        ]
        second_players = [{"cid": 101, "n8Price0": 1100}]

        replace_daily_snapshots(
            self.connection,
            first_players,
            date(2026, 8, 12),
            min_fetched_player_count=0,
            min_priced_player_count=0,
        )
        replace_daily_snapshots(
            self.connection,
            second_players,
            date(2026, 8, 12),
            min_fetched_player_count=0,
            min_priced_player_count=0,
        )

        rows = self.connection.execute(
            "SELECT player_cid, base_price FROM player_price_snapshot"
        ).fetchall()
        self.assertEqual([(row[0], row[1]) for row in rows], [(101, 1100)])

    def test_history_is_returned_oldest_first(self):
        for snapshot_date, price in (
            (date(2026, 8, 12), 1000),
            (date(2026, 8, 13), 1200),
        ):
            replace_daily_snapshots(
                self.connection,
                [{"cid": 101, "n8Price0": price}],
                snapshot_date,
                collected_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
                min_fetched_player_count=0,
                min_priced_player_count=0,
            )

        history = get_player_price_history(self.connection, 101)
        self.assertEqual([item["date"] for item in history], ["2026-08-12", "2026-08-13"])
        self.assertEqual([item["base_price"] for item in history], [1000, 1200])

    def test_two_scheduled_snapshots_are_preserved_on_the_same_day(self):
        kst = ZoneInfo("Asia/Seoul")
        morning = datetime(2026, 8, 19, 3, tzinfo=kst)
        afternoon = datetime(2026, 8, 19, 15, tzinfo=kst)

        replace_daily_snapshots(
            self.connection,
            [{"cid": 101, "n8Price0": 1000}],
            morning,
            min_fetched_player_count=0,
            min_priced_player_count=0,
        )
        replace_daily_snapshots(
            self.connection,
            [{"cid": 101, "n8Price0": 1200}],
            afternoon,
            min_fetched_player_count=0,
            min_priced_player_count=0,
        )

        history = get_player_price_history(self.connection, 101)
        self.assertEqual(
            [item["timestamp"] for item in history],
            ["2026-08-19T03:00:00+09:00", "2026-08-19T15:00:00+09:00"],
        )
        self.assertEqual([item["base_price"] for item in history], [1000, 1200])

    def test_rerun_replaces_only_the_same_scheduled_slot(self):
        kst = ZoneInfo("Asia/Seoul")
        morning = datetime(2026, 8, 19, 3, tzinfo=kst)
        afternoon = datetime(2026, 8, 19, 15, tzinfo=kst)
        for snapshot_at, price in ((morning, 1000), (afternoon, 1200), (morning, 1100)):
            replace_daily_snapshots(
                self.connection,
                [{"cid": 101, "n8Price0": price}],
                snapshot_at,
                min_fetched_player_count=0,
                min_priced_player_count=0,
            )

        history = get_player_price_history(self.connection, 101)
        self.assertEqual([item["base_price"] for item in history], [1100, 1200])

    def test_safety_threshold_preserves_existing_day(self):
        replace_daily_snapshots(
            self.connection,
            [{"cid": 101, "n8Price0": 1000}],
            date(2026, 8, 12),
            min_fetched_player_count=0,
            min_priced_player_count=0,
        )

        with self.assertRaises(ValueError):
            replace_daily_snapshots(
                self.connection,
                [],
                date(2026, 8, 12),
                min_fetched_player_count=1,
                min_priced_player_count=1,
            )

        count = self.connection.execute(
            "SELECT COUNT(*) FROM player_price_snapshot"
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_readonly_loader_does_not_create_missing_database(self):
        missing_path = Path(self.temp_dir.name) / "missing.db"
        self.assertEqual(load_player_price_history(missing_path, 101), [])
        self.assertFalse(missing_path.exists())

    def test_readonly_loader_returns_recent_history(self):
        replace_daily_snapshots(
            self.connection,
            [{"cid": 101, "n8Price0": 1000}],
            date(2026, 8, 12),
            min_fetched_player_count=0,
            min_priced_player_count=0,
        )
        self.connection.commit()
        history = load_player_price_history(self.database_path, 101)
        self.assertEqual(history[0]["date"], "2026-08-12")
        self.assertEqual(history[0]["prices"][0], 1000)


if __name__ == "__main__":
    unittest.main()
