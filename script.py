import requests
from bs4 import BeautifulSoup
import json  # JSON 덤프용
import math  # 페이지 계산용


def fetch_player_search_list(player_names_list, page_no=1, filters=None):
    """
    Nexon FC Mobile SquadMakerAjaxInfo API 호출 (수정판).

    주의:
      - strPlayerName은 JSON 배열 문자열(예: '["호나우두"]')를 그대로 넣고,
        requests가 data=로 전달할 때 인코딩하도록 둡니다.
      - __RequestVerificationToken, Referer 헤더 등이 올바르게 전송되어야 합니다.
    """

    # 1) 세션 생성 → SquadMaker 페이지 GET → CSRF 토큰 + 세션 쿠키 가져오기
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept-Language": "ko,en-US;q=0.9,en;q=0.8"
    })

    url_get = "https://fcmobile.nexon.com/datacenterweb/squadmaker"
    res_get = session.get(url_get)
    if not res_get.ok:
        raise RuntimeError(f"GET 요청 실패: {res_get.status_code}")

    # HTML 파싱해서 CSRF 토큰 뽑기
    soup = BeautifulSoup(res_get.text, "html.parser")
    token_input = soup.find("input", {"name": "__RequestVerificationToken"})
    if token_input is None or not token_input.get("value"):
        raise RuntimeError("CSRF 토큰을 찾을 수 없습니다.")
    csrf_token = token_input["value"]

    # 2) POST Body 구성
    json_array_str = json.dumps(player_names_list, ensure_ascii=False)  # 예: '["호나우두"]'
    default_body = {
        "strMethod": "PlayerSearchList",
        "n8Cid": 0,
        "n4PageNo": page_no,
        "strPlayerName": json_array_str,
        "strClass": "",
        "strLeagueId": "",
        "strPositionCode": "",
        "strTeamId": "",
        "strNationality": "",
        "n1Force": 0,
        "n4OvrMin": "",
        "n4OvrMax": "",
        "n8PriceMin": "",
        "n8PriceMax": "",
        "n1WeakFoot": "",
        "n4HeightMin": "",
        "n4HeightMax": "",
        "n4WeightMin": "",
        "n4WeightMax": "",
        "strSkillMove": "",
        "strSkillBoost": "",
        "__RequestVerificationToken": csrf_token
    }

    if filters:
        default_body.update(filters)

    # 3) POST 요청
    url_post = "https://fcmobile.nexon.com/datacenterweb/SquadMakerAjaxInfo"
    headers_post = {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://fcmobile.nexon.com/datacenterweb/squadmaker"
    }
    res_post = session.post(url_post, headers=headers_post, data=default_body)

    if not res_post.ok:
        raise RuntimeError(f"POST 요청 실패: {res_post.status_code}")

    # 응답 JSON 반환
    return res_post.json()


def display_player_list(player_list):
    """PlayerList에서 번호별로 선수 클래스, 이름, OVR, 팀을 출력"""
    print(f"검색된 선수 수: {len(player_list)}\n")
    for idx, p in enumerate(player_list, start=1):
        class_name = p.get("className", "클래스 정보 없음")
        name = p.get("playerKor", "이름 없음")
        ovr = p.get("ovr", "N/A")
        team = p.get("team", "소속 없음")
        print(f"{idx}. {class_name} {name} – OVR {ovr}, 팀 {team}")
    print()


