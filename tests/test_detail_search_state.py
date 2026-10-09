import unittest
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlsplit

import app as app_module


class _ResultsFormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_sort_form = False
        self.hidden_fields = []
        self.back_url = ""

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "form" and "sort-form" in attributes.get("class", "").split():
            self.in_sort_form = True
        elif tag == "input" and self.in_sort_form and attributes.get("type") == "hidden":
            self.hidden_fields.append((attributes.get("name", ""), attributes.get("value", "")))
        elif tag == "a" and "back-btn" in attributes.get("class", "").split():
            self.back_url = attributes.get("href", "")

    def handle_endtag(self, tag):
        if tag == "form" and self.in_sort_form:
            self.in_sort_form = False


class DetailSearchStateTest(unittest.TestCase):
    def setUp(self):
        self.original_players = app_module.PLAYER_DATA
        app_module.PLAYER_DATA = [
            {
                "cid": 9101,
                "pid": 9101,
                "playerKor": "조건 유지 선수",
                "className": "STATE TEST",
                "position": "ST",
                "ovr": 140,
                "height": 188,
                "n8Price0": 5_000,
            },
            {
                "cid": 9102,
                "pid": 9102,
                "playerKor": "제외 선수",
                "className": "OTHER",
                "position": "ST",
                "ovr": 140,
                "height": 175,
                "n8Price0": 50_000,
            },
        ]
        app_module._ADVANCED_FILTER_OPTIONS_CACHE.clear()
        app_module._TEAM_FILTER_CONTEXT_CACHE.clear()
        self.client = app_module.app.test_client()

    def tearDown(self):
        app_module.PLAYER_DATA = self.original_players
        app_module._ADVANCED_FILTER_OPTIONS_CACHE.clear()
        app_module._TEAM_FILTER_CONTEXT_CACHE.clear()

    def test_sort_form_and_back_link_keep_every_filter(self):
        filters = [
            ("player_class", "STATE TEST"),
            ("min_ovr", "100"),
            ("max_ovr", "200"),
            ("min_height", "180"),
            ("max_height", "195"),
            ("min_price", "1000"),
            ("max_price", "10000"),
            ("sort", "ovr_desc"),
        ]
        response = self.client.get("/filtered_players?" + urlencode(filters))
        self.assertEqual(response.status_code, 200)

        parser = _ResultsFormParser()
        parser.feed(response.data.decode("utf-8"))
        hidden_query = parse_qs(urlencode(parser.hidden_fields))
        for name, expected in {
            "player_class": ["STATE TEST"],
            "min_height": ["180"],
            "max_height": ["195"],
            "min_price": ["1000"],
            "max_price": ["10000"],
        }.items():
            self.assertEqual(hidden_query.get(name), expected)

        sorted_response = self.client.get(
            "/filtered_players?" + urlencode(parser.hidden_fields + [("sort", "price_desc")])
        )
        sorted_html = sorted_response.data.decode("utf-8")
        self.assertIn("/player/9101", sorted_html)
        self.assertNotIn("/player/9102", sorted_html)
        self.assertIn("1000~10000 MP", sorted_html)

        back_query = parse_qs(urlsplit(parser.back_url).query)
        self.assertEqual(back_query.get("player_class"), ["STATE TEST"])
        self.assertEqual(back_query.get("min_height"), ["180"])
        self.assertEqual(back_query.get("max_height"), ["195"])
        self.assertEqual(back_query.get("min_price"), ["1000"])
        self.assertEqual(back_query.get("max_price"), ["10000"])

        search_response = self.client.get(parser.back_url)
        search_html = search_response.data.decode("utf-8")
        self.assertIn("restoreFiltersFromUrl", search_html)
        self.assertIn("window.history.replaceState", search_html)


if __name__ == "__main__":
    unittest.main()
