"""Player skill data: official local skill ids, display items and the fcplayer.org card match.

Skills and boost names always come from the official local data. The fcplayer.org
snapshot (instance/fcplayer_cards.json) is only used to find the matching card id.
"""

import json
import os
import re
import time
from urllib.parse import quote

import requests

from player_rules import FCPLAYER_ASSET_BASE, MAX_ENHANCE_LEVEL, NEW_SKILL_STAT_CODES, SKILL_BOOST_LEVEL_VALUES, SKILL_BOOST_STAT_CODES, SKILL_ID_NAME_MAP
from player_search import _normalize_filter_text
from player_stats_card import STATS_CARD_SUMMARY_WEIGHTS, _stats_card_numeric, _stats_card_summary_value


_instance_path = None


def configure(instance_path):
    """Point the fcplayer snapshot lookup at the application instance folder."""
    global _instance_path
    _instance_path = instance_path


_FCPLAYER_CARD_CACHE = {}


_FCPLAYER_CARD_CACHE_TTL = 6 * 60 * 60


_FCPLAYER_SNAPSHOT = {"mtime": None, "by_name": {}}


def _fcplayer_snapshot_cards(name):
    """Cards from the synced fcplayer.org snapshot, or None when it is unavailable."""
    path = os.path.join(_instance_path, "fcplayer_cards.json")
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    if _FCPLAYER_SNAPSHOT["mtime"] != mtime:
        try:
            with open(path, "r", encoding="utf-8") as snapshot_file:
                cards = json.load(snapshot_file).get("cards") or []
        except (OSError, ValueError) as error:
            print(f"fcplayer snapshot read failed: {error}")
            return None
        by_name = {}
        for card in cards:
            if isinstance(card, dict) and card.get("name"):
                by_name.setdefault(str(card["name"]).strip(), []).append(card)
        _FCPLAYER_SNAPSHOT.update(mtime=mtime, by_name=by_name)
    return _FCPLAYER_SNAPSHOT["by_name"].get(name, [])


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
    target_skill_names = set()
    if target_skill_system == "skill":
        target_skill_names = {
            _normalize_filter_text(_get_skill_name(skill_id)) for skill_id in _player_skill_ids(player)
        }
        target_skill_names.discard("")
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

    cards = _fcplayer_snapshot_cards(name)
    if cards is None:
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
        card_skills = card.get("skills")
        if target_skill_names and isinstance(card_skills, list) and card_skills:
            card_skill_names = {
                _normalize_filter_text(item.get("name")) for item in card_skills if isinstance(item, dict)
            }
            # Same name and OVR can still be a different card; its skills must agree with ours.
            if len(target_skill_names & card_skill_names) < 3:
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

    # Skills and boost names come from the official local data; the matched card is
    # only used for its id (review lookups are keyed by it).
    player["fcplayerCardId"] = fcplayer_card.get("id")
    player["fcplayerMatchedClass"] = fcplayer_card.get("className")
    return player


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
            slot_number = re.match(r"U(\d+)", str(item["_review_slot"]).upper())
            item["_required_base_slot"] = (
                f"B{slot_number.group(1)}" if slot_number else ("B1" if idx % 2 == 0 else "B2")
            )
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