def display_player_details(player):
    """선택된 선수의 세부 정보(모든 스탯, 주발/약발, 스킬 부스트, 가격 등)를 출력"""

    # 영어 키를 한국어로 바꿀 수 있는 매핑 (없으면 키 자체를 표시)
    stat_names = {
        "ACC": "가속",
        "AGG": "공격성",
        "AGI": "민첩성",
        "AWR": "위치 선정",
        "BAC": "볼 컨트롤",
        "BAL": "밸런스",
        "CRO": "크로스",
        "CUR": "감아차기",
        "DRI": "드리블",
        "FIN": "결정력",
        "FRK": "프리킥",
        "GKD": "GK 다이빙",
        "GKK": "GK 킥",
        "GKP": "GK 위치 선정",
        "HAN": "태클",
        "HEA": "헤딩",
        "JMP": "점프",
        "LPA": "롱패스",
        "LSA": "롱슛",
        "MRK": "수비 마킹",
        "PAS": "패스",
        "PEN": "페널티 킥",
        "POS": "포지셔닝",
        "REA": "반응도",
        "REF": "반사 신경",
        "SHO": "슈팅력",
        "SLT": "슬라이딩 태클",
        "SPD": "질주 속도",
        "STA": "체력",
        "STR": "힘",
        "STT": "마크",
        "VIS": "시야",
        "VOL": "볼 컨트롤",
        "WFA": "약발 정확도",
        "LVO": "로빙 발리 정확도",
        "LVOD": "로빙 발리 데미지"
    }

    print("----- 선수 상세 정보 -----")
    # 기본 정보
    print(f"클래스: {player.get('className', 'N/A')}")
    print(f"이름: {player.get('playerKor', 'N/A')}")
    print(f"영문 이름: {player.get('playerEng', 'N/A')}")
    print(f"팀: {player.get('team', 'N/A')}")
    print(f"포지션: {player.get('position', 'N/A')}")
    print(f"OVR: {player.get('ovr', 'N/A')}")
    print(f"키: {player.get('height', 'N/A')}cm, 몸무게: {player.get('weight', 'N/A')}kg")
    print(f"국적: {player.get('nation', 'N/A')}\n")

    # 주발 / 약발 정보
    main_foot = player.get("mainFoot")
    footL = player.get("footL")
    footR = player.get("footR")
    main_foot_name = "왼발" if main_foot == 1 else ("오른발" if main_foot == 2 else "알 수 없음")
    print(f"주발: {main_foot_name}")
    print(f"왼발 능력치 등급: {footL}")
    print(f"오른발 능력치 등급: {footR}\n")

    # 스킬 부스트 정보
    skill_boost_name = player.get("skillBoostName", "N/A")
    skill_boost_level = player.get("skillBoostLevel", "N/A")
    print(f"스킬 부스트: {skill_boost_name} (레벨: {skill_boost_level})\n")

    # 모든 능력치 출력
    print("----- 모든 능력치 -----")
    for key, value in player.items():
        # 키가 모두 대문자이고, 정수형 값인 경우 능력치로 판단
        if key.isupper() and isinstance(value, int):
            label = stat_names.get(key, key)
            print(f"{label}: {value}")
    print()

    # 가격 정보 (진화 등급: 가격) - 콤마 추가
    print("----- 가격 (진화 등급: 가격) -----")
    for i in range(0, 11):  # n8Price0부터 n8Price10까지
        price_key = f"n8Price{i}"
        if price_key in player:
            print(f"{i}진화: {player[price_key]:,}원")
    print()

    # Trait(특성) 출력
    traits = player.get("Trait", [])
    if traits:
        print("특성:")
        for t in traits:
            print(f"- {t.get('name', '')}")
        print()


if __name__ == "__main__":
    try:
        # 1) 사용자에게 검색할 선수 이름 입력 받기
        names_input = input("검색할 선수 이름을 쉼표로 구분하여 입력하세요 (예: 호나우두, 메시): ")
        player_names = [name.strip() for name in names_input.split(",") if name.strip()]

        # 2) 첫 페이지 요청 → totalCount, pageSize로 전체 페이지 계산
        first_page_data = fetch_player_search_list(player_names, page_no=1)
        if first_page_data.get("ResultCode") != 1:
            print("검색 실패:", first_page_data.get("ResultMsg"))
            exit(1)

        rd = first_page_data["ResultData"]
        total_count = rd.get("totalCount", 0)
        page_size = rd.get("pageSize", 10)
        total_pages = math.ceil(total_count / page_size)

        # 3) 첫 페이지 목록 취득
        all_players = rd.get("PlayerList", []).copy()

        # 4) 2페이지 이상이 있다면 반복해서 가져오기
        for page in range(2, total_pages + 1):
            page_data = fetch_player_search_list(player_names, page_no=page)
            if page_data.get("ResultCode") != 1:
                print(f"{page}페이지 검색 실패:", page_data.get("ResultMsg"))
                continue
            page_players = page_data["ResultData"].get("PlayerList", [])
            all_players.extend(page_players)

        # 5) PlayerList 출력
        if not all_players:
            print("검색된 선수가 없습니다.")
            exit(0)

        display_player_list(all_players)

        # 6) 사용자 선택
        while True:
            try:
                choice = int(input(f"상세 정보를 볼 선수 번호를 입력하세요 (1~{len(all_players)}): "))
                if 1 <= choice <= len(all_players):
                    selected = all_players[choice - 1]
                    break
                else:
                    print(f"1부터 {len(all_players)} 사이의 숫자를 입력해주세요.")
            except ValueError:
                print("숫자를 정확히 입력해주세요.")

        # 7) 선택된 선수의 세부 정보 출력
        print()
        display_player_details(selected)

    except Exception as e:
        print("에러 발생:", e)
