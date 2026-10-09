import json
import re
import unittest
from unittest.mock import patch
from pathlib import Path

import app as app_module


class NormalModePowerRankingTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            PUBLIC_BASE_URL="https://fcbook.info",
        )
        self.client = app_module.app.test_client()

    def test_power_ranking_page_renders_filters_and_visuals(self):
        ranking_data = {
            "version": 1,
            "meta": {
                "updated_at": "2026-09-07 22:30",
                "scope": "일반모드 TOP 1~100 (일부 제외)",
                "source_name": "샤인",
                "source_url": "",
                "notice": "테스트 안내",
            },
            "players": [
                {
                    "position": "ST",
                    "class_name": "26얼토츠",
                    "player_name": "음바페",
                    "counts": {"top_1_50": 10, "top_51_100": 11},
                }
            ],
        }
        with patch.object(app_module, "_load_normal_mode_power_ranking", return_value=ranking_data):
            response = self.client.get(
                "/normal-mode-power-ranking",
                base_url="https://fcbook.info",
            )

        html = response.data.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("<title>FC모바일 일반모드 파워랭킹 | 피모북</title>", html)
        self.assertIn("<h1>일반모드 파워랭킹</h1>", html)
        self.assertIn('data-scope="top_1_50"', html)
        self.assertNotIn('data-group="FW"', html)
        self.assertIn('id="powerPositionSelect"', html)
        self.assertIn('class="power-toolbar-tools"', html)
        self.assertIn('id="powerPositionRankList"', html)
        self.assertIn('id="powerOverallList"', html)
        self.assertNotIn('powerPositionOptions', html)
        self.assertNotIn('power-group-tabs', html)
        self.assertNotIn('powerPitch', html)
        self.assertNotIn('power-hero', html)
        self.assertNotIn('일반모드 상위 랭커 선수 사용 기록', html)
        self.assertNotIn('집계 안내', html)
        self.assertIn('데이터 제공 : 샤인, 아우프비더젠', html)
        data_match = re.search(
            r'<script type="application/json" id="normalPowerRankingData">(.*?)</script>',
            html,
        )
        self.assertIsNotNone(data_match)
        rendered_data = json.loads(data_match.group(1))
        self.assertEqual(rendered_data["players"][0]["player_name"], "음바페")
        self.assertIn(
            '<link rel="canonical" href="https://fcbook.info/normal-mode-power-ranking">',
            html,
        )

    def test_power_ranking_page_is_linked_from_navigation(self):
        with patch.object(app_module, "_load_normal_mode_power_ranking", return_value={"meta": {}, "players": []}):
            response = self.client.get("/normal-mode-power-ranking")

        self.assertIn(
            'href="/normal-mode-power-ranking"',
            response.data.decode("utf-8"),
        )

    def test_imported_dataset_has_pid_cid_and_source_totals(self):
        data_path = Path(app_module.app.root_path) / "static/data/normal-mode-power-ranking.json"
        data = json.loads(data_path.read_text(encoding="utf-8"))
        players = data["players"]
        self.assertGreaterEqual(len(players), 200)
        self.assertTrue(all(int(player["pid"]) > 0 and int(player["cid"]) > 0 for player in players))
        self.assertTrue(all(player["season_abbr"] and player["player_name"] for player in players))
        self.assertEqual(sum(player["counts"]["top_1_50"] for player in players), 355)
        self.assertEqual(sum(player["counts"]["top_51_100"] for player in players), 418)

        by_source_label = {
            label: player
            for player in players
            for label in player.get("source_labels", [])
        }
        self.assertEqual(by_source_label["썸머 밀리토"]["display_name"], "SS26 디에고 밀리토")
        self.assertEqual(by_source_label["26챔피언스 고메스"]["display_name"], "CMP26 마리오 고메스")
        self.assertEqual(by_source_label["월드게임 야야투레"]["cid"], 22902253)
        self.assertEqual(by_source_label["FCA 루시우"]["cid"], 22900994)

    def test_power_ranking_page_embeds_imported_dataset(self):
        response = self.client.get("/normal-mode-power-ranking", base_url="https://fcbook.info")
        html = response.data.decode("utf-8")
        data_match = re.search(
            r'<script type="application/json" id="normalPowerRankingData">(.*?)</script>',
            html,
        )
        self.assertIsNotNone(data_match)
        rendered_data = json.loads(data_match.group(1))
        self.assertEqual(len(rendered_data["players"]), 223)
        self.assertEqual(rendered_data["players"][0]["pid"], 231747)
        self.assertEqual(rendered_data["players"][0]["season_abbr"], "26TOTS")
        self.assertEqual(rendered_data["players"][0]["player_name"], "킬리안 음바페")
        self.assertTrue(rendered_data["players"][0]["card_image"])
        self.assertTrue(rendered_data["players"][0]["face_image"])


if __name__ == "__main__":
    unittest.main()
