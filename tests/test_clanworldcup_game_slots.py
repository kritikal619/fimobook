import unittest
from unittest.mock import patch

import app as app_module


class FakeSnapshot:
    def __init__(self, document_id, data, exists):
        self.id = document_id
        self._data = dict(data)
        self.exists = exists

    def to_dict(self):
        return dict(self._data)


class FakeDocument:
    def __init__(self, document_id):
        self.id = document_id
        self.data = {}
        self.exists = False
        self.collections = {}

    def get(self):
        return FakeSnapshot(self.id, self.data, self.exists)

    def collection(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]

    def set(self, data, merge=False):
        if merge:
            self.data.update(data)
        else:
            self.data = dict(data)
        self.exists = True

    def update(self, data):
        self.data.update(data)


class FakeCollection:
    def __init__(self):
        self.documents = {}

    def document(self, document_id):
        document_id = str(document_id)
        if document_id not in self.documents:
            self.documents[document_id] = FakeDocument(document_id)
        return self.documents[document_id]

    def stream(self):
        return [
            FakeSnapshot(doc.id, doc.data, doc.exists)
            for doc in self.documents.values()
            if doc.exists
        ]


class FakeBase:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]


def make_match(base, **overrides):
    data = {
        "phase": "GROUP",
        "group": "A",
        "bestOfMode": "ALL5",
        "gameCount": 5,
        "homeClanId": "clan1",
        "awayClanId": "clan2",
        "homeWins": 0,
        "awayWins": 0,
        "winnerClanId": None,
        "status": "PENDING",
    }
    data.update(overrides)
    match_ref = base.collection("matches").document("G-A-01")
    match_ref.set(data)
    return match_ref, data


def add_game(match_ref, document_id, **data):
    match_ref.collection("games").document(document_id).set(data)


