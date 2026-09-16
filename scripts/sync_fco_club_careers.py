#!/usr/bin/env python3
"""Build a compact, PID-keyed club-career cache from NEXON's latest data."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_URL = (
    "https://fco.vod.nexoncdn.co.kr/list/2025/3/"
    "club_FCO_250313_gkelks0jkf4dG_test.html"
)
DEFAULT_PROFILE_FILE = ROOT / "instance" / "fco_allp.js"
DEFAULT_PLAYER_FILE = ROOT / "player_data.json"
DEFAULT_OUTPUT_FILE = ROOT / "static" / "data" / "player_club_careers.json"


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    return re.sub(r"[^0-9a-z가-힣]", "", text)


def normalize_team(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    text = re.sub(r"\((?:임대|loan)\)", "", text, flags=re.IGNORECASE)
    replacements = {
        "아스날": "아스널",
        "롬바르디아fc": "인테르",
        "라티움": "ss라치오",
        "나폴리fc": "ssc나폴리",
        "ac밀란": "밀라노fc",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"[^0-9a-z가-힣]", "", text)
    for suffix in ("afc", "fc", "cf", "sc", "ac"):
        if text.endswith(suffix) and len(text) > len(suffix) + 2:
            text = text[: -len(suffix)]
            break
    return text


def abbreviated_korean_tail(value: object) -> str:
    """Return the Korean part of names such as `V. 요케레스`."""
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not re.match(r"^[A-Za-zÀ-ÖØ-öø-ÿ]\s*\.?\s*", text):
        return ""
    remainder = re.sub(r"^[A-Za-zÀ-ÖØ-öø-ÿ]\s*\.?\s*", "", text, count=1)
    korean_parts = re.findall(r"[가-힣]+", remainder)
    tail = "".join(korean_parts)
    return tail if len(tail) >= 2 else ""


def full_name_korean_tail(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    parts = re.findall(r"[가-힣]+", text)
    if not parts:
        return ""
    # 공식 DB가 `빅토르 요케레스`처럼 전체 이름을 쓰는 경우뿐 아니라
    # `그바르디올`처럼 한글 한 단어만 쓰는 경우도 축약명 후보로 등록한다.
    tail = parts[-1] if len(parts) > 1 else parts[0]
    return tail if len(tail) >= 2 else ""


def load_json_or_js(path: Path):
    raw = path.read_text(encoding="utf-8").strip()
    raw = re.sub(r"^\s*(?:const|let|var)\s+allData\s*=\s*", "", raw)
    raw = re.sub(r";\s*$", "", raw)
    return json.loads(raw)


def fetch_latest_source(source_url: str, timeout: int = 30):
    session = requests.Session()
    session.headers.update({"User-Agent": "Fimobook club-career sync/1.0"})
    response = session.get(source_url, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    script_text = "\n".join(script.get_text("\n") for script in soup.find_all("script"))
    base_match = re.search(r'CDN_BASE\s*=\s*["\']([^"\']+club_json/)["\']', script_text)
    if not base_match:
        raise RuntimeError("원본 페이지에서 club_json CDN 경로를 찾지 못했습니다.")

    month_tabs = soup.select(".tab2 li")
    if not month_tabs:
        raise RuntimeError("원본 페이지에서 월별 데이터 탭을 찾지 못했습니다.")

    latest_label = month_tabs[0].get_text(" ", strip=True)
    label_match = re.search(r"(\d{2})\s*년\s*(\d{1,2})\s*월", latest_label)
    updated_label = latest_label
    if label_match:
        updated_label = f"20{label_match.group(1)}년 {int(label_match.group(2))}월"

    pages_per_month = 5
    latest_last_index = len(month_tabs) * pages_per_month
    source_indices = list(range(latest_last_index - pages_per_month + 1, latest_last_index + 1))
    cdn_base = base_match.group(1)
    shards = []
    for index in source_indices:
        data_response = session.get(f"{cdn_base}{index}.json", timeout=timeout)
        data_response.raise_for_status()
        data = data_response.json()
        if not isinstance(data, list):
            raise RuntimeError(f"{index}.json 데이터가 배열 형식이 아닙니다.")
        shards.append((index, data))

    return {
        "updated_label": updated_label,
        "source_indices": source_indices,
        "shards": shards,
    }


def split_career_runs(rows):
    runs = []
    current_name = None
    current_rows = []
    for row in rows:
        name = str(row.get("선수명") or "").strip()
        if current_rows and name != current_name:
            runs.append((current_name, current_rows))
            current_rows = []
        current_name = name
        current_rows.append(row)
    if current_rows:
        runs.append((current_name, current_rows))
    return runs


def build_candidate_index(shards):
    by_name = defaultdict(list)
    total_rows = 0
    for source_index, rows in shards:
        total_rows += len(rows)
        for name, career_rows in split_career_runs(rows):
            key = normalize_text(name)
            if key:
                by_name[key].append({"source_index": source_index, "rows": career_rows})
            korean_tail = full_name_korean_tail(name)
            if korean_tail:
                by_name[f"@tail:{korean_tail}"].append(
                    {"source_index": source_index, "rows": career_rows}
                )
    return by_name, total_rows


def choose_candidate(by_name, names, teams):
    candidates = []
    seen = set()
    used_abbreviated_alias = False
    for name in names:
        for candidate in by_name.get(normalize_text(name), []):
            marker = (candidate["source_index"], id(candidate["rows"]))
            if marker not in seen:
                seen.add(marker)
                candidates.append(candidate)
    if not candidates:
        for name in names:
            korean_tail = abbreviated_korean_tail(name)
            if not korean_tail:
                continue
            for candidate in by_name.get(f"@tail:{korean_tail}", []):
                marker = (candidate["source_index"], id(candidate["rows"]))
                if marker not in seen:
                    seen.add(marker)
                    candidates.append(candidate)
                    used_abbreviated_alias = True
    if not candidates:
        return None

    normalized_teams = [normalize_team(team) for team in teams if normalize_team(team)]
    team_set = set(normalized_teams)
    scored = []
    for candidate in candidates:
        clubs = [normalize_team(row.get("클럽명")) for row in candidate["rows"]]
        club_set = {club for club in clubs if club}
        overlap = len(team_set & club_set)
        score = overlap * 100
        if normalized_teams and clubs and normalized_teams[0] == clubs[-1]:
            score += 25
        for profile_club, source_club in zip(normalized_teams, reversed(clubs)):
            if profile_club == source_club:
                score += 5
        score += min(len(candidate["rows"]), 20) / 100
        scored.append((score, overlap, candidate))

    scored.sort(key=lambda item: item[0], reverse=True)
    if len(scored) == 1 and (not used_abbreviated_alias or scored[0][1] >= 1):
        return scored[0][2]
    if scored[0][1] < 1 or scored[0][0] == scored[1][0]:
        return None
    return scored[0][2]


def compact_career(rows):
    compact = []
    for row in rows:
        club = str(row.get("클럽명") or "").strip()
        if not club:
            continue
        start = row.get("연도 시작일")
        end = row.get("연도 종료일")
        compact.append(
            {
                "start": int(start) if str(start or "").isdigit() else None,
                "end": int(end) if str(end or "").isdigit() else None,
                "club": club,
                "loan": str(row.get("임대 여부") or "").strip() == "임대",
            }
        )
    return compact


def build_player_cache(candidate_index, profiles, player_cards):
    careers_by_pid = {}

    for profile in profiles:
        raw_id = str(profile.get("id") or "").strip()
        if not raw_id.isdigit():
            continue
        pid = str(int(raw_id) % 1_000_000)
        teams = [profile.get("team"), *(profile.get("career") or [])]
        candidate = choose_candidate(
            candidate_index,
            [profile.get("name"), profile.get("originName")],
            teams,
        )
        if candidate:
            career = compact_career(candidate["rows"])
            if career:
                careers_by_pid[pid] = career

    cards_by_pid = defaultdict(list)
    for card in player_cards:
        pid = card.get("pid")
        if pid not in (None, ""):
            cards_by_pid[str(pid)].append(card)

    for pid, cards in cards_by_pid.items():
        if pid in careers_by_pid:
            continue
        names = Counter(str(card.get("playerKor") or "").strip() for card in cards)
        names.pop("", None)
        if not names:
            continue
        teams = []
        for card in cards:
            team = str(card.get("team") or "").strip()
            league = str(card.get("league") or "").strip()
            if team and league != "국가대표" and team not in teams:
                teams.append(team)
        candidate = choose_candidate(candidate_index, [names.most_common(1)[0][0]], teams)
        if candidate:
            career = compact_career(candidate["rows"])
            if career:
                careers_by_pid[pid] = career

    return careers_by_pid, len(cards_by_pid)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILE_FILE)
    parser.add_argument("--players", type=Path, default=DEFAULT_PLAYER_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_FILE)
    args = parser.parse_args()

    source = fetch_latest_source(args.source_url)
    candidate_index, source_row_count = build_candidate_index(source["shards"])
    profiles = load_json_or_js(args.profiles)
    player_cards = load_json_or_js(args.players)
    careers_by_pid, local_player_count = build_player_cache(candidate_index, profiles, player_cards)

    payload = {
        "meta": {
            "source_url": args.source_url,
            "updated_label": source["updated_label"],
            "source_indices": source["source_indices"],
            "source_row_count": source_row_count,
            "local_player_count": local_player_count,
            "matched_player_count": len(careers_by_pid),
            "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "players": {
            pid: careers_by_pid[pid]
            for pid in sorted(careers_by_pid, key=lambda value: int(value))
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(
        f"saved {len(careers_by_pid):,}/{local_player_count:,} players "
        f"from {source_row_count:,} rows to {args.output}"
    )


if __name__ == "__main__":
    main()
