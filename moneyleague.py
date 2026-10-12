"""Money League registration board: storage quotas, screenshots and comments."""

import hashlib
import hmac
import ipaddress
import os
import re
import stat
import uuid
import warnings
from datetime import date, datetime
from io import BytesIO

from firebase_admin import firestore
from flask import abort, request
from PIL import Image
from werkzeug.utils import secure_filename

# Anonymous registrations are allowed, so bound decoded image work and the
# cumulative Firestore/filesystem footprint.
MONEYLEAGUE_MAX_IMAGE_PIXELS = 40_000_000
MONEYLEAGUE_MAX_IMAGE_FRAMES = 20
MONEYLEAGUE_MAX_ACTIVE_REGISTRATIONS = 2_000
MONEYLEAGUE_MAX_ACTIVE_IMAGE_BYTES = 2 * 1024 * 1024 * 1024
MONEYLEAGUE_MAX_ACTIVE_COMMENTS = 10_000
MONEYLEAGUE_MAX_ACTIVE_COMMENT_BYTES = 64 * 1024 * 1024
MONEYLEAGUE_MAX_TOTAL_COMMENT_WRITES = 10_000
MONEYLEAGUE_MAX_DAILY_WRITES = 1_000
MONEYLEAGUE_MAX_DAILY_CLIENT_WRITES = 30
MONEYLEAGUE_MAX_DAILY_CLIENT_BYTES = 50 * 1024 * 1024
MONEYLEAGUE_QUOTA_COLLECTION = 'moneyleague_registration_quotas'
MONEYLEAGUE_SCREENSHOT_NAME_RE = re.compile(
    r"mreg_[0-9]+_[0-9a-f]{8}\.(?:png|jpg|jpeg|gif|webp)\Z"
)

_app = None
_get_fs = None
Notification = None
allowed_image = None


def configure(app, get_fs, notification_model, allowed_image_check):
    """Wire in the Flask app, Firestore client and helpers that still live in app.py."""
    global _app, _get_fs, Notification, allowed_image
    _app = app
    _get_fs = get_fs
    Notification = notification_model
    allowed_image = allowed_image_check


def _is_moneyleague_registration_open():
    return bool(_app.config.get("MONEYLEAGUE_REGISTRATION_OPEN"))

def _moneyleague_registration_collection():
    if not _get_fs():
        return None
    return _get_fs().collection("moneyleague_registrations")

def _format_moneyleague_registration(doc):
    data = doc.to_dict() or {}
    created_at = data.get("created_at")
    created_at_display = "-"
    if hasattr(created_at, "strftime"):
        created_at_display = created_at.strftime("%Y-%m-%d %H:%M")

    return {
        "id": doc.id,
        "clan_name": data.get("clan_name", ""),
        "participant_count": data.get("participant_count", ""),
        "participant_roster": data.get("participant_roster", ""),
        "resolve_message": data.get("resolve_message", ""),
        "author_id": data.get("author_id"),
        "author_name": data.get("author_name", "익명"),
        "author_ip_prefix": data.get("author_ip_prefix", ""),
        "author_display": data.get("author_display") or data.get("author_name", "익명"),
        "clan_screenshot_path": data.get("clan_screenshot_path"),
        "created_at_display": created_at_display,
    }

def _get_moneyleague_registration_or_404(registration_id):
    collection = _moneyleague_registration_collection()
    if not collection:
        abort(503)
    doc = collection.document(registration_id).get()
    if not doc.exists:
        abort(404)
    return doc, _format_moneyleague_registration(doc)

def _extract_moneyleague_registration_payload(form):
    clan_name = (form.clan_name.data or "").strip()
    participant_count_raw = (form.participant_count.data or "").strip()
    participant_roster = (form.participant_roster.data or "").strip()
    resolve_message = (form.resolve_message.data or "").strip()

    invalid = False
    participant_count = None
    try:
        participant_count = int(participant_count_raw)
        if participant_count <= 0:
            raise ValueError
    except ValueError:
        form.participant_count.errors.append("참가 인원은 1명 이상의 숫자로 입력해 주세요.")
        invalid = True

    if not clan_name:
        form.clan_name.errors.append("클랜명을 입력해 주세요.")
        invalid = True
    if not participant_roster:
        form.participant_roster.errors.append("참가 인원 명단을 입력해 주세요.")
        invalid = True
    if not resolve_message:
        form.resolve_message.errors.append("각오 한마디를 입력해 주세요.")
        invalid = True

    payload = {
        "clan_name": clan_name,
        "participant_count": participant_count,
        "participant_roster": participant_roster,
        "resolve_message": resolve_message,
    }
    return payload, invalid

