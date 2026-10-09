import unittest

import app as app_module


class V2ExperienceTest(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_v2_home_is_isolated_and_uses_live_player_api(self):
        response = self.client.get("/v2")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('<meta name="robots" content="noindex,nofollow">', html)
        self.assertIn('css/v2-home.css', html)
        self.assertIn('js/v2-player-finder.js', html)
        self.assertIn('data-search-api="/api/squad_players"', html)
        self.assertIn('data-autocomplete-api="/autocomplete"', html)
        self.assertIn('action="/v2"', html)
        self.assertIn('name="q"', html)

    def test_v2_player_detail_renders_normalized_player_data(self):
        source_player = next(player for player in app_module.PLAYER_DATA if player.get("cid"))
        cid = int(source_player["cid"])

        response = self.client.get(f"/v2/player/{cid}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn(str(source_player.get("playerKor") or ""), html)
        self.assertIn(f'href="/player/{cid}"', html)
        self.assertIn("세부 능력치", html)
        self.assertIn("진화별 기준가", html)

    def test_v2_player_detail_has_a_clear_missing_state(self):
        response = self.client.get("/v2/player/999999999")

        self.assertEqual(response.status_code, 404)
        html = response.get_data(as_text=True)
        self.assertIn("선수를 찾을 수 없어요", html)
        self.assertIn('href="/v2"', html)


if __name__ == "__main__":
    unittest.main()
