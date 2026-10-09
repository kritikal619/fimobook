import unittest
from urllib.parse import urlencode
from tests.test_detail_search_state import _ResultsFormParser
import app as m


class DetailSearchMaxStatsTests(unittest.TestCase):
    def setUp(self):
        self.original = m.PLAYER_DATA
        style = [{"code": "PLAYSTYLE_TRICKSTER_1", "name": "트릭스터"}]
        base = dict(position="ST", height=180, className="TEST", ovr=140, ACC=254, SPD=251,
                    playStyleSlotMaxLevels=[1, 1], playstyles=style)
        m.PLAYER_DATA = [
            dict(base, cid=97001, pid=97001, playerKor="경계 일치"),
            dict(base, cid=97002, pid=97002, playerKor="낮은 스탯", SPD=250),
            dict(base, cid=97003, pid=97003, playerKor="다른 OVR", ovr=142),
            dict(base, cid=97004, pid=97004, playerKor="빈 슬롯 없음", playStyleSlotMaxLevels=[1]),
            dict(base, cid=97005, pid=97005, playerKor="슬롯 정보 없음", playStyleSlotMaxLevels=[], playstyles=[]),
            dict(base, cid=97006, pid=97006, playerKor="빈 슬롯만 있음", playstyles=[]),
        ]
        m._ADVANCED_FILTER_OPTIONS_CACHE.clear()
        m._TEAM_FILTER_CONTEXT_CACHE.clear()
        self.client = m.app.test_client()

    def tearDown(self):
        m.PLAYER_DATA = self.original
        m._ADVANCED_FILTER_OPTIONS_CACHE.clear()
        m._TEAM_FILTER_CONTEXT_CACHE.clear()

    def search(self, *extra):
        return self.client.get('/filtered_players?' + urlencode([
            ('min_ovr', '118'), ('max_ovr', '160'), *extra])).get_data(as_text=True)

    def test_search_form_has_field_and_goalkeeper_stat_choices(self):
        html = self.client.get('/traits_selection').get_data(as_text=True)
        self.assertIn('name="max_stat" value="ACC"', html)
        self.assertIn('name="max_stat" value="GKD"', html)
        self.assertIn('name="empty_playstyle_slot"', html)
        self.assertNotIn('name="max_stat" value="height"', html)

    def test_cap_is_per_card_ovr_and_all_stats_must_match(self):
        html = self.search(('max_stat', 'ACC'), ('max_stat', 'SPD'), ('max_stat_gap', '3'))
        self.assertIn('/player/97001', html)
        self.assertNotIn('/player/97002', html)
        self.assertNotIn('/player/97003', html)
        self.assertIn('질주 속도 <b>251</b>', html)
        exact = self.search(('max_stat', 'ACC'), ('max_stat_gap', '0'))
        self.assertIn('/player/97001', exact)
        self.assertNotIn('/player/97003', exact)
        gap5 = self.search(('max_stat', 'SPD'), ('max_stat_gap', '5'))
        self.assertIn('/player/97002', gap5)

    def test_empty_slot_is_required_even_with_selected_playstyle(self):
        empty = self.search(('empty_playstyle_slot', '1'))
        self.assertIn('/player/97001', empty)
        self.assertIn('/player/97006', empty)
        self.assertNotIn('/player/97004', empty)
        self.assertNotIn('/player/97005', empty)
        both = self.search(('empty_playstyle_slot', '1'), ('playstyle', '트릭스터'))
        self.assertIn('/player/97001', both)
        self.assertNotIn('/player/97004', both)
        self.assertNotIn('/player/97006', both)

    def test_sort_and_back_preserve_new_filters_and_ad_is_rendered(self):
        html = self.search(('max_stat', 'ACC'), ('max_stat', 'SPD'), ('max_stat_gap', '3'), ('empty_playstyle_slot', '1'))
        parser = _ResultsFormParser()
        parser.feed(html)
        self.assertIn(('max_stat_gap', '3'), parser.hidden_fields)
        self.assertIn(('max_stat', 'ACC'), parser.hidden_fields)
        self.assertIn(('max_stat', 'SPD'), parser.hidden_fields)
        self.assertIn(('empty_playstyle_slot', '1'), parser.hidden_fields)
        sorted_html = self.client.get('/filtered_players?' + urlencode(parser.hidden_fields + [('sort', 'price_asc')])).get_data(as_text=True)
        self.assertIn('/player/97001', sorted_html)
        self.assertNotIn('/player/97002', sorted_html)
        self.assertIn('adsbygoogle.js', html)
        self.assertIn('data-ad-slot="8520020783"', html)

    def test_invalid_filters_are_not_silently_ignored(self):
        for query in [(('max_stat', 'HEIGHT'),), (('max_stat', 'ACC'), ('max_stat_gap', '-3')), (('max_stat', 'ACC'), ('max_stat_gap', '31'))]:
            self.assertIn('허용 차이(0~30)', self.search(*query))

    def test_missing_unknown_or_nonfinite_stats_never_match(self):
        for override in [{'ACC': None}, {'ACC': '254'}, {'ACC': float('nan')}, {'ACC': float('inf')}, {'ACC': True}, {'ovr': 117}]:
            self.assertFalse(m._player_matches_max_level_stats(dict(ovr=140, ACC=254, **{}) | override, ['ACC'], 5))


if __name__ == '__main__':
    unittest.main()