def _moneyleague_comments_collection(registration_id):
    collection = _moneyleague_registration_collection()
    if not collection:
        return None
    return collection.document(registration_id).collection("comments")

def _client_ip_prefix():
    forwarded_for = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    ip = forwarded_for or (request.remote_addr or "").strip()
    if not ip:
        return ""
    if "." in ip:
        parts = ip.split(".")
        if len(parts) >= 2:
            return f"{parts[0]}.{parts[1]}"
        return ip
    if ":" in ip:
        parts = [p for p in ip.split(":") if p]
        if len(parts) >= 2:
            return f"{parts[0]}:{parts[1]}"
        return ip
    return ip

BLOCKED_REGISTRATION_IP_PREFIXES = {
    "115.161", "175.202", "121.190", "122.32", "223.33", "223.62",
    "39.7", "110.70", "175.223", "175.252", "210.125", "211.246",
    "114.200", "117.111", "211.36",
}

def _is_blocked_registration_ip_prefix(ip_prefix):
    if not ip_prefix:
        return False
    return ip_prefix in BLOCKED_REGISTRATION_IP_PREFIXES

def _moneyleague_quota_ref():
    if not _get_fs():
        raise RuntimeError("Firestore is not configured.")
    return _get_fs().collection(MONEYLEAGUE_QUOTA_COLLECTION).document("active")


def _moneyleague_comment_quota_bytes(content):
    if not isinstance(content, str):
        raise RuntimeError("Money League comment data is invalid.")
    return len(content.encode("utf-8")) + 512


def _moneyleague_existing_quota_usage():
    collection = _moneyleague_registration_collection()
    if not collection:
        raise RuntimeError("Money League registration storage is unavailable.")

    registration_count = 0
    comment_count = 0
    comment_bytes = 0
    for registration in collection.stream():
        registration_count += 1
        for comment in registration.reference.collection("comments").stream():
            comment_count += 1
            comment_data = comment.to_dict() or {}
            comment_bytes += _moneyleague_comment_quota_bytes(
                comment_data.get("content")
            )

    legacy_notification_writes = Notification.query.filter_by(
        kind="moneyleague_comment"
    ).count()

    image_bytes = 0
    upload_dir = os.path.join(
        _app.config["UPLOAD_FOLDER"], "moneyleague_registrations"
    )
    try:
        with os.scandir(upload_dir) as entries:
            for entry in entries:
                try:
                    stat_result = entry.stat(follow_symlinks=False)
                except OSError as error:
                    raise RuntimeError("Could not inspect Money League uploads.") from error
                if stat.S_ISREG(stat_result.st_mode):
                    image_bytes += stat_result.st_size
    except FileNotFoundError:
        pass

    return {
        "active_registrations": registration_count,
        "active_image_bytes": image_bytes,
        "active_comments": comment_count,
        "active_comment_bytes": comment_bytes,
        "total_comment_writes": max(comment_count, legacy_notification_writes),
        "quota_day": datetime.utcnow().date().isoformat(),
        "daily_write_count": 0,
        "daily_clients": {},
    }


def _ensure_moneyleague_quota_initialized():
    quota_ref = _moneyleague_quota_ref()
    if quota_ref.get().exists:
        return quota_ref

    initial_usage = _moneyleague_existing_quota_usage()
    transaction = _get_fs().transaction()

    @firestore.transactional
    def initialize(transaction):
        snapshot = quota_ref.get(transaction=transaction)
        if not snapshot.exists:
            transaction.set(quota_ref, initial_usage)

    initialize(transaction)
    return quota_ref


