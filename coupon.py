import re
import time
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

import requests

RTDB_BASE = "https://game-coupon-default-rtdb.firebaseio.com"
CODES_PATH = "fifaMobile/codes"

_cache: Dict[str, Any] = {"fetched_at": 0.0, "raw": None}


def normalize_rtdb_payload(payload: Any) -> List[Dict[str, Any]]:
    """payload가 list면 그대로, dict면 values()로 리스트화."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        return [v for v in payload.values() if isinstance(v, dict)]
    return []


def _parse_expires(expires_str: Any) -> Optional[date]:
    """지원 포맷을 넓게 받아서 만료일 date 객체로 변환."""
    if not expires_str:
        return None
    if isinstance(expires_str, (int, float)):
        try:
            return datetime.fromtimestamp(expires_str).date()
        except Exception:
            return None
    if not isinstance(expires_str, str):
        return None

    cleaned = expires_str.strip()
    if not cleaned:
        return None

    normalized = cleaned.replace(".", "-").replace("/", "-")
    candidates: Iterable[str] = (cleaned, normalized)
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y.%m.%d",
        "%Y/%m/%d",
        "%Y.%m.%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
    ]

    for text in candidates:
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue

    digits = re.findall(r"\d+", cleaned)
    if len(digits) >= 3:
        try:
            y, m, d = [int(x) for x in digits[:3]]
            return date(y, m, d)
        except Exception:
            return None

    return None


def _parse_added(added_val: Any) -> Optional[datetime]:
    """added 값에서 datetime 추출."""
    if added_val is None:
        return None
    if isinstance(added_val, (int, float)):
        try:
            return datetime.fromtimestamp(added_val)
        except Exception:
            return None
    if not isinstance(added_val, str):
        return None

    text = added_val.strip()
    if not text:
        return None

    iso_text = text.replace("Z", "").replace("T", " ")
    patterns = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%Y/%m/%d",
        "%Y.%m.%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
    ]

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        pass

    for fmt in patterns:
        try:
            return datetime.strptime(iso_text, fmt)
        except ValueError:
            continue

    digits = re.findall(r"\d+", text)
    if len(digits) >= 3:
        try:
            y, m, d = [int(x) for x in digits[:3]]
            return datetime(y, m, d)
        except Exception:
            return None

    return None


def _dedupe_by_code(coupons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """code가 중복이면 added 최신만 남김."""
    by_code: Dict[str, Dict[str, Any]] = {}
    no_code: List[Dict[str, Any]] = []

    for coupon in coupons:
        code = coupon.get("code")
        if not code:
            no_code.append(coupon)
            continue

        existing = by_code.get(code)
        if not existing:
            by_code[code] = coupon
            continue

        if coupon.get("_parsed_added") and existing.get("_parsed_added"):
            if coupon["_parsed_added"] > existing["_parsed_added"]:
                by_code[code] = coupon
        elif coupon.get("_parsed_added") and not existing.get("_parsed_added"):
            by_code[code] = coupon

    return [*by_code.values(), *no_code]


def _prepare_coupons(raw_coupons: List[Dict[str, Any]], dedupe: bool = True) -> List[Dict[str, Any]]:
    """정렬/만료 플래그 세팅까지 마친 최종 리스트."""
    today = date.today()
    enriched: List[Dict[str, Any]] = []

    for entry in raw_coupons:
        coupon = dict(entry)
        exp_date = _parse_expires(coupon.get("expires"))
        coupon["_parsed_expires"] = exp_date
        coupon["_parsed_added"] = _parse_added(coupon.get("added"))
        coupon["boolExpires"] = bool(exp_date and exp_date < today)
        enriched.append(coupon)

    processed = _dedupe_by_code(enriched) if dedupe else enriched

    def sort_key(c: Dict[str, Any]):
        return (
            c.get("_parsed_added") or datetime.min,
            c.get("_parsed_expires") or date.min,
        )

    processed.sort(key=sort_key, reverse=True)

    for coupon in processed:
        coupon.pop("_parsed_expires", None)
        coupon.pop("_parsed_added", None)

    return processed


def _fetch_raw():
    url = f"{RTDB_BASE}/{CODES_PATH}.json"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def get_coupons(dedupe: bool = True, ttl: int = 120) -> List[Dict[str, Any]]:
    """RTDB에서 쿠폰을 읽어와 정제 후 반환 (TTL 캐시 적용)."""
    now = time.time()
    if _cache.get("raw") is not None and now - _cache.get("fetched_at", 0) < ttl:
        raw_payload = _cache["raw"]
    else:
        raw_payload = _fetch_raw()
        _cache["raw"] = raw_payload
        _cache["fetched_at"] = now

    normalized = normalize_rtdb_payload(raw_payload)
    return _prepare_coupons(normalized, dedupe=dedupe)
