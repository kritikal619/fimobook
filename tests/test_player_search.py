import copy
import unittest

from werkzeug.datastructures import MultiDict

from player_search import parse_detail_search_query, price_enhance_arg, sort_detail_search_players


class PlayerSearchQueryTests(unittest.TestCase):
    def parse(self, values=(), **overrides):
        options = dict(
            skill_or_boost_options=[
                {"name": "스킬 A", "kind": "skill"},
                {"name": "부스트 B", "kind": "boost"},
                {"name": "공통 이름", "kind": "skill"},
                {"name": "공통 이름", "kind": "boost"},
            ],
            work_rate_options={"3-2": {"label": "높음/보통"}},
            raised_stat_options=[{"code": code} for code in ["ACC", "SPD", "FIN", "SHO", "DRI", "STR"]],
            max_level_stat_codes={"ACC", "SPD", "GKD"},
            stat_labels={"ACC": "가속", "SPD": "질주 속도", "GKD": "GK 다이빙"},
            default_min_ovr=132,
            default_max_ovr=160,
            max_enhance_level=15,
        )
        options.update(overrides)
        return parse_detail_search_query(MultiDict(values), **options)

    def test_defaults_and_repeated_values_keep_display_order(self):
        query = self.parse([
            ("position", " st,cm "), ("position", "ST"),
            ("player_class", " CLASS A "), ("player_class", "CLASS A"),
            ("skill_level", "3,1,3,invalid"), ("work_rate", "unknown,3-2"),
        ])
        self.assertIsNone(query.error)
        self.assertEqual(query.filters["positions"], ["ST", "CM"])
        self.assertEqual(query.filters["player_classes"], ["CLASS A"])
        self.assertEqual(query.filters["skill_levels"], [1, 3])
        self.assertEqual(query.filters["work_rate_labels"], ["높음/보통"])
        self.assertEqual((query.filters["min_ovr"], query.filters["max_ovr"]), (132, 160))
        self.assertEqual(query.sort, "ovr_desc")

    def test_skill_boost_collision_and_unknown_names_keep_original_meaning(self):
        query = self.parse([
            ("skill_or_boost", "공통 이름,알 수 없는 스킬"),
            ("skill_boost", "부스트 B"),
        ])
        self.assertIsNone(query.error)
        self.assertEqual(query.skills, {"공통이름", "알수없는스킬"})
        self.assertEqual(query.boosts, {"부스트b"})
        self.assertEqual(query.filters["skill_or_boosts"], ["공통 이름", "알 수 없는 스킬", "부스트 B"])

    def test_invalid_max_stat_error_precedes_reversed_range(self):
        query = self.parse([("max_stat", "HEIGHT"), ("min_ovr", "160"), ("max_ovr", "132")])
        self.assertIn("허용 차이(0~30)", query.error)
        self.assertEqual(query.filters["max_stats"], [])

    def test_reversed_detail_ranges_are_rejected_without_swapping(self):
        for key,fragment in [("ovr", "최소 OVR"), ("height", "최소 키"), ("price", "최소 가격")]:
            with self.subTest(key=key):
                query = self.parse([("min_" + key, "200"), ("max_" + key, "100")])
                self.assertIn(fragment, query.error)
                self.assertEqual(query.filters["min_" + key], 200)
                self.assertEqual(query.filters["max_" + key], 100)

    def test_growth_limits_and_conflicting_filters_are_rejected(self):
        for values,fragment in [
            ([("skill_or_boost", "a,b,c")], "스킬은 최대 2개"),
            ([("skill_boost", "a,b")], "스킬부스트는 한 번에 하나"),
            ([("raised_stat", "ACC,SPD,FIN,SHO,DRI,STR")], "상승 스탯은 최대 5개"),
            ([("raised_stat", "ACC"), ("skill_or_boost", "스킬 A")], "함께 사용할 수 없습니다"),
        ]:
            with self.subTest(values=values):
                self.assertIn(fragment, self.parse(values).error)

    def test_prices_booleans_and_stat_boundaries(self):
        query = self.parse([
            ("min_price", "1,000"), ("max_price", "2,000"),
            ("include_sub_position", "YES"), ("all_career", "on"),
            ("empty_playstyle_slot", "true"), ("max_stat", "acc,SPD"), ("max_stat_gap", "30"),
        ])
        self.assertIsNone(query.error)
        self.assertEqual((query.filters["min_price"], query.filters["max_price"]), (1000, 2000))
        self.assertEqual(query.filters["max_stat_labels"], ["가속", "질주 속도"])
        for key in ["include_sub_position", "all_career", "empty_playstyle_slot"]:
            self.assertTrue(query.filters[key])
        for gap in ["-1", "31", "100", "invalid"]:
            with self.subTest(gap=gap):
                self.assertIsNotNone(self.parse([("max_stat", "ACC"), ("max_stat_gap", gap)]).error)

    def test_price_enhancement_preserves_existing_fallback(self):
        for raw,expected in [("15", 15), ("0", 0), ("-1", 0), ("16", 0), ("bad", 0), ("", 0)]:
            with self.subTest(raw=raw):
                self.assertEqual(price_enhance_arg({"price_enhance": raw}, max_enhance_level=15), expected)


class PlayerSearchOrderingTests(unittest.TestCase):
    def test_all_sort_modes_keep_zero_prices_unknown_prices_and_ties(self):
        players = [
            {"cid": 1, "playerKor": "B", "ovr": 140, "price": None},
            {"cid": 2, "playerKor": "A", "ovr": 140, "price": 100},
            {"cid": 3, "playerKor": "C", "ovr": 141, "price": 0},
            {"cid": 4, "playerKor": "A", "ovr": 142, "price": 100},
            {"cid": 5, "playerKor": "A", "ovr": 142, "price": 100},
        ]
        expected = {
            "price_asc": [3, 4, 5, 2, 1], "price_desc": [4, 5, 2, 3, 1],
            "ovr_asc": [2, 1, 3, 4, 5], "ovr_desc": [4, 5, 3, 2, 1],
            "name_asc": [4, 5, 2, 1, 3], "unknown": [4, 5, 3, 2, 1],
        }
        for mode,cids in expected.items():
            with self.subTest(mode=mode):
                rows = copy.deepcopy(players)
                sort_detail_search_players(rows, mode)
                self.assertEqual([row["cid"] for row in rows], cids)
                self.assertEqual(sorted(rows, key=lambda p: p["cid"]), players)


if __name__ == "__main__":
    unittest.main()
