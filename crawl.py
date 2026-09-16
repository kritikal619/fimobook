import requests
import json
import math
from bs4 import BeautifulSoup
import time


# ---------------------------------------------
# [1] 선수 검색 (SquadMakerAjaxInfo)
# ---------------------------------------------
def fetch_player_search_list(player_names_list=None, page_no=1, filters=None) -> dict:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept-Language": "ko,en-US;q=0.9,en;q=0.8",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://fcmobile.nexon.com/DataCenterWeb/SquadMaker"
    })

    # 1️⃣ CSRF 토큰 얻기
    url_get = "https://fcmobile.nexon.com/datacenterweb/squadmaker"
    res_get = session.get(url_get)
    if not res_get.ok:
        raise RuntimeError(f"GET 요청 실패: {res_get.status_code}")

    soup = BeautifulSoup(res_get.text, "html.parser")
    token_input = soup.find("input", {"name": "__RequestVerificationToken"})
    if token_input is None or not token_input.get("value"):
        raise RuntimeError("CSRF 토큰을 찾을 수 없습니다.")
    csrf_token = token_input["value"]

    # 2️⃣ 요청 데이터 구성
    if not player_names_list:
        player_name_param = ""
    else:
        player_name_param = json.dumps(player_names_list, ensure_ascii=False)

    body = {
        "strMethod": "PlayerSearchList",
        "n8Cid": 0,
        "n4PageNo": page_no,
        "strPlayerName": player_name_param,
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
        body.update(filters)

    # 3️⃣ POST 요청
    url_post = "https://fcmobile.nexon.com/datacenterweb/SquadMakerAjaxInfo"
    res_post = session.post(url_post, data=body)
    if not res_post.ok:
        raise RuntimeError(f"POST 요청 실패: {res_post.status_code}")

    return res_post.json()


# ---------------------------------------------
# [2] 실제 거래소 가격 HTML에서 크롤링
# ---------------------------------------------
def fetch_market_price_html(cid: int) -> int | None:
    """
    HTML 파싱으로 0진화 가격을 가져옵니다.
    """
    url = f"https://fcmobile.nexon.com/datacenterweb/markettrade?cid={cid}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://fcmobile.nexon.com/datacenterweb/squadmaker"
    }

    try:
        res = requests.get(url, headers=headers, timeout=7)
        if not res.ok:
            return None

        soup = BeautifulSoup(res.text, "html.parser")

        # 화면에 표시되는 0진가를 담은 span 태그 탐색
        price_tag = soup.select_one(".price .num, .num_price, .price_value")
        if not price_tag:
            return None

        # 숫자만 추출
        digits = ''.join(ch for ch in price_tag.get_text() if ch.isdigit())
        return int(digits) if digits else None

    except Exception:
        return None


# ---------------------------------------------
# [3] 메인 실행
# ---------------------------------------------
min_ovr = 115
all_high_ovr_players = []
page_no = 1
total_pages = 1

print(f"--- 오버롤 {min_ovr} 이상의 선수 데이터 수집 시작 ---")

try:
    while page_no <= total_pages:
        print(f"📥 데이터 가져오는 중: 페이지 {page_no}/{total_pages}...")
        page_data = fetch_player_search_list(
            player_names_list=None,
            page_no=page_no,
            filters={"n4OvrMin": min_ovr}
        )

        if page_data.get("ResultCode") != 1:
            print(f"⚠️ API 오류 (페이지 {page_no}): {page_data.get('ResultMsg', '알 수 없는 오류')}")
            break

        rd = page_data["ResultData"]
        current_page_players = rd.get("PlayerList", [])
        if not current_page_players and page_no == 1:
            print("❌ 오버롤 조건에 맞는 선수를 찾을 수 없습니다.")
            break

        # 첫 페이지일 때 총 페이지 계산
        if page_no == 1:
            total_count = rd.get("totalCount", 0)
            page_size = rd.get("pageSize", 10)
            total_pages = math.ceil(total_count / page_size) if page_size > 0 else 1
            print(f"총 {total_count}명, {total_pages}페이지")

        for player in current_page_players:
            cid = player.get("cid")
            player_info = {
                "cid": cid,
                "className": player.get("className"),
                "playerKor": player.get("playerKor"),
                "ovr": player.get("ovr"),
                "position": player.get("position"),
                "team": player.get("team"),
                "pimage": player.get("pimage", ""),
                "bimage": player.get("bimage", ""),
                "traits": [t.get("name") for t in (player.get("Trait") or [])],
                "n8Price0": None
            }

            # 가격 수집 (HTML 파싱)
            if cid:
                price = fetch_market_price_html(cid)
                if price:
                    player_info["n8Price0"] = price
                    print(f"💰 {player_info['playerKor']} - 0진가 {price:,} MP")
                else:
                    print(f"⚠️ {player_info['playerKor']} - 가격 정보 없음")
                time.sleep(0.6)  # 서버 요청 간 딜레이

            all_high_ovr_players.append(player_info)

        page_no += 1

except Exception as e:
    print(f"❌ 오류 발생: {e}")

finally:
    output_filename = "player_data.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(all_high_ovr_players, f, indent=2, ensure_ascii=False)

    print("\n✅ --- 데이터 수집 완료 ---")
    print(f"총 {len(all_high_ovr_players)}명의 선수 정보 저장됨")
    print(f"파일: {output_filename}")
