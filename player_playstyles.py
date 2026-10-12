"""Player playstyle metadata lookup and equipped-playstyle extraction."""

import json
import os
import re
from urllib.parse import quote
from player_search import _normalize_filter_text

PLAYSTYLE_CDN_BASE = "https://fco.vod.nexoncdn.co.kr/jade_assets/playstyle/playstyle_128"
PLAYSTYLE_META_FILE = None
_PLAYSTYLE_META_BY_ID = None
_root_path = None


def configure(root_path):
    """Locate the bundled playstyle metadata under the application root."""
    global _root_path, PLAYSTYLE_META_FILE
    _root_path = root_path
    PLAYSTYLE_META_FILE = os.path.join(root_path, "static", "playstyles", "meta.json")


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
    local_path = os.path.join(_root_path, "static", "playstyles", filename)
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


def _normalize_review_playstyle_config(items):
    normalized = []
    meta_by_id = _load_playstyle_meta()
    for index, item in enumerate(items if isinstance(items, list) else []):
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        if not code:
            continue
        meta = meta_by_id.get(code, {})
        try:
            slot_number = max(1, int(item.get("slotNumber") or index + 1))
        except (TypeError, ValueError):
            slot_number = index + 1
        icon_name = meta.get("icon") or item.get("icon") or code
        normalized.append(
            {
                "code": code,
                "name": str(item.get("name") or meta.get("korname") or _fallback_playstyle_name(code)).strip(),
                "description": str(item.get("description") or meta.get("description") or "").strip(),
                "category": str(item.get("category") or meta.get("category") or "").strip(),
                "level": item.get("level") if item.get("level") is not None else meta.get("level"),
                "imageUrl": _playstyle_image_url(icon_name),
                "slotNumber": slot_number,
            }
        )
    return normalized


def _extract_player_playstyle_filter_values(player):
    values = set()
    for item in _extract_player_playstyles(player):
        for key in ("name", "code"):
            normalized = _normalize_filter_text(item.get(key))
            if normalized:
                values.add(normalized)
    return values
