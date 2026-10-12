"""Club and career team matching for player search and the squad maker."""

import json
import os
import re
import threading

import requests

from player_search import _normalize_filter_text, _normalize_name_for_match

FCO_CAREER_DATA_FILE = None
FCO_CAREER_DATA_URL = os.getenv(
    "FCO_CAREER_DATA_URL",
    "https://raw.githubusercontent.com/Indvel/indvel.github.io/master/fcmsquad/resources/fco_allp.js",
)
_FCO_CAREER_ROWS = None
FCO_CLUB_CAREER_DATA_FILE = None
_FCO_CLUB_CAREER_DATA = None

_get_players = None


def configure(root_path, instance_path, get_players):
    """Wire in the application paths and the live player catalog accessor."""
    global FCO_CAREER_DATA_FILE, FCO_CLUB_CAREER_DATA_FILE, _get_players
    FCO_CAREER_DATA_FILE = os.getenv(
        "FCO_CAREER_DATA_FILE",
        os.path.join(instance_path, "fco_allp.js"),
    )
    FCO_CLUB_CAREER_DATA_FILE = os.getenv(
        "FCO_CLUB_CAREER_DATA_FILE",
        os.path.join(root_path, "static", "data", "player_club_careers.json"),
    )
    _get_players = get_players


def _normalize_team_for_match(value):
    normalized = _normalize_filter_text(value)
    normalized = re.sub(r"\((?:임대|loan)\)", "", normalized, flags=re.IGNORECASE)
    normalized = normalized.replace("아스날", "아스널")
    normalized = normalized.replace("롬바르디아fc", "인테르")
    normalized = normalized.replace("라티움", "ss라치오")
    normalized = normalized.replace("나폴리fc", "ssc나폴리")
    normalized = re.sub(r"(?:fc|cf|sc|afc|ac)$", "", normalized, flags=re.IGNORECASE)
    return normalized


