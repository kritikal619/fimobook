"""Signed, shareable pack-opening summaries and their preview image.

The draw API signs a compact summary of each result, so a shared link can only
show results the server actually produced. The token carries the summary itself;
nothing is stored server-side.
"""

from io import BytesIO
import hashlib
import math
import os
import random

from itsdangerous import BadSignature, URLSafeSerializer
from PIL import Image, ImageDraw, ImageFilter

from player_stats_card import (
    _stats_card_asset_image,
    _stats_card_contain,
    _stats_card_fit_text,
    _stats_card_font,
)

SHARE_SALT = "pack-share-v1"
SHARE_TOP_PLAYERS = 5
MAX_TOKEN_LENGTH = 1200
IMAGE_SIZE = (1200, 630)

TEXT = "#f8fafc"
MUTED = "#c9d6e3"
DEFAULT_ANIMATION = "DEFAULT26"

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
    animation = ranked[0].get("animation") if ranked else None
    if isinstance(animation, str) and animation.isalnum():
        payload["a"] = animation
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


def _share_background(root_path, animation):
    """Scoreboard frame (7.8s, fireworks lit) from the season's opening cinematic."""
    folder = os.path.join(root_path, "static", "pack-opener", "share-bg")
    for name in (animation, DEFAULT_ANIMATION):
        if isinstance(name, str) and name.isalnum():
            path = os.path.join(folder, f"{name}.jpg")
            if os.path.isfile(path):
                return Image.open(path).convert("RGBA").resize(IMAGE_SIZE)
    return Image.new("RGBA", IMAGE_SIZE, "#05070d")


def _shadowed_text(canvas, xy, text, font, fill, anchor="la", blur=4):
    """Text with the soft dark halo the opener uses (text-shadow: 0 0 5px #000b)."""
    halo = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(halo).text(xy, text, font=font, fill=(0, 0, 0, 200), anchor=anchor,
                              stroke_width=2, stroke_fill=(0, 0, 0, 200))
    canvas.alpha_composite(halo.filter(ImageFilter.GaussianBlur(blur)))
    ImageDraw.Draw(canvas).text(xy, text, font=font, fill=fill, anchor=anchor)


def _is_dark(color):
    value = str(color or "").lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    try:
        r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return False
    return r * .2126 + g * .7152 + b * .0722 < 140


def _card_text(canvas, xy, text, font, color, anchor):
    if _is_dark(color):
        ImageDraw.Draw(canvas).text(xy, text, font=font, fill=color, anchor=anchor)
    else:
        _shadowed_text(canvas, xy, text, font, color or TEXT, anchor=anchor, blur=3)


