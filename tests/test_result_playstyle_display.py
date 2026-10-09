import unittest

import app as app_module


class ResultPlaystyleDisplayTests(unittest.TestCase):
    def setUp(self):
        self.original_players = app_module.PLAYER_DATA
        self.two_playstyles = [
            {
                "code": "PLAYSTYLE_TEST_A_1",
                "name": "투플레이 A",
                "imageUrl": "/static/playstyles/test-a.png",
            },
            {
                "code": "PLAYSTYLE_TEST_B_1",
                "name": "투플레이 B",
                "imageUrl": "/static/playstyles/test-b.png",
            },
        ]
        self.one_playstyle = [
            {
                "code": "PLAYSTYLE_TEST_C_1",
                "name": "원플레이 C",
                "imageUrl": "/static/playstyles/test-c.png",
            }
        ]
        app_module.PLAYER_DATA = [
            self._player(99101, "UI테스트투", 77, self.two_playstyles),
            self._player(99102, "UI테스트원", 88, self.one_playstyle),
            self._player(99103, "UI테스트빈", 99, [], slot_levels=[1, 1]),
            self._player(99104, "UI테스트빈하나", 66, [], slot_levels=[1]),
        ]
        app_module._ADVANCED_FILTER_OPTIONS_CACHE.clear()
        app_module._TEAM_FILTER_CONTEXT_CACHE.clear()

    def tearDown(self):
        app_module.PLAYER_DATA = self.original_players
        app_module._ADVANCED_FILTER_OPTIONS_CACHE.clear()
        app_module._TEAM_FILTER_CONTEXT_CACHE.clear()

    @staticmethod
    def _player(cid, name, jersey_number, playstyles, slot_levels=None):
        return {
            "cid": cid,
            "pid": cid,
            "playerKor": name,
            "className": "UI TEST",
            "position": "ST",
            "ovr": 140,
            "n8Price0": 1_000,
            "jerseyNumber": jersey_number,
            "playstyles": playstyles,
            "playStyleSlotMaxLevels": slot_levels or [],
        }

    def _assert_result_ui(self, html, advanced=False):
        self.assertEqual(4, html.count('class="playstyle-pill is-icon-only"'))
        self.assertEqual(3, html.count("PLAYSTYLE_EMPTY_SLOT.png"))
        self.assertEqual(1, html.count("<span>빈 슬롯</span>"))
        self.assertNotIn("<span>투플레이 A</span>", html)
        self.assertNotIn("<span>투플레이 B</span>", html)
        self.assertIn("<span>원플레이 C</span>", html)
        self.assertNotIn("등번호", html)
        if advanced:
            self.assertNotIn("<span>#77</span>", html)
            self.assertNotIn("<span>#88</span>", html)
            self.assertNotIn("<span>#99</span>", html)
            self.assertNotIn("<span>#66</span>", html)

    def test_name_search_result_uses_two_logos_and_hides_jersey_number(self):
        response = app_module.app.test_client().get("/search?names=UI테스트")

        self.assertEqual(200, response.status_code)
        self._assert_result_ui(response.data.decode("utf-8"))

    def test_advanced_search_result_uses_two_logos_and_hides_jersey_number(self):
        response = app_module.app.test_client().get(
            "/filtered_players?name=UI테스트&min_ovr=0&max_ovr=200"
        )

        self.assertEqual(200, response.status_code)
        self._assert_result_ui(response.data.decode("utf-8"), advanced=True)


if __name__ == "__main__":
    unittest.main()
