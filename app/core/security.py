import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from jwt import InvalidTokenError

from app.common import BusinessException, ErrorCode
from app.core.config import settings

OAUTH_STATE_COOKIE = "kakao_oauth_state"
ACCESS_TOKEN_COOKIE = "access_token"
OAUTH_STATE_COOKIE_PATH = "/api/auth/kakao/callback"


def _jwt_secret() -> str:
    secret = settings.jwt_secret_key.get_secret_value()
    if len(secret.encode("utf-8")) < 32:
        raise BusinessException(ErrorCode.AUTH_CONFIGURATION_ERROR)
    return secret


def create_oauth_state() -> str:
    return secrets.token_urlsafe(32)


def verify_oauth_state(expected_state: str | None, received_state: str | None) -> bool:
    if not expected_state or not received_state:
        return False
    return hmac.compare_digest(expected_state, received_state)


def create_access_token(user_id: int) -> str:
    secret = _jwt_secret()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    secret = _jwt_secret()
    try:
        return jwt.decode(token, secret, algorithms=[settings.jwt_algorithm])
    except InvalidTokenError as exc:
        raise BusinessException(ErrorCode.INVALID_ACCESS_TOKEN) from exc
