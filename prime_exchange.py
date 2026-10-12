"""Prime exchange efficiency page: config, live price sync and ranking rows."""

import json
import os
import threading
import time
import math
from datetime import datetime, timezone

PRIME_EXCHANGE_CONFIG_PATH = None
PRIME_EXCHANGE_PRICE_SEED_PATH = None
PRIME_EXCHANGE_PRICE_CACHE_PATH = None
PRIME_EXCHANGE_PRICE_CACHE_TTL = 300
_PRIME_EXCHANGE_CACHE = {"signature": None, "value": None}
_PRIME_PRICE_REFRESH_LOCK = threading.Lock()

_get_players = None
_positive_int = None
_has_price_value = None
_new_nexon_price_session = None
_apply_local_assets = None
_normalize_player_record = None


def configure(root_path, instance_path, get_players, **helpers):
    """Wire in the application paths and the helpers that still live in app.py."""
    global PRIME_EXCHANGE_CONFIG_PATH, PRIME_EXCHANGE_PRICE_SEED_PATH, PRIME_EXCHANGE_PRICE_CACHE_PATH, _get_players
    PRIME_EXCHANGE_CONFIG_PATH = os.path.join(root_path, "static", "data", "prime_exchange.json")
    PRIME_EXCHANGE_PRICE_SEED_PATH = os.path.join(root_path, "static", "data", "prime_exchange_prices.json")
    PRIME_EXCHANGE_PRICE_CACHE_PATH = os.path.join(instance_path, "prime_exchange_prices.json")
    _get_players = get_players
    module_globals = globals()
    for name in ['_positive_int', '_has_price_value', '_new_nexon_price_session', '_apply_local_assets', '_normalize_player_record']:
        module_globals[name] = helpers[name]


def _load_prime_exchange_config():
    try:
        with open(PRIME_EXCHANGE_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"Prime exchange config read failed: {e}")
        return {}


def _load_prime_exchange_price_payload():
    for path in (PRIME_EXCHANGE_PRICE_CACHE_PATH, PRIME_EXCHANGE_PRICE_SEED_PATH):
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, dict) and isinstance(payload.get("prices"), dict):
                return payload
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"Prime exchange price cache read failed ({path}): {e}")
    return {"prices": {}, "fetched_at_epoch": 0}


def _prime_exchange_price_cache_signature():
    signature = []
    for path in (PRIME_EXCHANGE_PRICE_CACHE_PATH, PRIME_EXCHANGE_PRICE_SEED_PATH):
        try:
            signature.append(os.path.getmtime(path))
        except OSError:
            signature.append(None)
    return tuple(signature)


def _prime_exchange_target_players(config=None):
    config = config or _load_prime_exchange_config()
    target_ids = {
        cid
        for groups in (config.get("players") or {}).values()
        if isinstance(groups, dict)
        for player_ids in groups.values()
        if isinstance(player_ids, list)
        for raw_cid in player_ids
        if (cid := _positive_int(raw_cid))
    }
    players_by_cid = {
        _positive_int(player.get("cid")): player
        for player in _get_players()
        if isinstance(player, dict) and _positive_int(player.get("cid")) in target_ids
    }
    return target_ids, players_by_cid


