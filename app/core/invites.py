import secrets
import string

INVITE_URL_PREFIX = "https://kankan.app/invite"
_INVITE_CODE_ALPHABET = string.ascii_uppercase + string.digits


def generate_invite_code() -> str:
    return "".join(secrets.choice(_INVITE_CODE_ALPHABET) for _ in range(8))


def build_invite_url(invite_code: str) -> str:
    return f"{INVITE_URL_PREFIX}/{invite_code}"
