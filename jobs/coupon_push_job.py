import os
import sys
import time
from datetime import datetime, timedelta
import requests
import firebase_admin
from firebase_admin import credentials, exceptions, messaging
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_

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
    PUSH_TOKEN_STALE_DAYS,
    PushEnrollmentReservation,
    PUSH_ENROLLMENT_RESERVATION_TTL_MINUTES,
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
    return [c.get("code") for c in coupons if c.get("code") and not c.get("boolExpires")]


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


PUSH_JOB_BATCH_SIZE = 500
PUSH_JOB_DEADLINE_SECONDS = 120


def _prune_stale_push_tokens(stale_before, deadline):
    while time.monotonic() < deadline:
        stale_ids = [
            row.id
            for row in PushToken.query.filter(
                or_(PushToken.last_seen.is_(None), PushToken.last_seen < stale_before)
            )
            .order_by(PushToken.id.asc())
            .limit(PUSH_JOB_BATCH_SIZE)
            .with_entities(PushToken.id)
            .all()
        ]
        if not stale_ids:
            break
        PushToken.query.filter(PushToken.id.in_(stale_ids)).delete(
            synchronize_session=False
        )
        db.session.commit()

    reservation_cutoff = datetime.utcnow() - timedelta(
        minutes=PUSH_ENROLLMENT_RESERVATION_TTL_MINUTES
    )
    while time.monotonic() < deadline:
        expired_ids = [
            row.id
            for row in PushEnrollmentReservation.query.filter(
                PushEnrollmentReservation.created_at < reservation_cutoff
            )
            .order_by(PushEnrollmentReservation.id.asc())
            .limit(PUSH_JOB_BATCH_SIZE)
            .with_entities(PushEnrollmentReservation.id)
            .all()
        ]
        if not expired_ids:
            return True
        PushEnrollmentReservation.query.filter(
            PushEnrollmentReservation.id.in_(expired_ids)
        ).delete(synchronize_session=False)
        db.session.commit()
    return False


def _build_multicast_message(tokens, body, new_codes):
    return messaging.MulticastMessage(
        tokens=[token.token for token in tokens],
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


def _is_permanently_invalid_token_error(error):
    return isinstance(
        error,
        (
            messaging.SenderIdMismatchError,
            messaging.UnregisteredError,
            exceptions.InvalidArgumentError,
        ),
    )


def run():
    with app.app_context():
        deadline = time.monotonic() + PUSH_JOB_DEADLINE_SECONDS
        now = datetime.utcnow()
        stale_before = now - timedelta(days=PUSH_TOKEN_STALE_DAYS)
        if not _prune_stale_push_tokens(stale_before, deadline):
            return

        codes = _fetch_coupon_codes()
        if not codes:
            return

        existing_codes = {
            row.code for row in CouponSeen.query.filter(CouponSeen.code.in_(codes)).all()
        }
        new_codes = [code for code in codes if code not in existing_codes]
        if not new_codes:
            return

        body = _build_message_body(new_codes)
        token_query = PushToken.query.filter(
            PushToken.is_enabled.is_(True),
            PushToken.coupons_enabled.is_(True),
            PushToken.last_seen >= stale_before,
        )
        if not token_query.first():
            _save_new_codes(new_codes)
            return

        fcm_app = _get_fcm_app()
        last_id = 0
        completed = True

        while True:
            if time.monotonic() >= deadline:
                completed = False
                break

            batch = (
                PushToken.query.filter(
                    PushToken.is_enabled.is_(True),
                    PushToken.coupons_enabled.is_(True),
                    PushToken.last_seen >= stale_before,
                    PushToken.id > last_id,
                )
                .order_by(PushToken.id.asc())
                .limit(PUSH_JOB_BATCH_SIZE)
                .all()
            )
            if not batch:
                break

            last_id = batch[-1].id
            unverified = [token for token in batch if token.fcm_verified_at is None]
            if unverified:
                if time.monotonic() >= deadline:
                    completed = False
                    break
                verification_message = _build_multicast_message(
                    unverified,
                    body,
                    new_codes,
                )
                try:
                    verification = messaging.send_each_for_multicast(
                        verification_message,
                        dry_run=True,
                        app=fcm_app,
                    )
                except Exception:
                    app.logger.warning(
                        "Legacy coupon push-token validation failed; codes remain pending"
                    )
                    db.session.rollback()
                    completed = False
                    break

                if len(verification.responses) != len(unverified):
                    db.session.rollback()
                    completed = False
                    break

                verified_at = datetime.utcnow()
                transient_validation_error = False
                for token, result in zip(unverified, verification.responses):
                    if result.success:
                        token.fcm_verified_at = verified_at
                        token.last_seen = verified_at
                    elif _is_permanently_invalid_token_error(result.exception):
                        token.is_enabled = False
                        token.last_seen = verified_at
                    else:
                        transient_validation_error = True

                if transient_validation_error:
                    db.session.rollback()
                    completed = False
                    break

            recipients = [
                token
                for token in batch
                if token.fcm_verified_at is not None and not _should_skip(token, now)
            ]
            if recipients:
                multicast = _build_multicast_message(recipients, body, new_codes)
                try:
                    response = messaging.send_each_for_multicast(multicast, app=fcm_app)
                except Exception:
                    app.logger.warning("Coupon push batch failed; the codes remain pending")
                    db.session.rollback()
                    completed = False
                    break

                sent_at = datetime.utcnow()
                for token, result in zip(recipients, response.responses):
                    if result.success:
                        token.last_push_at = sent_at
                    else:
                        token.is_enabled = False
                    token.last_seen = sent_at

            db.session.commit()
            if len(batch) < PUSH_JOB_BATCH_SIZE:
                break
            if time.monotonic() >= deadline:
                completed = False
                break

        if completed:
            _save_new_codes(new_codes)

if __name__ == "__main__":
    with app.app_context():
        run()
