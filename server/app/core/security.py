"""JWT и хеширование кодов подтверждения."""

import hashlib
import hmac
import secrets
import string
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings

ALGORITHM = "HS256"


def create_access_token(user_id: int, role: str) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(days=settings.access_token_ttl_days)
    payload = {"sub": str(user_id), "role": role, "exp": expire}
    return jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> int:
    """Возвращает id пользователя. Бросает jwt.PyJWTError / ValueError при невалидном токене."""
    payload = jwt.decode(
        token,
        get_settings().secret_key.get_secret_value(),
        algorithms=[ALGORITHM],
        options={"require": ["exp", "sub"]},
    )
    return int(payload["sub"])


def generate_login_code(length: int = 6) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))


def hash_login_code(code: str) -> str:
    # HMAC с секретным ключом: обычный SHA-256 от 6 цифр подбирается мгновенно
    key = get_settings().secret_key.get_secret_value().encode()
    return hmac.new(key, code.encode(), hashlib.sha256).hexdigest()


def verify_login_code(code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_login_code(code), code_hash)
