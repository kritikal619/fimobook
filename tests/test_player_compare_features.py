import unittest
from pathlib import Path

import app as app_module


class PlayerCompareFeaturesTest(unittest.TestCase):
    def setUp(self):
        self.original_players = app_module.PLAYER_DATA
        app_module._TEAM_FILTER_CONTEXT_CACHE.clear()

    def tearDown(self):
        app_module.PLAYER_DATA = self.original_players
        app_module._TEAM_FILTER_CONTEXT_CACHE.clear()

    def test_compare_player_exposes_price_and_correct_skill_move_label(self):
        player = {
            "cid": 901,
            "playerKor": "테스트 선수",
            "className": "TEST",
            "position": "ST",
            "ovr": 147,
            "skillMovesLevel": 4,
            "skillMovesName": "라 크로케타",
            "n8Price0": 110_000_000,
        }

        compare_player = app_module._build_compare_player(player)

        self.assertEqual(compare_player["skillMovesDisplay"], "5성 라 크로케타")
        self.assertEqual(compare_player["price"], 110_000_000)
        self.assertEqual(compare_player["priceByEnhance"][0], 110_000_000)

    def test_basic_compare_rows_exclude_ovr_and_keep_requested_order(self):
        expected = ["footPair", "skillMovesDisplay", "height", "weight"]
        self.assertEqual(list(app_module.FIELD_COMPARE_STAT_GROUPS["기본"]), expected)
        self.assertEqual(list(app_module.GK_COMPARE_STAT_GROUPS["기본"]), expected)

    def test_squad_search_returns_only_four_ultimate_skill_labels(self):
        app_module.PLAYER_DATA = [
            {
                "cid": 902,
                "pid": 90,
                "playerKor": "얼티밋 테스트",
                "className": "26TOTS",
                "position": "ST",
                "ovr": 147,
                "n8Price0": 110_000_000,
                "skills": [
                    {"id": "262001", "name": "베이스 하나"},
                    {"id": "262002", "name": "얼티밋 하나"},
                    {"id": "262003", "name": "얼티밋 둘"},
                    {"id": "262004", "name": "베이스 둘"},
                    {"id": "262005", "name": "얼티밋 셋"},
                    {"id": "262006", "name": "얼티밋 넷"},
                ],
            }
        ]

        response = app_module.app.test_client().get("/api/squad_players?q=얼티밋")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(
            payload[0]["ultimateSkillLabels"],
            ["얼티밋 하나", "얼티밋 둘", "얼티밋 셋", "얼티밋 넷"],
        )

    def test_templates_link_compare_tool_and_render_compact_price(self):
        home_template = Path("templates/search.html").read_text(encoding="utf-8")
        compare_template = Path("templates/compare_players.html").read_text(encoding="utf-8")

        self.assertIn("url_for('player_compare_page')", home_template)
        self.assertIn('<span class="tool-name">선수 비교</span>', home_template)
        self.assertIn("function formatShortPrice(value)", compare_template)
        self.assertIn("function priceWithMpIcon(value)", compare_template)
        self.assertIn("images/ea-token.png", compare_template)
        self.assertIn("priceWithMpIcon(priceForEnhance(player, slot.enhance))", compare_template)
        self.assertIn("priceWithMpIcon(player.price)", compare_template)
        self.assertIn("player.ultimateSkillLabels.slice(0, 4)", compare_template)
        self.assertIn(
            'const BASIC_STAT_ORDER = ["footPair", "skillMovesDisplay", "height", "weight"]',
            compare_template,
        )


if __name__ == "__main__":
    unittest.main()
