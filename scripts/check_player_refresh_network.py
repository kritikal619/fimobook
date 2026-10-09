"""Read-only network preflight using the same requests as the player crawler."""

import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastcrawl import build_session, fetch_csrf_token, fetch_player_search_page


def main() -> int:
    try:
        socket.getaddrinfo("fcmobile.nexon.com", 443)
        with build_session() as session:
            token = fetch_csrf_token(session)
            payload = fetch_player_search_page(
                session, token, page_no=1, filters={"n4OvrMin": 100}
            )
        if payload.get("ResultCode") != 1:
            raise RuntimeError(payload.get("ResultMsg") or "Player search failed")
        data = payload.get("ResultData") or {}
        players = data.get("PlayerList") or []
        if not isinstance(players, list) or not players:
            raise RuntimeError("Player search returned no players")
        print(f"NETWORK_OK: system DNS, CSRF, player search ({len(players)} players)")
        return 0
    except Exception as error:
        print(f"NETWORK_FAILED: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
