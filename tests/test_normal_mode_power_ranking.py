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
        for element_id in (
            "powerEdition",
            "powerScopes",
            "powerSearch",
            "powerPositions",
            "powerRows",
            "powerCredit",
        ):
            self.assertIn(f'id="{element_id}"', html)
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
        self.assertTrue(all(player["display_name"] for player in players))

        # Every ranked squad fills the same number of slots, so each rank range
        # must account for exactly ranked squads x slots per squad.
        meta = data["meta"]
        slots_per_squad = meta["slot_count"] // meta["squad_count"]
        for scope, squad_count in meta["rank_ranges"].items():
            self.assertEqual(
                sum(player["counts"][scope] for player in players),
                squad_count * slots_per_squad,
            )

    def test_power_ranking_page_embeds_imported_dataset(self):
        response = self.client.get("/normal-mode-power-ranking", base_url="https://fcbook.info")
        html = response.data.decode("utf-8")
        data_match = re.search(
            r'<script type="application/json" id="normalPowerRankingData">(.*?)</script>',
            html,
        )
        self.assertIsNotNone(data_match)
        rendered_data = json.loads(data_match.group(1))
        data_path = Path(app_module.app.root_path) / "static/data/normal-mode-power-ranking.json"
        source_players = json.loads(data_path.read_text(encoding="utf-8"))["players"]
        self.assertEqual(len(rendered_data["players"]), len(source_players))
        for key in ("pid", "cid", "season_abbr", "player_name"):
            self.assertEqual(rendered_data["players"][0][key], source_players[0][key])
        self.assertTrue(rendered_data["players"][0]["card_image"])
        self.assertTrue(rendered_data["players"][0]["face_image"])


if __name__ == "__main__":
    unittest.main()
