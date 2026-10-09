import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_module


class LandingPageSeoTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            PUBLIC_BASE_URL="https://fcbook.info",
        )
        self.client = app_module.app.test_client()

    def test_home_targets_fc_mobile_player_search(self):
        with (
            patch.object(app_module, "_latest_home_review_activity", return_value=[]),
            patch.object(app_module, "_latest_notice_post", return_value=None),
        ):
            response = self.client.get("/", base_url="https://fcbook.info")

        html = response.data.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("<title>피모북 - FC모바일 선수 검색</title>", html)
        self.assertIn('<h1 class="seo-page-title">FC모바일 선수 검색</h1>', html)
        self.assertIn("clip-path:inset(50%)", html)
        self.assertNotIn('<span class="tool-name">선수 비교</span>', html)
        self.assertIn('<span class="tool-name">쿠폰</span>', html)

        blocks = re.findall(
            r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
            html,
            re.DOTALL,
        )
        website = next(item for item in map(json.loads, blocks) if item.get("@type") == "WebSite")
        self.assertEqual(website["name"], "피모북")
        self.assertEqual(website["url"], "https://fcbook.info/")

    def test_comparison_has_unique_search_intent_content(self):
        response = self.client.get("/player_compare", base_url="https://fcbook.info")
        html = response.data.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("<title>FC모바일 선수 비교 - 능력치·진화·스킬 | 피모북</title>", html)
        self.assertIn("<h1>FC모바일 선수 비교</h1>", html)
        self.assertIn("FC모바일 선수 비교 방법", html)
        self.assertIn(': "FC모바일 선수 비교 - 능력치·진화·스킬 | 피모북";', html)
        self.assertIn('<link rel="canonical" href="https://fcbook.info/player_compare">', html)

    def test_coupon_page_has_code_reward_and_registration_content(self):
        coupon = {
            "code": "SEO-TEST",
            "category": "테스트",
            "manualStatus": "auto",
            "boolExpires": False,
            "expires": "-",
            "items": ["보상"],
            "added": "2026-09-01",
            "statusOverridden": False,
        }
        with patch.object(app_module, "get_coupons", return_value=[coupon]):
            response = self.client.get("/coupons/", base_url="https://fcbook.info")
        html = response.data.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("<title>FC모바일 쿠폰 코드·보상·등록 방법 | 피모북</title>", html)
        self.assertIn('<h1 class="coupon-title">FC모바일 쿠폰</h1>', html)
        self.assertIn("FC모바일 쿠폰 등록 방법", html)
        self.assertIn("게임 내 또는 FC모바일 공식 사이트", html)
        self.assertIn("복사한 <strong>쿠폰명</strong>을 입력", html)
        self.assertIn('meta name="description" content="FC모바일 최신 등록 쿠폰: SEO-TEST.', html)
        self.assertIn('meta property="og:description" content="FC모바일 최신 등록 쿠폰: SEO-TEST.', html)
        self.assertIn('<details class="coupon-guide">', html)
        self.assertIn("<summary>이용 안내</summary>", html)
        self.assertIn('class="coupon-guide-content"', html)

    def test_feature_sitemap_includes_comparison_page(self):
        response = self.client.get("/sitemaps/sitemap_pages.xml")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"https://fcbook.info/player_compare", response.data)

    def test_renewal_times_has_server_rendered_search_content(self):
        response = self.client.get("/times", base_url="https://fcbook.info")
        html = response.data.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "<title>FC모바일 갱신시간 - 클래스별 다음 갱신 시간 | 피모북</title>",
            html,
        )
        self.assertIn('<h1 class="times-title">FC모바일 갱신시간</h1>', html)
        self.assertIn('meta name="description" content="FC모바일 클래스별 갱신시간', html)
        self.assertIn('data-server-rendered="true"', html)
        self.assertIn("일반 아이콘", html)
        self.assertIn("홀수시 32분", html)
        self.assertIn("FC모바일 갱신시간 확인 방법", html)
        self.assertIn('<details class="times-guide">', html)
        self.assertIn("<summary>이용 안내</summary>", html)
        self.assertIn('class="times-guide-content"', html)
        self.assertIn('<link rel="canonical" href="https://fcbook.info/times">', html)

    def test_advanced_search_explains_filter_intent(self):
        response = self.client.get("/traits_selection", base_url="https://fcbook.info")
        html = response.data.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "<title>FC모바일 선수 세부검색 - 특성·스킬·경력 필터 | 피모북</title>",
            html,
        )
        self.assertIn("<h1>FC모바일 선수 세부검색</h1>", html)
        self.assertIn('meta name="description" content="FC모바일 선수를 이름, OVR, 가격', html)
        self.assertIn("FC모바일 선수 세부검색 사용 방법", html)
        self.assertIn("현재 소속팀 또는 전체 팀 경력", html)
        self.assertIn('<details class="detail-search-guide">', html)
        self.assertIn("<summary>이용 안내</summary>", html)
        self.assertIn('class="detail-search-guide-content"', html)
        self.assertIn('<link rel="canonical" href="https://fcbook.info/traits_selection">', html)

    def test_seo_guides_have_dark_theme_surfaces_and_readable_text(self):
        css = Path("static/css/theme.css").read_text(encoding="utf-8")
        theme_head = Path("templates/_theme_head.html").read_text(encoding="utf-8")

        for selector in (
            ".compare-guide",
            ".coupon-guide",
            ".times-guide",
            ".detail-search-guide",
            ".compare-hero-desc",
            ".times-desc",
        ):
            self.assertIn(selector, css)
        self.assertIn("background: var(--dark-panel) !important", css)
        self.assertIn("color: var(--dark-muted) !important", css)
        self.assertIn("20260901-detail-guide-compact", theme_head)


if __name__ == "__main__":
    unittest.main()
