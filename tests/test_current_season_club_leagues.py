import unittest

import app as app_module


class CurrentSeasonClubLeagueTest(unittest.TestCase):
    def test_promoted_club_is_grouped_under_current_top_flight(self):
        league_teams = app_module._build_league_team_map(
            [
                {
                    "league": "잉글랜드 EFL 챔피언십",
                    "team": "코벤트리 시티",
                }
            ]
        )

        self.assertIn("코벤트리 시티", league_teams["잉글랜드 프리미어리그"])
        self.assertNotIn("잉글랜드 EFL 챔피언십", league_teams)

    def test_relegated_club_matches_only_its_current_league(self):
        old_card_pair = {
            "league": "독일 분데스리가",
            "team": "VfL 볼프스부르크",
        }

        self.assertTrue(
            app_module._team_pair_matches(
                old_card_pair,
                selected_league="독일 분데스리가 2",
                selected_team="VfL 볼프스부르크",
            )
        )
        self.assertFalse(
            app_module._team_pair_matches(
                old_card_pair,
                selected_league="독일 분데스리가",
                selected_team="VfL 볼프스부르크",
            )
        )

    def test_unchanged_club_keeps_card_league(self):
        pair = {
            "league": "잉글랜드 프리미어리그",
            "team": "아스널",
        }

        self.assertEqual(app_module._current_season_team_pair(pair), pair)

    def test_top_flight_map_includes_promoted_clubs_without_current_cards(self):
        league_teams = app_module._build_league_team_map(
            [], include_current_top_flight=True
        )

        self.assertIn("헐 시티", league_teams["잉글랜드 프리미어리그"])
        self.assertIn("말라가 CF", league_teams["스페인 라리가 EA스포츠"])
        self.assertIn("SC 파더보른 07", league_teams["독일 분데스리가"])
        self.assertIn("프로시노네", league_teams["이탈리아 세리에 A"])
        self.assertIn("르망 FC", league_teams["프랑스 리그 1 맥도날드"])

    def test_other_league_promotions_are_seeded_in_career_search(self):
        league_teams = app_module._build_league_team_map(
            [], include_current_top_flight=True
        )
        expected = {
            "그리스 리그": "이라클리스",
            "네덜란드 에레디비지": "ADO 덴하흐",
            "노르웨이 엘리테세리엔": "릴레스트룀 SK",
            "대한민국 K리그 1": "부천 FC 1995",
            "덴마크 3F 수페르리가": "륑뷔 BK",
            "루마니아 수페르리가": "셉시 OSK",
            "리가 포르투갈": "CS 마리티무",
            "벨기에 프로 리그": "SK 베베런",
            "사우디 프로페셔널 리그": "알 디리야",
            "스웨덴 알스벤스칸": "칼마르 FF",
            "스위스 슈퍼리그": "FC 파두츠",
            "스코티시 프리미어십": "세인트 존스톤",
            "아일랜드 프리미어 디비전": "던도크 FC",
            "오스트리아 분데스리가": "SC 아우스트리아 루스테나우",
            "우크라이나 리그": "FC 부코비나 체르니우치",
            "중국 슈퍼 리그": "충칭 퉁량룽",
            "체코 체스카 리그": "FC 즈브로요프카 브르노",
            "크로아티아 리그": "NK 루데스",
            "튀르키예 트렌디욜 쉬페르리그": "에르주룸스포르 FK",
            "폴란드 엑스트라클라사": "비스와 크라쿠프",
            "핀란드 리그": "FC 라흐티",
            "아르헨티나 리가 프로페시오날 데 풋볼": "힘나시아 이 에스그리마 데 멘도사",
            "인도 슈퍼리그": "처칠 브라더스 FC",
            "헝가리 리그": "버셔시 SC",
            "아랍에미리트 리그": "두바이 유나이티드",
        }

        for league, team in expected.items():
            with self.subTest(league=league, team=team):
                self.assertIn(team, league_teams[league])

    def test_other_league_relegations_override_old_card_leagues(self):
        cases = (
            ("네덜란드 에레디비지", "헤라클레스 알멜로", "네덜란드 에이르스터 디비시"),
            ("노르웨이 엘리테세리엔", "스트룀스고드세", "노르웨이 OBOS-리가엔"),
            ("대한민국 K리그 1", "대구 FC", "대한민국 K리그 2"),
            ("리가 포르투갈", "AVS 풋볼 SAD", "리가 포르투갈 2"),
            ("사우디 프로페셔널 리그", "다마크", "사우디 퍼스트 디비전 리그"),
            ("튀르키예 트렌디욜 쉬페르리그", "안탈리아스포르", "튀르키예 TFF 1. 리그"),
            ("중국 슈퍼 리그", "광저우 풋볼 클럽", "중국 하위 리그"),
            ("오스트레일리아 A리그", "웨스턴 유나이티드 FC", "오스트레일리아 하위 리그"),
        )

        for old_league, team, current_league in cases:
            with self.subTest(team=team):
                old_pair = {"league": old_league, "team": team}
                self.assertTrue(
                    app_module._team_pair_matches(
                        old_pair,
                        selected_league=current_league,
                        selected_team=team,
                    )
                )
                self.assertFalse(
                    app_module._team_pair_matches(
                        old_pair,
                        selected_league=old_league,
                        selected_team=team,
                    )
                )


if __name__ == "__main__":
    unittest.main()
