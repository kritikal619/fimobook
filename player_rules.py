"""FC Mobile game rules and player-data readers shared by the site.

Position compatibility, enhance/training tables, skill and skill-boost stat
maps, review form constants, and helpers that read positions, work rates and
traits from catalog player dicts. No Flask app, database or request state.
"""
import math
import re

from player_stats_card import _max_level_stat_value


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
        "footPair": "주발/약발",
        "skillMovesDisplay": "개인기",
        "height": "키(cm)",
        "weight": "몸무게(kg)",
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
        "footPair": "주발/약발",
        "skillMovesDisplay": "개인기",
        "height": "키(cm)",
        "weight": "몸무게(kg)",
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

MAX_LEVEL_STAT_OPTIONS = [
    {"code": code, "label": label}
    for code, label in STAT_CODE_LABELS.items()
    if code in set(STAT_LABEL_TO_CODE.values())
]
MAX_LEVEL_STAT_CODES = {item["code"] for item in MAX_LEVEL_STAT_OPTIONS}


def _player_matches_max_level_stats(player, codes, gap):
    if not codes:
        return True
    cap = _max_level_stat_value(player.get("ovr"))
    if cap is None:
        return False
    for code in codes:
        value = player.get(code)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if not math.isfinite(value) or value < cap - gap:
            return False
    return True


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


def _player_matches_position_filter(player, positions, include_sub_position=False):
    selected_positions = {
        str(position or "").upper().strip()
        for position in positions
        if str(position or "").strip()
    }
    if not selected_positions:
        return True

    primary_position = _extract_primary_player_position(player)
    if primary_position in selected_positions:
        return True
    if not include_sub_position:
        return False

    secondary_positions = set(_extract_potential_positions(player))
    return not secondary_positions.isdisjoint(selected_positions)


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
