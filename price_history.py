"""FC Mobile player price history storage.

Price history intentionally lives in a separate SQLite database so a large
history table cannot increase lock contention or backup size for board.db.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


MAX_ENHANCE_LEVEL = 15

SCHEMA = """
CREATE TABLE IF NOT EXISTS player_price_snapshot (
    player_cid INTEGER NOT NULL,
    snapshot_date TEXT NOT NULL,
    prices_json TEXT NOT NULL,
    base_price INTEGER NOT NULL,
    collected_at TEXT NOT NULL,
    PRIMARY KEY (player_cid, snapshot_date)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS ix_player_price_snapshot_date
    ON player_price_snapshot (snapshot_date);

CREATE TABLE IF NOT EXISTS player_price_snapshot_run (
    snapshot_date TEXT PRIMARY KEY,
    fetched_player_count INTEGER NOT NULL,
    priced_player_count INTEGER NOT NULL,
    collected_at TEXT NOT NULL
) WITHOUT ROWID;
"""


def connect_price_history(database_path: str | Path) -> sqlite3.Connection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA busy_timeout=30000")
    connection.executescript(SCHEMA)
    return connection


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def extract_price_array(
    player: dict[str, Any],
    max_enhance_level: int = MAX_ENHANCE_LEVEL,
) -> list[int | None]:
    """Return a stable index-addressable array of enhancement prices."""
    prices = [
        _positive_int(player.get(f"n8Price{level}"))
        for level in range(max_enhance_level + 1)
    ]
    if prices[0] is None:
        prices[0] = _positive_int(player.get("n8Price"))
    return prices


def _snapshot_key(snapshot_at: date | datetime) -> str:
    if isinstance(snapshot_at, datetime):
        if snapshot_at.tzinfo is None or snapshot_at.utcoffset() is None:
            raise ValueError("snapshot datetime must be timezone-aware")
        return snapshot_at.isoformat(timespec="seconds")
    return snapshot_at.isoformat()


def build_snapshot_rows(
    players: Iterable[dict[str, Any]],
    snapshot_at: date | datetime,
    collected_at: datetime | None = None,
) -> list[tuple[int, str, str, int, str]]:
    collected_at = collected_at or datetime.now(timezone.utc)
    collected_at_text = collected_at.astimezone(timezone.utc).isoformat()
    snapshot_key = _snapshot_key(snapshot_at)
    rows: list[tuple[int, str, str, int, str]] = []
    seen_cids: set[int] = set()

    for player in players:
        try:
            cid = int(player.get("cid"))
        except (TypeError, ValueError):
            continue
        if cid <= 0 or cid in seen_cids:
            continue

        prices = extract_price_array(player)
        base_price = next((price for price in prices if price is not None), None)
        if base_price is None:
            continue

        seen_cids.add(cid)
        rows.append(
            (
                cid,
                snapshot_key,
                json.dumps(prices, ensure_ascii=False, separators=(",", ":")),
                base_price,
                collected_at_text,
            )
        )

    return rows


def replace_daily_snapshots(
    connection: sqlite3.Connection,
    players: Sequence[dict[str, Any]],
    snapshot_at: date | datetime,
    *,
    collected_at: datetime | None = None,
    min_fetched_player_count: int = 10_000,
    min_priced_player_count: int = 5_000,
) -> int:
    """Atomically replace one complete scheduled snapshot.

    Safety thresholds stop an incomplete upstream crawl from replacing a good
    snapshot. Re-running the job for the same date/time slot is idempotent.
    """
    fetched_player_count = len(players)
    if fetched_player_count < min_fetched_player_count:
        raise ValueError(
            f"fetched only {fetched_player_count} players; "
            f"minimum is {min_fetched_player_count}"
        )

    collected_at = collected_at or datetime.now(timezone.utc)
    rows = build_snapshot_rows(players, snapshot_at, collected_at)
    priced_player_count = len(rows)
    if priced_player_count < min_priced_player_count:
        raise ValueError(
            f"found prices for only {priced_player_count} players; "
            f"minimum is {min_priced_player_count}"
        )

    snapshot_date_text = _snapshot_key(snapshot_at)
    collected_at_text = collected_at.astimezone(timezone.utc).isoformat()
    with connection:
        connection.execute(
            "DELETE FROM player_price_snapshot WHERE snapshot_date = ?",
            (snapshot_date_text,),
        )
        connection.executemany(
            """
            INSERT INTO player_price_snapshot (
                player_cid, snapshot_date, prices_json, base_price, collected_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.execute(
            """
            INSERT INTO player_price_snapshot_run (
                snapshot_date, fetched_player_count, priced_player_count, collected_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(snapshot_date) DO UPDATE SET
                fetched_player_count = excluded.fetched_player_count,
                priced_player_count = excluded.priced_player_count,
                collected_at = excluded.collected_at
            """,
            (
                snapshot_date_text,
                fetched_player_count,
                priced_player_count,
                collected_at_text,
            ),
        )
    return priced_player_count


def get_player_price_history(
    connection: sqlite3.Connection,
    player_cid: int,
    *,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Read recent snapshots in chronological order for the price chart/API."""
    safe_limit = max(1, min(int(limit), 3650))
    database_rows = connection.execute(
        """
        SELECT snapshot_date, prices_json, base_price, collected_at
        FROM player_price_snapshot
        WHERE player_cid = ?
        ORDER BY snapshot_date DESC
        LIMIT ?
        """,
        (int(player_cid), safe_limit),
    ).fetchall()
    return [
        {
            "date": row["snapshot_date"],
            "timestamp": row["snapshot_date"],
            "prices": json.loads(row["prices_json"]),
            "base_price": row["base_price"],
            "collected_at": row["collected_at"],
        }
        for row in reversed(database_rows)
    ]


def load_player_price_history(
    database_path: str | Path,
    player_cid: int,
    *,
    limit: int = 128,
) -> list[dict[str, Any]]:
    """Read history without creating or modifying the database file."""
    path = Path(database_path)
    if not path.is_file():
        return []

    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=5000")
    try:
        return get_player_price_history(connection, player_cid, limit=limit)
    finally:
        connection.close()


def load_market_price_changes(database_path: str | Path) -> dict[str, Any]:
    """Compare latest base prices, skipping unchanged snapshots within 24 hours."""
    empty = {"dates": [], "players": []}
    path = Path(database_path)
    if not path.is_file() or path.stat().st_size == 0:
        return empty
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
    try:
        dates = [row[0] for row in connection.execute(
            "SELECT snapshot_date FROM player_price_snapshot_run ORDER BY snapshot_date DESC LIMIT 3"
        )]
        if len(dates) < 2:
            return empty
        latest = datetime.fromisoformat(dates[0])
        unchanged = {"dates": [dates[1], dates[0]], "players": []}
        for previous_date in dates[1:]:
            baseline = datetime.fromisoformat(previous_date)
            if baseline.tzinfo is None:
                baseline = baseline.replace(tzinfo=latest.tzinfo)
            current_time = latest if latest.tzinfo is not None else latest.replace(tzinfo=baseline.tzinfo)
            if current_time - baseline > timedelta(days=1):
                break
            rows = connection.execute(
                """SELECT current.player_cid, current.prices_json, previous.prices_json
                   FROM player_price_snapshot AS current
                   JOIN player_price_snapshot AS previous ON previous.player_cid = current.player_cid
                   WHERE current.snapshot_date = ? AND previous.snapshot_date = ?""",
                (dates[0], previous_date),
            )
            players = []
            for cid, current_json, previous_json in rows:
                current_prices, previous_prices = json.loads(current_json), json.loads(previous_json)
                current = _positive_int(current_prices[0]) if current_prices else None
                previous = _positive_int(previous_prices[0]) if previous_prices else None
                if current is None or previous is None or current == previous:
                    continue
                players.append({"cid": cid, "price": current,
                                "change": (current - previous) / previous * 100})
            if players:
                return {"dates": [previous_date, dates[0]], "players": players}
        return unchanged
    finally:
        connection.close()
