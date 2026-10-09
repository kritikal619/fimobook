import json
import re
import unittest

import app as app_module


class PlayerDetailSeoTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            PUBLIC_BASE_URL="https://fcbook.info",
        )
        self.client = app_module.app.test_client()

    def test_detail_page_targets_fc_mobile_player_name_query(self):
        player = next(p for p in app_module.PLAYER_DATA if p.get("playerKor") == "하피냐")
        response = self.client.get(f"/player/{player['cid']}")
        html = response.data.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f"<title>FC모바일 하피냐 {player['className']} {player['ovr']} 능력치• 시세 | 피모북</title>",
            html,
        )
        self.assertIn(f'<link rel="canonical" href="https://fcbook.info/player/{player["cid"]}">', html)
        self.assertIn(
            f'<h1 class="visually-hidden">FC모바일 하피냐 {player["className"]} {player["ovr"]} 능력치• 시세</h1>',
            html,
        )
        self.assertIn(".visually-hidden {", html)
        visually_hidden_css = html.split(".visually-hidden {", 1)[1].split("}", 1)[0]
        self.assertNotIn("display: none", visually_hidden_css)
        self.assertIn("clip-path: inset(50%)", visually_hidden_css)
        self.assertIn('<h2 class="detail-section-title">모든 능력치</h2>', html)
        self.assertNotIn('data-training-bonus=', html)
        self.assertNotIn('title="훈련 상승"', html)
        self.assertIn("base + enhanceStatBonus + skillBonus + trainingBonus", html)
        self.assertIn(
            f'<div class="player-title">{player["className"]} - 하피냐</div>',
            html,
        )
        self.assertIn('meta name="description" content="FC모바일', html)

        json_ld_blocks = re.findall(
            r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
            html,
            re.DOTALL,
        )
        structured_data = [json.loads(block) for block in json_ld_blocks]
        web_page = next(item for item in structured_data if item.get("@type") == "WebPage")
        breadcrumb = next(item for item in structured_data if item.get("@type") == "BreadcrumbList")
        self.assertEqual(web_page["about"]["name"], "하피냐")
        self.assertEqual(web_page["url"], f"https://fcbook.info/player/{player['cid']}")
        self.assertEqual(breadcrumb["itemListElement"][1]["item"], "https://fcbook.info/players")

    def test_missing_player_is_a_noindex_404(self):
        response = self.client.get("/player/999999999")
        html = response.data.decode("utf-8")

        self.assertEqual(response.status_code, 404)
        self.assertIn('<meta name="robots" content="noindex,follow">', html)

    def test_robots_file_points_crawlers_to_the_sitemap(self):
        response = self.client.get("/robots.txt")
        self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content_type.startswith("text/plain"))
        self.assertIn(b"User-agent: *", response.data)
        self.assertIn(b"Sitemap: https://fcbook.info/sitemap.xml", response.data)


if __name__ == "__main__":
    unittest.main()
