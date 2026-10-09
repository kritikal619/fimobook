"""Account-bound renewal push with durable, per-device delivery receipts."""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy.exc import IntegrityError
from pywebpush import WebPushException
# This notification process does not read the 50 MB player catalog.
os.environ["FIMOBOOK_SKIP_PLAYER_DATA"] = "1"
from app import (app, db, RenewalInterest, RenewalPushDevice, RenewalPushDelivery, RenewalQuietHours,
                 Notification, _load_renewal_cards, _renewal_vapid_path)
from renewal_webpush import send_push, ensure_key, public_key
from renewal import renewal_reminder, renewal_is_quiet, KST

def queue_due(now):
    cards = {c['name']: c for c in _load_renewal_cards() if c.get('available')}
    devices = RenewalPushDevice.query.filter_by(enabled=True).all()
    by_user = {}
    for device in devices:
        by_user.setdefault(device.user_id, []).append(device)
    if not by_user:
        return
    quiet_by_user = {row.user_id: row for row in RenewalQuietHours.query.filter(
        RenewalQuietHours.user_id.in_(by_user)).all()}
    for interest in RenewalInterest.query.filter(RenewalInterest.user_id.in_(by_user)).all():
        card = cards.get(interest.card_name)
        if not card:
            continue
        target = renewal_reminder(card, now.replace(tzinfo=timezone.utc))
        if target is None:
            continue
        quiet = quiet_by_user.get(interest.user_id)
        if renewal_is_quiet(quiet, now) or renewal_is_quiet(quiet, target):
            continue
        occurrence = target.replace(tzinfo=None)
        if interest.subscribed_at > now:
            continue
        for device in by_user[interest.user_id]:
            existing = RenewalPushDelivery.query.filter_by(interest_id=interest.id, device_id=device.id,
                                                           occurrence=occurrence).first()
            if existing:
                continue
            try:
                with db.session.begin_nested():
                    db.session.add(RenewalPushDelivery(user_id=interest.user_id, interest_id=interest.id,
                                                      device_id=device.id, occurrence=occurrence))
                    db.session.flush()
            except IntegrityError:
                pass
        if interest.notified_at is None or interest.notified_at < occurrence:
            changed = RenewalInterest.query.filter(
                RenewalInterest.id == interest.id, RenewalInterest.notified_at == interest.notified_at,
            ).update({RenewalInterest.notified_at: occurrence}, synchronize_session=False)
            if changed:
                stamp = target.astimezone(KST).strftime('%H:%M')
                db.session.add(Notification(user_id=interest.user_id, kind='renewal',
                                            message=f'{interest.card_name} 1분 후 갱신\n{stamp} 한국시간', target_url='/times'))
    db.session.commit()


def deliver_pending(now, send=None):
    deliveries = RenewalPushDelivery.query.filter_by(status='pending').order_by(RenewalPushDelivery.id).limit(100).all()
    counts = {'sent': 0, 'retry': 0, 'expired': 0}
    deadline = time.monotonic() + 60
    for item in deliveries:
        if time.monotonic() >= deadline:
            break
        device = db.session.get(RenewalPushDevice, item.device_id)
        interest = db.session.get(RenewalInterest, item.interest_id)
        quiet = db.session.get(RenewalQuietHours, item.user_id)
        delivery_now = now if send else datetime.now(timezone.utc).replace(tzinfo=None)
        if (not device or not interest or not device.enabled or device.user_id != item.user_id
                or interest.user_id != item.user_id or interest.subscribed_at > item.occurrence
                or delivery_now >= item.occurrence or delivery_now < item.occurrence - timedelta(seconds=60) or item.attempts >= 5
                or renewal_is_quiet(quiet, delivery_now) or renewal_is_quiet(quiet, item.occurrence)):
            item.status = 'expired'; counts['expired'] += 1
            continue
        if item.retry_at and item.retry_at > delivery_now:
            continue
        # The service timer runs one job at a time. Outbox survives restart and network failures.
        stamp = item.occurrence.replace(tzinfo=timezone.utc).astimezone(KST).strftime('%H:%M')
        tag = f'renewal-{item.interest_id}-{int(item.occurrence.replace(tzinfo=timezone.utc).timestamp())}'
        payload = {
            'kind': 'renewal', 'title': f'{interest.card_name} 1분 후 갱신',
            'body': f'{stamp} 한국시간에 갱신됩니다.', 'url': '/times', 'tag': tag,
            'renewal_at': item.occurrence.replace(tzinfo=timezone.utc).isoformat(),
        }
        item.attempts += 1
        try:
            if send:
                send(json.loads(device.subscription_json), payload)
            else:
                send_push(json.loads(device.subscription_json), payload, _renewal_vapid_path(),
                          ttl=max(1, int((item.occurrence-delivery_now).total_seconds())))
            item.status = 'sent'
            counts['sent'] += 1
        except WebPushException as error:
            status = getattr(error.response, 'status_code', None)
            if status in (404, 410):
                device.enabled = False
                device.coupons_enabled = False
                item.status = 'expired'
                counts['expired'] += 1
            else:
                item.retry_at = delivery_now + timedelta(seconds=min(15, 3 * 2 ** item.attempts))
                counts['retry'] += 1
                app.logger.warning('Renewal push delivery deferred')
        except Exception:
            item.retry_at = delivery_now + timedelta(seconds=min(15, 3 * 2 ** item.attempts))
            counts['retry'] += 1
            app.logger.warning('Renewal push delivery deferred')
        db.session.commit()
    db.session.commit()
    old = [r.id for r in RenewalPushDelivery.query.filter(
        RenewalPushDelivery.occurrence < now - timedelta(days=7)).limit(1000).all()]
    if old:
        RenewalPushDelivery.query.filter(RenewalPushDelivery.id.in_(old)).delete(synchronize_session=False)
        db.session.commit()
    return counts


def run(now=None, send=None):
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    queue_due(now)
    return deliver_pending(now, send)


def check_configuration():
    key = public_key(_renewal_vapid_path())
    from pywebpush import webpush
    print(json.dumps({'web_push_ready': len(key) == 87, 'encryption_ready': callable(webpush)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--setup', action='store_true')
    args = parser.parse_args()
    with app.app_context():
        if args.setup:
            ensure_key(_renewal_vapid_path())
            check_configuration()
        elif args.check:
            check_configuration()
        else:
            result = run()
            if any(result.values()):
                print(json.dumps(result))
