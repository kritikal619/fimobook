"""Cheaper alternative cards for the player detail page.

Candidates play a compatible position at a nearby OVR and height. Similarity is the
position-weighted gap across detailed stats, using the in-game training
importance tiers for that position, so a striker is judged mostly on
shooting/heading/positioning and a centre-back on marking/heading/aggression.
"""

from player_rules import (
    POSITION_COMPATIBILITY,
    STAT_CODE_LABELS,
    TRAINING_POSITION_STAT_TIERS,
    _extract_primary_player_position,
    _training_position_key,
)

OVR_BELOW = 6
OVR_ABOVE = 2
# A weighted average gap of this many stat points scores 0.
STAT_GAP_FOR_ZERO = 40
HEIGHT_RANGE_CM = 5
# Tall target men: any candidate in this band is a fair heading alternative.
TALL_HEIGHT_BAND = (190, 200)
WEAK_FOOT_PENALTY = 2.0
SKILL_MOVE_PENALTY = 1.5
MIN_SIMILARITY = 70
CHEAPER_RATIO = 0.9
MAX_ALTERNATIVES = 4

_CACHE = {}
_CACHE_LIMIT = 4096


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stat_weights(position):
    tiers = TRAINING_POSITION_STAT_TIERS.get(_training_position_key(position))
    if not tiers:
        return {}
    return {code: weight for weight, codes in tiers.items() for code in codes}


def _weak_foot(player):
    feet = [_number(player.get(key)) for key in ("footL", "footR")]
    feet = [value for value in feet if value is not None]
    return min(feet) if feet else None


def _height_fits(target_height, candidate_height):
    if target_height is None:
        return True
    if candidate_height is None:
        return False
    low, high = TALL_HEIGHT_BAND
    if low <= target_height <= high:
        return low <= candidate_height <= high
    return abs(candidate_height - target_height) <= HEIGHT_RANGE_CM


def _compatible(target_position, candidate):
    candidate_position = _extract_primary_player_position(candidate)
    if (target_position == "GK") != (candidate_position == "GK"):
        return False
    allowed = POSITION_COMPATIBILITY.get(target_position, {target_position})
    return candidate_position in allowed


def _compare(target, candidate, weights):
    gaps = []
    weighted_gap = total_weight = 0.0
    for code, weight in weights.items():
        mine, theirs = _number(target.get(code)), _number(candidate.get(code))
        if mine is None or theirs is None:
            continue
        gaps.append((code, weight, theirs - mine))
        weighted_gap += weight * abs(theirs - mine)
        total_weight += weight
    if not total_weight:
        return None, gaps
    score = 100 * max(0.0, 1 - (weighted_gap / total_weight) / STAT_GAP_FOR_ZERO)

    target_foot, candidate_foot = _weak_foot(target), _weak_foot(candidate)
    if target_foot is not None and candidate_foot is not None:
        score -= abs(candidate_foot - target_foot) * WEAK_FOOT_PENALTY
    target_moves = _number(target.get("skillMovesLevel"))
    candidate_moves = _number(candidate.get("skillMovesLevel"))
    if target_moves is not None and candidate_moves is not None:
        score -= abs(candidate_moves - target_moves) * SKILL_MOVE_PENALTY
    return max(0.0, score), gaps


def _summary(gaps, weights):
    top_weight = max(weights.values())
    core = [delta for _code, weight, delta in gaps if weight == top_weight]
    important = [(code, delta) for code, weight, delta in gaps if weight >= top_weight - 3]
    weakest = min(important, key=lambda item: item[1], default=None)
    strongest = max(important, key=lambda item: item[1], default=None)

    def label(item):
        if not item or round(item[1]) == 0:
            return None
        code, delta = item
        return {"label": STAT_CODE_LABELS.get(code, code), "delta": int(round(delta))}

    return {
        "core_delta": int(round(sum(core) / len(core))) if core else 0,
        "weakness": label(weakest) if weakest and weakest[1] < 0 else None,
        "strength": label(strongest) if strongest and strongest[1] > 0 else None,
    }


def format_compact_price(value):
    value = int(value or 0)
    if value >= 100_000_000:
        unit, divisor = "억", 100_000_000
    elif value >= 10_000:
        unit, divisor = "만", 10_000
    else:
        return f"{value:,}"
    return f"{value / divisor:,.1f}".rstrip("0").rstrip(".") + unit


def find_alternatives(target, players, price_of, limit=MAX_ALTERNATIVES):
    """Return up to ``limit`` alternatives, cheaper ones first.

    ``price_of(player)`` returns the base (0 enhance) market price or 0.
    Each player appears once, as its most similar class.
    """
    target_position = _extract_primary_player_position(target)
    weights = _stat_weights(target_position)
    target_ovr = _number(target.get("ovr"))
    if not weights or target_ovr is None:
        return []

    cache_key = (id(players), len(players), target.get("cid"), target_position)
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached[:limit]

    target_price = price_of(target) or 0
    target_height = _number(target.get("height")) or None
    best_by_player = {}
    for candidate in players:
        if not isinstance(candidate, dict) or candidate.get("cid") == target.get("cid"):
            continue
        if target.get("pid") is not None and candidate.get("pid") == target.get("pid"):
            continue
        candidate_ovr = _number(candidate.get("ovr"))
        if candidate_ovr is None or not (target_ovr - OVR_BELOW <= candidate_ovr <= target_ovr + OVR_ABOVE):
            continue
        if not _compatible(target_position, candidate):
            continue
        if not _height_fits(target_height, _number(candidate.get("height")) or None):
            continue
        price = price_of(candidate) or 0
        if not price:
            continue
        score, gaps = _compare(target, candidate, weights)
        if score is None or score < MIN_SIMILARITY:
            continue
        identity = candidate.get("pid") or (candidate.get("playerKor"), candidate.get("playerEng"))
        previous = best_by_player.get(identity)
        if previous and previous["similarity"] >= score:
            continue
        ratio = price / target_price if target_price else None
        best_by_player[identity] = {
            "player": candidate,
            "similarity": score,
            "price": price,
            "price_label": format_compact_price(price),
            "cheaper_percent": int(round((1 - ratio) * 100)) if ratio is not None and ratio < 1 else 0,
            "is_cheaper": ratio is not None and ratio <= CHEAPER_RATIO,
            **_summary(gaps, weights),
        }

    ranked = sorted(
        best_by_player.values(),
        key=lambda item: (not item["is_cheaper"], -item["similarity"], item["price"]),
    )[:MAX_ALTERNATIVES]
    for item in ranked:
        item["similarity"] = int(round(item["similarity"]))

    if len(_CACHE) >= _CACHE_LIMIT:
        _CACHE.clear()
    _CACHE[cache_key] = ranked
    return ranked[:limit]