def _moneyleague_quota_values(snapshot):
    if not snapshot.exists:
        raise RuntimeError("Money League storage quota is not initialized.")
    data = snapshot.to_dict() or {}
    integer_fields = (
        "active_registrations",
        "active_image_bytes",
        "active_comments",
        "active_comment_bytes",
        "total_comment_writes",
        "daily_write_count",
    )
    for field in integer_fields:
        value = data.get(field)
        if type(value) is not int or value < 0:
            raise RuntimeError("Money League storage quota data is invalid.")
    quota_day = data.get("quota_day")
    if not isinstance(quota_day, str):
        raise RuntimeError("Money League storage quota data is invalid.")
    try:
        parsed_quota_day = date.fromisoformat(quota_day)
    except ValueError as error:
        raise RuntimeError("Money League storage quota data is invalid.") from error
    if parsed_quota_day.isoformat() != quota_day:
        raise RuntimeError("Money League storage quota data is invalid.")
    clients = data.get("daily_clients")
    if not isinstance(clients, dict):
        raise RuntimeError("Money League storage quota data is invalid.")
    if quota_day == datetime.utcnow().date().isoformat():
        if len(clients) > MONEYLEAGUE_MAX_DAILY_WRITES:
            raise RuntimeError("Money League storage quota data is invalid.")
        for client_key, client_usage in clients.items():
            if not re.fullmatch(r"[0-9a-f]{64}", str(client_key)):
                raise RuntimeError("Money League storage quota data is invalid.")
            if not isinstance(client_usage, dict):
                raise RuntimeError("Money League storage quota data is invalid.")
            for field in ("writes", "bytes"):
                value = client_usage.get(field)
                if type(value) is not int or value < 0:
                    raise RuntimeError("Money League storage quota data is invalid.")
    return data


def _moneyleague_quota_client_key():
    # Nginx overwrites X-Real-IP after restoring the visitor address from a
    # trusted Cloudflare peer; X-Forwarded-For may contain client-supplied hops.
    raw_address = (request.headers.get("X-Real-IP") or request.remote_addr or "").strip()
    try:
        parsed_address = ipaddress.ip_address(raw_address)
        if isinstance(parsed_address, ipaddress.IPv6Address) and parsed_address.ipv4_mapped:
            parsed_address = parsed_address.ipv4_mapped
        if isinstance(parsed_address, ipaddress.IPv6Address):
            address = f"{ipaddress.ip_network((parsed_address, 64), strict=False).network_address.compressed}/64"
        else:
            address = parsed_address.compressed
    except ValueError:
        address = "unknown"
    secret = str(_app.secret_key or "").encode("utf-8")
    return hmac.new(secret, address.encode("utf-8"), hashlib.sha256).hexdigest()


def _moneyleague_quota_day_state(data):
    today = datetime.utcnow().date().isoformat()
    if data["quota_day"] > today:
        raise RuntimeError("Money League storage quota date is invalid.")
    if data["quota_day"] != today:
        return today, 0, {}
    return today, data["daily_write_count"], dict(data["daily_clients"])


def _reserve_moneyleague_storage(
    kind, amount, client_key, *, new_registration=False, daily_amount=None
):
    if kind not in {"registration", "comment", "edit"}:
        raise ValueError("Invalid Money League quota kind.")
    if type(amount) is not int or amount <= 0:
        raise ValueError("Invalid Money League quota amount.")
    if daily_amount is None:
        daily_amount = amount
    if type(daily_amount) is not int or daily_amount <= 0:
        raise ValueError("Invalid Money League daily quota amount.")
    if not re.fullmatch(r"[0-9a-f]{64}", str(client_key)):
        raise ValueError("Invalid Money League client quota key.")

    quota_ref = _ensure_moneyleague_quota_initialized()
    transaction = _get_fs().transaction()

    @firestore.transactional
    def reserve(transaction):
        data = _moneyleague_quota_values(quota_ref.get(transaction=transaction))
        quota_day, daily_count, daily_clients = _moneyleague_quota_day_state(data)
        client_usage = daily_clients.get(client_key, {"writes": 0, "bytes": 0})
        client_writes = client_usage["writes"]
        client_bytes = client_usage["bytes"]

        if daily_count + 1 > MONEYLEAGUE_MAX_DAILY_WRITES:
            return "global_limit"
        if (
            client_writes + 1 > MONEYLEAGUE_MAX_DAILY_CLIENT_WRITES
            or client_bytes + daily_amount > MONEYLEAGUE_MAX_DAILY_CLIENT_BYTES
        ):
            return "client_limit"

        if kind == "registration":
            next_count = data["active_registrations"] + (1 if new_registration else 0)
            if (
                next_count > MONEYLEAGUE_MAX_ACTIVE_REGISTRATIONS
                or data["active_image_bytes"] + amount
                > MONEYLEAGUE_MAX_ACTIVE_IMAGE_BYTES
            ):
                return "global_limit"
            data["active_registrations"] = next_count
            data["active_image_bytes"] += amount
        elif kind == "comment":
            if (
                data["active_comments"] + 1 > MONEYLEAGUE_MAX_ACTIVE_COMMENTS
                or data["active_comment_bytes"] + amount
                > MONEYLEAGUE_MAX_ACTIVE_COMMENT_BYTES
                or data["total_comment_writes"] + 1
                > MONEYLEAGUE_MAX_TOTAL_COMMENT_WRITES
            ):
                return "global_limit"
            data["active_comments"] += 1
            data["active_comment_bytes"] += amount
            data["total_comment_writes"] += 1

        client_usage = {"writes": client_writes + 1, "bytes": client_bytes + daily_amount}
        daily_clients[client_key] = client_usage
        transaction.set(
            quota_ref,
            {
                "active_registrations": data["active_registrations"],
                "active_image_bytes": data["active_image_bytes"],
                "active_comments": data["active_comments"],
                "active_comment_bytes": data["active_comment_bytes"],
                "total_comment_writes": data["total_comment_writes"],
                "quota_day": quota_day,
                "daily_write_count": daily_count + 1,
                "daily_clients": daily_clients,
            },
            merge=True,
        )
        return "ok"

    return reserve(transaction)


