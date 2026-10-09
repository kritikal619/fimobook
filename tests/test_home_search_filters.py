import unittest
from unittest.mock import patch

import app as app_module


class HomeSearchFiltersTest(unittest.TestCase):
    def setUp(self):
        self.original_players = app_module.PLAYER_DATA
        app_module.PLAYER_DATA = [
            {
                "cid": 9801,
                "pid": 9801,
                "playerKor": "필터 공격수",
                "className": "FILTER A",
                "position": "ST",
                "ovr": 145,
                "n8Price0": 1_000,
            },
            {
                "cid": 9802,
                "pid": 9802,
                "playerKor": "필터 미드필더",
                "className": "FILTER B",
                "position": "CM",
                "ovr": 140,
                "n8Price0": 2_000,
            },
        ]
        app_module._ADVANCED_FILTER_OPTIONS_CACHE.clear()

    def tearDown(self):
        app_module.PLAYER_DATA = self.original_players
        app_module._ADVANCED_FILTER_OPTIONS_CACHE.clear()

    def test_home_renders_filter_button_and_grouped_positions(self):
        with (
            patch.object(app_module, "_latest_home_review_activity", return_value=[]),
            patch.object(app_module, "_latest_notice_post", return_value=None),
        ):
            response = app_module.app.test_client().get("/")

        html = response.data.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="home-filter-btn"', html)
        self.assertIn('id="home-filter-panel"', html)
        self.assertIn("공격 전체선택", html)
        self.assertIn('data-position-group="midfield"', html)

    def test_filter_only_search_applies_ovr_position_and_class(self):
        response = app_module.app.test_client().get(
            "/search?position=ST&player_class=FILTER+A&min_ovr=145&max_ovr=145"
        )

        html = response.data.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/player/9801", html)
        self.assertNotIn("/player/9802", html)
        self.assertIn('name="position" value="ST"', html)
        self.assertIn('name="player_class" value="FILTER A"', html)


if __name__ == "__main__":
    unittest.main()
