import os
import sys
from datetime import datetime, timedelta
import requests
import firebase_admin
from firebase_admin import credentials, messaging
from sqlalchemy.exc import IntegrityError

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import (  # noqa: E402
    app,
    db,
    RTDB_BASE,
    CODES_PATH,
    _normalize_rtdb_payload,
    _prepare_coupons,
    PushToken,
    CouponSeen,
)
print("[JOB] CWD =", os.getcwd())
print("[JOB] URI =", app.config.get("SQLALCHEMY_DATABASE_URI"))
print("[JOB] INSTANCE_PATH =", getattr(app, "instance_path", None))

def _get_fcm_app():
    key_path = os.environ.get("FIREBASE_ADMIN_KEY_PATH")
    if not key_path:
        key_path = os.path.join(app.instance_path, "clanworldcup-f6399-firebase-adminsdk-fbsvc-211898d910.json")

    if firebase_admin._apps:
        try:
            return firebase_admin.get_app("fcm")
        except ValueError:
            if os.path.exists(key_path):
                cred = credentials.Certificate(key_path)
                return firebase_admin.initialize_app(cred, name="fcm")
            return firebase_admin.get_app()

    if not os.path.exists(key_path):
        raise RuntimeError(f"Firebase admin key not found: {key_path}")
    cred = credentials.Certificate(key_path)
    return firebase_admin.initialize_app(cred)


def _fetch_coupon_codes():
    url = f"{RTDB_BASE}/{CODES_PATH}.json"
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    normalized = _normalize_rtdb_payload(res.json())
    coupons = _prepare_coupons(normalized, dedupe=True)
    return [c.get("code") for c in coupons if c.get("code")]


def _save_new_codes(new_codes):
    now = datetime.utcnow()
    for code in new_codes:
        db.session.add(CouponSeen(code=code, first_seen_at=now))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()


def _should_skip(token, now):
    cooldown_minutes = 30 if token.mode == "instant" else 60
    if not token.last_push_at:
        return False
    return token.last_push_at >= now - timedelta(minutes=cooldown_minutes)


def _build_message_body(new_codes):
    if len(new_codes) == 1:
        return f"새 쿠폰: {new_codes[0]}"
    return f"새 쿠폰 {len(new_codes)}개 추가"


def run():
    with app.app_context():
        codes = _fetch_coupon_codes()
        if not codes:
            return

        existing_codes = {
            row.code for row in CouponSeen.query.filter(CouponSeen.code.in_(codes)).all()
        }
        new_codes = [code for code in codes if code not in existing_codes]
        if not new_codes:
            return

        _save_new_codes(new_codes)

        tokens = PushToken.query.filter_by(is_enabled=True, coupons_enabled=True).all()
        if not tokens:
            return

        fcm_app = _get_fcm_app()
        now = datetime.utcnow()
        body = _build_message_body(new_codes)

        for token in tokens:
            if _should_skip(token, now):
                continue

            message = messaging.Message(
                token=token.token,
                notification=messaging.Notification(
                    title="FC모바일 쿠폰",
                    body=body,
                ),
                webpush=messaging.WebpushConfig(
                    notification=messaging.WebpushNotification(
                        icon="/static/icons/android-launchericon-192-192.png",
                        badge="/static/icons/android-launchericon-72-72.png",
                    ),
                    fcm_options=messaging.WebpushFCMOptions(
                        link="/coupons/",
                    ),
                ),
                data={
                    "type": "coupon",
                    "count": str(len(new_codes)),
                    "url": "/coupons/",
                },
            )

            try:
                messaging.send(message, app=fcm_app)
                token.last_push_at = now
            except Exception:
                token.is_enabled = False
            finally:
                token.last_seen = now

        db.session.commit()

if __name__ == "__main__":
    with app.app_context():
        run()
