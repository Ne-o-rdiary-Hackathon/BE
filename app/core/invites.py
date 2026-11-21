import secrets
import string

from app.core.config import settings

_INVITE_CODE_ALPHABET = string.ascii_uppercase + string.digits


def generate_invite_code() -> str:
    return "".join(secrets.choice(_INVITE_CODE_ALPHABET) for _ in range(8))


def build_invite_url(invite_code: str) -> str:
    return f"{settings.frontend_base_url.rstrip('/')}/invite/{invite_code}"