def _adjust_moneyleague_storage(
    kind, count_delta=0, bytes_delta=0, lifetime_delta=0
):
    if kind not in {"registration", "comment"}:
        raise ValueError("Invalid Money League quota kind.")
    if (
        type(count_delta) is not int
        or type(bytes_delta) is not int
        or type(lifetime_delta) is not int
    ):
        raise ValueError("Invalid Money League quota adjustment.")
    if kind == "registration" and lifetime_delta:
        raise ValueError("Invalid Money League registration quota adjustment.")

    quota_ref = _ensure_moneyleague_quota_initialized()
    transaction = _get_fs().transaction()

    @firestore.transactional
    def adjust(transaction):
        data = _moneyleague_quota_values(quota_ref.get(transaction=transaction))
        if kind == "registration":
            count_field, bytes_field = "active_registrations", "active_image_bytes"
        else:
            count_field, bytes_field = "active_comments", "active_comment_bytes"
        next_count = data[count_field] + count_delta
        next_bytes = data[bytes_field] + bytes_delta
        updates = {count_field: next_count, bytes_field: next_bytes}
        if kind == "comment" and lifetime_delta:
            next_lifetime = data["total_comment_writes"] + lifetime_delta
            if next_lifetime < 0:
                raise RuntimeError("Money League comment quota would become negative.")
            updates["total_comment_writes"] = next_lifetime
        if next_count < 0 or next_bytes < 0:
            raise RuntimeError("Money League storage quota would become negative.")
        transaction.set(quota_ref, updates, merge=True)

    adjust(transaction)


def _delete_moneyleague_registration_once(registration_ref):
    quota_ref = _ensure_moneyleague_quota_initialized()
    transaction = _get_fs().transaction()

    @firestore.transactional
    def delete(transaction):
        registration = registration_ref.get(transaction=transaction)
        quota = _moneyleague_quota_values(quota_ref.get(transaction=transaction))
        if not registration.exists:
            return None
        if quota["active_registrations"] == 0:
            raise RuntimeError("Money League registration quota data is invalid.")
        transaction.delete(registration_ref)
        transaction.set(
            quota_ref,
            {"active_registrations": quota["active_registrations"] - 1},
            merge=True,
        )
        return registration.to_dict() or {}

    return delete(transaction)


def _moneyleague_screenshot_file_path(relative_path):
    prefix = "uploads/moneyleague_registrations/"
    if not isinstance(relative_path, str) or not relative_path.startswith(prefix):
        return None
    filename = relative_path[len(prefix):]
    if "/" in filename or "\\" in filename:
        return None
    if not MONEYLEAGUE_SCREENSHOT_NAME_RE.fullmatch(filename):
        return None
    return os.path.join(
        _app.config["UPLOAD_FOLDER"], "moneyleague_registrations", filename
    )


def _remove_moneyleague_screenshot(relative_path):
    file_path = _moneyleague_screenshot_file_path(relative_path)
    if not file_path:
        return 0, False
    try:
        stat_result = os.lstat(file_path)
    except FileNotFoundError:
        return 0, True
    except OSError:
        return 0, False
    try:
        os.remove(file_path)
    except OSError:
        return 0, False
    size = stat_result.st_size if stat.S_ISREG(stat_result.st_mode) else 0
    return size, True


