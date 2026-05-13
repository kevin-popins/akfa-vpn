import base64
import re
import secrets
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import pyotp
from argon2 import PasswordHasher
from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.core.config import settings

password_hasher = PasswordHasher()
session_serializer = URLSafeTimedSerializer(settings.session_secret, salt="akfa-session")
csrf_serializer = URLSafeTimedSerializer(settings.session_secret, salt="akfa-csrf")
login_token_serializer = URLSafeTimedSerializer(settings.session_secret, salt="akfa-login-token")
_login_attempts: dict[str, list[float]] = defaultdict(list)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except Exception:
        return False


def new_totp_secret() -> str:
    return pyotp.random_base32()


def verify_totp(secret: str | None, code: str | None) -> bool:
    if not secret:
        return False
    if not code:
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="AKFA")


def create_login_token(admin_id: int, purpose: str) -> str:
    return login_token_serializer.dumps({"admin_id": admin_id, "purpose": purpose})


def read_login_token(value: str | None, purpose: str, max_age_seconds: int = 300) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        data = login_token_serializer.loads(value, max_age=max_age_seconds)
    except BadSignature:
        return None
    if data.get("purpose") != purpose:
        return None
    return data


def create_session(admin_id: int, needs_2fa: bool = False) -> str:
    return session_serializer.dumps(
        {"admin_id": admin_id, "needs_2fa": needs_2fa, "issued_at": datetime.now(timezone.utc).isoformat()}
    )


def read_session(value: str | None, max_age_seconds: int = 60 * 60 * 12) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        return session_serializer.loads(value, max_age=max_age_seconds)
    except BadSignature:
        return None


def create_csrf_token(admin_id: int) -> str:
    return csrf_serializer.dumps({"admin_id": admin_id, "nonce": secrets.token_urlsafe(24)})


def verify_csrf_token(token: str | None, admin_id: int) -> bool:
    if not token:
        return False
    try:
        data = csrf_serializer.loads(token, max_age=60 * 60 * 12)
    except BadSignature:
        return False
    return data.get("admin_id") == admin_id


def check_rate_limit(key: str, limit: int = 8, window_seconds: int = 300) -> bool:
    now = time.time()
    attempts = [item for item in _login_attempts[key] if item > now - window_seconds]
    _login_attempts[key] = attempts
    if len(attempts) >= limit:
        return False
    attempts.append(now)
    return True


def _fernet() -> Fernet:
    key = settings.encryption_key.encode()
    try:
        return Fernet(key)
    except ValueError:
        normalized = base64.urlsafe_b64encode(settings.encryption_key.encode().ljust(32, b"0")[:32])
        return Fernet(normalized)


def encrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None


def mask_secret(text: str) -> str:
    redacted = text
    for marker in ["password", "passwd", "private_key", "token", "secret"]:
        redacted = redacted.replace(marker, f"{marker[:2]}***")
    redacted = re.sub(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
        "<uuid>",
        redacted,
    )
    return redacted
