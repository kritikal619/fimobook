import unittest
from unittest.mock import patch

import app as app_module


class ClanworldcupRecalcAuthorizationTest(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.url = "/clanworldcup/api/standings/recalc"

    def test_missing_code_does_not_recalculate(self):
        with patch.object(app_module, "fs", object()), patch.object(
            app_module, "_recalc_standings"
        ) as recalculate:
            response = self.client.post(self.url, json={})

        self.assertEqual(response.status_code, 400)
        recalculate.assert_not_called()

    def test_non_admin_member_cannot_recalculate(self):
        with patch.object(app_module, "fs", object()), patch.object(
            app_module, "_verify_member_code", return_value={"admin": False}
        ) as verify_member, patch.object(
            app_module, "_recalc_standings"
        ) as recalculate:
            response = self.client.post(self.url, json={"code": "member-code"})

        self.assertEqual(response.status_code, 403)
        verify_member.assert_called_once_with("member-code")
        recalculate.assert_not_called()

    def test_admin_member_can_recalculate_and_sync_bracket(self):
        base = object()
        with patch.object(app_module, "fs", object()), patch.object(
            app_module, "_verify_member_code", return_value={"admin": True}
        ) as verify_member, patch.object(
            app_module, "_recalc_standings", return_value={"groups": ["A"]}
        ) as recalculate, patch.object(
            app_module, "_fs_base", return_value=base
        ), patch.object(app_module, "_sync_knockout_bracket") as sync_bracket:
            response = self.client.post(self.url, json={"code": "admin-code"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True, "groups": ["A"]})
        verify_member.assert_called_once_with("admin-code")
        recalculate.assert_called_once_with()
        sync_bracket.assert_called_once_with(base)

    def test_unavailable_firestore_still_returns_service_error(self):
        with patch.object(app_module, "fs", None), patch.object(
            app_module, "_recalc_standings"
        ) as recalculate:
            response = self.client.post(self.url, json={"code": "admin-code"})

        self.assertEqual(response.status_code, 503)
        recalculate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