# 2026/27 promotion and relegation changes for leagues represented in the
# career-search data.  Player cards retain the league from the season in which
# they were issued, so the team name is the stable key for presenting clubs in
# their current competition.
CURRENT_SEASON_CLUB_LEAGUES = {
    # England
    "코벤트리 시티": "잉글랜드 프리미어리그",
    "입스위치 타운": "잉글랜드 프리미어리그",
    "헐 시티": "잉글랜드 프리미어리그",
    "울버햄프턴 원더러스": "잉글랜드 EFL 챔피언십",
    "번리": "잉글랜드 EFL 챔피언십",
    "웨스트 햄 유나이티드": "잉글랜드 EFL 챔피언십",
    "노리치 시티": "잉글랜드 EFL 챔피언십",
    "사우샘프턴": "잉글랜드 EFL 챔피언십",
    "왓퍼드": "잉글랜드 EFL 챔피언십",
    "레스터 시티": "잉글랜드 EFL 리그 원",
    "루턴 타운": "잉글랜드 EFL 리그 원",
    # Spain
    "RC 데포르티보": "스페인 라리가 EA스포츠",
    "말라가 CF": "스페인 라리가 EA스포츠",
    "라싱 산탄데르": "스페인 라리가 EA스포츠",
    "레알 오비에도": "스페인 라리가 하이퍼모션",
    "RCD 마요르카": "스페인 라리가 하이퍼모션",
    "지로나 FC": "스페인 라리가 하이퍼모션",
    "CD 레가네스": "스페인 라리가 하이퍼모션",
    "UD 라스 팔마스": "스페인 라리가 하이퍼모션",
    "UD 알메리아": "스페인 라리가 하이퍼모션",
    "그라나다 CF": "스페인 라리가 하이퍼모션",
    "레알 바야돌리드 CF": "스페인 라리가 하이퍼모션",
    "카디스 CF": "스페인 라리가 하이퍼모션",
    "SD 우에스카": "스페인 프리메라 페데라시온",
    # Germany
    "FC 샬케 04": "독일 분데스리가",
    "SV 엘버스베르크": "독일 분데스리가",
    "SC 파더보른 07": "독일 분데스리가",
    "FC 장크트파울리": "독일 분데스리가 2",
    "1. FC 하이덴하임 1846": "독일 분데스리가 2",
    "VfL 볼프스부르크": "독일 분데스리가 2",
    "VfL 보훔 1848": "독일 분데스리가 2",
    "헤르타 BSC": "독일 분데스리가 2",
    "홀슈타인 킬": "독일 분데스리가 2",
    # Italy
    "프로시노네": "이탈리아 세리에 A",
    "몬차": "이탈리아 세리에 A",
    "베네치아": "이탈리아 세리에 A",
    "크레모네세": "이탈리아 세리에 BKT",
    "엘라스 베로나": "이탈리아 세리에 BKT",
    "피사": "이탈리아 세리에 BKT",
    "삼프도리아": "이탈리아 세리에 BKT",
    "엠폴리": "이탈리아 세리에 BKT",
    "살레르니타나": "이탈리아 세리에 C",
    "스페치아": "이탈리아 세리에 C",
    "코모 1907": "이탈리아 세리에 A",
    # France
    "ESTAC 트루아": "프랑스 리그 1 맥도날드",
    "르망 FC": "프랑스 리그 1 맥도날드",
    "FC 메스": "프랑스 리그 2 BKT",
    "FC 낭트": "프랑스 리그 2 BKT",
    "AS 생-테티엔": "프랑스 리그 2 BKT",
    "몽펠리에 HSC": "프랑스 리그 2 BKT",
    "스타드 드 랭스": "프랑스 리그 2 BKT",
    "FC 지롱댕 드 보르도": "프랑스 나시오날",
    # Netherlands
    "ADO 덴하흐": "네덜란드 에레디비지",
    "SC 캄뷔르": "네덜란드 에레디비지",
    "빌럼 II": "네덜란드 에레디비지",
    "헤라클레스 알멜로": "네덜란드 에이르스터 디비시",
    "알메러 시티 FC": "네덜란드 에이르스터 디비시",
    "비테서": "네덜란드 에이르스터 디비시",
    # Greece
    "이라클리스": "그리스 리그",
    "칼라마타 FC": "그리스 리그",
    "AEL": "그리스 수페르리가 2",
    "판세라이코스": "그리스 수페르리가 2",
    # Norway (2026)
    "릴레스트룀 SK": "노르웨이 엘리테세리엔",
    "IK 스타르트": "노르웨이 엘리테세리엔",
    "올레순 FK": "노르웨이 엘리테세리엔",
    "스트룀스고드세": "노르웨이 OBOS-리가엔",
    # Korea (2026)
    "인천 유나이티드 FC": "대한민국 K리그 1",
    "TeamName_110765_Incheon-United-FC_Auth-FullChar": "대한민국 K리그 1",
    "부천 FC 1995": "대한민국 K리그 1",
    "FC 안양": "대한민국 K리그 1",
    "대구 FC": "대한민국 K리그 2",
    "수원 FC": "대한민국 K리그 2",
    "성남 FC": "대한민국 K리그 2",
    "수원 삼성 블루윙즈": "대한민국 K리그 2",
    # Denmark
    "륑뷔 BK": "덴마크 3F 수페르리가",
    "AC 호르센스": "덴마크 3F 수페르리가",
    "FC 프레데리시아": "덴마크 1부 리그",
    # Romania
    "코르비눌 후네도아라": "루마니아 수페르리가",
    "셉시 OSK": "루마니아 수페르리가",
    "FC 볼룬타리": "루마니아 수페르리가",
    # Portugal
    "CS 마리티무": "리가 포르투갈",
    "아카데미쿠 드 비제우": "리가 포르투갈",
    "AVS 풋볼 SAD": "리가 포르투갈 2",
    "FC 파수스 드 페헤이라": "리가 포르투갈 2",
    # Belgium
    "SK 베베런": "벨기에 프로 리그",
    "KV 코르트레이크": "벨기에 프로 리그",
    "롬멜 SK": "벨기에 프로 리그",
    "FCV 덴더 EH": "벨기에 챌린저 프로 리그",
    # Saudi Arabia
    "아브하 클럽": "사우디 프로페셔널 리그",
    "알 파이살리": "사우디 프로페셔널 리그",
    "알 디리야": "사우디 프로페셔널 리그",
    "다마크": "사우디 퍼스트 디비전 리그",
    "알 오로바흐": "사우디 퍼스트 디비전 리그",
    "알 웨흐다": "사우디 퍼스트 디비전 리그",
    # Sweden (2026)
    "칼마르 FF": "스웨덴 알스벤스칸",
    "베스테로스 SK": "스웨덴 알스벤스칸",
    "외리뤼테 IS": "스웨덴 알스벤스칸",
    # Switzerland
    "FC 파두츠": "스위스 슈퍼리그",
    # Scotland
    "세인트 존스톤": "스코티시 프리미어십",
    "리빙스턴": "스코티시 챔피언십",
    # Republic of Ireland (2026)
    "던도크 FC": "아일랜드 프리미어 디비전",
    "TeamName_837_Dundalk-FC_Auth-FullChar": "아일랜드 프리미어 디비전",
    "코크 시티": "아일랜드 퍼스트 디비전",
    # Austria
    "SC 아우스트리아 루스테나우": "오스트리아 분데스리가",
    "FC 블라우바이스 린츠": "오스트리아 2. 리가",
    # Ukraine
    "FC 부코비나 체르니우치": "우크라이나 리그",
    "초르노모레츠 오데사": "우크라이나 리그",
    "리비 베레흐 키이우": "우크라이나 리그",
    # China (2026)
    "랴오닝 톄런": "중국 슈퍼 리그",
    "충칭 퉁량룽": "중국 슈퍼 리그",
    "광저우 풋볼 클럽": "중국 하위 리그",
    # Czech Republic and Croatia
    "FC 즈브로요프카 브르노": "체코 체스카 리그",
    "SK 아르티스 브르노": "체코 체스카 리그",
    "FK 두클라 프라하": "체코 2부 리그",
    "NK 루데스": "크로아티아 리그",
    "HNK 부코바르 1991": "크로아티아 2부 리그",
    # Türkiye
    "에르주룸스포르 FK": "튀르키예 트렌디욜 쉬페르리그",
    "아메드 SK": "튀르키예 트렌디욜 쉬페르리그",
    "초룸 FK": "튀르키예 트렌디욜 쉬페르리그",
    "안탈리아스포르": "튀르키예 TFF 1. 리그",
    "카이세리스포르 풋볼 A.Ş": "튀르키예 TFF 1. 리그",
    "파티흐 카라귐뤼크 SK": "튀르키예 TFF 1. 리그",
    "아다나 데미르스포르": "튀르키예 TFF 1. 리그",
    # Poland
    "비스와 크라쿠프": "폴란드 엑스트라클라사",
    "실롱스크 브로츠와프": "폴란드 엑스트라클라사",
    "비에치스타 크라쿠프": "폴란드 엑스트라클라사",
    # Finland (2026)
    "FC 라흐티": "핀란드 리그",
    "TPS": "핀란드 리그",
    # Argentina (2026)
    "힘나시아 이 에스그리마 데 멘도사": "아르헨티나 리가 프로페시오날 데 풋볼",
    "에스투디안테스 데 리오 콰르토": "아르헨티나 리가 프로페시오날 데 풋볼",
    "고도이 크루스": "아르헨티나 프리메라 나시오날",
    "산 마르틴 데 산후안": "아르헨티나 프리메라 나시오날",
    # India
    "처칠 브라더스 FC": "인도 슈퍼리그",
    "모하메단 SC": "인도 I리그",
    "잠셰드푸르 FC": "인도 I리그",
    # Hungary
    "버셔시 SC": "헝가리 리그",
    "부다페스트 혼베드": "헝가리 리그",
    # UAE
    "두바이 유나이티드": "아랍에미리트 리그",
    "디바 FC": "아랍에미리트 1부 리그",
    # Australia has no sporting promotion/relegation, but Western United's
    # licence was terminated for 2026/27 and it must not remain in A-League.
    "웨스턴 유나이티드 FC": "오스트레일리아 하위 리그",
}
_CURRENT_SEASON_CLUB_LEAGUES_NORMALIZED = {
    _normalize_team_for_match(team): league
    for team, league in CURRENT_SEASON_CLUB_LEAGUES.items()
}
_CURRENT_SEASON_TOP_FLIGHT_LEAGUES = {
    "잉글랜드 프리미어리그",
    "스페인 라리가 EA스포츠",
    "독일 분데스리가",
    "이탈리아 세리에 A",
    "프랑스 리그 1 맥도날드",
    "그리스 리그",
    "네덜란드 에레디비지",
    "노르웨이 엘리테세리엔",
    "대한민국 K리그 1",
    "덴마크 3F 수페르리가",
    "루마니아 수페르리가",
    "리가 포르투갈",
    "벨기에 프로 리그",
    "사우디 프로페셔널 리그",
    "스웨덴 알스벤스칸",
    "스위스 슈퍼리그",
    "스코티시 프리미어십",
    "아일랜드 프리미어 디비전",
    "오스트리아 분데스리가",
    "우크라이나 리그",
    "중국 슈퍼 리그",
    "체코 체스카 리그",
    "크로아티아 리그",
    "튀르키예 트렌디욜 쉬페르리그",
    "폴란드 엑스트라클라사",
    "핀란드 리그",
    "아르헨티나 리가 프로페시오날 데 풋볼",
    "인도 슈퍼리그",
    "헝가리 리그",
    "아랍에미리트 리그",
}


