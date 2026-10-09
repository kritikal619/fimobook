import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_module


class AnalyticsMeasurementTest(unittest.TestCase):
    def setUp(self):
        self.previous_measurement_id = app_module.app.config.get("GA_MEASUREMENT_ID", "")
        self.previous_disabled = app_module.app.config.get("FIMOBOOK_ANALYTICS_DISABLED", False)
        app_module.app.config["GA_MEASUREMENT_ID"] = "G-TEST123"
        app_module.app.config["FIMOBOOK_ANALYTICS_DISABLED"] = False
        self.client = app_module.app.test_client()

    def tearDown(self):
        app_module.app.config["GA_MEASUREMENT_ID"] = self.previous_measurement_id
        app_module.app.config["FIMOBOOK_ANALYTICS_DISABLED"] = self.previous_disabled

    def test_public_production_page_uses_privacy_safe_config_page_view(self):
        response = self.client.get("/times?query=should-not-enter-page-location", base_url="https://fcbook.info")
        html = response.data.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("G-TEST123", html)
        self.assertNotIn("send_page_view: false", html)
        self.assertIn("page_location: window.fimoAnalytics.pageLocation", html)
        self.assertIn("'utm_source'", html)
        self.assertIn("'utm_medium'", html)
        self.assertIn("'gclid'", html)
        self.assertIn("pageUrl.searchParams.delete(paramName)", html)
        analytics_snippet = html.split("<!-- Google Analytics:", 1)[1].split(
            '<script src="/static/js/site-metrics.js', 1
        )[0]
        self.assertNotIn("should-not-enter-page-location", analytics_snippet)
        self.assertIn('"page_type": "renewal_times"', html)
        self.assertIn('"content_group": "utility"', html)
        self.assertIn("/static/js/site-metrics.js", html)

    def test_dedicated_google_tag_configures_only_current_fcbook_stream(self):
        app_module.app.config["GA_MEASUREMENT_ID"] = "G-J8ZL7VF352"
        html = self.client.get("/times", base_url="https://fcbook.info").data.decode("utf-8")

        self.assertIn("gtag/js?id=GT-WKPJTP28", html)
        self.assertNotIn("gtag/js?id=G-J8ZL7VF352", html)
        self.assertNotIn("gtag/js?id=G-KJ387QBM97", html)
        self.assertEqual(html.count("gtag('config',"), 1)
        self.assertIn('gtag(\'config\', "GT-WKPJTP28"', html)
        self.assertNotIn('gtag(\'config\', "G-J8ZL7VF352"', html)
        self.assertNotIn('gtag(\'config\', "G-KJ387QBM97"', html)
        self.assertIn('measurementId: "G-J8ZL7VF352"', html)
        self.assertNotIn("gtag('event', 'page_view'", html)
        self.assertIn("measurement_version: '2026-09-06-2'", html)

    def test_localhost_never_sends_production_analytics(self):
        response = self.client.get("/times", base_url="http://localhost")
        html = response.data.decode("utf-8")

        self.assertNotIn("googletagmanager.com/gtag/js", html)
        self.assertNotIn("/static/js/site-metrics.js", html)

    def test_secret_and_admin_pages_are_excluded(self):
        secret_response = self.client.get(
            "/secret/player-review-summary",
            base_url="https://fcbook.info",
        )
        self.assertNotIn("googletagmanager.com/gtag/js", secret_response.data.decode("utf-8"))

        with patch.object(app_module, "_is_admin_user", return_value=True):
            admin_response = self.client.get("/times", base_url="https://fcbook.info")
        self.assertNotIn("googletagmanager.com/gtag/js", admin_response.data.decode("utf-8"))

    def test_known_crawlers_do_not_receive_analytics_tag(self):
        crawler_agents = (
            "Mozilla/5.0 (compatible; MJ12bot/v1.4.8; http://mj12bot.com/)",
            "Mozilla/5.0 (compatible; Amzn-SearchBot/0.1) Chrome/119 Safari/537.36",
            "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
            "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
            "CriteoBot/0.1 (+https://www.criteo.com/criteo-crawler/)",
            "Mozilla/5.0 (compatible; Yeti/1.1; +https://naver.me/spd)",
            "Mediapartners-Google",
            "Mozilla/5.0 AppleWebKit/537.36; compatible; ChatGPT-User/1.0; +https://openai.com/bot",
            "Mozilla/5.0 (compatible; ClaudeBot/1.0; +https://anthropic.com/bot)",
            "Mozilla/5.0 (compatible; PerplexityBot/1.0; +https://perplexity.ai/bot)",
        )
        for user_agent in crawler_agents:
            with self.subTest(user_agent=user_agent):
                response = self.client.get(
                    "/times",
                    base_url="https://fcbook.info",
                    headers={"User-Agent": user_agent},
                )
                self.assertNotIn(
                    "googletagmanager.com/gtag/js",
                    response.data.decode("utf-8"),
                )

    def test_real_mobile_device_with_bot_in_model_name_keeps_analytics(self):
        response = self.client.get(
            "/times",
            base_url="https://fcbook.info",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Linux; Android 9; CUBOT X19 Build/PPR1) "
                    "AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"
                )
            },
        )
        self.assertIn("googletagmanager.com/gtag/js", response.data.decode("utf-8"))

    def test_global_disable_switch_stops_collection(self):
        app_module.app.config["FIMOBOOK_ANALYTICS_DISABLED"] = True
        response = self.client.get("/player_compare", base_url="https://fcbook.info")
        self.assertNotIn("googletagmanager.com/gtag/js", response.data.decode("utf-8"))

    def test_core_tools_render_measurement_hooks(self):
        compare_html = self.client.get(
            "/player_compare",
            base_url="https://fcbook.info",
        ).data.decode("utf-8")
        filter_html = self.client.get(
            "/traits_selection",
            base_url="https://fcbook.info",
        ).data.decode("utf-8")
        squad_html = self.client.get(
            "/squad_maker",
            base_url="https://fcbook.info",
        ).data.decode("utf-8")

        self.assertIn('"page_type": "player_compare"', compare_html)
        self.assertIn('trackAnalytics("comparison_complete"', compare_html)
        self.assertIn('data-ga-event="advanced_filter_apply"', filter_html)
        self.assertIn('trackAnalytics("squad_complete"', squad_html)
        self.assertEqual(squad_html.count("googletagmanager.com/gtag/js"), 1)

    def test_shared_client_tracks_active_use_without_idle_time(self):
        script = Path(app_module.app.root_path, "static/js/site-metrics.js").read_text(encoding="utf-8")

        self.assertNotIn('window.fetch(', script)
        self.assertIn('window.gtag("event", eventName', script)
        self.assertNotIn('"fimo_ga_client_id"', script)
        self.assertNotIn('"fimo_ga_session_id"', script)
        self.assertIn("siteMetricsLastEvent", script)
        self.assertIn('"site_interaction"', script)
        self.assertIn('document.visibilityState === "visible"', script)
        self.assertIn("document.hasFocus()", script)
        self.assertIn("Date.now() - lastInteractionAt <= 30000", script)
        self.assertIn('"qualified_engagement"', script)
        self.assertIn('"active_time_milestone"', script)

    @patch("requests.post")
    def test_legacy_tabs_cannot_continue_server_side_collection(self, post):
        for client_id in ("12345678.1700000000", "f39a262b-63fb-40da-aa83-9a2f015748e2"):
            response = self.client.post(
                "/api/analytics/event", base_url="https://fcbook.info",
                headers={"Origin": "https://fcbook.info"},
                json={"event_name": "site_interaction", "client_id": client_id,
                      "session_id": "1700000000", "params": {"measurement_version": "2026-08-31-3"}},
            )
            self.assertEqual(response.status_code, 204)
        post.assert_not_called()

    @patch("requests.post")
    def test_legacy_endpoint_never_validates_or_forwards_payloads(self, post):
        response = self.client.post(
            "/api/analytics/event",
            base_url="https://fcbook.info",
            headers={"Origin": "https://example.com"},
            json={
                "event_name": "anything",
                "client_id": "invalid",
                "session_id": "invalid",
            },
        )

        self.assertEqual(response.status_code, 204)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
