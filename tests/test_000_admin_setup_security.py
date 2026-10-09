import os
import tempfile
import unittest
from pathlib import Path

_TEST_DATABASE_DIRECTORY = tempfile.TemporaryDirectory(
    prefix="fimobook-admin-setup-tests-"
)
_TEST_DATABASE_PATH = Path(_TEST_DATABASE_DIRECTORY.name) / "admin-setup.db"
_original_database_path = os.environ.get("FIMOBOOK_DATABASE_PATH")
_original_secret_key = os.environ.get("FIMOBOOK_SECRET_KEY")
try:
    os.environ["FIMOBOOK_DATABASE_PATH"] = str(_TEST_DATABASE_PATH)
    os.environ["FIMOBOOK_SECRET_KEY"] = "isolated-admin-setup-test-key"
    import app as app_module
finally:
    if _original_database_path is None:
        os.environ.pop("FIMOBOOK_DATABASE_PATH", None)
    else:
        os.environ["FIMOBOOK_DATABASE_PATH"] = _original_database_path
    if _original_secret_key is None:
        os.environ.pop("FIMOBOOK_SECRET_KEY", None)
    else:
        os.environ["FIMOBOOK_SECRET_KEY"] = _original_secret_key


class AdminSetupSecurityTest(unittest.TestCase):
    def setUp(self):
        self.app = app_module.app
        expected_database_uri = "sqlite:///" + str(_TEST_DATABASE_PATH)
        if self.app.config["SQLALCHEMY_DATABASE_URI"] != expected_database_uri:
            self.skipTest("app was imported before the isolated test database was configured")
        self.client = self.app.test_client()
        self.original_config = {
            key: self.app.config.get(key)
            for key in (
                "TESTING",
                "WTF_CSRF_ENABLED",
                "FIMOBOOK_ADMIN_SETUP_PASSWORD",
                "FIMOBOOK_ADMIN_SETUP_EMAIL",
                "FIMOBOOK_ADMIN_USER_IDS",
                "FIMOBOOK_ADMIN_EMAILS",
                "FIMOBOOK_ADMIN_USERNAMES",
                "PLAYER_SUMMARY_ADMIN_PASSWORD",
            )
        }
        self.app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            FIMOBOOK_ADMIN_SETUP_PASSWORD="dedicated-setup-secret",
            FIMOBOOK_ADMIN_SETUP_EMAIL="bootstrap@example.com",
            FIMOBOOK_ADMIN_USER_IDS="",
            FIMOBOOK_ADMIN_EMAILS="",
            FIMOBOOK_ADMIN_USERNAMES="configured-editor",
            PLAYER_SUMMARY_ADMIN_PASSWORD="summary-editor-secret",
        )
        with self.app.app_context():
            app_module.db.drop_all()
            app_module.db.create_all()

    def tearDown(self):
        with self.app.app_context():
            app_module.db.session.remove()
            app_module.db.drop_all()
        for key, value in self.original_config.items():
            if value is None:
                self.app.config.pop(key, None)
            else:
                self.app.config[key] = value

    def _create_user(
        self,
        email,
        username,
        *,
        email_verified=False,
        is_admin=False,
    ):
        with self.app.app_context():
            user = app_module.User(
                email=email,
                username=username,
                email_verified=email_verified,
                is_admin=is_admin,
            )
            app_module.db.session.add(user)
            app_module.db.session.commit()
            return user.id

    def _login(self, user_id):
        with self.client.session_transaction(base_url="https://localhost") as session:
            session["_user_id"] = str(user_id)
            session["_fresh"] = True

    def _is_admin(self, user_id):
        with self.app.app_context():
            return bool(app_module.db.session.get(app_module.User, user_id).is_admin)

    def _post_setup(self, user_id, password):
        self._login(user_id)
        return self.client.post(
            "/secret/admin/setup",
            data={"password": password},
            base_url="https://localhost",
        )

    def test_summary_editor_password_is_not_admin_setup_credential(self):
        self.app.config["FIMOBOOK_ADMIN_SETUP_PASSWORD"] = ""
        user_id = self._create_user(
            "bootstrap@example.com",
            "bootstrap-user",
            email_verified=True,
        )

        response = self._post_setup(user_id, "summary-editor-secret")

        self.assertEqual(response.status_code, 302)
        self.assertFalse(self._is_admin(user_id))
        self.assertEqual(app_module._admin_setup_password(), "")

    def test_verified_preconfigured_identity_can_bootstrap_once(self):
        user_id = self._create_user(
            "bootstrap@example.com",
            "bootstrap-user",
            email_verified=True,
        )

        response = self._post_setup(user_id, "dedicated-setup-secret")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/admin/points")
        self.assertTrue(self._is_admin(user_id))
        admin_page = self.client.get("/admin/points", base_url="https://localhost")
        self.assertEqual(admin_page.status_code, 200)

    def test_unverified_or_different_identity_cannot_bootstrap(self):
        unverified_id = self._create_user(
            "bootstrap@example.com",
            "unverified-user",
            email_verified=False,
        )
        different_id = self._create_user(
            "other@example.com",
            "other-user",
            email_verified=True,
        )

        self._post_setup(unverified_id, "dedicated-setup-secret")
        self._post_setup(different_id, "dedicated-setup-secret")

        self.assertFalse(self._is_admin(unverified_id))
        self.assertFalse(self._is_admin(different_id))

    def test_existing_administrator_blocks_another_bootstrap(self):
        first_id = self._create_user(
            "existing-admin@example.com",
            "existing-admin",
            is_admin=True,
        )
        second_id = self._create_user(
            "bootstrap@example.com",
            "bootstrap-user",
            email_verified=True,
        )

        self._post_setup(second_id, "dedicated-setup-secret")

        self.assertTrue(self._is_admin(first_id))
        self.assertFalse(self._is_admin(second_id))

    def test_existing_configured_admin_identity_blocks_bootstrap(self):
        configured_admin_id = self._create_user(
            "trusted@example.com",
            "trusted-admin",
            email_verified=True,
        )
        bootstrap_id = self._create_user(
            "bootstrap@example.com",
            "bootstrap-user",
            email_verified=True,
        )
        self.app.config["FIMOBOOK_ADMIN_EMAILS"] = "trusted@example.com"

        self._post_setup(bootstrap_id, "dedicated-setup-secret")

        self.assertFalse(self._is_admin(configured_admin_id))
        self.assertFalse(self._is_admin(bootstrap_id))
        with self.app.app_context():
            self.assertTrue(app_module._admin_already_exists())

    def test_configured_admins_require_a_verified_email_or_configured_id(self):
        self.app.config["FIMOBOOK_ADMIN_EMAILS"] = "trusted@example.com"
        self.app.config["FIMOBOOK_ADMIN_USER_IDS"] = "42"

        verified_email = app_module.User(
            id=10,
            email="TRUSTED@example.com",
            username="ordinary",
            email_verified=True,
        )
        unverified_email = app_module.User(
            id=11,
            email="trusted@example.com",
            username="ordinary",
            email_verified=False,
        )
        username_only = app_module.User(
            id=12,
            email="ordinary@example.com",
            username="configured-editor",
            email_verified=True,
        )
        configured_id = app_module.User(
            id=42,
            email="ordinary@example.com",
            username="ordinary",
            email_verified=False,
        )

        self.assertTrue(app_module._user_matches_configured_admin(verified_email))
        self.assertFalse(app_module._user_matches_configured_admin(unverified_email))
        self.assertFalse(app_module._user_matches_configured_admin(username_only))
        self.assertTrue(app_module._user_matches_configured_admin(configured_id))


if __name__ == "__main__":
    unittest.main()
