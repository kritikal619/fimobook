import unittest

import app as app_module


class PositionFilterTest(unittest.TestCase):
    def setUp(self):
        self.original_players = app_module.PLAYER_DATA
        app_module._TEAM_FILTER_CONTEXT_CACHE.clear()

    def tearDown(self):
        app_module.PLAYER_DATA = self.original_players
        app_module._TEAM_FILTER_CONTEXT_CACHE.clear()

    @staticmethod
    def _player(cid, primary, potential="", postion2=None, postion3=None):
        return {
            "cid": cid,
            "pid": cid,
            "playerKor": f"테스트 선수 {cid}",
            "className": "TEST",
            "position": primary,
            "positionOrg": primary,
            "potentialPosition": potential,
            "postion2": postion2 or [],
            "postion3": postion3 or [],
            "ovr": 140,
            "n8Price0": 1_000,
        }

    def test_every_position_uses_only_primary_or_actual_sub_position(self):
        for index, position in enumerate(app_module.POSITION_COMPATIBILITY, start=1):
            with self.subTest(position=position):
                primary = self._player(index * 10 + 1, position)
                actual_sub = self._player(index * 10 + 2, "OTHER", potential=position)
                penalty_only = self._player(
                    index * 10 + 3,
                    "OTHER",
                    potential="DIFFERENT",
                    postion2=[position],
                    postion3=[position],
                )

                self.assertTrue(
                    app_module._player_matches_position_filter(
                        primary, {position}, include_sub_position=True
                    )
                )
                self.assertTrue(
                    app_module._player_matches_position_filter(
                        actual_sub, {position}, include_sub_position=True
                    )
                )
                self.assertFalse(
                    app_module._player_matches_position_filter(
                        penalty_only, {position}, include_sub_position=True
                    )
                )

    def test_detail_and_squad_search_share_actual_sub_position_rule(self):
        app_module.PLAYER_DATA = [
            self._player(101, "CAM"),
            self._player(102, "CM", potential="CAM"),
            self._player(103, "ST", potential="", postion3=["CAM"]),
        ]
        app_module._TEAM_FILTER_CONTEXT_CACHE.clear()
        client = app_module.app.test_client()

        detail_response = client.get(
            "/filtered_players?min_ovr=0&max_ovr=200"
            "&position=CAM&include_sub_position=1"
        )
        detail_html = detail_response.data.decode("utf-8")
        squad_response = client.get(
            "/api/squad_players?position=CAM&include_sub_position=1&limit=10"
        )

        self.assertEqual(detail_response.status_code, 200)
        self.assertIn("/player/101", detail_html)
        self.assertIn("/player/102", detail_html)
        self.assertNotIn("/player/103", detail_html)
        self.assertEqual(squad_response.status_code, 200)
        self.assertEqual(
            {player["cid"] for player in squad_response.get_json()},
            {101, 102},
        )


if __name__ == "__main__":
    unittest.main()
