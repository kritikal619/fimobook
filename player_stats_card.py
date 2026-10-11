"""Player statistics PNG rendering, independent of Flask and database setup.

The summary weights and numeric helpers are also used by player comparison.
Keep those shared definitions here so the card and comparison use the same values.
"""
from io import BytesIO
import os

import requests
from PIL import Image, ImageDraw, ImageFont


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


