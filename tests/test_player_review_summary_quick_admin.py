import unittest
from unittest.mock import patch

import app as app_module


class PlayerReviewSummaryQuickAdminTest(unittest.TestCase):
    def setUp(self):
        self.previous_csrf = app_module.app.config.get("WTF_CSRF_ENABLED", True)
        app_module.app.config["WTF_CSRF_ENABLED"] = False

    def tearDown(self):
        app_module.app.config["WTF_CSRF_ENABLED"] = self.previous_csrf

    def _authenticated_client(self):
        client = app_module.app.test_client()
        with client.session_transaction() as session:
            session["player_summary_admin"] = True
        return client

    def test_player_reference_accepts_detail_url_and_cid(self):
        player = {"cid": 22901978, "playerKor": "D. 드로그바"}
        with patch.object(app_module, "_get_local_player_by_cid", return_value=player) as lookup:
            self.assertEqual(
                app_module._resolve_admin_summary_player("https://fcbook.info/player/22901978?from=admin"),
                player,
            )
            self.assertEqual(app_module._resolve_admin_summary_player("22901978"), player)
        self.assertEqual(lookup.call_count, 2)

    def test_quick_form_is_visible_after_admin_authentication(self):
        client = self._authenticated_client()
        with patch.object(app_module, "_load_player_review_summaries", return_value={}):
            response = client.get("/secret/player-review-summary")
        html = response.data.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("요약 리뷰 빠른 등록", html)
        self.assertIn('name="player_reference"', html)
        self.assertIn('name="review_summary_json"', html)

    def test_quick_save_parses_json_and_stores_selected_player(self):
        client = self._authenticated_client()
        player = {
            "cid": 22901978,
            "playerKor": "D. 드로그바",
            "className": "아이콘",
        }
        with patch.object(app_module, "_resolve_admin_summary_player", return_value=player), \
             patch.object(app_module, "_store_player_review_summary", autospec=True) as store:
            response = client.post(
                "/secret/player-review-summary",
                data={
                    "action": "quick_save",
                    "player_reference": "22901978",
                    "review_summary_json": '{"pros":["몸싸움"],"cons":["체감"],"final_verdict":"강력한 공격수"}',
                },
            )

        self.assertEqual(response.status_code, 302)
        store.assert_called_once_with(
            player,
            summary_text="강력한 공격수",
            strengths="• 몸싸움",
            weaknesses="• 체감",
        )


if __name__ == "__main__":
    unittest.main()
