#!/usr/bin/env python3
"""Run the search/presentation regression suite with isolated local state.

Usage: venv/bin/python scripts/run_local_tests.py [tests.test_module ...]
External HTTP is disabled; this does not verify live third-party services.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TESTS = [
    "tests.test_squad_maker",
    "tests.test_player_compare_features",
    "tests.test_player_detail_seo",
    "tests.test_home_search_filters",
    "tests.test_detail_search_state",
    "tests.test_detail_search_max_stats",
    "tests.test_skill_move_filter_ui",
    "tests.test_price_history_detail",
    "tests.test_landing_page_seo",
    "tests.test_v2_experience",
    "tests.test_player_search",
    "tests.test_browser_session",
    "tests.test_position_filter",
    "tests.test_playstyle_slots",
    "tests.test_result_playstyle_display",
    "tests.test_current_season_club_leagues",
    "tests.test_player_review_playstyles",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tests", nargs="*", help="Optional unittest module or test names")
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    run_dir = Path(tempfile.mkdtemp(prefix="fimobook-local-tests-"))
    os.environ.update(
        FIMOBOOK_DATABASE_PATH=str(run_dir / "board.db"),
        FIMOBOOK_PRICE_HISTORY_DB=str(run_dir / "price.db"),
        FIMOBOOK_SECRET_KEY="isolated-local-test-session-key",
        FIREBASE_ADMIN_KEY_PATH=str(run_dir / "no-firebase-key.json"),
        FIMOBOOK_ANALYTICS_DISABLED="true",
        MAIL_SUPPRESS_SEND="true",
    )
    os.environ.pop("FIRESTORE_EMULATOR_HOST", None)
    os.environ.pop("FIMOBOOK_SKIP_PLAYER_DATA", None)

    import flask
    import requests

    base_flask = flask.Flask

    class IsolatedFlask(base_flask):
        def __init__(self, *app_args, **kwargs):
            kwargs["instance_path"] = str(run_dir)
            super().__init__(*app_args, **kwargs)

    blocked_requests = []

    def offline(_session, method, url, *request_args, **kwargs):
        blocked_requests.append(method)
        raise requests.ConnectionError("External HTTP disabled by local test runner")

    with patch.object(flask, "Flask", IsolatedFlask), patch.object(
        requests.sessions.Session, "request", offline,
    ):
        import app as app_module

        app_module.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        try:
            suite = unittest.defaultTestLoader.loadTestsFromNames(args.tests or DEFAULT_TESTS)
            result = unittest.TextTestRunner(verbosity=1).run(suite)
        finally:
            app_module._PRICE_LOOKUP_EXECUTOR.shutdown(wait=True)

    summary = {
        "tests_run": result.testsRun,
        "failures": [test.id() for test, _trace in result.failures],
        "errors": [test.id() for test, _trace in result.errors],
        "skipped": [test.id() for test, _reason in result.skipped],
        "blocked_external_requests": len(blocked_requests),
        "instance_path": str(run_dir),
    }
    report = run_dir / "result.json"
    report.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Isolated test summary: {report}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
