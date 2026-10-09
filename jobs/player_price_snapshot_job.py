"""Collect and store one complete scheduled player-price snapshot."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, time as datetime_time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from price_history import connect_price_history, replace_daily_snapshots  # noqa: E402


KST = ZoneInfo("Asia/Seoul")
DEFAULT_DATABASE = PROJECT_ROOT / "instance" / "player_price_history.db"
SQUADMAKER_URL = "https://fcmobile.nexon.com/datacenterweb/squadmaker"
SQUADMAKER_AJAX_URL = "https://fcmobile.nexon.com/datacenterweb/SquadMakerAjaxInfo"


def _build_session() -> requests.Session:
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


def _fetch_csrf_token(session: requests.Session) -> str:
    response = session.get(SQUADMAKER_URL, timeout=20)
    response.raise_for_status()
    token_input = BeautifulSoup(response.text, "html.parser").find(
        "input", {"name": "__RequestVerificationToken"}
    )
    if token_input is None or not token_input.get("value"):
        raise RuntimeError("CSRF token was not found on the SquadMaker page")
    return str(token_input["value"])


def _fetch_player_page(
    session: requests.Session,
    csrf_token: str,
    *,
    page_no: int,
    min_ovr: int,
) -> dict[str, Any]:
    body = {
        "strMethod": "PlayerSearchList",
        "n8Cid": 0,
        "n4PageNo": page_no,
        "strPlayerName": "",
        "strClass": "",
        "strLeagueId": "",
        "strPositionCode": "",
        "strTeamId": "",
        "strNationality": "",
        "n1Force": 0,
        "n4OvrMin": min_ovr,
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
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = session.post(SQUADMAKER_AJAX_URL, data=body, timeout=30)
            response.raise_for_status()
            payload = response.json()
            if payload.get("ResultCode") != 1:
                raise RuntimeError(payload.get("ResultMsg") or "player search failed")
            return payload
        except (requests.RequestException, ValueError, RuntimeError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"page {page_no} failed after 3 attempts: {last_error}")


def collect_players(
    min_ovr: int,
    delay: float,
    max_pages: int | None = None,
) -> list[dict[str, Any]]:
    """Collect only the official fields needed for the daily price snapshot."""
    session = _build_session()
    csrf_token = _fetch_csrf_token(session)
    page_no = 1
    total_pages = 1
    players: list[dict[str, Any]] = []
    seen_cids: set[int] = set()

    while page_no <= total_pages:
        payload = _fetch_player_page(
            session,
            csrf_token,
            page_no=page_no,
            min_ovr=min_ovr,
        )
        result_data = payload.get("ResultData") or {}
        if page_no == 1:
            total_count = int(result_data.get("totalCount") or 0)
            page_size = int(result_data.get("pageSize") or 10)
            total_pages = max(1, math.ceil(total_count / page_size))
            if max_pages is not None:
                total_pages = min(total_pages, max_pages)
            print(f"[PRICE] upstream count={total_count} pages={total_pages}")

        for player in result_data.get("PlayerList") or []:
            try:
                cid = int(player.get("cid"))
            except (TypeError, ValueError):
                continue
            if cid in seen_cids:
                continue
            seen_cids.add(cid)
            players.append(player)

        if page_no == 1 or page_no % 100 == 0 or page_no == total_pages:
            print(f"[PRICE] collected page {page_no}/{total_pages}, players={len(players)}")
        page_no += 1
        if delay > 0 and page_no <= total_pages:
            time.sleep(delay)

    return players


def _snapshot_time(value: str | None, now: datetime | None = None) -> datetime:
    """Return an idempotent 03:00/15:00 KST snapshot slot."""
    if value:
        if "T" not in value:
            return datetime.combine(
                datetime.fromisoformat(value).date(),
                datetime_time(hour=3),
                tzinfo=KST,
            )
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=KST)
        return parsed.astimezone(KST).replace(microsecond=0)

    current = now or datetime.now(KST)
    if current.tzinfo is None or current.utcoffset() is None:
        current = current.replace(tzinfo=KST)
    current = current.astimezone(KST)
    if current.hour >= 15:
        slot_date = current.date()
        slot_hour = 15
    elif current.hour >= 3:
        slot_date = current.date()
        slot_hour = 3
    else:
        slot_date = (current - timedelta(days=1)).date()
        slot_hour = 15
    return datetime.combine(
        slot_date,
        datetime_time(hour=slot_hour),
        tzinfo=KST,
    )


def _load_players(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as player_file:
        payload = json.load(player_file)
    if not isinstance(payload, list):
        raise ValueError("player JSON must contain a list")
    return [player for player in payload if isinstance(player, dict)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="FC Mobile 선수 시세를 03시/15시 SQLite 스냅샷으로 저장합니다."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(os.getenv("FIMOBOOK_PRICE_HISTORY_DB", DEFAULT_DATABASE)),
        help="시세 이력 SQLite 경로",
    )
    snapshot_group = parser.add_mutually_exclusive_group()
    snapshot_group.add_argument(
        "--at",
        help="저장 기준 시각(ISO 8601). 기본값은 가장 최근 03시/15시 한국시간 슬롯",
    )
    snapshot_group.add_argument(
        "--date",
        help="저장 기준일(YYYY-MM-DD, 호환용). 해당 날짜 오전 3시로 저장",
    )
    parser.add_argument("--min-ovr", type=int, default=100, help="수집할 최소 OVR")
    parser.add_argument("--delay", type=float, default=0.05, help="API 페이지 사이 대기 시간(초)")
    parser.add_argument("--max-pages", type=int, help="수집 페이지 제한(테스트 전용)")
    parser.add_argument(
        "--from-file",
        type=Path,
        help="API 대신 기존 player_data.json을 읽음(점검/초기 적재용)",
    )
    parser.add_argument(
        "--min-fetched-player-count",
        type=int,
        default=int(os.getenv("FIMOBOOK_PRICE_MIN_FETCHED", "10000")),
        help="불완전 수집 방지 최소 선수 수",
    )
    parser.add_argument(
        "--min-priced-player-count",
        type=int,
        default=int(os.getenv("FIMOBOOK_PRICE_MIN_PRICED", "5000")),
        help="불완전 수집 방지 최소 가격 보유 선수 수",
    )
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    target_snapshot = _snapshot_time(args.at or args.date)
    started_at = datetime.now(KST)
    print(
        f"[PRICE] snapshot_at={target_snapshot.isoformat()} "
        f"started_at={started_at.isoformat()}"
    )

    if args.from_file:
        players = _load_players(args.from_file)
        print(f"[PRICE] loaded {len(players)} players from {args.from_file}")
    else:
        players = collect_players(args.min_ovr, args.delay, args.max_pages)
        print(f"[PRICE] fetched {len(players)} players from Nexon")

    connection = connect_price_history(args.database)
    try:
        saved_count = replace_daily_snapshots(
            connection,
            players,
            target_snapshot,
            min_fetched_player_count=args.min_fetched_player_count,
            min_priced_player_count=args.min_priced_player_count,
        )
    finally:
        connection.close()

    elapsed_seconds = (datetime.now(KST) - started_at).total_seconds()
    print(
        f"[PRICE] saved {saved_count} player snapshots to {args.database} "
        f"in {elapsed_seconds:.1f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
