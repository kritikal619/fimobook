#!/usr/bin/env python3
"""Read-only report on web-push adoption (renewal and coupon alerts).

Compares the current database with the baseline taken on 2026-10-12, just before
the "alerts are off" notices went live on /times and /coupons. Run it on the
server, or pipe it over ssh:

    ssh fimobook-prod python3 - < scripts/push_adoption_report.py
"""

import argparse
import sqlite3
from pathlib import Path

DEFAULT_DB = "/home/ubuntu/fimobook/instance/board.db"
BASELINE = {
    "devices_total": 14,
    "max_device_id": 14,
    "renewal_enabled_devices": 4,
    "coupon_enabled_devices": 7,
    "interest_users": 31,
    "interest_rows": 70,
    "interest_users_with_renewal_push": 0,
    "renewal_deliveries_sent": 2,
    "coupon_deliveries_sent": 3,
}


def collect(connection):
    one = lambda sql, *args: connection.execute(sql, args).fetchone()[0]
    interest_users = {row[0] for row in connection.execute("select distinct user_id from renewal_interest")}
    renewal_users = {row[0] for row in connection.execute(
        "select distinct user_id from renewal_push_device where enabled=1")}
    return {
        "devices_total": one("select count(*) from renewal_push_device"),
        "max_device_id": one("select coalesce(max(id),0) from renewal_push_device"),
        "renewal_enabled_devices": one("select count(*) from renewal_push_device where enabled=1"),
        "coupon_enabled_devices": one("select count(*) from renewal_push_device where coupons_enabled=1"),
        "interest_users": len(interest_users),
        "interest_rows": one("select count(*) from renewal_interest"),
        "interest_users_with_renewal_push": len(interest_users & renewal_users),
        "renewal_deliveries_sent": one("select count(*) from renewal_push_delivery where status='sent'"),
        "coupon_deliveries_sent": one("select count(*) from coupon_push_delivery where status='sent'"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB)
    args = parser.parse_args()
    if not Path(args.db).exists():
        raise SystemExit(f"database not found: {args.db}")
    connection = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    now = collect(connection)
    labels = {
        "devices_total": "등록된 기기 수",
        "renewal_enabled_devices": "갱신 알림 켠 기기",
        "coupon_enabled_devices": "쿠폰 알림 켠 기기",
        "interest_users": "관심 카드를 저장한 사용자",
        "interest_rows": "저장된 관심 카드 수",
        "interest_users_with_renewal_push": "그중 갱신 알림을 켠 사용자",
        "renewal_deliveries_sent": "갱신 알림 발송(누적)",
        "coupon_deliveries_sent": "쿠폰 알림 발송(누적)",
    }
    print(f"{'항목':<28}{'기준(10/12)':>12}{'현재':>8}{'증감':>8}")
    for key, label in labels.items():
        before, after = BASELINE[key], now[key]
        print(f"{label:<24}{before:>12}{after:>8}{after - before:>+8}")
    new_ids = [row for row in connection.execute(
        "select id, user_id, enabled, coupons_enabled from renewal_push_device where id > ? order by id",
        (BASELINE["max_device_id"],))]
    print(f"\n기준 이후 새로 등록된 기기: {len(new_ids)}대")
    for device_id, user_id, enabled, coupons in new_ids:
        print(f"  기기 {device_id}: 사용자 {user_id}, 갱신 {'켜짐' if enabled else '꺼짐'}, 쿠폰 {'켜짐' if coupons else '꺼짐'}")


if __name__ == "__main__":
    main()
