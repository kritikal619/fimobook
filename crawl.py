import requests
import json
import math
from bs4 import BeautifulSoup

# fetch_player_search_list 함수 정의 (strPlayerName 처리 로직 변경)
def fetch_player_search_list(player_names_list: list[str] = None, page_no: int = 1, filters: dict = None) -> dict:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", # User-Agent 업데이트
        "Accept-Language": "ko,en-US;q=0.9,en;q=0.8",
        "Accept": "application/json, text/javascript, */*; q=0.01", # JSON 응답 명시
        "X-Requested-With": "XMLHttpRequest", # AJAX 요청 명시
        "Referer": "https://fcmobile.nexon.com/DataCenterWeb/SquadMaker" # Referer 추가
    })

    # 1) CSRF 토큰 얻기 (페이지를 직접 방문하여 얻음)
    url_get = "https://fcmobile.nexon.com/datacenterweb/squadmaker"
    res_get = session.get(url_get)
    if not res_get.ok:
        raise RuntimeError(f"GET 요청 실패: {res_get.status_code}")

    soup = BeautifulSoup(res_get.text, "html.parser")
    token_input = soup.find("input", {"name": "__RequestVerificationToken"})
    if token_input is None or not token_input.get("value"):
        raise RuntimeError("CSRF 토큰을 찾을 수 없습니다.")
    csrf_token = token_input["value"]

    # 2) POST Body 구성
    # player_names_list가 비어있거나 None이면 strPlayerName을 빈 문자열로 설정
    if not player_names_list: # Handles None, [], or empty string
        player_name_param = ""
    else:
        player_name_param = json.dumps(player_names_list, ensure_ascii=False)

    default_body = {
        "strMethod": "PlayerSearchList",
        "n8Cid": 0,
        "n4PageNo": page_no,
        "strPlayerName": player_name_param, # 변경된 부분
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
    # headers_post는 session.headers.update에 이미 포함
    res_post = session.post(url_post, data=default_body) # headers_post 제거
    if not res_post.ok:
        raise RuntimeError(f"POST 요청 실패: {res_post.status_code}")

    return res_post.json()

# 오버롤 115 이상의 선수 데이터 수집
min_ovr = 115
all_high_ovr_players = []
page_no = 1
total_pages = 1 # 초기값

print(f"--- 오버롤 {min_ovr} 이상의 선수 데이터 수집 시작 ---")

try:
    while page_no <= total_pages:
        print(f"데이터 가져오는 중: 페이지 {page_no}/{total_pages}...")
        
        # filters에 n4OvrMin 설정
        # player_names_list는 None으로 설정하여 특정 이름 없이 전체 범위 검색
        page_data = fetch_player_search_list(
            player_names_list=None, # 빈 문자열("")로 변환될 것임
            page_no=page_no,
            filters={"n4OvrMin": min_ovr}
        )

        if page_data.get("ResultCode") != 1:
            print(f"API 오류 발생 (페이지 {page_no}): {page_data.get('ResultMsg', '알 수 없는 오류')}")
            break

        rd = page_data["ResultData"]
        current_page_players = rd.get("PlayerList", [])
        
        if not current_page_players and page_no == 1:
            print(f"오버롤 {min_ovr} 이상인 선수를 찾을 수 없습니다. (API에서 데이터 반환 안 함 또는 실제 선수 없음)")
            break # 첫 페이지부터 데이터 없으면 중단

        # 첫 페이지에서만 total_pages 계산
        if page_no == 1:
            total_count = rd.get("totalCount", 0)
            page_size = rd.get("pageSize", 10) # 일반적으로 10개씩 가져옴
            if page_size > 0:
                total_pages = math.ceil(total_count / page_size)
            else:
                total_pages = 1
            print(f"총 선수 수: {total_count}, 총 페이지 수: {total_pages}")

        for player in current_page_players:
            # 필요한 정보만 추출
            player_info = {
                "cid": player.get("cid"), # 상세보기를 위해 CID도 저장
                "className": player.get("className"),
                "playerKor": player.get("playerKor"),
                "ovr": player.get("ovr"),
                "position": player.get("position"), # 포지션도 함께 저장 (테이블 표시용)
                "team": player.get("team"), # 팀도 함께 저장 (테이블 표시용)
                "pimage": player.get("pimage", ""), # 선수 이미지 URL 추가
                "bimage": player.get("bimage", ""), # 배경 이미지 URL 추가
                "traits": [] # 특성 정보 저장
            }
            traits_data = player.get("Trait")
            if traits_data:
                for trait in traits_data:
                    player_info["traits"].append(trait.get("name"))
            all_high_ovr_players.append(player_info)
        
        page_no += 1

except Exception as e:
    print(f"데이터 수집 중 예기치 않은 오류 발생: {e}")

finally:
    # 수집된 데이터 JSON 파일로 저장
    output_filename = "player_data.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(all_high_ovr_players, f, indent=2, ensure_ascii=False)
    
    print(f"\n--- 데이터 수집 완료 ---")
    print(f"총 {len(all_high_ovr_players)}명의 선수가 수집되었습니다.")
    print(f"데이터가 '{output_filename}' 파일에 저장되었습니다.")