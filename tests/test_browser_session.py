import unittest
from unittest.mock import patch

import app as app_module
from tests.browser_session import page_client


class BrowserPageSessionTests(unittest.TestCase):
    def test_valid_page_session_is_required_for_search_api(self):
        self.assertEqual(app_module.app.test_client().get("/api/squad_players?q=missing").status_code, 403)
        client = page_client(app_module.app)
        with patch.object(app_module, "PLAYER_DATA", []):
            response = client.get("/api/squad_players?q=missing")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [])
        self.assertIn("private", response.headers["Cache-Control"])

    def test_cross_site_and_other_session_cannot_reuse_page_token(self):
        client = page_client(app_module.app)
        self.assertEqual(client.get("/api/squad_players", headers={"Sec-Fetch-Site": "cross-site"}).status_code, 403)
        other = app_module.app.test_client()
        response = other.get("/api/squad_players", headers={
            "X-Fimobook-Page-Token": client.environ_base["HTTP_X_FIMOBOOK_PAGE_TOKEN"],
        })
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
