#!/usr/bin/env python3
"""Download the fcplayer.org card catalogue into a private snapshot file.

The detail pages used to query fcplayer.org once per player view, which hit its
60 requests/minute limit whenever crawlers walked the player pages. The app now
reads this snapshot instead; it only needs the skill slots/types, skill boost
name and a few stats used to pick the right card.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
API_URL = "https://fcplayer.org/api/cards"
DEFAULT_OUTPUT = ROOT / "instance" / "fcplayer_cards.json"
PAGE_SIZE = 50
KEEP_FIELDS = (
    "id", "name", "ovr", "position", "className", "skills", "skillBoost",
    "leftFootRating", "rightFootRating",
    "pace", "shooting", "passing", "agilityMain", "defending", "physical",
)
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def fetch_page(session, offset, attempts=6):
    for attempt in range(attempts):
        response = session.get(
            API_URL, params={"limit": PAGE_SIZE, "offset": offset},
            headers=HEADERS, timeout=20,
        )
        if response.status_code == 429:
            wait = response.headers.get("retry-after") or response.headers.get("ratelimit-reset") or "60"
            try:
                delay = min(120.0, max(5.0, float(wait)))
            except ValueError:
                delay = 60.0
            print(f"429 at offset {offset}; waiting {delay:.0f}s (attempt {attempt + 1}/{attempts})", flush=True)
            time.sleep(delay)
            continue
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("cards"), list):
            raise ValueError(f"unexpected payload at offset {offset}")
        return payload
    raise RuntimeError(f"gave up at offset {offset} after repeated 429 responses")


def download(delay):
    session = requests.Session()
    cards = {}
    first = fetch_page(session, 0)
    total = int(first.get("total") or 0)
    pages = [first]
    offset = PAGE_SIZE
    while offset < total:
        time.sleep(delay)
        pages.append(fetch_page(session, offset))
        offset += PAGE_SIZE
    for payload in pages:
        for card in payload["cards"]:
            if isinstance(card, dict) and card.get("id") is not None and card.get("name"):
                cards[card["id"]] = {key: card.get(key) for key in KEEP_FIELDS}
    return total, list(cards.values())


def write_atomic(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False, separators=(",", ":"))
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        else:
            os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--delay", type=float, default=1.6,
                        help="seconds between requests (default keeps under 40/min)")
    args = parser.parse_args()

    total, cards = download(args.delay)
    if total < 1000 or len(cards) < total * 0.95:
        print(f"refusing to write: total={total}, downloaded={len(cards)}", file=sys.stderr)
        return 1
    if args.output.exists():
        try:
            previous = len(json.loads(args.output.read_text(encoding="utf-8")).get("cards", []))
        except (OSError, ValueError):
            previous = 0
        if previous and len(cards) < previous * 0.8:
            print(f"refusing to write: {len(cards)} cards is far below previous {previous}", file=sys.stderr)
            return 1
    cards.sort(key=lambda card: (str(card["name"]), card["id"]))
    write_atomic(args.output, {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": total,
        "cards": cards,
    })
    print(f"wrote {len(cards)} cards (source total {total}) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
