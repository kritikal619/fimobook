"""Server-owned player refresh: validate staged data and images before publishing."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "venv/bin/python"
PLAYER_FILE = ROOT / "player_data.json"
CLASS_FILE = ROOT / "static/data/player_class_names.json"
ORDER_FILE = ROOT / "static/js/player-class-order.js"


def run(*command, timeout):
    subprocess.run([str(part) for part in command], cwd=ROOT, check=True, timeout=timeout)


def validate(player_path, class_path, previous_count):
    players = json.loads(player_path.read_text())
    mapping = json.loads(class_path.read_text())
    if not isinstance(players, list) or not players:
        raise ValueError("Player array is empty or invalid")
    cids = [str(int(player["cid"])) for player in players]
    if len(set(cids)) != len(cids):
        raise ValueError("Duplicate player CIDs")
    if len(players) < previous_count * 0.9:
        raise ValueError(f"Abnormal player decline: {previous_count} -> {len(players)}")
    required = {"source", "class_count", "target_count", "mapped_count", "overlap_count", "classes"}
    if not isinstance(mapping, dict) or not required.issubset(mapping):
        raise ValueError("Invalid class-map schema")
    classes = mapping["classes"]
    if not isinstance(classes, dict) or set(classes) != set(cids):
        raise ValueError("Incomplete class mapping")
    if mapping["target_count"] != len(players) or mapping["mapped_count"] != len(classes):
        raise ValueError("Class-map counts do not match player data")
    for player, cid in zip(players, cids):
        if not isinstance(classes[cid], str) or not classes[cid].strip():
            raise ValueError(f"Missing class name: {cid}")
        if player.get("className") != classes[cid]:
            raise ValueError(f"Player class and class map disagree: {cid}")
    return players


def class_updates(players):
    source = ORDER_FILE.read_text()
    match = re.search(r"const playerClassOrder = (\[.*?\]);", source, re.S)
    if not match:
        raise ValueError("Cannot locate class-order array")
    order = json.loads(match.group(1))
    incoming = sorted({player["className"] for player in players} - set(order))
    if not incoming:
        return {}, incoming
    # Preserve the four pinned groups, then show newly discovered classes.
    updated = order[:4] + incoming + order[4:]
    array = json.dumps(updated, ensure_ascii=False, indent=2)
    text = source[:match.start(1)] + array + source[match.end(1):]
    version = "refresh-" + hashlib.sha256(text.encode()).hexdigest()[:12]
    changes = {ORDER_FILE: text.encode()}
    for path in (ROOT / "templates").rglob("*.html"):
        template = path.read_text()
        if "js/player-class-order.js" not in template:
            continue
        pattern = r"(filename=['\"]js/player-class-order\.js['\"]\s*,\s*v=)['\"][^'\"]*['\"]"
        updated_template, count = re.subn(pattern, lambda m: m.group(1) + repr(version), template)
        if not count:
            raise ValueError(f"Cannot update class-order cache version: {path}")
        if updated_template != template:
            changes[path] = updated_template.encode()
    return changes, incoming


def publish(changes, stage):
    prepared = []
    for index, (target, content) in enumerate(changes.items()):
        if target.read_bytes() == content:
            continue
        info = target.stat()
        backup = stage / f"backup-{index}"
        shutil.copy2(target, backup)
        temporary = target.with_name(target.name + ".player-refresh.tmp")
        temporary.write_bytes(content)
        os.chown(temporary, info.st_uid, info.st_gid)
        os.chmod(temporary, info.st_mode & 0o7777)
        prepared.append((temporary, target))
    # All network work, validation, and file preparation have succeeded.
    for temporary, target in prepared:
        os.replace(temporary, target)
        print(f"Installed {target.relative_to(ROOT)}", flush=True)
    return bool(prepared)


def refresh(check_only):
    stage = Path(tempfile.mkdtemp(prefix="fimobook-player-refresh-"))
    print(f"Refresh workspace: {stage}", flush=True)
    try:
        run(PYTHON, "-u", ROOT / "scripts/check_player_refresh_network.py", timeout=90)
        old_count = len(json.loads(PLAYER_FILE.read_text()))
        if check_only:
            players = validate(PLAYER_FILE, CLASS_FILE, old_count)
            candidate = PLAYER_FILE
        else:
            candidate = stage / "player_data.json"
            class_candidate = stage / "player_class_names.json"
            run(PYTHON, "-u", ROOT / "fastcrawl.py", "--output", candidate,
                "--class-map-output", class_candidate, timeout=90 * 60)
            players = validate(candidate, class_candidate, old_count)
        changes, incoming = class_updates(players)
        report_path = stage / "images.json"
        command = [PYTHON, "-u", ROOT / "scripts/ensure_player_images.py",
                   "--data", candidate, "--report", report_path]
        if check_only:
            command.append("--check-only")
        run(*command, timeout=30 * 60)
        report = json.loads(report_path.read_text())
        if report["missing"]:
            raise ValueError("Unresolved server images; refusing publication")
        print(f"Validated {len(players)} players; new classes={incoming}; "
              f"images downloaded={report['downloaded']}; "
              f"known missing={len(report['allowed_missing'])}", flush=True)
        if check_only:
            print("READY: no application files changed", flush=True)
        else:
            changes = {PLAYER_FILE: candidate.read_bytes(), CLASS_FILE: class_candidate.read_bytes(), **changes}
            if publish(changes, stage):
                run("sudo", "-n", "/usr/bin/systemctl", "restart", "fimobook.service", timeout=90)
            run("/usr/bin/systemctl", "is-active", "--quiet", "fimobook.service", timeout=15)
            with urllib.request.urlopen("https://fcbook.info", timeout=30) as response:
                if response.status != 200:
                    raise RuntimeError(f"Public site HTTP {response.status}")
            print("SUCCESS: service active, public HTTP 200", flush=True)
    except Exception:
        print(f"FAILED: workspace and any backups retained at {stage}; no automatic rollback", flush=True)
        raise
    else:
        shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    with open("/tmp/fimobook-player-refresh.lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("SKIPPED: another server refresh holds the lock", flush=True)
            return 0
        refresh(args.check_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