def _current_season_team_pair(pair):
    if not pair:
        return pair
    current_league = _CURRENT_SEASON_CLUB_LEAGUES_NORMALIZED.get(
        _normalize_team_for_match(pair.get("team"))
    )
    if not current_league:
        return pair
    return {"league": current_league, "team": pair.get("team", "")}


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
    for player in _get_players():
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

    for player in _get_players():
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
    for player in _get_players():
        pair = _current_season_team_pair(_player_team_pair(player))
        if not pair:
            continue
        key = _player_identity_key(player)
        score = _current_team_score(player)
        if key not in best_rows or score > best_rows[key][0]:
            best_rows[key] = (score, pair)
    return {key: pair for key, (_, pair) in best_rows.items()}


def _build_league_team_map(pairs, include_current_top_flight=False):
    league_teams = {}
    for pair in pairs:
        pair = _current_season_team_pair(pair)
        if not pair or not pair.get("league") or not pair.get("team"):
            continue
        league_teams.setdefault(pair["league"], set()).add(pair["team"])
    if include_current_top_flight:
        for team, league in CURRENT_SEASON_CLUB_LEAGUES.items():
            if league in _CURRENT_SEASON_TOP_FLIGHT_LEAGUES:
                league_teams.setdefault(league, set()).add(team)
    return {
        league: sorted(teams)
        for league, teams in sorted(league_teams.items(), key=lambda item: item[0])
    }