def _draw_card(canvas, player, root_path, origin, size):
    """The opener's player card: art, face, OVR, position, name, symbols, evolution.

    Offsets mirror .player-card in pack-opener.css, as fractions of the card width.
    """
    x0, y0 = origin
    card = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    background = _stats_card_asset_image(_local_asset(root_path, "card", player["cid"]), root_path)
    face = _stats_card_asset_image(_local_asset(root_path, "faceon", player["cid"]), root_path)
    if background:
        background = _stats_card_contain(background, (size, size))
        card.alpha_composite(background, ((size - background.width) // 2, (size - background.height) // 2))
    if face:
        inner = int(size * 0.95)
        face = _stats_card_contain(face, (inner, inner))
        card.alpha_composite(face, ((size - face.width) // 2, (size - face.height) // 2))

    meta = player.get("meta") or {}
    colors = meta.get("colors") or {}
    fonts_dir = os.path.join(root_path, "static", "fonts")
    _card_text(card, (size * 0.22, size * 0.10), str(player["ovr"]),
               _stats_card_font(os.path.join(fonts_dir, "FCOVR.otf"), int(size * 0.125)),
               colors.get("ovr") or TEXT, "lt")
    if player.get("position"):
        _card_text(card, (size * 0.23, size * 0.24), player["position"],
                   _stats_card_font(os.path.join(fonts_dir, "POSITION.otf"), int(size * 0.0842)),
                   colors.get("pos") or TEXT, "lt")
    name_draw = ImageDraw.Draw(card)
    name_font = _stats_card_fit_text(name_draw, player["playerKor"], os.path.join(fonts_dir, "NAME.ttf"),
                                     int(size * 0.0875), int(size * 0.05), int(size * 0.55))
    _card_text(card, (size * 0.5, size * 0.745), player["playerKor"], name_font,
               colors.get("name") or TEXT, "mb")

    symbols = [
        _stats_card_asset_image(meta.get(key), root_path)
        for key in ("flag", "leagueBadge", "club")
        if isinstance(meta.get(key), str) and meta[key].startswith("/static/")
    ]
    symbols = [_stats_card_contain(icon, (int(size * 0.2), int(size * 0.0833))) for icon in symbols if icon]
    if symbols:
        gap = int(size * 0.0975)
        total = sum(icon.width for icon in symbols) + gap * (len(symbols) - 1)
        x, top = (size - total) // 2, int(size * (1 - 0.161 - 0.0833))
        for icon in symbols:
            card.alpha_composite(icon, (x, top + (int(size * 0.0833) - icon.height) // 2))
            x += icon.width + gap
    if player.get("enhance"):
        badge = _stats_card_asset_image(f"/static/squad/evolution/{player['enhance']}.png", root_path)
        if badge:
            height = int(size * 0.14167)
            badge = badge.resize((max(1, int(badge.width * height / badge.height)), height))
            card.alpha_composite(badge, (int(size * 0.209), int(size * 0.34)))
    canvas.alpha_composite(card, (x0, y0))


def _draw_burst(canvas, center, radius, seed):
    """The opener's reveal: a white-lime flash and lime/mint sparks thrown outward.

    Mirrors .opening-flash (radial #fff -> #dbff9f) and particles() in pack-opener.js,
    frozen mid-burst, with short motion trails.
    """
    rng = random.Random(seed)
    cx, cy = center
    flash = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(flash)
    draw.ellipse((cx - radius * 1.25, cy - radius, cx + radius * 1.25, cy + radius), fill=(219, 255, 159, 130))
    draw.ellipse((cx - radius * 0.55, cy - radius * 0.5, cx + radius * 0.55, cy + radius * 0.5), fill=(255, 255, 255, 160))
    canvas.alpha_composite(flash.filter(ImageFilter.GaussianBlur(radius * 0.4)))

    sparks = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(sparks)
    elapsed = 0.75  # seconds into the 1.5s burst
    for _ in range(170):
        angle = rng.uniform(0, 2 * math.pi)
        speed = rng.uniform(140, 420) * radius / 180
        distance = speed * elapsed
        x = cx + math.cos(angle) * distance
        y = cy + math.sin(angle) * distance + 35 * elapsed ** 2 * radius / 180
        if abs(x - cx) < radius * 0.42 and abs(y - cy) < radius * 0.55:
            continue  # hidden behind the card
        color = (234, 255, 178) if rng.random() > .4 else (158, 255, 220)
        alpha = int(255 * rng.uniform(.7, 1))
        trail = rng.uniform(14, 40)
        tx, ty = x - math.cos(angle) * trail, y - math.sin(angle) * trail
        draw.line((tx, ty, x, y), fill=color + (alpha // 2,), width=3)
        size = rng.uniform(3.5, 7)
        draw.rectangle((x - size / 2, y - size, x + size / 2, y + size), fill=color + (alpha,))
    canvas.alpha_composite(sparks.filter(ImageFilter.GaussianBlur(4)))
    canvas.alpha_composite(sparks)


def render_share_image(token, summary, players, root_path):
    """Render a 1200x630 link-preview PNG: the opener's scoreboard reveal of the best card."""
    cached = _IMAGE_CACHE.get(token)
    if cached is not None:
        return BytesIO(cached)

    canvas = _share_background(root_path, summary.get("a"))
    width, height = IMAGE_SIZE
    font_path = os.path.join(root_path, "static", "fonts", "NAME.ttf")

    shade = Image.new("RGBA", IMAGE_SIZE, (0, 0, 0, 0))
    shade_draw = ImageDraw.Draw(shade)
    for y in range(height):
        edge = max(0.0, 1 - y / 120) if y < 120 else max(0.0, (y - (height - 150)) / 150)
        if edge:
            shade_draw.line((0, y, width, y), fill=(0, 0, 0, int(170 * edge)))
    canvas.alpha_composite(shade)

    if players:
        size = 400
        center = (width // 2, 300)
        seed = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:8], 16)
        _draw_burst(canvas, center, size * 0.62, seed)
        _draw_card(canvas, players[0], root_path, (center[0] - size // 2, center[1] - size // 2), size)

    pack_name = summary.get("p") or "선수팩"
    draw = ImageDraw.Draw(canvas)
    _shadowed_text(canvas, (36, 28), pack_name, _stats_card_fit_text(draw, pack_name, font_path, 32, 20, 820), TEXT)
    facts = f"{summary.get('q', 1):,}팩 · 선수 {summary.get('n', 0):,}명"
    total = int(summary.get("v") or 0) + int(summary.get("m") or 0)
    if total:
        facts += f" · {format_mp(total)} MP"
    _shadowed_text(canvas, (36, height - 30), facts, _stats_card_font(font_path, 26), TEXT, anchor="ls")
    _shadowed_text(canvas, (width - 36, height - 30), "fcbook.info", _stats_card_font(font_path, 22), MUTED, anchor="rs")

    output = BytesIO()
    canvas.convert("RGB").save(output, format="PNG", optimize=True)
    data = output.getvalue()
    if len(_IMAGE_CACHE) >= _IMAGE_CACHE_LIMIT:
        _IMAGE_CACHE.clear()
    _IMAGE_CACHE[token] = data
    return BytesIO(data)
