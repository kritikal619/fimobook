import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import app as app_module


class SquadMakerTest(unittest.TestCase):
    def setUp(self):
        self.original_players = app_module.PLAYER_DATA
        app_module._TEAM_FILTER_CONTEXT_CACHE.clear()

    def tearDown(self):
        app_module.PLAYER_DATA = self.original_players
        app_module._TEAM_FILTER_CONTEXT_CACHE.clear()

    def _player(self, cid, pid, team, year, ovr=140, **extra):
        player = {
            "cid": cid,
            "pid": pid,
            "playerKor": "테스트 선수",
            "className": f"TEST {year}",
            "position": "ST",
            "ovr": ovr,
            "PlayerYear": year,
            "league": "테스트 리그",
            "team": team,
            "n8Price0": 1000,
        }
        player.update(extra)
        return player

    def test_squad_search_uses_current_team_by_default_and_full_career_on_request(self):
        app_module.PLAYER_DATA = [
            self._player(101, 1, "이전 팀", 2024, 139),
            self._player(102, 1, "현재 팀", 2026, 145),
        ]
        client = app_module.app.test_client()

        current_response = client.get(
            "/api/squad_players?slot=ST&league=테스트+리그&team=이전+팀"
        )
        self.assertEqual(current_response.status_code, 200)
        self.assertEqual(current_response.get_json(), [])

        with patch.object(
            app_module,
            "_extend_career_index_with_external_data",
            side_effect=lambda career_index: career_index,
        ):
            app_module._TEAM_FILTER_CONTEXT_CACHE.clear()
            career_response = client.get(
                "/api/squad_players?slot=ST&league=테스트+리그&team=이전+팀&all_career=1"
            )

        self.assertEqual(career_response.status_code, 200)
        self.assertEqual(
            {player["cid"] for player in career_response.get_json()},
            {101, 102},
        )

    def test_player_thumbnail_is_webp_and_long_lived(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "source.png"
            cache_path = Path(temp_dir) / "cache"
            Image.new("RGBA", (512, 512), (20, 180, 100, 255)).save(source_path)

            with patch.object(
                app_module,
                "_find_local_asset_path",
                return_value=str(source_path),
            ), patch.object(
                app_module,
                "PLAYER_THUMBNAIL_CACHE_DIR",
                str(cache_path),
            ):
                response = app_module.app.test_client().get(
                    "/media/player/v2/card/123-128.webp"
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, "image/webp")
            self.assertIn("max-age=31536000", response.headers["Cache-Control"])
            self.assertLess(len(response.data), source_path.stat().st_size)
            response.close()

    def test_local_assets_serve_refreshed_faceon(self):
        player = {
            "cid": 123,
            "pimage": "https://official.example/latest-faceon.png",
            "bimage": "https://official.example/card.png",
        }

        with patch.object(
            app_module,
            "_find_local_asset_url",
            side_effect=lambda kind, cid: (
                f"/static/{kind}/{cid}.png?v=v2"
                if kind == "faceon"
                else f"/static/{kind}/{cid}.png"
            ),
        ), patch.object(
            app_module,
            "_find_local_asset_path",
            return_value="/tmp/existing.png",
        ):
            normalized = app_module._apply_local_assets(player.copy())
            face_thumbnail = app_module._player_thumbnail_url("faceon", 123, 128)

        self.assertEqual(normalized["pimage"], "/static/faceon/123.png?v=v2")
        self.assertEqual(
            normalized["pimageThumb"],
            "/media/player/v2/faceon/123-256.webp",
        )
        self.assertEqual(face_thumbnail, "/media/player/v2/faceon/123-128.webp")
        self.assertEqual(normalized["bimage"], "/static/card/123.png")
        self.assertEqual(
            normalized["bimageThumb"],
            "/media/player/v2/card/123-256.webp",
        )

    def test_price_refresh_returns_canonical_artwork_for_saved_squads(self):
        app_module.PLAYER_DATA = [
            self._player(
                301,
                31,
                "현재 팀",
                2026,
                pimage="https://official.example/latest-faceon.png",
                bimage="https://official.example/card.png",
            )
        ]

        with patch.object(
            app_module,
            "populate_live_prices",
            side_effect=lambda players: None,
        ), patch.object(
            app_module,
            "_find_local_asset_url",
            side_effect=lambda kind, cid: (
                f"/static/{kind}/{cid}.png?v=v2"
                if kind == "faceon"
                else f"/static/{kind}/{cid}.png"
            ),
        ), patch.object(
            app_module,
            "_find_local_asset_path",
            return_value="/tmp/existing.png",
        ):
            response = app_module.app.test_client().get("/api/player_prices?cids=301")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()["artwork"]["301"]
        self.assertEqual(payload["pimage"], "/static/faceon/301.png?v=v2")
        self.assertEqual(
            payload["pimageThumb"],
            "/media/player/v2/faceon/301-256.webp",
        )
        self.assertEqual(payload["bimage"], "/static/card/301.png")

    def test_missing_faceon_uses_local_fallback(self):
        player = {
            "cid": 302,
            "pimage": "https://official.example/unavailable-faceon.png",
        }

        with patch.object(
            app_module,
            "_find_local_asset_url",
            return_value=None,
        ):
            normalized = app_module._apply_local_assets(player.copy())

        self.assertEqual(normalized["pimage"], "/static/apple-touch-icon.png")
        self.assertEqual(
            normalized["pimageThumb"],
            "/static/apple-touch-icon.png",
        )

    def test_missing_card_background_uses_local_fallback(self):
        player = {
            "cid": 303,
            "bimage": "https://official.example/unavailable-background.png",
        }

        with patch.object(
            app_module,
            "_find_local_asset_url",
            return_value=None,
        ):
            normalized = app_module._apply_local_assets(player.copy())

        self.assertEqual(
            normalized["bimage"],
            "/static/images/card-background-placeholder.svg",
        )
        self.assertEqual(
            normalized["bimageThumb"],
            "/static/images/card-background-placeholder.svg",
        )

    def test_squad_api_supports_detail_and_price_filters(self):
        app_module.PLAYER_DATA = [
            self._player(
                201,
                1,
                "현재 팀",
                2026,
                ovr=138,
                className="CLASS A",
                height=176,
                footL=3,
                footR=5,
                mainFoot=2,
                n8Price0=2_000,
                traits=["플레이메이커"],
            ),
            self._player(
                202,
                2,
                "현재 팀",
                2026,
                ovr=144,
                className="CLASS B",
                height=188,
                footL=4,
                footR=5,
                mainFoot=2,
                n8Price0=7_000,
                traits=["강철몸"],
            ),
        ]
        app_module._TEAM_FILTER_CONTEXT_CACHE.clear()
        client = app_module.app.test_client()

        response = client.get(
            "/api/squad_players?slot=ST&min_ovr=142&max_ovr=146"
            "&min_price=6000&max_price=8000&min_height=185"
            "&weak_foot_min=4&player_class=CLASS+B&trait=강철몸"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([player["cid"] for player in response.get_json()], [202])

    def test_squad_search_supports_english_name_cid_and_sorting(self):
        app_module.PLAYER_DATA = [
            self._player(
                211,
                11,
                "팀",
                2026,
                ovr=141,
                playerKor="알파",
                playerEng="Alpha Player",
                n8Price0=9_000,
            ),
            self._player(
                212,
                12,
                "팀",
                2026,
                ovr=145,
                playerKor="베타",
                playerEng="Beta Player",
                n8Price0=2_000,
            ),
        ]
        client = app_module.app.test_client()

        english_response = client.get("/api/squad_players?q=alpha")
        cid_response = client.get("/api/squad_players?q=212")
        price_response = client.get("/api/squad_players?sort=price_asc")

        self.assertEqual([player["cid"] for player in english_response.get_json()], [211])
        self.assertEqual([player["cid"] for player in cid_response.get_json()], [212])
        self.assertEqual([player["cid"] for player in price_response.get_json()], [212, 211])

    def test_squad_search_normalizes_reversed_ranges(self):
        app_module.PLAYER_DATA = [
            self._player(221, 21, "팀", 2026, ovr=140, height=180, n8Price0=5_000),
            self._player(222, 22, "팀", 2026, ovr=150, height=190, n8Price0=15_000),
        ]
        client = app_module.app.test_client()

        response = client.get(
            "/api/squad_players?min_ovr=145&max_ovr=135"
            "&min_height=185&max_height=175&min_price=9000&max_price=1000"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([player["cid"] for player in response.get_json()], [221])

    def test_player_prices_api_returns_live_price_metadata(self):
        app_module.PLAYER_DATA = [self._player(231, 31, "팀", 2026, n8Price0=1_000)]

        def apply_test_live_price(players):
            for player in players:
                player["price"] = 9_900
                player["price_source"] = "live"
                player["price_checked_at"] = 123456
            return players

        with patch.object(app_module, "populate_live_prices", side_effect=apply_test_live_price):
            response = app_module.app.test_client().get("/api/player_prices?cids=231")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["prices"]["231"],
            {"price": 9_900, "source": "live", "checked_at": 123456},
        )

    def test_squad_page_uses_latest_price_copy(self):
        response = app_module.app.test_client().get("/squad_maker")
        html = response.data.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("4/18일 기준", html)
        self.assertIn("최신 0진 시세 자동 반영", html)
        self.assertIn("refreshSquadMarketPrices", html)

    def test_detail_search_supports_class_height_and_price_ranges(self):
        app_module.PLAYER_DATA = [
            self._player(301, 1, "팀", 2026, className="CLASS A", height=175, n8Price0=1_000),
            self._player(302, 2, "팀", 2026, className="CLASS B", height=190, n8Price0=9_000),
        ]
        app_module._TEAM_FILTER_CONTEXT_CACHE.clear()
        client = app_module.app.test_client()

        response = client.get(
            "/filtered_players?min_ovr=0&max_ovr=200&player_class=CLASS+B"
            "&min_height=185&max_height=195&min_price=8000&max_price=10000"
        )
        html = response.data.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("/player/302", html)
        self.assertNotIn("/player/301", html)


if __name__ == "__main__":
    unittest.main()
