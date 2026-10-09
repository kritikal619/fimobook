import unittest

import app as app_module


class SkillMoveFilterUiTest(unittest.TestCase):
    def setUp(self):
        self.original_players = app_module.PLAYER_DATA
        app_module.PLAYER_DATA = [
            {
                "cid": 901,
                "pid": 901,
                "playerKor": "개인기 테스트 선수",
                "className": "TEST",
                "position": "CAM",
                "ovr": 140,
                "skillMovesLevel": 0,
                "skillMovesName": "라 크로케타",
                "n8Price0": 1_000,
            }
        ]
        app_module._ADVANCED_FILTER_OPTIONS_CACHE.clear()
        app_module._TEAM_FILTER_CONTEXT_CACHE.clear()

    def tearDown(self):
        app_module.PLAYER_DATA = self.original_players
        app_module._ADVANCED_FILTER_OPTIONS_CACHE.clear()
        app_module._TEAM_FILTER_CONTEXT_CACHE.clear()

    def test_detail_search_separates_rating_and_unique_skill_groups(self):
        response = app_module.app.test_client().get("/traits_selection")
        html = response.data.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('<div class="filter-label">개인기 등급</div>', html)
        self.assertIn("개인기 등급 1성", html)
        self.assertIn('<div class="filter-label">고유 개인기</div>', html)
        self.assertIn('name="skill_move" value="라 크로케타"', html)
        self.assertIn("if (search) {", html)

    def test_squad_filter_separates_rating_and_unique_skill_groups(self):
        response = app_module.app.test_client().get("/squad_maker")
        html = response.data.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("<summary>개인기 등급", html)
        self.assertIn("개인기 등급 1성", html)
        self.assertIn("<summary>고유 개인기", html)
        self.assertIn('name="skill_move" value="라 크로케타"', html)

    def test_results_chip_calls_skill_move_a_unique_skill(self):
        response = app_module.app.test_client().get(
            "/filtered_players?min_ovr=0&max_ovr=200&skill_move=라+크로케타"
        )
        html = response.data.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('<span class="chip">고유 개인기<b>라 크로케타</b></span>', html)


if __name__ == "__main__":
    unittest.main()
