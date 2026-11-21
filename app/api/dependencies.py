from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.common import BusinessException, ErrorCode
from app.core.security import ACCESS_TOKEN_COOKIE, decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository

bearer_scheme = HTTPBearer(auto_error=False, scheme_name="Service JWT")


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if not token and credentials is not None:
        token = credentials.credentials
    if not token:
        raise BusinessException(ErrorCode.INVALID_ACCESS_TOKEN)

    payload = decode_access_token(token)
    subject = payload.get("sub")
    try:
        if not isinstance(subject, str):
            raise ValueError
        user_id = int(subject)
    except ValueError:
        raise BusinessException(ErrorCode.INVALID_ACCESS_TOKEN) from None

    user = UserRepository(db).get_by_id(user_id)
    if user is None:
        raise BusinessException(ErrorCode.INVALID_ACCESS_TOKEN)
    return user
