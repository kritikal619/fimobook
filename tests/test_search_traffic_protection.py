from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SearchTrafficProtectionTests(unittest.TestCase):
    def test_dynamic_search_routes_are_disallowed_for_compliant_crawlers(self):
        robots = (ROOT / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("Disallow: /search", robots)
        self.assertIn("Disallow: /filtered_players", robots)
        self.assertIn("Disallow: /autocomplete", robots)
        self.assertIn("Disallow: /api/", robots)

    def test_search_results_do_not_load_ads(self):
        template = (ROOT / "templates" / "results.html").read_text(encoding="utf-8")
        self.assertNotIn("_adsense_head.html", template)
        self.assertNotIn("_adsense_unit.html", template)

    def test_nginx_search_limits_and_incident_network_block_are_present(self):
        zones = (ROOT / "deploy" / "nginx" / "cloudflare-real-ip-rate-limit.conf").read_text(encoding="utf-8")
        site = (ROOT / "deploy" / "nginx" / "fimobook-site.conf").read_text(encoding="utf-8")
        self.assertIn("zone=search_per_ip:10m rate=5r/m", zones)
        self.assertIn('"Mozilla/5.0 (Windows NT 10.0; Win64; x64)" 1;', zones)
        self.assertIn("location = /search", site)
        self.assertIn("deny 2406:5900:1177:721c::/64;", site)
        self.assertIn("limit_req zone=search_per_ip burst=15 nodelay;", site)

    def test_player_thumbnails_do_not_share_the_dynamic_page_rate_limit(self):
        for relative_path in (
            "deploy/nginx/fimobook-site.conf",
            "ops/nginx/fimobook.conf",
        ):
            site = (ROOT / relative_path).read_text(encoding="utf-8")
            media_location = site.split("location ^~ /media/player/ {", 1)[1].split("\n    }", 1)[0]
            self.assertIn("limit_conn dynamic_conn_per_ip 64;", media_location)
            self.assertNotIn("limit_req ", media_location)


if __name__ == "__main__":
    unittest.main()
