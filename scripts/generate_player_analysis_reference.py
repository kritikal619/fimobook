#!/usr/bin/env python3
"""Build the peer reference used by the player-detail role analysis.

The browser only receives compact quantiles. Raw player rows stay in
``player_data.json`` and are never shipped as part of the analysis payload.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path


POSITION_GROUPS = {
    "attack": ["ST", "CF"],
    "wing": ["LW", "RW", "LM", "RM", "LF", "RF"],
    "am": ["CAM"],
    "cm": ["CM"],
    "dm": ["CDM"],
    "fb": ["LB", "RB", "LWB", "RWB"],
    "cb": ["CB"],
    "gk": ["GK"],
}

# Percentile cohorts are intentionally asymmetric for fullbacks/wingbacks.
# A wingback is compared with the matching fullback as well, while a fullback
# remains compared only with the exact same position.
REFERENCE_POSITIONS = {
    "LWB": ["LWB", "LB"],
    "RWB": ["RWB", "RB"],
}
WIDE_OVR_RADIUS_POSITIONS = {"LM", "RM", "CF"}


def role(role_id, short, name, description, group, weights, **extra):
    return {
        "id": role_id,
        "short": short,
        "name": name,
        "description": description,
        "group": group,
        "weights": weights,
        **extra,
    }


ROLES = [
    role("line_breaker", "LB9", "라인 브레이커", "가속과 위치 선정으로 수비 뒷공간을 먼저 점유하는 공격수", "attack", {"ACC": 18, "SPD": 16, "POS": 20, "FIN": 18, "REA": 10, "DRI": 8, "BAC": 6, "STA": 4}, requirements=[{"stat": "POS", "min": 42, "penalty": 5, "label": "위치 선정"}, {"stat": "ACC", "min": 40, "penalty": 4, "label": "가속"}], factors=["attack_work", "weak_foot"]),
    role("box_finisher", "BF", "문전 해결사", "박스 안 위치 선정과 결정력으로 공격을 끝내는 득점원", "attack", {"FIN": 28, "POS": 22, "SHO": 12, "REA": 12, "BAC": 8, "AGI": 6, "VOL": 6, "PEN": 3, "HEA": 3}, requirements=[{"stat": "FIN", "min": 45, "penalty": 7, "label": "결정력"}], factors=["weak_foot"]),
    role("link_forward", "LF9", "연계 전방축", "등지고 공을 지키며 패스와 움직임으로 2선을 살리는 공격수", "attack", {"STR": 14, "BAC": 16, "SPA": 16, "VIS": 12, "REA": 10, "DRI": 8, "POS": 8, "FIN": 8, "AGG": 4, "STA": 4}, requirements=[{"stat": "SPA", "min": 38, "penalty": 4, "label": "짧은 패스"}], factors=["weak_foot", "height_link"]),
    role("aerial_hub", "AH", "공중 거점", "높이와 힘으로 롱볼을 받아내고 헤딩으로 위협하는 전방 기준점", "attack", {"HEA": 24, "JMP": 20, "STR": 20, "POS": 10, "FIN": 8, "REA": 7, "AGG": 7, "BAC": 4}, requirements=[{"stat": "HEA", "min": 42, "penalty": 7, "label": "헤딩"}, {"stat": "STR", "min": 40, "penalty": 5, "label": "힘"}], factors=["height_aerial"]),
    role("pressing_forward", "PF", "전방 사냥꾼", "활동량과 공격성으로 빌드업을 압박하고 곧바로 득점을 노리는 공격수", "attack", {"STA": 20, "AGG": 18, "ACC": 14, "SPD": 10, "REA": 10, "POS": 10, "FIN": 10, "STR": 8}, requirements=[{"stat": "STA", "min": 40, "penalty": 5, "label": "체력"}], factors=["attack_work", "defense_work"]),
    role("complete_nine", "C9", "완성형 9번", "마무리·연계·피지컬을 고르게 갖춰 여러 공격 방식을 수행하는 공격수", "attack", {"FIN": 15, "POS": 13, "SHO": 8, "ACC": 8, "SPD": 7, "DRI": 8, "BAC": 8, "SPA": 8, "STR": 8, "HEA": 6, "REA": 6, "STA": 5}, requirements=[{"stat": "FIN", "min": 38, "penalty": 3, "label": "결정력"}], factors=["weak_foot", "skill_moves"]),

    role("touchline_dribbler", "TD", "터치라인 돌파수", "폭발적인 속도와 드리블로 측면 일대일을 깨는 윙어", "wing", {"ACC": 19, "SPD": 17, "DRI": 20, "AGI": 14, "BAC": 12, "BAL": 7, "CRO": 5, "REA": 3, "STA": 3}, requirements=[{"stat": "DRI", "min": 44, "penalty": 6, "label": "드리블"}], factors=["skill_moves"]),
    role("inside_scorer", "IS", "안쪽 득점수", "측면에서 중앙으로 들어와 슈팅과 침투로 직접 마무리하는 윙어", "wing", {"FIN": 20, "POS": 17, "ACC": 14, "SPD": 10, "DRI": 12, "AGI": 8, "CUR": 7, "SHO": 6, "REA": 6}, requirements=[{"stat": "FIN", "min": 40, "penalty": 6, "label": "결정력"}], factors=["weak_foot", "attack_work", "skill_moves"]),
    role("wide_runner", "WR", "뒷공간 윙러너", "지속적인 스프린트와 침투로 측면 뒤 공간을 공략하는 공격수", "wing", {"ACC": 20, "SPD": 20, "POS": 16, "STA": 13, "REA": 9, "DRI": 8, "BAC": 6, "FIN": 5, "CRO": 3}, requirements=[{"stat": "SPD", "min": 43, "penalty": 6, "label": "질주 속도"}], factors=["attack_work"]),
    role("wide_creator", "WC", "측면 설계자", "시야와 패스로 측면에서 찬스를 설계하는 창조형 윙어", "wing", {"VIS": 20, "SPA": 17, "CRO": 15, "CUR": 9, "DRI": 12, "BAC": 10, "AGI": 7, "LPA": 6, "REA": 4}, requirements=[{"stat": "VIS", "min": 42, "penalty": 5, "label": "시야"}], factors=["weak_foot", "skill_moves"]),
    role("cross_supplier", "CS", "크로스 공급자", "속도와 정확한 크로스로 측면에서 반복적으로 공을 공급하는 윙어", "wing", {"CRO": 28, "CUR": 13, "ACC": 13, "SPD": 11, "DRI": 10, "BAC": 8, "VIS": 7, "LPA": 5, "STA": 5}, requirements=[{"stat": "CRO", "min": 45, "penalty": 7, "label": "크로스"}], factors=["attack_work"]),

    role("box_runner_ten", "BR10", "박스 러너 10번", "2선에서 박스로 침투해 결정력과 반응으로 득점에 가담하는 미드필더", "am", {"POS": 22, "FIN": 20, "ACC": 11, "REA": 11, "DRI": 9, "BAC": 8, "SHO": 7, "AGI": 6, "STA": 6}, requirements=[{"stat": "POS", "min": 44, "penalty": 6, "label": "위치 선정"}, {"stat": "FIN", "min": 38, "penalty": 5, "label": "결정력"}], factors=["attack_work", "weak_foot"]),
    role("final_third_architect", "FA", "전방 설계자", "시야와 패스로 공격 템포를 조절하고 마지막 패스를 공급하는 10번", "am", {"VIS": 24, "SPA": 18, "LPA": 12, "DRI": 11, "BAC": 11, "REA": 8, "AGI": 7, "CUR": 5, "POS": 4}, requirements=[{"stat": "VIS", "min": 45, "penalty": 7, "label": "시야"}, {"stat": "SPA", "min": 40, "penalty": 4, "label": "짧은 패스"}], factors=["weak_foot"]),
    role("free_creator", "FC", "자유 창조자", "드리블과 패스를 섞어 공격 3분의 1 지역을 자유롭게 지배하는 창조자", "am", {"DRI": 18, "AGI": 14, "BAC": 14, "VIS": 18, "SPA": 11, "REA": 9, "ACC": 6, "CUR": 5, "BAL": 5}, requirements=[{"stat": "DRI", "min": 43, "penalty": 5, "label": "드리블"}, {"stat": "VIS", "min": 40, "penalty": 4, "label": "시야"}], factors=["skill_moves", "weak_foot"]),
    role("support_shadow", "SS", "지원형 섀도", "공격수 주변에서 연계와 슈팅을 오가며 두 번째 득점원이 되는 2선 공격수", "am", {"FIN": 15, "POS": 16, "SPA": 12, "DRI": 12, "BAC": 10, "REA": 10, "ACC": 8, "SHO": 7, "VIS": 6, "STA": 4}, requirements=[{"stat": "POS", "min": 40, "penalty": 4, "label": "위치 선정"}], factors=["attack_work", "weak_foot"]),

    role("two_way_engine", "2W", "전천후 엔진", "왕성한 활동량으로 수비 회수부터 전진 지원까지 넓게 관여하는 중앙 미드필더", "cm", {"STA": 18, "REA": 10, "SPA": 10, "LPA": 8, "DRI": 8, "BAC": 8, "AWR": 9, "STT": 8, "AGG": 7, "ACC": 6, "STR": 4, "POS": 4}, requirements=[{"stat": "STA", "min": 43, "penalty": 6, "label": "체력"}], factors=["attack_work", "defense_work"]),
    role("progressive_passer", "PP", "전진 배급자", "전진 패스와 시야로 중원에서 공격 방향을 빠르게 바꾸는 미드필더", "cm", {"VIS": 22, "LPA": 19, "SPA": 18, "REA": 10, "BAC": 8, "DRI": 6, "CUR": 5, "AWR": 5, "STA": 4, "POS": 3}, requirements=[{"stat": "VIS", "min": 43, "penalty": 5, "label": "시야"}], factors=["weak_foot"]),
    role("deep_tempo", "DT", "후방 템포메이커", "압박 아래서 공을 지키고 긴 패스로 후방 빌드업의 속도를 조절하는 미드필더", "cm", {"LPA": 22, "SPA": 18, "VIS": 17, "BAC": 12, "REA": 9, "AWR": 7, "DRI": 5, "CUR": 4, "STR": 3, "STA": 3}, requirements=[{"stat": "LPA", "min": 42, "penalty": 5, "label": "긴 패스"}, {"stat": "SPA", "min": 40, "penalty": 4, "label": "짧은 패스"}], factors=["weak_foot"]),
    role("halfspace_runner", "HR", "하프스페이스 러너", "중앙과 측면 사이를 반복적으로 파고들어 패스와 득점을 연결하는 미드필더", "cm", {"STA": 16, "POS": 15, "ACC": 11, "DRI": 10, "SPA": 10, "FIN": 9, "REA": 9, "BAC": 8, "VIS": 7, "AGI": 5}, requirements=[{"stat": "STA", "min": 40, "penalty": 4, "label": "체력"}], factors=["attack_work"]),
    role("central_carrier", "CC", "중앙 운반자", "압박을 드리블과 밸런스로 벗겨내며 직접 공을 전진시키는 중앙 미드필더", "cm", {"DRI": 20, "BAC": 18, "AGI": 14, "BAL": 12, "ACC": 10, "STR": 7, "REA": 7, "SPA": 6, "STA": 6}, requirements=[{"stat": "DRI", "min": 43, "penalty": 6, "label": "드리블"}], factors=["skill_moves"]),

    role("ball_winner", "BW", "볼 회수자", "기동력과 태클로 중원에서 빠르게 소유권을 되찾는 수비형 미드필더", "dm", {"STT": 20, "AWR": 18, "MRK": 13, "AGG": 13, "REA": 10, "STA": 10, "SLT": 6, "STR": 6, "ACC": 4}, requirements=[{"stat": "STT", "min": 43, "penalty": 6, "label": "태클"}, {"stat": "AWR", "min": 40, "penalty": 5, "label": "가로채기"}], factors=["defense_work"]),
    role("backline_shield", "BS", "수비선 보호자", "위치 선정과 힘으로 센터백 앞 공간을 막고 위험을 사전에 제거하는 앵커", "dm", {"AWR": 22, "MRK": 17, "STT": 15, "STR": 12, "REA": 10, "AGG": 8, "HEA": 6, "STA": 5, "SPA": 5}, requirements=[{"stat": "AWR", "min": 45, "penalty": 7, "label": "가로채기"}], factors=["defense_work", "height_defense"]),
    role("deep_distribution", "DD", "후방 배급축", "수비형 위치에서 시야와 패스로 빌드업의 첫 방향을 정하는 미드필더", "dm", {"SPA": 19, "LPA": 19, "VIS": 17, "AWR": 12, "BAC": 9, "REA": 8, "STT": 6, "DRI": 5, "STR": 3, "STA": 2}, requirements=[{"stat": "SPA", "min": 42, "penalty": 5, "label": "짧은 패스"}], factors=["weak_foot", "defense_work"]),
    role("mobile_anchor", "MA", "기동형 앵커", "넓은 수비 범위를 커버하고 압박 뒤 공간을 빠르게 메우는 수비형 미드필더", "dm", {"ACC": 13, "SPD": 10, "STA": 17, "AWR": 17, "STT": 13, "REA": 10, "AGG": 8, "MRK": 7, "BAL": 5}, requirements=[{"stat": "STA", "min": 42, "penalty": 5, "label": "체력"}, {"stat": "AWR", "min": 40, "penalty": 4, "label": "가로채기"}], factors=["defense_work"]),

    role("stay_fullback", "SF", "잔류 풀백", "대인 수비와 위치 선정에 집중해 측면 뒷공간을 안정시키는 풀백", "fb", {"MRK": 18, "STT": 18, "AWR": 16, "SPD": 12, "ACC": 10, "REA": 8, "STA": 7, "SLT": 6, "STR": 5}, requirements=[{"stat": "MRK", "min": 40, "penalty": 5, "label": "마크"}], factors=["defense_work"]),
    role("overlap_wingback", "OW", "오버랩 윙백", "스피드와 체력으로 바깥쪽을 왕복하며 크로스를 공급하는 측면 수비수", "fb", {"SPD": 16, "ACC": 15, "STA": 16, "CRO": 17, "DRI": 8, "BAC": 7, "AWR": 7, "STT": 5, "REA": 5, "SPA": 4}, requirements=[{"stat": "STA", "min": 42, "penalty": 5, "label": "체력"}, {"stat": "CRO", "min": 38, "penalty": 4, "label": "크로스"}], factors=["attack_work"]),
    role("inverted_fullback", "IF", "중앙 합류 풀백", "안쪽으로 들어와 패스 선택지를 늘리고 역습의 출발점을 지키는 풀백", "fb", {"SPA": 16, "LPA": 12, "VIS": 11, "BAC": 11, "AWR": 14, "REA": 9, "STT": 8, "DRI": 7, "STA": 7, "STR": 5}, requirements=[{"stat": "SPA", "min": 39, "penalty": 4, "label": "짧은 패스"}, {"stat": "AWR", "min": 38, "penalty": 4, "label": "가로채기"}], factors=["weak_foot"]),
    role("complete_wingback", "CW", "양방향 윙백", "공수 능력과 활동량을 고르게 활용해 측면 전 구간에 영향을 주는 윙백", "fb", {"STA": 14, "SPD": 10, "ACC": 10, "CRO": 11, "DRI": 7, "SPA": 7, "MRK": 9, "STT": 9, "AWR": 9, "REA": 7, "STR": 4, "BAC": 3}, requirements=[{"stat": "STA", "min": 40, "penalty": 4, "label": "체력"}], factors=["attack_work", "defense_work"]),

    role("box_blocker", "BB", "문전 차단자", "높이와 수비 판단으로 박스 안 슈팅·크로스를 먼저 제거하는 센터백", "cb", {"MRK": 18, "AWR": 18, "HEA": 16, "STR": 14, "JMP": 10, "STT": 9, "REA": 8, "AGG": 7}, requirements=[{"stat": "AWR", "min": 43, "penalty": 6, "label": "가로채기"}, {"stat": "HEA", "min": 40, "penalty": 5, "label": "헤딩"}], factors=["height_defense"]),
    role("buildout_centerback", "BC", "빌드업 센터백", "수비 안정감에 패스와 볼 컨트롤을 더해 후방 전개를 시작하는 센터백", "cb", {"AWR": 15, "MRK": 13, "STT": 12, "SPA": 14, "LPA": 13, "BAC": 9, "VIS": 7, "REA": 7, "STR": 5, "DRI": 5}, requirements=[{"stat": "SPA", "min": 38, "penalty": 4, "label": "짧은 패스"}, {"stat": "AWR", "min": 38, "penalty": 4, "label": "가로채기"}], factors=["weak_foot"]),
    role("duel_lock", "DL", "대인 봉쇄자", "힘·마크·태클로 상대 공격수와의 직접 경합을 지배하는 센터백", "cb", {"MRK": 22, "STT": 20, "STR": 18, "AGG": 12, "REA": 9, "AWR": 8, "HEA": 6, "BAL": 5}, requirements=[{"stat": "MRK", "min": 44, "penalty": 6, "label": "마크"}, {"stat": "STR", "min": 40, "penalty": 5, "label": "힘"}], factors=["height_defense", "defense_work"]),
    role("space_cover", "SC", "뒷공간 커버", "빠른 발과 반응으로 높은 수비선 뒤의 침투를 추적하는 커버형 센터백", "cb", {"ACC": 17, "SPD": 17, "REA": 15, "AWR": 16, "MRK": 12, "STT": 10, "AGI": 7, "STR": 6}, requirements=[{"stat": "SPD", "min": 40, "penalty": 6, "label": "질주 속도"}, {"stat": "AWR", "min": 40, "penalty": 5, "label": "가로채기"}], factors=["defense_work"]),

    role("goal_line_keeper", "GLK", "골라인 수호자", "반사신경과 다이빙으로 골문 가까이에서 슈팅을 막는 선방형 골키퍼", "gk", {"REF": 28, "GKD": 24, "GKP": 18, "HAN": 14, "REA": 8, "AGI": 4, "JMP": 4}, requirements=[{"stat": "REF", "min": 44, "penalty": 7, "label": "반사신경"}], factors=["height_keeper"]),
    role("sweeper_keeper", "SWK", "전진 커버 키퍼", "빠른 판단과 킥으로 수비 뒤 공간을 처리하고 빌드업에 참여하는 골키퍼", "gk", {"GKP": 20, "GKK": 20, "REF": 16, "GKD": 14, "REA": 12, "ACC": 7, "SPD": 6, "HAN": 5}, requirements=[{"stat": "GKP", "min": 40, "penalty": 5, "label": "GK 위치 선정"}, {"stat": "GKK", "min": 38, "penalty": 4, "label": "킥"}], factors=["height_keeper"]),
]


def style(style_id, name, description, groups, weights, factors=None):
    return {
        "id": style_id,
        "name": name,
        "description": description,
        "groups": groups,
        "weights": weights,
        "factors": factors or [],
    }


FIELD_GROUPS = ["attack", "wing", "am", "cm", "dm", "fb", "cb"]
STYLES = [
    style("run_in_behind", "골문 침투", "속도와 위치 선정으로 최종 수비선 뒤를 공략하는 성향", FIELD_GROUPS, {"ACC": 25, "SPD": 20, "POS": 25, "REA": 12, "STA": 8, "FIN": 10}, ["attack_work"]),
    style("finishing_focus", "마무리 집중", "슈팅 기회가 왔을 때 직접 득점으로 연결하는 성향", FIELD_GROUPS, {"FIN": 30, "SHO": 18, "POS": 18, "REA": 12, "LSA": 10, "VOL": 6, "CUR": 6}, ["weak_foot"]),
    style("direct_carry", "직선 돌파", "가속과 드리블로 상대 라인을 직접 넘어서는 성향", FIELD_GROUPS, {"ACC": 20, "SPD": 15, "DRI": 25, "AGI": 16, "BAC": 14, "BAL": 10}, ["skill_moves"]),
    style("combination", "짧은 연계", "볼 컨트롤과 짧은 패스로 주변 동료와 빠르게 연결하는 성향", FIELD_GROUPS, {"SPA": 27, "BAC": 22, "REA": 15, "VIS": 12, "DRI": 9, "AGI": 8, "BAL": 7}, ["weak_foot"]),
    style("chance_creation", "찬스 설계", "시야와 다양한 패스로 결정적인 기회를 만드는 성향", FIELD_GROUPS, {"VIS": 30, "SPA": 21, "LPA": 18, "CRO": 10, "CUR": 8, "BAC": 7, "REA": 6}, ["weak_foot"]),
    style("wide_delivery", "측면 공급", "크로스와 스피드를 활용해 바깥쪽에서 공을 전달하는 성향", FIELD_GROUPS, {"CRO": 32, "CUR": 15, "ACC": 14, "SPD": 12, "LPA": 9, "DRI": 9, "STA": 9}),
    style("defensive_screen", "수비 차단", "마크·가로채기·태클로 상대 전진을 끊는 성향", FIELD_GROUPS, {"AWR": 24, "MRK": 21, "STT": 20, "REA": 12, "SLT": 9, "STR": 8, "AGG": 6}, ["defense_work"]),
    style("active_press", "적극 압박", "체력과 공격성을 바탕으로 넓은 범위를 압박하는 성향", FIELD_GROUPS, {"STA": 27, "AGG": 23, "ACC": 15, "REA": 14, "SPD": 9, "STT": 7, "STR": 5}, ["defense_work"]),
    style("aerial_duel", "공중 경합", "점프·헤딩·힘으로 높은 공의 소유권을 다투는 성향", FIELD_GROUPS, {"HEA": 34, "JMP": 30, "STR": 24, "AGG": 7, "REA": 5}, ["height_aerial"]),
    style("shot_stopping", "순간 선방", "반사신경과 다이빙으로 슈팅에 빠르게 반응하는 골키퍼 성향", ["gk"], {"REF": 38, "GKD": 32, "REA": 15, "AGI": 8, "JMP": 7}),
    style("secure_handling", "안정 캐칭", "핸들링과 위치 선정으로 세컨드 볼을 줄이는 골키퍼 성향", ["gk"], {"HAN": 42, "GKP": 28, "REF": 15, "REA": 10, "STR": 5}),
    style("keeper_distribution", "후방 배급", "킥과 판단으로 골키퍼 위치에서 공격 전개를 시작하는 성향", ["gk"], {"GKK": 48, "GKP": 19, "REA": 13, "LPA": 10, "SPA": 10}),
    style("keeper_sweep", "전진 커버", "위치 선정과 기동력으로 페널티 박스 밖의 공간까지 처리하는 성향", ["gk"], {"GKP": 33, "REA": 22, "ACC": 15, "SPD": 15, "REF": 10, "GKK": 5}),
    style("keeper_aerial", "공중 장악", "높이·점프·힘으로 크로스와 높은 공을 통제하는 골키퍼 성향", ["gk"], {"JMP": 28, "STR": 22, "GKP": 22, "HAN": 18, "REA": 10}, ["height_keeper"]),
]


ALL_STATS = sorted(
    {code for item in ROLES + STYLES for code in item["weights"]}
    | {requirement["stat"] for item in ROLES for requirement in item.get("requirements", [])}
)
QUANTILE_POINTS = list(range(0, 101, 5))
POSITION_TO_GROUP = {
    position: group
    for group, positions in POSITION_GROUPS.items()
    for position in positions
}


def numeric(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def quantile(values, percentile):
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + ((ordered[upper] - ordered[lower]) * fraction)


def compact(value):
    rounded = round(float(value), 2)
    return int(rounded) if rounded.is_integer() else rounded


def stat_score(value, anchors):
    q10, q50, q90 = anchors
    if q50 <= q10:
        q50 = q10 + 1
    if q90 <= q50:
        q90 = q50 + 1
    if value <= q50:
        score = 20 + ((value - q10) / (q50 - q10) * 30)
    else:
        score = 50 + ((value - q50) / (q90 - q50) * 30)
    return max(0.0, min(100.0, score))


def composite_score(stats, definition, anchors):
    weighted = 0.0
    total_weight = 0.0
    for code, weight in definition["weights"].items():
        if code not in stats or code not in anchors:
            continue
        weighted += stat_score(stats[code], anchors[code]) * weight
        total_weight += weight
    if not total_weight:
        return 0.0
    score = weighted / total_weight
    for requirement in definition.get("requirements", []):
        code = requirement["stat"]
        if code not in stats or code not in anchors:
            continue
        current = stat_score(stats[code], anchors[code])
        minimum = requirement["min"]
        if current < minimum:
            score -= ((minimum - current) / minimum) * requirement["penalty"]
    return max(0.0, min(100.0, score))


def adjusted_record(player, target_ovr):
    player_ovr = numeric(player.get("ovr"))
    if player_ovr is None:
        return None
    adjustment = (target_ovr - player_ovr) * 2
    stats = {}
    for code in ALL_STATS:
        value = numeric(player.get(code))
        if value is not None:
            stats[code] = value + adjustment
    return stats


def build_reference(players):
    grouped = defaultdict(list)
    for player in players:
        position = str(player.get("position") or "").upper()
        ovr = numeric(player.get("ovr"))
        if position in POSITION_TO_GROUP and ovr is not None:
            grouped[position].append(player)

    reference = {}
    for position, position_players in grouped.items():
        group = POSITION_TO_GROUP[position]
        comparison_positions = REFERENCE_POSITIONS.get(position, [position])
        comparison_players = [
            player
            for comparison_position in comparison_positions
            for player in grouped.get(comparison_position, [])
        ]
        position_reference = {}
        ovrs = sorted({int(numeric(player.get("ovr"))) for player in position_players})
        group_roles = [item for item in ROLES if item["group"] == group]
        group_styles = [item for item in STYLES if group in item["groups"]]
        radius = 4 if position in WIDE_OVR_RADIUS_POSITIONS else 2

        for target_ovr in ovrs:
            cohort = [
                player for player in comparison_players
                if abs((numeric(player.get("ovr")) or 0) - target_ovr) <= radius
            ]

            adjusted = [adjusted_record(player, target_ovr) for player in cohort]
            adjusted = [record for record in adjusted if record]
            anchors = {}
            for code in ALL_STATS:
                values = [record[code] for record in adjusted if code in record]
                if values:
                    anchors[code] = [
                        compact(quantile(values, 0.10)),
                        compact(quantile(values, 0.50)),
                        compact(quantile(values, 0.90)),
                    ]

            role_quantiles = {}
            for item in group_roles:
                scores = [composite_score(record, item, anchors) for record in adjusted]
                role_quantiles[item["id"]] = [
                    compact(quantile(scores, point / 100)) for point in QUANTILE_POINTS
                ]

            style_quantiles = {}
            for item in group_styles:
                scores = [composite_score(record, item, anchors) for record in adjusted]
                style_quantiles[item["id"]] = [
                    compact(quantile(scores, point / 100)) for point in QUANTILE_POINTS
                ]

            position_reference[str(target_ovr)] = {
                "sample": len(adjusted),
                "radius": radius,
                "positions": comparison_positions,
                "stats": anchors,
                "roles": role_quantiles,
                "styles": style_quantiles,
            }
        reference[position] = position_reference
    return reference


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=root / "player_data.json")
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "static" / "data" / "player-analysis-reference.json",
    )
    args = parser.parse_args()

    with args.input.open("r", encoding="utf-8") as source:
        players = json.load(source)

    payload = {
        "version": 1,
        "generatedAt": date.today().isoformat(),
        "sourceCount": len(players),
        "positionGroups": POSITION_GROUPS,
        "quantilePoints": QUANTILE_POINTS,
        "roles": ROLES,
        "styles": STYLES,
        "reference": build_reference(players),
        "method": {
            "cohort": "동일 주포지션과 기본 OVR ±2 비교. LM·RM·CF는 ±4, LWB는 LWB·LB, RWB는 RWB·RB를 비교하며 LB·RB는 동일 포지션만 비교",
            "normalization": "각 능력치를 동급 표본의 10·50·90 분위수에 맞춰 강건 정규화",
            "enhancement": "진화의 전 능력치 공통 상승분은 비교 전에 제외하고 스킬·훈련 배분 차이는 유지",
            "percentile": "역할 점수를 같은 역할·포지션·OVR 표본의 점수 분포와 비교",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as target:
        json.dump(payload, target, ensure_ascii=False, separators=(",", ":"))
        target.write("\n")
    print(f"wrote {args.output} ({args.output.stat().st_size:,} bytes, {len(players):,} players)")


if __name__ == "__main__":
    main()
