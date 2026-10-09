import unittest
import uuid
from unittest.mock import patch

from flask_login import UserMixin

import app as app_module


class _TestUser(UserMixin):
    def __init__(self, user_id):
        self.id = user_id


class PlayerReviewLikeTests(unittest.TestCase):
    cid = 29999991
    review_id = "review-like-test"

    def setUp(self):
        self.old_csrf_enabled = app_module.app.config.get("WTF_CSRF_ENABLED", True)
        app_module.app.config["WTF_CSRF_ENABLED"] = False
        self.user = _TestUser(int(uuid.uuid4().int % 1000000000) + 1000000000)
        with app_module.app.app_context():
            app_module.PlayerReviewLike.query.filter_by(player_cid=self.cid).delete()
            app_module.db.session.commit()

    def tearDown(self):
        with app_module.app.app_context():
            app_module.PlayerReviewLike.query.filter_by(player_cid=self.cid).delete()
            app_module.db.session.commit()
        app_module.app.config["WTF_CSRF_ENABLED"] = self.old_csrf_enabled

    def _logged_in_client(self):
        client = app_module.app.test_client()
        with client.session_transaction() as session:
            session["_user_id"] = str(self.user.id)
            session["_fresh"] = True
        return client

    def test_like_toggles_once_per_user_and_returns_current_total(self):
        review = {"id": self.review_id, "player_cid": self.cid}
        client = self._logged_in_client()

        with patch.object(app_module.login_manager, "_user_callback", return_value=self.user), patch.object(
            app_module, "_get_player_review_by_id", return_value=review
        ):
            first = client.post(
                f"/community/reviews/{self.cid}/{self.review_id}/like",
                headers={"Accept": "application/json"},
            )
            second = client.post(
                f"/community/reviews/{self.cid}/{self.review_id}/like",
                headers={"Accept": "application/json"},
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual({"likes": 1, "liked": True}, first.get_json())
        self.assertEqual(second.status_code, 200)
        self.assertEqual({"likes": 0, "liked": False}, second.get_json())

        with app_module.app.app_context():
            self.assertEqual(
                0,
                app_module.PlayerReviewLike.query.filter_by(
                    player_cid=self.cid,
                    review_id=self.review_id,
                    user_id=self.user.id,
                ).count(),
            )

    def test_detail_shows_a_login_link_and_like_total_for_guests(self):
        review = {
            "id": self.review_id,
            "player_cid": self.cid,
            "player_name": "테스트 선수",
            "title": "좋아요 테스트 리뷰",
            "created_at_display": "2026-09-12 12:00",
            "ratings": {},
            "rating_notes": {},
        }
        player = {"cid": self.cid, "position": "ST"}
        client = app_module.app.test_client()

        with patch.object(app_module, "_get_player_review_by_id", return_value=review), patch.object(
            app_module, "_get_local_player_by_cid", return_value=player
        ), patch.object(app_module, "_get_latest_player_reviews", return_value=[]):
            response = client.get(f"/community/reviews/{self.cid}/{self.review_id}")

        self.assertEqual(200, response.status_code)
        self.assertIn('좋아요 0', response.get_data(as_text=True))
        self.assertIn('/login?next=', response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
