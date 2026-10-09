import unittest
from pathlib import Path
from types import SimpleNamespace

from flask import render_template

import app as app_module


class ProfileEditorTemplateTest(unittest.TestCase):
    def test_public_profile_renders_reworked_layout_without_activity_context(self):
        profile_user = SimpleNamespace(
            id=1,
            username="테스트",
            email="test@example.com",
            email_verified=False,
            google_sub=None,
            password_hash="hash",
        )
        with app_module.app.test_request_context("/profile/1"):
            html = render_template(
                "profile.html",
                profile_user=profile_user,
                reviews=[],
                own_profile=False,
                monthly_points=0,
                all_time_points=0,
            )

        self.assertIn("profile-page.css", html)
        self.assertIn('class="profile-panel profile-activity"', html)
        self.assertIn('class="profile-layout"', html)
        self.assertIn("선수를 찾아 리뷰 남기기", html)

    def test_create_post_renders_poll_controls_and_live_counts(self):
        with app_module.app.test_request_context("/board/new?tab=free"):
            form = app_module.PostForm(meta={"csrf": False})
            html = render_template(
                "create_post.html",
                form=form,
                boards=app_module.COMMUNITY_BOARDS,
                active_board="free",
                poll_enabled=False,
                poll_options=[],
            )

        self.assertIn("post-editor.css", html)
        self.assertIn('class="post-editor-shell"', html)
        self.assertIn("data-title-count", html)
        self.assertIn("data-content-count", html)
        self.assertIn("data-poll-box", html)
        self.assertIn("등록하기", html)

        theme_css = Path("static/css/theme.css").read_text(encoding="utf-8")
        self.assertIn(
            'html[data-theme="dark"] .post-editor-page .post-editor-card',
            theme_css,
        )
        self.assertIn(
            'html[data-theme="dark"] .post-editor-page .post-editor-submit',
            theme_css,
        )
        self.assertIn("post-editor-dark-20260907", html)


if __name__ == "__main__":
    unittest.main()
