#!/usr/bin/env python3
"""Sync FC Mobile refresh-time data and card images into local static files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests


SOURCE_BASE = "https://indvel.github.io/fcmobiletimes/"
SOURCE_JSON = urljoin(SOURCE_BASE, "scripts/cardData.json")
ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "static" / "times"
OUT_JSON = OUT_DIR / "cardData.json"
USER_AGENT = "Mozilla/5.0 fimobook asset sync"


def fetch_bytes(url: str) -> bytes:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    return response.content


def local_image_path(image: str) -> Path:
    normalized = image.strip()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized.startswith("/"):
        normalized = normalized[1:]
    if normalized.startswith("resources/"):
        normalized = normalized[len("resources/") :]
    return Path(normalized)


def sync(force: bool = False) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = fetch_bytes(SOURCE_JSON)
    cards = json.loads(raw.decode("utf-8"))

    downloaded = 0
    failed: list[str] = []

    for card in cards:
        image = str(card.get("image") or "").strip()
        if not image:
            continue

        if image.startswith("http://") or image.startswith("https://"):
            source_url = image
            rel_path = local_image_path(Path(image).name)
        else:
            source_url = urljoin(SOURCE_BASE, image[2:] if image.startswith("./") else image)
            rel_path = local_image_path(image)

        target = OUT_DIR / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)

        if force or not target.exists():
            try:
                target.write_bytes(fetch_bytes(source_url))
                downloaded += 1
            except Exception as exc:
                failed.append(f"{source_url} ({exc})")
                continue

        card["image"] = rel_path.as_posix()

    OUT_JSON.write_text(
        json.dumps(cards, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"cards: {len(cards)}")
    print(f"images downloaded: {downloaded}")
    print(f"data: {OUT_JSON.relative_to(ROOT)}")

    if failed:
        print("failed images:", file=sys.stderr)
        for item in failed:
            print(f"- {item}", file=sys.stderr)
        return 1

    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="redownload images even when files already exist")
    args = parser.parse_args()
    return sync(force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
