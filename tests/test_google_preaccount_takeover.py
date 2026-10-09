import os
import tempfile
import time
import unittest
from unittest.mock import patch

_database = tempfile.TemporaryDirectory(prefix="fimobook-google-test-")
os.environ["FIMOBOOK_DATABASE_PATH"] = os.path.join(_database.name, "test.db")
os.environ["FIMOBOOK_SECRET_KEY"] = "isolated-google-test-key"
import app as m


class GoogleAccountLinkTest(unittest.TestCase):
    def setUp(self):
        self.assertEqual(m.app.config["SQLALCHEMY_DATABASE_URI"],
                         "sqlite:///" + os.path.join(_database.name, "test.db"))
        m.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                            GOOGLE_CLIENT_ID="test", RECAPTCHA_SITE_KEY="",
                            RECAPTCHA_SECRET_KEY="")
        with m.app.app_context():
            m.db.drop_all()
            m.db.create_all()

    def exercise(self, verified=False, completion=False, existing=False):
        with m.app.app_context():
            user = m.User(email="victim@example.com", username="original",
                          email_verified=verified, username_confirmed=not existing,
                          google_sub="victim-sub" if existing else None)
            user.set_password("attacker-password")
            m.db.session.add(user)
            m.db.session.commit()
            user_id, old_hash = user.id, user.password_hash
        client = m.app.test_client()
        if completion:
            with client.session_transaction(base_url="https://localhost") as session:
                session["pending_google_signup"] = {
                    "google_sub": "victim-sub", "email": "victim@example.com",
                    "issued_at": int(time.time()), "next_url": "",
                    "existing_user_id": user_id if existing else None,
                }
            response = client.post("/auth/google/complete", data={"username": "new-name"},
                                   base_url="https://localhost")
        else:
            with patch.object(m.google_id_token, "verify_oauth2_token", return_value={
                "iss": "https://accounts.google.com", "sub": "victim-sub",
                "email": "victim@example.com", "email_verified": True,
            }):
                response = client.post("/auth/google", data={"credential": "test"},
                                       base_url="https://localhost")
        self.assertEqual(response.status_code, 302)
        with client.session_transaction(base_url="https://localhost") as session:
            self.assertEqual(session.get("_user_id"), str(user_id))
        with m.app.app_context():
            user = m.db.session.get(m.User, user_id)
            self.assertTrue(user.email_verified)
            self.assertEqual(user.google_sub, "victim-sub")
            self.assertEqual(user.password_hash, old_hash if verified else None)
        password_client = m.app.test_client()
        response = password_client.post("/login", data={
            "email": "victim@example.com", "password": "attacker-password",
        }, base_url="https://localhost")
        self.assertEqual(response.status_code, 302)
        with password_client.session_transaction(base_url="https://localhost") as session:
            self.assertEqual(session.get("_user_id"), str(user_id) if verified else None)

    def test_direct_unverified_account(self):
        self.exercise()

    def test_verified_password_preserved(self):
        self.exercise(verified=True)

    def test_pending_email_race(self):
        self.exercise(completion=True)

    def test_existing_identity_completion(self):
        self.exercise(completion=True, existing=True)


if __name__ == "__main__":
    unittest.main()
