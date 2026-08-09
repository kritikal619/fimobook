import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests


ALLOWED_EXTENSIONS = {".webp", ".png", ".jpg", ".jpeg"}


def infer_extension(url: str, content_type: str) -> str:
    path_ext = os.path.splitext(urlparse(url).path)[1].lower()
    if path_ext in ALLOWED_EXTENSIONS:
        return path_ext
    ct = (content_type or "").lower()
    if "webp" in ct:
        return ".webp"
    if "png" in ct:
        return ".png"
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    return ".jpg"


def remove_existing_variants(directory: str, cid: int) -> None:
    for ext in ALLOWED_EXTENSIONS:
        path = os.path.join(directory, f"{cid}{ext}")
        if os.path.exists(path):
            os.remove(path)


def has_existing_variant(directory: str, cid: int) -> bool:
    for ext in ALLOWED_EXTENSIONS:
        if os.path.exists(os.path.join(directory, f"{cid}{ext}")):
            return True
    return False


def download_one(session: requests.Session, url: str, target_dir: str, cid: int, force: bool) -> tuple[bool, str]:
    if not url:
        return False, "missing_url"

    if not force and has_existing_variant(target_dir, cid):
        return False, "exists"

    try:
        response = session.get(url, timeout=20)
        response.raise_for_status()
    except Exception:
        return False, "request_failed"

    extension = infer_extension(url, response.headers.get("Content-Type"))
    if force:
        remove_existing_variants(target_dir, cid)

    out_path = os.path.join(target_dir, f"{cid}{extension}")
    tmp_path = f"{out_path}.tmp"
    with open(tmp_path, "wb") as file:
        file.write(response.content)
    os.replace(tmp_path, out_path)
    return True, out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Download all player card/face images into static folders.")
    parser.add_argument("--data", default="player_data.json", help="Path to player_data.json")
    parser.add_argument("--workers", type=int, default=20, help="Concurrent worker count")
    parser.add_argument("--force", action="store_true", help="Re-download even when local file exists")
    parser.add_argument("--limit", type=int, default=0, help="Only process first N players (0 means all)")
    args = parser.parse_args()

    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    data_path = args.data if os.path.isabs(args.data) else os.path.join(root_dir, args.data)
    card_dir = os.path.join(root_dir, "static", "card")
    face_dir = os.path.join(root_dir, "static", "faceon")
    os.makedirs(card_dir, exist_ok=True)
    os.makedirs(face_dir, exist_ok=True)

    with open(data_path, "r", encoding="utf-8") as file:
        players = json.load(file)

    if args.limit > 0:
        players = players[: args.limit]

    tasks = []
    with requests.Session() as session:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            for player in players:
                if not isinstance(player, dict):
                    continue
                cid = player.get("cid")
                if not cid:
                    continue
                card_url = player.get("bimage")
                face_url = player.get("pimage")
                if card_url:
                    tasks.append(executor.submit(download_one, session, card_url, card_dir, int(cid), args.force))
                if face_url:
                    tasks.append(executor.submit(download_one, session, face_url, face_dir, int(cid), args.force))

            saved = 0
            skipped = 0
            failed = 0
            for future in as_completed(tasks):
                ok, state = future.result()
                if ok:
                    saved += 1
                elif state == "exists":
                    skipped += 1
                else:
                    failed += 1

    print(f"done: saved={saved}, skipped={skipped}, failed={failed}, total_tasks={len(tasks)}")


if __name__ == "__main__":
    main()
