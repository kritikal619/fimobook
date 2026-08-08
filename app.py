import math
import re
import secrets
import time
import threading
import json
import uuid
import hashlib
import requests
from io import BytesIO
from urllib.parse import quote, urljoin, urlparse
from flask import Flask, request, render_template, redirect, url_for, jsonify, flash, Response, send_from_directory, send_file, abort, session, has_request_context
from bs4 import BeautifulSoup
import os
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, date, timezone, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_wtf import FlaskForm
from werkzeug.utils import secure_filename
from flask_wtf.file import FileField, FileAllowed
from flask.sessions import SecureCookieSessionInterface
from wtforms import StringField, TextAreaField
from wtforms.validators import DataRequired
import firebase_admin
from firebase_admin import credentials, firestore
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_auth_requests
from google.oauth2 import id_token as google_id_token
from google.cloud.firestore_v1 import FieldFilter
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)


def _load_or_create_secret_key():
    configured = (
        os.getenv("FIMOBOOK_SECRET_KEY", "").strip()
        or os.getenv("SECRET_KEY", "").strip()
    )
    if configured:
        return configured

    os.makedirs(app.instance_path, exist_ok=True)
    secret_path = os.path.join(app.instance_path, ".secret_key")
    try:
        with open(secret_path, "r", encoding="utf-8") as secret_file:
            stored = secret_file.read().strip()
        if stored:
            return stored
    except FileNotFoundError:
        pass

    generated = secrets.token_urlsafe(64)
    try:
        descriptor = os.open(
            secret_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as secret_file:
            secret_file.write(generated)
        return generated
    except FileExistsError:
        for _ in range(20):
            with open(secret_path, "r", encoding="utf-8") as secret_file:
                stored = secret_file.read().strip()
            if stored:
                return stored
            time.sleep(0.05)
        raise RuntimeError("서버 세션 키 파일을 읽을 수 없습니다.")


app.config["SECRET_KEY"] = _load_or_create_secret_key()
db_path = (
    os.getenv("FIMOBOOK_DATABASE_PATH", "").strip()
    or os.path.join(app.instance_path, "board.db")
)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path
app.config["MONEYLEAGUE_REGISTRATION_OPEN"] = (
    os.getenv("MONEYLEAGUE_REGISTRATION_OPEN", "false").strip().lower() in {"1", "true", "yes", "on"}
)
app.config["PLAYER_SUMMARY_ADMIN_PASSWORD"] = os.getenv("PLAYER_SUMMARY_ADMIN_PASSWORD", "").strip()
app.config["FIMOBOOK_ADMIN_SETUP_PASSWORD"] = os.getenv("FIMOBOOK_ADMIN_SETUP_PASSWORD", "").strip()
app.config["FIMOBOOK_ADMIN_USER_IDS"] = os.getenv("FIMOBOOK_ADMIN_USER_IDS", "").strip()
app.config["FIMOBOOK_ADMIN_EMAILS"] = os.getenv(
    "FIMOBOOK_ADMIN_EMAILS",
    "",
).strip()
app.config["FIMOBOOK_ADMIN_USERNAMES"] = os.getenv("FIMOBOOK_ADMIN_USERNAMES", "").strip()
app.config["FIMOBOOK_ADMIN_USER_DELETE_PASSWORD"] = os.getenv("FIMOBOOK_ADMIN_USER_DELETE_PASSWORD", "").strip()
app.config["GA_MEASUREMENT_ID"] = os.getenv("GA_MEASUREMENT_ID", "G-J8ZL7VF352").strip()
app.config["GOOGLE_CLIENT_ID"] = os.getenv("GOOGLE_CLIENT_ID", "").strip()
app.config["RECAPTCHA_SITE_KEY"] = os.getenv("RECAPTCHA_SITE_KEY", "").strip()
app.config["RECAPTCHA_SECRET_KEY"] = os.getenv("RECAPTCHA_SECRET_KEY", "").strip()
app.config["RECAPTCHA_ALLOWED_HOSTNAMES"] = os.getenv(
    "RECAPTCHA_ALLOWED_HOSTNAMES",
    "fcbook.info,www.fcbook.info",
).strip()
app.config["PUBLIC_BASE_URL"] = os.getenv(
    "PUBLIC_BASE_URL",
    "https://fcbook.info",
).strip().rstrip("/")
app.config["EMAIL_VERIFICATION_MAX_AGE"] = int(
    os.getenv("EMAIL_VERIFICATION_MAX_AGE", "86400")
)
app.config["EMAIL_VERIFICATION_RESEND_SECONDS"] = int(
    os.getenv("EMAIL_VERIFICATION_RESEND_SECONDS", "60")
)
app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp.gmail.com").strip()
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", "587"))
app.config["MAIL_USE_TLS"] = os.getenv(
    "MAIL_USE_TLS",
    "true",
).strip().lower() in {"1", "true", "yes", "on"}
app.config["MAIL_USE_SSL"] = os.getenv(
    "MAIL_USE_SSL",
    "false",
).strip().lower() in {"1", "true", "yes", "on"}
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME", "").strip()
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD", "").strip()
app.config["MAIL_DEFAULT_SENDER"] = (
    os.getenv("MAIL_DEFAULT_SENDER", "").strip()
    or app.config["MAIL_USERNAME"]
)
app.config["MAIL_SUPPRESS_SEND"] = os.getenv(
    "MAIL_SUPPRESS_SEND",
    "false",
).strip().lower() in {"1", "true", "yes", "on"}

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
mail = Mail(app)
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

app.config['ALLOWED_IMAGE_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['MAX_SCREENSHOT_BYTES'] = 10 * 1024 * 1024


# ---------------------------
# Player statistics PNG card
# ---------------------------
STATS_CARD_CANVAS_SIZE = (1280, 1280)
STATS_CARD_BG = "#080d19"
STATS_CARD_PANEL = "#111827"
STATS_CARD_PANEL_SOFT = "#151e2e"
STATS_CARD_BORDER = "#263247"
STATS_CARD_TEXT = "#f8fafc"
STATS_CARD_MUTED = "#93a4b8"
STATS_CARD_ACCENT = "#22d3a6"
STATS_CARD_ACCENT_DARK = "#0e7b66"
STATS_CARD_TRAINING = "#fbbf24"
STATS_CARD_MAX = "#fb7185"

STATS_CARD_SUMMARY_WEIGHTS = {
    "페이스": (("ACC", 50), ("SPD", 50)),
    "슈팅": (("FIN", 35), ("LSA", 20), ("SHO", 20), ("POS", 15), ("VOL", 5), ("PEN", 5)),
    "패스": (("SPA", 30), ("LPA", 20), ("VIS", 25), ("CRO", 15), ("CUR", 5), ("FRK", 5)),
    "드리블": (("DRI", 25), ("BAC", 25), ("AGI", 25), ("REA", 15), ("BAL", 10)),
    "수비": (("MRK", 25), ("STT", 20), ("SLT", 20), ("AWR", 20), ("HEA", 15)),
    "피지컬": (("STR", 45), ("AGG", 30), ("JMP", 25)),
}

STATS_CARD_DETAIL_STATS = {
    "페이스": (("ACC", "가속"), ("SPD", "질주 속도")),
    "슈팅": (
        ("FIN", "결정력"), ("LSA", "중거리 슛"), ("SHO", "슈팅력"),
        ("POS", "위치선정"), ("VOL", "발리 슛"), ("PEN", "페널티 킥"),
    ),
    "패스": (
        ("SPA", "짧은 패스"), ("LPA", "긴 패스"), ("VIS", "시야"),
        ("CRO", "크로스"), ("CUR", "감아차기"), ("FRK", "프리킥"),
    ),
    "드리블": (
        ("DRI", "드리블"), ("BAC", "볼 컨트롤"), ("AGI", "민첩성"),
        ("REA", "반응도"), ("BAL", "밸런스"),
    ),
    "수비": (
        ("MRK", "마크"), ("STT", "태클"), ("SLT", "슬라이딩 태클"),
        ("AWR", "가로채기"), ("HEA", "헤딩"),
    ),
    "피지컬": (("STR", "힘"), ("AGG", "공격성"), ("JMP", "점프"), ("STA", "스태미나")),
}

STATS_CARD_GK_SUMMARY_WEIGHTS = {
    "다이빙": (("GKD", 100),),
    "핸들링": (("HAN", 100),),
    "킥": (("GKK", 100),),
    "반사 신경": (("REF", 100),),
    "위치선정": (("GKP", 100),),
    "피지컬": (("REA", 45), ("JMP", 25), ("STR", 20), ("AGI", 10)),
}

STATS_CARD_GK_DETAIL_STATS = {
    "다이빙": (("GKD", "GK 다이빙"), ("AGI", "민첩성"), ("REA", "반응도")),
    "핸들링": (("HAN", "핸들링"), ("BAC", "볼 컨트롤"), ("STR", "힘")),
    "킥": (("GKK", "GK 킥"), ("LPA", "긴 패스"), ("SPA", "짧은 패스")),
    "반사 신경": (("REF", "반사 신경"), ("REA", "반응도"), ("AGI", "민첩성")),
    "위치선정": (("GKP", "GK 위치선정"), ("POS", "위치선정"), ("AWR", "가로채기")),
    "피지컬": (("STR", "힘"), ("JMP", "점프"), ("AGG", "공격성"), ("STA", "스태미나")),
}


def _stats_card_font(font_path, size):
    return ImageFont.truetype(font_path, size=size)


def _stats_card_asset_image(source, root_path):
    if not source:
        return None
    try:
        if source.startswith("/static/"):
            path = os.path.join(root_path, source.lstrip("/"))
            return Image.open(path).convert("RGBA")
        if source.startswith("http://") or source.startswith("https://"):
            response = requests.get(
                source,
                timeout=(3, 8),
                headers={"User-Agent": "FimoBook/1.0"},
            )
            response.raise_for_status()
            return Image.open(BytesIO(response.content)).convert("RGBA")
        if os.path.isfile(source):
            return Image.open(source).convert("RGBA")
    except Exception:
        return None
    return None


def _stats_card_contain(image, box, scale=1.0):
    width, height = box
    ratio = min(width / image.width, height / image.height) * scale
    size = (max(1, int(image.width * ratio)), max(1, int(image.height * ratio)))
    return image.resize(size, Image.Resampling.LANCZOS)


def _stats_card_paste_center(canvas, image, bounds):
    left, top, right, bottom = bounds
    x = left + (right - left - image.width) // 2
    y = top + (bottom - top - image.height) // 2
    canvas.alpha_composite(image, (x, y))


def _stats_card_fit_text(draw, text, font_path, max_size, min_size, max_width):
    for size in range(max_size, min_size - 1, -2):
        candidate = _stats_card_font(font_path, size)
        if draw.textbbox((0, 0), text, font=candidate)[2] <= max_width:
            return candidate
    return _stats_card_font(font_path, min_size)


def _stats_card_pill(
    draw,
    xy,
    text,
    font,
    *,
    fill=STATS_CARD_PANEL_SOFT,
    outline=STATS_CARD_BORDER,
    text_fill=STATS_CARD_TEXT,
):
    x, y = xy
    bounds = draw.textbbox((0, 0), text, font=font)
    width = bounds[2] - bounds[0] + 32
    draw.rounded_rectangle(
        (x, y, x + width, y + 42),
        radius=21,
        fill=fill,
        outline=outline,
        width=2,
    )
    draw.text((x + 16, y + 8), text, font=font, fill=text_fill)
    return width


def _stats_card_numeric(player, key):
    value = player.get(key)
    return float(value) if isinstance(value, (int, float)) else 0.0


def _max_level_stat_value(base_ovr):
    """Return the stat ceiling determined only by the player's 0-rank OVR."""
    try:
        numeric_ovr = int(base_ovr)
    except (TypeError, ValueError):
        return None
    if numeric_ovr < 118:
        return None
    return 210 + (2 * (numeric_ovr - 118))


def _stats_card_summary_value(stat_values, weights):
    total_weight = sum(weight for _, weight in weights)
    if not total_weight:
        return 0
    value = sum(float(stat_values.get(key) or 0) * weight for key, weight in weights)
    return int(value / total_weight)


def _draw_stats_card_panel(
    draw,
    player,
    bounds,
    label,
    rows,
    summary,
    stat_values,
    training_bonuses,
    max_stat_codes,
    fonts,
):
    left, top, right, bottom = bounds
    draw.rounded_rectangle(
        bounds,
        radius=18,
        fill=STATS_CARD_PANEL,
        outline=STATS_CARD_BORDER,
        width=2,
    )
    draw.text((left + 22, top + 18), label, font=fonts["panel_title"], fill=STATS_CARD_TEXT)
    draw.text(
        (right - 22, top + 13),
        str(summary),
        font=fonts["panel_value"],
        fill=STATS_CARD_ACCENT,
        anchor="ra",
    )
    gauge_top = top + 62
    draw.rounded_rectangle(
        (left + 22, gauge_top, right - 22, gauge_top + 8),
        radius=4,
        fill="#203247",
    )
    ratio = min(max(summary / 180, 0.08), 1.0)
    draw.rounded_rectangle(
        (left + 22, gauge_top, left + 22 + int((right - left - 44) * ratio), gauge_top + 8),
        radius=4,
        fill=STATS_CARD_ACCENT,
    )
    available_rows = [row for row in rows if player.get(row[0]) is not None]
    selected_rows = available_rows[:6]
    boosted_rows = [
        row
        for row in available_rows
        if int(training_bonuses.get(row[0]) or 0) > 0 and row not in selected_rows
    ]
    for boosted_row in boosted_rows:
        replace_at = next(
            (
                index
                for index in range(len(selected_rows) - 1, -1, -1)
                if int(training_bonuses.get(selected_rows[index][0]) or 0) == 0
            ),
            None,
        )
        if replace_at is not None:
            selected_rows[replace_at] = boosted_row

    y = top + 83
    for key, row_label in selected_rows:
        value = int(float(stat_values.get(key) or 0))
        row_label_fill = STATS_CARD_MAX if key in max_stat_codes else STATS_CARD_MUTED
        draw.text((left + 22, y), row_label, font=fonts["row"], fill=row_label_fill)
        training_bonus = int(training_bonuses.get(key) or 0)
        if training_bonus > 0:
            draw.text(
                (right - 72, y),
                f"+{training_bonus}",
                font=fonts["row_bold"],
                fill=STATS_CARD_TRAINING,
                anchor="ra",
            )
        draw.text(
            (right - 22, y),
            str(value),
            font=fonts["row_bold"],
            fill=STATS_CARD_ACCENT,
            anchor="ra",
        )
        y += 26


def render_player_stats_card(
    player,
    *,
    root_path,
    enhance_level=0,
    enhance_bonus=0,
    training_level=0,
    training_bonuses=None,
    skill_bonuses=None,
    skill_config_labels=None,
    tier=None,
    variant="current",
):
    """Render a square, share-ready PNG containing the player's key statistics."""
    canvas = Image.new("RGBA", STATS_CARD_CANVAS_SIZE, STATS_CARD_BG)
    draw = ImageDraw.Draw(canvas)
    font_path = os.path.join(root_path, "static", "fonts", "NAME.ttf")
    fonts = {
        "brand": _stats_card_font(font_path, 25),
        "name": _stats_card_fit_text(
            draw,
            str(player.get("playerKor") or "-"),
            font_path,
            56,
            34,
            610,
        ),
        "class": _stats_card_font(font_path, 23),
        "meta_label": _stats_card_font(font_path, 20),
        "meta_value": _stats_card_font(font_path, 25),
        "pill": _stats_card_font(font_path, 19),
        "panel_title": _stats_card_font(font_path, 22),
        "panel_value": _stats_card_font(font_path, 34),
        "row": _stats_card_font(font_path, 18),
        "row_bold": _stats_card_font(font_path, 19),
        "footer": _stats_card_font(font_path, 18),
    }

    draw.ellipse((820, -280, 1440, 340), fill="#112d31")
    draw.ellipse((-420, 850, 340, 1580), fill="#121f38")
    draw.rectangle((0, 0, 24, 1280), fill=STATS_CARD_ACCENT)
    draw.text((34, 31), "피모북", font=fonts["brand"], fill=STATS_CARD_TEXT)

    card_bounds = (70, 112, 430, 590)
    draw.rounded_rectangle(
        card_bounds,
        radius=28,
        fill="#0d1422",
        outline=STATS_CARD_BORDER,
        width=2,
    )
    card_bg = _stats_card_asset_image(str(player.get("bimage") or ""), root_path)
    face = _stats_card_asset_image(str(player.get("pimage") or ""), root_path)
    if card_bg:
        _stats_card_paste_center(
            canvas,
            _stats_card_contain(card_bg, (330, 438)),
            (85, 126, 415, 564),
        )
    if face:
        _stats_card_paste_center(
            canvas,
            _stats_card_contain(face, (330, 438)),
            (85, 126, 415, 564),
        )
    if not card_bg and not face:
        draw.text(
            (250, 338),
            "선수 이미지",
            font=fonts["class"],
            fill=STATS_CARD_MUTED,
            anchor="mm",
        )

    ovr = int(_stats_card_numeric(player, "ovr") + enhance_bonus)
    draw.rounded_rectangle((82, 128, 158, 204), radius=18, fill="#08111ccc")
    draw.text(
        (120, 139),
        str(ovr),
        font=_stats_card_font(font_path, 34),
        fill=STATS_CARD_TEXT,
        anchor="ma",
    )
    draw.text(
        (120, 178),
        str(player.get("position") or "-"),
        font=_stats_card_font(font_path, 18),
        fill=STATS_CARD_ACCENT,
        anchor="ma",
    )

    name = str(player.get("playerKor") or "-")
    draw.text((474, 118), name, font=fonts["name"], fill=STATS_CARD_TEXT)
    class_name = str(player.get("className") or "").strip()
    if class_name:
        draw.text(
            (476, 184),
            class_name,
            font=fonts["class"],
            fill=STATS_CARD_MUTED,
        )

    pill_x = 476
    config_label = (
        "기본"
        if variant == "base" or enhance_level == 0
        else f"{enhance_level}진화"
    )
    pill_x += _stats_card_pill(
        draw,
        (pill_x, 232),
        config_label,
        fonts["pill"],
        fill="#0d2f2b",
        outline=STATS_CARD_ACCENT_DARK,
        text_fill=STATS_CARD_ACCENT,
    ) + 10
    if training_level > 0:
        pill_x += _stats_card_pill(
            draw,
            (pill_x, 232),
            f"훈련 {training_level}단계",
            fonts["pill"],
            fill="#302711",
            outline="#8a6b13",
            text_fill=STATS_CARD_TRAINING,
        ) + 10
    if tier and pill_x < 1060:
        _stats_card_pill(
            draw,
            (pill_x, 232),
            f"투표 {tier}티어",
            fonts["pill"],
            fill="#2b1f2d",
            outline="#6c4d72",
            text_fill="#f6a6ff",
        )

    meta = [
        ("포지션", str(player.get("position") or "-")),
        (
            "주발",
            "오른발"
            if player.get("mainFoot") == 1
            else ("왼발" if player.get("mainFoot") == 2 else "-"),
        ),
        ("신체", f"{player.get('height') or '-'}cm · {player.get('weight') or '-'}kg"),
        (
            "개인기",
            f"{int(player.get('skillMovesLevel') or player.get('skillMoves') or 0) + 1}성",
        ),
    ]
    for index, (label, value) in enumerate(meta):
        column = index % 2
        row = index // 2
        x = 476 + column * 310
        y = 310 + row * 88
        draw.text((x, y), label, font=fonts["meta_label"], fill=STATS_CARD_MUTED)
        draw.text((x, y + 32), value, font=fonts["meta_value"], fill=STATS_CARD_TEXT)

    skill_names = []
    skill_display = (
        player.get("skillDisplay")
        if isinstance(player.get("skillDisplay"), dict)
        else {}
    )
    for item in skill_display.get("items") or []:
        if isinstance(item, dict) and item.get("name") and item["name"] not in skill_names:
            skill_names.append(str(item["name"]))
    if not skill_names:
        skill_names = [str(value) for value in (player.get("skillLabels") or []) if value]
    display_skill_names = [
        str(value) for value in (skill_config_labels or []) if str(value).strip()
    ] or skill_names
    x = 476
    y = 505
    for skill in display_skill_names[:4]:
        estimated_width = draw.textbbox((0, 0), skill, font=fonts["pill"])[2] + 32
        if x > 476 and x + estimated_width > 1210:
            x = 476
            y += 51
        width = _stats_card_pill(draw, (x, y), skill, fonts["pill"])
        x += width + 9

    is_gk = str(player.get("position") or "").upper() == "GK"
    weights = (
        STATS_CARD_GK_SUMMARY_WEIGHTS
        if is_gk
        else STATS_CARD_SUMMARY_WEIGHTS
    )
    details = STATS_CARD_GK_DETAIL_STATS if is_gk else STATS_CARD_DETAIL_STATS
    training_bonuses = training_bonuses or {}
    skill_bonuses = skill_bonuses or {}
    stat_values = {}
    all_stat_codes = {
        code
        for rows in details.values()
        for code, _ in rows
    } | {
        code
        for rows in weights.values()
        for code, _ in rows
    }
    for code in all_stat_codes:
        stat_values[code] = (
            _stats_card_numeric(player, code)
            + enhance_bonus
            + int(skill_bonuses.get(code) or 0)
            + int(training_bonuses.get(code) or 0)
        )
    max_stat_value = _max_level_stat_value(player.get("ovr"))
    max_stat_codes = {
        code
        for code in all_stat_codes
        if max_stat_value is not None
        and player.get(code) is not None
        and _stats_card_numeric(player, code) >= max_stat_value
    }
    panel_width = 362
    panel_height = 237
    start_x = 70
    start_y = 650
    for index, label in enumerate(weights):
        column = index % 3
        row = index // 3
        left = start_x + column * (panel_width + 26)
        top = start_y + row * (panel_height + 24)
        summary = _stats_card_summary_value(stat_values, weights[label])
        _draw_stats_card_panel(
            draw,
            player,
            (left, top, left + panel_width, top + panel_height),
            label,
            details[label],
            summary,
            stat_values,
            training_bonuses,
            max_stat_codes,
            fonts,
        )

    footer_y = 1228
    draw.text((70, footer_y), "fcbook.info", font=fonts["footer"], fill=STATS_CARD_ACCENT)
    if enhance_level == 0 and max_stat_value is not None:
        draw.text(
            (1210, footer_y),
            f"0진 만렙스탯 {max_stat_value}",
            font=fonts["footer"],
            fill=STATS_CARD_MAX,
            anchor="ra",
        )

    output = BytesIO()
    canvas.convert("RGB").save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


class NoVarySessionInterface(SecureCookieSessionInterface):
    def save_session(self, app, session, response):
        if request.path == "/sitemap.xml" or request.path.startswith("/sitemaps/"):
            return
        return super().save_session(app, session, response)

app.session_interface = NoVarySessionInterface()

def _canonical(path: str) -> str:
    base_url = app.config.get("PUBLIC_BASE_URL", "https://fcbook.info").rstrip("/") + "/"
    return urljoin(base_url, path.lstrip("/"))

@app.after_request
def add_x_robots_tag(response):
    path = request.path or ""
    if path.startswith("/api/") or path.startswith("/clanworldcup/api/") or path.startswith("/secret/") or path == "/autocomplete":
        response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
    if path == "/sitemap.xml" or path.startswith("/sitemaps/"):
        response.headers.pop("Set-Cookie", None)
        response.headers["Vary"] = "Accept-Encoding"
        response.headers.setdefault("Cache-Control", "public, max-age=3600")
    return response
# ---------------------------
# Firebase (Web Push / Admin)
# ---------------------------
app.config["FIREBASE_WEB_VAPID_KEY"] = os.getenv("FIREBASE_WEB_VAPID_KEY", "").strip()

# 1) FIREBASE_WEB_CONFIG (JSON string) 우선 지원
# 2) 없으면 기존처럼 쪼개진 FIREBASE_WEB_* 값으로 fallback
def _firebase_web_config():
    cfg_json = os.getenv("FIREBASE_WEB_CONFIG", "").strip()
    if cfg_json:
        try:
            cfg = json.loads(cfg_json)
            return cfg if isinstance(cfg, dict) else {}
        except Exception as e:
            print(f"[FIREBASE_WEB_CONFIG] JSON parse failed: {e} / raw={cfg_json!r}")
            return {}

    # fallback: split env vars
    raw = {
        "apiKey": os.getenv("FIREBASE_WEB_API_KEY"),
        "authDomain": os.getenv("FIREBASE_WEB_AUTH_DOMAIN"),
        "projectId": os.getenv("FIREBASE_WEB_PROJECT_ID"),
        "storageBucket": os.getenv("FIREBASE_WEB_STORAGE_BUCKET"),
        "messagingSenderId": os.getenv("FIREBASE_WEB_MESSAGING_SENDER_ID"),
        "appId": os.getenv("FIREBASE_WEB_APP_ID"),
        "measurementId": os.getenv("FIREBASE_WEB_MEASUREMENT_ID"),
    }
    return {k: v for k, v in raw.items() if v}

app.config["FIREBASE_WEB_CONFIG"] = _firebase_web_config()

# Firebase 초기화 (에뮬레이터 우선)
# .env에 FIREBASE_ADMIN_KEY_PATH가 있으면 그걸 최우선 사용 (네가 이미 넣어둔 값)
FIREBASE_KEY_PATH = os.getenv(
    "FIREBASE_ADMIN_KEY_PATH",
    os.path.join(app.instance_path, 'clanworldcup-f6399-firebase-adminsdk-fbsvc-211898d910.json'),
)


USE_EMULATOR = bool(os.getenv("FIRESTORE_EMULATOR_HOST"))
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")

fs = None
if not firebase_admin._apps:
    try:
        init_options = {}
        if PROJECT_ID:
            init_options["projectId"] = PROJECT_ID

        if os.path.exists(FIREBASE_KEY_PATH):
            cred = credentials.Certificate(FIREBASE_KEY_PATH)
            firebase_admin.initialize_app(cred, options=init_options or None)
        elif USE_EMULATOR:
            firebase_admin.initialize_app(options=init_options or {"projectId": "dev-local"})

        if firebase_admin._apps:
            fs = firestore.client()
    except Exception as e:
        print(f"Firebase init failed: {e}")

@app.route("/manifest.json")
def manifest():
    return send_from_directory(app.root_path, "manifest.json", mimetype="application/manifest+json")

@app.route("/ads.txt")
def ads_txt():
    return send_from_directory(app.root_path, "ads.txt", mimetype="text/plain", max_age=3600)

@app.route("/favicon.ico")
def root_favicon():
    return send_from_directory(os.path.join(app.root_path, "static"), "favicon.ico", mimetype="image/x-icon")

@app.route("/apple-touch-icon.png")
@app.route("/apple-touch-icon-precomposed.png")
@app.route("/apple-touch-icon-120x120.png")
@app.route("/apple-touch-icon-120x120-precomposed.png")
def apple_touch_icon():
    return send_from_directory(os.path.join(app.root_path, "static"), "apple-touch-icon.png", mimetype="image/png")

@app.route("/sitemap.xml", methods=["GET"])
def sitemap():
    sitemaps_dir = os.path.join(app.root_path, "sitemaps")
    sitemap_index = os.path.join(sitemaps_dir, "sitemap.xml")
    if os.path.exists(sitemap_index):
        return send_from_directory(
            sitemaps_dir,
            "sitemap.xml",
            mimetype="application/xml",
            max_age=3600,
        )

    pages = [
        urljoin(request.url_root, "/"),
        urljoin(request.url_root, "/players"),
        urljoin(request.url_root, "/traits_selection"),
        urljoin(request.url_root, "/player-reviews"),
        urljoin(request.url_root, "/coupons/"),
        urljoin(request.url_root, "/times"),
        urljoin(request.url_root, "/prime-exchange"),
    ]

    for player in PLAYER_DATA:
        cid = player.get("cid")
        if cid:
            pages.append(urljoin(request.url_root, f"/player/{cid}"))

    sitemap_xml = render_template("sitemap.xml", pages=pages)
    response = Response(sitemap_xml, mimetype="application/xml")
    response.headers["Cache-Control"] = "public, max-age=3600"
    response.headers["Vary"] = "Accept-Encoding"
    response.headers.pop("Set-Cookie", None)
    return response

@app.route("/sitemaps/<path:filename>", methods=["GET"], strict_slashes=False)
def sitemap_file(filename):
    if filename.endswith("/"):
        filename = filename[:-1]
    sitemaps_dir = os.path.join(app.root_path, "sitemaps")
    return send_from_directory(
        sitemaps_dir,
        filename,
        mimetype="application/xml",
        max_age=3600,
    )

# Firebase 초기화 (에뮬레이터 우선)
FIREBASE_KEY_PATH = os.getenv(
    "FIREBASE_ADMIN_KEY_PATH",
    os.path.join(app.instance_path, 'clanworldcup-f6399-firebase-adminsdk-fbsvc-211898d910.json'),
)
USE_EMULATOR = bool(os.environ.get("FIRESTORE_EMULATOR_HOST"))
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")



def _fs_base():
    """Firestore base doc for clanworldcup3."""
    if not fs:
        return None
    return fs.collection("tournaments").document("clanworldcup3")

def _fs_where(query, field, op, value):
    """Compatibility wrapper for Firestore where() filters."""
    try:
        return query.where(filter=FieldFilter(field, op, value))
    except Exception:
        return query.where(field, op, value)

def _get_match(match_id):
    base = _fs_base()
    if not base:
        return None
    doc = base.collection("matches").document(match_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    data["id"] = match_id
    return data

def _get_match_games(match_id):
    base = _fs_base()
    if not base:
        return []
    games_ref = base.collection("matches").document(match_id).collection("games")
    games = []
    for g in games_ref.stream():
        data = g.to_dict() or {}
        data["id"] = g.id
        games.append(data)
    games.sort(key=lambda x: x.get("slot", 0))
    return games

def _normalize_clan_id(value):
    if value is None:
        return None
    clan_id = str(value).strip()
    return clan_id or None

def _normalize_clan_key(value):
    clan_id = _normalize_clan_id(value)
    return clan_id.lower() if clan_id else None

def _is_placeholder_clan_name(name):
    if not name:
        return True
    value = str(name).strip()
    return bool(re.match(r"^team\\s*\\d+$", value, re.IGNORECASE))

def _normalize_member(member):
    if not member:
        return None
    admin_val = member.get("admin")
    is_admin = False
    if isinstance(admin_val, bool):
        is_admin = admin_val
    elif isinstance(admin_val, (int, float)):
        is_admin = admin_val == 1
    elif isinstance(admin_val, str):
        is_admin = admin_val.strip().lower() in {"1", "true", "yes", "y", "admin"}
    member["admin"] = is_admin

    clan_id = member.get("clanId") or member.get("clan_id") or member.get("clan") or member.get("clanID")
    member["clanId"] = _normalize_clan_id(clan_id)
    return member

def _verify_member_code(code):
    base = _fs_base()
    if not base:
        return None
    doc = base.collection("memberCodes").document(code).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    if not data.get("enabled"):
        return None
    return _normalize_member(data)

def _recalc_match_totals(match_id):
    """Recalculate homeWins/awayWins and winner/status based on games."""
    base = _fs_base()
    if not base:
        return None
    match_ref = base.collection("matches").document(match_id)
    match_snap = match_ref.get()
    if not match_snap.exists:
        return None
    match_data = match_snap.to_dict() or {}
    games = _get_match_games(match_id)
    home_wins = 0
    away_wins = 0
    final_count = 0
    for g in games:
        if g.get("status") == "FINAL":
            final_count += 1
            hs = g.get("homeScore")
            as_ = g.get("awayScore")
            if hs is not None and as_ is not None:
                if hs > as_:
                    home_wins += 1
                elif as_ > hs:
                    away_wins += 1
    best_of = (match_data.get("bestOfMode") or "ALL5").upper()
    phase = (match_data.get("phase") or "").upper()
    if phase == "QF" and best_of != "FIRST3":
        # Ensure quarterfinals always play first-to-3 wins.
        best_of = "FIRST3"
        match_ref.set({"bestOfMode": "FIRST3"}, merge=True)
    winner = None
    status = match_data.get("status") or "PENDING"
    if best_of == "FIRST3":
        if home_wins >= 3 or away_wins >= 3:
            winner = match_data.get("homeClanId") if home_wins > away_wins else match_data.get("awayClanId")
            status = "FINAL"
        elif final_count > 0:
            status = "IN_PROGRESS"
    else:  # ALL5
        if final_count >= 5:
            winner = match_data.get("homeClanId") if home_wins > away_wins else match_data.get("awayClanId")
            status = "FINAL"
        elif final_count > 0:
            status = "IN_PROGRESS"
    match_ref.update({
        "homeWins": home_wins,
        "awayWins": away_wins,
        "winnerClanId": winner,
        "status": status,
    })
    match_data.update({
        "homeWins": home_wins,
        "awayWins": away_wins,
        "winnerClanId": winner,
        "status": status,
    })
    return match_data


def _recalc_standings(admin_code=None):
    """Recompute standings for GROUP phase matches that are FINAL."""
    base = _fs_base()
    if not base:
        return {"error": "Firestore 연결 없음"}

    # IMPORTANT:
    # standings 재계산은 "표시/집계" 로직이므로, clans의 조 배정(group)을 절대 변경하면 안 된다.
    # (조가 이상해지는 원인) 따라서 clans는 읽기만 하고, group이 없는 팀은 "추정"만 해서 standings에 포함한다.
    clans = []
    for doc in base.collection("clans").stream():
        data = doc.to_dict() or {}
        data["_docId"] = doc.id
        clans.append(data)

    clan_groups = {}
    for c in clans:
        clan_id = c.get("clanId") or c.get("_docId")
        gid = (c.get("group") or "").upper()
        if clan_id and gid:
            clan_groups[clan_id] = gid

    def infer_group_from_clan(clan_id):
        if not clan_id or not clan_id.lower().startswith("clan"):
            return None
        try:
            num = int(''.join(filter(str.isdigit, clan_id)))
        except Exception:
            return None
        if num <= 0:
            return None
        sizes = _group_size_map()
        cursor = 1
        for gid in _group_ids():
            size = sizes.get(gid, 0)
            if cursor <= num <= (cursor + size - 1):
                return gid
            cursor += size
        return None

    def _zero_row(clan_id):
        return {"clanId": clan_id, "MP": 0, "W": 0, "L": 0, "GW": 0, "GL": 0, "GD": 0, "PTS": 0}

    # IMPORTANT:
    # Standings는 "경기를 한 팀만"이 아니라 조에 속한 "전체 팀"이 항상 노출되어야 한다.
    # 그래서 먼저 clans 기반으로 각 조 row를 0으로 초기화하고,
    # 그 다음에 FINAL 경기만 누적 반영한다.
    groups = {gid: {} for gid in _group_ids()}
    for c in clans:
        clan_id = c.get("clanId") or c.get("_docId")
        if not clan_id:
            continue
        gid = (c.get("group") or "").upper()
        if not gid:
            gid = infer_group_from_clan(str(clan_id))
        if gid in groups:
            groups[gid].setdefault(clan_id, _zero_row(clan_id))

    matches = _fs_where(base.collection("matches"), "phase", "==", "GROUP").stream()
    for snap in matches:
        m = snap.to_dict() or {}
        if m.get("status") != "FINAL":
            continue
        group_id = (m.get("group") or "").upper()
        if not group_id:
            group_id = clan_groups.get(m.get("homeClanId")) or clan_groups.get(m.get("awayClanId"))
        if not group_id:
            group_id = infer_group_from_clan(m.get("homeClanId")) or infer_group_from_clan(m.get("awayClanId")) or "UNGROUPED"
        groups.setdefault(group_id, {})
        group_rows = groups[group_id]
        home = m.get("homeClanId")
        away = m.get("awayClanId")
        home_w = m.get("homeWins") or 0
        away_w = m.get("awayWins") or 0

        def add_row(clan_id, mp=0, w=0, l=0, gw=0, gl=0, pts=0):
            if not clan_id:
                return
            row = group_rows.setdefault(clan_id, _zero_row(clan_id))
            row["MP"] += mp
            row["W"] += w
            row["L"] += l
            row["GW"] += gw
            row["GL"] += gl
            row["GD"] = row["GW"] - row["GL"]
            row["PTS"] += pts

        # 승패 집계
        if home_w > away_w:
            add_row(home, mp=1, w=1, l=0, gw=home_w, gl=away_w, pts=3)
            add_row(away, mp=1, w=0, l=1, gw=away_w, gl=home_w, pts=0)
        elif away_w > home_w:
            add_row(home, mp=1, w=0, l=1, gw=home_w, gl=away_w, pts=0)
            add_row(away, mp=1, w=1, l=0, gw=away_w, gl=home_w, pts=3)
        # 무승부는 없다는 규칙이므로 동점은 무시

    # 저장
    for group_id, rows in groups.items():
        rows_list = list(rows.values())
        rows_list.sort(key=lambda r: (-(r.get("PTS") or 0), -(r.get("GD") or 0), -(r.get("GW") or 0)))
        base.collection("standings").document(group_id).set({"rows": rows_list})

    return {"ok": True, "groups": list(groups.keys())}


def _group_ids():
    return [chr(ord('A') + i) for i in range(4)]

def _group_size_map():
    return {
        "A": 6,
        "B": 5,
        "C": 5,
        "D": 5,
    }


def _fixed_groups_from_seed(clans):
    try:
        from seed_clanworldcup import FIXED_GROUPS
    except Exception:
        return None, []
    name_to_id = {}
    for c in clans:
        cid = c.get("clanId")
        name = c.get("name")
        if cid and name:
            name_to_id[name] = cid
    groups = {}
    missing = []
    for gid, names in FIXED_GROUPS.items():
        clan_ids = []
        for name in names:
            cid = name_to_id.get(name)
            if not cid:
                missing.append(name)
                continue
            clan_ids.append(cid)
        groups[gid] = clan_ids
    if missing:
        return None, missing
    return groups, []


def _ensure_clan_groups(base):
    """Ensure clans have group assignments (A~D), 21 teams total (A=6, B~D=5)."""
    clans = []
    for doc in base.collection("clans").stream():
        data = doc.to_dict() or {}
        clan_id = data.get("clanId") or doc.id
        group_id = (data.get("group") or "").upper()
        data["clanId"] = clan_id
        data["group"] = group_id
        clans.append(data)

    clans.sort(key=lambda c: c["clanId"])
    group_sizes = _group_size_map()
    groups = {gid: [] for gid in _group_ids()}
    updates = []

    fixed_groups, missing = _fixed_groups_from_seed(clans)
    if fixed_groups and not missing:
        groups = {gid: list(fixed_groups.get(gid, [])) for gid in _group_ids()}
        wanted = {}
        for gid, ids in groups.items():
            for cid in ids:
                wanted[cid] = gid
        for c in clans:
            cid = c["clanId"]
            desired = wanted.get(cid)
            if desired and c.get("group") != desired:
                updates.append({"clanId": cid, "group": desired})
        # Fill any remaining slots (should not happen when FIXED_GROUPS is complete)
        assigned = set(wanted.keys())
        unassigned = [c["clanId"] for c in clans if c["clanId"] not in assigned]
        for gid in _group_ids():
            while len(groups[gid]) < group_sizes.get(gid, 0) and unassigned:
                cid = unassigned.pop(0)
                groups[gid].append(cid)
                updates.append({"clanId": cid, "group": gid})
    else:
        unassigned = []
        for c in clans:
            if c["group"] in groups and len(groups[c["group"]]) < group_sizes.get(c["group"], 0):
                groups[c["group"]].append(c["clanId"])
            else:
                unassigned.append(c["clanId"])

        for gid in _group_ids():
            while len(groups[gid]) < group_sizes.get(gid, 0) and unassigned:
                clan_id = unassigned.pop(0)
                groups[gid].append(clan_id)
                updates.append({"clanId": clan_id, "group": gid})

        for c in clans:
            if c["group"] not in groups:
                desired = next((gid for gid, ids in groups.items() if c["clanId"] in ids), None)
                if desired:
                    updates.append({"clanId": c["clanId"], "group": desired})

    for upd in updates:
        base.collection("clans").document(upd["clanId"]).set({"group": upd["group"]}, merge=True)

    return groups


def _build_group_matches(groups):
    matches = []
    for g, clan_ids in groups.items():
        mid = 1
        for i in range(len(clan_ids)):
            for j in range(i + 1, len(clan_ids)):
                home = clan_ids[i]
                away = clan_ids[j]
                match_id = f"G{g}-{mid:02d}"
                matches.append({
                    "id": match_id,
                    "phase": "GROUP",
                    "group": g,
                    "leg": 1,
                    "bestOfMode": "FIRST3",
                    "homeClanId": home,
                    "awayClanId": away,
                    "homeWins": 0,
                    "awayWins": 0,
                    "winnerClanId": None,
                    "status": "PENDING",
                    "gameCount": 5,
                })
                mid += 1
    return matches


def _ensure_group_matches(base, groups):
    existing = {doc.id: (doc.to_dict() or {}) for doc in base.collection("matches").stream()}
    created = 0
    updated = 0
    matches = _build_group_matches(groups)
    desired_ids = {m["id"] for m in matches}
    deleted = 0

    for doc_id, doc in existing.items():
        phase = (doc.get("phase") or "").upper()
        group = (doc.get("group") or "").upper()
        if doc_id in desired_ids:
            continue
        if phase != "GROUP" and group not in set(_group_ids()):
            continue
        match_ref = base.collection("matches").document(doc_id)
        for g in match_ref.collection("games").stream():
            g.reference.delete()
        match_ref.delete()
        deleted += 1

    for m in matches:
        if m["id"] in existing:
            doc = existing[m["id"]]
            payload = {}
            if not (doc.get("group") or "").strip():
                payload["group"] = m["group"]
                payload["phase"] = "GROUP"
            if (doc.get("status") or "PENDING").upper() == "PENDING":
                home_wins = doc.get("homeWins") or 0
                away_wins = doc.get("awayWins") or 0
                if home_wins == 0 and away_wins == 0:
                    if doc.get("homeClanId") != m["homeClanId"]:
                        payload["homeClanId"] = m["homeClanId"]
                    if doc.get("awayClanId") != m["awayClanId"]:
                        payload["awayClanId"] = m["awayClanId"]
                    if "homeClanId" in payload or "awayClanId" in payload:
                        payload["winnerClanId"] = None
                        payload["status"] = "PENDING"
            if (doc.get("bestOfMode") or "").upper() != m["bestOfMode"]:
                payload["bestOfMode"] = m["bestOfMode"]
            if doc.get("gameCount") != m["gameCount"]:
                payload["gameCount"] = m["gameCount"]
            if doc.get("leg") != m.get("leg"):
                payload["leg"] = m.get("leg")
            if payload:
                base.collection("matches").document(m["id"]).set(payload, merge=True)
                updated += 1
            continue
        base.collection("matches").document(m["id"]).set({k: v for k, v in m.items() if k != "id"})
        created += 1
    return {"created": created, "updated": updated, "deleted": deleted}


def _ensure_bracket_matches(base):
    seeds = [
        ("QF-1", "A1", "B2"),
        ("QF-2", "C1", "D2"),
        ("QF-3", "B1", "A2"),
        ("QF-4", "D1", "C2"),
    ]
    progression = [
        ("SF-1", "QF-1", "QF-2", "FIRST3"),
        ("SF-2", "QF-3", "QF-4", "FIRST3"),
        ("F-1", "SF-1", "SF-2", "FIRST3"),
    ]
    created = 0
    updated = 0

    for mid, h, a in seeds:
        doc_ref = base.collection("matches").document(mid)
        snap = doc_ref.get()
        if not snap.exists:
            doc_ref.set({
                "phase": "QF",
                "group": None,
                "bestOfMode": "FIRST3",
                "homeClanId": h,
                "awayClanId": a,
                "homeWins": 0,
                "awayWins": 0,
                "winnerClanId": None,
                "status": "PENDING",
                "gameCount": 5,
            })
            created += 1
        else:
            data = snap.to_dict() or {}
            payload = {}
            if (data.get("phase") or "").upper() != "QF":
                payload["phase"] = "QF"
            if (data.get("bestOfMode") or "ALL5").upper() != "FIRST3":
                payload["bestOfMode"] = "FIRST3"
            if (data.get("status") or "PENDING").upper() == "PENDING":
                if _is_seed_placeholder(data.get("homeClanId")) and data.get("homeClanId") != h:
                    payload["homeClanId"] = h
                if _is_seed_placeholder(data.get("awayClanId")) and data.get("awayClanId") != a:
                    payload["awayClanId"] = a
            if payload:
                doc_ref.set(payload, merge=True)
                updated += 1

    for mid, h, a, mode in progression:
        doc_ref = base.collection("matches").document(mid)
        snap = doc_ref.get()
        if not snap.exists:
            doc_ref.set({
                "phase": "QF" if mid.startswith("QF") else ("SF" if mid.startswith("SF") else "F"),
                "group": None,
                "bestOfMode": mode,
                "homeClanId": f"WIN-{h}",
                "awayClanId": f"WIN-{a}",
                "homeWins": 0,
                "awayWins": 0,
                "winnerClanId": None,
                "status": "PENDING",
                "gameCount": 5,
            })
            created += 1
        else:
            data = snap.to_dict() or {}
            payload = {}
            expected_phase = "SF" if mid.startswith("SF") else "F"
            if (data.get("phase") or "").upper() != expected_phase:
                payload["phase"] = expected_phase
            if (data.get("bestOfMode") or "").upper() != mode:
                payload["bestOfMode"] = mode
            if (data.get("status") or "PENDING").upper() == "PENDING":
                home_val = f"WIN-{h}"
                away_val = f"WIN-{a}"
                if _is_seed_placeholder(data.get("homeClanId")) and data.get("homeClanId") != home_val:
                    payload["homeClanId"] = home_val
                if _is_seed_placeholder(data.get("awayClanId")) and data.get("awayClanId") != away_val:
                    payload["awayClanId"] = away_val
            if payload:
                doc_ref.set(payload, merge=True)
                updated += 1

    return {"created": created, "updated": updated}


def _ensure_group_standings(base, groups):
    created = 0
    for gid, clan_ids in groups.items():
        doc_ref = base.collection("standings").document(gid)
        if doc_ref.get().exists:
            continue
        rows = [
            {"clanId": cid, "MP": 0, "W": 0, "L": 0, "GW": 0, "GL": 0, "GD": 0, "PTS": 0}
            for cid in clan_ids
        ]
        doc_ref.set({"rows": rows})
        created += 1
    return {"created": created}


def _build_group_seed_map(base):
    standings = {}
    for gid in _group_ids():
        doc = base.collection("standings").document(gid).get()
        if not doc.exists:
            continue
        data = doc.to_dict() or {}
        rows = data.get("rows") or []
        rows = sorted(rows, key=lambda r: (-(r.get("PTS") or 0), -(r.get("GD") or 0), -(r.get("GW") or 0)))
        if len(rows) >= 1 and rows[0].get("clanId"):
            standings[f"{gid}1"] = rows[0].get("clanId")
        if len(rows) >= 2 and rows[1].get("clanId"):
            standings[f"{gid}2"] = rows[1].get("clanId")
    return standings


def _is_seed_placeholder(value):
    if value in [None, ""]:
        return True
    text = str(value)
    return text.startswith("WIN-") or bool(re.match(r"^[A-D][12]$", text))


def _resolve_knockout_seed(seed_label, group_seed_map, winner_map):
    if not seed_label:
        return None
    text = str(seed_label)
    if text.startswith("WIN-"):
        return winner_map.get(text.replace("WIN-", "", 1)) or text
    return group_seed_map.get(text) or text


def _reset_match_games(match_ref):
    reset = 0
    for snap in match_ref.collection("games").stream():
        game = snap.to_dict() or {}
        slot = game.get("slot")
        if slot is None:
            try:
                slot = int(snap.id)
            except Exception:
                slot = snap.id
        snap.reference.set({
            "slot": slot,
            "homeScore": None,
            "awayScore": None,
            "status": "NOT_PLAYED",
        }, merge=True)
        reset += 1
    return reset


def _sync_knockout_bracket(base):
    """
    Keep knockout bracket participants in sync with latest standings/winners.
    If upstream results change, downstream participants and match results are reset.
    """
    if not base:
        return {"updated": 0, "resetGames": 0}

    # Ensure existing quarterfinal matches honor first-to-3 and finalize if already decided.
    for mid in ["QF-1", "QF-2", "QF-3", "QF-4"]:
        _recalc_match_totals(mid)

    group_seed_map = _build_group_seed_map(base)
    winner_map = {}
    updated = 0
    reset_games = 0
    knockout_order = [
        "QF-1", "QF-2", "QF-3", "QF-4",
        "SF-1", "SF-2",
        "F-1",
    ]

    for match_id in knockout_order:
        match_ref = base.collection("matches").document(match_id)
        snap = match_ref.get()
        if not snap.exists:
            continue
        data = snap.to_dict() or {}
        labels = _knockout_seed_labels(match_id)
        if not labels:
            continue

        expected_home = _resolve_knockout_seed(labels[0], group_seed_map, winner_map)
        expected_away = _resolve_knockout_seed(labels[1], group_seed_map, winner_map)
        current_home = data.get("homeClanId")
        current_away = data.get("awayClanId")
        participants_changed = (current_home != expected_home) or (current_away != expected_away)

        unresolved_participants = _is_seed_placeholder(expected_home) or _is_seed_placeholder(expected_away)
        needs_reset = participants_changed
        if unresolved_participants:
            needs_reset = needs_reset or (
                (data.get("status") or "PENDING").upper() != "PENDING"
                or (data.get("winnerClanId") is not None)
                or (data.get("homeWins") or 0) != 0
                or (data.get("awayWins") or 0) != 0
            )

        payload = {}
        if participants_changed:
            payload["homeClanId"] = expected_home
            payload["awayClanId"] = expected_away
        if needs_reset:
            payload.update({
                "homeWins": 0,
                "awayWins": 0,
                "winnerClanId": None,
                "status": "PENDING",
            })

        if payload:
            match_ref.set(payload, merge=True)
            updated += 1
        if needs_reset:
            reset_games += _reset_match_games(match_ref)

        if not needs_reset:
            winner = data.get("winnerClanId")
            if (
                (data.get("status") or "").upper() == "FINAL"
                and winner
                and winner in [expected_home, expected_away]
                and not _is_seed_placeholder(winner)
            ):
                winner_map[match_id] = winner

    return {"updated": updated, "resetGames": reset_games}


def _apply_group_seeds_to_qf(base):
    standings = _build_group_seed_map(base)

    if not standings:
        return {"updated": 0}

    seeds = [
        ("QF-1", "A1", "B2"),
        ("QF-2", "C1", "D2"),
        ("QF-3", "B1", "A2"),
        ("QF-4", "D1", "C2"),
    ]
    updated = 0
    for mid, h_seed, a_seed in seeds:
        doc_ref = base.collection("matches").document(mid)
        snap = doc_ref.get()
        if not snap.exists:
            continue
        data = snap.to_dict() or {}
        if (data.get("status") or "PENDING").upper() != "PENDING":
            continue
        home = standings.get(h_seed)
        away = standings.get(a_seed)
        payload = {}
        if home and (data.get("homeClanId") in [None, "", h_seed]):
            payload["homeClanId"] = home
        if away and (data.get("awayClanId") in [None, "", a_seed]):
            payload["awayClanId"] = away
        if payload:
            doc_ref.set(payload, merge=True)
            updated += 1
    return {"updated": updated}


def _apply_bracket_winner(base, match_id, winner_clan_id):
    if not winner_clan_id:
        return {"updated": 0}
    updated = 0
    matches = base.collection("matches").stream()
    for snap in matches:
        data = snap.to_dict() or {}
        home = data.get("homeClanId")
        away = data.get("awayClanId")
        win_key = f"WIN-{match_id}"
        payload = {}
        if home == win_key:
            payload["homeClanId"] = winner_clan_id
        if away == win_key:
            payload["awayClanId"] = winner_clan_id
        if payload:
            snap.reference.set(payload, merge=True)
            updated += 1
    return {"updated": updated}


def _rebuild_clan_groups_from_group_matches(base):
    """
    Rebuild `clans.group` using GROUP-phase match schedule.
    This is a recovery tool for cases where clan group assignments were accidentally changed.

    Strategy:
    - Scan all matches where phase == GROUP and group in A~D
    - For each clanId, count how many times it appears per group
    - Assign the clan to the group with the highest count (ties -> alphabetically)
    - Write back to clans/{clanId}.group with merge=True
    """
    if not base:
        return {"updated": 0, "skipped": 0}

    counts = {}  # clanId -> {gid: n}
    matches = _fs_where(base.collection("matches"), "phase", "==", "GROUP").stream()
    for snap in matches:
        m = snap.to_dict() or {}
        gid = (m.get("group") or "").upper()
        if gid not in set(_group_ids()):
            continue
        for key in ("homeClanId", "awayClanId"):
            cid = m.get(key)
            if not cid:
                continue
            counts.setdefault(cid, {})
            counts[cid][gid] = counts[cid].get(gid, 0) + 1

    updated = 0
    skipped = 0
    for clan_id, per_group in counts.items():
        if not per_group:
            skipped += 1
            continue
        best_gid, _best_n = sorted(per_group.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        base.collection("clans").document(str(clan_id)).set({"group": best_gid}, merge=True)
        updated += 1

    return {"updated": updated, "skipped": skipped}


def _seed_schedule(base):
    groups = _ensure_clan_groups(base)
    group_matches = _ensure_group_matches(base, groups)
    standings = _ensure_group_standings(base, groups)
    bracket = _ensure_bracket_matches(base)
    return {"groups": groups, "group_matches": group_matches, "standings": standings, "bracket": bracket}


def _get_clans():
    base = _fs_base()
    if not base:
        return []
    clans = []
    for doc in base.collection("clans").stream():
        data = doc.to_dict() or {}
        data["clanId"] = data.get("clanId") or doc.id
        clans.append(data)
    return clans


def _get_standings():
    base = _fs_base()
    if not base:
        return []
    standings = []
    for doc in base.collection("standings").stream():
        data = doc.to_dict() or {}
        data["groupId"] = doc.id
        standings.append(data)
    return standings


def _is_group_stage_complete(base):
    matches = _fs_where(base.collection("matches"), "phase", "==", "GROUP").stream()
    for snap in matches:
        data = snap.to_dict() or {}
        if (data.get("status") or "").upper() != "FINAL":
            return False
    return True


def _knockout_seed_labels(match_id):
    qf_seeds = {
        "QF-1": ("A1", "B2"),
        "QF-2": ("C1", "D2"),
        "QF-3": ("B1", "A2"),
        "QF-4": ("D1", "C2"),
    }
    if match_id in qf_seeds:
        return qf_seeds[match_id]
    sf_seeds = {
        "SF-1": ("WIN-QF-1", "WIN-QF-2"),
        "SF-2": ("WIN-QF-3", "WIN-QF-4"),
    }
    if match_id in sf_seeds:
        return sf_seeds[match_id]
    f_seeds = {
        "F-1": ("WIN-SF-1", "WIN-SF-2"),
    }
    return f_seeds.get(match_id)


csrf = CSRFProtect(app)
@app.context_processor
def inject_csrf_token():
    if request.path == "/sitemap.xml" or request.path.startswith("/sitemaps/"):
        return {}
    analytics_excluded_endpoints = {
        "player_review_summary_admin",
    }
    try:
        is_admin_user = _is_admin_user()
    except Exception:
        is_admin_user = False
    unread_notification_count = 0
    notification_model = globals().get("Notification")
    if current_user.is_authenticated and notification_model is not None:
        try:
            unread_notification_count = notification_model.query.filter_by(
                user_id=current_user.id,
                read_at=None,
            ).count()
        except Exception as e:
            print(f"Notification count read failed: {e}")
    return dict(
        csrf_token=generate_csrf(),
        price_unit=globals().get("PRICE_UNIT", "MP"),
        is_admin_user=is_admin_user,
        unread_notification_count=unread_notification_count,
        google_client_id=app.config.get("GOOGLE_CLIENT_ID", ""),
        recaptcha_site_key=app.config.get("RECAPTCHA_SITE_KEY", ""),
        recaptcha_enabled=bool(
            app.config.get("RECAPTCHA_SITE_KEY")
            and app.config.get("RECAPTCHA_SECRET_KEY")
        ),
        ga_measurement_id=(
            ""
            if request.endpoint in analytics_excluded_endpoints
            else app.config.get("GA_MEASUREMENT_ID", "")
        ),
    )


db = SQLAlchemy(app)
migrate = Migrate(app, db)

login_manager = LoginManager(app)
login_manager.login_view = 'login' # Redirect to 'login' view if user is not logged in
login_manager.login_message = "로그인이 필요한 페이지입니다."
login_manager.login_message_category = "info"

@app.template_filter('nl2br')
def nl2br_filter(s):
    if not s:
        return ""
    return s.replace("\n", "<br>")


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    email_verified_at = db.Column(db.DateTime, nullable=True)
    verification_sent_at = db.Column(db.DateTime, nullable=True)
    google_sub = db.Column(db.String(255), unique=True, nullable=True)
    username_confirmed = db.Column(db.Boolean, default=True, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return bool(
            self.password_hash
            and password
            and check_password_hash(self.password_hash, password)
        )


def _csv_config_values(key):
    return {item.strip().lower() for item in app.config.get(key, "").split(",") if item.strip()}


def _user_matches_configured_admin(user):
    if not user:
        return False
    admin_ids = _csv_config_values("FIMOBOOK_ADMIN_USER_IDS")
    admin_emails = _csv_config_values("FIMOBOOK_ADMIN_EMAILS")
    admin_usernames = _csv_config_values("FIMOBOOK_ADMIN_USERNAMES")
    return (
        str(getattr(user, "id", "")).lower() in admin_ids
        or (getattr(user, "email", "") or "").strip().lower() in admin_emails
        or (getattr(user, "username", "") or "").strip().lower() in admin_usernames
    )


def _sync_admin_flag(user):
    if user and not getattr(user, "is_admin", False) and _user_matches_configured_admin(user):
        user.is_admin = True
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    return user


def _is_admin_user():
    return bool(
        current_user.is_authenticated
        and (getattr(current_user, "is_admin", False) or _user_matches_configured_admin(current_user))
    )


def _admin_setup_password():
    return (
        app.config.get("FIMOBOOK_ADMIN_SETUP_PASSWORD", "").strip()
        or app.config.get("PLAYER_SUMMARY_ADMIN_PASSWORD", "").strip()
    )


@login_manager.user_loader
def load_user(user_id):
    return _sync_admin_flag(db.session.get(User, int(user_id)))

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    likes = db.Column(db.Integer, default=0)
    views = db.Column(db.Integer, default=0, nullable=False)
    image_filename = db.Column(db.String(200), nullable=True)  # 🔥 추가
    board_type = db.Column(db.String(20), default="free", nullable=False)
    is_pinned = db.Column(db.Boolean, default=False, nullable=False)
    poll_question = db.Column(db.String(200), nullable=True)
    comments = db.relationship('Comment', backref='post', lazy=True)
    poll_options = db.relationship(
        'PollOption',
        backref='post',
        lazy=True,
        cascade='all, delete-orphan',
        order_by='PollOption.position',
    )
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    author = db.relationship('User', backref='posts')


class PollOption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False, index=True)
    text = db.Column(db.String(80), nullable=False)
    position = db.Column(db.Integer, default=0, nullable=False)
    votes = db.relationship(
        'PollVote',
        backref='option',
        lazy=True,
        cascade='all, delete-orphan',
    )


class PollVote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False, index=True)
    option_id = db.Column(db.Integer, db.ForeignKey('poll_option.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (
        db.UniqueConstraint('post_id', 'user_id', name='uq_poll_vote_post_user'),
    )


class PostLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (
        db.UniqueConstraint('post_id', 'user_id', name='uq_post_like_post_user'),
    )


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # Can be nullable for anonymous comments
    author = db.relationship('User', backref='comments')
    replies = db.relationship(
        'Comment',
        backref=db.backref('parent', remote_side=[id]),
        lazy=True,
        cascade='all, delete-orphan',
        single_parent=True,
    )


class PlayerReviewComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_cid = db.Column(db.Integer, nullable=False, index=True)
    review_id = db.Column(db.String(120), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('player_review_comment.id'), nullable=True)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    author = db.relationship('User', backref='player_review_comments')
    replies = db.relationship(
        'PlayerReviewComment',
        backref=db.backref('parent', remote_side=[id]),
        lazy=True,
        cascade='all, delete-orphan',
        single_parent=True,
    )


COMMENT_RATE_LIMIT_WINDOW = timedelta(minutes=1)
COMMENT_RATE_LIMIT_COUNT = 5
COMMENT_HOURLY_LIMIT_WINDOW = timedelta(hours=1)
COMMENT_HOURLY_LIMIT_COUNT = 20
COMMENT_MAX_LENGTH = 1000


def _comment_count_since(user_id, cutoff):
    return (
        Comment.query.filter(
            Comment.author_id == user_id,
            Comment.created_at >= cutoff,
        ).count()
        + PlayerReviewComment.query.filter(
            PlayerReviewComment.author_id == user_id,
            PlayerReviewComment.created_at >= cutoff,
        ).count()
    )


def _comment_rate_limit_message(user_id):
    """Return a user-facing error when an account is posting comments too quickly."""
    if user_id is None or _is_admin_user():
        return None

    now = datetime.utcnow()
    if _comment_count_since(user_id, now - COMMENT_RATE_LIMIT_WINDOW) >= COMMENT_RATE_LIMIT_COUNT:
        return "댓글을 너무 빠르게 작성하고 있습니다. 1분 후 다시 시도해주세요."
    if _comment_count_since(user_id, now - COMMENT_HOURLY_LIMIT_WINDOW) >= COMMENT_HOURLY_LIMIT_COUNT:
        return "시간당 댓글 작성 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
    return None


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    kind = db.Column(db.String(40), nullable=False, default="activity")
    message = db.Column(db.String(300), nullable=False)
    target_url = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    read_at = db.Column(db.DateTime, nullable=True, index=True)
    actor = db.relationship('User', foreign_keys=[actor_id])
    __table_args__ = (
        db.Index("ix_notification_user_unread", "user_id", "read_at"),
    )


class ReviewPointLedger(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    player_cid = db.Column(db.Integer, nullable=False)
    points = db.Column(db.Integer, default=100, nullable=False)
    month_key = db.Column(db.String(7), nullable=False)
    source = db.Column(db.String(30), default="review", nullable=False)
    admin_reason = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='review_point_entries')

class PlayerRating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_cid = db.Column(db.Integer, nullable=False) # 선수 고유 ID
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    overall_rating = db.Column(db.Integer, nullable=False) # 전체 평점 (1-5점)

    # 상세 평점 (1-5점)
    speed_rating = db.Column(db.Integer, nullable=True)
    shot_rating = db.Column(db.Integer, nullable=True)
    pass_rating = db.Column(db.Integer, nullable=True)
    feel_rating = db.Column(db.Integer, nullable=True)
    heading_rating = db.Column(db.Integer, nullable=True)
    powershot_rating = db.Column(db.Integer, nullable=True)
    defense_ai_rating = db.Column(db.Integer, nullable=True)
    physicality_rating = db.Column(db.Integer, nullable=True)

    review_text = db.Column(db.Text, nullable=True) # 평가 텍스트
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 한 사용자는 한 선수에게 한 번만 평점을 남길 수 있도록 유니크 제약 조건 추가
    __table_args__ = (db.UniqueConstraint('player_cid', 'user_id', name='_player_user_uc'),)


class PushToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(512), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    is_enabled = db.Column(db.Boolean, default=True, nullable=False)
    coupons_enabled = db.Column(db.Boolean, default=True, nullable=False)
    mode = db.Column(db.String(20), default="digest", nullable=False)
    last_push_at = db.Column(db.DateTime, nullable=True)


class CouponSeen(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(120), unique=True, nullable=False)
    first_seen_at = db.Column(db.DateTime, default=datetime.utcnow)


class PostForm(FlaskForm):
    title = StringField('제목', validators=[DataRequired()])
    content = TextAreaField('내용', validators=[DataRequired()])
    image = FileField(
        '이미지',
        validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], '이미지 파일만 업로드할 수 있습니다.')]
    )

class MoneyLeagueRegistrationForm(FlaskForm):
    author_nickname = StringField('작성자 닉네임')
    clan_name = StringField('클랜명', validators=[DataRequired()])
    participant_count = StringField('참가 인원', validators=[DataRequired()])
    participant_roster = TextAreaField('참가 인원 명단', validators=[DataRequired()])
    resolve_message = TextAreaField('각오 한마디', validators=[DataRequired()])
    clan_screenshot = FileField(
        '게임 내 클랜 페이지 스크린샷',
        validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], '이미지 파일만 업로드할 수 있습니다.')]
    )

COMMUNITY_BOARDS = {
    "notice": {"label": "공지사항", "title": "공지사항"},
    "free": {"label": "자유게시판", "title": "자유게시판"},
    "review": {"label": "리뷰게시판", "title": "선수 리뷰"},
    "squad": {"label": "스쿼드게시판", "title": "스쿼드게시판"},
}
REVIEW_POINT_VALUE = 100
KST = timezone(timedelta(hours=9))


def _now_kst():
    return datetime.now(KST)


def _now_kst_iso():
    return _now_kst().isoformat(timespec="seconds")


def _format_kst_datetime(value=None, fallback_iso=None):
    dt = None
    if hasattr(value, "astimezone"):
        dt = value
    else:
        raw = str(fallback_iso or "").strip()
        if raw and raw != "-":
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                dt = None
    if not dt:
        return "-"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M")


def _notification_time_display(created_at):
    if not created_at:
        return ""
    now = datetime.utcnow()
    seconds = max(0, int((now - created_at).total_seconds()))
    if seconds < 60:
        return "방금 전"
    if seconds < 3600:
        return f"{seconds // 60}분 전"
    if seconds < 86400:
        return f"{seconds // 3600}시간 전"
    if seconds < 604800:
        return f"{seconds // 86400}일 전"
    return created_at.replace(tzinfo=timezone.utc).astimezone(KST).strftime("%Y.%m.%d")


def _notification_target_url(value):
    value = str(value or "").strip()
    if not value.startswith("/") or value.startswith("//"):
        return url_for("notifications")
    return value[:500]


def _create_notifications(recipient_ids, kind, message, target_url, actor_id=None):
    try:
        actor_id = int(actor_id) if actor_id is not None else None
    except (TypeError, ValueError):
        actor_id = None

    valid_ids = set()
    for value in recipient_ids or []:
        try:
            user_id = int(value)
        except (TypeError, ValueError):
            continue
        if user_id > 0 and user_id != actor_id:
            valid_ids.add(user_id)

    if not valid_ids:
        return

    existing_user_ids = {
        row[0]
        for row in db.session.query(User.id).filter(User.id.in_(valid_ids)).all()
    }
    safe_message = re.sub(r"\s+", " ", str(message or "새로운 알림이 있습니다.")).strip()[:300]
    safe_target_url = _notification_target_url(target_url)
    safe_kind = str(kind or "activity").strip()[:40]
    for user_id in existing_user_ids:
        db.session.add(Notification(
            user_id=user_id,
            actor_id=actor_id,
            kind=safe_kind,
            message=safe_message,
            target_url=safe_target_url,
        ))


def _ensure_local_schema():
    try:
        os.makedirs(app.instance_path, exist_ok=True)
        db.create_all()
        with db.engine.begin() as conn:
            def columns(table):
                return {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}

            post_columns = columns("post")
            if "board_type" not in post_columns:
                conn.exec_driver_sql("ALTER TABLE post ADD COLUMN board_type VARCHAR(20) NOT NULL DEFAULT 'free'")
            if "views" not in post_columns:
                conn.exec_driver_sql("ALTER TABLE post ADD COLUMN views INTEGER NOT NULL DEFAULT 0")
            if "is_pinned" not in post_columns:
                conn.exec_driver_sql("ALTER TABLE post ADD COLUMN is_pinned BOOLEAN NOT NULL DEFAULT 0")
            if "poll_question" not in post_columns:
                conn.exec_driver_sql("ALTER TABLE post ADD COLUMN poll_question VARCHAR(200)")

            user_columns = columns("user")
            if "is_admin" not in user_columns:
                conn.exec_driver_sql("ALTER TABLE user ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0")

            comment_columns = columns("comment")
            if "parent_id" not in comment_columns:
                conn.exec_driver_sql("ALTER TABLE comment ADD COLUMN parent_id INTEGER")

            ledger_columns = columns("review_point_ledger")
            if "source" not in ledger_columns:
                conn.exec_driver_sql("ALTER TABLE review_point_ledger ADD COLUMN source VARCHAR(30) NOT NULL DEFAULT 'review'")
            if "admin_reason" not in ledger_columns:
                conn.exec_driver_sql("ALTER TABLE review_point_ledger ADD COLUMN admin_reason VARCHAR(200)")

            push_columns = columns("push_token")
            if "coupons_enabled" not in push_columns:
                conn.exec_driver_sql("ALTER TABLE push_token ADD COLUMN coupons_enabled BOOLEAN NOT NULL DEFAULT 1")
            if "mode" not in push_columns:
                conn.exec_driver_sql("ALTER TABLE push_token ADD COLUMN mode VARCHAR(20) NOT NULL DEFAULT 'digest'")
            if "last_push_at" not in push_columns:
                conn.exec_driver_sql("ALTER TABLE push_token ADD COLUMN last_push_at DATETIME")

            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_notification_user_unread ON notification (user_id, read_at)"
            )
    except Exception as e:
        print(f"Local schema ensure failed: {e}")


with app.app_context():
    _ensure_local_schema()


def _normalize_board_type(value):
    value = str(value or "").strip().lower()
    return value if value in COMMUNITY_BOARDS else "free"


def _poll_payload_from_request():
    if request.form.get("poll_enabled") != "1":
        return None, [], None

    question = re.sub(r"\s+", " ", request.form.get("poll_question", "")).strip()
    if not question:
        return None, [], "투표 질문을 입력해주세요."
    if len(question) > 200:
        return None, [], "투표 질문은 200자 이하로 입력해주세요."

    options = []
    seen = set()
    for raw_option in request.form.getlist("poll_options"):
        option = re.sub(r"\s+", " ", raw_option or "").strip()
        if not option:
            continue
        if len(option) > 80:
            return None, [], "투표 항목은 각각 80자 이하로 입력해주세요."
        normalized = option.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        options.append(option)

    if len(options) < 2:
        return None, [], "투표 항목을 2개 이상 입력해주세요."
    if len(options) > 6:
        return None, [], "투표 항목은 최대 6개까지 등록할 수 있습니다."
    return question, options, None


def _save_post_poll(post, question, options):
    PollVote.query.filter_by(post_id=post.id).delete(synchronize_session=False)
    PollOption.query.filter_by(post_id=post.id).delete(synchronize_session=False)
    post.poll_question = question
    for position, text in enumerate(options):
        db.session.add(PollOption(post_id=post.id, text=text, position=position))


def _save_uploaded_post_image(file):
    if not file or not file.filename or not allowed_image(file.filename):
        return None
    original = secure_filename(file.filename)
    extension = os.path.splitext(original)[1].lower()
    filename = f"board_{uuid.uuid4().hex}{extension}"
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return filename


def _month_key(dt=None):
    dt = dt or datetime.utcnow()
    return dt.strftime("%Y-%m")


def _previous_month_key(dt=None):
    dt = dt or datetime.utcnow()
    year = dt.year
    month = dt.month - 1
    if month == 0:
        year -= 1
        month = 12
    return f"{year:04d}-{month:02d}"


def _review_point_total(user_id, month_key=None):
    query = db.session.query(func.coalesce(func.sum(ReviewPointLedger.points), 0)).filter(
        ReviewPointLedger.user_id == user_id
    )
    if month_key:
        query = query.filter(ReviewPointLedger.month_key == month_key)
    return int(query.scalar() or 0)


def _review_point_rankings(month_key=None, limit=20):
    query = (
        db.session.query(
            User,
            func.coalesce(func.sum(ReviewPointLedger.points), 0).label("points"),
        )
        .join(ReviewPointLedger, ReviewPointLedger.user_id == User.id)
    )
    if month_key:
        query = query.filter(ReviewPointLedger.month_key == month_key)
    query = (
        query.group_by(User.id)
        .order_by(func.sum(ReviewPointLedger.points).desc(), User.username.asc())
    )
    if limit:
        query = query.limit(limit)
    rows = query.all()
    return [{"user": user, "points": int(points or 0)} for user, points in rows]


def _award_review_points(user, cid):
    if not user or not getattr(user, "id", None):
        return
    entry = ReviewPointLedger(
        user_id=user.id,
        player_cid=int(cid),
        points=REVIEW_POINT_VALUE,
        month_key=_month_key(),
    )
    db.session.add(entry)
    db.session.commit()


def _award_admin_points(user, points, reason=""):
    if not user or not getattr(user, "id", None):
        return
    entry = ReviewPointLedger(
        user_id=user.id,
        player_cid=0,
        points=int(points),
        month_key=_month_key(),
        source="admin_grant",
        admin_reason=(reason or "").strip()[:200],
    )
    db.session.add(entry)
    reason_text = re.sub(r"\s+", " ", (reason or "").strip())[:80]
    message = f"관리자가 {int(points):,}포인트를 지급했습니다."
    if reason_text:
        message += f" 사유: {reason_text}"
    _create_notifications(
        [user.id],
        "points",
        message,
        "/profile",
        actor_id=current_user.id if has_request_context() and current_user.is_authenticated else None,
    )
    db.session.commit()


def _delete_all_cached_player_reviews_for_user(user_id):
    if user_id is None:
        return
    cache = _load_player_review_cache()
    changed = False
    user_key = str(user_id)
    for player_reviews in cache.values():
        if not isinstance(player_reviews, dict):
            continue
        if user_key in player_reviews:
            player_reviews.pop(user_key, None)
            changed = True
        for review_id, review in list(player_reviews.items()):
            if isinstance(review, dict) and str(review.get("user_id")) == user_key:
                player_reviews.pop(review_id, None)
                changed = True
    if changed:
        _save_player_review_cache(cache)


def _cached_player_review_refs_for_user(user_id):
    if user_id is None:
        return []
    user_key = str(user_id)
    refs = set()
    cache = _load_player_review_cache()
    for player_cid, player_reviews in cache.items():
        if not isinstance(player_reviews, dict):
            continue
        for review_id, review in player_reviews.items():
            if not isinstance(review, dict):
                continue
            if str(review.get("user_id")) != user_key and str(review_id) != user_key:
                continue
            document_ids = {
                user_key,
                str(review_id or "").strip(),
                str(review.get("id") or "").strip(),
            }
            for document_id in document_ids:
                if document_id:
                    refs.add((str(player_cid), document_id))
    return sorted(refs)


def _delete_remote_player_reviews_for_user(user_id):
    """Delete the user's Firestore review documents before removing the account."""
    if user_id is None or not fs:
        return True
    refs = _cached_player_review_refs_for_user(user_id)
    if not refs:
        return True
    try:
        for offset in range(0, len(refs), 400):
            batch = fs.batch()
            for player_cid, review_id in refs[offset:offset + 400]:
                batch.delete(
                    _player_review_collection(player_cid).document(review_id)
                )
            batch.commit(retry=None, timeout=20)
        return True
    except Exception as error:
        app.logger.exception(
            "Firestore account review deletion failed for user %s: %s",
            user_id,
            error,
        )
        return False


def _purge_local_user_content(user_id):
    """Delete local posts and comment threads created by an abusive account."""
    if user_id is None:
        return

    authored_posts = Post.query.filter_by(author_id=user_id).all()
    for post in authored_posts:
        Comment.query.filter_by(post_id=post.id).delete(synchronize_session=False)
        PollVote.query.filter_by(post_id=post.id).delete(synchronize_session=False)
        PollOption.query.filter_by(post_id=post.id).delete(synchronize_session=False)
        PostLike.query.filter_by(post_id=post.id).delete(synchronize_session=False)
        db.session.delete(post)

    PollVote.query.filter_by(user_id=user_id).delete(synchronize_session=False)

    target_comment_ids = {
        row[0]
        for row in db.session.query(Comment.id).filter(Comment.author_id == user_id).all()
    }
    if target_comment_ids:
        roots = Comment.query.filter(
            Comment.id.in_(target_comment_ids),
            (Comment.parent_id.is_(None)) | (~Comment.parent_id.in_(target_comment_ids)),
        ).all()
        for comment in roots:
            db.session.delete(comment)

    target_review_comment_ids = {
        row[0]
        for row in db.session.query(PlayerReviewComment.id)
        .filter(PlayerReviewComment.author_id == user_id)
        .all()
    }
    if target_review_comment_ids:
        roots = PlayerReviewComment.query.filter(
            PlayerReviewComment.id.in_(target_review_comment_ids),
            (PlayerReviewComment.parent_id.is_(None))
            | (~PlayerReviewComment.parent_id.in_(target_review_comment_ids)),
        ).all()
        for comment in roots:
            db.session.delete(comment)


def _delete_local_user_account(user, purge_content=False):
    user_id = getattr(user, "id", None)
    if user_id is None:
        return
    if purge_content:
        _purge_local_user_content(user_id)
    else:
        Post.query.filter_by(author_id=user_id).update({"author_id": None}, synchronize_session=False)
        Comment.query.filter_by(author_id=user_id).update({"author_id": None}, synchronize_session=False)
        PlayerReviewComment.query.filter_by(author_id=user_id).update({"author_id": None}, synchronize_session=False)
    Notification.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    if purge_content:
        Notification.query.filter_by(actor_id=user_id).delete(synchronize_session=False)
    else:
        Notification.query.filter_by(actor_id=user_id).update({"actor_id": None}, synchronize_session=False)
    ReviewPointLedger.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    PlayerRating.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    _delete_all_cached_player_reviews_for_user(user_id)
    for key in list(_PENDING_PLAYER_REVIEWS.keys()):
        if len(key) > 1 and str(key[1]) == str(user_id):
            _PENDING_PLAYER_REVIEWS.pop(key, None)
    db.session.delete(user)
    db.session.commit()


def _community_sidebar_context():
    return {
        "monthly_rankings": _review_point_rankings(_month_key(), limit=30),
        "current_month_key": _month_key(),
    }


def _latest_notice_post():
    try:
        return (
            Post.query.filter_by(board_type="notice")
            .order_by(Post.is_pinned.desc(), Post.created_at.desc())
            .first()
        )
    except Exception as e:
        print(f"Latest notice read failed: {e}")
        return None


def _get_reviews_by_user(user_id, limit=None):
    reviews = []
    cached = _load_player_review_cache()
    for player_reviews in cached.values():
        if isinstance(player_reviews, dict):
            for item in player_reviews.values():
                if isinstance(item, dict) and str(item.get("user_id")) == str(user_id):
                    reviews.append(_format_player_review_data(dict(item)))

    # The local cache is updated together with every review write and contains the
    # complete migrated history. Only fall back to the indexed remote query when a
    # user's reviews are absent locally.
    if not reviews and fs:
        try:
            query = _fs_where(
                fs.collection_group("reviews"),
                "user_id",
                "==",
                user_id,
            )
            if limit:
                query = query.limit(limit)
            reviews.extend(
                _format_player_review_doc(doc)
                for doc in query.stream(retry=None, timeout=8)
            )
        except Exception as e:
            print(f"Firestore user review read failed for {user_id}: {e}")

    return _dedupe_player_reviews(reviews, limit=limit)


def _profile_activity_summary(user, reviews):
    user_id = user.id
    post_count = Post.query.filter_by(author_id=user_id).count()
    post_comment_count = Comment.query.filter_by(author_id=user_id).count()
    review_comment_count = PlayerReviewComment.query.filter_by(
        author_id=user_id
    ).count()
    likes_received = int(
        db.session.query(func.coalesce(func.sum(Post.likes), 0))
        .filter(Post.author_id == user_id)
        .scalar()
        or 0
    )

    monthly_rank = None
    for index, row in enumerate(
        _review_point_rankings(_month_key(), limit=None),
        start=1,
    ):
        if row["user"].id == user_id:
            monthly_rank = index
            break

    return {
        "review_count": len(reviews),
        "post_count": post_count,
        "comment_count": post_comment_count + review_comment_count,
        "post_comment_count": post_comment_count,
        "review_comment_count": review_comment_count,
        "likes_received": likes_received,
        "monthly_rank": monthly_rank,
    }


def _is_moneyleague_registration_open():
    return bool(app.config.get("MONEYLEAGUE_REGISTRATION_OPEN"))

def _moneyleague_registration_collection():
    if not fs:
        return None
    return fs.collection("moneyleague_registrations")

def _format_moneyleague_registration(doc):
    data = doc.to_dict() or {}
    created_at = data.get("created_at")
    created_at_display = "-"
    if hasattr(created_at, "strftime"):
        created_at_display = created_at.strftime("%Y-%m-%d %H:%M")

    return {
        "id": doc.id,
        "clan_name": data.get("clan_name", ""),
        "participant_count": data.get("participant_count", ""),
        "participant_roster": data.get("participant_roster", ""),
        "resolve_message": data.get("resolve_message", ""),
        "author_id": data.get("author_id"),
        "author_name": data.get("author_name", "익명"),
        "author_ip_prefix": data.get("author_ip_prefix", ""),
        "author_display": data.get("author_display") or data.get("author_name", "익명"),
        "clan_screenshot_path": data.get("clan_screenshot_path"),
        "created_at_display": created_at_display,
    }

def _get_moneyleague_registration_or_404(registration_id):
    collection = _moneyleague_registration_collection()
    if not collection:
        abort(503)
    doc = collection.document(registration_id).get()
    if not doc.exists:
        abort(404)
    return doc, _format_moneyleague_registration(doc)

def _extract_moneyleague_registration_payload(form):
    clan_name = (form.clan_name.data or "").strip()
    participant_count_raw = (form.participant_count.data or "").strip()
    participant_roster = (form.participant_roster.data or "").strip()
    resolve_message = (form.resolve_message.data or "").strip()

    invalid = False
    participant_count = None
    try:
        participant_count = int(participant_count_raw)
        if participant_count <= 0:
            raise ValueError
    except ValueError:
        form.participant_count.errors.append("참가 인원은 1명 이상의 숫자로 입력해 주세요.")
        invalid = True

    if not clan_name:
        form.clan_name.errors.append("클랜명을 입력해 주세요.")
        invalid = True
    if not participant_roster:
        form.participant_roster.errors.append("참가 인원 명단을 입력해 주세요.")
        invalid = True
    if not resolve_message:
        form.resolve_message.errors.append("각오 한마디를 입력해 주세요.")
        invalid = True

    payload = {
        "clan_name": clan_name,
        "participant_count": participant_count,
        "participant_roster": participant_roster,
        "resolve_message": resolve_message,
    }
    return payload, invalid

def _moneyleague_comments_collection(registration_id):
    collection = _moneyleague_registration_collection()
    if not collection:
        return None
    return collection.document(registration_id).collection("comments")

def _client_ip_prefix():
    forwarded_for = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    ip = forwarded_for or (request.remote_addr or "").strip()
    if not ip:
        return ""
    if "." in ip:
        parts = ip.split(".")
        if len(parts) >= 2:
            return f"{parts[0]}.{parts[1]}"
        return ip
    if ":" in ip:
        parts = [p for p in ip.split(":") if p]
        if len(parts) >= 2:
            return f"{parts[0]}:{parts[1]}"
        return ip
    return ip

BLOCKED_REGISTRATION_IP_PREFIXES = {
    "115.161", "175.202", "121.190", "122.32", "223.33", "223.62",
    "39.7", "110.70", "175.223", "175.252", "210.125", "211.246",
    "114.200", "117.111", "211.36",
}

def _is_blocked_registration_ip_prefix(ip_prefix):
    if not ip_prefix:
        return False
    return ip_prefix in BLOCKED_REGISTRATION_IP_PREFIXES

def _save_moneyleague_screenshot(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_image(file_storage.filename):
        return None
    original_name = secure_filename(file_storage.filename)
    _, ext = os.path.splitext(original_name)
    ext = (ext or "").lower() or ".png"
    filename = f"mreg_{int(datetime.utcnow().timestamp())}_{uuid.uuid4().hex[:8]}{ext}"
    save_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'moneyleague_registrations')
    os.makedirs(save_dir, exist_ok=True)
    file_storage.save(os.path.join(save_dir, filename))
    return os.path.join('uploads', 'moneyleague_registrations', filename)

def _get_moneyleague_comments(registration_id):
    comments = []
    collection = _moneyleague_comments_collection(registration_id)
    if not collection:
        return comments
    try:
        query = collection.order_by("created_at", direction=firestore.Query.ASCENDING)
        for doc in query.stream():
            data = doc.to_dict() or {}
            created_at = data.get("created_at")
            created_at_display = "-"
            if hasattr(created_at, "strftime"):
                created_at_display = created_at.strftime("%Y-%m-%d %H:%M")
            author_name = data.get("author_name", "익명")
            author_ip_prefix = data.get("author_ip_prefix", "")
            author_display = data.get("author_display")
            if not author_display:
                author_display = f"{author_name} ({author_ip_prefix})" if author_ip_prefix else author_name
            comments.append({
                "id": doc.id,
                "content": data.get("content", ""),
                "author_id": data.get("author_id"),
                "author_name": author_name,
                "author_ip_prefix": author_ip_prefix,
                "author_display": author_display,
                "created_at_display": created_at_display,
            })
    except Exception as e:
        print(f"_get_moneyleague_comments error: {e}")
    return comments

@app.route("/moneyleague/registrations")
def moneyleague_registration_board():
    posts = []
    load_error = None

    collection = _moneyleague_registration_collection()
    if not collection:
        load_error = "현재 접수 게시판을 불러올 수 없습니다. 잠시 후 다시 시도해 주세요."
    else:
        try:
            query = collection.order_by("created_at", direction=firestore.Query.DESCENDING)
            for doc in query.stream():
                posts.append(_format_moneyleague_registration(doc))
        except Exception as e:
            print(f"moneyleague_registration_board error: {e}")
            load_error = "접수 게시판을 불러오는 중 오류가 발생했습니다."

    return render_template(
        "moneyleague_registration_board.html",
        posts=posts,
        load_error=load_error,
        registration_open=_is_moneyleague_registration_open(),
    )

@app.route("/moneyleague/registrations/new", methods=["GET", "POST"])
def moneyleague_registration_new():
    if not _is_moneyleague_registration_open():
        flash("머니리그 접수가 마감되어 현재는 열람만 가능합니다.", "info")
        return redirect(url_for("moneyleague_registration_board"))

    form = MoneyLeagueRegistrationForm()

    if form.validate_on_submit():
        payload, invalid = _extract_moneyleague_registration_payload(form)

        if not invalid:
            collection = _moneyleague_registration_collection()
            if not collection:
                form.clan_name.errors.append("Firebase 연결 상태를 확인해 주세요.")
            else:
                try:
                    requester_ip_prefix = _client_ip_prefix()
                    if _is_blocked_registration_ip_prefix(requester_ip_prefix):
                        form.clan_name.errors.append("해당 통신망에서는 접수 글 작성이 제한됩니다.")
                        return render_template("moneyleague_registration_create.html", form=form)

                    author_id = None
                    author_name = ""
                    if current_user.is_authenticated:
                        author_id = current_user.id
                        author_name = (current_user.username or "").strip() or "회원"
                    else:
                        author_name = (form.author_nickname.data or "").strip()
                        if not author_name:
                            form.author_nickname.errors.append("비로그인 작성 시 닉네임을 입력해 주세요.")
                            invalid = True
                        author_name = author_name[:20]

                    if invalid:
                        return render_template("moneyleague_registration_create.html", form=form)

                    screenshot = form.clan_screenshot.data
                    screenshot_path = _save_moneyleague_screenshot(screenshot)
                    if not screenshot_path:
                        form.clan_screenshot.errors.append("게임 내 클랜 페이지 스크린샷을 업로드해 주세요.")
                        return render_template("moneyleague_registration_create.html", form=form)

                    author_ip_prefix = requester_ip_prefix
                    author_display = f"{author_name} ({author_ip_prefix})" if author_ip_prefix else author_name
                    payload.update({
                        "author_id": author_id,
                        "author_name": author_name,
                        "author_ip_prefix": author_ip_prefix,
                        "author_display": author_display,
                        "clan_screenshot_path": screenshot_path,
                        "created_at": datetime.utcnow(),
                    })
                    collection.add(payload)
                    return redirect(url_for("moneyleague_registration_board"))
                except Exception as e:
                    print(f"moneyleague_registration_new error: {e}")
                    form.clan_name.errors.append("등록 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")

    return render_template("moneyleague_registration_create.html", form=form)

@app.route("/moneyleague/registrations/<registration_id>")
def moneyleague_registration_detail(registration_id):
    _, post = _get_moneyleague_registration_or_404(registration_id)
    comments = _get_moneyleague_comments(registration_id)
    can_manage = (
        current_user.is_authenticated
        and str(post.get("author_id")) == str(current_user.id)
    )
    return render_template(
        "moneyleague_registration_detail.html",
        post=post,
        comments=comments,
        can_manage=can_manage,
        registration_open=_is_moneyleague_registration_open(),
    )

@app.route("/moneyleague/registrations/<registration_id>/edit", methods=["GET", "POST"])
@login_required
def moneyleague_registration_edit(registration_id):
    if not _is_moneyleague_registration_open():
        flash("머니리그 접수가 마감되어 수정이 불가합니다.", "info")
        return redirect(url_for("moneyleague_registration_detail", registration_id=registration_id))

    doc, post = _get_moneyleague_registration_or_404(registration_id)
    if str(post.get("author_id")) != str(current_user.id):
        abort(403)

    if request.method == "GET":
        form = MoneyLeagueRegistrationForm(data={
            "clan_name": post.get("clan_name"),
            "participant_count": str(post.get("participant_count") or ""),
            "participant_roster": post.get("participant_roster"),
            "resolve_message": post.get("resolve_message"),
        })
    else:
        form = MoneyLeagueRegistrationForm()

    if form.validate_on_submit():
        payload, invalid = _extract_moneyleague_registration_payload(form)
        if not invalid:
            try:
                screenshot = form.clan_screenshot.data
                screenshot_path = _save_moneyleague_screenshot(screenshot)
                if screenshot_path:
                    payload["clan_screenshot_path"] = screenshot_path
                doc.reference.set(payload, merge=True)
                return redirect(url_for("moneyleague_registration_detail", registration_id=registration_id))
            except Exception as e:
                print(f"moneyleague_registration_edit error: {e}")
                form.clan_name.errors.append("수정 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")

    return render_template(
        "moneyleague_registration_edit.html",
        form=form,
        registration_id=registration_id,
    )

@app.route("/moneyleague/registrations/<registration_id>/delete", methods=["POST"])
@login_required
def moneyleague_registration_delete(registration_id):
    if not _is_moneyleague_registration_open():
        flash("머니리그 접수가 마감되어 삭제가 불가합니다.", "info")
        return redirect(url_for("moneyleague_registration_detail", registration_id=registration_id))

    doc, post = _get_moneyleague_registration_or_404(registration_id)
    if str(post.get("author_id")) != str(current_user.id):
        abort(403)
    doc.reference.delete()
    return redirect(url_for("moneyleague_registration_board"))

@app.route("/moneyleague/registrations/<registration_id>/comments", methods=["POST"])
def moneyleague_registration_add_comment(registration_id):
    if not _is_moneyleague_registration_open():
        flash("머니리그 접수가 마감되어 댓글 작성이 불가합니다.", "info")
        return redirect(url_for("moneyleague_registration_detail", registration_id=registration_id))

    _, post = _get_moneyleague_registration_or_404(registration_id)
    content = (request.form.get("content") or "").strip()
    if not content:
        return redirect(url_for("moneyleague_registration_detail", registration_id=registration_id))

    nickname = ""
    author_id = None
    if current_user.is_authenticated:
        nickname = (current_user.username or "").strip() or "회원"
        author_id = current_user.id
    else:
        nickname = (request.form.get("nickname") or "").strip()
        if not nickname:
            return redirect(url_for("moneyleague_registration_detail", registration_id=registration_id))
        nickname = nickname[:20]

    ip_prefix = _client_ip_prefix()
    author_display = f"{nickname} ({ip_prefix})" if ip_prefix else nickname

    collection = _moneyleague_comments_collection(registration_id)
    if not collection:
        abort(503)

    payload = {
        "content": content[:1000],
        "author_id": author_id,
        "author_name": nickname,
        "author_ip_prefix": ip_prefix,
        "author_display": author_display,
        "created_at": datetime.utcnow(),
    }
    collection.add(payload)
    clan_name = re.sub(r"\s+", " ", str(post.get("clan_name") or "머니리그 접수 글")).strip()
    if len(clan_name) > 34:
        clan_name = clan_name[:34] + "…"
    try:
        _create_notifications(
            [post.get("author_id")],
            "moneyleague_comment",
            f"{nickname}님이 ‘{clan_name}’ 접수 글에 댓글을 남겼습니다.",
            url_for("moneyleague_registration_detail", registration_id=registration_id, _anchor="comments"),
            actor_id=author_id,
        )
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Money league comment notification failed: {e}")
    return redirect(url_for("moneyleague_registration_detail", registration_id=registration_id))

@app.route("/moneyleague/registrations/<registration_id>/comments/<comment_id>/delete", methods=["POST"])
@login_required
def moneyleague_registration_delete_comment(registration_id, comment_id):
    if not _is_moneyleague_registration_open():
        flash("머니리그 접수가 마감되어 댓글 삭제가 불가합니다.", "info")
        return redirect(url_for("moneyleague_registration_detail", registration_id=registration_id))

    _get_moneyleague_registration_or_404(registration_id)
    collection = _moneyleague_comments_collection(registration_id)
    if not collection:
        abort(503)

    comment_ref = collection.document(comment_id)
    comment_doc = comment_ref.get()
    if not comment_doc.exists:
        abort(404)
    comment_data = comment_doc.to_dict() or {}
    if str(comment_data.get("author_id")) != str(current_user.id):
        abort(403)

    comment_ref.delete()
    return redirect(url_for("moneyleague_registration_detail", registration_id=registration_id))

@app.route("/board")
def board():
    return redirect(url_for("community", tab="free"))


@app.route("/player-reviews")
@app.route("/community")
def community():
    active_board = (
        "review"
        if request.path == "/player-reviews"
        else _normalize_board_type(request.args.get("tab", "free"))
    )
    q = request.args.get("q", "").strip()
    if active_board == "review":
        review_position = request.args.get("position", "").strip().upper()
        if review_position not in PLAYER_REVIEW_POSITIONS:
            review_position = ""

        review_min_rating = request.args.get("min_rating", "").strip()
        if review_min_rating not in {
            "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"
        }:
            review_min_rating = ""

        review_posts = _all_home_review_activity()
        if q:
            normalized_query = _normalize_filter_text(q)
            review_posts = [
                review for review in review_posts
                if normalized_query in _normalize_filter_text(" ".join([
                    str(review.get("title") or ""),
                    str(review.get("player_name") or ""),
                    str(review.get("player_class") or ""),
                    str(review.get("username") or ""),
                    str(review.get("review_text") or ""),
                    str(review.get("excerpt") or ""),
                    str(review.get("kind_label") or ""),
                ]))
            ]

        if review_position:
            review_posts = [
                review for review in review_posts
                if str(review.get("player_position") or "").strip().upper()
                == review_position
            ]

        if review_min_rating:
            minimum_rating = float(review_min_rating)
            filtered_review_posts = []
            for review in review_posts:
                try:
                    average_rating = float(review.get("average_rating"))
                except (TypeError, ValueError):
                    continue
                if average_rating >= minimum_rating:
                    filtered_review_posts.append(review)
            review_posts = filtered_review_posts

        review_per_page = 20
        review_total = len(review_posts)
        review_total_pages = max(
            1,
            math.ceil(review_total / review_per_page),
        )
        review_page = max(1, request.args.get("page", 1, type=int))
        review_page = min(review_page, review_total_pages)
        review_start = (review_page - 1) * review_per_page
        review_posts = review_posts[
            review_start:review_start + review_per_page
        ]
        page_start = max(1, review_page - 2)
        page_end = min(review_total_pages, review_page + 2)
        review_page_numbers = list(range(page_start, page_end + 1))
        review_is_filtered = bool(
            q or review_position or review_min_rating or review_page > 1
        )

        return render_template(
            "board.html",
            posts=[],
            review_posts=review_posts,
            review_total=review_total,
            review_page=review_page,
            review_total_pages=review_total_pages,
            review_page_numbers=review_page_numbers,
            q=q,
            review_position=review_position,
            review_min_rating=review_min_rating,
            review_positions=PLAYER_REVIEW_POSITIONS,
            boards=COMMUNITY_BOARDS,
            active_board=active_board,
            can_write_board=False,
            sidebar=_community_sidebar_context(),
            canonical_url=_canonical("/player-reviews"),
            robots_meta="noindex,follow" if review_is_filtered else "index,follow",
            meta_description="FC모바일 선수리뷰를 포지션과 별점으로 검색하고, 실제 이용자들의 사용 후기와 평가를 확인하세요.",
            og_title="FC모바일 선수리뷰, 사용 후기 | 피모북",
            og_description="FC모바일 선수리뷰, 실제 사용 후기, 평점과 장단점을 확인하세요.",
        )

    post_query = Post.query.filter(Post.board_type == active_board)
    if q:
        post_query = post_query.filter(
            (Post.title.ilike(f"%{q}%")) |
            (Post.content.ilike(f"%{q}%"))
        )
    post_per_page = 20
    post_total = post_query.count()
    post_total_pages = max(1, math.ceil(post_total / post_per_page))
    post_page = max(1, request.args.get("page", 1, type=int))
    post_page = min(post_page, post_total_pages)
    posts = (
        post_query
        .order_by(Post.is_pinned.desc(), Post.created_at.desc())
        .offset((post_page - 1) * post_per_page)
        .limit(post_per_page)
        .all()
    )
    post_page_start = max(1, post_page - 2)
    post_page_end = min(post_total_pages, post_page + 2)
    return render_template(
        "board.html",
        posts=posts,
        review_posts=[],
        post_total=post_total,
        post_page=post_page,
        post_total_pages=post_total_pages,
        post_page_numbers=list(range(post_page_start, post_page_end + 1)),
        q=q,
        boards=COMMUNITY_BOARDS,
        active_board=active_board,
        can_write_board=(active_board != "notice" or _is_admin_user()),
        sidebar=_community_sidebar_context(),
    )

@app.route("/board/new", methods=["GET", "POST"])
@login_required
def new_post():
    form = PostForm()
    active_board = _normalize_board_type(request.values.get("board_type") or request.args.get("tab"))
    if active_board == "review":
        flash("선수 리뷰는 선수 상세 페이지에서 작성할 수 있습니다.", "info")
        return redirect(url_for("community", tab="review"))
    if active_board == "notice" and not _is_admin_user():
        flash("공지사항은 관리자만 작성할 수 있습니다.", "danger")
        return redirect(url_for("community", tab="notice"))
    if form.validate_on_submit():  # CSRF + 폼 검증
        title = form.title.data
        content = form.content.data
        active_board = _normalize_board_type(request.form.get("board_type"))
        if _is_admin_user() and request.form.get("make_notice") == "1":
            active_board = "notice"
        if active_board == "notice" and not _is_admin_user():
            flash("공지사항은 관리자만 작성할 수 있습니다.", "danger")
            return redirect(url_for("community", tab="notice"))

        poll_question, poll_options, poll_error = _poll_payload_from_request()
        if poll_error:
            flash(poll_error, "danger")
            return render_template(
                "create_post.html",
                form=form,
                boards=COMMUNITY_BOARDS,
                active_board=active_board,
                poll_question=request.form.get("poll_question", ""),
                poll_options=request.form.getlist("poll_options"),
                poll_enabled=True,
            )

        image_filename = _save_uploaded_post_image(form.image.data)

        new_post = Post(
            title=title,
            content=content,
            author_id=current_user.id,
            image_filename=image_filename,
            board_type=active_board,
            is_pinned=(
                active_board == "notice"
                and _is_admin_user()
                and request.form.get("is_pinned") == "1"
            ),
            poll_question=poll_question,
        )
        db.session.add(new_post)
        db.session.flush()
        for position, option_text in enumerate(poll_options):
            db.session.add(PollOption(
                post_id=new_post.id,
                text=option_text,
                position=position,
            ))
        db.session.commit()
        flash("글이 작성되었습니다.", "success")
        return redirect(url_for("community", tab=active_board))
    return render_template("create_post.html", form=form, boards=COMMUNITY_BOARDS, active_board=active_board)


@app.route("/board/<int:post_id>")
def post_detail(post_id):
    post = Post.query.get_or_404(post_id)
    viewed_post_id_list = [
        int(value)
        for value in session.get("viewed_post_ids", [])
        if str(value).isdigit()
    ]
    viewed_post_ids = set(viewed_post_id_list)
    if post.id not in viewed_post_ids:
        post.views = int(post.views or 0) + 1
        try:
            db.session.commit()
        except Exception as error:
            db.session.rollback()
            print(f"Post view count update failed for {post.id}: {error}")
        session["viewed_post_ids"] = (viewed_post_id_list + [post.id])[-200:]

    top_comments = (
        Comment.query
        .filter_by(post_id=post.id, parent_id=None)
        .order_by(Comment.created_at.asc())
        .all()
    )
    has_liked = bool(
        current_user.is_authenticated
        and PostLike.query.filter_by(post_id=post.id, user_id=current_user.id).first()
    )
    poll_option_rows = []
    poll_total_votes = 0
    selected_poll_option_id = None
    if post.poll_question:
        vote_counts = dict(
            db.session.query(PollVote.option_id, func.count(PollVote.id))
            .filter(PollVote.post_id == post.id)
            .group_by(PollVote.option_id)
            .all()
        )
        poll_total_votes = sum(int(count or 0) for count in vote_counts.values())
        if current_user.is_authenticated:
            selected_vote = PollVote.query.filter_by(
                post_id=post.id,
                user_id=current_user.id,
            ).first()
            selected_poll_option_id = selected_vote.option_id if selected_vote else None
        for option in post.poll_options:
            count = int(vote_counts.get(option.id, 0))
            poll_option_rows.append({
                "id": option.id,
                "text": option.text,
                "votes": count,
                "percent": round((count / poll_total_votes) * 100) if poll_total_votes else 0,
            })
    return render_template(
        "post_detail.html",
        post=post,
        board=COMMUNITY_BOARDS.get(_normalize_board_type(post.board_type), COMMUNITY_BOARDS["free"]),
        top_comments=top_comments,
        total_comments=Comment.query.filter_by(post_id=post.id).count(),
        has_liked=has_liked,
        poll_options=poll_option_rows,
        poll_total_votes=poll_total_votes,
        selected_poll_option_id=selected_poll_option_id,
    )


@app.route("/board/<int:post_id>/vote", methods=["POST"])
@login_required
def vote_post_poll(post_id):
    post = Post.query.get_or_404(post_id)
    if not post.poll_question:
        abort(404)
    option_id = request.form.get("option_id", type=int)
    option = PollOption.query.filter_by(id=option_id, post_id=post.id).first()
    if not option:
        flash("투표 항목을 선택해주세요.", "danger")
        return redirect(url_for("post_detail", post_id=post.id, _anchor="post-poll"))

    vote = PollVote.query.filter_by(post_id=post.id, user_id=current_user.id).first()
    if vote:
        vote.option_id = option.id
    else:
        db.session.add(PollVote(
            post_id=post.id,
            option_id=option.id,
            user_id=current_user.id,
        ))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("투표 처리 중 충돌이 발생했습니다. 다시 시도해주세요.", "danger")
        return redirect(url_for("post_detail", post_id=post.id, _anchor="post-poll"))
    flash("투표가 반영되었습니다.", "success")
    return redirect(url_for("post_detail", post_id=post.id, _anchor="post-poll"))


@app.route("/board/<int:post_id>/like", methods=["POST"])
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    existing = PostLike.query.filter_by(
        post_id=post.id,
        user_id=current_user.id,
    ).first()
    if existing:
        db.session.delete(existing)
        post.likes = max(0, int(post.likes or 0) - 1)
        liked = False
    else:
        db.session.add(PostLike(post_id=post.id, user_id=current_user.id))
        post.likes = int(post.likes or 0) + 1
        liked = True

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        liked = bool(
            PostLike.query.filter_by(
                post_id=post.id,
                user_id=current_user.id,
            ).first()
        )
        post = db.session.get(Post, post.id)

    payload = {"likes": int(post.likes or 0), "liked": liked}
    if (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best == "application/json"
    ):
        return jsonify(payload)
    flash("좋아요를 눌렀습니다." if liked else "좋아요를 취소했습니다.", "success")
    return redirect(url_for("post_detail", post_id=post.id))

@app.route("/board/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author_id != current_user.id and not _is_admin_user():
        flash("수정 권한이 없습니다.", "danger")
        return redirect(url_for("post_detail", post_id=post_id))

    form = PostForm(obj=post)
    if form.validate_on_submit():
        next_board = _normalize_board_type(request.form.get("board_type") or post.board_type)
        if _is_admin_user() and request.form.get("make_notice") == "1":
            next_board = "notice"
        if next_board == "review":
            flash("리뷰게시판에는 선수 리뷰만 표시할 수 있습니다.", "danger")
            return redirect(url_for("edit_post", post_id=post_id))
        if next_board == "notice" and not _is_admin_user():
            flash("공지사항은 관리자만 작성할 수 있습니다.", "danger")
            return redirect(url_for("post_detail", post_id=post_id))

        poll_question, poll_options, poll_error = _poll_payload_from_request()
        if poll_error:
            flash(poll_error, "danger")
            return render_template(
                "edit_post.html",
                form=form,
                post=post,
                boards=COMMUNITY_BOARDS,
                active_board=next_board,
                poll_question=request.form.get("poll_question", ""),
                poll_options=request.form.getlist("poll_options"),
                poll_enabled=True,
                poll_has_votes=PollVote.query.filter_by(post_id=post.id).first() is not None,
            )

        current_option_texts = [option.text for option in post.poll_options]
        poll_changed = (
            (post.poll_question or None) != poll_question
            or current_option_texts != poll_options
        )
        poll_has_votes = PollVote.query.filter_by(post_id=post.id).first() is not None
        if poll_changed and poll_has_votes:
            flash("이미 참여자가 있는 투표는 질문이나 항목을 변경·삭제할 수 없습니다.", "danger")
            return redirect(url_for("edit_post", post_id=post.id))

        post.title = form.title.data
        post.content = form.content.data
        post.board_type = next_board
        post.is_pinned = bool(
            next_board == "notice"
            and _is_admin_user()
            and request.form.get("is_pinned") == "1"
        )
        if form.image.data:
            new_image_filename = _save_uploaded_post_image(form.image.data)
            if new_image_filename:
                post.image_filename = new_image_filename
        elif request.form.get("remove_image") == "1":
            post.image_filename = None
        if poll_changed:
            _save_post_poll(post, poll_question, poll_options)
        db.session.commit()
        flash("게시글이 수정되었습니다.", "success")
        return redirect(url_for("post_detail", post_id=post_id))

    return render_template(
        "edit_post.html",
        form=form,
        post=post,
        boards=COMMUNITY_BOARDS,
        active_board=_normalize_board_type(post.board_type),
        poll_question=post.poll_question or "",
        poll_options=[option.text for option in post.poll_options],
        poll_enabled=bool(post.poll_question),
        poll_has_votes=PollVote.query.filter_by(post_id=post.id).first() is not None,
    )

@app.route("/board/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author_id != current_user.id and not _is_admin_user():
        flash("삭제 권한이 없습니다.", "danger")
        return redirect(url_for("post_detail", post_id=post_id))

    board_type = _normalize_board_type(post.board_type)
    # 댓글 포함 삭제
    Comment.query.filter_by(post_id=post.id).delete()
    PostLike.query.filter_by(post_id=post.id).delete()
    PollVote.query.filter_by(post_id=post.id).delete()
    PollOption.query.filter_by(post_id=post.id).delete()
    db.session.delete(post)
    db.session.commit()
    flash("게시글이 삭제되었습니다.", "info")
    return redirect(url_for("community", tab=board_type))

@app.route("/comment/<int:comment_id>/delete", methods=["POST"])
@login_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.author_id != current_user.id and not _is_admin_user():
        flash("삭제 권한이 없습니다.", "danger")
        return redirect(url_for("post_detail", post_id=comment.post_id))

    post_id = comment.post_id
    db.session.delete(comment)
    db.session.commit()
    flash("댓글이 삭제되었습니다.", "info")
    return redirect(url_for("post_detail", post_id=post_id, _anchor="comments"))

@app.route("/search_post")
def search_post():
    q = request.args.get("q", "").strip()
    active_board = _normalize_board_type(request.args.get("tab", "free"))
    if active_board == "review":
        return redirect(url_for("community", tab="review", q=q))
    if not q:
        return redirect(url_for("community", tab=active_board))

    return redirect(url_for("community", tab=active_board, q=q))


@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    post = Post.query.get_or_404(post_id)
    rate_limit_message = _comment_rate_limit_message(current_user.id)
    if rate_limit_message:
        flash(rate_limit_message, "danger")
        return redirect(url_for("post_detail", post_id=post_id, _anchor="comments"))

    content = request.form.get('content', '').strip()
    if not content:
        flash("댓글 내용을 입력해주세요.", "danger")
        return redirect(url_for('post_detail', post_id=post_id))
    if len(content) > COMMENT_MAX_LENGTH:
        flash(f"댓글은 {COMMENT_MAX_LENGTH:,}자 이내로 작성해주세요.", "danger")
        return redirect(url_for("post_detail", post_id=post_id, _anchor="comments"))

    parent_id = request.form.get("parent_id", type=int)
    parent = None
    notification_parent = None
    if parent_id:
        parent = Comment.query.filter_by(id=parent_id, post_id=post.id).first()
        if not parent:
            flash("답글을 달 댓글을 찾을 수 없습니다.", "danger")
            return redirect(url_for('post_detail', post_id=post_id))
        notification_parent = parent
        if parent.parent_id:
            parent = parent.parent or Comment.query.filter_by(
                id=parent.parent_id,
                post_id=post.id,
            ).first()

    comment = Comment(content=content, author=current_user, post_id=post_id, parent_id=parent.id if parent else None)
    db.session.add(comment)
    post_title = re.sub(r"\s+", " ", post.title or "게시글").strip()
    if len(post_title) > 34:
        post_title = post_title[:34] + "…"
    target_url = url_for("post_detail", post_id=post.id, _anchor="comments")
    if parent:
        _create_notifications(
            [notification_parent.author_id if notification_parent else parent.author_id, post.author_id],
            "post_reply",
            f"{current_user.username}님이 ‘{post_title}’ 게시글의 댓글에 답글을 남겼습니다.",
            target_url,
            actor_id=current_user.id,
        )
    else:
        _create_notifications(
            [post.author_id],
            "post_comment",
            f"{current_user.username}님이 ‘{post_title}’ 게시글에 댓글을 남겼습니다.",
            target_url,
            actor_id=current_user.id,
        )
    db.session.commit()
    return redirect(url_for("post_detail", post_id=post_id, _anchor=f"comment-{comment.id}"))


@app.route("/notifications")
@login_required
def notifications():
    rows = (
        Notification.query
        .filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(100)
        .all()
    )
    for item in rows:
        item.time_display = _notification_time_display(item.created_at)
    unread_count = Notification.query.filter_by(user_id=current_user.id, read_at=None).count()
    return render_template(
        "notifications.html",
        notifications=rows,
        unread_count=unread_count,
        robots_meta="noindex,nofollow",
    )


@app.route("/notifications/<int:notification_id>/open")
@login_required
def open_notification(notification_id):
    item = Notification.query.filter_by(id=notification_id, user_id=current_user.id).first_or_404()
    if item.read_at is None:
        item.read_at = datetime.utcnow()
        db.session.commit()
    return redirect(_notification_target_url(item.target_url))


@app.route("/notifications/read-all", methods=["POST"])
@login_required
def read_all_notifications():
    Notification.query.filter_by(user_id=current_user.id, read_at=None).update(
        {"read_at": datetime.utcnow()},
        synchronize_session=False,
    )
    db.session.commit()
    flash("모든 알림을 확인했습니다.", "success")
    return redirect(url_for("notifications"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        if not username:
            flash("이름을 입력해주세요.", "danger")
            return redirect(url_for("profile"))
        if len(username) > 100:
            flash("이름은 100자 이내로 입력해주세요.", "danger")
            return redirect(url_for("profile"))
        existing = User.query.filter(
            func.lower(User.username) == username.lower(),
            User.id != current_user.id,
        ).first()
        if existing:
            flash("이미 사용 중인 이름입니다.", "danger")
            return redirect(url_for("profile"))

        current_user.username = username
        current_user.username_confirmed = True
        db.session.commit()
        flash("프로필 이름이 변경되었습니다.", "success")
        return redirect(url_for("profile"))

    reviews = _get_reviews_by_user(current_user.id)
    return render_template(
        "profile.html",
        profile_user=current_user,
        reviews=reviews,
        profile_stats=_profile_activity_summary(current_user, reviews),
        own_profile=True,
        monthly_points=_review_point_total(current_user.id, _month_key()),
        all_time_points=_review_point_total(current_user.id),
    )


@app.route("/profile/<int:user_id>")
def public_profile(user_id):
    profile_user = User.query.get_or_404(user_id)
    reviews = _get_reviews_by_user(profile_user.id)
    return render_template(
        "profile.html",
        profile_user=profile_user,
        reviews=reviews,
        profile_stats=_profile_activity_summary(profile_user, reviews),
        own_profile=current_user.is_authenticated and current_user.id == profile_user.id,
        monthly_points=_review_point_total(profile_user.id, _month_key()),
        all_time_points=_review_point_total(profile_user.id),
    )


@app.route("/account/delete", methods=["GET", "POST"])
@login_required
def delete_account():
    if request.method == "GET":
        return render_template(
            "delete_account.html",
            error=None,
            robots_meta="noindex,nofollow",
        )

    confirm_email = _normalize_email(request.form.get("confirm_email"))
    confirm_text = (request.form.get("confirm_text") or "").strip()
    confirm_checkbox = request.form.get("confirm_delete") == "yes"
    current_password = request.form.get("current_password") or ""

    error = None
    if confirm_email != _normalize_email(current_user.email):
        error = "계정 이메일이 일치하지 않습니다."
    elif confirm_text != "회원탈퇴":
        error = "확인 문구에 ‘회원탈퇴’를 정확히 입력해주세요."
    elif not confirm_checkbox:
        error = "탈퇴 안내 확인에 체크해주세요."
    elif current_user.password_hash and not current_user.check_password(
        current_password
    ):
        error = "현재 비밀번호가 올바르지 않습니다."

    if error:
        return render_template(
            "delete_account.html",
            error=error,
            robots_meta="noindex,nofollow",
        ), 400

    user = current_user._get_current_object()
    user_id = user.id
    if not _delete_remote_player_reviews_for_user(user_id):
        return render_template(
            "delete_account.html",
            error=(
                "선수 리뷰 삭제 중 문제가 발생했습니다. "
                "계정은 삭제되지 않았으니 잠시 후 다시 시도해주세요."
            ),
            robots_meta="noindex,nofollow",
        ), 503

    try:
        _delete_local_user_account(user, purge_content=False)
    except Exception as error:
        db.session.rollback()
        app.logger.exception(
            "Local account deletion failed for user %s: %s",
            user_id,
            error,
        )
        return render_template(
            "delete_account.html",
            error=(
                "회원탈퇴 처리 중 문제가 발생했습니다. "
                "계정은 삭제되지 않았으니 잠시 후 다시 시도해주세요."
            ),
            robots_meta="noindex,nofollow",
        ), 500

    logout_user()
    session.clear()
    return render_template(
        "account_deleted.html",
        robots_meta="noindex,nofollow",
    )


@app.route("/community/rankings")
def review_rankings():
    ranking_tabs = {
        "current": {
            "label": "이번 시즌",
            "title": "이번 시즌 전체 랭킹",
            "period": _month_key(),
            "rows": _review_point_rankings(_month_key(), limit=None),
        },
        "previous": {
            "label": "기존 랭킹",
            "title": "기존 랭킹",
            "period": _previous_month_key(),
            "rows": _review_point_rankings(_previous_month_key(), limit=None),
        },
        "all": {
            "label": "전체 기간",
            "title": "전체 기간 랭킹",
            "period": "누적 포인트",
            "rows": _review_point_rankings(None, limit=None),
        },
    }
    active_tab = request.args.get("tab", "current").strip().lower()
    if active_tab not in ranking_tabs:
        active_tab = "current"

    return render_template(
        "review_rankings.html",
        ranking_tabs=ranking_tabs,
        active_tab=active_tab,
        active_ranking=ranking_tabs[active_tab],
        boards=COMMUNITY_BOARDS,
    )


@app.route("/secret/admin/setup", methods=["GET", "POST"])
@login_required
def admin_setup():
    if _is_admin_user():
        return redirect(url_for("admin_points"))

    setup_password = _admin_setup_password()
    if request.method == "POST":
        if not setup_password:
            flash("관리자 설정 비밀번호가 서버에 설정되어 있지 않습니다.", "danger")
            return redirect(url_for("admin_setup"))
        password = request.form.get("password", "").strip()
        if password != setup_password:
            flash("관리자 설정 비밀번호가 올바르지 않습니다.", "danger")
            return redirect(url_for("admin_setup"))

        current_user.is_admin = True
        db.session.commit()
        flash("관리자로 등록되었습니다.", "success")
        return redirect(url_for("admin_points"))

    return render_template("admin_setup.html", setup_enabled=bool(setup_password))


@app.route("/admin/points", methods=["GET", "POST"])
@login_required
def admin_points():
    if not _is_admin_user():
        abort(403)

    if request.method == "POST":
        target_user_id = request.form.get("user_id", type=int)
        points = request.form.get("points", type=int)
        reason = request.form.get("reason", "").strip()
        target_user = db.session.get(User, target_user_id) if target_user_id else None

        if not target_user:
            flash("포인트를 받을 회원을 찾을 수 없습니다.", "danger")
            return redirect(url_for("admin_points"))
        if not points or points <= 0:
            flash("증정 포인트는 1점 이상이어야 합니다.", "danger")
            return redirect(url_for("admin_points"))
        if points > 1000000:
            flash("한 번에 증정할 수 있는 포인트는 1,000,000점까지입니다.", "danger")
            return redirect(url_for("admin_points"))

        _award_admin_points(target_user, points, reason)
        flash(f"{target_user.username}님에게 {points}점을 증정했습니다.", "success")
        return redirect(url_for("admin_points", q=target_user.username))

    q = request.args.get("q", "").strip()
    user_query = User.query
    if q:
        user_query = user_query.filter(
            (User.username.ilike(f"%{q}%")) |
            (User.email.ilike(f"%{q}%"))
        )
    total_user_count = User.query.count()
    users = user_query.order_by(User.id.asc()).all()
    user_ids = [user.id for user in users]
    post_counts = {}
    comment_counts = {}
    review_comment_counts = {}
    if user_ids:
        post_counts = dict(
            db.session.query(Post.author_id, func.count(Post.id))
            .filter(Post.author_id.in_(user_ids))
            .group_by(Post.author_id)
            .all()
        )
        comment_counts = dict(
            db.session.query(Comment.author_id, func.count(Comment.id))
            .filter(Comment.author_id.in_(user_ids))
            .group_by(Comment.author_id)
            .all()
        )
        review_comment_counts = dict(
            db.session.query(PlayerReviewComment.author_id, func.count(PlayerReviewComment.id))
            .filter(PlayerReviewComment.author_id.in_(user_ids))
            .group_by(PlayerReviewComment.author_id)
            .all()
        )
    user_activity_counts = {
        user.id: {
            "posts": post_counts.get(user.id, 0),
            "comments": comment_counts.get(user.id, 0),
            "review_comments": review_comment_counts.get(user.id, 0),
        }
        for user in users
    }
    recent_grants = (
        ReviewPointLedger.query
        .filter_by(source="admin_grant")
        .order_by(ReviewPointLedger.created_at.desc())
        .limit(20)
        .all()
    )
    return render_template(
        "admin_points.html",
        users=users,
        q=q,
        recent_grants=recent_grants,
        user_count=len(users),
        total_user_count=total_user_count,
        user_activity_counts=user_activity_counts,
        delete_password_required=bool(
            app.config.get("FIMOBOOK_ADMIN_USER_DELETE_PASSWORD", "").strip()
        ),
    )


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required
def admin_delete_user(user_id):
    if not _is_admin_user():
        abort(403)

    target_user = db.session.get(User, user_id)
    if not target_user:
        flash("삭제할 회원을 찾을 수 없습니다.", "danger")
        return redirect(url_for("admin_points"))
    if target_user.id == current_user.id:
        flash("현재 로그인한 관리자 계정은 직접 삭제할 수 없습니다.", "danger")
        return redirect(url_for("admin_points", q=target_user.username))

    delete_password = request.form.get("delete_password", "").strip()
    confirm_checkbox = request.form.get("confirm_delete") == "yes"
    purge_content = request.form.get("purge_content") == "yes"

    configured_delete_password = app.config.get(
        "FIMOBOOK_ADMIN_USER_DELETE_PASSWORD", ""
    ).strip()
    if configured_delete_password and delete_password != configured_delete_password:
        flash("회원 삭제 비밀번호가 올바르지 않습니다.", "danger")
        return redirect(url_for("admin_points", q=target_user.username))
    if not confirm_checkbox:
        flash("회원 삭제 2단 확인을 완료해주세요.", "danger")
        return redirect(url_for("admin_points", q=target_user.username))

    deleted_label = target_user.username or target_user.email or f"회원 {target_user.id}"
    _delete_local_user_account(target_user, purge_content=purge_content)
    if purge_content:
        flash(f"{deleted_label} 회원과 작성한 게시글·댓글·답글을 모두 삭제했습니다.", "info")
    else:
        flash(f"{deleted_label} 회원을 삭제했습니다. 기존 게시글과 댓글은 익명 처리되었습니다.", "info")
    return redirect(url_for("admin_points"))


EMAIL_VERIFICATION_SALT = "fimobook-email-verification-v1"


def _normalize_email(value):
    return (value or "").strip().lower()


def _safe_auth_next_url(value):
    next_url = (value or "").strip()
    if not next_url:
        return ""
    parsed_next = urlparse(next_url)
    if parsed_next.netloc or not next_url.startswith("/"):
        return ""
    return next_url


def _verification_serializer():
    return URLSafeTimedSerializer(app.config["SECRET_KEY"])


def _create_verification_token(user):
    return _verification_serializer().dumps(
        {
            "user_id": user.id,
            "email_digest": hashlib.sha256(
                _normalize_email(user.email).encode("utf-8")
            ).hexdigest(),
        },
        salt=EMAIL_VERIFICATION_SALT,
    )


def _verification_link(user):
    path = url_for(
        "verify_email",
        token=_create_verification_token(user),
    )
    return f"{app.config['PUBLIC_BASE_URL']}{path}"


def _send_verification_email(user):
    if not app.config.get("MAIL_USERNAME") or not app.config.get("MAIL_PASSWORD"):
        raise RuntimeError("메일 발송 계정이 설정되지 않았습니다.")
    verification_link = _verification_link(user)
    message = Message(
        subject="[피모북] 이메일 주소를 인증해주세요",
        sender=(
            app.config.get("MAIL_DEFAULT_SENDER")
            or app.config["MAIL_USERNAME"]
        ),
        recipients=[user.email],
        body=(
            f"{user.username}님, 피모북 가입을 완료하려면 아래 링크를 눌러주세요.\n\n"
            f"{verification_link}\n\n"
            "이 링크는 24시간 동안 유효합니다. 본인이 요청하지 않았다면 이 메일을 무시해주세요."
        ),
        html=render_template(
            "emails/verify_email.html",
            user=user,
            verification_link=verification_link,
            expires_hours=max(
                1,
                app.config["EMAIL_VERIFICATION_MAX_AGE"] // 3600,
            ),
        ),
    )
    mail.send(message)


def _google_email_is_verified(payload):
    value = payload.get("email_verified")
    return value is True or str(value).lower() == "true"


def _recaptcha_enabled():
    return bool(
        app.config.get("RECAPTCHA_SITE_KEY")
        and app.config.get("RECAPTCHA_SECRET_KEY")
    )


def _verify_recaptcha_response():
    if not _recaptcha_enabled():
        return True

    token = (
        request.form.get("g-recaptcha-response")
        or request.form.get("google-recaptcha-response")
        or ""
    ).strip()
    if not token:
        return False

    try:
        verification = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={
                "secret": app.config["RECAPTCHA_SECRET_KEY"],
                "response": token,
            },
            timeout=(3, 7),
        )
        verification.raise_for_status()
        result = verification.json()
    except (requests.RequestException, ValueError) as error:
        app.logger.warning("reCAPTCHA verification request failed: %s", error)
        return False

    if not result.get("success"):
        app.logger.info(
            "reCAPTCHA rejected request: %s",
            result.get("error-codes") or [],
        )
        return False

    allowed_hostnames = {
        hostname.strip().lower()
        for hostname in app.config.get(
            "RECAPTCHA_ALLOWED_HOSTNAMES",
            "",
        ).split(",")
        if hostname.strip()
    }
    verified_hostname = (result.get("hostname") or "").strip().lower()
    if allowed_hostnames and verified_hostname not in allowed_hostnames:
        app.logger.warning(
            "reCAPTCHA hostname rejected: %s",
            verified_hostname or "<missing>",
        )
        return False
    return True


def _require_recaptcha():
    if _verify_recaptcha_response():
        return True
    flash('로봇이 아님을 확인한 후 다시 시도해주세요.', 'warning')
    return False


GOOGLE_SIGNUP_SESSION_TTL = 10 * 60


def _set_pending_google_signup(payload, next_url="", existing_user=None):
    session["pending_google_signup"] = {
        "google_sub": (payload.get("sub") or "").strip(),
        "email": _normalize_email(payload.get("email")),
        "google_name": (payload.get("name") or "").strip()[:100],
        "next_url": _safe_auth_next_url(next_url),
        "existing_user_id": existing_user.id if existing_user else None,
        "issued_at": int(time.time()),
    }


def _pending_google_signup():
    pending = session.get("pending_google_signup")
    if not isinstance(pending, dict):
        return None
    try:
        age = int(time.time()) - int(pending.get("issued_at", 0))
    except (TypeError, ValueError):
        age = GOOGLE_SIGNUP_SESSION_TTL + 1
    if (
        age < 0
        or age > GOOGLE_SIGNUP_SESSION_TTL
        or not pending.get("google_sub")
        or not _normalize_email(pending.get("email"))
    ):
        session.pop("pending_google_signup", None)
        return None
    return pending


@app.route('/verify-email/<token>')
def verify_email(token):
    if current_user.is_authenticated and current_user.email_verified:
        return redirect(url_for('index'))

    try:
        payload = _verification_serializer().loads(
            token,
            salt=EMAIL_VERIFICATION_SALT,
            max_age=app.config["EMAIL_VERIFICATION_MAX_AGE"],
        )
    except SignatureExpired:
        flash('인증 링크가 만료되었습니다. 인증 메일을 다시 요청해주세요.', 'warning')
        return redirect(url_for('resend_verification'))
    except (BadSignature, TypeError, ValueError):
        flash('유효하지 않은 인증 링크입니다.', 'danger')
        return redirect(url_for('login'))

    user = db.session.get(User, payload.get("user_id"))
    expected_digest = (
        hashlib.sha256(_normalize_email(user.email).encode("utf-8")).hexdigest()
        if user
        else ""
    )
    if (
        not user
        or not secrets.compare_digest(
            expected_digest,
            str(payload.get("email_digest") or ""),
        )
    ):
        flash('유효하지 않은 인증 링크입니다.', 'danger')
        return redirect(url_for('login'))

    if not user.email_verified:
        user.email_verified = True
        user.email_verified_at = datetime.utcnow()
        db.session.commit()
    flash('이메일 인증이 완료되었습니다. 이제 로그인할 수 있습니다.', 'success')
    return redirect(url_for('login'))


@app.route('/resend-verification', methods=['GET', 'POST'])
def resend_verification():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = _normalize_email(request.form.get('email'))
        user = User.query.filter(func.lower(User.email) == email).first() if email else None
        now = datetime.utcnow()
        cooldown = app.config["EMAIL_VERIFICATION_RESEND_SECONDS"]
        can_send = bool(
            user
            and not user.email_verified
            and (
                user.verification_sent_at is None
                or (now - user.verification_sent_at).total_seconds() >= cooldown
            )
        )
        if can_send:
            try:
                _send_verification_email(user)
                user.verification_sent_at = now
                db.session.commit()
            except Exception as error:
                db.session.rollback()
                app.logger.exception("Verification email resend failed: %s", error)
        flash(
            '가입된 미인증 계정이라면 인증 메일을 보냈습니다. '
            '메일함과 스팸함을 확인해주세요.',
            'info',
        )
        return redirect(url_for('resend_verification'))
    return render_template('resend_verification.html')


@app.route('/auth/google', methods=['POST'])
def google_login():
    next_url = _safe_auth_next_url(request.form.get("next"))
    client_id = app.config.get("GOOGLE_CLIENT_ID", "")
    credential = (request.form.get("credential") or "").strip()
    if not client_id or not credential:
        flash('Google 로그인이 아직 설정되지 않았습니다.', 'warning')
        return redirect(url_for('login', next=next_url) if next_url else url_for('login'))
    if not _require_recaptcha():
        return redirect(url_for('login', next=next_url) if next_url else url_for('login'))

    try:
        payload = google_id_token.verify_oauth2_token(
            credential,
            google_auth_requests.Request(),
            client_id,
        )
    except (ValueError, GoogleAuthError) as error:
        app.logger.warning("Google ID token verification failed: %s", error)
        flash('Google 로그인 정보를 확인하지 못했습니다. 다시 시도해주세요.', 'danger')
        return redirect(url_for('login', next=next_url) if next_url else url_for('login'))

    if payload.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
        flash('Google 로그인 발급자를 확인하지 못했습니다.', 'danger')
        return redirect(url_for('login', next=next_url) if next_url else url_for('login'))

    google_sub = (payload.get("sub") or "").strip()
    email = _normalize_email(payload.get("email"))
    if not google_sub or not email or not _google_email_is_verified(payload):
        flash('인증된 Google 이메일 계정이 필요합니다.', 'danger')
        return redirect(url_for('login', next=next_url) if next_url else url_for('login'))

    user = User.query.filter_by(google_sub=google_sub).first()
    if user and not user.username_confirmed:
        _set_pending_google_signup(
            payload,
            next_url=next_url,
            existing_user=user,
        )
        return redirect(url_for('complete_google_signup'))

    if user:
        login_user(user)
        flash(f'{user.username}님, Google 계정으로 로그인했습니다.', 'success')
        return redirect(next_url or url_for('index'))

    user = User.query.filter(func.lower(User.email) == email).first()
    if user:
        if user.google_sub and user.google_sub != google_sub:
            flash('이 이메일은 다른 Google 계정에 연결되어 있습니다.', 'danger')
            return redirect(url_for('login'))
        user.google_sub = google_sub
        user.email_verified = True
        user.email_verified_at = user.email_verified_at or datetime.utcnow()
        user.username_confirmed = True
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Google 계정을 연결하지 못했습니다. 다시 시도해주세요.', 'danger')
            return redirect(url_for('login'))
        login_user(user)
        flash(f'{user.username}님, Google 계정으로 로그인했습니다.', 'success')
        return redirect(next_url or url_for('index'))

    _set_pending_google_signup(payload, next_url=next_url)
    return redirect(url_for('complete_google_signup'))


@app.route('/auth/google/complete', methods=['GET', 'POST'])
def complete_google_signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    pending = _pending_google_signup()
    if not pending:
        flash('Google 가입 정보가 만료되었습니다. 다시 로그인해주세요.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        username = (request.form.get('username') or "").strip()
        if not username or len(username) > 100:
            flash('감독명은 1자 이상 100자 이하로 입력해주세요.', 'danger')
            return render_template(
                'complete_google_signup.html',
                pending=pending,
            )

        existing_user_id = pending.get("existing_user_id")
        user = (
            db.session.get(User, int(existing_user_id))
            if existing_user_id
            else User.query.filter_by(
                google_sub=pending["google_sub"],
            ).first()
        )
        if user and user.username_confirmed:
            next_url = _safe_auth_next_url(pending.get("next_url"))
            session.pop("pending_google_signup", None)
            login_user(user)
            return redirect(next_url or url_for('index'))
        username_query = User.query.filter(
            func.lower(User.username) == username.lower()
        )
        if user:
            username_query = username_query.filter(User.id != user.id)
        if username_query.first():
            flash('이미 사용 중인 감독명입니다.', 'danger')
            return render_template(
                'complete_google_signup.html',
                pending=pending,
            )

        email = _normalize_email(pending["email"])
        if user:
            if (
                user.google_sub != pending["google_sub"]
                or _normalize_email(user.email) != email
            ):
                session.pop("pending_google_signup", None)
                flash('Google 가입 정보를 확인하지 못했습니다.', 'danger')
                return redirect(url_for('login'))
            user.username = username
            user.username_confirmed = True
            user.email_verified = True
            user.email_verified_at = user.email_verified_at or datetime.utcnow()
        else:
            email_user = User.query.filter(func.lower(User.email) == email).first()
            if email_user:
                if (
                    email_user.google_sub
                    and email_user.google_sub != pending["google_sub"]
                ):
                    session.pop("pending_google_signup", None)
                    flash('이 이메일은 다른 계정에 연결되어 있습니다.', 'danger')
                    return redirect(url_for('login'))
                user = email_user
                user.google_sub = pending["google_sub"]
                user.email_verified = True
                user.email_verified_at = user.email_verified_at or datetime.utcnow()
                user.username_confirmed = True
            else:
                user = User(
                    email=email,
                    username=username,
                    password_hash=None,
                    email_verified=True,
                    email_verified_at=datetime.utcnow(),
                    google_sub=pending["google_sub"],
                    username_confirmed=True,
                )
                db.session.add(user)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('이미 사용 중인 감독명입니다. 다른 이름을 선택해주세요.', 'danger')
            return render_template(
                'complete_google_signup.html',
                pending=pending,
            )

        next_url = _safe_auth_next_url(pending.get("next_url"))
        session.pop("pending_google_signup", None)
        login_user(user)
        flash(f'{user.username} 감독님, 가입이 완료되었습니다!', 'success')
        return redirect(next_url or url_for('index'))

    return render_template(
        'complete_google_signup.html',
        pending=pending,
    )


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        if not _require_recaptcha():
            return render_template('register.html')
        email = _normalize_email(request.form.get('email'))
        username = (request.form.get('username') or "").strip()
        password = request.form.get('password') or ""

        if not email or "@" not in email or len(email) > 100:
            flash('올바른 이메일 주소를 입력해주세요.', 'danger')
            return render_template('register.html')
        if not username or len(username) > 100:
            flash('감독명은 1자 이상 100자 이하로 입력해주세요.', 'danger')
            return render_template('register.html')
        if len(password) < 8:
            flash('비밀번호는 8자 이상으로 설정해주세요.', 'danger')
            return render_template('register.html')

        user_by_email = User.query.filter(func.lower(User.email) == email).first()
        if user_by_email:
            flash('이미 가입된 이메일 주소입니다.', 'danger')
            return render_template('register.html')

        user_by_name = User.query.filter(
            func.lower(User.username) == username.lower()
        ).first()
        if user_by_name:
            flash('이미 사용 중인 감독명입니다.', 'danger')
            return render_template('register.html')

        new_user = User(
            email=email,
            username=username,
            email_verified=False,
        )
        new_user.set_password(password)

        db.session.add(new_user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('이미 사용 중인 이메일 또는 감독명입니다.', 'danger')
            return render_template('register.html')

        try:
            _send_verification_email(new_user)
            new_user.verification_sent_at = datetime.utcnow()
            db.session.commit()
            flash(
                '회원가입이 완료되었습니다. 이메일로 보낸 인증 링크를 확인해주세요.',
                'success',
            )
        except Exception as error:
            db.session.rollback()
            app.logger.exception("Verification email send failed: %s", error)
            flash(
                '회원가입은 완료됐지만 인증 메일을 보내지 못했습니다. '
                '잠시 후 인증 메일 재전송을 이용해주세요.',
                'warning',
            )
        return redirect(url_for('login'))
    return render_template('register.html')




@app.route('/login', methods=['GET', 'POST'])
def login():
    next_url = _safe_auth_next_url(
        request.args.get("next") or request.form.get("next")
    )

    if current_user.is_authenticated:
        return redirect(next_url or url_for('index'))
    if request.method == 'POST':
        if not _require_recaptcha():
            return render_template('login.html', next_url=next_url)
        email = _normalize_email(request.form.get('email'))
        password = request.form.get('password') or ""
        user = User.query.filter(func.lower(User.email) == email).first()

        if user and user.check_password(password):
            if not user.email_verified:
                flash(
                    '이메일 인증이 필요합니다. 받은 메일의 인증 링크를 눌러주세요.',
                    'warning',
                )
                return redirect(url_for('resend_verification'))
            login_user(user)
            flash(f'{current_user.username}님, 환영합니다!', 'success')
            return redirect(next_url or url_for('index'))
        else:
            flash('이메일 또는 비밀번호가 올바르지 않습니다.', 'danger')
            return redirect(url_for('login', next=next_url) if next_url else url_for('login'))
    return render_template('login.html', next_url=next_url)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('로그아웃되었습니다.', 'info')
    return redirect(url_for('index'))


# FC Mobile 선수 특성 목록 정의
TRAITS = [
    "장거리 스로인", "강력한 프리킥", "유리몸", "강철몸", "주발 선호", "슬라이딩 태클 선호",
    "라인 브레이커", "팀 플레이어", "리더십", "화려한 터치", "얼리 크로스 선호",
    "예리한 감아차기", "화려한 개인기", "긴 패스 선호", "중거리 슛 선호", "빠른 드리블",
    "플레이메이커", "GK 공격 가담", "GK 능숙한 펀칭", "GK 멀리 던지기", "강력한 헤더",
    "GK 침착한 1:1 수비", "초장거리 스로인", "아웃사이드 슈팅", "군중 선호", "패스 마스터",
    "두 번째 활력", "화려한 걷어내기", "GK 플랫킥"
]

# 전역 변수로 선수 데이터 저장 (앱 시작 시 로드) - 이제 특성 검색에만 사용됩니다.
PLAYER_DATA = []
PLAYER_DATA_FILE = "player_data.json"
PLAYER_CLASS_MAP_FILE = os.path.join(
    app.root_path,
    "static",
    "data",
    "player_class_names.json",
)
PLAYER_CLASS_NAMES_BY_CID = {}
DETAIL_SEARCH_DEFAULT_MIN_OVR = 132
DETAIL_SEARCH_DEFAULT_MAX_OVR = 160
LOCAL_ASSET_EXTENSIONS = ("webp", "png", "jpg", "jpeg")
PLAYSTYLE_META_FILE = os.path.join(app.root_path, "static", "playstyles", "meta.json")
PLAYSTYLE_CDN_BASE = "https://fco.vod.nexoncdn.co.kr/jade_assets/playstyle/playstyle_128"
_PLAYSTYLE_META_BY_ID = None
FCO_CAREER_DATA_FILE = os.getenv(
    "FCO_CAREER_DATA_FILE",
    os.path.join(app.instance_path, "fco_allp.js"),
)
FCO_CAREER_DATA_URL = os.getenv(
    "FCO_CAREER_DATA_URL",
    "https://raw.githubusercontent.com/Indvel/indvel.github.io/master/fcmsquad/resources/fco_allp.js",
)
_FCO_CAREER_ROWS = None
FCO_CLUB_CAREER_DATA_FILE = os.getenv(
    "FCO_CLUB_CAREER_DATA_FILE",
    os.path.join(app.root_path, "static", "data", "player_club_careers.json"),
)
_FCO_CLUB_CAREER_DATA = None


def _normalize_class_display_name(value):
    if isinstance(value, (list, tuple, set)):
        names = []
        for item in value:
            name = _normalize_class_display_name(item)
            if name and name not in names:
                names.append(name)
        return " / ".join(names)

    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("[") and text.endswith("]"):
        try:
            decoded = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            decoded = None
        if isinstance(decoded, list):
            return _normalize_class_display_name(decoded)
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    return text


def _load_player_class_names():
    try:
        with open(PLAYER_CLASS_MAP_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError:
        print(f"'{PLAYER_CLASS_MAP_FILE}' 파일이 없어 클래스명을 비워둡니다.")
        return {}
    except json.JSONDecodeError as e:
        print(f"'{PLAYER_CLASS_MAP_FILE}' JSON 파싱 오류: {e}")
        return {}
    except Exception as e:
        print(f"'{PLAYER_CLASS_MAP_FILE}' 로드 오류: {e}")
        return {}

    raw_names = payload.get("classes") if isinstance(payload, dict) and "classes" in payload else payload
    if not isinstance(raw_names, dict):
        return {}
    return {
        str(cid): name
        for cid, raw_name in raw_names.items()
        if (name := _normalize_class_display_name(raw_name))
    }


PLAYER_CLASS_NAMES_BY_CID = _load_player_class_names()


def _find_local_asset_url(folder, cid):
    if cid is None:
        return None
    static_folder = os.path.join(app.root_path, "static", folder)
    cid_str = str(cid)
    for ext in LOCAL_ASSET_EXTENSIONS:
        file_name = f"{cid_str}.{ext}"
        file_path = os.path.join(static_folder, file_name)
        if os.path.exists(file_path):
            return f"/static/{folder}/{file_name}"
    return None


def _apply_local_assets(player):
    if not isinstance(player, dict):
        return player
    cid = player.get("cid")
    if not cid:
        return player
    local_card = _find_local_asset_url("card", cid)
    local_face = _find_local_asset_url("faceon", cid)
    if local_card:
        player["bimage"] = local_card
    if local_face:
        player["pimage"] = local_face
    return player

def load_player_data_for_traits():
    global PLAYER_DATA
    if os.path.exists(PLAYER_DATA_FILE):
        try:
            with open(PLAYER_DATA_FILE, "r", encoding="utf-8") as f:
                PLAYER_DATA = json.load(f)
            PLAYER_DATA = [_normalize_player_record(player) for player in PLAYER_DATA if isinstance(player, dict)]
            print(f"'{PLAYER_DATA_FILE}'에서 {len(PLAYER_DATA)}명의 선수 데이터를 로드했습니다 (특성 검색용).")
        except json.JSONDecodeError as e:
            print(f"'{PLAYER_DATA_FILE}' 파일 JSON 파싱 오류: {e} → 비어 있는 데이터로 초기화합니다.")
            PLAYER_DATA = []
        except Exception as e:
            print(f"'{PLAYER_DATA_FILE}' 파일 로드 중 다른 오류: {e} → 비어 있는 데이터로 초기화합니다.")
            PLAYER_DATA = []
    else:
        print(f"'{PLAYER_DATA_FILE}' 파일이 없습니다. 새로 생성합니다.")
        PLAYER_DATA = []
        with open(PLAYER_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)

_FCPLAYER_CARD_CACHE = {}
_FCPLAYER_CARD_CACHE_TTL = 6 * 60 * 60


def _normalize_player_record(player):
    if not isinstance(player, dict):
        return {}

    class_name = _normalize_class_display_name(player.get("className"))
    if not class_name:
        class_name = PLAYER_CLASS_NAMES_BY_CID.get(str(player.get("cid") or ""), "")
    player["className"] = class_name

    if not isinstance(player.get("traits"), list):
        raw_traits = player.get("Trait") or []
        if isinstance(raw_traits, list):
            player["traits"] = [
                trait.get("name")
                for trait in raw_traits
                if isinstance(trait, dict) and trait.get("name")
            ]
        else:
            player["traits"] = []

    if not isinstance(player.get("skills"), list):
        raw_skills = player.get("skillInfo") or []
        if isinstance(raw_skills, list):
            player["skills"] = [
                {
                    "id": str(skill.get("id", "")).strip(),
                    "level": skill.get("lv"),
                }
                for skill in raw_skills
                if isinstance(skill, dict) and str(skill.get("id", "")).strip()
            ]
        else:
            player["skills"] = []

    if not isinstance(player.get("staticPlayStyles"), list):
        raw_playstyles = player.get("staticPlayStyles_org") or []
        player["staticPlayStyles"] = raw_playstyles if isinstance(raw_playstyles, list) else []
    return player


def _normalize_name_for_match(value):
    return re.sub(r"\s+", "", (value or "")).lower()


def _get_local_player_by_cid(cid):
    player = next((p for p in PLAYER_DATA if p.get("cid") == cid), None)
    if not player:
        return None
    normalized = _normalize_player_record(player.copy())
    return _apply_local_assets(normalized)


def _normalize_class_name_for_match(value):
    return re.sub(r"[\s\[\]]+", "", str(value or "")).lower()


def _player_skill_ids(player):
    ids = []
    for field in ("skillInfo", "skills"):
        items = player.get(field) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            skill_id = str(item.get("id") or "").strip()
            if skill_id and skill_id not in ids:
                ids.append(skill_id)
    return ids


def _player_skill_system(player):
    """Return the official local card's skill system without external guessing."""
    skill_ids = _player_skill_ids(player)
    if any(skill_id.startswith("262") for skill_id in skill_ids):
        return "skill"
    if any(skill_id.startswith("261") for skill_id in skill_ids):
        return "boost"

    raw_skills = player.get("skills") or []
    if isinstance(raw_skills, list) and any(
        isinstance(item, dict)
        and str(item.get("kind") or item.get("type") or "").upper() in {"BASE", "ULTIMATE"}
        for item in raw_skills
    ):
        return "skill"

    style_id = str(player.get("skillStyleId") or "").strip()
    if style_id.startswith("260"):
        return "boost"
    if style_id.startswith("30"):
        return "skill"
    return ""


def _fcplayer_card_skill_system(card):
    if isinstance(card.get("skills"), list) and card.get("skills"):
        return "skill"
    if str(card.get("skillBoost") or "").strip():
        return "boost"
    return ""


def _local_skill_boost_name(player):
    existing = str(player.get("skillBoostName") or "").strip()
    if existing:
        return existing
    if _player_skill_system(player) != "boost":
        return ""
    for skill_id in _player_skill_ids(player):
        name = _get_skill_name(skill_id)
        if name and not name.startswith("스킬 "):
            return name
    return ""


def _local_fcplayer_summary(player):
    fields = {
        "pace": STATS_CARD_SUMMARY_WEIGHTS["페이스"],
        "shooting": STATS_CARD_SUMMARY_WEIGHTS["슈팅"],
        "passing": STATS_CARD_SUMMARY_WEIGHTS["패스"],
        "agilityMain": STATS_CARD_SUMMARY_WEIGHTS["드리블"],
        "defending": STATS_CARD_SUMMARY_WEIGHTS["수비"],
        "physical": STATS_CARD_SUMMARY_WEIGHTS["피지컬"],
    }
    stat_values = {
        code: _stats_card_numeric(player, code)
        for weights in fields.values()
        for code, _ in weights
    }
    return {
        field: _stats_card_summary_value(stat_values, weights)
        for field, weights in fields.items()
    }


def _fetch_fcplayer_card_match(player):
    name = str(player.get("playerKor") or "").strip()
    if not name:
        return None

    target_skill_system = _player_skill_system(player)
    target_boost_name = _normalize_filter_text(_local_skill_boost_name(player))
    target_summary = _local_fcplayer_summary(player)
    cache_key = (
        player.get("cid"),
        name,
        int(player.get("ovr") or 0),
        str(player.get("position") or "").upper(),
        _normalize_class_name_for_match(player.get("className")),
        target_skill_system,
        tuple(target_summary.items()),
    )
    now = time.time()
    cached = _FCPLAYER_CARD_CACHE.get(cache_key)
    if cached and now - cached[1] < _FCPLAYER_CARD_CACHE_TTL:
        return cached[0]

    try:
        response = requests.get(
            "https://fcplayer.org/api/cards",
            params={"search": name, "limit": 50},
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            timeout=4,
        )
        response.raise_for_status()
        cards = response.json().get("cards") or []
    except Exception as e:
        print(f"fcplayer card lookup error for {name}: {e}")
        _FCPLAYER_CARD_CACHE[cache_key] = (None, now)
        return None

    target_ovr = int(player.get("ovr") or 0)
    target_position = str(player.get("position") or "").upper()
    target_class = _normalize_class_name_for_match(player.get("className"))

    def score(card):
        if str(card.get("name") or "").strip() != name:
            return -1
        card_ovr_matches = int(card.get("ovr") or 0) == target_ovr
        card_class_matches = target_class and target_class in _normalize_class_name_for_match(card.get("className"))
        if not card_ovr_matches and not card_class_matches:
            return -1
        card_skill_system = _fcplayer_card_skill_system(card)
        if target_skill_system and card_skill_system and target_skill_system != card_skill_system:
            return -1

        value = 100
        if card_ovr_matches:
            value += 80
        if str(card.get("position") or "").upper() == target_position:
            value += 40
        if card_class_matches:
            value += 30
        if target_skill_system and card_skill_system == target_skill_system:
            value += 100

        card_boost_name = _normalize_filter_text(card.get("skillBoost"))
        if target_boost_name and card_boost_name:
            value += 80 if target_boost_name == card_boost_name else -80

        summary_difference = 0
        compared_summary_fields = 0
        for field, local_value in target_summary.items():
            card_value = card.get(field)
            if not isinstance(card_value, (int, float)):
                continue
            summary_difference += abs(int(local_value) - int(card_value))
            compared_summary_fields += 1
        if compared_summary_fields:
            value += max(-80, 120 - (summary_difference * 10))

        for local_field, card_field in (("footL", "leftFootRating"), ("footR", "rightFootRating")):
            local_value = player.get(local_field)
            card_value = card.get(card_field)
            if isinstance(local_value, (int, float)) and isinstance(card_value, (int, float)):
                value += 12 if int(local_value) == int(card_value) else -8
        return value

    best = max(cards, key=score, default=None)
    if not best or score(best) < 100:
        best = None
    _FCPLAYER_CARD_CACHE[cache_key] = (best, now)
    return best


def _merge_fcplayer_skill_data(player):
    local_skill_system = _player_skill_system(player)
    local_boost_name = _local_skill_boost_name(player)
    if local_skill_system == "boost" and local_boost_name:
        player["skillBoostName"] = local_boost_name

    fcplayer_card = _fetch_fcplayer_card_match(player)
    if not fcplayer_card:
        return player

    player["fcplayerCardId"] = fcplayer_card.get("id")
    player["fcplayerMatchedClass"] = fcplayer_card.get("className")
    card_skill_system = _fcplayer_card_skill_system(fcplayer_card)
    if (
        isinstance(fcplayer_card.get("skills"), list)
        and fcplayer_card.get("skills")
        and local_skill_system in {"", "skill"}
        and card_skill_system == "skill"
    ):
        player["skills"] = fcplayer_card.get("skills")
    if (
        fcplayer_card.get("skillBoost")
        and not player.get("skillBoostName")
        and local_skill_system in {"", "boost"}
        and card_skill_system == "boost"
    ):
        player["skillBoostName"] = fcplayer_card.get("skillBoost")
    return player


def _search_local_players_by_name(name_query):
    query = _normalize_name_for_match(name_query)
    if not query:
        return []

    exact_matches = []
    partial_matches = []
    for player in PLAYER_DATA:
        player_name = _normalize_name_for_match(player.get("playerKor"))
        if not player_name:
            continue
        if player_name == query:
            exact_matches.append(_apply_local_assets(_normalize_player_record(player.copy())))
        elif query in player_name:
            partial_matches.append(_apply_local_assets(_normalize_player_record(player.copy())))

    matches = exact_matches or partial_matches
    return sorted(matches, key=lambda p: (-(p.get("ovr") or 0), p.get("className") or "", p.get("cid") or 0))


# 앱 시작 시 데이터 로드 (특성 검색용)
load_player_data_for_traits()


POSITION_COMPATIBILITY = {
    "GK": {"GK"},
    "LB": {"LB", "LWB"},
    "RB": {"RB", "RWB"},
    "CB": {"CB", "CDM"},
    "LWB": {"LWB", "LB", "LM"},
    "RWB": {"RWB", "RB", "RM"},
    "CDM": {"CDM", "CM", "CB"},
    "CM": {"CM", "CDM", "CAM"},
    "CAM": {"CAM", "CM", "CF"},
    "LM": {"LM", "LW", "LWB"},
    "RM": {"RM", "RW", "RWB"},
    "LW": {"LW", "LM", "LF"},
    "RW": {"RW", "RM", "RF"},
    "LF": {"LF", "LW", "CF", "ST"},
    "RF": {"RF", "RW", "CF", "ST"},
    "CF": {"CF", "CAM", "ST", "LF", "RF"},
    "ST": {"ST", "CF", "LF", "RF"},
}


FIELD_COMPARE_STAT_GROUPS = {
    "기본": {
        "ovr": "OVR",
        "height": "키(cm)",
        "weight": "몸무게(kg)",
        "footPair": "주발/약발",
        "skillMovesLevel": "개인기",
    },
    "속도": {
        "ACC": "가속",
        "SPD": "질주 속도",
    },
    "슈팅": {
        "FIN": "결정력",
        "SHO": "슈팅력",
        "LSA": "중거리 슛",
        "PEN": "PK",
        "CUR": "감아차기",
        "VOL": "발리슛",
        "POS": "위치선정",
    },
    "패스": {
        "SPA": "짧은 패스",
        "LPA": "긴 패스",
        "VIS": "시야",
        "CRO": "크로스",
        "FRK": "프리킥",
    },
    "드리블": {
        "DRI": "드리블",
        "BAC": "볼 컨트롤",
        "AGI": "민첩성",
        "REA": "반응도",
        "BAL": "밸런스",
    },
    "수비": {
        "MRK": "마크",
        "STT": "태클",
        "SLT": "슬라이딩 태클",
        "AWR": "가로채기",
        "AGG": "공격성",
    },
    "피지컬": {
        "HEA": "헤딩",
        "STR": "힘",
        "JMP": "점프",
    },
}


GK_COMPARE_STAT_GROUPS = {
    "기본": {
        "ovr": "OVR",
        "height": "키(cm)",
        "weight": "몸무게(kg)",
        "footPair": "주발/약발",
    },
    "골키퍼": {
        "GKD": "다이빙",
        "HAN": "핸들링",
        "GKK": "킥",
        "REF": "반사 신경",
        "GKP": "GK 위치선정",
    },
    "기본 능력": {
        "REA": "반응도",
        "POS": "위치선정",
        "JMP": "점프",
        "STR": "힘",
        "AGG": "공격성",
    },
}

ENHANCE_LEVEL_STEPS = [0, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 5, 9, 12]
ENHANCE_LEVEL_TOTALS = []
_enhance_total = 0
for _enhance_step in ENHANCE_LEVEL_STEPS:
    _enhance_total += _enhance_step
    ENHANCE_LEVEL_TOTALS.append(_enhance_total)
MAX_ENHANCE_LEVEL = len(ENHANCE_LEVEL_TOTALS) - 1
PRICE_UNIT = "MP"
FCPLAYER_ASSET_BASE = "https://fcplayer.org/assets"

SKILL_BOOST_LEVEL_VALUES = [0, 3, 5, 8, 11, 13, 16, 19, 21, 24, 27, 29, 32, 35, 37, 40]

# FC Mobile official SquadMaker's regular training rules (0-10).
# These are separate from the game's 0-63 special-training table. Each regular
# training stage is cumulative and raises stats according to the player's
# original-position stat tier.
MAX_TRAINING_LEVEL = 10
TRAINING_TIER_LEVEL_BONUSES = {
    15: [0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 15],
    12: [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 12],
    9: [0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 9],
    6: [0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 6],
}
TRAINING_POSITION_STAT_TIERS = {
    "ST": {
        15: ("SHO", "REA", "HEA"),
        12: ("SPD", "FIN", "LSA", "POS", "SPA", "STR"),
        9: ("ACC", "VOL", "LPA", "DRI", "BAC", "AWR"),
        6: ("PEN", "VIS", "CRO", "CUR", "FRK", "AGI", "BAL", "MRK", "SLT", "STT", "AGG", "JMP"),
    },
    "LW / RW": {
        15: ("CRO", "DRI", "BAC"),
        12: ("ACC", "SPD", "FIN", "SPA", "REA", "AWR"),
        9: ("SHO", "LSA", "POS", "LPA", "VIS", "AGI"),
        6: ("VOL", "PEN", "CUR", "FRK", "BAL", "MRK", "SLT", "STT", "HEA", "STR", "AGG", "JMP"),
    },
    "CM": {
        15: ("POS", "SPA", "REA"),
        12: ("ACC", "SPD", "LPA", "DRI", "BAC", "AWR"),
        9: ("FIN", "SHO", "LSA", "VIS", "MRK", "STT"),
        6: ("VOL", "PEN", "CRO", "CUR", "FRK", "AGI", "BAL", "SLT", "HEA", "STR", "AGG", "JMP"),
    },
    "CAM": {
        15: ("SPA", "LPA", "AWR"),
        12: ("SPD", "FIN", "LSA", "POS", "DRI", "BAC"),
        9: ("ACC", "SHO", "VIS", "CRO", "AGI", "REA"),
        6: ("VOL", "PEN", "CUR", "FRK", "BAL", "MRK", "SLT", "STT", "HEA", "STR", "AGG", "JMP"),
    },
    "CDM": {
        15: ("POS", "SPA", "AGG"),
        12: ("ACC", "LPA", "BAC", "REA", "MRK", "AWR"),
        9: ("SPD", "LSA", "SLT", "STT", "HEA", "STR"),
        6: ("FIN", "SHO", "VOL", "PEN", "VIS", "CRO", "CUR", "FRK", "DRI", "AGI", "BAL", "JMP"),
    },
    "LW / RM": {
        15: ("ACC", "SPD", "SPA"),
        12: ("POS", "CRO", "DRI", "BAC", "REA", "AWR"),
        9: ("FIN", "SHO", "LSA", "LPA", "VIS", "AGI"),
        6: ("VOL", "PEN", "CUR", "FRK", "BAL", "MRK", "SLT", "STT", "HEA", "STR", "AGG", "JMP"),
    },
    "GK": {
        15: ("GKD", "REF", "HAN"),
        12: ("POS", "LPA", "REA", "AWR", "AGG", "GKP"),
        9: ("ACC", "SPD", "SPA", "HEA", "JMP", "GKK"),
        6: ("SHO", "PEN", "VIS", "CUR", "FRK", "DRI", "BAC", "AGI", "BAL", "MRK", "SLT", "STR"),
    },
    "CB": {
        15: ("MRK", "HEA", "AGG"),
        12: ("POS", "SPA", "BAC", "REA", "AWR", "STR"),
        9: ("ACC", "SPD", "BAL", "SLT", "STT", "JMP"),
        6: ("FIN", "SHO", "LSA", "VOL", "PEN", "LPA", "VIS", "CRO", "CUR", "FRK", "DRI", "AGI"),
    },
    "LB / RB": {
        15: ("CRO", "REA", "MRK"),
        12: ("ACC", "SPD", "SPA", "LPA", "BAC", "HEA"),
        9: ("SHO", "SLT", "STT", "AWR", "STR", "AGG"),
        6: ("FIN", "LSA", "POS", "VOL", "PEN", "VIS", "CUR", "FRK", "DRI", "AGI", "BAL", "JMP"),
    },
    "LWB / RWB": {
        15: ("SPD", "POS", "CRO"),
        12: ("ACC", "SPA", "LPA", "DRI", "BAC", "REA"),
        9: ("FIN", "MRK", "SLT", "STT", "AWR", "HEA"),
        6: ("SHO", "LSA", "VOL", "PEN", "VIS", "CUR", "FRK", "AGI", "BAL", "STR", "AGG", "JMP"),
    },
    "CF": {
        15: ("SPA", "DRI", "AWR"),
        12: ("ACC", "FIN", "LSA", "POS", "BAC", "REA"),
        9: ("SPD", "SHO", "LPA", "VIS", "CRO", "STR"),
        6: ("VOL", "PEN", "CUR", "FRK", "AGI", "BAL", "MRK", "SLT", "STT", "HEA", "AGG", "JMP"),
    },
}


def _training_position_key(position):
    normalized = re.sub(r"[^A-Z]", "", str(position or "").upper())
    if normalized in TRAINING_POSITION_STAT_TIERS:
        return normalized
    if normalized in {"LW", "RW", "LRW"}:
        return "LW / RW"
    if normalized in {"LM", "RM", "LRM"}:
        return "LW / RM"
    if normalized in {"LB", "RB", "LRB"}:
        return "LB / RB"
    if normalized in {"LWB", "RWB", "WB"}:
        return "LWB / RWB"
    if normalized in {"LF", "RF"}:
        return "CF"
    return normalized


def _training_stat_tiers(position):
    tiers = TRAINING_POSITION_STAT_TIERS.get(_training_position_key(position), {})
    return {
        code: tier
        for tier, codes in tiers.items()
        for code in codes
    }


def _training_stat_bonuses(position, training_level):
    try:
        level = max(0, min(int(training_level), MAX_TRAINING_LEVEL))
    except (TypeError, ValueError):
        level = 0
    return {
        code: TRAINING_TIER_LEVEL_BONUSES[tier][level]
        for code, tier in _training_stat_tiers(position).items()
        if TRAINING_TIER_LEVEL_BONUSES[tier][level] > 0
    }


def _training_bonuses_by_level(position):
    return [
        _training_stat_bonuses(position, level)
        for level in range(MAX_TRAINING_LEVEL + 1)
    ]

WORK_RATE_OPTIONS = [
    {"value": "2-2", "label": "높/높", "att": 2, "def": 2},
    {"value": "2-0", "label": "높/보", "att": 2, "def": 0},
    {"value": "2-1", "label": "높/낮", "att": 2, "def": 1},
    {"value": "0-0", "label": "보/보", "att": 0, "def": 0},
    {"value": "0-2", "label": "보/높", "att": 0, "def": 2},
    {"value": "0-1", "label": "보/낮", "att": 0, "def": 1},
    {"value": "1-2", "label": "낮/높", "att": 1, "def": 2},
    {"value": "1-0", "label": "낮/보", "att": 1, "def": 0},
    {"value": "1-1", "label": "낮/낮", "att": 1, "def": 1},
]
WORK_RATE_OPTION_MAP = {item["value"]: item for item in WORK_RATE_OPTIONS}

STAT_LABEL_TO_CODE = {
    "가속": "ACC",
    "질주 속도": "SPD",
    "결정력": "FIN",
    "슈팅력": "SHO",
    "중거리 슛": "LSA",
    "위치 선정": "POS",
    "위치선정": "POS",
    "드리블": "DRI",
    "볼 컨트롤": "BAC",
    "짧은 패스": "SPA",
    "긴 패스": "LPA",
    "긴패스": "LPA",
    "시야": "VIS",
    "크로스": "CRO",
    "감아차기": "CUR",
    "발리슛": "VOL",
    "프리킥": "FRK",
    "PK": "PEN",
    "마크": "MRK",
    "태클": "STT",
    "슬라이딩 태클": "SLT",
    "가로채기": "AWR",
    "공격성": "AGG",
    "헤딩": "HEA",
    "힘": "STR",
    "점프": "JMP",
    "스태미나": "STA",
    "민첩성": "AGI",
    "반응도": "REA",
    "밸런스": "BAL",
    "다이빙": "GKD",
    "핸들링": "HAN",
    "킥": "GKK",
    "반사 신경": "REF",
    "GK 위치 선정": "GKP",
    "GK 위치선정": "GKP",
}

SKILL_BOOST_STATS = {
    # Legacy/special boosts still used by sub-130 OVR cards. These names are
    # present in the official card data but were missing from the display map,
    # so selecting a boost level rendered no stat changes for those cards.
    "MVP 공격수": ["가속", "결정력", "슈팅력", "위치 선정", "드리블"],
    "MVP 미드필더": ["중거리 슛", "짧은 패스", "긴패스", "시야", "반응도"],
    "MVP 수비수": ["질주 속도", "마크", "태클", "가로채기", "힘"],
    "MVP 골키퍼": ["다이빙", "핸들링", "킥", "반사 신경", "GK 위치 선정"],
    "FW 레코드 브레이커": ["가속", "결정력", "슈팅력", "위치 선정", "드리블"],
    "MF 레코드 브레이커": ["중거리 슛", "짧은 패스", "긴패스", "시야", "반응도"],
    "DF 레코드 브레이커": ["질주 속도", "마크", "태클", "가로채기", "힘"],
    "GK 레코드 브레이커": ["다이빙", "핸들링", "킥", "반사 신경", "GK 위치 선정"],
    "도미네이션": ["가속", "결정력", "슈팅력", "위치 선정", "드리블"],
    "이해도": ["긴패스", "시야", "반응도", "가로채기", "볼 컨트롤"],
    "밸런스": ["질주 속도", "크로스", "드리블", "볼 컨트롤", "밸런스", "태클"],
    "로켓": ["질주 속도", "중거리 슛", "크로스", "드리블", "볼 컨트롤"],
    "중거리 슛": ["슈팅력", "중거리 슛", "긴패스", "시야", "볼 컨트롤"],
    "세트 피스": ["슈팅력", "중거리 슛", "긴패스", "크로스", "프리킥"],
    "막스맨": ["가속", "결정력", "중거리 슛", "위치 선정", "드리블"],
    "파워풀": ["가속", "결정력", "위치선정", "헤딩", "힘"],
    "스나이퍼": ["가속", "결정력", "중거리 슛", "위치 선정", "드리블"],
    "마에스트로": ["가속", "결정력", "짧은 패스", "드리블", "볼 컨트롤"],
    "아키텍트": ["가속", "슈팅력", "드리블", "볼 컨트롤", "민첩성"],
    "결정력": ["결정력", "슈팅력", "위치 선정", "점프", "드리블"],
    "타이거": ["결정력", "슈팅력", "위치 선정", "힘", "드리블"],
    "공격 마스터": ["가속", "중거리 슛", "짧은 패스", "드리블", "볼 컨트롤"],
    "호크": ["가속", "결정력", "크로스", "감아차기", "드리블"],
    "나이프": ["가속", "긴패스", "크로스", "민첩성", "드리블"],
    "세컨드 스트라이커": ["결정력", "드리블", "슈팅력", "볼 컨트롤", "짧은 패스"],
    "슈퍼카": ["가속", "질주 속도", "크로스", "긴패스", "드리블"],
    "위치 선정": ["위치 선정", "헤딩", "슈팅력", "민첩성", "밸런스"],
    "헤딩": ["결정력", "반응도", "헤딩", "힘", "점프"],
    "공격": ["볼 컨트롤", "결정력", "질주 속도", "반응도", "발리슛"],
    "민첩성": ["결정력", "드리블", "민첩성", "반응도", "밸런스"],
    "페이스": ["가속", "질주 속도", "긴패스", "크로스", "민첩성"],
    "슈팅": ["결정력", "슈팅력", "중거리 슛", "위치 선정", "발리슛"],
    "속도": ["질주 속도", "위치 선정", "드리블", "볼 컨트롤", "민첩성"],
    "어택미드": ["질주 속도", "짧은 패스", "긴패스", "드리블", "민첩성"],
    "패스": ["짧은 패스", "긴패스", "시야", "크로스", "밸런스"],
    "제너럴리스트": ["중거리 슛", "민첩성", "반응도", "가로채기", "공격성"],
    "주장": ["드리블", "짧은 패스", "볼 컨트롤", "시야", "민첩성"],
    "짧은 패스": ["짧은 패스", "위치 선정", "드리블", "태클", "힘"],
    "플레이메이커": ["짧은 패스", "긴패스", "시야", "드리블", "반응도"],
    "미드엔진": ["중거리 슛", "긴패스", "감아차기", "밸런스", "태클"],
    "홀딩": ["가속", "마크", "태클", "공격성", "힘"],
    "월": ["가속", "마크", "태클", "가로채기", "공격성"],
    "특별 구성": ["마크", "질주 속도", "볼 컨트롤", "힘", "슬라이딩 태클"],
    "스톤": ["질주 속도", "긴패스", "마크", "가로채기", "공격성"],
    "공격성": ["마크", "슬라이딩 태클", "헤딩", "힘", "점프"],
    "가로채기": ["가로채기", "반응도", "헤딩", "태클", "공격성"],
    "수비 마스터": ["가속", "태클", "슬라이딩 태클", "헤딩", "공격성"],
    "앵커": ["마크", "가로채기", "헤딩", "힘", "점프"],
    "수비": ["긴패스", "밸런스", "마크", "슬라이딩 태클", "헤딩"],
    "피지컬": ["반응도", "슬라이딩 태클", "힘", "공격성", "점프"],
    "반응도": ["크로스", "드리블", "슬라이딩 태클", "반응도", "가로채기"],
    "마크": ["짧은 패스", "반응도", "마크", "가로채기", "헤딩"],
    "플라이윙": ["질주 속도", "긴패스", "마크", "가로채기", "공격성"],
    "글래디에이터": ["가속", "크로스", "마크", "태클", "가로채기"],
    "라스트라인": ["다이빙", "반사 신경", "GK 위치 선정", "핸들링", "킥"],
    "GK 다이빙": ["다이빙", "반사 신경", "GK 위치 선정", "핸들링", "반응도"],
    "글러브": ["다이빙", "GK 위치 선정", "반사 신경", "긴패스", "킥"],
    "반사 신경": ["다이빙", "GK 위치 선정", "반사 신경", "긴패스", "민첩성"],
    "다이빙": ["다이빙", "핸들링", "점프", "긴패스", "반사 신경"],
    "핸들링": ["핸들링", "킥", "반응도", "긴패스", "반사 신경"],
    "카운터": ["긴패스", "민첩성", "중거리 슛", "위치 선정", "시야"],
    "GK 위치 선정": ["GK 위치 선정", "킥", "반응도", "긴패스", "다이빙"],
    "넘버원": ["GK 위치 선정", "다이빙", "킥", "반응도", "핸들링"],
    "GK 제너럴리스트": ["킥", "반응도", "GK 위치 선정", "긴패스", "핸들링"],
    "프리킥": ["프리킥", "감아차기", "중거리 슛", "슈팅력", "시야"],
    "슈팅력": ["질주 속도", "슈팅력", "중거리 슛", "발리슛", "볼 컨트롤"],
    "드리블": ["결정력", "중거리 슛", "드리블", "반응도", "발리슛"],
    "가속": ["가속", "위치 선정", "발리슛", "긴패스", "반응도"],
    "크로스": ["긴패스", "시야", "크로스", "감아차기", "마크"],
    "볼 컨트롤": ["짧은 패스", "크로스", "드리블", "볼 컨트롤", "밸런스"],
    "긴패스": ["긴패스", "시야", "감아차기", "민첩성", "가로채기"],
    "긴 패스": ["긴패스", "시야", "감아차기", "민첩성", "가로채기"],
    "시야": ["가속", "짧은 패스", "긴패스", "시야", "드리블"],
    "태클": ["반응도", "밸런스", "태클", "슬라이딩 태클", "힘"],
    "힘": ["밸런스", "태클", "힘", "헤딩", "점프"],
    "커맨더": ["가속", "슈팅력", "드리블", "반응도", "볼 컨트롤"],
    "코어": ["가속", "슈팅력", "민첩성", "마크", "가로채기"],
    "크랙": ["가속", "질주 속도", "결정력", "볼 컨트롤", "드리블"],
    "실드": ["가속", "마크", "태클", "민첩성", "힘"],
    "에너지": ["가속", "마크", "드리블", "가로채기", "크로스"],
    "워리어": ["가속", "결정력", "슈팅력", "힘", "드리블"],
    "세이비어": ["다이빙", "GK 위치선정", "반사 신경", "킥", "반응도"],
}

SKILL_BOOST_STAT_CODES = {
    name: [STAT_LABEL_TO_CODE[label] for label in labels if label in STAT_LABEL_TO_CODE]
    for name, labels in SKILL_BOOST_STATS.items()
}

ENGLISH_STAT_TO_CODE = {
    "acceleration": "ACC",
    "sprintSpeed": "SPD",
    "finishing": "FIN",
    "shotPower": "SHO",
    "longShots": "LSA",
    "positioning": "POS",
    "penalties": "PEN",
    "volleys": "VOL",
    "shortPassing": "SPA",
    "longPassing": "LPA",
    "vision": "VIS",
    "crossing": "CRO",
    "curve": "CUR",
    "fkAccuracy": "FRK",
    "ballControl": "BAC",
    "dribbling": "DRI",
    "agility": "AGI",
    "reactions": "REA",
    "balance": "BAL",
    "marking": "MRK",
    "standingTackle": "STT",
    "slidingTackle": "SLT",
    "interceptions": "AWR",
    "headingAccuracy": "HEA",
    "strength": "STR",
    "aggression": "AGG",
    "jumping": "JMP",
    "gkDiving": "GKD",
    "gkHandling": "HAN",
    "gkKicking": "GKK",
    "gkReflexes": "REF",
    "gkPositioning": "GKP",
}

NEW_SKILL_STATS = {
    "골 가드": ["gkPositioning", "gkKicking"],
    "딥라잉 포워드": ["shortPassing", "finishing"],
    "레지스타": ["longPassing", "vision"],
    "메찰라": ["shotPower", "positioning"],
    "미들라이커": ["shortPassing", "longShots"],
    "박스 투 박스": ["ballControl", "dribbling"],
    "볼 캐리어": ["ballControl", "marking"],
    "빌드업 센터백": ["longPassing", "marking"],
    "섀도우 스트라이커": ["positioning", "agility"],
    "새도우 스트라이커": ["positioning", "agility"],
    "수비형 윙어": ["sprintSpeed", "slidingTackle"],
    "수비형 키퍼": ["gkReflexes", "gkDiving"],
    "스위퍼": ["interceptions", "standingTackle"],
    "스위퍼 키퍼": ["sprintSpeed", "gkHandling"],
    "스위스 키퍼": ["sprintSpeed", "gkHandling"],
    "스토퍼": ["aggression", "standingTackle"],
    "압박형 전방 공격수": ["strength", "positioning"],
    "앵커맨": ["marking", "standingTackle"],
    "올라운더 디펜더": ["standingTackle", "slidingTackle"],
    "올라운드 키퍼": ["gkDiving", "jumping"],
    "와이드 미드필더": ["crossing", "sprintSpeed"],
    "윙백": ["ballControl", "dribbling"],
    "윙어": ["crossing", "curve"],
    "인버티드 윙백": ["marking", "slidingTackle"],
    "인버티드 윙어": ["dribbling", "longShots"],
    "인버티드 풀백": ["marking", "standingTackle"],
    "인사이드 포워드": ["shortPassing", "reactions"],
    "중앙 미드필더": ["interceptions", "dribbling"],
    "클래식 스트라이커": ["ballControl", "finishing"],
    "타겟형 스트라이커": ["strength", "jumping"],
    "트레콰르티스타": ["crossing", "shortPassing"],
    "판타지스타": ["longPassing", "shortPassing"],
    "판타지 스타": ["longPassing", "shortPassing"],
    "포처": ["finishing", "positioning"],
    "풀백": ["interceptions", "slidingTackle"],
    "프리롤": ["reactions", "agility"],
    "플레이메이킹 윙어": ["crossing", "shortPassing"],
    "PK 마스터": ["finishing", "fkAccuracy", "penalties"],
    "감아차기 마스터": ["shotPower", "longShots", "curve"],
    "공중의 지배자": ["headingAccuracy", "strength", "jumping"],
    "기민한 드리블": ["ballControl", "dribbling", "agility"],
    "깔아차기 슛": ["shotPower", "longShots", "volleys"],
    "디스트로이어": ["aggression", "interceptions", "standingTackle"],
    "민첩한 드리블러": ["dribbling", "reactions", "agility"],
    "밀착 드리블": ["ballControl", "dribbling", "balance"],
    "밀착 압박": ["marking", "balance", "standingTackle"],
    "부동의 수비": ["interceptions", "marking", "standingTackle"],
    "빠른 복귀": ["acceleration", "interceptions", "reactions"],
    "빠른 위치 선정": ["interceptions", "marking", "sprintSpeed"],
    "세트피스 마스터": ["crossing", "longPassing", "fkAccuracy"],
    "솔로 런": ["ballControl", "dribbling", "sprintSpeed"],
    "수호신": ["gkReflexes", "gkDiving", "gkKicking"],
    "슈퍼 슛": ["finishing", "longShots", "curve"],
    "슈퍼 캐치": ["headingAccuracy", "gkDiving", "jumping"],
    "스피드스터": ["acceleration", "sprintSpeed", "reactions"],
    "슬라이딩 태클": ["interceptions", "standingTackle", "slidingTackle"],
    "아크로바틱 슈팅": ["positioning", "balance", "volleys"],
    "아티스트": ["longPassing", "shortPassing", "curve"],
    "예리한 피니셔": ["finishing", "shotPower", "volleys"],
    "원거리 슛": ["ballControl", "shotPower", "longShots"],
    "유연한 탈압박": ["ballControl", "strength", "agility"],
    "찰거머리 마크": ["aggression", "interceptions", "marking"],
    "철옹성": ["marking", "standingTackle", "slidingTackle"],
    "총지휘관": ["longPassing", "balance", "vision"],
    "추격 수비": ["acceleration", "aggression", "marking"],
    "커브 패스": ["crossing", "longPassing", "curve"],
    "컨트롤 타워": ["longPassing", "shortPassing", "vision"],
    "쾌속 침투": ["acceleration", "positioning", "vision"],
    "퀵 릴리즈": ["shotPower", "agility", "volleys"],
    "퀵 턴": ["acceleration", "reactions", "agility"],
    "킬러 패스": ["crossing", "shortPassing", "vision"],
    "탁월한 밸런스": ["reactions", "agility", "balance"],
    "파워 샷": ["finishing", "shotPower", "longShots"],
    "파이널 라인": ["gkReflexes", "strength", "gkHandling"],
    "포지셔닝": ["strength", "aggression", "gkPositioning"],
    "폭격기": ["headingAccuracy", "positioning", "jumping"],
    "폭발적 가속": ["acceleration", "dribbling", "balance"],
    "피지컬 거인": ["aggression", "headingAccuracy", "strength"],
    "핀포인트 크로스": ["crossing", "longPassing", "vision"],
}

NEW_SKILL_STAT_CODES = {
    name: [ENGLISH_STAT_TO_CODE[stat] for stat in stats if stat in ENGLISH_STAT_TO_CODE]
    for name, stats in NEW_SKILL_STATS.items()
}

STAT_CODE_LABELS = {
    code: label
    for groups in (FIELD_COMPARE_STAT_GROUPS, GK_COMPARE_STAT_GROUPS)
    for stats in groups.values()
    for code, label in stats.items()
}

RAISED_STAT_OPTIONS = sorted(
    [
        {"code": code, "label": label}
        for code, label in STAT_CODE_LABELS.items()
        if any(
            code in stat_codes
            for stat_codes in list(SKILL_BOOST_STAT_CODES.values()) + list(NEW_SKILL_STAT_CODES.values())
        )
    ],
    key=lambda item: item["label"],
)

PLAYER_REVIEW_TIERS = [
    "레전더리 2",
    "레전더리 1",
    "FC챔피언 10",
    "FC챔피언 20",
    "FC챔피언 30",
    "FC챔피언 40",
    "FC챔피언 50",
    "FC챔피언 100이상",
]

PLAYER_REVIEW_FORMATIONS = [
    "4-3-3 ATTACK",
    "4-3-3 DEFEND",
    "4-3-3 HOLDING",
    "4-3-3",
    "4-4-2 FLAT",
    "4-2-4",
    "4-2-3-1 WIDE",
    "4-1-2-1-2 WIDE",
    "4-4-1-1 ATTACK",
    "4-1-2-1-2 NARROW",
    "3-4-3 DIAMOND",
    "3-4-3 FLAT",
    "3-5-1-1",
    "3-5-2",
    "5-2-1-2",
    "4-5-1 FLAT",
    "4-3-2-1",
    "5-3-2",
    "4-3-3 FALSE 9",
    "3-4-1-2",
    "4-2-2-2",
    "4-4-2 HOLDING",
    "4-1-4-1",
    "5-2-2-1",
    "4-3-1-2",
    "4-2-3-1 NARROW",
    "3-4-2-1",
    "4-5-1",
    "5-4-1",
]

PLAYER_REVIEW_POSITIONS = [
    "ST", "CF", "LW", "RW", "CAM", "CM", "CDM", "LM", "RM",
    "LWB", "RWB", "LB", "RB", "CB", "GK",
]

PLAYER_REVIEW_RATING_FIELDS = [
    {"key": "speed", "field": "rating_speed", "note_field": "note_speed", "label": "속도"},
    {"key": "shot", "field": "rating_shot", "note_field": "note_shot", "label": "슛"},
    {"key": "positioning", "field": "rating_positioning", "note_field": "note_positioning", "label": "위치선정"},
    {"key": "feel", "field": "rating_feel", "note_field": "note_feel", "label": "체감"},
    {"key": "stepover", "field": "rating_stepover", "note_field": "note_stepover", "label": "스텝오버"},
]
PLAYER_REVIEW_DEFENDER_RATING_FIELDS = [
    {"key": "speed", "field": "rating_speed", "note_field": "note_speed", "label": "속도"},
    {"key": "shot", "field": "rating_shot", "note_field": "note_shot", "label": "슛"},
    {"key": "positioning", "field": "rating_positioning", "note_field": "note_positioning", "label": "위치선정"},
    {"key": "feel", "field": "rating_feel", "note_field": "note_feel", "label": "체감"},
    {"key": "duel", "field": "rating_duel", "note_field": "note_duel", "label": "경합"},
    {"key": "defense", "field": "rating_defense", "note_field": "note_defense", "label": "수비"},
]
DEFENDER_REVIEW_POSITIONS = {"CB", "LB", "RB", "LWB", "RWB"}
MIN_REVIEW_TEXT_CHARS = 20
MIN_REVIEW_NOTE_CHARS = 6
MIN_MEANINGFUL_REVIEW_NOTES = 3
LOW_EFFORT_REVIEW_TERMS = {
    "굿", "좋음", "좋아요", "좋다", "나쁨", "별로", "쓸만함", "쓸만해요",
    "모름", "몰라", "없음", "무난", "보통", "그냥", "대충", "테스트",
    "test", "asdf", "qwer", "ㅇㅇ", "ㄴㄴ", "ㅁㄴㅇㄹ", "ㅋㅋ", "ㅎㅎ",
}

SKILL_ID_NAME_MAP = {
    "261001": "MVP 공격수",
    "261002": "MVP 수비수",
    "261003": "MVP 골키퍼",
    "261004": "MVP 미드필더",
    "261005": "FW 레코드 브레이커",
    "261006": "DF 레코드 브레이커",
    "261007": "GK 레코드 브레이커",
    "261008": "MF 레코드 브레이커",
    "261009": "앵커",
    "261010": "어택미드",
    "261011": "아키텍트",
    "261012": "플라이윙",
    "261013": "글래디에이터",
    "261014": "글러브",
    "261015": "호크",
    "261016": "나이프",
    "261017": "라스트라인",
    "261018": "마에스트로",
    "261019": "막스맨",
    "261020": "미드엔진",
    "261021": "플레이메이커",
    "261022": "파워풀",
    "261023": "로켓",
    "261024": "스나이퍼",
    "261025": "스톤",
    "261026": "슈퍼카",
    "261027": "타이거",
    "261028": "월",
    "261029": "커맨더",
    "261030": "코어",
    "261031": "크랙",
    "261032": "에너지",
    "261033": "세이비어",
    "261034": "실드",
    "261035": "워리어",
    "261036": "가속",
    "261037": "공격성",
    "261038": "민첩성",
    "261039": "공격",
    "261040": "이해도",
    "261041": "밸런스",
    "261042": "볼 컨트롤",
    "261043": "주장",
    "261044": "특별 구성",
    "261045": "카운터",
    "261046": "크로스",
    "261047": "수비 마스터",
    "261048": "공격 마스터",
    "261049": "수비",
    "261050": "다이빙",
    "261051": "도미네이션",
    "261052": "드리블",
    "261053": "결정력",
    "261054": "프리킥",
    "261055": "제너럴리스트",
    "261056": "GK 다이빙",
    "261057": "GK 제너럴리스트",
    "261058": "GK 위치 선정",
    "261059": "핸들링",
    "261060": "헤딩",
    "261061": "홀딩",
    "261062": "가로채기",
    "261063": "긴 패스",
    "261064": "중거리 슛",
    "261065": "마크",
    "261066": "넘버원",
    "261067": "페이스",
    "261068": "패스",
    "261069": "피지컬",
    "261070": "위치 선정",
    "261071": "반응도",
    "261072": "반사 신경",
    "261073": "세컨드 스트라이커",
    "261074": "세트 피스",
    "261075": "슈팅",
    "261076": "짧은 패스",
    "261077": "슈팅력",
    "261078": "속도",
    "261079": "힘",
    "261080": "태클",
    "261081": "시야",
    "262001": "타겟형 스트라이커",
    "262002": "포처",
    "262003": "클래식 스트라이커",
    "262004": "딥라잉 포워드",
    "262005": "압박형 전방 공격수",
    "262006": "윙어",
    "262007": "인사이드 포워드",
    "262008": "플레이메이킹 윙어",
    "262009": "인버티드 윙어",
    "262010": "섀도우 스트라이커",
    "262011": "프리롤",
    "262012": "미들라이커",
    "262013": "트레콰르티스타",
    "262014": "메찰라",
    "262015": "판타지스타",
    "262016": "중앙 미드필더",
    "262017": "박스 투 박스",
    "262018": "레지스타",
    "262019": "앵커맨",
    "262020": "볼 캐리어",
    "262021": "와이드 미드필더",
    "262022": "수비형 윙어",
    "262023": "윙백",
    "262024": "인버티드 윙백",
    "262025": "풀백",
    "262026": "인버티드 풀백",
    "262027": "빌드업 센터백",
    "262028": "스위퍼",
    "262029": "스토퍼",
    "262030": "올라운더 디펜더",
    "262031": "수비형 키퍼",
    "262032": "스위퍼 키퍼",
    "262033": "골 가드",
    "262034": "올라운드 키퍼",
    "262035": "파워 샷",
    "262036": "슈퍼 슛",
    "262037": "원거리 슛",
    "262038": "깔아차기 슛",
    "262039": "아크로바틱 슈팅",
    "262040": "예리한 피니셔",
    "262041": "감아차기 마스터",
    "262042": "폭격기",
    "262043": "PK 마스터",
    "262044": "퀵 릴리즈",
    "262045": "컨트롤 타워",
    "262046": "총지휘관",
    "262047": "아티스트",
    "262048": "킬러 패스",
    "262049": "커브 패스",
    "262050": "핀포인트 크로스",
    "262051": "민첩한 드리블러",
    "262052": "밀착 드리블",
    "262053": "기민한 드리블",
    "262054": "탁월한 밸런스",
    "262055": "퀵 턴",
    "262056": "유연한 탈압박",
    "262057": "피지컬 거인",
    "262058": "철옹성",
    "262059": "부동의 수비",
    "262060": "찰거머리 마크",
    "262061": "밀착 압박",
    "262062": "슬라이딩 태클",
    "262063": "디스트로이어",
    "262064": "스피드스터",
    "262065": "추격 수비",
    "262066": "쾌속 침투",
    "262067": "빠른 복귀",
    "262068": "빠른 위치 선정",
    "262069": "솔로 런",
    "262070": "폭발적 가속",
    "262071": "공중의 지배자",
    "262072": "세트피스 마스터",
    "262073": "수호신",
    "262074": "포지셔닝",
    "262075": "파이널 라인",
    "262076": "슈퍼 캐치",
}


def _extract_player_positions(player):
    positions = []
    for key in ("position", "positionOrg", "webposition", "potentialPosition", "postion2", "postion3", "postionPanalty2", "postionPanalty3"):
        value = player.get(key)
        if isinstance(value, list):
            values = value
        elif isinstance(value, str):
            values = re.split(r"[,/|]+", value.upper())
        else:
            continue
        for token in values:
            normalized = str(token or "").upper().strip()
            if normalized and normalized not in positions:
                positions.append(normalized)
    return positions


def _extract_potential_positions(player):
    positions = []
    value = player.get("potentialPosition")
    if isinstance(value, list):
        values = value
    elif isinstance(value, str):
        values = re.split(r"[,/|]+", value.upper())
    else:
        values = []

    primary_position = str(player.get("position") or "").upper().strip()
    for token in values:
        normalized = str(token or "").upper().strip()
        if normalized and normalized != primary_position and normalized not in positions:
            positions.append(normalized)
    return positions


def _extract_primary_player_position(player):
    for key in ("position", "positionOrg", "webposition"):
        value = player.get(key)
        if isinstance(value, list):
            values = value
        elif isinstance(value, str):
            values = re.split(r"[,/|]+", value.upper())
        else:
            continue

        for token in values:
            normalized = str(token or "").upper().strip()
            if normalized:
                return normalized
    return ""


def _player_work_rate_key(player):
    try:
        att_rate = int(player.get("attWorkRate"))
        def_rate = int(player.get("defWorkRate"))
    except (TypeError, ValueError):
        return ""
    return f"{att_rate}-{def_rate}"


def _work_rate_labels(values):
    return [
        WORK_RATE_OPTION_MAP[value]["label"]
        for value in values
        if value in WORK_RATE_OPTION_MAP
    ]


def _extract_player_traits(player):
    traits = []
    raw_traits = player.get("traits")
    if not isinstance(raw_traits, list):
        raw_traits = player.get("Trait") or []

    for trait in raw_traits:
        if isinstance(trait, dict):
            value = trait.get("name")
        else:
            value = trait
        normalized = str(value or "").strip()
        if normalized and normalized not in traits:
            traits.append(normalized)
    return traits


def _load_playstyle_meta():
    global _PLAYSTYLE_META_BY_ID
    if _PLAYSTYLE_META_BY_ID is not None:
        return _PLAYSTYLE_META_BY_ID

    rows = []
    try:
        with open(PLAYSTYLE_META_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, list):
            rows = loaded
    except FileNotFoundError:
        print(f"'{PLAYSTYLE_META_FILE}' 파일이 없어 플레이스타일 메타를 비워둡니다.")
    except json.JSONDecodeError as e:
        print(f"'{PLAYSTYLE_META_FILE}' JSON 파싱 오류: {e}")
    except Exception as e:
        print(f"'{PLAYSTYLE_META_FILE}' 로드 오류: {e}")

    _PLAYSTYLE_META_BY_ID = {
        str(item.get("idStr") or "").strip(): item
        for item in rows
        if isinstance(item, dict) and str(item.get("idStr") or "").strip()
    }
    return _PLAYSTYLE_META_BY_ID


def _playstyle_image_url(icon_name):
    clean_name = str(icon_name or "").strip()
    if not clean_name:
        return ""
    filename = f"{clean_name}.png"
    local_path = os.path.join(app.root_path, "static", "playstyles", filename)
    if os.path.exists(local_path):
        return f"/static/playstyles/{filename}"
    return f"{PLAYSTYLE_CDN_BASE}/{quote(clean_name)}.png"


def _fallback_playstyle_name(code):
    clean_code = str(code or "").strip()
    if not clean_code:
        return ""
    name = re.sub(r"^PLAYSTYLE_", "", clean_code)
    name = re.sub(r"_\d+$", "", name)
    return name.replace("_", " ").title()


def _extract_player_playstyle_codes(player):
    raw_playstyles = player.get("staticPlayStyles")
    if not isinstance(raw_playstyles, list):
        raw_playstyles = player.get("staticPlayStyles_org") or []

    codes = []
    for item in raw_playstyles:
        if isinstance(item, dict):
            value = item.get("idStr") or item.get("icon") or item.get("code")
        else:
            value = item
        code = str(value or "").strip()
        if code and code not in codes:
            codes.append(code)
    return codes


def _extract_player_playstyles(player):
    meta_by_id = _load_playstyle_meta()
    stored_playstyles = player.get("playstyles")
    if isinstance(stored_playstyles, list):
        normalized_items = []
        for item in stored_playstyles:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or item.get("idStr") or item.get("icon") or "").strip()
            if not code:
                continue
            meta = meta_by_id.get(code, {})
            icon_name = item.get("icon") or meta.get("icon") or code
            normalized_items.append(
                {
                    "code": code,
                    "name": str(item.get("name") or meta.get("korname") or _fallback_playstyle_name(code)).strip(),
                    "description": str(item.get("description") or meta.get("description") or "").strip(),
                    "category": str(item.get("category") or meta.get("category") or "").strip(),
                    "level": item.get("level") if item.get("level") is not None else meta.get("level"),
                    "imageUrl": str(item.get("imageUrl") or _playstyle_image_url(icon_name)).strip(),
                }
            )
        if normalized_items:
            return normalized_items

    playstyles = []
    for code in _extract_player_playstyle_codes(player):
        meta = meta_by_id.get(code, {})
        icon_name = meta.get("icon") or code
        name = str(meta.get("korname") or _fallback_playstyle_name(code)).strip()
        playstyles.append(
            {
                "code": code,
                "name": name,
                "description": str(meta.get("description") or "").strip(),
                "category": str(meta.get("category") or "").strip(),
                "level": meta.get("level"),
                "imageUrl": _playstyle_image_url(icon_name),
            }
        )
    return playstyles


def _extract_player_playstyle_filter_values(player):
    values = set()
    for item in _extract_player_playstyles(player):
        for key in ("name", "code"):
            normalized = _normalize_filter_text(item.get(key))
            if normalized:
                values.add(normalized)
    return values


def _get_skill_name(skill_id):
    normalized = str(skill_id or "").strip()
    if not normalized:
        return ""
    if normalized in SKILL_ID_NAME_MAP:
        return SKILL_ID_NAME_MAP[normalized]

    # Official squadmaker style ids such as 26031 point to skill ids such as 261031.
    if re.fullmatch(r"260\d{2}", normalized):
        converted = f"261{normalized[-3:]}"
        if converted in SKILL_ID_NAME_MAP:
            return SKILL_ID_NAME_MAP[converted]

    return f"스킬 {normalized}"


def _fcplayer_asset_url(folder, name):
    clean_name = str(name or "").strip()
    if not clean_name:
        return ""
    return f"{FCPLAYER_ASSET_BASE}/{folder}/{quote(clean_name)}.png"


def _stat_codes_for_skill_name(name):
    return NEW_SKILL_STAT_CODES.get(name) or SKILL_BOOST_STAT_CODES.get(name) or []


def _extract_player_skill_items(player):
    boost_name = str(player.get("skillBoostName") or "").strip()
    if boost_name:
        level = player.get("skillBoostLevel")
        return {
            "type": "boost",
            "label": "스킬부스트",
            "items": [
                {
                    "name": boost_name,
                    "level": level,
                    "slot": "",
                    "kind": "BOOST",
                    "imageUrl": _fcplayer_asset_url("skill-boosts", boost_name),
                    "statCodes": _stat_codes_for_skill_name(boost_name),
                }
            ],
        }

    items = []
    seen = set()
    display_type = ""

    def add_item(name, level=None, slot="", kind="", image_folder="skills", item_type="skill"):
        clean_name = str(name or "").strip()
        if not clean_name:
            return
        key = (clean_name, str(slot or ""), str(kind or ""))
        if key in seen:
            return
        seen.add(key)
        nonlocal display_type
        if item_type == "skill":
            display_type = "skill"
        elif not display_type:
            display_type = "boost"
        items.append(
            {
                "name": clean_name,
                "level": level,
                "slot": slot or "",
                "kind": kind or "",
                "imageUrl": _fcplayer_asset_url(image_folder, clean_name),
                "statCodes": _stat_codes_for_skill_name(clean_name),
            }
        )

    raw_skills = player.get("skills") or []
    if isinstance(raw_skills, list):
        for skill in raw_skills:
            if isinstance(skill, dict):
                skill_id = str(skill.get("id", "")).strip()
                kind = skill.get("kind") or skill.get("type") or ""
                item_type = "skill" if skill_id.startswith("262") or str(kind).upper() in {"BASE", "ULTIMATE"} else "boost"
                image_folder = "skills" if item_type == "skill" else "skill-boosts"
                if skill.get("name"):
                    add_item(
                        skill.get("name"),
                        skill.get("level", skill.get("lv")),
                        skill.get("slot"),
                        kind,
                        image_folder,
                        item_type,
                    )
                else:
                    add_item(
                        _get_skill_name(skill_id),
                        skill.get("level", skill.get("lv")),
                        skill.get("slot"),
                        kind,
                        image_folder,
                        item_type,
                    )
            else:
                add_item(skill, image_folder="skills", item_type="skill")

    raw_skill_info = player.get("skillInfo") or []
    if not items and isinstance(raw_skill_info, list):
        for skill in raw_skill_info:
            if isinstance(skill, dict):
                skill_id = str(skill.get("id", "")).strip()
                item_type = "skill" if skill_id.startswith("262") else "boost"
                add_item(
                    _get_skill_name(skill_id),
                    skill.get("lv", skill.get("level")),
                    image_folder="skills" if item_type == "skill" else "skill-boosts",
                    item_type=item_type,
                )

    if (
        not items
        and player.get("skillStyleId")
        and _player_skill_system(player) == "boost"
    ):
        add_item(_get_skill_name(player.get("skillStyleId")), image_folder="skill-boosts", item_type="boost")

    return {
        "type": display_type if items else "",
        "label": "스킬" if display_type == "skill" else ("스킬부스트" if display_type == "boost" else ""),
        "items": items,
    }


def _extract_player_skills(player):
    skill_display = _extract_player_skill_items(player)
    labels = []
    for item in skill_display.get("items", []):
        label = item.get("name")
        level = item.get("level")
        if level is not None and str(level).strip() != "":
            label = f"{label} Lv.{level}"
        if label and label not in labels:
            labels.append(label)
    return labels


def _extract_player_skill_or_boost_names(player):
    names = []

    def add_name(value):
        name = str(value or "").strip()
        if name and name not in names:
            names.append(name)

    add_name(player.get("skillBoostName"))

    raw_skills = player.get("skills") or []
    if isinstance(raw_skills, list):
        for skill in raw_skills:
            if isinstance(skill, dict):
                add_name(skill.get("name") or _get_skill_name(skill.get("id")))
            else:
                add_name(skill)

    raw_skill_info = player.get("skillInfo") or []
    if isinstance(raw_skill_info, list):
        for skill in raw_skill_info:
            if isinstance(skill, dict):
                add_name(skill.get("name") or _get_skill_name(skill.get("id")))
            else:
                add_name(skill)

    if (
        not names
        and player.get("skillStyleId")
        and _player_skill_system(player) == "boost"
    ):
        add_name(_get_skill_name(player.get("skillStyleId")))

    return names


def _clean_filter_values(values, uppercase=False):
    cleaned = []
    for raw in values:
        for token in str(raw or "").split(","):
            value = token.strip()
            if not value:
                continue
            if uppercase:
                value = value.upper()
            if value not in cleaned:
                cleaned.append(value)
    return cleaned


def _get_filter_values(name, uppercase=False):
    return _clean_filter_values(request.args.getlist(name), uppercase=uppercase)


def _normalize_filter_text(value):
    return re.sub(r"\s+", "", str(value or "").strip()).lower()


def _extract_player_raised_stat_codes(player):
    stat_codes = set()
    for item in _extract_player_skill_items(player).get("items", []):
        stat_codes.update(item.get("statCodes") or [])
    return stat_codes


def _is_review_defender(player):
    positions = set(_extract_player_positions(player))
    primary_position = _extract_primary_player_position(player)
    if primary_position:
        positions.add(primary_position)
    return not positions.isdisjoint(DEFENDER_REVIEW_POSITIONS)


def _review_rating_fields_for_player(player):
    if _is_review_defender(player):
        return PLAYER_REVIEW_DEFENDER_RATING_FIELDS
    return PLAYER_REVIEW_RATING_FIELDS


def _review_skill_move_labels(player):
    if _is_review_defender(player):
        return []
    move = _normalize_filter_text(player.get("skillMovesName"))
    level = player.get("skillMovesLevel")
    star_level = None
    if level is not None and str(level).strip() != "":
        try:
            star_level = int(level) + 1
        except (TypeError, ValueError):
            star_level = None

    if "라크로케타" in move:
        return ["개인기"]
    if "플립플랩" in move or "플립플랩" in move.replace(" ", ""):
        return ["개인기"]
    return ["개인기"]


def _player_review_collection(cid):
    if not fs:
        return None
    return fs.collection("player_reviews").document(str(cid)).collection("reviews")


_PENDING_PLAYER_REVIEWS = {}
PLAYER_REVIEW_CACHE_PATH = os.path.join(app.instance_path, "player_reviews_cache.json")
PLAYER_REVIEW_SUMMARY_PATH = os.path.join(app.instance_path, "player_review_summaries.json")
_LATEST_PLAYER_REVIEWS_REMOTE_CACHE = {"fetched_at": 0.0, "reviews": []}
LATEST_PLAYER_REVIEWS_REMOTE_TTL = 90
_PLAYER_REVIEWS_FIRESTORE_CACHE = {}
_PLAYER_REVIEWS_FIRESTORE_CACHE_LOCK = threading.Lock()
PLAYER_REVIEWS_FIRESTORE_CACHE_TTL = 120


def _invalidate_player_reviews_firestore_cache(*cids):
    target_cids = {str(cid) for cid in cids if cid not in (None, "")}
    with _PLAYER_REVIEWS_FIRESTORE_CACHE_LOCK:
        if target_cids:
            for cache_key in list(_PLAYER_REVIEWS_FIRESTORE_CACHE):
                cached_cids = set(cache_key[0])
                if target_cids.intersection(cached_cids):
                    _PLAYER_REVIEWS_FIRESTORE_CACHE.pop(cache_key, None)
        else:
            _PLAYER_REVIEWS_FIRESTORE_CACHE.clear()
    _LATEST_PLAYER_REVIEWS_REMOTE_CACHE["fetched_at"] = 0.0
    _LATEST_PLAYER_REVIEWS_REMOTE_CACHE["reviews"] = []


def _load_player_review_summaries():
    try:
        with open(PLAYER_REVIEW_SUMMARY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"Player review summary read failed: {e}")
        return {}


def _save_player_review_summaries(summaries):
    try:
        os.makedirs(app.instance_path, exist_ok=True)
        with open(PLAYER_REVIEW_SUMMARY_PATH, "w", encoding="utf-8") as f:
            json.dump(summaries, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Player review summary write failed: {e}")
        raise


def _get_player_review_summary(cid):
    summary = _load_player_review_summaries().get(str(cid))
    if not isinstance(summary, dict):
        return None
    has_content = any(str(summary.get(key) or "").strip() for key in ("summary", "strengths", "weaknesses"))
    return summary if has_content else None


def _parse_player_review_summary_json(raw_text):
    text = str(raw_text or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().lower() in {"```", "```json"}:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("JSON 최상위 값은 객체여야 합니다.")

    def normalize_value(*keys):
        value = next((data.get(key) for key in keys if data.get(key) is not None), "")
        if isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
            return "\n".join(f"• {item}" for item in items)
        if isinstance(value, str):
            return value.strip()
        if value is None:
            return ""
        raise ValueError(f"{keys[0]} 값은 문자열 또는 문자열 배열이어야 합니다.")

    parsed = {
        "summary": normalize_value("final_verdict", "summary", "conclusion"),
        "strengths": normalize_value("pros", "strengths"),
        "weaknesses": normalize_value("cons", "weaknesses"),
    }
    if not any(parsed.values()):
        raise ValueError("pros, cons, final_verdict 중 하나 이상의 내용이 필요합니다.")
    return parsed


def _is_player_summary_admin():
    return bool(session.get("player_summary_admin"))


def _verify_player_summary_admin_password(password):
    expected = app.config.get("PLAYER_SUMMARY_ADMIN_PASSWORD", "")
    return bool(expected) and secrets.compare_digest(str(password or ""), expected)


def _find_admin_summary_players(query, limit=40):
    query = str(query or "").strip()
    if not query:
        return []

    normalized_query = _normalize_name_for_match(query)
    matches = []
    seen = set()
    for player in PLAYER_DATA:
        cid = player.get("cid")
        if not cid or cid in seen:
            continue

        player_name = str(player.get("playerKor") or "")
        player_class = str(player.get("className") or "")
        haystacks = [
            str(cid),
            _normalize_name_for_match(player_name),
            _normalize_name_for_match(player_class),
            _normalize_name_for_match(f"{player_class} {player_name}"),
        ]
        if query == str(cid) or any(normalized_query and normalized_query in item for item in haystacks):
            seen.add(cid)
            matches.append(_apply_local_assets(_normalize_player_record(player.copy())))
            if len(matches) >= limit:
                break

    matches.sort(key=lambda p: (-(p.get("ovr") or 0), p.get("className") or "", p.get("playerKor") or ""))
    return matches


def _load_player_review_cache():
    try:
        with open(PLAYER_REVIEW_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"Player review cache read failed: {e}")
        return {}


def _save_player_review_cache(cache):
    try:
        os.makedirs(app.instance_path, exist_ok=True)
        with open(PLAYER_REVIEW_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Player review cache write failed: {e}")


def _cache_player_review(cid, review_doc):
    user_id = review_doc.get("user_id")
    if user_id is None:
        return
    cache = _load_player_review_cache()
    player_key = str(cid)
    cache.setdefault(player_key, {})
    cached_doc = dict(review_doc)
    cached_doc.pop("created_at", None)
    cached_doc.pop("updated_at", None)
    cached_doc["id"] = str(user_id)
    cached_doc["created_at_display"] = _format_kst_datetime(fallback_iso=cached_doc.get("created_at_iso"))
    cache[player_key][str(user_id)] = cached_doc
    _save_player_review_cache(cache)
    _invalidate_player_reviews_firestore_cache(cid)


def _delete_cached_player_review(cids, user_id):
    if user_id is None:
        return
    cache = _load_player_review_cache()
    changed = False
    for cid in cids:
        player_reviews = cache.get(str(cid))
        if isinstance(player_reviews, dict) and str(user_id) in player_reviews:
            player_reviews.pop(str(user_id), None)
            changed = True
    if changed:
        _save_player_review_cache(cache)
        _invalidate_player_reviews_firestore_cache(*cids)


def _get_cached_player_reviews(*cids):
    cache = _load_player_review_cache()
    reviews = []
    seen_keys = []
    for cid in cids:
        key = str(cid)
        if not key or key in seen_keys:
            continue
        seen_keys.append(key)
        player_reviews = cache.get(key)
        if isinstance(player_reviews, dict):
            reviews.extend(_format_player_review_data(dict(item)) for item in player_reviews.values() if isinstance(item, dict))
        elif isinstance(player_reviews, list):
            reviews.extend(_format_player_review_data(dict(item)) for item in player_reviews if isinstance(item, dict))
    return reviews


def _get_current_user_player_review(cid, player=None):
    if not current_user.is_authenticated:
        return None
    review_cids = _review_cid_candidates(
        cid,
        player.get("cid") if player else None,
        player.get("fcplayerCardId") if player else None,
    )

    if fs:
        for review_cid in review_cids:
            try:
                doc = _player_review_collection(review_cid).document(str(current_user.id)).get(retry=None, timeout=8)
                if getattr(doc, "exists", False):
                    review = _format_player_review_doc(doc)
                    review["_source_cid"] = str(review_cid)
                    return review
            except Exception as e:
                print(f"Firestore current player review read failed for {review_cid}: {e}")

    pending = _PENDING_PLAYER_REVIEWS.get((str(cid), str(current_user.id)))
    if pending:
        return _format_player_review_data(dict(pending))

    for review in _get_cached_player_reviews(*review_cids):
        if str(review.get("user_id")) == str(current_user.id):
            return review
    return None


def _delete_current_user_player_review(cid, player=None):
    review_cids = _review_cid_candidates(
        cid,
        player.get("cid") if player else None,
        player.get("fcplayerCardId") if player else None,
    )
    deleted = False
    if fs:
        for review_cid in review_cids:
            try:
                _player_review_collection(review_cid).document(str(current_user.id)).delete(retry=None, timeout=8)
                deleted = True
            except Exception as e:
                print(f"Firestore player review delete failed for {review_cid}: {e}")
    _delete_cached_player_review(review_cids, current_user.id)
    for review_cid in review_cids:
        _PENDING_PLAYER_REVIEWS.pop((str(review_cid), str(current_user.id)), None)
    _invalidate_player_reviews_firestore_cache(*review_cids)
    return deleted


def _format_player_review_doc(doc):
    data = doc.to_dict() or {}
    data["id"] = doc.id
    return _format_player_review_data(data)


def _review_player_context(review):
    raw_cid = review.get("player_cid")
    try:
        cid = int(raw_cid)
    except (TypeError, ValueError):
        return None
    return _get_local_player_by_cid(cid)


def _fallback_player_review_title(review, player=None):
    player = player or _review_player_context(review) or {}
    name = str(review.get("player_name") or player.get("playerKor") or "선수").strip()
    ovr = review.get("player_ovr")
    if ovr in (None, ""):
        ovr = player.get("ovr")
    ovr_text = str(ovr).strip() if ovr not in (None, "") else ""
    return f"{ovr_text} {name} 리뷰" if ovr_text else f"{name} 리뷰"


def _hydrate_player_review_metadata(review):
    data = dict(review or {})
    player = _review_player_context(data) or {}
    review_id = data.get("id") or data.get("user_id")
    data["id"] = str(review_id or "")
    data["title"] = str(data.get("title") or "").strip()[:80] or _fallback_player_review_title(data, player)
    data["player_name"] = str(data.get("player_name") or player.get("playerKor") or "선수").strip()
    data["player_class"] = str(data.get("player_class") or player.get("className") or "").strip()
    data["player_ovr"] = data.get("player_ovr") if data.get("player_ovr") not in (None, "") else player.get("ovr")
    data["player_position"] = str(data.get("player_position") or player.get("position") or "").strip().upper()
    data["player_pimage"] = str(data.get("player_pimage") or player.get("pimage") or "").strip()
    data["player_bimage"] = str(data.get("player_bimage") or player.get("bimage") or "").strip()
    review_text = str(data.get("review_text") or "").strip()
    data["excerpt"] = re.sub(r"\s+", " ", review_text)[:220]
    date_display = str(data.get("created_at_display") or "-")
    data["created_date_display"] = date_display[5:10].replace("-", ".") if len(date_display) >= 10 else date_display
    return data


def _format_player_review_data(data):
    created_at = data.get("created_at")
    data["created_at_display"] = _format_kst_datetime(created_at, data.get("created_at_iso"))
    ratings = data.get("ratings") if isinstance(data.get("ratings"), dict) else {}
    data["ratings"] = ratings
    data["rating_notes"] = data.get("rating_notes") if isinstance(data.get("rating_notes"), dict) else {}
    rating_values = []
    for value in ratings.values():
        try:
            rating_values.append(float(value))
        except (TypeError, ValueError):
            pass
    for item in data.get("skill_move_ratings") or []:
        try:
            rating_values.append(float(item.get("rating")))
        except (AttributeError, TypeError, ValueError):
            pass
    data["average_rating"] = round(sum(rating_values) / len(rating_values), 1) if rating_values else None
    return _hydrate_player_review_metadata(data)


def _all_cached_player_reviews():
    reviews = []
    cache = _load_player_review_cache()
    for player_cid, player_reviews in cache.items():
        if isinstance(player_reviews, dict):
            values = player_reviews.values()
        elif isinstance(player_reviews, list):
            values = player_reviews
        else:
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            review = dict(item)
            review.setdefault("player_cid", player_cid)
            reviews.append(_format_player_review_data(review))
    for pending in _PENDING_PLAYER_REVIEWS.values():
        if isinstance(pending, dict):
            reviews.append(_format_player_review_data(dict(pending)))
    return reviews


def _latest_remote_player_reviews(limit=30):
    if not fs:
        return []
    now = time.time()
    cached = _LATEST_PLAYER_REVIEWS_REMOTE_CACHE
    if now - float(cached.get("fetched_at") or 0) < LATEST_PLAYER_REVIEWS_REMOTE_TTL:
        return list(cached.get("reviews") or [])

    reviews = []
    try:
        query = (
            fs.collection_group("reviews")
            .order_by("created_at_iso", direction=firestore.Query.DESCENDING)
            .limit(max(12, min(int(limit or 30), 60)))
        )
        reviews = [_format_player_review_doc(doc) for doc in query.stream(retry=None, timeout=1.5)]
    except Exception as e:
        print(f"Latest player review feed read failed: {e}")
        error_text = str(e).lower()
        if "index" in error_text or "failedprecondition" in error_text or "failed precondition" in error_text:
            try:
                query = fs.collection_group("reviews").limit(max(12, min(int(limit or 30), 60)))
                reviews = [_format_player_review_doc(doc) for doc in query.stream(retry=None, timeout=1.5)]
            except Exception as fallback_error:
                print(f"Latest player review fallback read failed: {fallback_error}")
                reviews = []

    cached["fetched_at"] = now
    cached["reviews"] = reviews
    return list(reviews)


def _attach_review_comment_counts(reviews):
    try:
        rows = (
            db.session.query(
                PlayerReviewComment.player_cid,
                PlayerReviewComment.review_id,
                func.count(PlayerReviewComment.id),
            )
            .group_by(PlayerReviewComment.player_cid, PlayerReviewComment.review_id)
            .all()
        )
        counts = {(str(cid), str(review_id)): int(count or 0) for cid, review_id, count in rows}
    except Exception as e:
        print(f"Player review comment count read failed: {e}")
        counts = {}
    for review in reviews:
        review["comment_count"] = counts.get((str(review.get("player_cid")), str(review.get("id"))), 0)
    return reviews


def _get_latest_player_reviews(limit=50, include_remote=True):
    limit = max(1, min(int(limit or 50), 100))
    reviews = _all_cached_player_reviews()
    if include_remote and len(reviews) < min(limit, 3):
        reviews.extend(_latest_remote_player_reviews(max(limit, 20)))
    reviews = [_hydrate_player_review_metadata(review) for review in reviews]
    reviews = _dedupe_player_reviews(reviews, limit=max(limit, 100))
    return _attach_review_comment_counts(reviews[:limit])


def _get_all_player_reviews(include_remote=True):
    reviews = _all_cached_player_reviews()
    if include_remote and not reviews:
        reviews.extend(_latest_remote_player_reviews(100))
    reviews = [_hydrate_player_review_metadata(review) for review in reviews]
    reviews = _dedupe_player_reviews(reviews, limit=None)
    return _attach_review_comment_counts(reviews)


def _get_player_review_by_id(cid, review_id):
    review_id = str(review_id or "").strip()
    for pending in _PENDING_PLAYER_REVIEWS.values():
        if not isinstance(pending, dict):
            continue
        if str(pending.get("player_cid")) == str(cid) and str(pending.get("id") or pending.get("user_id")) == review_id:
            return _format_player_review_data(dict(pending))
    for review in _get_cached_player_reviews(cid):
        if str(review.get("id") or review.get("user_id")) == review_id:
            return _hydrate_player_review_metadata(review)

    for review in _LATEST_PLAYER_REVIEWS_REMOTE_CACHE.get("reviews") or []:
        if str(review.get("player_cid")) == str(cid) and str(review.get("id") or review.get("user_id")) == review_id:
            return _hydrate_player_review_metadata(review)

    if fs:
        try:
            doc = _player_review_collection(cid).document(review_id).get(retry=None, timeout=4)
            if getattr(doc, "exists", False):
                return _format_player_review_doc(doc)
        except Exception as e:
            print(f"Player review detail read failed for {cid}/{review_id}: {e}")

    for review in _get_player_reviews_from_firestore(cid, limit=60):
        if str(review.get("id") or review.get("user_id")) == review_id:
            return _hydrate_player_review_metadata(review)
    return None


def _all_home_review_activity():
    items = []
    for review in _get_all_player_reviews(include_remote=True):
        item = dict(review)
        item["kind"] = "review"
        item["kind_label"] = "선수 리뷰"
        item["sort_at"] = str(item.get("created_at_iso") or "")
        items.append(item)

    for summary_key, summary in _load_player_review_summaries().items():
        if not isinstance(summary, dict):
            continue
        try:
            # 예전에 저장한 요약에는 player_cid가 없을 수 있으므로 JSON 키도 허용한다.
            cid = int(summary.get("player_cid") or summary_key)
        except (TypeError, ValueError):
            continue
        player = _get_local_player_by_cid(cid) or {}
        player_name = str(summary.get("player_name") or player.get("playerKor") or "선수")
        player_ovr = player.get("ovr")
        title_prefix = f"{player_ovr} " if player_ovr not in (None, "") else ""
        text = str(summary.get("summary") or summary.get("strengths") or summary.get("weaknesses") or "").strip()
        updated_at = str(summary.get("updated_at_iso") or summary.get("created_at_iso") or "")
        date_display = _format_kst_datetime(fallback_iso=updated_at)
        items.append({
            "kind": "summary",
            "kind_label": "선수 장단점",
            "player_cid": cid,
            "player_name": player_name,
            "player_class": str(summary.get("player_class") or player.get("className") or ""),
            "player_ovr": player_ovr,
            "player_position": str(player.get("position") or "").upper(),
            "player_pimage": player.get("pimage") or "",
            "player_bimage": player.get("bimage") or "",
            "title": f"{title_prefix}{player_name} 장단점",
            "excerpt": re.sub(r"\s+", " ", text)[:220],
            "username": "피모북 관리자",
            "created_at_display": date_display,
            "created_date_display": date_display[5:10].replace("-", ".") if len(date_display) >= 10 else date_display,
            "sort_at": updated_at,
            "average_rating": None,
            "comment_count": 0,
        })

    items.sort(key=lambda item: str(item.get("sort_at") or ""), reverse=True)
    return items


def _latest_home_review_activity(limit=3):
    limit = max(1, int(limit or 3))
    items = _all_home_review_activity()
    selected = items[:limit]
    available_kinds = {item.get("kind") for item in items}
    selected_kinds = {item.get("kind") for item in selected}
    if limit > 1 and {"review", "summary"}.issubset(available_kinds) and len(selected_kinds) == 1:
        missing_kind = next(kind for kind in ("review", "summary") if kind not in selected_kinds)
        missing_item = next((item for item in items if item.get("kind") == missing_kind), None)
        if missing_item:
            selected[-1] = missing_item
            selected.sort(key=lambda item: str(item.get("sort_at") or ""), reverse=True)
    return selected


def _review_display_reviews_for_player(reviews, player):
    normalized_reviews = []
    hide_skill_moves = _is_review_defender(player)
    for review in reviews:
        review = dict(review)
        if hide_skill_moves:
            review["skill_move_ratings"] = []
        else:
            skill_move_ratings = []
            for item in review.get("skill_move_ratings") or []:
                if not isinstance(item, dict):
                    continue
                item = dict(item)
                label_key = _normalize_filter_text(item.get("label"))
                if "라크로케타" in label_key or "크로케타" in label_key or "플립플랩" in label_key:
                    item["label"] = "개인기"
                skill_move_ratings.append(item)
            review["skill_move_ratings"] = skill_move_ratings
        normalized_reviews.append(review)
    return normalized_reviews


def _remember_pending_player_review(cid, review_doc):
    user_id = review_doc.get("user_id")
    if user_id is None:
        return
    pending = dict(review_doc)
    pending.pop("created_at", None)
    pending.pop("updated_at", None)
    pending["id"] = str(user_id)
    pending["created_at_display"] = _format_kst_datetime(fallback_iso=pending.get("created_at_iso"))
    pending = _format_player_review_data(pending)
    _PENDING_PLAYER_REVIEWS[(str(cid), str(user_id))] = pending


def _merge_pending_player_review(cid, reviews):
    if not current_user.is_authenticated:
        return reviews
    key = (str(cid), str(current_user.id))
    pending = _PENDING_PLAYER_REVIEWS.get(key)
    if not pending:
        return reviews
    pending_user_id = str(pending.get("user_id"))
    has_saved_review = any(str(review.get("user_id")) == pending_user_id for review in reviews)
    if has_saved_review:
        _PENDING_PLAYER_REVIEWS.pop(key, None)
        return reviews
    return [pending] + reviews


def _find_current_user_review(reviews):
    if not current_user.is_authenticated:
        return None
    return next((review for review in reviews if str(review.get("user_id")) == str(current_user.id)), None)


def _dedupe_player_reviews(reviews, limit=50):
    seen = set()
    unique = []
    for review in reviews:
        key = (
            str(review.get("player_cid") or ""),
            str(review.get("user_id") or review.get("id") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(review)
    unique.sort(key=lambda item: str(item.get("created_at_iso") or item.get("created_at_display") or ""), reverse=True)
    return unique[:limit] if limit else unique


def _review_cid_candidates(*values):
    candidates = []
    seen = set()
    for value in values:
        if value in (None, ""):
            continue
        for candidate in (value, str(value)):
            key = (type(candidate).__name__, str(candidate))
            if key not in seen:
                seen.add(key)
                candidates.append(candidate)
    return candidates


def _get_player_reviews_from_firestore(cid, limit=50, extra_cids=None):
    review_cids = _review_cid_candidates(cid, *(extra_cids or []))
    if not fs or not review_cids:
        return []
    cache_key = (
        tuple(str(review_cid) for review_cid in review_cids),
        int(limit or 50),
    )
    now = time.time()
    with _PLAYER_REVIEWS_FIRESTORE_CACHE_LOCK:
        cached = _PLAYER_REVIEWS_FIRESTORE_CACHE.get(cache_key)
    if cached and now - float(cached.get("fetched_at") or 0) < PLAYER_REVIEWS_FIRESTORE_CACHE_TTL:
        return [dict(review) for review in cached.get("reviews") or []]

    reviews = []

    for review_cid in review_cids:
        collection = _player_review_collection(review_cid)
        if not collection:
            continue
        try:
            reviews.extend(_format_player_review_doc(doc) for doc in collection.limit(limit).stream(retry=None, timeout=8))
        except Exception as e:
            print(f"Firestore player review direct read failed for {review_cid}: {e}")

        try:
            parent_doc = fs.collection("player_reviews").document(str(review_cid)).get(retry=None, timeout=8)
            if getattr(parent_doc, "exists", False):
                parent_data = parent_doc.to_dict() or {}
                if parent_data.get("ratings") or parent_data.get("review_text"):
                    parent_data["id"] = parent_doc.id
                    reviews.append(_format_player_review_data(parent_data))
                nested_reviews = parent_data.get("reviews")
                if isinstance(nested_reviews, list):
                    for idx, item in enumerate(nested_reviews):
                        if isinstance(item, dict):
                            item = dict(item)
                            item.setdefault("id", f"{parent_doc.id}-{idx}")
                            reviews.append(_format_player_review_data(item))
                elif isinstance(nested_reviews, dict):
                    for key, item in nested_reviews.items():
                        if isinstance(item, dict):
                            item = dict(item)
                            item.setdefault("id", str(key))
                            reviews.append(_format_player_review_data(item))
        except Exception as e:
            print(f"Firestore player review parent read failed for {review_cid}: {e}")

    if not reviews and fs:
        fallback_queries = []
        for cid_value in review_cids:
            fallback_queries.extend(
                [
                    _fs_where(fs.collection_group("reviews"), "player_cid", "==", cid_value).limit(limit),
                    _fs_where(fs.collection("player_reviews"), "player_cid", "==", cid_value).limit(limit),
                    _fs_where(fs.collection("reviews"), "player_cid", "==", cid_value).limit(limit),
                ]
            )

        for query in fallback_queries:
            try:
                reviews.extend(_format_player_review_doc(doc) for doc in query.stream(retry=None, timeout=8))
            except Exception as e:
                print(f"Firestore player review fallback read failed for {cid}: {e}")

    reviews = _dedupe_player_reviews(reviews, limit=limit)
    with _PLAYER_REVIEWS_FIRESTORE_CACHE_LOCK:
        _PLAYER_REVIEWS_FIRESTORE_CACHE[cache_key] = {
            "fetched_at": now,
            "reviews": [dict(review) for review in reviews],
        }
    print(f"Firestore player review read for {cid}: {len(reviews)} reviews from cids {review_cids}")
    return reviews


def _parse_rating_field(name):
    value = request.form.get(name, type=int)
    if value is None or value < 1 or value > 10:
        raise ValueError("모든 별점은 1점부터 10점까지 선택해야 합니다.")
    return value


def _parse_short_note_field(name, max_length=160):
    return request.form.get(name, "").strip()[:max_length]


def _review_meaningful_text(value):
    text = re.sub(r"\s+", "", str(value or "").strip().lower())
    return re.sub(r"[^0-9a-z가-힣]", "", text)


def _is_low_effort_review_fragment(value, min_chars=MIN_REVIEW_NOTE_CHARS):
    meaningful = _review_meaningful_text(value)
    if len(meaningful) < min_chars:
        return True
    if meaningful in LOW_EFFORT_REVIEW_TERMS:
        return True
    if re.fullmatch(r"(.)\1{4,}", meaningful):
        return True
    if re.search(r"(.)\1{7,}", meaningful):
        return True
    unique_ratio = len(set(meaningful)) / max(len(meaningful), 1)
    if len(meaningful) >= 12 and unique_ratio < 0.22:
        return True
    return False


def _validate_player_review_quality(review_text, rating_notes, skill_move_ratings):
    if _is_low_effort_review_fragment(review_text, min_chars=MIN_REVIEW_TEXT_CHARS):
        return f"전체 리뷰를 {MIN_REVIEW_TEXT_CHARS}자 이상, 실제 사용감이 드러나게 작성해주세요."

    note_values = [
        str(value or "").strip()
        for value in (rating_notes or {}).values()
        if str(value or "").strip()
    ]
    note_values.extend(
        str(item.get("note") or "").strip()
        for item in (skill_move_ratings or [])
        if isinstance(item, dict) and str(item.get("note") or "").strip()
    )

    meaningful_notes = [
        note
        for note in note_values
        if not _is_low_effort_review_fragment(note, min_chars=MIN_REVIEW_NOTE_CHARS)
    ]
    if len(meaningful_notes) < MIN_MEANINGFUL_REVIEW_NOTES:
        return f"항목별 짧은 평가를 {MIN_MEANINGFUL_REVIEW_NOTES}개 이상 구체적으로 작성해주세요."

    normalized_notes = [_review_meaningful_text(note) for note in meaningful_notes]
    repeated_count = max((normalized_notes.count(note) for note in set(normalized_notes)), default=0)
    if repeated_count >= 3:
        return "같은 짧은 평가를 여러 항목에 반복해서 작성할 수 없습니다."

    return None


def _safe_local_next_url(default_url):
    next_url = request.form.get("next") or request.args.get("next") or ""
    if next_url:
        parsed_next = urlparse(next_url)
        if not parsed_next.netloc and next_url.startswith("/"):
            return next_url
    return default_url


def _render_player_review_form(player, move_labels, review=None, form_action=None, form_mode="create"):
    return render_template(
        "player_review_form.html",
        player=player,
        review=review or {},
        form_action=form_action or url_for("submit_player_firebase_review_post", cid=player.get("review_cid") or player.get("cid")),
        form_mode=form_mode,
        review_skill_move_labels=move_labels,
        review_rating_fields=_review_rating_fields_for_player(player),
        review_tiers=PLAYER_REVIEW_TIERS,
        review_formations=PLAYER_REVIEW_FORMATIONS,
        review_positions=PLAYER_REVIEW_POSITIONS,
        enhance_totals=ENHANCE_LEVEL_TOTALS,
        stat_labels=STAT_CODE_LABELS,
        robots_meta="noindex,follow",
    )


def _save_player_review_from_request(cid, player, move_labels, existing_review=None, success_message="선수 리뷰가 저장되었습니다.", error_endpoint="submit_player_firebase_review"):
    collection = _player_review_collection(cid)
    if not collection:
        flash("Firebase 리뷰 저장소가 설정되지 않았습니다.", "danger")
        return redirect(url_for(error_endpoint, cid=cid))

    if existing_review is None:
        existing_review = _get_current_user_player_review(cid, player)
    is_new_review = existing_review is None

    formation = request.form.get("formation", "").strip()
    used_position = request.form.get("used_position", "").strip().upper()
    tier = request.form.get("tier", "").strip()
    enhance_level = request.form.get("enhance_level", type=int)
    review_title = request.form.get("title", "").strip()
    review_text = request.form.get("review_text", "").strip()

    if len(review_title) < 2 or len(review_title) > 80:
        flash("리뷰 제목을 2자 이상 80자 이내로 입력해주세요.", "danger")
        return redirect(url_for(error_endpoint, cid=cid))
    if formation not in PLAYER_REVIEW_FORMATIONS:
        flash("사용한 포메이션을 선택해주세요.", "danger")
        return redirect(url_for(error_endpoint, cid=cid))
    if used_position not in PLAYER_REVIEW_POSITIONS:
        flash("사용한 포지션을 선택해주세요.", "danger")
        return redirect(url_for(error_endpoint, cid=cid))
    if tier not in PLAYER_REVIEW_TIERS:
        flash("사용자 티어를 선택해주세요.", "danger")
        return redirect(url_for(error_endpoint, cid=cid))
    if enhance_level is None or enhance_level < 0 or enhance_level > MAX_ENHANCE_LEVEL:
        flash("사용한 진화 등급을 선택해주세요.", "danger")
        return redirect(url_for(error_endpoint, cid=cid))

    try:
        ratings = {}
        rating_notes = {}
        for field in _review_rating_fields_for_player(player):
            ratings[field["key"]] = _parse_rating_field(field["field"])
            rating_notes[field["key"]] = _parse_short_note_field(field["note_field"])
        skill_move_ratings = [
            {
                "label": label,
                "rating": _parse_rating_field(f"rating_skill_move_{idx}"),
                "note": _parse_short_note_field(f"note_skill_move_{idx}"),
            }
            for idx, label in enumerate(move_labels)
        ]
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for(error_endpoint, cid=cid))

    skill_config = []
    if _player_has_configurable_skills(player):
        review_skill_items = (player.get("reviewSkillDisplay") or player.get("skillDisplay") or {}).get("items", [])
        base_points = {}
        for idx, skill in enumerate(review_skill_items):
            raw_point = request.form.get(f"skill_config_{idx}", type=int)
            if raw_point is None:
                raw_point = 0
            if raw_point < 0 or raw_point > 10:
                flash("스킬 구성을 선택해주세요.", "danger")
                return redirect(url_for(error_endpoint, cid=cid))

            kind = str(skill.get("_review_kind") or skill.get("kind") or "").upper()
            slot = str(skill.get("_review_slot") or skill.get("slot") or "").upper()
            max_point = 4 if kind == "ULTIMATE" else 2
            if raw_point > max_point:
                flash("스킬 포인트 구성이 올바르지 않습니다.", "danger")
                return redirect(url_for(error_endpoint, cid=cid))
            if kind == "BASE":
                base_points[slot] = raw_point

            skill_config.append(
                {
                    "name": skill.get("name"),
                    "slot": skill.get("_review_slot") or skill.get("slot") or "",
                    "kind": skill.get("_review_kind") or skill.get("kind") or "",
                    "required_base": skill.get("_required_base_slot") or "",
                    "point": raw_point,
                }
            )

        if sum(item["point"] for item in skill_config) > enhance_level:
            flash("스킬 포인트가 사용 진화 등급을 초과했습니다.", "danger")
            return redirect(url_for(error_endpoint, cid=cid))

        for item in skill_config:
            if item.get("kind") == "ULTIMATE" and item.get("point", 0) > 0:
                required_base = item.get("required_base")
                if required_base and base_points.get(required_base, 0) < 2:
                    flash("얼티밋 스킬은 연결된 베이스 스킬을 2단계 찍어야 선택할 수 있습니다.", "danger")
                    return redirect(url_for(error_endpoint, cid=cid))

    quality_error = _validate_player_review_quality(review_text, rating_notes, skill_move_ratings)
    if quality_error:
        flash(quality_error, "danger")
        return redirect(url_for(error_endpoint, cid=cid))

    now_iso = _now_kst_iso()
    review_doc = {
        "player_cid": cid,
        "player_name": player.get("playerKor"),
        "player_class": player.get("className"),
        "player_ovr": player.get("ovr"),
        "player_position": player.get("position"),
        "user_id": current_user.id,
        "username": current_user.username,
        "title": review_title[:80],
        "formation": formation,
        "used_position": used_position,
        "enhance_level": enhance_level,
        "tier": tier,
        "ratings": ratings,
        "rating_notes": rating_notes,
        "skill_move_ratings": skill_move_ratings,
        "skill_config": skill_config,
        "review_text": review_text[:3000],
        "created_at_iso": (existing_review or {}).get("created_at_iso") or now_iso,
        "updated_at_iso": now_iso,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }

    try:
        collection.document(str(current_user.id)).set(review_doc, retry=None, timeout=5)
        _remember_pending_player_review(cid, review_doc)
        _cache_player_review(cid, review_doc)
        flash(success_message, "success")
        if is_new_review:
            try:
                _award_review_points(current_user, cid)
                flash(f"리뷰 작성 보상 {REVIEW_POINT_VALUE}포인트가 지급되었습니다.", "success")
            except Exception as point_error:
                db.session.rollback()
                print(f"Review point award failed for user {current_user.id}, cid {cid}: {point_error}")
                flash("리뷰는 저장됐지만 포인트 지급 중 오류가 발생했습니다.", "warning")
    except Exception as e:
        print(f"Firestore player review write failed for {cid}: {e}")
        flash("리뷰 저장 중 오류가 발생했습니다. Firebase 설정을 확인해주세요.", "danger")
        return redirect(url_for(error_endpoint, cid=cid))

    return redirect(_safe_local_next_url(url_for("player_detail", cid=cid, _anchor="player-reviews")))


def _player_has_configurable_skills(player):
    skill_display = player.get("skillDisplay") or _extract_player_skill_items(player)
    return skill_display.get("type") == "skill" and bool(skill_display.get("items"))


def _review_skill_sort_key(item):
    slot = str(item.get("_review_slot") or item.get("slot") or "").upper().strip()
    kind = str(item.get("_review_kind") or item.get("kind") or "").upper().strip()
    required_base = str(item.get("_required_base_slot") or "").upper().strip()
    name = str(item.get("name") or "")

    column = 99
    base_match = re.search(r"(\d+)", required_base or slot)
    if base_match:
        column = int(base_match.group(1))
    row = 1 if kind == "ULTIMATE" or slot.startswith("U") else 0
    order = 99
    match = re.search(r"(\d+)", slot)
    if match:
        order = int(match.group(1))
    return (column, row, order, name)


def _prepare_review_skill_display(player):
    skill_display = player.get("skillDisplay") or _extract_player_skill_items(player)
    if skill_display.get("type") != "skill":
        return skill_display

    items = list(skill_display.get("items") or [])
    has_slot_or_kind = any(str(item.get("slot") or item.get("kind") or "").strip() for item in items)
    inferred_tree_slots = {}
    if not has_slot_or_kind and len(items) >= 6:
        inferred_tree_slots = {
            0: ("B1", "BASE", ""),
            1: ("U1", "ULTIMATE", "B1"),
            2: ("U1", "ULTIMATE", "B1"),
            3: ("B2", "BASE", ""),
            4: ("U2", "ULTIMATE", "B2"),
            5: ("U2", "ULTIMATE", "B2"),
        }
    for idx, item in enumerate(items):
        item["_original_index"] = idx
        inferred = inferred_tree_slots.get(idx)
        if inferred:
            item["_review_slot"] = inferred[0]
        elif item.get("slot"):
            item["_review_slot"] = item.get("slot")
        elif has_slot_or_kind:
            item["_review_slot"] = f"B{idx + 1}"
        else:
            if idx < 2:
                item["_review_slot"] = f"B{idx + 1}"
            else:
                item["_review_slot"] = f"U{((idx - 2) // 2) + 1}"

        if inferred:
            item["_review_kind"] = inferred[1]
        elif item.get("kind"):
            item["_review_kind"] = item.get("kind")
        elif str(item["_review_slot"]).upper().startswith("U"):
            item["_review_kind"] = "ULTIMATE"
        else:
            item["_review_kind"] = "BASE"

        if inferred:
            item["_required_base_slot"] = inferred[2]
        elif str(item["_review_kind"]).upper() == "ULTIMATE":
            item["_required_base_slot"] = "B1" if idx % 2 == 0 else "B2"
        else:
            item["_required_base_slot"] = ""
    skill_display = dict(skill_display)
    skill_display["items"] = items
    return skill_display


def _configured_skill_bonuses(player, enhance_level, requested_levels):
    """Apply the same skill-point rules used by the detail page."""
    skill_display = _prepare_review_skill_display(player)
    items = list(skill_display.get("items") or [])
    skill_type = str(skill_display.get("type") or "")
    is_gk = str(player.get("position") or "").upper() == "GK"
    try:
        enhance = max(0, min(int(enhance_level), MAX_ENHANCE_LEVEL))
    except (TypeError, ValueError):
        enhance = 0

    levels = []
    for index in range(len(items)):
        try:
            value = int(requested_levels[index])
        except (IndexError, TypeError, ValueError):
            value = 0
        levels.append(max(0, value))

    slot_levels = {}
    bonuses = {}
    labels = []
    spent = 0
    for index, item in enumerate(items):
        slot = str(item.get("_review_slot") or item.get("slot") or "").upper()
        kind = str(item.get("_review_kind") or item.get("kind") or "").upper()
        points = levels[index]
        if skill_type == "boost":
            points = min(points, enhance, len(SKILL_BOOST_LEVEL_VALUES) - 1)
            amount = int(SKILL_BOOST_LEVEL_VALUES[points] or 0)
            level_label = f"Lv.{points}"
        else:
            required_slot = str(item.get("_required_base_slot") or "").upper()
            unlocked = kind != "ULTIMATE" or not required_slot or slot_levels.get(required_slot, 0) >= 2
            max_for_card = 4 if kind == "ULTIMATE" else 2
            points = min(points, max_for_card, max(0, enhance - spent)) if unlocked else 0
            spent += points
            steps = (
                ([7, 6, 6, 5] if is_gk else [6, 5, 5, 4])
                if kind == "ULTIMATE"
                else ([5, 7] if is_gk else [4, 6])
            )
            amount = sum(steps[:points])
            level_label = f"{points}pt"
        if slot:
            slot_levels[slot] = points

        if amount <= 0:
            continue
        for code in item.get("statCodes") or []:
            code = str(code).upper()
            bonuses[code] = bonuses.get(code, 0) + amount
        name = str(item.get("name") or "스킬")
        labels.append(f"{name} {level_label} +{amount}")

    return bonuses, labels


def _build_review_player_context(cid):
    player = _get_local_player_by_cid(cid)
    if not player:
        return None

    skill_display = _extract_player_skill_items(player)
    if not skill_display.get("items"):
        player = _merge_fcplayer_skill_data(player)
        skill_display = _extract_player_skill_items(player)
    player["review_cid"] = cid
    player["skillDisplay"] = skill_display
    player["reviewSkillDisplay"] = _prepare_review_skill_display(player)
    player["initialEnhance"] = int(player.get("enhance") or 0)
    return player


def _normalize_team_for_match(value):
    normalized = _normalize_filter_text(value)
    normalized = re.sub(r"\((?:임대|loan)\)", "", normalized, flags=re.IGNORECASE)
    normalized = normalized.replace("아스날", "아스널")
    normalized = normalized.replace("롬바르디아fc", "인테르")
    normalized = normalized.replace("라티움", "ss라치오")
    normalized = normalized.replace("나폴리fc", "ssc나폴리")
    normalized = re.sub(r"(?:fc|cf|sc|afc|ac)$", "", normalized, flags=re.IGNORECASE)
    return normalized


def _player_identity_key(player):
    pid = player.get("pid")
    if pid not in (None, ""):
        return f"pid:{pid}"
    return f"name:{_normalize_name_for_match(player.get('playerKor'))}:{_normalize_name_for_match(player.get('playerEng'))}"


def _player_team_pair(player):
    league = str(player.get("league") or "").strip()
    team = str(player.get("team") or "").strip()
    if not league and not team:
        return None
    return {"league": league, "team": team}


def _build_player_career_index():
    career_index = {}
    for player in PLAYER_DATA:
        pair = _player_team_pair(player)
        if not pair:
            continue
        key = _player_identity_key(player)
        career_index.setdefault(key, [])
        if pair not in career_index[key]:
            career_index[key].append(pair)
    return career_index


def _parse_fco_career_text(text):
    raw = re.sub(r"^\s*(?:const|let|var)\s+allData\s*=\s*", "", text.strip())
    raw = re.sub(r";\s*$", "", raw)
    data = json.loads(raw)
    return data if isinstance(data, list) else []


def _load_fco_career_rows():
    global _FCO_CAREER_ROWS
    if _FCO_CAREER_ROWS is not None:
        return _FCO_CAREER_ROWS

    rows = []
    try:
        if os.path.exists(FCO_CAREER_DATA_FILE):
            with open(FCO_CAREER_DATA_FILE, "r", encoding="utf-8") as f:
                rows = _parse_fco_career_text(f.read())
        elif FCO_CAREER_DATA_URL:
            response = requests.get(FCO_CAREER_DATA_URL, timeout=3)
            response.raise_for_status()
            rows = _parse_fco_career_text(response.text)
    except Exception as e:
        print(f"FC온라인 경력 데이터 로드 실패: {e}")
        rows = []

    _FCO_CAREER_ROWS = rows
    return _FCO_CAREER_ROWS


def _load_fco_club_career_data():
    global _FCO_CLUB_CAREER_DATA
    if _FCO_CLUB_CAREER_DATA is not None:
        return _FCO_CLUB_CAREER_DATA

    payload = {"meta": {}, "players": {}}
    try:
        with open(FCO_CLUB_CAREER_DATA_FILE, "r", encoding="utf-8") as file:
            loaded = json.load(file)
        if isinstance(loaded, dict) and isinstance(loaded.get("players"), dict):
            payload = loaded
    except FileNotFoundError:
        pass
    except Exception as exc:
        print(f"FC온라인 상세 클럽 경력 데이터 로드 실패: {exc}")

    _FCO_CLUB_CAREER_DATA = payload
    return _FCO_CLUB_CAREER_DATA


def _get_player_club_career(player):
    pid = player.get("pid") if isinstance(player, dict) else None
    if pid in (None, ""):
        return None
    payload = _load_fco_club_career_data()
    rows = payload.get("players", {}).get(str(pid))
    if not isinstance(rows, list) or not rows:
        return None
    return {
        "rows": rows,
        "updated_label": str(payload.get("meta", {}).get("updated_label") or "").strip(),
    }


def _build_external_career_lookup():
    by_id = {}
    by_name = {}
    for row in _load_fco_career_rows():
        if not isinstance(row, dict):
            continue
        careers = [
            str(team or "").strip()
            for team in row.get("career", [])
            if str(team or "").strip()
        ]
        current_team = str(row.get("team") or "").strip()
        if current_team:
            careers.insert(0, current_team)
        if not careers:
            continue

        compact = []
        for team in careers:
            if team not in compact:
                compact.append(team)

        raw_id = str(row.get("id") or "").strip()
        if raw_id.isdigit():
            by_id.setdefault(str(int(raw_id) % 1000000), []).extend(compact)

        for key in (row.get("name"), row.get("originName")):
            normalized = _normalize_name_for_match(key)
            if normalized:
                by_name.setdefault(normalized, []).extend(compact)

    return by_id, by_name


def _extend_career_index_with_external_data(career_index):
    by_id, by_name = _build_external_career_lookup()
    club_career_players = _load_fco_club_career_data().get("players", {})
    if not by_id and not by_name and not club_career_players:
        return career_index

    for player in PLAYER_DATA:
        teams = []
        pid = player.get("pid")
        if pid is not None:
            teams.extend(by_id.get(str(pid), []))
            for row in club_career_players.get(str(pid), []):
                if not isinstance(row, dict):
                    continue
                club = str(row.get("club") or "").strip()
                if club:
                    teams.append(club)

        teams.extend(by_name.get(_normalize_name_for_match(player.get("playerKor")), []))
        if not teams:
            continue

        key = _player_identity_key(player)
        career_index.setdefault(key, [])
        for team in teams:
            pair = {"league": "", "team": team}
            if pair not in career_index[key]:
                career_index[key].append(pair)
    return career_index


def _current_team_score(player):
    pair = _player_team_pair(player)
    is_club = 1 if pair and pair.get("league") != "국가대표" else 0
    return (
        is_club,
        int(player.get("PlayerYear") or 0),
        int(player.get("cid") or 0),
    )


def _build_player_current_team_index():
    best_rows = {}
    for player in PLAYER_DATA:
        pair = _player_team_pair(player)
        if not pair:
            continue
        key = _player_identity_key(player)
        score = _current_team_score(player)
        if key not in best_rows or score > best_rows[key][0]:
            best_rows[key] = (score, pair)
    return {key: pair for key, (_, pair) in best_rows.items()}


def _build_league_team_map(pairs):
    league_teams = {}
    for pair in pairs:
        if not pair or not pair.get("league") or not pair.get("team"):
            continue
        league_teams.setdefault(pair["league"], set()).add(pair["team"])
    return {
        league: sorted(teams)
        for league, teams in sorted(league_teams.items(), key=lambda item: item[0])
    }


def _team_pair_matches(pair, selected_league="", selected_team=""):
    if not pair:
        return False
    league = _normalize_filter_text(pair.get("league"))
    team = _normalize_team_for_match(pair.get("team"))
    league_filter = _normalize_filter_text(selected_league)
    team_filter = _normalize_team_for_match(selected_team)
    if league_filter and league and league != league_filter:
        return False
    if team_filter and team != team_filter:
        return False
    return True


def _player_matches_team_filter(
    player,
    selected_league="",
    selected_team="",
    all_career=False,
    career_index=None,
    current_team_index=None,
):
    if not selected_league and not selected_team:
        return True

    if all_career:
        career_index = career_index or {}
        for pair in career_index.get(_player_identity_key(player), []):
            if _team_pair_matches(pair, selected_league, selected_team):
                return True
        return False

    current_team_index = current_team_index or {}
    current_pair = current_team_index.get(_player_identity_key(player)) or _player_team_pair(player)
    return _team_pair_matches(current_pair, selected_league, selected_team)


def _get_main_foot_label(player):
    main_foot = player.get("mainFoot")
    if main_foot == 1:
        return "오른발"
    if main_foot == 2:
        return "왼발"
    return "-"


def _get_weak_foot_value(player):
    """Return the rating of the foot opposite to the player's main foot."""
    try:
        left_foot = int(player.get("footL") or 0)
    except (TypeError, ValueError):
        left_foot = 0
    try:
        right_foot = int(player.get("footR") or 0)
    except (TypeError, ValueError):
        right_foot = 0

    main_foot = player.get("mainFoot")
    try:
        main_foot = int(main_foot)
    except (TypeError, ValueError):
        main_foot = 0

    if main_foot == 1:
        return left_foot
    if main_foot == 2:
        return right_foot
    valid_values = [value for value in (left_foot, right_foot) if value > 0]
    return min(valid_values) if valid_values else 0


def _build_compare_player(player):
    normalized = _apply_local_assets(_normalize_player_record(player.copy()))
    skill_display = _extract_player_skill_items(normalized)
    normalized["mainFootLabel"] = _get_main_foot_label(normalized)
    normalized["skillLabels"] = _extract_player_skills(normalized)
    normalized["skillDisplay"] = _prepare_review_skill_display(
        {**normalized, "skillDisplay": skill_display}
    )
    normalized["playstyles"] = _extract_player_playstyles(normalized)
    normalized["potentialPositions"] = _extract_potential_positions(normalized)
    return normalized


def _get_compare_stat_groups(player):
    positions = set(_extract_player_positions(player))
    primary_position = (player.get("position") or "").upper().strip()
    if primary_position == "GK" or "GK" in positions:
        return GK_COMPARE_STAT_GROUPS
    return FIELD_COMPARE_STAT_GROUPS


PLAYER_TIER_CHOICES = ("S", "A", "B", "C", "D", "F")
PLAYER_TIER_COLLECTION = "player_tier_votes"
PLAYER_TIER_FIRESTORE_TIMEOUT = 3.0


def _empty_player_tier_summary():
    counts = {tier: 0 for tier in PLAYER_TIER_CHOICES}
    return {
        "tiers": list(PLAYER_TIER_CHOICES),
        "counts": counts,
        "percentages": counts.copy(),
        "total": 0,
        "dominant_tier": None,
        "my_vote": None,
        "available": fs is not None,
    }


def _player_tier_summary(player_cid):
    summary = _empty_player_tier_summary()
    if not fs:
        return summary

    player_ref = fs.collection(PLAYER_TIER_COLLECTION).document(str(player_cid))
    try:
        snapshot = player_ref.get(timeout=PLAYER_TIER_FIRESTORE_TIMEOUT, retry=None)
        data = snapshot.to_dict() or {}
        stored_counts = data.get("counts") or {}
        counts = {
            tier: max(0, int(stored_counts.get(tier, 0) or 0))
            for tier in PLAYER_TIER_CHOICES
        }
        total = sum(counts.values())
    except Exception as error:
        app.logger.warning("Firestore tier summary read failed for %s: %s", player_cid, error)
        summary["available"] = False
        return summary

    percentages = {
        tier: round((count / total) * 100) if total else 0
        for tier, count in counts.items()
    }
    dominant_tier = None
    if total:
        dominant_tier = max(PLAYER_TIER_CHOICES, key=lambda tier: (counts[tier], -PLAYER_TIER_CHOICES.index(tier)))

    my_vote = None
    if has_request_context() and current_user.is_authenticated:
        try:
            vote_snapshot = player_ref.collection("votes").document(str(current_user.id)).get(
                timeout=PLAYER_TIER_FIRESTORE_TIMEOUT,
                retry=None,
            )
            vote_data = vote_snapshot.to_dict() or {}
            candidate = str(vote_data.get("tier") or "").upper()
            if candidate in PLAYER_TIER_CHOICES:
                my_vote = candidate
        except Exception as error:
            app.logger.warning(
                "Firestore tier vote read failed for player %s/user %s: %s",
                player_cid,
                current_user.id,
                error,
            )

    return {
        "tiers": list(PLAYER_TIER_CHOICES),
        "counts": counts,
        "percentages": percentages,
        "total": total,
        "dominant_tier": dominant_tier,
        "my_vote": my_vote,
        "available": True,
    }


def _save_player_tier_vote(player_cid, user_id, tier=None):
    """Atomically save or cancel one user's vote and keep counters in sync."""
    if not fs:
        raise RuntimeError("Firestore is not configured.")

    player_ref = fs.collection(PLAYER_TIER_COLLECTION).document(str(player_cid))
    vote_ref = player_ref.collection("votes").document(str(user_id))
    transaction = fs.transaction()

    @firestore.transactional
    def save_vote(transaction):
        vote_snapshot = vote_ref.get(
            transaction=transaction,
            timeout=PLAYER_TIER_FIRESTORE_TIMEOUT,
            retry=None,
        )
        summary_snapshot = player_ref.get(
            transaction=transaction,
            timeout=PLAYER_TIER_FIRESTORE_TIMEOUT,
            retry=None,
        )
        vote_data = vote_snapshot.to_dict() or {}
        summary_data = summary_snapshot.to_dict() or {}
        previous_tier = str(vote_data.get("tier") or "").upper()
        counts = {
            choice: max(0, int((summary_data.get("counts") or {}).get(choice, 0) or 0))
            for choice in PLAYER_TIER_CHOICES
        }

        if tier is None:
            if previous_tier not in counts:
                return
            counts[previous_tier] = max(0, counts[previous_tier] - 1)
            transaction.delete(vote_ref)
            transaction.set(
                player_ref,
                {
                    "player_cid": int(player_cid),
                    "counts": counts,
                    "total": sum(counts.values()),
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
            return

        if previous_tier == tier:
            transaction.set(
                vote_ref,
                {
                    "player_cid": int(player_cid),
                    "user_id": str(user_id),
                    "tier": tier,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
            return

        if previous_tier in counts:
            counts[previous_tier] = max(0, counts[previous_tier] - 1)
        counts[tier] += 1
        vote_payload = {
            "player_cid": int(player_cid),
            "user_id": str(user_id),
            "tier": tier,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
        if not vote_snapshot.exists:
            vote_payload["created_at"] = firestore.SERVER_TIMESTAMP

        transaction.set(vote_ref, vote_payload, merge=True)
        transaction.set(
            player_ref,
            {
                "player_cid": int(player_cid),
                "counts": counts,
                "total": sum(counts.values()),
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )

    save_vote(transaction)


def _is_position_compatible(slot_position, player_positions):
    slot = (slot_position or "").upper().strip()
    if not slot:
        return True
    compatible_positions = POSITION_COMPATIBILITY.get(slot, {slot})
    return any(position in compatible_positions for position in player_positions)


def _score_squad_player(player, name_query="", slot_position="", class_query=""):
    player_name = _normalize_name_for_match(player.get("playerKor"))
    class_name = _normalize_name_for_match(player.get("className"))
    query = _normalize_name_for_match(name_query)
    class_filter = _normalize_name_for_match(class_query)
    positions = _extract_player_positions(player)
    primary_position = (player.get("position") or "").upper()

    if class_filter and class_filter not in class_name:
        return None

    score = 0
    if query:
        if player_name == query:
            score += 300
        elif player_name.startswith(query):
            score += 220
        elif query in player_name:
            score += 140
        elif query in class_name:
            score += 70
        else:
            return None

    slot = (slot_position or "").upper().strip()
    if slot:
        if primary_position == slot:
            score += 120
        elif slot in positions:
            score += 90
        elif _is_position_compatible(slot, positions):
            score += 45
        elif not query:
            return None

    score += int(player.get("ovr") or 0)
    return score

def _has_price_value(value):
    return value is not None and str(value).strip() != ""

def _extract_price(player):
    if not player:
        return None
    if _has_price_value(player.get("n8Price0")):
        return player.get("n8Price0")
    if _has_price_value(player.get("n8Price")):
        return player.get("n8Price")
    for i in range(0, MAX_ENHANCE_LEVEL + 1):
        key = f"n8Price{i}"
        if _has_price_value(player.get(key)):
            return player.get(key)
    return None

def _build_price_by_enhance(player):
    if not isinstance(player, dict):
        return {}
    price_by_enhance = {}
    base_price = _extract_price(player)
    if base_price is not None:
        price_by_enhance[0] = base_price
    for level in range(0, MAX_ENHANCE_LEVEL + 1):
        value = player.get(f"n8Price{level}")
        if _has_price_value(value):
            price_by_enhance[level] = value
    return price_by_enhance

def _build_price_rows(player):
    return [
        {"level": level, "price": price}
        for level, price in sorted(_build_price_by_enhance(player).items())
        if price is not None
    ]

def _price_fields_from_player(player):
    if not isinstance(player, dict):
        return {}
    fields = {}
    for key in ["n8Price", *[f"n8Price{i}" for i in range(0, MAX_ENHANCE_LEVEL + 1)]]:
        value = player.get(key)
        if _has_price_value(value):
            fields[key] = value
    return fields

PRICE_FIELD_CACHE_TTL = 300
_PRICE_FIELDS_BY_NAME_CACHE = {}

def _same_cid(left, right):
    return str(left or "").strip() == str(right or "").strip()

def _fetch_player_price_fields_by_name_from_api(name):
    if not name:
        return {}
    cache_key = _normalize_filter_text(name)
    now = time.time()
    cached = _PRICE_FIELDS_BY_NAME_CACHE.get(cache_key)
    if cached and now - cached.get("fetched_at", 0) < PRICE_FIELD_CACHE_TTL:
        return cached.get("data") or {}
    try:
        first_page_data = fetch_player_search_list(player_names_list=[name], page_no=1)
        if first_page_data.get("ResultCode") != 1:
            return {}
        rd = first_page_data.get("ResultData", {})
        total_count = rd.get("totalCount", 0)
        page_size = rd.get("pageSize", 10)
        total_pages = math.ceil(total_count / page_size) if page_size > 0 else 1

        price_fields_by_cid = {}
        page_players = rd.get("PlayerList", [])
        for player in page_players:
            cid = str(player.get("cid") or "").strip()
            if cid:
                price_fields_by_cid[cid] = _price_fields_from_player(player)

        for page_no in range(2, total_pages + 1):
            page_data = fetch_player_search_list(player_names_list=[name], page_no=page_no)
            if page_data.get("ResultCode") != 1:
                continue
            page_players = page_data.get("ResultData", {}).get("PlayerList", [])
            for player in page_players:
                cid = str(player.get("cid") or "").strip()
                if cid:
                    price_fields_by_cid[cid] = _price_fields_from_player(player)
        _PRICE_FIELDS_BY_NAME_CACHE[cache_key] = {"fetched_at": time.time(), "data": price_fields_by_cid}
        return price_fields_by_cid
    except Exception as e:
        print(f"Price fetch error for {name}: {e}")
    _PRICE_FIELDS_BY_NAME_CACHE[cache_key] = {"fetched_at": time.time(), "data": {}}
    return {}

def _fetch_player_price_fields_from_api(cid, name):
    if not name:
        local_player = _get_local_player_by_cid(cid)
        name = (local_player or {}).get("playerKor")
    if not name:
        return None
    price_fields_by_cid = _fetch_player_price_fields_by_name_from_api(name)
    for api_cid, price_fields in price_fields_by_cid.items():
        if _same_cid(api_cid, cid):
            return price_fields
    return None

def apply_live_price_fields(player):
    if not isinstance(player, dict):
        return player
    api_price_fields = _fetch_player_price_fields_from_api(player.get("cid"), player.get("playerKor"))
    if api_price_fields:
        player.update(api_price_fields)
    return player

def populate_live_prices(players):
    players_by_name = {}
    for player in players:
        name = str(player.get("playerKor") or "").strip()
        if name:
            players_by_name.setdefault(name, []).append(player)

    for name, name_players in players_by_name.items():
        price_fields_by_cid = _fetch_player_price_fields_by_name_from_api(name)
        for player in name_players:
            cid = str(player.get("cid") or "").strip()
            api_price_fields = price_fields_by_cid.get(cid)
            if api_price_fields:
                player.update(api_price_fields)
            player["price"] = _extract_price(player)
    return players

def get_live_price(cid, name=None):
    price_fields = _fetch_player_price_fields_from_api(cid, name)
    if price_fields:
        return _extract_price(price_fields)
    local_player = _get_local_player_by_cid(cid)
    return _extract_price(local_player)


# 홈 화면 "이주의 선수" 3명. cid를 넣으면 해당 카드, pid를 넣으면 같은 pid 중 OVR이 가장 높은 카드가 표시됩니다.
WEEKLY_PLAYER_IDS = [22507020, 22902256, 22901043]
WEEKLY_PLAYER_CONFIG_PATH = os.path.join(app.instance_path, "weekly_player_ids.json")
PRIME_EXCHANGE_CONFIG_PATH = os.path.join(app.root_path, "static", "data", "prime_exchange.json")
PRIME_EXCHANGE_PRICE_SEED_PATH = os.path.join(app.root_path, "static", "data", "prime_exchange_prices.json")
PRIME_EXCHANGE_PRICE_CACHE_PATH = os.path.join(app.instance_path, "prime_exchange_prices.json")
PRIME_EXCHANGE_PRICE_CACHE_TTL = 300
_PRIME_EXCHANGE_CACHE = {"signature": None, "value": None}
_PRIME_PRICE_REFRESH_LOCK = threading.Lock()


def _load_weekly_player_ids():
    try:
        with open(WEEKLY_PLAYER_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        values = data.get("player_ids") if isinstance(data, dict) else data
        if isinstance(values, list):
            cleaned = [int(value) for value in values[:3] if str(value).strip().isdigit()]
            if len(cleaned) == 3:
                return cleaned
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Weekly player config read failed: {e}")
    return list(WEEKLY_PLAYER_IDS)


def _save_weekly_player_ids(player_ids):
    os.makedirs(app.instance_path, exist_ok=True)
    with open(WEEKLY_PLAYER_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"player_ids": player_ids}, f, ensure_ascii=False, indent=2)


def _get_local_player_by_weekly_id(player_id):
    player = _get_local_player_by_cid(player_id)
    if player:
        return player

    candidates = [
        _apply_local_assets(_normalize_player_record(item.copy()))
        for item in PLAYER_DATA
        if str(item.get("pid")) == str(player_id)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-(item.get("ovr") or 0), -(item.get("cid") or 0)))
    return candidates[0]


def _get_weekly_players():
    weekly_players = []
    seen_cids = set()
    for player_id in _load_weekly_player_ids():
        player = _get_local_player_by_weekly_id(player_id)
        if not player:
            continue
        cid = player.get("cid")
        if not cid or cid in seen_cids:
            continue
        seen_cids.add(cid)
        player["price"] = _extract_price(player)
        weekly_players.append(player)
    populate_live_prices(weekly_players)
    return weekly_players


def _load_prime_exchange_config():
    try:
        with open(PRIME_EXCHANGE_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"Prime exchange config read failed: {e}")
        return {}


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _load_prime_exchange_price_payload():
    for path in (PRIME_EXCHANGE_PRICE_CACHE_PATH, PRIME_EXCHANGE_PRICE_SEED_PATH):
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, dict) and isinstance(payload.get("prices"), dict):
                return payload
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"Prime exchange price cache read failed ({path}): {e}")
    return {"prices": {}, "fetched_at_epoch": 0}


def _prime_exchange_price_cache_signature():
    signature = []
    for path in (PRIME_EXCHANGE_PRICE_CACHE_PATH, PRIME_EXCHANGE_PRICE_SEED_PATH):
        try:
            signature.append(os.path.getmtime(path))
        except OSError:
            signature.append(None)
    return tuple(signature)


def _prime_exchange_target_players(config=None):
    config = config or _load_prime_exchange_config()
    target_ids = {
        cid
        for groups in (config.get("players") or {}).values()
        if isinstance(groups, dict)
        for player_ids in groups.values()
        if isinstance(player_ids, list)
        for raw_cid in player_ids
        if (cid := _positive_int(raw_cid))
    }
    players_by_cid = {
        _positive_int(player.get("cid")): player
        for player in PLAYER_DATA
        if isinstance(player, dict) and _positive_int(player.get("cid")) in target_ids
    }
    return target_ids, players_by_cid


def _new_nexon_price_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "ko,en-US;q=0.9,en;q=0.8",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://fcmobile.nexon.com/DataCenterWeb/SquadMaker",
    })
    response = session.get("https://fcmobile.nexon.com/datacenterweb/squadmaker", timeout=20)
    response.raise_for_status()
    token_input = BeautifulSoup(response.text, "html.parser").find(
        "input", {"name": "__RequestVerificationToken"}
    )
    csrf_token = token_input.get("value") if token_input else ""
    if not csrf_token:
        raise RuntimeError("넥슨 선수 검색 CSRF 토큰을 찾을 수 없습니다.")
    return session, csrf_token


def _fetch_prime_exchange_price_page(session, csrf_token, names, ovr, page_no):
    body = {
        "strMethod": "PlayerSearchList",
        "n8Cid": 0,
        "n4PageNo": page_no,
        "strPlayerName": json.dumps(sorted(names), ensure_ascii=False),
        "strClass": "",
        "strLeagueId": "",
        "strPositionCode": "",
        "strTeamId": "",
        "strNationality": "",
        "n1Force": 0,
        "n4OvrMin": ovr,
        "n4OvrMax": ovr,
        "n8PriceMin": "",
        "n8PriceMax": "",
        "n1WeakFoot": "",
        "n4HeightMin": "",
        "n4HeightMax": "",
        "n4WeightMin": "",
        "n4WeightMax": "",
        "strSkillMove": "",
        "strSkillBoost": "",
        "__RequestVerificationToken": csrf_token,
    }
    response = session.post(
        "https://fcmobile.nexon.com/datacenterweb/SquadMakerAjaxInfo",
        data=body,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _sync_prime_exchange_live_prices(output_path=None):
    config = _load_prime_exchange_config()
    target_ids, players_by_cid = _prime_exchange_target_players(config)
    targets_by_ovr = {}
    for cid, player in players_by_cid.items():
        ovr = _positive_int(player.get("ovr"))
        name = str(player.get("playerKor") or "").strip()
        if ovr and name:
            bucket = targets_by_ovr.setdefault(ovr, {"ids": set(), "names": set()})
            bucket["ids"].add(cid)
            bucket["names"].add(name)

    session, csrf_token = _new_nexon_price_session()
    live_prices = {}
    for ovr in sorted(targets_by_ovr, reverse=True):
        bucket = targets_by_ovr[ovr]
        sorted_names = sorted(bucket["names"])
        # 공식 검색 API는 선수명을 한 요청에 최대 5개까지만 허용한다.
        for chunk_start in range(0, len(sorted_names), 5):
            name_chunk = set(sorted_names[chunk_start:chunk_start + 5])
            chunk_ids = {
                cid
                for cid in bucket["ids"]
                if str(players_by_cid[cid].get("playerKor") or "").strip() in name_chunk
            }
            missing_ids = set(chunk_ids)
            page_no = 1
            total_pages = 1
            while page_no <= total_pages and missing_ids:
                page_data = _fetch_prime_exchange_price_page(
                    session, csrf_token, name_chunk, ovr, page_no
                )
                if page_data.get("ResultCode") != 1:
                    break
                result_data = page_data.get("ResultData") or {}
                if page_no == 1:
                    total_count = _positive_int(result_data.get("totalCount")) or 0
                    page_size = _positive_int(result_data.get("pageSize")) or 10
                    total_pages = max(1, math.ceil(total_count / page_size))
                for player in result_data.get("PlayerList") or []:
                    cid = _positive_int(player.get("cid"))
                    if cid not in chunk_ids:
                        continue
                    fields = {
                        key: player.get(key)
                        for key in ("n8Price7", "n8Price10")
                        if _has_price_value(player.get(key))
                    }
                    if fields:
                        live_prices[str(cid)] = fields
                        missing_ids.discard(cid)
                page_no += 1

    previous = _load_prime_exchange_price_payload().get("prices") or {}
    merged_prices = dict(previous)
    merged_prices.update(live_prices)
    now = time.time()
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "fetched_at_epoch": now,
        "source": "NEXON SquadMakerAjaxInfo",
        "target_count": len(target_ids),
        "updated_count": len(live_prices),
        "prices": merged_prices,
    }
    destination = output_path or PRIME_EXCHANGE_PRICE_CACHE_PATH
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    temp_path = f"{destination}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, destination)
    _PRIME_EXCHANGE_CACHE.update(signature=None, value=None)
    return payload


def _refresh_prime_exchange_prices_in_background():
    try:
        _sync_prime_exchange_live_prices()
    except Exception as e:
        print(f"Prime exchange live price refresh failed: {e}")
    finally:
        _PRIME_PRICE_REFRESH_LOCK.release()


def _ensure_prime_exchange_live_prices():
    payload = _load_prime_exchange_price_payload()
    fetched_at = float(payload.get("fetched_at_epoch") or 0)
    if time.time() - fetched_at < PRIME_EXCHANGE_PRICE_CACHE_TTL:
        return
    if not _PRIME_PRICE_REFRESH_LOCK.acquire(blocking=False):
        return
    threading.Thread(
        target=_refresh_prime_exchange_prices_in_background,
        name="prime-price-refresh",
        daemon=True,
    ).start()


def _get_prime_exchange_efficiency():
    try:
        config_mtime = os.path.getmtime(PRIME_EXCHANGE_CONFIG_PATH)
    except OSError:
        config_mtime = None
    price_cache_signature = _prime_exchange_price_cache_signature()
    cache_signature = (config_mtime, price_cache_signature, id(PLAYER_DATA), len(PLAYER_DATA))
    if _PRIME_EXCHANGE_CACHE["signature"] == cache_signature:
        return _PRIME_EXCHANGE_CACHE["value"]

    config = _load_prime_exchange_config()
    live_price_payload = _load_prime_exchange_price_payload()
    live_prices = live_price_payload.get("prices") or {}
    rewards = config.get("token_rewards") or {}
    level_groups = config.get("players") or {}
    players_by_cid = {
        _positive_int(player.get("cid")): player
        for player in PLAYER_DATA
        if isinstance(player, dict) and _positive_int(player.get("cid"))
    }
    best_by_player_level = {}
    missing_prices = 0

    for level_key, groups in level_groups.items():
        try:
            enhance_level = int(level_key)
        except (TypeError, ValueError):
            continue
        if enhance_level not in {7, 10} or not isinstance(groups, dict):
            continue

        for raw_group, player_ids in groups.items():
            group = str(raw_group or "").strip().upper()
            token_count = _positive_int(rewards.get(group))
            if not group or not token_count or not isinstance(player_ids, list):
                continue

            for raw_cid in player_ids:
                cid = _positive_int(raw_cid)
                player = players_by_cid.get(cid) if cid else None
                if not player:
                    continue

                price_field = f"n8Price{enhance_level}"
                live_player_prices = live_prices.get(str(cid)) or {}
                price = _positive_int(live_player_prices.get(price_field))
                price_source = "live"
                if not price:
                    price = _positive_int(player.get(price_field))
                    price_source = "local"
                if not price:
                    missing_prices += 1
                    continue

                normalized = _apply_local_assets(_normalize_player_record(player.copy()))
                row = {
                    "cid": cid,
                    "group": group,
                    "enhance_level": enhance_level,
                    "token_count": token_count,
                    "price": price,
                    "price_per_token": price / token_count,
                    "price_source": price_source,
                    "player_name": normalized.get("playerKor") or "선수",
                    "player_class": normalized.get("className") or "",
                    "player_ovr": normalized.get("ovr"),
                    "player_position": normalized.get("position") or "",
                    "player_pimage": normalized.get("pimage") or "",
                    "player_bimage": normalized.get("bimage") or "",
                }

                # 같은 CID가 같은 진화 단계의 여러 그룹에 들어오면 토큰을 더 많이
                # 지급하여 실제 교환 효율이 좋은 그룹 하나만 노출한다.
                dedupe_key = (cid, enhance_level)
                previous = best_by_player_level.get(dedupe_key)
                if previous is None or row["price_per_token"] < previous["price_per_token"]:
                    best_by_player_level[dedupe_key] = row

    rows = sorted(
        best_by_player_level.values(),
        key=lambda item: (
            item["price_per_token"],
            item["price"],
            -item["token_count"],
            item["player_name"],
        ),
    )
    result = {
        "title": config.get("title") or "프라임 교환 효율",
        "source_url": config.get("source_url") or "https://fcmobile.nexon.com/ForumProbability",
        "expires_at": config.get("expires_at") or "",
        "expires_label": config.get("expires_label") or "",
        "rows": rows,
        "missing_prices": missing_prices,
    }
    _PRIME_EXCHANGE_CACHE.update(signature=cache_signature, value=result)
    return result

# === 쿠폰 데이터 유틸 ===
RTDB_BASE = "https://game-coupon-default-rtdb.firebaseio.com"
CODES_PATH = "fifaMobile/codes"
_coupon_cache = {"fetched_at": 0.0, "raw": None}


def _normalize_rtdb_payload(payload):
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        return [v for v in payload.values() if isinstance(v, dict)]
    return []


def _parse_expires(expires_str):
    if not expires_str:
        return None
    if isinstance(expires_str, (int, float)):
        try:
            return datetime.fromtimestamp(expires_str).date()
        except Exception:
            return None
    if not isinstance(expires_str, str):
        return None

    cleaned = expires_str.strip()
    if not cleaned:
        return None

    normalized = cleaned.replace(".", "-").replace("/", "-")
    candidates = (cleaned, normalized)
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y.%m.%d",
        "%Y/%m/%d",
        "%Y.%m.%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
    ]

    for text in candidates:
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue

    digits = re.findall(r"\d+", cleaned)
    if len(digits) >= 3:
        try:
            y, m, d = [int(x) for x in digits[:3]]
            return date(y, m, d)
        except Exception:
            return None

    return None


def _parse_added(added_val):
    if added_val is None:
        return None
    if isinstance(added_val, (int, float)):
        try:
            return datetime.fromtimestamp(added_val)
        except Exception:
            return None
    if not isinstance(added_val, str):
        return None

    text = added_val.strip()
    if not text:
        return None

    iso_text = text.replace("Z", "").replace("T", " ")
    patterns = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%Y/%m/%d",
        "%Y.%m.%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
    ]

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        pass

    for fmt in patterns:
        try:
            return datetime.strptime(iso_text, fmt)
        except ValueError:
            continue

    digits = re.findall(r"\d+", text)
    if len(digits) >= 3:
        try:
            y, m, d = [int(x) for x in digits[:3]]
            return datetime(y, m, d)
        except Exception:
            return None

    return None


def _dedupe_by_code(coupons):
    by_code = {}
    no_code = []

    for coupon in coupons:
        code = coupon.get("code")
        if not code:
            no_code.append(coupon)
            continue

        existing = by_code.get(code)
        if not existing:
            by_code[code] = coupon
            continue

        if coupon.get("_parsed_added") and existing.get("_parsed_added"):
            if coupon["_parsed_added"] > existing["_parsed_added"]:
                by_code[code] = coupon
        elif coupon.get("_parsed_added") and not existing.get("_parsed_added"):
            by_code[code] = coupon

    return [*by_code.values(), *no_code]


def _prepare_coupons(raw_coupons, dedupe=True):
    today = date.today()
    enriched = []

    for entry in raw_coupons:
        coupon = dict(entry)
        exp_date = _parse_expires(coupon.get("expires"))
        coupon["_parsed_expires"] = exp_date
        coupon["_parsed_added"] = _parse_added(coupon.get("added"))
        coupon["boolExpires"] = bool(exp_date and exp_date < today)
        enriched.append(coupon)

    processed = _dedupe_by_code(enriched) if dedupe else enriched

    def sort_key(c):
        return (
            c.get("_parsed_added") or datetime.min,
            c.get("_parsed_expires") or date.min,
        )

    processed.sort(key=sort_key, reverse=True)

    for coupon in processed:
        coupon.pop("_parsed_expires", None)
        coupon.pop("_parsed_added", None)

    return processed


def _fetch_coupon_raw():
    url = f"{RTDB_BASE}/{CODES_PATH}.json"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def get_coupons(dedupe=True, ttl=120):
    now = time.time()
    if _coupon_cache.get("raw") is not None and now - _coupon_cache.get("fetched_at", 0) < ttl:
        raw_payload = _coupon_cache["raw"]
    else:
        try:
            raw_payload = _fetch_coupon_raw()
            _coupon_cache["raw"] = raw_payload
            _coupon_cache["fetched_at"] = now
        except Exception as e:
            print(f"Coupon fetch failed: {e}")
            raw_payload = _coupon_cache.get("raw") or []

    normalized = _normalize_rtdb_payload(raw_payload)
    return _prepare_coupons(normalized, dedupe=dedupe)


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("1", "true", "yes", "y", "on"):
            return True
        if normalized in ("0", "false", "no", "n", "off"):
            return False
        return None
    return None


def allowed_image(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_IMAGE_EXTENSIONS']


# 넥슨 API를 통한 실시간 선수 검색 함수 (이름 검색, 자동완성, 상세 정보용)
from typing import List, Dict

def fetch_player_search_list(player_names_list: List[str] = None, page_no: int = 1, filters: Dict = None) -> Dict:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "ko,en-US;q=0.9,en;q=0.8",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://fcmobile.nexon.com/DataCenterWeb/SquadMaker"
    })

    csrf_token = None
    for _ in range(3): # 최대 3번 재시도
        try:
            url_get = "https://fcmobile.nexon.com/datacenterweb/squadmaker"
            res_get = session.get(url_get, timeout=15)
            res_get.raise_for_status() # HTTP 오류 발생 시 예외 발생

            soup = BeautifulSoup(res_get.text, "html.parser")
            token_input = soup.find("input", {"name": "__RequestVerificationToken"})
            if token_input and token_input.get("value"):
                csrf_token = token_input["value"]
                break # 토큰을 성공적으로 가져오면 루프 종료
        except requests.exceptions.RequestException as e:
            print(f"CSRF 토큰 GET 요청 실패 (재시도): {e}")
        except Exception as e:
            print(f"CSRF 토큰 파싱 오류 (재시도): {e}")

    if not csrf_token:
        raise RuntimeError("CSRF 토큰을 가져올 수 없습니다. 여러 번 시도했지만 실패했습니다.")

    if not player_names_list: # 빈 리스트가 들어오면 빈 문자열로 보내고, 아니면 JSON 배열로
        player_name_param = ""
    else:
        player_name_param = json.dumps(player_names_list, ensure_ascii=False)

    default_body = {
        "strMethod": "PlayerSearchList",
        "n8Cid": 0,
        "n4PageNo": page_no,
        "strPlayerName": player_name_param,
        "strClass": "", "strLeagueId": "", "strPositionCode": "",
        "strTeamId": "", "strNationality": "", "n1Force": 0,
        "n4OvrMin": "", "n4OvrMax": "", "n8PriceMin": "", "n8PriceMax": "",
        "n1WeakFoot": "", "n4HeightMin": "", "n4HeightMax": "",
        "n4WeightMin": "", "n4WeightMax": "", "strSkillMove": "",
        "strSkillBoost": "", "__RequestVerificationToken": csrf_token
    }
    if filters:
        default_body.update(filters)

    url_post = "https://fcmobile.nexon.com/datacenterweb/SquadMakerAjaxInfo"
    res_post = session.post(url_post, data=default_body, timeout=30)
    res_post.raise_for_status() # HTTP 오류 발생 시 예외 발생

    return res_post.json()


# 시작 페이지는 search.html
@app.route("/")
def index():
    return render_template(
        "search.html",
        robots_meta="index,follow",
        weekly_players=_get_weekly_players(),
        latest_notice=_latest_notice_post(),
        latest_review_activity=_latest_home_review_activity(3),
    )


@app.route("/prime-exchange")
def prime_exchange_page():
    _ensure_prime_exchange_live_prices()
    return render_template(
        "prime_exchange.html",
        robots_meta="index,follow",
        prime_exchange=_get_prime_exchange_efficiency(),
    )


# 메인 이름 검색 페이지 (API 사용)
@app.route("/search", methods=["GET", "POST"])
@csrf.exempt
def search():
    names_input = request.args.get("names", "").strip()
    if not names_input:
        return render_template(
            "search.html",
            robots_meta="noindex,follow",
            weekly_players=_get_weekly_players(),
            latest_notice=_latest_notice_post(),
            latest_review_activity=_latest_home_review_activity(3),
        )

    sort = request.args.get("sort", "ovr").strip() or "ovr"
    player_names_queries = [n.strip() for n in names_input.split(",") if n.strip()]

    all_players = []
    for name_query in player_names_queries:
        current_query_players = _search_local_players_by_name(name_query)
        for p in current_query_players:
            if not any(existing_p.get('cid') == p.get('cid') for existing_p in all_players):
                all_players.append(p)

    if not all_players:
        return render_template(
            "results.html",
            error=f"'{names_input}'에 해당하는 선수를 찾을 수 없습니다.",
            players=[],
            names=names_input,
            sort=sort,
            robots_meta="noindex,follow",
        )

    populate_live_prices(all_players)
    for player in all_players:
        player["playstyles"] = _extract_player_playstyles(player)

    if sort == "price_desc":
        all_players.sort(key=lambda p: (p.get("price") is None, -(p.get("price") or 0), p.get("playerKor", "")))
    elif sort == "price_asc":
        all_players.sort(key=lambda p: (p.get("price") is None, p.get("price") or 0, p.get("playerKor", "")))
    else:
        all_players.sort(key=lambda p: (-p.get("ovr", 0), p.get("playerKor", "")))

    return render_template(
        "results.html",
        error=None,
        players=all_players,
        names=names_input,
        sort=sort,
        robots_meta="noindex,follow",
    )

@app.route("/players")
def players_hub():
    per_page = 100
    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1

    players_sorted = sorted(
        PLAYER_DATA,
        key=lambda p: (p.get("playerKor") or "", p.get("cid") or 0),
    )
    total = len(players_sorted)
    total_pages = max(1, math.ceil(total / per_page)) if per_page else 1
    if page > total_pages:
        page = total_pages

    start = (page - 1) * per_page
    end = start + per_page
    page_players = players_sorted[start:end]

    if page == 1:
        canonical_url = _canonical("/players")
    else:
        canonical_url = f"{_canonical('/players')}?page={page}"

    return render_template(
        "players.html",
        players=page_players,
        page=page,
        total_pages=total_pages,
        per_page=per_page,
        total=total,
        canonical_url=canonical_url,
        robots_meta="index,follow",
        meta_description="FC모바일 전체 선수 목록에서 선수 이름, 클래스, 포지션과 OVR 정보를 확인하고 상세 능력치를 살펴보세요.",
        og_title="FC모바일 전체 선수 목록과 정보 | 피모북",
        og_description="FC모바일 선수 이름, 클래스, 포지션, OVR과 상세 정보를 확인하세요.",
    )


@app.route("/squad_maker")
def squad_maker():
    return render_template("squad_maker.html", skill_id_name_map=SKILL_ID_NAME_MAP)


@app.route("/player_compare")
def player_compare_page():
    return render_template(
        "compare_players.html",
        stat_groups={
            "field": FIELD_COMPARE_STAT_GROUPS,
            "gk": GK_COMPARE_STAT_GROUPS,
        },
        enhance_totals=ENHANCE_LEVEL_TOTALS,
        skill_boost_values=SKILL_BOOST_LEVEL_VALUES,
        skill_boost_stats=SKILL_BOOST_STAT_CODES,
        robots_meta="index,follow",
    )

# 선수 상세 정보 페이지 (API 사용)
@app.route("/player/<int:cid>")
def player_detail(cid):
    detail_cid = cid
    selected_player = _get_local_player_by_cid(cid)

    if not selected_player:
        return render_template(
            "detail.html",
            error=f"ID {cid}에 해당하는 선수의 상세 정보를 찾을 수 없습니다.",
            player=None,
            robots_meta="index,follow",
        )

    selected_player = apply_live_price_fields(selected_player)
    selected_player = _merge_fcplayer_skill_data(selected_player)
    selected_player["review_cid"] = detail_cid
    selected_player["skillLabels"] = _extract_player_skills(selected_player)
    selected_player["skillDisplay"] = _extract_player_skill_items(selected_player)
    selected_player["skillDisplay"] = _prepare_review_skill_display(selected_player)
    selected_player["playstyles"] = _extract_player_playstyles(selected_player)
    selected_player["potentialPositions"] = _extract_potential_positions(selected_player)
    selected_player["initialEnhance"] = int(selected_player.get("enhance") or 0)
    selected_player["priceByEnhance"] = _build_price_by_enhance(selected_player)
    selected_player["priceRows"] = _build_price_rows(selected_player)

    other_classes = []
    base_name = (selected_player.get("playerKor") or "").strip()
    if base_name:
        seen_cids = {selected_player.get("cid")}
        for p in PLAYER_DATA:
            if (p.get("playerKor") or "").strip() != base_name:
                continue
            other_cid = p.get("cid")
            if not other_cid or other_cid in seen_cids:
                continue
            seen_cids.add(other_cid)
            other_classes.append(_apply_local_assets(_normalize_player_record(p.copy())))
        other_classes.sort(key=lambda p: (-(p.get("ovr") or 0), p.get("className") or ""))

    # 평점 정보 추가
    # 평점 정보 추가
    average_overall_rating = None
    all_overall_ratings = PlayerRating.query.filter_by(player_cid=detail_cid).all()
    if all_overall_ratings:
        total_overall_rating = sum([r.overall_rating for r in all_overall_ratings])
        average_overall_rating = round(total_overall_rating / len(all_overall_ratings), 1)

    review_cids = _review_cid_candidates(detail_cid, selected_player.get("cid"), selected_player.get("fcplayerCardId"))
    cached_reviews = _get_cached_player_reviews(*review_cids)
    firebase_reviews = _merge_pending_player_review(
        detail_cid,
        _dedupe_player_reviews(
            _get_player_reviews_from_firestore(detail_cid, extra_cids=review_cids) + cached_reviews,
        ),
    )
    firebase_reviews = _review_display_reviews_for_player(firebase_reviews, selected_player)
    firebase_reviews = _attach_review_comment_counts(firebase_reviews)
    current_user_review = _find_current_user_review(firebase_reviews)
    review_skill_move_labels = _review_skill_move_labels(selected_player)
    club_career = _get_player_club_career(selected_player)

    return render_template(
        "detail.html",
        error=None,
        player=selected_player,
        average_overall_rating=average_overall_rating,
        firebase_reviews=firebase_reviews,
        firebase_review_preview=firebase_reviews[:4],
        current_user_review=current_user_review,
        club_career=club_career,
        admin_review_summary=_get_player_review_summary(detail_cid),
        review_preview_limit=4,
        review_skill_move_labels=review_skill_move_labels,
        review_rating_fields=_review_rating_fields_for_player(selected_player),
        review_tiers=PLAYER_REVIEW_TIERS,
        review_formations=PLAYER_REVIEW_FORMATIONS,
        review_positions=PLAYER_REVIEW_POSITIONS,
        can_write_review=current_user.is_authenticated,
        player_cid=detail_cid,
        tier_summary=_player_tier_summary(detail_cid),
        robots_meta="index,follow",
        other_classes=other_classes,
        enhance_totals=ENHANCE_LEVEL_TOTALS,
        skill_boost_values=SKILL_BOOST_LEVEL_VALUES,
        stat_labels=STAT_CODE_LABELS,
        max_training_level=MAX_TRAINING_LEVEL,
        training_level_bonuses=_training_bonuses_by_level(selected_player.get("position")),
    )


@app.route("/player/<int:cid>/stats-card.png")
def player_stats_card(cid):
    player = _get_local_player_by_cid(cid)
    if not player:
        abort(404)

    variant = (request.args.get("variant") or "current").strip().lower()
    enhance_level = request.args.get("enhance", default=0, type=int)
    enhance_level = max(0, min(enhance_level, MAX_ENHANCE_LEVEL))
    if variant == "base":
        enhance_level = 0
    enhance_bonus = int(ENHANCE_LEVEL_TOTALS[enhance_level] or 0)
    training_level = request.args.get("training", default=0, type=int)
    training_level = max(0, min(training_level, MAX_TRAINING_LEVEL))
    raw_skill_levels = (request.args.get("skill_levels") or "").split(",")
    skill_levels = []
    for raw_level in raw_skill_levels:
        try:
            skill_levels.append(max(0, int(raw_level)))
        except (TypeError, ValueError):
            skill_levels.append(0)
    if variant == "base":
        training_level = 0
        skill_levels = []

    card_player = _build_compare_player(player)
    card_player["skillDisplay"] = _prepare_review_skill_display(card_player)
    training_bonuses = _training_stat_bonuses(card_player.get("position"), training_level)
    skill_bonuses, skill_config_labels = _configured_skill_bonuses(
        card_player,
        enhance_level,
        skill_levels,
    )
    tier_summary = _player_tier_summary(cid)
    image = render_player_stats_card(
        card_player,
        root_path=app.root_path,
        enhance_level=enhance_level,
        enhance_bonus=enhance_bonus,
        training_level=training_level,
        training_bonuses=training_bonuses,
        skill_bonuses=skill_bonuses,
        skill_config_labels=skill_config_labels,
        tier=tier_summary.get("dominant_tier"),
        variant=variant,
    )
    safe_name = re.sub(r"[^0-9A-Za-z가-힣_-]+", "-", str(card_player.get("playerKor") or cid)).strip("-")
    response = send_file(
        image,
        mimetype="image/png",
        as_attachment=request.args.get("download") == "1",
        download_name=f"피모북-{safe_name}-통계.png",
        max_age=300,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.route("/api/player/<int:cid>/tier-vote", methods=["POST"])
@login_required
def player_tier_vote(cid):
    if not _get_local_player_by_cid(cid):
        return jsonify({"ok": False, "error": "선수를 찾을 수 없습니다."}), 404

    payload = request.get_json(silent=True) or {}
    cancel_vote = str(payload.get("action") or "").strip().lower() == "cancel"
    tier = str(payload.get("tier") or "").strip().upper()
    if not cancel_vote and tier not in PLAYER_TIER_CHOICES:
        return jsonify({"ok": False, "error": "올바른 티어를 선택해주세요."}), 400

    if not fs:
        return jsonify({
            "ok": False,
            "error": "티어 투표 서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.",
        }), 503

    try:
        _save_player_tier_vote(cid, current_user.id, None if cancel_vote else tier)
    except Exception as error:
        app.logger.exception(
            "Firestore tier vote failed for player %s/user %s",
            cid,
            current_user.id,
        )
        return jsonify({
            "ok": False,
            "error": "투표를 저장하지 못했습니다. 잠시 후 다시 시도해주세요.",
        }), 503

    return jsonify({"ok": True, "summary": _player_tier_summary(cid)})


@app.route("/player/<int:cid>/reviews")
def player_reviews(cid):
    player = _get_local_player_by_cid(cid)
    if not player:
        return render_template(
            "reviews.html",
            error=f"ID {cid}에 해당하는 선수를 찾을 수 없습니다.",
            player=None,
            reviews=[],
            robots_meta="noindex,follow",
        )

    player = _merge_fcplayer_skill_data(player)
    player["review_cid"] = cid
    player["skillDisplay"] = _extract_player_skill_items(player)
    review_cids = _review_cid_candidates(cid, player.get("cid"), player.get("fcplayerCardId"))
    reviews = _merge_pending_player_review(
        cid,
        _dedupe_player_reviews(
            _get_player_reviews_from_firestore(cid, extra_cids=review_cids) + _get_cached_player_reviews(*review_cids),
        ),
    )
    reviews = _review_display_reviews_for_player(reviews, player)
    reviews = _attach_review_comment_counts(reviews)
    current_user_review = _find_current_user_review(reviews)

    return render_template(
        "reviews.html",
        error=None,
        player=player,
        reviews=reviews,
        current_user_review=current_user_review,
        review_rating_fields=_review_rating_fields_for_player(player),
        can_write_review=current_user.is_authenticated,
        robots_meta="noindex,follow",
    )


@app.route("/community/reviews/<int:cid>/<string:review_id>")
def player_review_detail(cid, review_id):
    review = _get_player_review_by_id(cid, review_id)
    if not review:
        abort(404)

    player = _get_local_player_by_cid(cid)
    if not player:
        abort(404)
    player["review_cid"] = cid

    top_comments = (
        PlayerReviewComment.query
        .filter_by(player_cid=cid, review_id=str(review.get("id")), parent_id=None)
        .order_by(PlayerReviewComment.created_at.asc())
        .all()
    )
    total_comments = PlayerReviewComment.query.filter_by(
        player_cid=cid,
        review_id=str(review.get("id")),
    ).count()

    related_reviews = []
    current_key = (str(cid), str(review.get("id")))
    for item in _get_latest_player_reviews(limit=24, include_remote=True):
        if (str(item.get("player_cid")), str(item.get("id"))) == current_key:
            continue
        related_reviews.append(item)
        if len(related_reviews) >= 4:
            break

    return render_template(
        "review_detail.html",
        review=review,
        player=player,
        review_rating_fields=_review_rating_fields_for_player(player),
        top_comments=top_comments,
        total_comments=total_comments,
        related_reviews=related_reviews,
        robots_meta="index,follow",
        og_title=f"{review.get('title')} | 피모북 선수 리뷰",
        og_description=review.get("excerpt") or f"{review.get('player_name')} 선수 사용 리뷰",
    )


@app.route("/community/reviews/<int:cid>/<string:review_id>/comments", methods=["POST"])
@login_required
def add_player_review_comment(cid, review_id):
    review = _get_player_review_by_id(cid, review_id)
    if not review:
        abort(404)

    rate_limit_message = _comment_rate_limit_message(current_user.id)
    if rate_limit_message:
        flash(rate_limit_message, "danger")
        return redirect(url_for("player_review_detail", cid=cid, review_id=review_id, _anchor="review-comments"))

    content = request.form.get("content", "").strip()
    if not content:
        flash("댓글 내용을 입력해주세요.", "danger")
        return redirect(url_for("player_review_detail", cid=cid, review_id=review_id, _anchor="review-comments"))
    if len(content) > COMMENT_MAX_LENGTH:
        flash(f"댓글은 {COMMENT_MAX_LENGTH:,}자 이내로 작성해주세요.", "danger")
        return redirect(url_for("player_review_detail", cid=cid, review_id=review_id, _anchor="review-comments"))

    parent_id = request.form.get("parent_id", type=int)
    parent = None
    if parent_id:
        parent = PlayerReviewComment.query.filter_by(
            id=parent_id,
            player_cid=cid,
            review_id=str(review.get("id")),
        ).first()
        if not parent:
            flash("답글을 달 댓글을 찾을 수 없습니다.", "danger")
            return redirect(url_for("player_review_detail", cid=cid, review_id=review_id, _anchor="review-comments"))

    comment = PlayerReviewComment(
        player_cid=cid,
        review_id=str(review.get("id")),
        content=content,
        parent_id=parent.id if parent else None,
        author_id=current_user.id,
    )
    db.session.add(comment)
    player_name = str(review.get("player_name") or "선수").strip()
    review_title = re.sub(r"\s+", " ", str(review.get("title") or f"{player_name} 리뷰")).strip()
    if len(review_title) > 34:
        review_title = review_title[:34] + "…"
    review_author_id = review.get("user_id") or review.get("id")
    target_url = url_for(
        "player_review_detail",
        cid=cid,
        review_id=str(review.get("id")),
        _anchor="review-comments",
    )
    if parent:
        _create_notifications(
            [parent.author_id, review_author_id],
            "review_reply",
            f"{current_user.username}님이 ‘{review_title}’ 리뷰의 댓글에 답글을 남겼습니다.",
            target_url,
            actor_id=current_user.id,
        )
    else:
        _create_notifications(
            [review_author_id],
            "review_comment",
            f"{current_user.username}님이 ‘{review_title}’ 리뷰에 댓글을 남겼습니다.",
            target_url,
            actor_id=current_user.id,
        )
    db.session.commit()
    flash("댓글이 등록되었습니다.", "success")
    return redirect(url_for("player_review_detail", cid=cid, review_id=review_id, _anchor="review-comments"))


@app.route("/community/review-comments/<int:comment_id>/delete", methods=["POST"])
@login_required
def delete_player_review_comment(comment_id):
    comment = PlayerReviewComment.query.get_or_404(comment_id)
    if comment.author_id != current_user.id and not _is_admin_user():
        abort(403)
    cid = comment.player_cid
    review_id = comment.review_id
    db.session.delete(comment)
    db.session.commit()
    flash("댓글이 삭제되었습니다.", "info")
    return redirect(url_for("player_review_detail", cid=cid, review_id=review_id, _anchor="review-comments"))


@app.route("/secret/player-review-summary", methods=["GET", "POST"])
def player_review_summary_admin():
    admin_password_configured = bool(app.config.get("PLAYER_SUMMARY_ADMIN_PASSWORD"))

    if request.method == "POST" and request.form.get("action") == "login":
        if _verify_player_summary_admin_password(request.form.get("admin_password")):
            session["player_summary_admin"] = True
            flash("관리자 페이지에 접속했습니다.", "success")
            return redirect(url_for("player_review_summary_admin"))
        flash("비밀번호가 올바르지 않습니다.", "danger")

    if request.method == "POST" and request.form.get("action") == "logout":
        session.pop("player_summary_admin", None)
        flash("관리자 페이지에서 나갔습니다.", "info")
        return redirect(url_for("player_review_summary_admin"))

    if not _is_player_summary_admin():
        return render_template(
            "player_review_summary_admin.html",
            is_authenticated=False,
            admin_password_configured=admin_password_configured,
            robots_meta="noindex,nofollow",
        )

    if request.method == "POST" and request.form.get("action") == "save_weekly_players":
        weekly_ids = []
        for slot in range(1, 4):
            raw_value = request.form.get(f"weekly_player_{slot}", "").strip()
            if not raw_value.isdigit():
                flash("이주의 선수 3개 슬롯에 CID 또는 PID를 숫자로 입력해주세요.", "danger")
                return redirect(url_for("player_review_summary_admin"))
            weekly_ids.append(int(raw_value))

        resolved_players = [_get_local_player_by_weekly_id(player_id) for player_id in weekly_ids]
        if any(player is None for player in resolved_players):
            flash("입력한 CID 또는 PID 중 선수 데이터에서 찾을 수 없는 값이 있습니다.", "danger")
            return redirect(url_for("player_review_summary_admin"))
        resolved_cids = [player.get("cid") for player in resolved_players]
        if len(set(resolved_cids)) != 3:
            flash("이주의 선수는 서로 다른 카드 3장을 선택해주세요.", "danger")
            return redirect(url_for("player_review_summary_admin"))

        _save_weekly_player_ids(weekly_ids)
        flash("이주의 선수 3명을 변경했습니다.", "success")
        return redirect(url_for("player_review_summary_admin"))

    if request.method == "POST" and request.form.get("action") in {"save", "delete"}:
        cid = request.form.get("cid", type=int)
        player = _get_local_player_by_cid(cid) if cid else None
        if not player:
            flash("요약을 저장할 선수를 찾을 수 없습니다.", "danger")
            return redirect(url_for("player_review_summary_admin"))

        summaries = _load_player_review_summaries()
        player_key = str(cid)
        action = request.form.get("action")
        if action == "delete":
            summaries.pop(player_key, None)
            _save_player_review_summaries(summaries)
            flash("선수 리뷰 요약을 삭제했습니다.", "success")
            return redirect(url_for("player_review_summary_admin", q=player.get("playerKor") or "", cid=cid))

        summary_text = request.form.get("summary", "").strip()
        strengths = request.form.get("strengths", "").strip()
        weaknesses = request.form.get("weaknesses", "").strip()
        raw_summary_json = request.form.get("review_summary_json", "").strip()
        if raw_summary_json:
            try:
                parsed_summary = _parse_player_review_summary_json(raw_summary_json)
            except (json.JSONDecodeError, ValueError) as exc:
                flash(f"요약 리뷰 JSON 형식을 확인해주세요: {exc}", "danger")
                return redirect(url_for("player_review_summary_admin", q=player.get("playerKor") or "", cid=cid))
            summary_text = parsed_summary["summary"]
            strengths = parsed_summary["strengths"]
            weaknesses = parsed_summary["weaknesses"]

        summary_text = summary_text[:800]
        strengths = strengths[:2000]
        weaknesses = weaknesses[:2000]
        if not any([summary_text, strengths, weaknesses]):
            summaries.pop(player_key, None)
            _save_player_review_summaries(summaries)
            flash("입력된 내용이 없어 기존 요약을 삭제했습니다.", "info")
            return redirect(url_for("player_review_summary_admin", q=player.get("playerKor") or "", cid=cid))

        now_iso = datetime.utcnow().isoformat(timespec="seconds")
        summaries[player_key] = {
            "player_cid": cid,
            "player_name": player.get("playerKor"),
            "player_class": player.get("className"),
            "summary": summary_text,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "updated_at_iso": now_iso,
            "updated_by": current_user.username if current_user.is_authenticated else "admin",
        }
        _save_player_review_summaries(summaries)
        flash("선수 리뷰 요약을 저장했습니다.", "success")
        return redirect(url_for("player_review_summary_admin", q=player.get("playerKor") or "", cid=cid))

    q = request.args.get("q", "").strip()
    selected_cid = request.args.get("cid", type=int)
    selected_player = _get_local_player_by_cid(selected_cid) if selected_cid else None
    selected_summary = _get_player_review_summary(selected_cid) if selected_cid else None
    matches = _find_admin_summary_players(q)
    summaries = _load_player_review_summaries()
    weekly_player_ids = _load_weekly_player_ids()
    weekly_players = [_get_local_player_by_weekly_id(player_id) for player_id in weekly_player_ids]
    saved_summaries = sorted(
        [item for item in summaries.values() if isinstance(item, dict)],
        key=lambda item: str(item.get("updated_at_iso") or ""),
        reverse=True,
    )

    return render_template(
        "player_review_summary_admin.html",
        is_authenticated=True,
        admin_password_configured=admin_password_configured,
        q=q,
        matches=matches,
        selected_player=selected_player,
        selected_summary=selected_summary or {},
        saved_summaries=saved_summaries[:20],
        weekly_player_ids=weekly_player_ids,
        weekly_players=weekly_players,
        robots_meta="noindex,nofollow",
    )


@app.route("/rate_player", methods=["POST"])
@login_required
def rate_player():
    player_cid = request.form.get("player_cid", type=int)
    overall_rating = request.form.get("overall_rating", type=int)
    speed_rating = request.form.get("speed_rating", type=int)
    shot_rating = request.form.get("shot_rating", type=int)
    pass_rating = request.form.get("pass_rating", type=int)
    feel_rating = request.form.get("feel_rating", type=int)
    heading_rating = request.form.get("heading_rating", type=int)
    powershot_rating = request.form.get("powershot_rating", type=int)
    defense_ai_rating = request.form.get("defense_ai_rating", type=int)
    physicality_rating = request.form.get("physicality_rating", type=int)
    review_text = request.form.get("review_text")

    if not player_cid or not overall_rating:
        flash("평점을 제출하려면 선수 ID와 전체 평점이 필요합니다.", "danger")
        return redirect(url_for("player_detail", cid=player_cid))

    # 이미 평점을 남겼는지 확인
    existing_rating = PlayerRating.query.filter_by(player_cid=player_cid, user_id=current_user.id).first()

    if existing_rating:
        # 기존 평점 업데이트
        existing_rating.overall_rating = overall_rating
        existing_rating.speed_rating = speed_rating
        existing_rating.shot_rating = shot_rating
        existing_rating.pass_rating = pass_rating
        existing_rating.feel_rating = feel_rating
        existing_rating.heading_rating = heading_rating
        existing_rating.powershot_rating = powershot_rating
        existing_rating.defense_ai_rating = defense_ai_rating
        existing_rating.physicality_rating = physicality_rating
        existing_rating.review_text = review_text
        existing_rating.created_at = datetime.utcnow() # 업데이트 시간 갱신
        flash("선수 평점이 업데이트되었습니다.", "success")
    else:
        # 새 평점 생성
        new_rating = PlayerRating(
            player_cid=player_cid,
            user_id=current_user.id,
            overall_rating=overall_rating,
            speed_rating=speed_rating,
            shot_rating=shot_rating,
            pass_rating=pass_rating,
            feel_rating=feel_rating,
            heading_rating=heading_rating,
            powershot_rating=powershot_rating,
            defense_ai_rating=defense_ai_rating,
            physicality_rating=physicality_rating,
            review_text=review_text
        )
        db.session.add(new_rating)
        flash("선수 평점이 제출되었습니다.", "success")

    db.session.commit()
    return redirect(url_for("player_detail", cid=player_cid))


@app.route("/player/<int:cid>/review/new", methods=["GET", "POST"])
@login_required
def submit_player_firebase_review(cid):
    player = _build_review_player_context(cid)
    if not player:
        flash("리뷰를 남길 선수를 찾을 수 없습니다.", "danger")
        return redirect(url_for("index"))

    move_labels = _review_skill_move_labels(player)
    if request.method == "GET":
        return _render_player_review_form(
            player,
            move_labels,
            form_action=url_for("submit_player_firebase_review_post", cid=cid),
            form_mode="create",
        )

    return _save_player_review_from_request(cid, player, move_labels)


@app.route("/player/<int:cid>/firebase_reviews", methods=["POST"])
@login_required
def submit_player_firebase_review_post(cid):
    return submit_player_firebase_review(cid)


@app.route("/player/<int:cid>/review/edit", methods=["GET", "POST"])
@login_required
def edit_player_firebase_review(cid):
    player = _build_review_player_context(cid)
    if not player:
        flash("리뷰를 수정할 선수를 찾을 수 없습니다.", "danger")
        return redirect(url_for("index"))

    move_labels = _review_skill_move_labels(player)
    existing_review = _get_current_user_player_review(cid, player)
    if not existing_review:
        flash("수정할 리뷰가 없습니다.", "danger")
        return redirect(url_for("player_detail", cid=cid, _anchor="player-reviews"))

    if request.method == "GET":
        return _render_player_review_form(
            player,
            move_labels,
            review=existing_review,
            form_action=url_for("edit_player_firebase_review", cid=cid),
            form_mode="edit",
        )

    return _save_player_review_from_request(
        cid,
        player,
        move_labels,
        existing_review=existing_review,
        success_message="선수 리뷰가 수정되었습니다.",
        error_endpoint="edit_player_firebase_review",
    )


@app.route("/player/<int:cid>/review/delete", methods=["POST"])
@login_required
def delete_player_firebase_review(cid):
    player = _build_review_player_context(cid)
    if not player:
        flash("리뷰를 삭제할 선수를 찾을 수 없습니다.", "danger")
        return redirect(url_for("index"))

    existing_review = _get_current_user_player_review(cid, player)
    if not existing_review:
        flash("삭제할 리뷰가 없습니다.", "danger")
        return redirect(_safe_local_next_url(url_for("player_detail", cid=cid, _anchor="player-reviews")))

    review_id = str(existing_review.get("id") or existing_review.get("user_id") or current_user.id)
    _delete_current_user_player_review(cid, player)
    PlayerReviewComment.query.filter_by(player_cid=cid, review_id=review_id).delete(synchronize_session=False)
    db.session.commit()
    flash("선수 리뷰가 삭제되었습니다.", "success")
    return redirect(_safe_local_next_url(url_for("player_detail", cid=cid, _anchor="player-reviews")))


def get_stat_color(value, min_val, max_val):
    if value is None or min_val is None or max_val is None or max_val == min_val:
        return "transparent"

    # 값의 범위를 0-100으로 정규화
    normalized_value = (value - min_val) / (max_val - min_val) * 100

    # 색상 그라데이션 (예: 연한 파랑 -> 진한 파랑)
    # HSL 색상 모델 사용 (Hue, Saturation, Lightness)
    # Hue: 파란색 계열 (200-240)
    # Saturation: 50-100%
    # Lightness: 70-40% (밝은 색에서 어두운 색으로)

    # Hue는 고정 (파란색 계열)
    h = 210
    # Saturation은 값에 따라 증가
    s = 50 + (normalized_value * 0.5) # 50%에서 100%까지
    # Lightness는 값에 따라 감소
    l = 70 - (normalized_value * 0.3) # 70%에서 40%까지

    return f"hsl({h}, {s}%, {l}%)"

app.jinja_env.globals.update(get_stat_color=get_stat_color)

# 자동완성 기능 (로컬 데이터 사용)
@app.route("/autocomplete")
def autocomplete():
    q = request.args.get("q", "").strip()
    class_name = request.args.get("class", "").strip()

    if not q and not class_name:
        return jsonify([])

    query = _normalize_name_for_match(q)
    class_query = _normalize_name_for_match(class_name)
    unique_names = []
    seen_names = set()

    players_sorted = sorted(
        PLAYER_DATA,
        key=lambda p: (-(p.get("ovr") or 0), p.get("playerKor") or ""),
    )
    for player in players_sorted:
        player_name = player.get("playerKor")
        normalized_name = _normalize_name_for_match(player_name)
        if not player_name or (query and query not in normalized_name):
            continue
        if class_query and class_query not in _normalize_name_for_match(player.get("className")):
            continue
        if player_name in seen_names:
            continue
        seen_names.add(player_name)
        unique_names.append({"playerKor": player_name})
        if len(unique_names) >= 15:
            break

    return jsonify(unique_names)


@app.route("/api/squad_players")
def api_squad_players():
    q = request.args.get("q", "").strip()
    slot = request.args.get("slot", "").strip().upper()
    class_name = request.args.get("class", "").strip()
    limit = request.args.get("limit", default=24, type=int)
    limit = max(1, min(limit, 60))

    ranked = []
    for player in PLAYER_DATA:
        score = _score_squad_player(player, name_query=q, slot_position=slot, class_query=class_name)
        if score is None:
            continue

        normalized = _apply_local_assets(_normalize_player_record(player.copy()))
        ranked.append(
            {
                "score": score,
                "player": {
                    "cid": normalized.get("cid"),
                    "playerKor": normalized.get("playerKor"),
                    "playerEng": normalized.get("playerEng"),
                    "className": normalized.get("className"),
                    "ovr": normalized.get("ovr"),
                    "position": normalized.get("position"),
                    "positions": _extract_player_positions(normalized),
                    "potentialPosition": normalized.get("potentialPosition"),
                    "potentialPositions": _extract_potential_positions(normalized),
                    "jerseyNumber": normalized.get("jerseyNumber"),
                    "team": normalized.get("team"),
                    "league": normalized.get("league"),
                    "nation": normalized.get("nation") or normalized.get("nationality"),
                    "pimage": normalized.get("pimage"),
                    "bimage": normalized.get("bimage"),
                    "price": _extract_price(normalized),
                    "skillBoostName": normalized.get("skillBoostName"),
                    "skillInfo": normalized.get("skillInfo"),
                    "skills": _extract_player_skills(normalized),
                    "skillDisplay": _extract_player_skill_items(normalized),
                    "skillStyleId": normalized.get("skillStyleId"),
                    "staticPlayStyles": normalized.get("staticPlayStyles") or [],
                    "playStyleSlotMaxLevels": normalized.get("playStyleSlotMaxLevels"),
                    "playstyles": _extract_player_playstyles(normalized),
                    "skillMovesName": normalized.get("skillMovesName"),
                    "skillMovesLevel": normalized.get("skillMovesLevel"),
                    "mainFoot": normalized.get("mainFoot"),
                    "footL": normalized.get("footL"),
                    "footR": normalized.get("footR"),
                    "height": normalized.get("height"),
                    "weight": normalized.get("weight"),
                    "traits": normalized.get("traits", []),
                },
            }
        )

    ranked.sort(
        key=lambda item: (
            -item["score"],
            -(item["player"].get("ovr") or 0),
            -(item["player"].get("price") or 0),
            item["player"].get("playerKor") or "",
        )
    )
    return jsonify([item["player"] for item in ranked[:limit]])


@app.route("/api/player_compare")
def api_player_compare():
    cid = request.args.get("cid", type=int)
    if not cid:
        return jsonify({"error": "cid is required"}), 400

    player = _get_local_player_by_cid(cid)
    if not player:
        return jsonify({"error": "player not found"}), 404

    compare_player = _build_compare_player(player)
    return jsonify(
        {
            "player": compare_player,
            "stat_groups": _get_compare_stat_groups(compare_player),
        }
    )


# 선수 세부검색 페이지 (로컬 데이터 사용)
@app.route("/traits_selection")
def traits_selection():
    player_classes = sorted(
        {
            str(player.get("className") or "").strip()
            for player in PLAYER_DATA
            if str(player.get("className") or "").strip()
        },
        key=lambda value: value.casefold(),
    )
    player_heights = []
    for player in PLAYER_DATA:
        try:
            player_heights.append(int(player.get("height")))
        except (TypeError, ValueError):
            continue
    skill_or_boost_names = sorted(
        {
            name
            for player in PLAYER_DATA
            for name in _extract_player_skill_or_boost_names(player)
        }
        | set(SKILL_BOOST_STATS.keys())
        | set(NEW_SKILL_STATS.keys())
        | set(SKILL_ID_NAME_MAP.values())
    )
    skill_moves = sorted(
        {
            str(player.get("skillMovesName")).strip()
            for player in PLAYER_DATA
            if str(player.get("skillMovesName") or "").strip()
        }
    )
    skill_levels = sorted(
        {
            int(player.get("skillMovesLevel"))
            for player in PLAYER_DATA
            if str(player.get("skillMovesLevel") or "").strip() or player.get("skillMovesLevel") == 0
        }
    )
    traits = sorted(
        {
            trait
            for player in PLAYER_DATA
            for trait in _extract_player_traits(player)
            if trait
        }
    )
    playstyles = sorted(
        {
            playstyle["name"]
            for player in PLAYER_DATA
            for playstyle in _extract_player_playstyles(player)
            if playstyle.get("name")
        }
    )
    positions = sorted(
        {
            position
            for player in PLAYER_DATA
            for position in [_extract_primary_player_position(player)]
            if position
        }
    )
    career_index = _build_player_career_index()
    current_team_index = _build_player_current_team_index()
    current_league_teams = _build_league_team_map(current_team_index.values())
    all_league_teams = _build_league_team_map(
        pair for pairs in career_index.values() for pair in pairs
    )

    return render_template(
        "traits_selection.html",
        player_classes=player_classes,
        skill_or_boost_names=skill_or_boost_names,
        skill_moves=skill_moves,
        skill_levels=skill_levels,
        traits=traits,
        playstyles=playstyles,
        positions=positions,
        work_rate_options=WORK_RATE_OPTIONS,
        raised_stat_options=RAISED_STAT_OPTIONS,
        current_league_teams=current_league_teams,
        all_league_teams=all_league_teams,
        default_min_ovr=DETAIL_SEARCH_DEFAULT_MIN_OVR,
        default_max_ovr=DETAIL_SEARCH_DEFAULT_MAX_OVR,
        min_player_height=min(player_heights) if player_heights else 150,
        max_player_height=max(player_heights) if player_heights else 210,
        canonical_url=_canonical("/traits_selection"),
        robots_meta="index,follow",
        meta_description="FC모바일 선수를 이름, OVR, 포지션, 클래스, 키, 특성, 플레이스타일과 팀 경력 조건으로 상세 검색하세요.",
        og_title="FC모바일 선수 세부 검색 | 피모북",
        og_description="FC모바일 선수를 능력치, 클래스, 특성, 플레이스타일과 팀 경력으로 검색하세요.",
    )


# 선수 세부검색 결과 페이지 (로컬 데이터 사용)
@app.route("/filtered_players", methods=["GET"])
def filtered_players():
    name_query = request.args.get("name", "").strip()
    skill_or_boosts = _get_filter_values("skill_or_boost")
    legacy_skill_boosts = _get_filter_values("skill_boost")
    for value in legacy_skill_boosts:
        if value not in skill_or_boosts:
            skill_or_boosts.append(value)
    positions = _get_filter_values("position", uppercase=True)
    include_sub_position = str(request.args.get("include_sub_position", "")).strip().lower() in {"1", "true", "yes", "on"}
    skill_moves = _get_filter_values("skill_move")
    skill_levels = _clean_filter_values(request.args.getlist("skill_level"))
    raised_stats = _clean_filter_values(request.args.getlist("raised_stat"), uppercase=True)
    selected_work_rates = [
        value
        for value in _clean_filter_values(request.args.getlist("work_rate"))
        if value in WORK_RATE_OPTION_MAP
    ]
    traits = _get_filter_values("trait")
    playstyles = _get_filter_values("playstyle")
    player_classes = _get_filter_values("player_class")
    height_group = request.args.get("height_group", "").strip()
    min_height_str = request.args.get("min_height", "").strip()
    max_height_str = request.args.get("max_height", "").strip()
    weak_foot_min_str = request.args.get("weak_foot_min", "").strip()
    selected_league = request.args.get("league", "").strip()
    selected_team = request.args.get("team", "").strip()
    all_career = str(request.args.get("all_career", "")).strip().lower() in {"1", "true", "yes", "on"}
    min_ovr_str = request.args.get("min_ovr", "").strip()
    max_ovr_str = request.args.get("max_ovr", "").strip()
    sort = request.args.get("sort", "ovr_desc").strip() or "ovr_desc"

    min_ovr = int(min_ovr_str) if min_ovr_str.isdigit() else DETAIL_SEARCH_DEFAULT_MIN_OVR
    max_ovr = int(max_ovr_str) if max_ovr_str.isdigit() else DETAIL_SEARCH_DEFAULT_MAX_OVR
    min_height = int(min_height_str) if min_height_str.isdigit() else None
    max_height = int(max_height_str) if max_height_str.isdigit() else None
    weak_foot_min = int(weak_foot_min_str) if weak_foot_min_str in {"1", "2", "3", "4", "5"} else 0
    normalized_skill_or_boosts = {_normalize_filter_text(value) for value in skill_or_boosts}
    normalized_skill_moves = {_normalize_filter_text(value) for value in skill_moves}
    normalized_traits = {_normalize_filter_text(value) for value in traits}
    normalized_playstyles = {_normalize_filter_text(value) for value in playstyles}
    normalized_player_classes = {_normalize_filter_text(value) for value in player_classes}
    selected_skill_levels = {int(value) for value in skill_levels if str(value).isdigit()}
    valid_stat_codes = {item["code"] for item in RAISED_STAT_OPTIONS}
    selected_raised_stat_codes = [code for code in raised_stats if code in valid_stat_codes][:5]
    career_index = _extend_career_index_with_external_data(_build_player_career_index()) if all_career else {}
    current_team_index = _build_player_current_team_index()
    filters = {
        "name": name_query,
        "skill_or_boosts": skill_or_boosts,
        "positions": positions,
        "include_sub_position": include_sub_position,
        "skill_moves": skill_moves,
        "skill_levels": sorted(selected_skill_levels),
        "raised_stats": selected_raised_stat_codes,
        "raised_stat_labels": [STAT_CODE_LABELS.get(code, code) for code in selected_raised_stat_codes],
        "work_rates": selected_work_rates,
        "work_rate_labels": _work_rate_labels(selected_work_rates),
        "traits": traits,
        "playstyles": playstyles,
        "player_classes": player_classes,
        "height_group": height_group,
        "min_height": min_height,
        "max_height": max_height,
        "weak_foot_min": weak_foot_min,
        "league": selected_league,
        "team": selected_team,
        "all_career": all_career,
        "min_ovr": min_ovr,
        "max_ovr": max_ovr,
    }

    if min_height is not None and max_height is not None and min_height > max_height:
        return render_template(
            "filtered_players_results.html",
            error="최소 키는 최대 키보다 클 수 없습니다.",
            players=[],
            filters=filters,
            sort=sort,
            robots_meta="noindex,follow",
        )

    if len(raised_stats) > 5:
        return render_template(
            "filtered_players_results.html",
            error="상승 스탯은 최대 5개까지만 선택할 수 있습니다.",
            players=[],
            filters=filters,
            sort=sort,
            robots_meta="noindex,follow",
        )

    if selected_raised_stat_codes and normalized_skill_or_boosts:
        return render_template(
            "filtered_players_results.html",
            error="상승 스탯 필터는 스킬/스킬부스트 필터와 함께 사용할 수 없습니다.",
            players=[],
            filters=filters,
            sort=sort,
            robots_meta="noindex,follow",
        )

    if not PLAYER_DATA:
        return render_template(
            "filtered_players_results.html",
            error="선수 데이터가 로드되지 않았습니다. 서버 로그를 확인하고 'player_data.json' 파일이 있는지 확인해주세요.",
            players=[],
            filters=filters,
            sort=sort,
            robots_meta="noindex,follow",
        )

    normalized_name_query = _normalize_name_for_match(name_query)
    filtered_list = []
    for player in PLAYER_DATA:
        player_ovr = int(player.get("ovr") or 0)
        if not (min_ovr <= player_ovr <= max_ovr):
            continue

        player_name = _normalize_name_for_match(player.get("playerKor"))
        if normalized_name_query and normalized_name_query not in player_name:
            continue

        player_skill_or_boosts = {
            _normalize_filter_text(value)
            for value in _extract_player_skill_or_boost_names(player)
        }
        if normalized_skill_or_boosts and player_skill_or_boosts.isdisjoint(normalized_skill_or_boosts):
            continue

        if selected_raised_stat_codes:
            player_raised_stats = _extract_player_raised_stat_codes(player)
            if player_raised_stats.isdisjoint(selected_raised_stat_codes):
                continue

        player_height = player.get("height")
        try:
            player_height = int(player_height)
        except (TypeError, ValueError):
            player_height = None
        if height_group == "tall" and (player_height is None or player_height < 185):
            continue
        if height_group == "short" and (player_height is None or player_height >= 185):
            continue
        if min_height is not None and (player_height is None or player_height < min_height):
            continue
        if max_height is not None and (player_height is None or player_height > max_height):
            continue

        player_class = _normalize_filter_text(player.get("className"))
        if normalized_player_classes and player_class not in normalized_player_classes:
            continue

        if weak_foot_min and _get_weak_foot_value(player) < weak_foot_min:
            continue

        player_position = _extract_primary_player_position(player)
        if positions:
            matches_position = player_position in positions
            if include_sub_position and not matches_position:
                secondary_positions = set(_extract_player_positions(player))
                if player_position:
                    secondary_positions.discard(player_position)
                matches_position = not secondary_positions.isdisjoint(positions)
            if not matches_position:
                continue

        player_skill_move = _normalize_filter_text(player.get("skillMovesName"))
        if normalized_skill_moves and player_skill_move not in normalized_skill_moves:
            continue

        player_traits = {_normalize_filter_text(value) for value in _extract_player_traits(player)}
        if normalized_traits and player_traits.isdisjoint(normalized_traits):
            continue

        player_playstyles = _extract_player_playstyle_filter_values(player)
        if normalized_playstyles and player_playstyles.isdisjoint(normalized_playstyles):
            continue

        player_skill_level = player.get("skillMovesLevel")
        if selected_skill_levels and player_skill_level not in selected_skill_levels:
            continue

        if selected_work_rates and _player_work_rate_key(player) not in selected_work_rates:
            continue

        if not _player_matches_team_filter(
            player,
            selected_league,
            selected_team,
            all_career,
            career_index,
            current_team_index,
        ):
            continue

        normalized = _apply_local_assets(_normalize_player_record(player.copy()))
        normalized["price"] = _extract_price(normalized)
        normalized["skillLabels"] = _extract_player_skills(normalized)
        normalized["playstyles"] = _extract_player_playstyles(normalized)
        normalized["potentialPositions"] = _extract_potential_positions(normalized)
        filtered_list.append(normalized)

    if sort == "ovr_asc":
        filtered_list.sort(key=lambda p: (p.get("ovr") or 0, p.get("playerKor") or ""))
    elif sort == "name_asc":
        filtered_list.sort(key=lambda p: (p.get("playerKor") or "", -(p.get("ovr") or 0)))
    elif sort == "price_desc":
        filtered_list.sort(
            key=lambda p: (
                p.get("price") is None,
                -(p.get("price") or 0),
                -(p.get("ovr") or 0),
                p.get("playerKor") or "",
            )
        )
    elif sort == "price_asc":
        filtered_list.sort(
            key=lambda p: (
                p.get("price") is None,
                p.get("price") or 0,
                -(p.get("ovr") or 0),
                p.get("playerKor") or "",
            )
        )
    else:
        filtered_list.sort(key=lambda p: (-(p.get("ovr") or 0), p.get("playerKor") or ""))

    if not filtered_list:
        error_msg = "조건에 맞는 선수를 찾을 수 없습니다. 필터를 조금 완화해 보세요."
        return render_template(
            "filtered_players_results.html",
            error=error_msg,
            players=[],
            filters=filters,
            sort=sort,
            robots_meta="noindex,follow",
        )

    return render_template(
        "filtered_players_results.html",
        error=None,
        players=filtered_list,
        filters=filters,
        sort=sort,
        robots_meta="noindex,follow",
    )


@app.route("/api/player_price/<int:cid>", methods=["GET"])
def api_player_price(cid):
    price = get_live_price(cid)
    return jsonify({"cid": cid, "price": price})


@app.route("/times")
def times():
    return render_template(
        "times.html",
        canonical_url=_canonical("/times"),
        robots_meta="index,follow",
        meta_description="FC모바일 클래스별 갱신시간을 확인하고 선수명과 클래스명으로 빠르게 검색하세요.",
        og_title="FC모바일 갱신시간 | 피모북",
        og_description="FC모바일 클래스별 갱신시간을 검색하고 빠르게 확인하세요.",
    )


@app.route("/clanworldcup")
def clanworldcup_home():
    return render_template("clanworldcup/home.html")


@app.route("/clanworldcup/groups")
def clanworldcup_groups():
    return render_template("clanworldcup/groups.html")


@app.route("/clanworldcup/bracket")
def clanworldcup_bracket():
    return render_template("clanworldcup/bracket.html")


@app.route("/clanworldcup/bracket/full")
def clanworldcup_bracket_full():
    return render_template("clanworldcup/bracket_full.html")


@app.route("/clanworldcup/match/<match_id>")
def clanworldcup_match_detail(match_id):
    match_data = _get_match(match_id)
    games = _get_match_games(match_id)
    return render_template("clanworldcup/match_detail.html", match_id=match_id, match_data=match_data, games=games)


@app.route("/clanworldcup/api/auth/verify", methods=["POST"])
@csrf.exempt
def clanworldcup_verify_code():
    payload = request.get_json(silent=True) or {}
    code = (payload.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "코드를 입력하세요."}), 400
    data = _verify_member_code(code)
    if not data:
        return jsonify({"ok": False, "error": "유효하지 않은 멤버코드입니다."}), 404
    data["code"] = code
    return jsonify({"ok": True, "member": data})


@app.route("/clanworldcup/api/match/<match_id>", methods=["GET"])
def clanworldcup_match_api(match_id):
    if not fs:
        return jsonify({"ok": False, "error": "Firestore 연결이 없습니다."}), 503
    match_data = _get_match(match_id)
    if not match_data:
        return jsonify({"ok": False, "error": "매치를 찾을 수 없습니다."}), 404
    games = _get_match_games(match_id)
    return jsonify({"ok": True, "match": match_data, "games": games})


@app.route("/clanworldcup/api/matches", methods=["GET"])
def clanworldcup_matches_api():
    if not fs:
        return jsonify({"ok": False, "error": "Firestore 연결이 없습니다."}), 503
    phase = request.args.get("phase", "").strip()
    group = request.args.get("group", "").strip().upper()
    leg = request.args.get("leg", "").strip().lower()
    base = _fs_base()
    q = base.collection("matches")
    if phase:
        q = _fs_where(q, "phase", "==", phase)
    if group and group != "ALL":
        q = _fs_where(q, "group", "==", group)
    if leg == "1":
        q = _fs_where(q, "leg", "==", int(leg))
    phase_upper = (phase or "").upper()
    # block_knockout = False
    # if phase_upper in {"QF", "SF", "F"} or not phase_upper:
    #     block_knockout = not _is_group_stage_complete(base)
    clan_ids = None
    if phase_upper == "GROUP":
        clan_ids = set()
        for c in _get_clans():
            name = c.get("name") or c.get("clanId") or c.get("clan_id") or c.get("id")
            if _is_placeholder_clan_name(name):
                continue
            clan_id = _normalize_clan_id(c.get("clanId") or c.get("clan_id") or c.get("id") or name)
            if clan_id:
                clan_ids.add(clan_id)
    matches = []
    base = _fs_base()

    # For on-the-fly resolution of seeds and winners
    group_seed_map = _build_group_seed_map(base)
    winner_map = {}
    # We fetch all matches once to build a winner map
    all_docs = base.collection("matches").stream()
    for adoc in all_docs:
        ad = adoc.to_dict() or {}
        if (ad.get("status") or "").upper() == "FINAL":
            w = ad.get("winnerClanId")
            if w and not _is_seed_placeholder(w):
                winner_map[adoc.id] = w

    for doc in q.stream():
        data = doc.to_dict() or {}
        data["id"] = doc.id

        # Resolve placeholders on the fly
        h_val = data.get("homeClanId")
        a_val = data.get("awayClanId")
        labels = _knockout_seed_labels(data["id"])
        if labels:
            if _is_seed_placeholder(h_val):
                data["homeClanId"] = _resolve_knockout_seed(labels[0], group_seed_map, winner_map)
            if _is_seed_placeholder(a_val):
                data["awayClanId"] = _resolve_knockout_seed(labels[1], group_seed_map, winner_map)

        if clan_ids is not None:
            home_id = _normalize_clan_id(data.get("homeClanId"))
            away_id = _normalize_clan_id(data.get("awayClanId"))
            if not home_id or not away_id or home_id not in clan_ids or away_id not in clan_ids:
                continue
        matches.append(data)
    phase_order = {"GROUP": 0, "QF": 1, "SF": 2, "F": 3}
    matches.sort(key=lambda m: (phase_order.get(str(m.get("phase") or "").upper(), 99), m.get("id", "")))
    return jsonify({"ok": True, "matches": matches})


@app.route("/clanworldcup/api/clans", methods=["GET"])
def clanworldcup_clans_api():
    if not fs:
        return jsonify({"ok": False, "error": "Firestore 연결이 없습니다."}), 503
    return jsonify({"ok": True, "clans": _get_clans()})


@app.route("/clanworldcup/api/standings", methods=["GET"])
def clanworldcup_standings_api():
    if not fs:
        return jsonify({"ok": False, "error": "Firestore 연결이 없습니다."}), 503
    return jsonify({"ok": True, "standings": _get_standings()})


@app.route("/clanworldcup/api/match/<match_id>/games/<int:slot>", methods=["POST"])
@csrf.exempt
def clanworldcup_update_game(match_id, slot):
    if not fs:
        return jsonify({"ok": False, "error": "Firestore 연결이 없습니다."}), 503
    payload = request.get_json(silent=True) or {}
    code = (payload.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "멤버코드를 입력하세요."}), 400
    member = _verify_member_code(code)
    if not member:
        return jsonify({"ok": False, "error": "유효하지 않은 멤버코드입니다."}), 404

    match_data = _get_match(match_id)
    if not match_data:
        return jsonify({"ok": False, "error": "매치를 찾을 수 없습니다."}), 404

    is_admin = member.get("admin")
    allowed_clans = {
        _normalize_clan_key(match_data.get("homeClanId")),
        _normalize_clan_key(match_data.get("awayClanId")),
    }
    member_clan = _normalize_clan_key(member.get("clanId"))
    if not is_admin and (not member_clan or member_clan not in allowed_clans):
        return jsonify({"ok": False, "error": "다른 팀의 경기 결과는 수정할 수 없습니다."}), 403

    status = (payload.get("status") or "FINAL").upper()
    home_score = payload.get("homeScore")
    away_score = payload.get("awayScore")

    try:
        home_score = int(home_score) if home_score is not None else None
        away_score = int(away_score) if away_score is not None else None
    except ValueError:
        return jsonify({"ok": False, "error": "점수는 숫자여야 합니다."}), 400

    if status == "FINAL":
        if home_score is None or away_score is None:
            return jsonify({"ok": False, "error": "FINAL 상태에서는 점수가 필요합니다."}), 400
        if home_score == away_score:
            return jsonify({"ok": False, "error": "동점은 허용되지 않습니다."}), 400
    elif status == "NOT_PLAYED":
        home_score = None
        away_score = None
    else:
        return jsonify({"ok": False, "error": "허용되지 않는 상태입니다."}), 400

    base = _fs_base()
    match_ref = base.collection("matches").document(match_id)
    game_ref = match_ref.collection("games").document(str(slot))
    game_ref.set({
        "slot": slot,
        "homeScore": home_score,
        "awayScore": away_score,
        "status": status,
    }, merge=True)

    updated = _recalc_match_totals(match_id)
    games = _get_match_games(match_id)
    if updated and (updated.get("phase") or "").upper() == "GROUP":
        _recalc_standings()
    if updated:
        _sync_knockout_bracket(base)

    return jsonify({
        "ok": True,
        "match": updated,
        "games": games,
    })


@app.route("/clanworldcup/api/match/<match_id>/games/<int:slot>/upload", methods=["POST"])
@csrf.exempt
def clanworldcup_upload_result(match_id, slot):
    if not fs:
        return jsonify({"ok": False, "error": "Firestore 연결이 없습니다."}), 503
    code = (request.form.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "멤버코드를 입력하세요."}), 400
    member = _verify_member_code(code)
    if not member:
        return jsonify({"ok": False, "error": "유효하지 않은 멤버코드입니다."}), 404

    match_data = _get_match(match_id)
    if not match_data:
        return jsonify({"ok": False, "error": "매치를 찾을 수 없습니다."}), 404

    is_admin = member.get("admin")
    allowed_clans = {
        _normalize_clan_key(match_data.get("homeClanId")),
        _normalize_clan_key(match_data.get("awayClanId")),
    }
    member_clan = _normalize_clan_key(member.get("clanId"))
    if not is_admin and (not member_clan or member_clan not in allowed_clans):
        return jsonify({"ok": False, "error": "다른 팀의 경기 결과는 수정할 수 없습니다."}), 403

    if "file" not in request.files:
        return jsonify({"ok": False, "error": "파일을 업로드하세요."}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"ok": False, "error": "파일을 업로드하세요."}), 400
    if not allowed_image(file.filename):
        return jsonify({"ok": False, "error": "지원하지 않는 이미지 형식입니다."}), 400
    try:
        file.stream.seek(0, os.SEEK_END)
        size = file.stream.tell()
        file.stream.seek(0)
    except Exception:
        size = None
    if size is not None and size > app.config['MAX_SCREENSHOT_BYTES']:
        return jsonify({"ok": False, "error": "스샷은 10MB 이하만 업로드 가능합니다."}), 400

    filename = secure_filename(file.filename)
    _, ext = os.path.splitext(filename)
    safe_ext = ext.lower()
    save_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'clanworldcup')
    os.makedirs(save_dir, exist_ok=True)
    unique_name = f"{match_id}-slot{slot}-{int(time.time())}{safe_ext}"
    save_path = os.path.join(save_dir, unique_name)
    file.save(save_path)

    rel_path = os.path.join('uploads', 'clanworldcup', unique_name)
    screenshot_url = url_for('static', filename=rel_path, _external=False)

    base = _fs_base()
    match_ref = base.collection("matches").document(match_id)
    game_ref = match_ref.collection("games").document(str(slot))
    game_ref.set({
        "slot": slot,
        "screenshotUrl": screenshot_url,
    }, merge=True)

    games = _get_match_games(match_id)
    match = _get_match(match_id)
    return jsonify({
        "ok": True,
        "screenshotUrl": screenshot_url,
        "games": games,
        "match": match,
    })


@app.route("/clanworldcup/api/match/<match_id>/games/<int:slot>/screenshot", methods=["DELETE"])
@csrf.exempt
def clanworldcup_delete_screenshot(match_id, slot):
    if not fs:
        return jsonify({"ok": False, "error": "Firestore 연결이 없습니다."}), 503
    payload = request.get_json(silent=True) or {}
    code = (payload.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "멤버코드를 입력하세요."}), 400
    member = _verify_member_code(code)
    if not member:
        return jsonify({"ok": False, "error": "유효하지 않은 멤버코드입니다."}), 404

    match_data = _get_match(match_id)
    if not match_data:
        return jsonify({"ok": False, "error": "매치를 찾을 수 없습니다."}), 404

    is_admin = member.get("admin")
    allowed_clans = {
        _normalize_clan_key(match_data.get("homeClanId")),
        _normalize_clan_key(match_data.get("awayClanId")),
    }
    member_clan = _normalize_clan_key(member.get("clanId"))
    if not is_admin and (not member_clan or member_clan not in allowed_clans):
        return jsonify({"ok": False, "error": "다른 팀의 경기 결과는 수정할 수 없습니다."}), 403

    base = _fs_base()
    match_ref = base.collection("matches").document(match_id)
    game_ref = match_ref.collection("games").document(str(slot))
    snap = game_ref.get()
    screenshot_url = ""
    if snap.exists:
        data = snap.to_dict() or {}
        screenshot_url = data.get("screenshotUrl") or ""

    if screenshot_url:
        if screenshot_url.startswith("/static/"):
            rel = screenshot_url[len("/static/"):]
        elif "/static/" in screenshot_url:
            rel = screenshot_url.split("/static/", 1)[1]
        else:
            rel = ""
        if rel:
            file_path = os.path.join(app.root_path, "static", rel)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass

    game_ref.set({"screenshotUrl": None}, merge=True)
    games = _get_match_games(match_id)
    match = _get_match(match_id)
    return jsonify({
        "ok": True,
        "games": games,
        "match": match,
    })


@app.route("/clanworldcup/api/standings/recalc", methods=["POST"])
@csrf.exempt
def clanworldcup_recalc_standings():
    if not fs:
        return jsonify({"ok": False, "error": "Firestore 연결이 없습니다."}), 503
    result = _recalc_standings()
    if result.get("error"):
        return jsonify({"ok": False, "error": result["error"]}), 400
    base = _fs_base()
    if base:
        _sync_knockout_bracket(base)
    return jsonify({"ok": True, "groups": result.get("groups", [])})


@app.route("/clanworldcup/api/admin/seed", methods=["POST"])
@csrf.exempt
def clanworldcup_admin_seed():
    if not fs:
        return jsonify({"ok": False, "error": "Firestore 연결이 없습니다."}), 503
    payload = request.get_json(silent=True) or {}
    code = (payload.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "멤버코드를 입력하세요."}), 400
    member = _verify_member_code(code)
    if not member or not member.get("admin"):
        return jsonify({"ok": False, "error": "관리자 권한이 없습니다."}), 403

    base = _fs_base()
    if not base:
        return jsonify({"ok": False, "error": "Firestore 연결이 없습니다."}), 503
    seed_result = _seed_schedule(base)
    standings_result = _recalc_standings()
    bracket_result = _sync_knockout_bracket(base)
    return jsonify({
        "ok": True,
        "seed": seed_result,
        "standings": standings_result,
        "bracket": bracket_result,
    })


@app.route("/clanworldcup/api/admin/rebuild-groups", methods=["POST"])
@csrf.exempt
def clanworldcup_admin_rebuild_groups():
    if not fs:
        return jsonify({"ok": False, "error": "Firestore 연결이 없습니다."}), 503
    payload = request.get_json(silent=True) or {}
    code = (payload.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "멤버코드를 입력하세요."}), 400
    member = _verify_member_code(code)
    if not member or not member.get("admin"):
        return jsonify({"ok": False, "error": "관리자 권한이 없습니다."}), 403

    base = _fs_base()
    if not base:
        return jsonify({"ok": False, "error": "Firestore 연결이 없습니다."}), 503

    rebuild = _rebuild_clan_groups_from_group_matches(base)
    standings_result = _recalc_standings()
    bracket_result = _sync_knockout_bracket(base)
    return jsonify({
        "ok": True,
        "rebuild": rebuild,
        "standings": standings_result,
        "bracket": bracket_result,
    })


def _bool_from_query(value, default=True):
    return default if value is None else str(value).lower() not in ("0", "false", "no", "off")


@app.route("/coupons/")
def coupons_page():
    dedupe = _bool_from_query(request.args.get("dedupe"), default=True)
    coupons = get_coupons(dedupe=dedupe)[:5]
    return render_template(
        "coupons.html",
        coupons=coupons,
        canonical_url=_canonical("/coupons/"),
        firebase_config=app.config.get("FIREBASE_WEB_CONFIG") or {},
        firebase_vapid_key=app.config.get("FIREBASE_WEB_VAPID_KEY", ""),
    )


@app.route("/coupons/api")
def coupons_api():
    dedupe = _bool_from_query(request.args.get("dedupe"), default=True)
    coupons = get_coupons(dedupe=dedupe)[:5]
    return jsonify(coupons)


@app.route("/firebase-messaging-sw.js")
def firebase_messaging_sw():
    payload = render_template(
        "firebase-messaging-sw.js",
        firebase_config=app.config.get("FIREBASE_WEB_CONFIG") or {},
    )
    response = Response(payload, mimetype="application/javascript")
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@app.route("/api/push/register", methods=["POST"])
@csrf.exempt
def push_register():
    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    if not token:
        return jsonify({"ok": False, "error": "token required"}), 400

    now = datetime.utcnow()
    existing = PushToken.query.filter_by(token=token).first()
    if existing:
        existing.last_seen = now
        existing.is_enabled = True
        db.session.commit()
        return jsonify({"ok": True, "token": token, "created": False})

    db.session.add(PushToken(token=token, last_seen=now))
    db.session.commit()
    return jsonify({"ok": True, "token": token, "created": True})


@app.route("/api/push/unregister", methods=["POST"])
@csrf.exempt
def push_unregister():
    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    if not token:
        return jsonify({"ok": False, "error": "token required"}), 400

    existing = PushToken.query.filter_by(token=token).first()
    if not existing:
        return jsonify({"ok": True, "token": token, "updated": False})

    existing.is_enabled = False
    existing.last_seen = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "token": token, "updated": True})


@app.route("/api/push/prefs", methods=["POST"])
@csrf.exempt
def push_prefs():
    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    if not token:
        return jsonify({"ok": False, "error": "token required"}), 400

    existing = PushToken.query.filter_by(token=token).first()
    if not existing:
        return jsonify({"ok": False, "error": "token not found"}), 404

    coupons_enabled = payload.get("coupons_enabled")
    mode = (payload.get("mode") or "").strip().lower()
    if mode and mode not in ("digest", "instant"):
        return jsonify({"ok": False, "error": "invalid mode"}), 400

    parsed_enabled = _parse_bool(coupons_enabled)
    if parsed_enabled is None and coupons_enabled is not None:
        return jsonify({"ok": False, "error": "invalid coupons_enabled"}), 400

    if parsed_enabled is not None:
        existing.coupons_enabled = parsed_enabled
    if mode:
        existing.mode = mode
    existing.last_seen = datetime.utcnow()
    db.session.commit()
    return jsonify({
        "ok": True,
        "token": token,
        "coupons_enabled": existing.coupons_enabled,
        "mode": existing.mode,
    })


@app.route("/api/push/status", methods=["GET"])
def push_status():
    token = (request.args.get("token") or "").strip()
    if not token:
        return jsonify({"ok": False, "error": "token required"}), 400
    existing = PushToken.query.filter_by(token=token).first()
    if not existing:
        return jsonify({"ok": False, "error": "token not found"}), 404
    return jsonify({
        "ok": True,
        "token": token,
        "is_enabled": existing.is_enabled,
        "coupons_enabled": existing.coupons_enabled,
        "mode": existing.mode,
        "last_seen": existing.last_seen.isoformat() if existing.last_seen else None,
        "last_push_at": existing.last_push_at.isoformat() if existing.last_push_at else None,
    })

@app.errorhandler(404)
def not_found_error(error):
    """404 에러 핸들러"""
    return render_template('errors/404.html'), 404

#@app.errorhandler(500)
#def internal_error(error):
#    """500 에러 핸들러"""
#    return render_template('errors/500.html'), 500

#@app.errorhandler(Exception)
#def handle_exception(e):
#    """일반적인 예외 핸들러 (500 에러로 처리)"""
#    # 개발 환경에서는 실제 에러를 보여주고, 프로덕션에서는 500 페이지를 보여줌
#    if app.debug:
#        return str(e), 500
#    return render_template('errors/500.html'), 500

# 선수 이름을 받아 상세 정보를 JSON으로 반환하는 API 엔드포인트
@app.route("/api/player_details_by_name")
def api_player_details_by_name():
    player_name = request.args.get("player_name", "").strip()
    if not player_name:
        return jsonify({"error": "Player name is required"}), 400

    player_list = _search_local_players_by_name(player_name)
    if not player_list:
        return jsonify({"error": "Player not found"}), 404

    return jsonify(player_list[0])


if __name__ == '__main__':
    #with app.app_context():
        #db.create_all()  # 이 라인은 주석 처리된 상태로 유지합니다.
    pass
    #app.run(host="0.0.0.0", port=8000, debug=True)
