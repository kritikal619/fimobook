"""Pure query parsing, validation and ordering for player search.

No Flask app, catalog, database or network initialization is needed here.
Detail-search ranges are rejected when reversed; the quick-search route keeps
its existing range-swapping behavior in app.py.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class DetailSearchQuery:
    filters: dict
    sort: str
    error: str | None
    skills: set[str]
    boosts: set[str]
    skill_moves: set[str]
    traits: set[str]
    playstyles: set[str]
    player_classes: set[str]
    skill_levels: set[int]


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


def _filter_arg_values(args, name, uppercase=False):
    return _clean_filter_values(args.getlist(name), uppercase=uppercase)


def _filter_int_arg(args, name, default=None, minimum=None):
    raw_value = str(args.get(name, "") or "").strip().replace(",", "")
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default
    if minimum is not None:
        value = max(minimum, value)
    return value


def _normalize_filter_text(value):
    return re.sub(r"\s+", "", str(value or "").strip()).lower()


def _normalize_name_for_match(value):
    return re.sub(r"\s+", "", (value or "")).lower()


def price_enhance_arg(args, *, max_enhance_level):
    level = _filter_int_arg(args, "price_enhance", default=0, minimum=0)
    return level if level is not None and level <= max_enhance_level else 0


def parse_detail_search_query(
    args, *, skill_or_boost_options, work_rate_options, raised_stat_options,
    max_level_stat_codes, stat_labels, default_min_ovr, default_max_ovr,
    max_enhance_level,
):
    """Parse explicit request arguments without accessing a request context."""
    name_query = args.get("name", "").strip()
    normalized_skill_option_names = {
        _normalize_filter_text(option["name"])
        for option in skill_or_boost_options
        if option["kind"] == "skill"
    }
    normalized_boost_option_names = {
        _normalize_filter_text(option["name"])
        for option in skill_or_boost_options
        if option["kind"] == "boost"
    }
    selected_skill_names = []
    selected_boost_names = []
    for value in _filter_arg_values(args, "skill_or_boost"):
        normalized = _normalize_filter_text(value)
        target = (
            selected_boost_names
            if normalized in normalized_boost_option_names
            and normalized not in normalized_skill_option_names
            else selected_skill_names
        )
        if value not in target:
            target.append(value)
    for value in _filter_arg_values(args, "skill_boost"):
        if value not in selected_boost_names:
            selected_boost_names.append(value)
    skill_or_boosts = selected_skill_names + [
        value for value in selected_boost_names if value not in selected_skill_names
    ]
    positions = _filter_arg_values(args, "position", uppercase=True)
    include_sub_position = str(args.get("include_sub_position", "")).strip().lower() in {"1", "true", "yes", "on"}
    skill_moves = _filter_arg_values(args, "skill_move")
    skill_levels = _clean_filter_values(args.getlist("skill_level"))
    raised_stats = _clean_filter_values(args.getlist("raised_stat"), uppercase=True)
    selected_work_rates = [
        value
        for value in _clean_filter_values(args.getlist("work_rate"))
        if value in work_rate_options
    ]
    traits = _filter_arg_values(args, "trait")
    playstyles = _filter_arg_values(args, "playstyle")
    empty_playstyle_slot = str(args.get("empty_playstyle_slot", "")).strip().lower() in {"1", "true", "yes", "on"}
    max_stats = _clean_filter_values(args.getlist("max_stat"), uppercase=True)
    selected_max_stats = [code for code in max_stats if code in max_level_stat_codes]
    max_stat_gap_raw = args.get("max_stat_gap", "0").strip()
    max_stat_gap = int(max_stat_gap_raw) if max_stat_gap_raw.isdigit() and len(max_stat_gap_raw) <= 2 else -1
    player_classes = _filter_arg_values(args, "player_class")
    height_group = args.get("height_group", "").strip()
    min_height_str = args.get("min_height", "").strip()
    max_height_str = args.get("max_height", "").strip()
    price_enhance = price_enhance_arg(args, max_enhance_level=max_enhance_level)
    min_price_str = args.get("min_price", "").strip().replace(",", "")
    max_price_str = args.get("max_price", "").strip().replace(",", "")
    weak_foot_min_str = args.get("weak_foot_min", "").strip()
    selected_league = args.get("league", "").strip()
    selected_team = args.get("team", "").strip()
    all_career = str(args.get("all_career", "")).strip().lower() in {"1", "true", "yes", "on"}
    min_ovr_str = args.get("min_ovr", "").strip()
    max_ovr_str = args.get("max_ovr", "").strip()
    sort = args.get("sort", "ovr_desc").strip() or "ovr_desc"

    min_ovr = int(min_ovr_str) if min_ovr_str.isdigit() else default_min_ovr
    max_ovr = int(max_ovr_str) if max_ovr_str.isdigit() else default_max_ovr
    min_height = int(min_height_str) if min_height_str.isdigit() else None
    max_height = int(max_height_str) if max_height_str.isdigit() else None
    min_price = int(min_price_str) if min_price_str.isdigit() else None
    max_price = int(max_price_str) if max_price_str.isdigit() else None
    weak_foot_min = int(weak_foot_min_str) if weak_foot_min_str in {"1", "2", "3", "4", "5"} else 0
    normalized_skill_or_boosts = {_normalize_filter_text(value) for value in skill_or_boosts}
    normalized_selected_skills = {
        _normalize_filter_text(value) for value in selected_skill_names
    }
    normalized_selected_boosts = {
        _normalize_filter_text(value) for value in selected_boost_names
    }
    normalized_skill_moves = {_normalize_filter_text(value) for value in skill_moves}
    normalized_traits = {_normalize_filter_text(value) for value in traits}
    normalized_playstyles = {_normalize_filter_text(value) for value in playstyles}
    normalized_player_classes = {_normalize_filter_text(value) for value in player_classes}
    selected_skill_levels = {int(value) for value in skill_levels if str(value).isdigit()}
    valid_stat_codes = {item["code"] for item in raised_stat_options}
    selected_raised_stat_codes = [code for code in raised_stats if code in valid_stat_codes][:5]
    filters = {
        "name": name_query,
        "skill_or_boosts": skill_or_boosts,
        "positions": positions,
        "include_sub_position": include_sub_position,
        "skill_moves": skill_moves,
        "skill_levels": sorted(selected_skill_levels),
        "raised_stats": selected_raised_stat_codes,
        "raised_stat_labels": [stat_labels.get(code, code) for code in selected_raised_stat_codes],
        "work_rates": selected_work_rates,
        "work_rate_labels": [work_rate_options[value]["label"] for value in selected_work_rates],
        "traits": traits,
        "playstyles": playstyles,
        "empty_playstyle_slot": empty_playstyle_slot,
        "max_stats": selected_max_stats,
        "max_stat_labels": [stat_labels[code] for code in selected_max_stats],
        "max_stat_gap": max_stat_gap,
        "player_classes": player_classes,
        "height_group": height_group,
        "min_height": min_height,
        "max_height": max_height,
        "min_price": min_price,
        "max_price": max_price,
        "price_enhance": price_enhance,
        "weak_foot_min": weak_foot_min,
        "league": selected_league,
        "team": selected_team,
        "all_career": all_career,
        "min_ovr": min_ovr,
        "max_ovr": max_ovr,
    }

    error = None
    if max_stats and (len(selected_max_stats) != len(max_stats) or not 0 <= max_stat_gap <= 30):
        error = '만렙 기준 스탯과 허용 차이(0~30)를 확인해 주세요.'
    elif min_ovr > max_ovr:
        error = '최소 OVR은 최대 OVR보다 클 수 없습니다.'
    elif min_height is not None and max_height is not None and min_height > max_height:
        error = '최소 키는 최대 키보다 클 수 없습니다.'
    elif min_price is not None and max_price is not None and min_price > max_price:
        error = '최소 가격은 최대 가격보다 클 수 없습니다.'
    elif len(raised_stats) > 5:
        error = '상승 스탯은 최대 5개까지만 선택할 수 있습니다.'
    elif len(selected_skill_names) > 2:
        error = '스킬은 최대 2개까지 선택할 수 있습니다.'
    elif len(selected_boost_names) > 1:
        error = '스킬부스트는 한 번에 하나만 선택할 수 있습니다.'
    elif selected_raised_stat_codes and normalized_skill_or_boosts:
        error = '상승 스탯 필터는 스킬/스킬부스트 필터와 함께 사용할 수 없습니다.'
    return DetailSearchQuery(
        filters=filters, sort=sort, error=error,
        skills=normalized_selected_skills, boosts=normalized_selected_boosts,
        skill_moves=normalized_skill_moves, traits=normalized_traits,
        playstyles=normalized_playstyles, player_classes=normalized_player_classes,
        skill_levels=selected_skill_levels,
    )


def sort_detail_search_players(players, sort):
    """Sort in place, keeping unavailable prices last and stable tie ordering."""
    if sort == "ovr_asc":
        players.sort(key=lambda p: (p.get("ovr") or 0, p.get("playerKor") or ""))
    elif sort == "name_asc":
        players.sort(key=lambda p: (p.get("playerKor") or "", -(p.get("ovr") or 0)))
    elif sort == "price_desc":
        players.sort(
            key=lambda p: (
                p.get("price") is None,
                -(p.get("price") or 0),
                -(p.get("ovr") or 0),
                p.get("playerKor") or "",
            )
        )
    elif sort == "price_asc":
        players.sort(
            key=lambda p: (
                p.get("price") is None,
                p.get("price") or 0,
                -(p.get("ovr") or 0),
                p.get("playerKor") or "",
            )
        )
    else:
        players.sort(key=lambda p: (-(p.get("ovr") or 0), p.get("playerKor") or ""))

