import hashlib
import hmac
import os
from datetime import timedelta

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import settings

SESSION_COOKIE = "aiacm_session"
SESSION_MAX_AGE = int(timedelta(days=30).total_seconds())


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt_hex, expected_hex = encoded.split("$", 2)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32
        )
        return hmac.compare_digest(actual.hex(), expected_hex)
    except (ValueError, TypeError):
        return False


def _serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=salt)


def create_session(user_id: str) -> str:
    return _serializer("session").dumps({"sub": user_id})


def read_session(token: str) -> str | None:
    try:
        payload = _serializer("session").loads(token, max_age=SESSION_MAX_AGE)
        return str(payload["sub"])
    except (BadSignature, SignatureExpired, KeyError):
        return None


def create_verification_token(user_id: str) -> str:
    return _serializer("verify-email").dumps({"sub": user_id})


def read_verification_token(token: str) -> str | None:
    try:
        payload = _serializer("verify-email").loads(token, max_age=24 * 3600)
        return str(payload["sub"])
    except (BadSignature, SignatureExpired, KeyError):
        return None

