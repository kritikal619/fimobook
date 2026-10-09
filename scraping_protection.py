"""Raise the cost of direct data harvesting without gating indexable HTML.

This is a browser-session gate, not proof that a visitor is human. Nginx also
limits requests by visitor IP; a scraper with a browser can still read public
pages. Do not use user-agent claims to grant privileged crawler access.
"""

from flask import abort, jsonify, request
from flask_wtf.csrf import validate_csrf
from wtforms.validators import ValidationError
import re


# Observed reading /times repeatedly around 20:34 KST on 2026-10-04.
# Match the exact legacy library identity, not mobile/Android visitors in general.
LEGACY_DATA_CLIENT = (
    "Mozilla/5.0 (Linux; U; Android 2.0; en-us; Droid Build/ESD20) "
    "AppleWebKit/530.17 (KHTML, like Gecko) Version/4.0 Mobile Safari/530.17"
)
PLAYER_HTML_PATH = re.compile(r"^/(?:v2/)?player/[0-9]+(?:/stats-card\.png)?$")


DATA_PATHS = frozenset({
    "/autocomplete",
    "/api/squad_players",
    "/api/player_compare",
    "/api/player_details_by_name",
    "/api/player_prices",
})
RAW_DATA_PATHS = frozenset({
    "/static/times/cardData.json",
    "/fctimes/cardData.json",
    "/player_data.json",
    "/player_data_old.json",
})


def _is_data_request():
    return request.path in DATA_PATHS or request.path.startswith("/api/player_price/")


def install_scraping_protection(app):
    @app.before_request
    def protect_data_reads():
        if (
            request.headers.get("User-Agent", "") == LEGACY_DATA_CLIENT
            and (request.path == "/times" or _is_data_request()
                 or request.path in {"/search", "/filtered_players"}
                 or PLAYER_HTML_PATH.fullmatch(request.path))
        ):
            abort(403)
        # Static files served by Nginx need the matching deny locations there.
        # Internal Python jobs read these files from disk and remain unaffected.
        if request.path in RAW_DATA_PATHS:
            abort(404)
        if not _is_data_request():
            return None
        if request.headers.get("Sec-Fetch-Site") in {"cross-site", "none"}:
            return _denied()
        try:
            # Reuse Flask-WTF's signed, session-bound page token. Read tokens
            # use the session lifetime so long-lived squad pages still work;
            # write requests retain Flask-WTF's ordinary expiration and checks.
            validate_csrf(
                request.headers.get("X-Fimobook-Page-Token"),
                time_limit=app.permanent_session_lifetime.total_seconds(),
            )
        except ValidationError:
            return _denied()
        return None

    @app.after_request
    def private_data_responses(response):
        if _is_data_request():
            # Never let a CDN serve a previously authorized JSON response to a
            # visitor who has not passed the session gate.
            response.headers["Cache-Control"] = "private, no-store"
            response.vary.add("Cookie")
            response.vary.add("X-Fimobook-Page-Token")
        elif response.mimetype == "text/html":
            # Base templates contain session-bound tokens, including on error
            # pages. Cache prevention does not change indexing directives.
            response.headers["Cache-Control"] = "private, no-store"
        return response


def _denied():
    response = jsonify(error="사이트에서 선수 검색 화면을 열고 다시 조회해주세요.")
    response.status_code = 403
    return response
