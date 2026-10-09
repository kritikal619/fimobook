import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import app as app_module
from price_history import connect_price_history, replace_daily_snapshots


class PriceHistoryDetailTest(unittest.TestCase):
    def test_detail_page_embeds_sixty_day_history_and_chart_controls(self):
        player = app_module.PLAYER_DATA[0].copy()
        player["enhance"] = 0
        player["n8Price0"] = 1_700
        player_cid = int(player["cid"])
        tier_summary = {
            "dominant_tier": None,
            "total": 0,
            "tiers": ["S", "A", "B", "C", "D", "F"],
            "percentages": {tier: 0 for tier in ["S", "A", "B", "C", "D", "F"]},
            "my_vote": None,
            "available": False,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "history.db"
            connection = connect_price_history(database_path)
            try:
                for offset in range(8):
                    replace_daily_snapshots(
                        connection,
                        [{"cid": player_cid, "n8Price0": 1_000 + offset * 100}],
                        date(2026, 8, 12) + timedelta(days=offset),
                        min_fetched_player_count=0,
                        min_priced_player_count=0,
                    )
            finally:
                connection.close()

            previous_path = app_module.app.config["PLAYER_PRICE_HISTORY_DB"]
            app_module.app.config["PLAYER_PRICE_HISTORY_DB"] = str(database_path)
            try:
                with patch.object(app_module, "_get_local_player_by_cid", return_value=player.copy()), \
                     patch.object(app_module, "apply_live_price_fields", side_effect=lambda value: value), \
                     patch.object(app_module, "_merge_fcplayer_skill_data", side_effect=lambda value: value), \
                     patch.object(app_module, "_get_player_reviews_from_firestore", return_value=[]), \
                     patch.object(app_module, "_get_cached_player_reviews", return_value=[]), \
                     patch.object(app_module, "_get_player_club_career", return_value=None), \
                     patch.object(app_module, "_get_player_review_summary", return_value=None), \
                     patch.object(app_module, "_player_tier_summary", return_value=tier_summary):
                    response = app_module.app.test_client().get(f"/player/{player_cid}")
            finally:
                app_module.app.config["PLAYER_PRICE_HISTORY_DB"] = previous_path

        html = response.data.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("시세 동향", html)
        self.assertIn('data-price-range="60"', html)
        self.assertIn('data-price-range="30"', html)
        self.assertIn('data-price-range="7"', html)
        self.assertIn('data-price-history-enhance', html)
        self.assertIn('"date": "2026-08-19"', html)
        self.assertIn('1700', html)


if __name__ == "__main__":
    unittest.main()
