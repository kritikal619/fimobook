import unittest
from unittest.mock import patch

import app as app_module


class _SingleUserQuery:
    def __init__(self, user):
        self.user = user

    def filter_by(self, **_kwargs):
        return self

    def first(self):
        return self.user


class _GoogleLinkQuery:
    def __init__(self, user):
        self.user = user
        self.filters = {}

    def filter_by(self, **kwargs):
        self.filters = kwargs
        return self

    def first(self):
        if "google_sub" in self.filters:
            return None
        return self.user


class AuthenticationTest(unittest.TestCase):
    def setUp(self):
        self.old_csrf_enabled = app_module.app.config.get("WTF_CSRF_ENABLED", True)
        self.old_google_client_id = app_module.app.config.get("GOOGLE_CLIENT_ID", "")
        app_module.app.config["WTF_CSRF_ENABLED"] = False

    def tearDown(self):
        app_module.app.config["WTF_CSRF_ENABLED"] = self.old_csrf_enabled
        app_module.app.config["GOOGLE_CLIENT_ID"] = self.old_google_client_id

    def _password_user(self):
        user = app_module.User(
            id=987654,
            email="remember@example.com",
            username="remember-user",
        )
        user.set_password("secret")
        return user

    def test_password_login_sets_30_day_remember_cookie_when_selected(self):
        client = app_module.app.test_client()
        user = self._password_user()

        with app_module.app.app_context(), patch.object(
            app_module.User,
            "query",
            _SingleUserQuery(user),
        ):
            response = client.post(
                "/login",
                data={
                    "email": user.email,
                    "password": "secret",
                    "remember": "on",
                },
                base_url="https://localhost",
            )

        remember_cookie = next(
            cookie
            for cookie in response.headers.getlist("Set-Cookie")
            if cookie.startswith("remember_token=")
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("Expires=", remember_cookie)
        self.assertIn("Secure", remember_cookie)
        self.assertIn("HttpOnly", remember_cookie)
        self.assertIn("SameSite=Lax", remember_cookie)

    def test_password_login_stays_session_only_when_remember_is_not_selected(self):
        client = app_module.app.test_client()
        user = self._password_user()

        with app_module.app.app_context(), patch.object(
            app_module.User,
            "query",
            _SingleUserQuery(user),
        ):
            response = client.post(
                "/login",
                data={"email": user.email, "password": "secret"},
                base_url="https://localhost",
            )

        self.assertFalse(any(
            cookie.startswith("remember_token=")
            for cookie in response.headers.getlist("Set-Cookie")
        ))

    def test_google_login_links_verified_gmail_and_remembers_user(self):
        app_module.app.config["GOOGLE_CLIENT_ID"] = "test.apps.googleusercontent.com"
        user = app_module.User(
            id=987655,
            email="googleuser@gmail.com",
            username="google-user",
        )
        payload = {
            "sub": "google-sub-1",
            "email": user.email,
            "email_verified": True,
            "name": "Google User",
            "picture": "https://example.com/avatar.png",
        }
        client = app_module.app.test_client()

        with app_module.app.app_context(), patch.object(
            app_module.User,
            "query",
            _GoogleLinkQuery(user),
        ), patch.object(
            app_module,
            "_verify_google_credential",
            return_value=payload,
        ):
            response = client.post(
                "/auth/google",
                data={"credential": "token"},
                base_url="https://localhost",
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")
        self.assertEqual(user.google_sub, payload["sub"])
        self.assertEqual(user.avatar_url, payload["picture"])
        self.assertTrue(any(
            cookie.startswith("remember_token=")
            for cookie in response.headers.getlist("Set-Cookie")
        ))

    def test_google_login_returns_to_the_page_that_opened_one_tap(self):
        app_module.app.config["GOOGLE_CLIENT_ID"] = "test.apps.googleusercontent.com"
        user = app_module.User(
            id=987656,
            email="return-user@gmail.com",
            username="return-user",
            google_sub="google-sub-2",
        )
        client = app_module.app.test_client()

        with app_module.app.app_context(), patch.object(
            app_module.User,
            "query",
            _SingleUserQuery(user),
        ), patch.object(
            app_module,
            "_verify_google_credential",
            return_value={
                "sub": user.google_sub,
                "email": user.email,
                "email_verified": True,
            },
        ):
            response = client.post(
                "/auth/google",
                data={"credential": "token", "next": "/times"},
                base_url="https://localhost",
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/times")


if __name__ == "__main__":
    unittest.main()