class ClanWorldCupGameSlotTest(unittest.TestCase):
    def setUp(self):
        self.base = FakeBase()
        self.match_ref, self.match_data = make_match(self.base)
        self.client = app_module.app.test_client()

    def _authorized_route_patches(self):
        return (
            patch.object(app_module, "fs", object()),
            patch.object(app_module, "_verify_member_code", return_value={"admin": False, "clanId": "clan1"}),
            patch.object(app_module, "_get_match", return_value=self.match_data),
            patch.object(app_module, "_fs_base", return_value=self.base),
        )

    def test_game_reads_and_totals_ignore_noncanonical_documents(self):
        for slot in range(1, 6):
            add_game(
                self.match_ref,
                str(slot),
                slot=slot,
                status="FINAL" if slot in (1, 5) else "NOT_PLAYED",
                homeScore=1 if slot == 1 else (10**24 if slot == 5 else None),
                awayScore=0 if slot in (1, 5) else None,
            )
        add_game(self.match_ref, "6", slot=6, status="FINAL", homeScore=0, awayScore=9)
        add_game(self.match_ref, "06", slot=6, status="FINAL", homeScore=0, awayScore=9)
        add_game(self.match_ref, "extra", slot=1, status="FINAL", homeScore=0, awayScore=9)
        add_game(self.match_ref, "2", slot=99, status="FINAL", homeScore=0, awayScore=9)

        with patch.object(app_module, "_fs_base", return_value=self.base):
            games = app_module._get_match_games("G-A-01")
            updated = app_module._recalc_match_totals("G-A-01")

        self.assertEqual([game["id"] for game in games], ["1", "3", "4", "5"])
        self.assertEqual(updated["homeWins"], 1)
        self.assertEqual(updated["awayWins"], 0)
        self.assertEqual(updated["status"], "IN_PROGRESS")

    def test_mutation_routes_reject_out_of_range_slots_without_creating_documents(self):
        route_cases = (
            ("result", "POST", {"code": "member", "homeScore": 1, "awayScore": 0}),
            ("upload", "POST", {"code": "member"}),
            ("screenshot", "DELETE", {"code": "member"}),
        )
        with self._authorized_route_patches()[0], self._authorized_route_patches()[1], \
                self._authorized_route_patches()[2], self._authorized_route_patches()[3]:
            for slot in (0, 6, 10**24):
                for route_name, _method, payload in route_cases:
                    path = f"/clanworldcup/api/match/G-A-01/games/{slot}"
                    if route_name == "upload":
                        response = self.client.post(f"{path}/upload", data=payload)
                    elif route_name == "screenshot":
                        response = self.client.delete(f"{path}/screenshot", json=payload)
                    else:
                        response = self.client.post(path, json=payload)
                    self.assertEqual(response.status_code, 400, f"{route_name} slot={slot}")

        self.assertFalse(self.match_ref.collection("games").document("6").exists)

    def test_result_route_requires_existing_canonical_document_and_keeps_valid_control(self):
        add_game(self.match_ref, "1", slot=1, status="NOT_PLAYED", homeScore=None, awayScore=None)
        with self._authorized_route_patches()[0], self._authorized_route_patches()[1], \
                self._authorized_route_patches()[2], self._authorized_route_patches()[3], \
                patch.object(app_module, "_recalc_match_totals", return_value={"phase": "GROUP"}), \
                patch.object(app_module, "_recalc_standings", return_value={"ok": True}), \
                patch.object(app_module, "_sync_knockout_bracket", return_value={"updated": 0}):
            missing = self.client.post(
                "/clanworldcup/api/match/G-A-01/games/3",
                json={"code": "member", "homeScore": 2, "awayScore": 1},
            )
            valid = self.client.post(
                "/clanworldcup/api/match/G-A-01/games/1",
                json={"code": "member", "homeScore": 99, "awayScore": 1},
            )

        self.assertEqual(missing.status_code, 404)
        self.assertFalse(self.match_ref.collection("games").document("3").exists)
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(self.match_ref.collection("games").document("1").data["homeScore"], 99)

    def test_match_reset_discards_stale_results_on_slot_mismatched_documents(self):
        add_game(
            self.match_ref,
            "1",
            slot=99,
            status="FINAL",
            homeScore=3,
            awayScore=0,
        )

        reset_count = app_module._reset_match_games(self.match_ref)
        game = self.match_ref.collection("games").document("1")

        self.assertEqual(reset_count, 1)
        self.assertEqual(game.data["slot"], 1)
        self.assertIsNone(game.data["homeScore"])
        self.assertIsNone(game.data["awayScore"])
        self.assertEqual(game.data["status"], "NOT_PLAYED")

    def test_admin_schedule_seed_initializes_missing_canonical_game_documents(self):
        add_game(
            self.match_ref,
            "1",
            slot=99,
            status="FINAL",
            homeScore=3,
            awayScore=0,
            screenshotUrl="/static/uploads/cwc.png",
        )
        with patch.object(app_module, "_ensure_clan_groups", return_value={}), \
                patch.object(app_module, "_ensure_group_matches", return_value={}), \
                patch.object(app_module, "_ensure_group_standings", return_value={}), \
                patch.object(app_module, "_ensure_bracket_matches", return_value={}):
            app_module._seed_schedule(self.base)

        games = self.match_ref.collection("games")
        for slot in range(1, 6):
            game = games.document(str(slot))
            self.assertTrue(game.exists)
            self.assertEqual(game.data["slot"], slot)
            self.assertEqual(game.data["status"], "NOT_PLAYED")
        self.assertIsNone(games.document("1").data["homeScore"])
        self.assertEqual(games.document("1").data["screenshotUrl"], "/static/uploads/cwc.png")

    def test_scores_accept_bounds_and_reject_negative_or_unreasonable_values(self):
        self.assertEqual(app_module._parse_clanworldcup_game_score(0), 0)
        self.assertEqual(app_module._parse_clanworldcup_game_score(99), 99)
        self.assertEqual(app_module._parse_clanworldcup_game_score(" 4 "), 4)
        for value in (-1, 100, True, 1.5, "not a score"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                app_module._parse_clanworldcup_game_score(value)


if __name__ == "__main__":
    unittest.main()
