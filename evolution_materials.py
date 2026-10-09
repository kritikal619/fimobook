"""Comparable evolution material prices from completed player snapshots."""

import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from price_history import extract_price_array

EXCLUDED_CLASSES = {"25TOTS", "25TOTY", "26TOTY"}
MIN_MATERIAL_OVR = 133
MIN_TARGET_OVR = 136
MAX_MATERIAL_LEVEL = 9
TRIM_LOW = 10
TRIM_HIGH = 20


def _integer(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def _summarize(prices):
    ordered = sorted(price for price in prices if isinstance(price, int) and price > 0)
    retained = ordered[TRIM_LOW:-TRIM_HIGH] if len(ordered) > TRIM_LOW + TRIM_HIGH else []
    return {
        "price": round(sum(retained) / len(retained)) if retained else None,
        "count": len(ordered),
        "retained_count": len(retained),
    }


def _snapshot_groups(database_path, players_by_cid):
    path = Path(database_path)
    if not path.is_file() or not path.stat().st_size or not players_by_cid:
        return []
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"player_price_snapshot", "player_price_snapshot_run"} <= tables:
            return []
        # Read only completed scheduled collections, keeping the latest 128 slots.
        dates = [row[0] for row in connection.execute(
            "SELECT snapshot_date FROM player_price_snapshot_run ORDER BY snapshot_date DESC LIMIT 128"
        )]
        if not dates:
            return []
        groups = {date: defaultdict(list) for date in dates}
        cids = list(players_by_cid)
        for offset in range(0, len(cids), 700):
            batch = cids[offset:offset + 700]
            rows = connection.execute(
                "SELECT snapshot_date, player_cid, prices_json FROM player_price_snapshot "
                f"WHERE snapshot_date IN ({','.join('?' for _ in dates)}) "
                f"AND player_cid IN ({','.join('?' for _ in batch)})",
                dates + batch,
            )
            for date, cid, raw in rows:
                prices = json.loads(raw)
                ovr = players_by_cid[cid]["ovr"]
                for level, value in enumerate(prices[1:MAX_MATERIAL_LEVEL + 1], 1):
                    price = _integer(value)
                    if price > 0:
                        groups[date][(ovr, level)].append(price)
        return [(date, groups[date]) for date in reversed(dates)]
    finally:
        connection.close()


def build_evolution_material_trends(players, database_path):
    eligible = {}
    max_target = MIN_TARGET_OVR
    for player in players:
        ovr, cid = _integer(player.get("ovr")), _integer(player.get("cid"))
        max_target = max(max_target, ovr)
        season = re.sub(r"\s+", "", str(player.get("className") or "")).upper()
        if cid > 0 and ovr >= MIN_MATERIAL_OVR and season not in EXCLUDED_CLASSES:
            eligible[cid] = {**player, "ovr": ovr}

    snapshots = _snapshot_groups(database_path, eligible)
    source = "snapshot" if snapshots else "local"
    if not snapshots:
        groups = defaultdict(list)
        for player in eligible.values():
            for level, price in enumerate(extract_price_array(player, max_enhance_level=MAX_MATERIAL_LEVEL)[1:], 1):
                if price is not None:
                    groups[(player["ovr"], level)].append(price)
        snapshots = [("", groups)]

    summaries = [(date, {key: _summarize(prices) for key, prices in groups.items()})
                 for date, groups in snapshots]
    targets = []
    for target_ovr in range(MIN_TARGET_OVR, max_target + 1):
        # Evolution-material OVR follows the user's base OVR + evolution rule;
        # this is separate from stat enhancement bonuses in the application.
        # Allow 133 for the newly requested 136/137 rows. For higher targets,
        # retain the original 134 floor because lower-OVR supply is scarce.
        material_floor = MIN_MATERIAL_OVR if target_ovr <= 137 else 134
        keys = [(ovr, target_ovr - ovr)
                for ovr in range(max(material_floor, target_ovr - MAX_MATERIAL_LEVEL), target_ovr)]
        history = []
        for date, groups in summaries:
            combinations = [{"ovr": ovr, "level": level,
                             **groups.get((ovr, level), {"price": None, "count": 0, "retained_count": 0})}
                            for ovr, level in keys]
            priced = [item for item in combinations if item["price"] is not None]
            best = min(priced, key=lambda item: (item["price"], item["level"], item["ovr"])) if priced else None
            history.append({"date": date, "price": best["price"] if best else None,
                            "best": best, "combinations": combinations})
        latest = history[-1]
        previous = history[-2] if len(history) > 1 else None
        previous_prices = {(item["ovr"], item["level"]): item["price"]
                           for item in previous["combinations"]} if previous else {}
        for item in latest["combinations"]:
            before = previous_prices.get((item["ovr"], item["level"]))
            item["change"] = (item["price"] / before - 1) * 100 if before and item["price"] else None
            item["best"] = item is latest["best"]
        before = previous["price"] if previous else None
        targets.append({"ovr": target_ovr, "combinations": latest["combinations"],
                        "best": latest["best"],
                        "change": (latest["price"] / before - 1) * 100 if before and latest["price"] else None,
                        "history": history if source == "snapshot" else []})
    return {"targets": targets, "updated_at": snapshots[-1][0], "source": source, "error": False}
