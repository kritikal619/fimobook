import math
import json
import requests
from flask import Flask, request, render_template, redirect, url_for
from bs4 import BeautifulSoup

app = Flask(__name__)

def fetch_player_search_list(player_names_list: list[str], page_no: int = 1, filters: dict = None) -> dict:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept-Language": "ko,en-US;q=0.9,en;q=0.8"
    })

    # 1) CSRF 토큰 얻기
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
    json_array_str = json.dumps(player_names_list, ensure_ascii=False)
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

    return res_post.json()


@app.route("/", methods=["GET", "POST"])
def search():
    if request.method == "POST":
        names_input = request.form.get("names", "").strip()
        if not names_input:
            return redirect(url_for("search"))

        player_names = [n.strip() for n in names_input.split(",") if n.strip()]
        # 첫 페이지 조회
        first_page_data = fetch_player_search_list(player_names, page_no=1)
        if first_page_data.get("ResultCode") != 1:
            return render_template("results.html", error=first_page_data.get("ResultMsg"), players=[], names=names_input)

        rd = first_page_data["ResultData"]
        total_count = rd.get("totalCount", 0)
        page_size = rd.get("pageSize", 10)
        total_pages = math.ceil(total_count / page_size)

        # 모든 페이지 합치기
        all_players = rd.get("PlayerList", []).copy()
        for page_no in range(2, total_pages + 1):
            page_data = fetch_player_search_list(player_names, page_no=page_no)
            if page_data.get("ResultCode") != 1:
                continue
            all_players.extend(page_data["ResultData"].get("PlayerList", []))

        return render_template("results.html", error=None, players=all_players, names=names_input)

    # GET: 검색 폼 렌더
    return render_template("search.html")


@app.route("/player/<int:cid>")
def player_detail(cid):
    names_query = request.args.get("names", "").split(",")
    if not names_query or names_query == [""]:
        return render_template("detail.html", error="검색 기록이 없습니다.", player=None)

    player_names = [n.strip() for n in names_query if n.strip()]
    first_page_data = fetch_player_search_list(player_names, page_no=1)
    if first_page_data.get("ResultCode") != 1:
        return render_template("detail.html", error=first_page_data.get("ResultMsg"), player=None)

    rd = first_page_data["ResultData"]
    total_count = rd.get("totalCount", 0)
    page_size = rd.get("pageSize", 10)
    total_pages = math.ceil(total_count / page_size)

    all_players = rd.get("PlayerList", []).copy()
    for page_no in range(2, total_pages + 1):
        page_data = fetch_player_search_list(player_names, page_no=page_no)
        if page_data.get("ResultCode") != 1:
            continue
        all_players.extend(page_data["ResultData"].get("PlayerList", []))

    selected = next((p for p in all_players if p.get("cid") == cid), None)
    if not selected:
        return render_template("detail.html", error="해당 선수를 찾을 수 없습니다.", player=None)

    return render_template("detail.html", error=None, player=selected)


if __name__ == "__main__":
    app.run(debug=True, port=9000)
