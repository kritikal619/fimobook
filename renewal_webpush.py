"""Validated Web Push subscriptions and a stable server-only VAPID key."""
import base64
import json
import os
from urllib.parse import urlparse
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def public_key(path):
    with open(path, 'rb') as source:
        key = serialization.load_pem_private_key(source.read(), password=None)
    raw = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


def ensure_key(path):
    if os.path.exists(path):
        public_key(path)
        return
    key = ec.generate_private_key(ec.SECP256R1())
    encoded = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        public_key(path)
        return
    with os.fdopen(descriptor, 'wb') as output:
        output.write(encoded)


def validate_subscription(value):
    if not isinstance(value, dict):
        raise ValueError('기기를 다시 연결해주세요.')
    endpoint = value.get('endpoint')
    if not isinstance(endpoint, str) or len(endpoint) > 2048:
        raise ValueError('푸시 주소를 확인해주세요.')
    parsed = urlparse(endpoint)
    host = (parsed.hostname or '').lower()
    allowed = (host in {'fcm.googleapis.com', 'web.push.apple.com', 'updates.push.services.mozilla.com'}
               or host.endswith('.push.services.mozilla.com') or host.endswith('.notify.windows.com'))
    if (parsed.scheme != 'https' or not allowed or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.fragment):
        raise ValueError('지원되는 푸시 주소가 아닙니다.')
    keys = value.get('keys')
    if not isinstance(keys, dict):
        raise ValueError('푸시 암호화 키를 확인해주세요.')
    decoded = {}
    for name in ('p256dh', 'auth'):
        text = keys.get(name)
        if not isinstance(text, str) or len(text) > 128:
            raise ValueError('푸시 암호화 키를 확인해주세요.')
        try:
            decoded[name] = base64.b64decode(text + '=' * (-len(text) % 4), altchars=b'-_', validate=True)
        except (ValueError, TypeError):
            raise ValueError('푸시 암호화 키를 확인해주세요.') from None
    if len(decoded['auth']) != 16 or len(decoded['p256dh']) != 65:
        raise ValueError('푸시 암호화 키를 확인해주세요.')
    try:
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), decoded['p256dh'])
    except ValueError:
        raise ValueError('푸시 암호화 키를 확인해주세요.') from None
    return {'endpoint': endpoint, 'keys': {name: keys[name] for name in ('p256dh', 'auth')}}


def send_push(subscription, payload, key_path, ttl=300):
    from pywebpush import webpush
    return webpush(subscription_info=subscription, data=json.dumps(payload, ensure_ascii=False),
                   vapid_private_key=key_path, vapid_claims={'sub': 'https://fcbook.info'},
                   ttl=ttl, headers={'Urgency': 'high'}, timeout=10)
