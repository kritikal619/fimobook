"""New coupon delivery using the account-bound browser subscription."""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pywebpush import WebPushException
# This notification process does not read the 50 MB player catalog.
os.environ["FIMOBOOK_SKIP_PLAYER_DATA"] = "1"
from app import (app, db, RenewalPushDevice, CouponPushState, CouponPushRelease, CouponPushDelivery,
                 Notification, _fetch_coupon_raw, _normalize_rtdb_payload,
                 _prepare_coupons, _renewal_vapid_path)
from renewal_webpush import send_push


def queue_new(coupons, now):
    active = {c['code'] for c in coupons if c.get('code') and not c.get('boolExpires')}
    # Seed once, so starting the scheduler never announces historical coupons.
    seeded = db.session.get(CouponPushState, 1) is not None
    if not seeded:
        db.session.add(CouponPushState(id=1, initialized_at=now))
    known = {row.code for row in CouponPushRelease.query.filter(CouponPushRelease.code.in_(active))}
    new = sorted(active - known)
    for code in new:
        db.session.add(CouponPushRelease(code=code, discovered_at=now))
    if seeded and new:
        devices = RenewalPushDevice.query.filter_by(coupons_enabled=True).all()
        users = set()
        for device in devices:
            if not device.coupons_subscribed_at or device.coupons_subscribed_at > now:
                continue
            for code in new:
                db.session.add(CouponPushDelivery(user_id=device.user_id, device_id=device.id, code=code, created_at=now))
            users.add(device.user_id)
        for uid in users:
            message = f'새 쿠폰: {new[0]}' if len(new) == 1 else f'새 쿠폰 {len(new)}개가 추가되었습니다.'
            db.session.add(Notification(user_id=uid, kind='coupon', message=message, target_url='/coupons/'))
    db.session.commit()


def deliver_pending(coupons, now, send=None):
    send = send or (lambda subscription, payload: send_push(subscription, payload, _renewal_vapid_path(), ttl=24*60*60))
    active = {c['code'] for c in coupons if c.get('code') and not c.get('boolExpires')}
    counts = {'sent': 0, 'retry': 0, 'expired': 0}
    deadline = time.monotonic() + 60
    for item in CouponPushDelivery.query.filter_by(status='pending').order_by(CouponPushDelivery.id).limit(100).all():
        if time.monotonic() >= deadline:
            break
        device = db.session.get(RenewalPushDevice, item.device_id)
        if (not device or not device.coupons_enabled or device.user_id != item.user_id
                or not device.coupons_subscribed_at or device.coupons_subscribed_at > item.created_at
                or item.code not in active or now - item.created_at > timedelta(hours=24) or item.attempts >= 5):
            item.status = 'expired'; counts['expired'] += 1
            continue
        if item.retry_at and item.retry_at > now:
            continue
        item.attempts += 1
        payload = {'kind': 'coupon', 'title': 'FC모바일 새 쿠폰', 'body': item.code,
                   'url': '/coupons/', 'tag': 'coupon-' + item.code}
        try:
            send(json.loads(device.subscription_json), payload)
            item.status = 'sent'; counts['sent'] += 1
        except WebPushException as error:
            if getattr(error.response, 'status_code', None) in (404, 410):
                device.enabled = False; device.coupons_enabled = False
                item.status = 'expired'; counts['expired'] += 1
            else:
                item.retry_at = now + timedelta(seconds=min(600, 30 * 2 ** item.attempts)); counts['retry'] += 1
                app.logger.warning('Coupon push delivery deferred')
        except Exception:
            item.retry_at = now + timedelta(seconds=min(600, 30 * 2 ** item.attempts)); counts['retry'] += 1
            app.logger.warning('Coupon push delivery deferred')
        db.session.commit()
    db.session.commit()
    old = [row.id for row in CouponPushDelivery.query.filter(CouponPushDelivery.created_at < now-timedelta(days=7)).limit(1000)]
    if old:
        CouponPushDelivery.query.filter(CouponPushDelivery.id.in_(old)).delete(synchronize_session=False)
        db.session.commit()
    return counts


def run(coupons=None, now=None, send=None):
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    # Source failures abort before changing the baseline or expiring pending delivery.
    if coupons is None:
        coupons = _prepare_coupons(_normalize_rtdb_payload(_fetch_coupon_raw()), dedupe=True)
    queue_new(coupons, now)
    return deliver_pending(coupons, now, send)


if __name__ == '__main__':
    with app.app_context():
        print(json.dumps(run()))