_TEAM_FILTER_CONTEXT_CACHE = {}
_TEAM_FILTER_CONTEXT_LOCK = threading.RLock()


def _get_team_filter_context(include_external=False):
    players = _get_players()
    signature = (id(players), len(players))
    with _TEAM_FILTER_CONTEXT_LOCK:
        if _TEAM_FILTER_CONTEXT_CACHE.get("signature") != signature:
            career_index = _build_player_career_index()
            current_team_index = _build_player_current_team_index()
            _TEAM_FILTER_CONTEXT_CACHE.clear()
            _TEAM_FILTER_CONTEXT_CACHE.update({
                "signature": signature,
                "career_index": career_index,
                "current_team_index": current_team_index,
                "current_league_teams": _build_league_team_map(
                    current_team_index.values(), include_current_top_flight=True
                ),
                "all_league_teams": _build_league_team_map(
                    (pair for pairs in career_index.values() for pair in pairs),
                    include_current_top_flight=True,
                ),
                "extended_career_index": None,
                "match_cache": {},
            })

        if include_external and _TEAM_FILTER_CONTEXT_CACHE["extended_career_index"] is None:
            career_copy = {
                key: [dict(pair) for pair in pairs]
                for key, pairs in _TEAM_FILTER_CONTEXT_CACHE["career_index"].items()
            }
            _TEAM_FILTER_CONTEXT_CACHE["extended_career_index"] = (
                _extend_career_index_with_external_data(career_copy)
            )

        return _TEAM_FILTER_CONTEXT_CACHE


def _get_team_filter_identity_keys(
    team_filter_context,
    selected_league="",
    selected_team="",
    all_career=False,
):
    if not selected_league and not selected_team:
        return None
    cache_key = (
        bool(all_career),
        _normalize_filter_text(selected_league),
        _normalize_team_for_match(selected_team),
    )
    with _TEAM_FILTER_CONTEXT_LOCK:
        cached = team_filter_context["match_cache"].get(cache_key)
        if cached is not None:
            return cached

        if all_career:
            career_index = team_filter_context["extended_career_index"] or {}
            matches = frozenset(
                identity_key
                for identity_key, pairs in career_index.items()
                if any(
                    _team_pair_matches(pair, selected_league, selected_team)
                    for pair in pairs
                )
            )
        else:
            matches = frozenset(
                identity_key
                for identity_key, pair in team_filter_context["current_team_index"].items()
                if _team_pair_matches(pair, selected_league, selected_team)
            )

        team_filter_context["match_cache"][cache_key] = matches
        return matches


def _team_pair_matches(pair, selected_league="", selected_team=""):
    if not pair:
        return False
    pair = _current_season_team_pair(pair)
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