def _fetch_prime_exchange_price_page(session, csrf_token, names, ovr, page_no):
    body = {
        "strMethod": "PlayerSearchList",
        "n8Cid": 0,
        "n4PageNo": page_no,
        "strPlayerName": json.dumps(sorted(names), ensure_ascii=False),
        "strClass": "",
        "strLeagueId": "",
        "strPositionCode": "",
        "strTeamId": "",
        "strNationality": "",
        "n1Force": 0,
        "n4OvrMin": ovr,
        "n4OvrMax": ovr,
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
    response = session.post(
        "https://fcmobile.nexon.com/datacenterweb/SquadMakerAjaxInfo",
        data=body,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _sync_prime_exchange_live_prices(output_path=None):
    config = _load_prime_exchange_config()
    target_ids, players_by_cid = _prime_exchange_target_players(config)
    targets_by_ovr = {}
    for cid, player in players_by_cid.items():
        ovr = _positive_int(player.get("ovr"))
        name = str(player.get("playerKor") or "").strip()
        if ovr and name:
            bucket = targets_by_ovr.setdefault(ovr, {"ids": set(), "names": set()})
            bucket["ids"].add(cid)
            bucket["names"].add(name)

    session, csrf_token = _new_nexon_price_session()
    live_prices = {}
    for ovr in sorted(targets_by_ovr, reverse=True):
        bucket = targets_by_ovr[ovr]
        sorted_names = sorted(bucket["names"])
        # 공식 검색 API는 선수명을 한 요청에 최대 5개까지만 허용한다.
        for chunk_start in range(0, len(sorted_names), 5):
            name_chunk = set(sorted_names[chunk_start:chunk_start + 5])
            chunk_ids = {
                cid
                for cid in bucket["ids"]
                if str(players_by_cid[cid].get("playerKor") or "").strip() in name_chunk
            }
            missing_ids = set(chunk_ids)
            page_no = 1
            total_pages = 1
            while page_no <= total_pages and missing_ids:
                page_data = _fetch_prime_exchange_price_page(
                    session, csrf_token, name_chunk, ovr, page_no
                )
                if page_data.get("ResultCode") != 1:
                    break
                result_data = page_data.get("ResultData") or {}
                if page_no == 1:
                    total_count = _positive_int(result_data.get("totalCount")) or 0
                    page_size = _positive_int(result_data.get("pageSize")) or 10
                    total_pages = max(1, math.ceil(total_count / page_size))
                for player in result_data.get("PlayerList") or []:
                    cid = _positive_int(player.get("cid"))
                    if cid not in chunk_ids:
                        continue
                    fields = {
                        key: player.get(key)
                        for key in ("n8Price7", "n8Price10")
                        if _has_price_value(player.get(key))
                    }
                    if fields:
                        live_prices[str(cid)] = fields
                        missing_ids.discard(cid)
                page_no += 1

    previous = _load_prime_exchange_price_payload().get("prices") or {}
    merged_prices = dict(previous)
    merged_prices.update(live_prices)
    now = time.time()
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "fetched_at_epoch": now,
        "source": "NEXON SquadMakerAjaxInfo",
        "target_count": len(target_ids),
        "updated_count": len(live_prices),
        "prices": merged_prices,
    }
    destination = output_path or PRIME_EXCHANGE_PRICE_CACHE_PATH
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    temp_path = f"{destination}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, destination)
    _PRIME_EXCHANGE_CACHE.update(signature=None, value=None)
    return payload


def _refresh_prime_exchange_prices_in_background():
    try:
        _sync_prime_exchange_live_prices()
    except Exception as e:
        print(f"Prime exchange live price refresh failed: {e}")
    finally:
        _PRIME_PRICE_REFRESH_LOCK.release()


def _ensure_prime_exchange_live_prices():
    payload = _load_prime_exchange_price_payload()
    fetched_at = float(payload.get("fetched_at_epoch") or 0)
    if time.time() - fetched_at < PRIME_EXCHANGE_PRICE_CACHE_TTL:
        return
    if not _PRIME_PRICE_REFRESH_LOCK.acquire(blocking=False):
        return
    threading.Thread(
        target=_refresh_prime_exchange_prices_in_background,
        name="prime-price-refresh",
        daemon=True,
    ).start()


def _get_prime_exchange_efficiency():
    try:
        config_mtime = os.path.getmtime(PRIME_EXCHANGE_CONFIG_PATH)
    except OSError:
        config_mtime = None
    price_cache_signature = _prime_exchange_price_cache_signature()
    cache_signature = (config_mtime, price_cache_signature, id(_get_players()), len(_get_players()))
    if _PRIME_EXCHANGE_CACHE["signature"] == cache_signature:
        return _PRIME_EXCHANGE_CACHE["value"]

    config = _load_prime_exchange_config()
    live_price_payload = _load_prime_exchange_price_payload()
    live_prices = live_price_payload.get("prices") or {}
    rewards = config.get("token_rewards") or {}
    level_groups = config.get("players") or {}
    players_by_cid = {
        _positive_int(player.get("cid")): player
        for player in _get_players()
        if isinstance(player, dict) and _positive_int(player.get("cid"))
    }
    best_by_player_level = {}
    missing_prices = 0

    for level_key, groups in level_groups.items():
        try:
            enhance_level = int(level_key)
        except (TypeError, ValueError):
            continue
        if enhance_level not in {7, 10} or not isinstance(groups, dict):
            continue

        for raw_group, player_ids in groups.items():
            group = str(raw_group or "").strip().upper()
            token_count = _positive_int(rewards.get(group))
            if not group or not token_count or not isinstance(player_ids, list):
                continue

            for raw_cid in player_ids:
                cid = _positive_int(raw_cid)
                player = players_by_cid.get(cid) if cid else None
                if not player:
                    continue

                price_field = f"n8Price{enhance_level}"
                live_player_prices = live_prices.get(str(cid)) or {}
                price = _positive_int(live_player_prices.get(price_field))
                price_source = "live"
                if not price:
                    price = _positive_int(player.get(price_field))
                    price_source = "local"
                if not price:
                    missing_prices += 1
                    continue

                normalized = _apply_local_assets(_normalize_player_record(player.copy()))
                row = {
                    "cid": cid,
                    "group": group,
                    "enhance_level": enhance_level,
                    "token_count": token_count,
                    "price": price,
                    "price_per_token": price / token_count,
                    "price_source": price_source,
                    "player_name": normalized.get("playerKor") or "선수",
                    "player_class": normalized.get("className") or "",
                    "player_ovr": normalized.get("ovr"),
                    "player_position": normalized.get("position") or "",
                    "player_pimage": normalized.get("pimage") or "",
                    "player_bimage": normalized.get("bimage") or "",
                }

                # 같은 CID가 같은 진화 단계의 여러 그룹에 들어오면 토큰을 더 많이
                # 지급하여 실제 교환 효율이 좋은 그룹 하나만 노출한다.
                dedupe_key = (cid, enhance_level)
                previous = best_by_player_level.get(dedupe_key)
                if previous is None or row["price_per_token"] < previous["price_per_token"]:
                    best_by_player_level[dedupe_key] = row

    rows = sorted(
        best_by_player_level.values(),
        key=lambda item: (
            item["price_per_token"],
            item["price"],
            -item["token_count"],
            item["player_name"],
        ),
    )
    result = {
        "title": config.get("title") or "프라임 교환 효율",
        "source_url": config.get("source_url") or "https://fcmobile.nexon.com/ForumProbability",
        "expires_at": config.get("expires_at") or "",
        "expires_label": config.get("expires_label") or "",
        "rows": rows,
        "missing_prices": missing_prices,
    }
    _PRIME_EXCHANGE_CACHE.update(signature=cache_signature, value=result)
    return result
