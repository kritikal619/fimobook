import argparse
import ast
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


SQUADMAKER_URL = "https://fcmobile.nexon.com/datacenterweb/squadmaker"
AJAX_URL = "https://fcmobile.nexon.com/datacenterweb/SquadMakerAjaxInfo"
ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "player_data.json"
DEFAULT_CLASS_MAP_OUTPUT = ROOT / "static" / "data" / "player_class_names.json"
MAX_ENHANCE_LEVEL = 15


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept-Language": "ko,en-US;q=0.9,en;q=0.8",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://fcmobile.nexon.com/DataCenterWeb/SquadMaker",
        }
    )
    return session


def fetch_csrf_token(session: requests.Session) -> str:
    response = session.get(SQUADMAKER_URL, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    token_input = soup.find("input", {"name": "__RequestVerificationToken"})
    if token_input is None or not token_input.get("value"):
        raise RuntimeError("CSRF 토큰을 찾을 수 없습니다.")
    return token_input["value"]


def fetch_player_search_page(
    session: requests.Session,
    csrf_token: str,
    *,
    player_names_list: list[str] | None = None,
    page_no: int = 1,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    player_name_param = "" if not player_names_list else json.dumps(player_names_list, ensure_ascii=False)
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
        "__RequestVerificationToken": csrf_token,
    }
    if filters:
        body.update(filters)

    response = session.post(AJAX_URL, data=body, timeout=30)
    response.raise_for_status()
    return response.json()


def clean_class_name(value: Any) -> str:
    if isinstance(value, list):
        names = [clean_class_name(item) for item in value]
        return " / ".join(dict.fromkeys(name for name in names if name))

    text = str(value or "").strip()
    if text.startswith("[") and text.endswith("]"):
        try:
            decoded = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            decoded = None
        if isinstance(decoded, list):
            return clean_class_name(decoded)
    return text.strip("\"'")


def fetch_class_infos(session: requests.Session, csrf_token: str) -> list[dict[str, Any]]:
    response = session.post(
        f"{AJAX_URL}?strMethod=Init",
        data={"__RequestVerificationToken": csrf_token},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("ResultCode") != 1:
        raise RuntimeError(payload.get("ResultMsg") or "클래스 목록을 불러오지 못했습니다.")
    return (payload.get("ResultData") or {}).get("ClassInfos") or []


def _parse_skill_style_rows(bundle_text: str) -> list[dict[str, Any]]:
    pattern = re.compile(r"JSON\.parse\(('(?:\\.|[^'\\])*')\)")
    for match in pattern.finditer(bundle_text):
        literal = match.group(1)
        if "StyledId" not in literal or "SkillID1" not in literal:
            continue
        try:
            decoded = ast.literal_eval(literal)
            rows = json.loads(decoded)
        except (SyntaxError, ValueError, TypeError, json.JSONDecodeError):
            continue
        if isinstance(rows, list) and any(
            isinstance(row, dict) and row.get("StyledId") and row.get("SkillID1")
            for row in rows
        ):
            return rows
    raise RuntimeError("스쿼드메이커 번들에서 스킬 스타일 표를 찾을 수 없습니다.")


def fetch_skill_style_map(session: requests.Session) -> dict[str, list[str]]:
    response = session.get(SQUADMAKER_URL, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    loader_src = next(
        (
            script.get("src")
            for script in soup.find_all("script", src=True)
            if "/sqmaker/app.js" in script.get("src", "")
        ),
        "",
    )
    if not loader_src:
        raise RuntimeError("스쿼드메이커 로더 경로를 찾을 수 없습니다.")

    loader_url = urljoin(SQUADMAKER_URL, loader_src)
    loader_response = session.get(loader_url, timeout=20)
    loader_response.raise_for_status()
    bundle_match = re.search(r'["\'](app\.[A-Za-z0-9_-]+\.js)["\']', loader_response.text)
    if not bundle_match:
        raise RuntimeError("스쿼드메이커 번들 경로를 찾을 수 없습니다.")

    bundle_url = urljoin(loader_url, bundle_match.group(1))
    bundle_response = session.get(bundle_url, timeout=30)
    bundle_response.raise_for_status()
    rows = _parse_skill_style_rows(bundle_response.text)

    style_map: dict[str, list[str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        style_id = str(row.get("StyledId") or "").strip()
        if not style_id:
            continue
        skill_ids = []
        for index in range(1, 7):
            skill_id = str(row.get(f"SkillID{index}") or "").strip()
            if not skill_id:
                break
            skill_ids.append(skill_id)
        if skill_ids:
            style_map[style_id] = skill_ids
    if not style_map:
        raise RuntimeError("스쿼드메이커 스킬 스타일 표가 비어 있습니다.")
    return style_map


def apply_skill_style_fallback(
    players: list[dict[str, Any]],
    style_map: dict[str, list[str]],
) -> int:
    filled_count = 0
    for player in players:
        if player.get("skillInfo") or player.get("skills"):
            continue
        style_id = str(player.get("skillStyleId") or "").strip()
        skill_ids = style_map.get(style_id) or []
        if not skill_ids:
            continue
        player["skillInfo"] = [{"id": skill_id, "lv": 0} for skill_id in skill_ids]
        player["skills"] = [{"id": skill_id, "level": 0} for skill_id in skill_ids]
        filled_count += 1
    return filled_count


def normalize_player(player: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(player)
    normalized["className"] = clean_class_name(normalized.get("className"))

    raw_traits = normalized.get("Trait") or []
    if isinstance(raw_traits, list):
        normalized["traits"] = [
            trait.get("name")
            for trait in raw_traits
            if isinstance(trait, dict) and trait.get("name")
        ]
    elif not isinstance(normalized.get("traits"), list):
        normalized["traits"] = []

    raw_skills = normalized.get("skillInfo") or []
    if isinstance(raw_skills, list):
        normalized["skills"] = [
            {
                "id": str(skill.get("id", "")).strip(),
                "level": skill.get("lv"),
            }
            for skill in raw_skills
            if isinstance(skill, dict) and str(skill.get("id", "")).strip()
        ]
    elif not isinstance(normalized.get("skills"), list):
        normalized["skills"] = []

    return normalized


def collect_player_class_names(
    players: list[dict[str, Any]],
    min_ovr: int,
    delay: float,
) -> tuple[dict[str, str], dict[str, set[str]], int]:
    target_cids = {
        int(player["cid"])
        for player in players
        if isinstance(player, dict) and str(player.get("cid") or "").isdigit()
    }
    if not target_cids:
        return {}, {}, 0

    session = build_session()
    csrf_token = fetch_csrf_token(session)
    class_infos = fetch_class_infos(session, csrf_token)
    class_names: dict[str, str] = {}
    overlaps: dict[str, set[str]] = {}

    print(f"\n--- 공식 클래스 {len(class_infos)}개 매칭 시작 ---")
    for class_index, class_info in enumerate(class_infos, start=1):
        class_id = str(class_info.get("id") or "").strip()
        class_name = clean_class_name(class_info.get("name"))
        if not class_id or not class_name:
            continue

        page_no = 1
        total_pages = 1
        mapped_for_class = 0
        while page_no <= total_pages:
            payload = fetch_player_search_page(
                session,
                csrf_token,
                page_no=page_no,
                filters={
                    "strClass": json.dumps([class_id], ensure_ascii=False),
                    "n4OvrMin": min_ovr,
                },
            )
            if payload.get("ResultCode") != 1:
                raise RuntimeError(
                    f"{class_name} {page_no}페이지: "
                    f"{payload.get('ResultMsg') or '선수 목록 오류'}"
                )

            result_data = payload.get("ResultData") or {}
            if page_no == 1:
                total_count = int(result_data.get("totalCount") or 0)
                page_size = int(result_data.get("pageSize") or 10)
                total_pages = max(1, math.ceil(total_count / page_size))

            for player in result_data.get("PlayerList") or []:
                try:
                    cid = int(player.get("cid"))
                except (TypeError, ValueError):
                    continue
                if cid not in target_cids:
                    continue

                key = str(cid)
                previous = class_names.get(key)
                if previous and previous != class_name:
                    overlaps.setdefault(key, set()).update((previous, class_name))
                    # "아이콘"은 이벤트 아이콘 카드까지 함께 반환하는 포괄
                    # 필터이므로 구체적인 이벤트 클래스 결과를 우선한다.
                    if previous == "아이콘":
                        class_names[key] = class_name
                        mapped_for_class += 1
                    continue

                class_names[key] = class_name
                mapped_for_class += 1

            page_no += 1
            if delay > 0:
                time.sleep(delay)

        print(
            f"[{class_index}/{len(class_infos)}] {class_name}: "
            f"{mapped_for_class}명, 누적 {len(class_names)}/{len(target_cids)}"
        )

    missing_cids = target_cids - {int(cid) for cid in class_names}
    if missing_cids:
        sample = ", ".join(str(cid) for cid in sorted(missing_cids)[:10])
        raise RuntimeError(
            f"클래스 매칭 누락 {len(missing_cids)}명"
            f"{f' (예: {sample})' if sample else ''}. 기존 파일은 유지합니다."
        )
    return class_names, overlaps, len(class_infos)


def apply_class_names(
    players: list[dict[str, Any]],
    class_names: dict[str, str],
) -> None:
    for player in players:
        cid = str(player.get("cid") or "")
        class_name = clean_class_name(class_names.get(cid))
        if not class_name:
            raise RuntimeError(f"CID {cid or '?'}의 클래스명이 없어 저장을 중단합니다.")
        player["className"] = class_name


def collect_players(min_ovr: int, delay: float, max_pages: int | None = None) -> list[dict[str, Any]]:
    session = build_session()
    csrf_token = fetch_csrf_token(session)

    page_no = 1
    total_pages = 1
    all_players: list[dict[str, Any]] = []
    seen_cids: set[int] = set()

    print(f"--- 오버롤 {min_ovr} 이상의 선수 데이터 전체 수집 시작 ---")

    while page_no <= total_pages:
        print(f"📥 페이지 {page_no}/{total_pages} 가져오는 중...")

        page_data = fetch_player_search_page(
            session,
            csrf_token,
            player_names_list=None,
            page_no=page_no,
            filters={"n4OvrMin": min_ovr},
        )

        if page_data.get("ResultCode") != 1:
            raise RuntimeError(page_data.get("ResultMsg", "알 수 없는 API 오류"))

        result_data = page_data.get("ResultData", {})
        player_list = result_data.get("PlayerList", [])

        if page_no == 1:
            total_count = result_data.get("totalCount", 0)
            page_size = result_data.get("pageSize", 10)
            total_pages = math.ceil(total_count / page_size) if page_size else 1
            if max_pages is not None:
                total_pages = min(total_pages, max_pages)
            print(f"총 {total_count}명, {total_pages}페이지")

        for player in player_list:
            normalized = normalize_player(player)
            cid = normalized.get("cid")
            if cid in seen_cids:
                continue
            seen_cids.add(cid)
            all_players.append(normalized)

        page_no += 1
        if delay > 0:
            time.sleep(delay)

    return all_players


def write_output(players: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    temp_path.write_text(
        json.dumps(players, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(temp_path, output_path)


def write_class_map(
    class_names: dict[str, str],
    class_count: int,
    target_count: int,
    overlaps: dict[str, set[str]],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": "NEXON SquadMakerAjaxInfo ClassInfos + class-filtered PlayerSearchList",
        "class_count": class_count,
        "target_count": target_count,
        "mapped_count": len(class_names),
        "overlap_count": len(overlaps),
        "classes": dict(sorted(class_names.items(), key=lambda item: int(item[0]))),
    }
    temp_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temp_path, output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FC Mobile 선수 데이터를 전체 필드 그대로 저장합니다.")
    parser.add_argument("--min-ovr", type=int, default=100, help="수집할 최소 OVR. 기본값은 100입니다.")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.05,
        help="페이지 요청 사이 대기 시간(초). 기본값은 0.05초입니다.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"저장할 선수 JSON 경로. 기본값은 {DEFAULT_OUTPUT} 입니다.",
    )
    parser.add_argument(
        "--class-map-output",
        type=Path,
        default=DEFAULT_CLASS_MAP_OUTPUT,
        help=f"저장할 클래스 매핑 경로. 기본값은 {DEFAULT_CLASS_MAP_OUTPUT} 입니다.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="테스트용으로 가져올 최대 페이지 수. 전체 크롤링 시 생략합니다.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    players = collect_players(args.min_ovr, args.delay, args.max_pages)
    skill_style_count = 0
    skill_fallback_count = 0
    try:
        skill_style_map = fetch_skill_style_map(build_session())
        skill_style_count = len(skill_style_map)
        skill_fallback_count = apply_skill_style_fallback(players, skill_style_map)
    except Exception as e:
        print(f"⚠️ 공식 스킬 스타일 표 보완을 건너뜁니다: {e}")
    class_names, overlaps, class_count = collect_player_class_names(
        players,
        args.min_ovr,
        args.delay,
    )
    apply_class_names(players, class_names)
    write_class_map(
        class_names,
        class_count,
        len(players),
        overlaps,
        args.class_map_output,
    )
    write_output(players, args.output)

    sample_keys = sorted(players[0].keys()) if players else []
    price_keys = [f"n8Price{i}" for i in range(MAX_ENHANCE_LEVEL + 1)]
    present_price_keys = [key for key in price_keys if players and key in players[0]]
    skill_keys = [
        key
        for key in ("skillInfo", "skills", "skillStyleId", "skillBoostName", "skillMovesName", "skillMovesLevel")
        if players and key in players[0]
    ]
    print("\n✅ 데이터 수집 완료")
    print(f"총 {len(players)}명의 선수 정보 저장됨")
    print(f"📄 저장 파일명: {args.output}")
    print(f"🏷️ 클래스 매핑: {args.class_map_output}")
    print(f"🔁 공식 중복 필터 정리: {len(overlaps)}명")
    print(f"🌳 공식 스킬 스타일: {skill_style_count}개, 빈 스킬트리 보완: {skill_fallback_count}명")
    print(f"🧩 저장 키 수(첫 선수 기준): {len(sample_keys)}")
    if sample_keys:
        print(f"예시 키: {', '.join(sample_keys[:20])}{' ...' if len(sample_keys) > 20 else ''}")
        print(f"가격 키: {', '.join(present_price_keys)} (단위: MP)")
        print(f"스킬 키: {', '.join(skill_keys) if skill_keys else '없음'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
