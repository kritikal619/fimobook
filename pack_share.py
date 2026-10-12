"""Signed, shareable pack-opening summaries and their preview image.

The draw API signs a compact summary of each result, so a shared link can only
show results the server actually produced. The token carries the summary itself;
nothing is stored server-side.
"""

from io import BytesIO
import os

from itsdangerous import BadSignature, URLSafeSerializer
from PIL import Image, ImageDraw

from player_stats_card import (
    _stats_card_asset_image,
    _stats_card_contain,
    _stats_card_fit_text,
    _stats_card_font,
    _stats_card_paste_center,
)

SHARE_SALT = "pack-share-v1"
SHARE_TOP_PLAYERS = 5
MAX_TOKEN_LENGTH = 1200
IMAGE_SIZE = (1200, 630)

BG = "#080d19"
PANEL = "#111827"
BORDER = "#263247"
TEXT = "#f8fafc"
MUTED = "#93a4b8"
ACCENT = "#22d3a6"
GOLD = "#fbbf24"

_IMAGE_CACHE = {}
_IMAGE_CACHE_LIMIT = 128


def _serializer(secret_key):
    return URLSafeSerializer(secret_key, salt=SHARE_SALT)


def _player_rewards(result):
    return [reward for reward in result.get("rewards", []) if reward.get("kind") == "player"]


def build_share_token(result, secret_key):
    """Sign the pack name, quantity, best players and totals of a draw result."""
    players = _player_rewards(result)
    if not players:
        return None
    ranked = sorted(
        (reward for reward in players if reward.get("cid")),
        key=lambda reward: (-(reward.get("ovr") or 0), -(reward.get("price") or 0)),
    )
    player_value = sum(
        int(reward["price"]) * int(reward.get("count") or 1)
        for reward in players
        if isinstance(reward.get("price"), int) and reward["price"] > 0
    )
    mp_value = sum(
        int(reward.get("count") or 0)
        for reward in result.get("rewards", [])
        if reward.get("kind") == "item" and str(reward.get("name", "")).startswith("MP")
    )
    payload = {
        "p": str(result.get("packName") or "")[:60],
        "q": int(result.get("quantity") or 1),
        "n": sum(int(reward.get("count") or 1) for reward in players),
        "v": player_value,
        "m": mp_value,
        "t": [[reward["cid"], int(reward.get("enhance") or 0)] for reward in ranked[:SHARE_TOP_PLAYERS]],
    }
    return _serializer(secret_key).dumps(payload)


def read_share_token(token, secret_key):
    """Return the signed summary, or None when the token is invalid."""
    if not token or len(token) > MAX_TOKEN_LENGTH:
        return None
    try:
        payload = _serializer(secret_key).loads(token)
    except BadSignature:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("t"), list):
        return None
    return payload


def format_mp(value):
    value = int(value or 0)
    if value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:,.1f}".rstrip("0").rstrip(".") + "조"
    if value >= 100_000_000:
        return f"{value / 100_000_000:,.1f}".rstrip("0").rstrip(".") + "억"
    if value >= 10_000:
        return f"{value / 10_000:,.0f}만"
    return f"{value:,}"


def _local_asset(root_path, folder, cid):
    for extension in ("webp", "png", "jpg", "jpeg"):
        path = os.path.join(root_path, "static", folder, f"{cid}.{extension}")
        if os.path.isfile(path):
            return path
    return None


def _draw_best_card(canvas, player, root_path, bounds):
    """Card background with the face cut-out on top, as on the opener stage."""
    left, top, right, bottom = bounds
    background = _stats_card_asset_image(_local_asset(root_path, "card", player["cid"]), root_path)
    face = _stats_card_asset_image(_local_asset(root_path, "faceon", player["cid"]), root_path)
    box = (right - left, bottom - top)
    if background:
        background = _stats_card_contain(background, box)
        _stats_card_paste_center(canvas, background, bounds)
    if face:
        face = _stats_card_contain(face, (int(box[0] * 0.72), int(box[1] * 0.62)))
        canvas.alpha_composite(face, (left + (box[0] - face.width) // 2, top + int(box[1] * 0.16)))


def render_share_image(token, summary, players, root_path):
    """Render a 1200x630 link-preview PNG; ``players`` are the summary's cards."""
    cached = _IMAGE_CACHE.get(token)
    if cached is not None:
        return BytesIO(cached)

    canvas = Image.new("RGBA", IMAGE_SIZE, BG)
    draw = ImageDraw.Draw(canvas)
    font_path = os.path.join(root_path, "static", "fonts", "NAME.ttf")
    font = lambda size: _stats_card_font(font_path, size)

    draw.ellipse((760, -320, 1400, 300), fill="#112d31")
    draw.ellipse((-300, 420, 300, 980), fill="#121f38")
    draw.rectangle((0, 0, 14, IMAGE_SIZE[1]), fill=ACCENT)

    card_bounds = (60, 70, 400, 560)
    draw.rounded_rectangle(card_bounds, radius=26, fill=PANEL, outline=BORDER, width=2)
    if players:
        best = players[0]
        _draw_best_card(canvas, best, root_path, (card_bounds[0] + 16, card_bounds[1] + 16,
                                                  card_bounds[2] - 16, card_bounds[3] - 70))
        label = f"OVR {best['ovr']}" + (f"  +{best['enhance']}" if best["enhance"] else "")
        draw.text((card_bounds[0] + 24, card_bounds[3] - 56), label, font=font(30), fill=GOLD)

    x = 450
    draw.text((x, 64), "피모북 팩 오프너", font=font(26), fill=ACCENT)
    pack_name = summary.get("p") or "선수팩"
    draw.text((x, 102), pack_name, font=_stats_card_fit_text(draw, pack_name, font_path, 48, 28, 700), fill=TEXT)
    draw.text((x, 166), f"{summary.get('q', 1):,}팩 개봉 · 선수 {summary.get('n', 0):,}명", font=font(26), fill=MUTED)

    y = 222
    for index, player in enumerate(players):
        row_fill = "#16213a" if index == 0 else PANEL
        draw.rounded_rectangle((x, y, 1140, y + 54), radius=14, fill=row_fill, outline=BORDER, width=1)
        draw.text((x + 18, y + 12), str(player["ovr"]), font=font(26), fill=GOLD if index == 0 else TEXT)
        enhance = f"+{player['enhance']}" if player["enhance"] else ""
        draw.text((x + 82, y + 15), enhance, font=font(20), fill=ACCENT)
        name = f"{player['className']} {player['playerKor']}".strip()
        draw.text((x + 130, y + 13), name, font=_stats_card_fit_text(draw, name, font_path, 26, 16, 520), fill=TEXT)
        draw.text((1124, y + 15), player.get("position") or "", font=font(20), fill=MUTED, anchor="ra")
        y += 62

    total = int(summary.get("v") or 0) + int(summary.get("m") or 0)
    if total:
        draw.text((x, 560), "획득 가치", font=font(24), fill=MUTED)
        draw.text((x + 120, 552), f"{format_mp(total)} MP", font=font(36), fill=TEXT)
    draw.text((1140, 572), "fcbook.info/pack-opener", font=font(20), fill=MUTED, anchor="ra")

    output = BytesIO()
    canvas.convert("RGB").save(output, format="PNG", optimize=True)
    data = output.getvalue()
    if len(_IMAGE_CACHE) >= _IMAGE_CACHE_LIMIT:
        _IMAGE_CACHE.clear()
    _IMAGE_CACHE[token] = data
    return BytesIO(data)
