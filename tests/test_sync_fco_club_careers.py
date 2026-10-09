import unittest

from scripts.sync_fco_club_careers import build_candidate_index, choose_candidate


class ClubCareerMatchingTest(unittest.TestCase):
    def setUp(self):
        shards = [
            (
                1,
                [
                    {
                        "선수명": "디디에 드로그바",
                        "클럽명": "첼시",
                        "연도 시작일": 2004,
                        "연도 종료일": 2012,
                    }
                ],
            )
        ]
        self.candidates, _ = build_candidate_index(shards)

    def test_unique_abbreviated_icon_name_matches_without_club_overlap(self):
        candidate = choose_candidate(self.candidates, ["D. 드로그바"], ["아이콘"])

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["rows"][0]["선수명"], "디디에 드로그바")

    def test_abbreviated_name_does_not_override_nonmatching_real_club(self):
        candidate = choose_candidate(self.candidates, ["D. 드로그바"], ["맨체스터 유나이티드"])

        self.assertIsNone(candidate)


if __name__ == "__main__":
    unittest.main()