def _validated_moneyleague_screenshot(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_image(file_storage.filename):
        return None
    safe_name = secure_filename(file_storage.filename)
    extension = os.path.splitext(safe_name)[1].lower().lstrip(".")
    expected_formats = {
        "jpg": "JPEG",
        "jpeg": "JPEG",
        "png": "PNG",
        "gif": "GIF",
        "webp": "WEBP",
    }
    expected_format = expected_formats.get(extension)
    if not expected_format:
        return None

    try:
        file_storage.stream.seek(0)
        image_bytes = file_storage.stream.read(_app.config["MAX_SCREENSHOT_BYTES"] + 1)
        file_storage.stream.seek(0)
    except (OSError, ValueError):
        return None
    if not image_bytes or len(image_bytes) > _app.config["MAX_SCREENSHOT_BYTES"]:
        return None

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(image_bytes)) as image:
                if image.format != expected_format:
                    return None
                width, height = image.size
                frame_count = getattr(image, "n_frames", 1)
                if (
                    width <= 0
                    or height <= 0
                    or width * height * frame_count > MONEYLEAGUE_MAX_IMAGE_PIXELS
                    or frame_count > MONEYLEAGUE_MAX_IMAGE_FRAMES
                ):
                    return None
                image.verify()
            with Image.open(BytesIO(image_bytes)) as image:
                for frame_index in range(getattr(image, "n_frames", 1)):
                    image.seek(frame_index)
                    image.load()
    except (
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        return None
    return image_bytes, "." + extension


def _save_moneyleague_screenshot(file_storage, validated_image=None):
    if validated_image is None:
        validated_image = _validated_moneyleague_screenshot(file_storage)
    if not validated_image:
        return None
    image_bytes, extension = validated_image
    filename = f"mreg_{int(datetime.utcnow().timestamp())}_{uuid.uuid4().hex[:8]}{extension}"
    save_dir = os.path.join(_app.config["UPLOAD_FOLDER"], "moneyleague_registrations")
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, filename)
    try:
        with open(save_path, "xb") as image_file:
            image_file.write(image_bytes)
    except OSError:
        try:
            os.remove(save_path)
        except OSError:
            pass
        raise
    return os.path.join("uploads", "moneyleague_registrations", filename)


def _release_reserved_moneyleague_upload(file_path, reserved_bytes, *, new_registration):
    if file_path:
        removed_bytes, removed = _remove_moneyleague_screenshot(file_path)
        if not removed:
            return False
        if removed_bytes:
            reserved_bytes = removed_bytes
    try:
        _adjust_moneyleague_storage(
            "registration",
            count_delta=-1 if new_registration else 0,
            bytes_delta=-reserved_bytes,
        )
    except Exception as error:
        _app.logger.error("Money League upload quota release failed: %s", error)
        return False
    return True


def _release_moneyleague_comment(content):
    try:
        _adjust_moneyleague_storage(
            "comment",
            count_delta=-1,
            bytes_delta=-_moneyleague_comment_quota_bytes(content),
        )
    except Exception as error:
        _app.logger.error("Money League comment quota release failed: %s", error)

def _delete_moneyleague_registration_comments(registration_ref):
    comments = registration_ref.collection("comments")
    batch = _get_fs().batch()
    pending_count = 0
    pending_bytes = 0
    for comment in comments.stream():
        comment_data = comment.to_dict() or {}
        batch.delete(comment.reference)
        pending_count += 1
        pending_bytes += _moneyleague_comment_quota_bytes(comment_data.get("content"))
        if pending_count == 400:
            batch.commit()
            _adjust_moneyleague_storage(
                "comment", count_delta=-pending_count, bytes_delta=-pending_bytes
            )
            batch = _get_fs().batch()
            pending_count = 0
            pending_bytes = 0
    if pending_count:
        batch.commit()
        _adjust_moneyleague_storage(
            "comment", count_delta=-pending_count, bytes_delta=-pending_bytes
        )


def _get_moneyleague_comments(registration_id):
    comments = []
    collection = _moneyleague_comments_collection(registration_id)
    if not collection:
        return comments
    try:
        query = collection.order_by("created_at", direction=firestore.Query.ASCENDING)
        for doc in query.stream():
            data = doc.to_dict() or {}
            created_at = data.get("created_at")
            created_at_display = "-"
            if hasattr(created_at, "strftime"):
                created_at_display = created_at.strftime("%Y-%m-%d %H:%M")
            author_name = data.get("author_name", "익명")
            author_ip_prefix = data.get("author_ip_prefix", "")
            author_display = data.get("author_display")
            if not author_display:
                author_display = f"{author_name} ({author_ip_prefix})" if author_ip_prefix else author_name
            comments.append({
                "id": doc.id,
                "content": data.get("content", ""),
                "author_id": data.get("author_id"),
                "author_name": author_name,
                "author_ip_prefix": author_ip_prefix,
                "author_display": author_display,
                "created_at_display": created_at_display,
            })
    except Exception as e:
        print(f"_get_moneyleague_comments error: {e}")
    return comments
