"""Download missing server assets and refuse refreshes with new image omissions."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
import os
from pathlib import Path
import time

from PIL import Image
import requests


ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = ("webp", "png", "jpg", "jpeg")  # Same precedence as app.py.
IMAGE_EXTENSIONS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}


def valid_image(path):
    try:
        with Image.open(path) as image:
            image.verify()
        return True
    except (OSError, ValueError, SyntaxError):
        return False


def existing_image(kind, cid):
    for extension in EXTENSIONS:
        path = ROOT / "static" / kind / f"{cid}.{extension}"
        if path.exists():
            # The app also uses the first existing variant. Do not overlook a
            # damaged preferred variant because a lower-priority one is valid.
            return path, valid_image(path)
    return None, False


def ensure_asset(asset, check_only):
    kind, cid, url = asset
    existing, valid = existing_image(kind, cid)
    result = {"kind": kind, "cid": cid, "url": url}
    if valid:
        return {**result, "status": "existing"}
    if check_only or not url:
        return {**result, "status": "missing", "error": "missing or invalid image"}
    error = ""
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=(10, 20))
            response.raise_for_status()
            with Image.open(BytesIO(response.content)) as image:
                extension = IMAGE_EXTENSIONS.get(image.format)
                image.verify()
            if not extension:
                raise ValueError("Unsupported image format")
            destination = existing or ROOT / "static" / kind / f"{cid}.{extension}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".refresh.tmp")
            temporary.write_bytes(response.content)
            os.replace(temporary, destination)
            return {**result, "status": "downloaded", "path": str(destination)}
        except (requests.RequestException, OSError, ValueError, SyntaxError) as exc:
            error = str(exc)
            if attempt < 2:
                time.sleep(attempt + 1)
    return {**result, "status": "missing", "error": error}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "player_data.json")
    parser.add_argument("--exceptions", type=Path,
                        default=ROOT / "static/data/player_image_exceptions.json")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    players = json.loads(args.data.read_text())
    if not isinstance(players, list) or not players:
        raise ValueError("Player data must be a nonempty array")
    exceptions = json.loads(args.exceptions.read_text())
    allowed = {(entry["kind"], str(entry["cid"]), entry["url"]) for entry in exceptions}
    assets = {}
    for player in players:
        cid = str(int(player["cid"]))
        for kind, key in (("card", "bimage"), ("faceon", "pimage")):
            url = player.get(key) or ""
            asset = (kind, cid, url)
            previous = assets.setdefault((kind, cid), asset)
            if previous != asset:
                raise ValueError(f"Conflicting source URLs for {kind}/{cid}")
    report = {"players": len(players), "required": len(assets),
              "existing": 0, "downloaded": 0, "allowed_missing": [], "missing": []}
    print(f"Checking {len(assets)} server images", flush=True)
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        for result in executor.map(lambda asset: ensure_asset(asset, args.check_only), assets.values()):
            if result["status"] == "missing":
                key = (result["kind"], result["cid"], result["url"])
                category = "allowed_missing" if key in allowed else "missing"
                report[category].append(result)
                print(f"{category}: {result['kind']}/{result['cid']}: {result['error']}", flush=True)
            else:
                report[result["status"]] += 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.report.with_name(args.report.name + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    os.replace(temporary, args.report)
    print(f"existing={report['existing']} downloaded={report['downloaded']} "
          f"known_missing={len(report['allowed_missing'])} new_missing={len(report['missing'])}")
    return 1 if report["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
